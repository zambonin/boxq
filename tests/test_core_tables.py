"""Table, format, and query regressions."""

from itertools import product

import pytest

from boxq.core.automaton import TableAutomaton
from boxq.core.tables import compute
from boxq.core.catalog import lookup
from boxq.core import catalog
from boxq.analysis import reports
from boxq.analysis import queries as query_reports
from boxq.formats.graph import PackedAutomaton
from boxq.formats.dense import DensePacked, DenseRangePacked
from boxq.formats.bitmap import BitmapPacked
from boxq.core.traversal import count_matches, iter_matches
from boxq.core.query import make


@pytest.mark.parametrize("kind", ["DDT", "LAT", "BCT"])
@pytest.mark.parametrize("name", ["SEA", "PRESENT"])
def test_definitions_and_roundtrips(kind, name):
    lut = lookup(name)
    N = len(lut)
    n = (N - 1).bit_length()
    raw = compute(lut, kind, raw=True)
    inv = {v: i for i, v in enumerate(lut)}
    for a, b in product(range(N), repeat=2):
        if kind == "DDT":
            want = sum((lut[x] ^ lut[x ^ a]) == b for x in range(N))
        elif kind == "LAT":
            want = (
                sum((a & x).bit_count() % 2 == (b & lut[x]).bit_count() % 2 for x in range(N))
                - N // 2
            )
        else:
            want = sum((inv[lut[x] ^ b] ^ inv[lut[x ^ a] ^ b]) == a for x in range(N))
        assert raw[a, b] == want
    m = compute(lut, kind)
    graph = TableAutomaton(m, n)
    packed = PackedAutomaton.from_automaton(graph)
    formats = [
        packed,
        DensePacked.from_matrix(m.tolist(), n),
        DenseRangePacked.from_matrix(m.tolist(), n),
        BitmapPacked.from_matrix(m.tolist(), n, rank_block=512),
    ]
    for a, b in product(range(N), repeat=2):
        assert graph.evaluate(a, b) == m[a, b]
        assert all(f.evaluate(a, b) == m[a, b] for f in formats)


def test_catalog_and_payloads():
    assert len(catalog.names()) == 288
    assert len(catalog.select(all_names=True, unique=True)) == 259
    rows = list(reports.stats(catalog.select(["PRESENT", "SEA", "Noekeon"]), ["DDT"]))
    assert [(r["states"], r["graph_bytes"], r["dense_bytes"], r["bitmap_bytes"]) for r in rows] == [
        (39, 119, 66, 45),
        (9, 19, 9, 9),
        (34, 104, 66, 45),
    ]
    assert lookup("SKINNY_8") == lookup("Romulus")


def test_original_query_examples():
    rows = list(
        query_reports.query_summary(catalog.select(["PRESENT", "AES"]), ["DDT", "LAT", "BCT"])
    )
    assert [(r["matches"], r["expanded"]) for r in rows] == [
        (7, 16),
        (26, 19),
        (12, 11),
        (24, 28),
        (0, 24),
        (5, 15),
        (63, 49),
        (36, 53),
        (2, 43),
        (127, 146),
        (8128, 1403),
        (129, 135),
        (255, 779),
        (24, 232),
        (116, 146),
        (1091, 1492),
        (1275, 17098),
        (510, 5459),
    ]


@pytest.mark.parametrize("kind", ["DDT", "LAT", "BCT"])
@pytest.mark.parametrize(
    "opts",
    [
        dict(input=5),
        dict(max_weight=3),
        dict(same=True),
        dict(value=0),
        dict(regex="[03]*"),
        dict(linear=[(3, 5, 1)]),
    ],
)
def test_queries(kind, opts):
    m = compute(lookup("PRESENT"), kind)
    g = TableAutomaton(m, 4)
    q = make(4, kind, **opts)
    found = set(iter_matches(g, q))
    expected = set()
    for a, b in product(range(16), repeat=2):
        domain = (
            a != 0 if kind == "DDT" else a != 0 and b != 0 if kind == "BCT" else (a, b) != (0, 0)
        )
        if not domain:
            continue
        if "input" in opts and a != opts["input"]:
            continue
        if "max_weight" in opts and a.bit_count() + b.bit_count() > opts["max_weight"]:
            continue
        if ("same" in opts or "regex" in opts) and a != b:
            continue
        if "linear" in opts and ((a & 3).bit_count() ^ (b & 5).bit_count()) & 1 != 1:
            continue
        value = int(m[a, b])
        if (value == opts["value"]) if "value" in opts else (value != 0):
            expected.add((a, b, value))
    assert found == expected
    assert count_matches(g, q) == len(expected)
