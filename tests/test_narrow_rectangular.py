"""Narrow rectangular lookups through zero-padded square automata."""

import json

import numpy as np
import pytest

from boxq.cli.main import main
from boxq.core.automaton import TableAutomaton
from boxq.core.catalog import Lookup, lookup
from boxq.core.traversal import count_matches, iter_matches
from boxq.core.query import make
from boxq.core.tables import compute, padded

SHAPES = [(6, 4), (3, 5), (5, 2)]


def definition(f, n, m, kind):
    """Direct DDT/LAT definitions with the cleared origin, independent of compute."""
    table = np.zeros((1 << n, 1 << m), dtype=np.int64)
    for a in range(1 << n):
        for b in range(1 << m):
            if kind == "DDT":
                table[a, b] = sum(f[x] ^ f[x ^ a] == b for x in range(1 << n))
            else:
                signs = ((-1) ** ((a & x).bit_count() + (b & f[x]).bit_count()) for x in range(1 << n))
                table[a, b] = sum(signs) // 2
    table[0, 0] = 0
    return table


@pytest.mark.parametrize("n,m", SHAPES)
@pytest.mark.parametrize("kind", ["DDT", "LAT"])
def test_padded_queries_match_definitions(n, m, kind):
    f = Lookup(np.random.default_rng(n * 10 + m).integers(0, 1 << m, 1 << n).tolist(), m)
    table = definition(f, n, m, kind)
    assert np.array_equal(compute(f, kind), table)
    graph = TableAutomaton(padded(compute(f, kind)), max(n, m))
    a, b = np.meshgrid(np.arange(1 << n), np.arange(1 << m), indexing="ij")
    popcount = np.vectorize(lambda v: int(v).bit_count())
    weight = popcount(a) + popcount(b)
    domain = (a != 0) if kind == "DDT" else (a != 0) | (b != 0)
    cases = [
        (dict(value=0), domain & (table == 0)),
        (dict(at_least=2), domain & (table >= 2)),
        (dict(input=3), domain & (a == 3) & (table != 0)),
        (dict(output=1, value=0), domain & (b == 1) & (table == 0)),
        (dict(max_weight=3), domain & (weight <= 3) & (table != 0)),
        (dict(output_mask="1" + "*" * (m - 1)), domain & (b >> (m - 1) == 1) & (table != 0)),
        (dict(linear=[(1, 1, 0)], value=0), domain & ((a & 1) == (b & 1)) & (table == 0)),
        (dict(include_trivial=True, value=0), table == 0),
    ]
    for options, mask in cases:
        query = make(n, kind, m=m, **options)
        assert count_matches(graph, query) == int(mask.sum()), options
        want = {(int(x), int(y), int(table[x, y])) for x, y in np.argwhere(mask)}
        assert set(iter_matches(graph, query)) == want, options


def test_rectangular_lookup_limits(tmp_path):
    path = tmp_path / "f.json"
    path.write_text(json.dumps({"lut": [x % 16 for x in range(64)], "m": 4}))
    f = lookup("@" + str(path))
    assert (f.n, f.m) == (6, 4)
    with pytest.raises(ValueError):
        Lookup(list(range(1024)), 4)
    with pytest.raises(ValueError):
        Lookup([0, 1, 2, 3], 1)
    with pytest.raises(ValueError):
        compute(f, "BCT")
    with pytest.raises(ValueError):
        make(6, m=4, output=16)


def test_rectangular_cli(tmp_path, capsys):
    f = [int(v) for v in np.random.default_rng(1).integers(0, 16, 64)]
    path = tmp_path / "f.json"
    path.write_text(json.dumps({"lut": f, "m": 4}))
    table = definition(f, 6, 4, "DDT")
    main(["query", "@" + str(path), "--value", "0", "-f", "dkvp"])
    assert capsys.readouterr().out == f"count={int((table[1:] == 0).sum())}\n"
    main(["matrix", "@" + str(path), "--entries", "-f", "dkvp"])
    assert len(capsys.readouterr().out.splitlines()) == 64 * 16
    main(["stats", "@" + str(path), "--kind", "DDT", "-f", "dkvp"])
    row = dict(field.split("=") for field in capsys.readouterr().out.strip().split(","))
    assert (row["n"], row["m"]) == ("6", "4") and int(row["states"]) > 0
