"""CLI, native build, and benchmark regressions."""
import io
from itertools import product
import shutil

import numpy as np
import pytest

from boxq.core.automaton import TableAutomaton
from boxq.core.tables import compute
from boxq.core import catalog
from boxq.core.catalog import lookup
from boxq.formats import text as output
from boxq.cli.main import main
from boxq.core.traversal import iter_matches
from boxq.core.query import make


@pytest.mark.parametrize("format", ["csv", "dkvp", "tex"])
def test_output(format):
    out = io.StringIO()
    output.write([dict(name="SKINNY_8", states=915, ratio=10.0)], out, format=format, precision=0)
    s = out.getvalue()
    assert "915" in s and "10" in s
    if format == "tex":
        assert r"SKINNY\_8" in s
        assert r"\begin{tabular}" in s
    if format == "dkvp":
        assert s == "name=SKINNY_8,states=915,ratio=10\n"


def test_output_failure_does_not_replace_file(tmp_path):
    target = tmp_path / "previous.csv"
    target.write_text("keep me")
    with pytest.raises(ValueError):
        with output.destination(target) as f:
            output.write([dict(name="a,b")], f, format="dkvp")
    assert target.read_text() == "keep me"
    assert len(list(tmp_path.iterdir())) == 1


def test_input_errors_and_nonpermutation():
    with pytest.raises(ValueError):
        compute(lookup("CMEA"), "BCT")
    m = compute(lookup("CMEA"))
    assert np.any(m[1:, 0] > 0)
    with pytest.raises(ValueError):
        lookup("FI:0")
    with pytest.raises(ValueError):
        compute([0, 1, 2])
    with pytest.raises(ValueError):
        make(4, input=16)


@pytest.mark.parametrize("command", [
    ["list", "--format", "dkvp"],
    ["matrix", "SEA", "--format", "tex"],
    ["stats", "PRESENT", "--kind", "DDT", "--format", "csv"],
    ["stats", "PRESENT", "SEA", "--kind", "DDT"],
    ["spectrum", "SEA"],
    ["query", "PRESENT", "--input", "5"],
    ["query", "PRESENT", "--input", "5", "--mode", "entries", "--limit", "2"],
    ["query", "PRESENT", "--against", "Noekeon"],
])
def test_cli(command, capsys):
    main(command)
    assert capsys.readouterr().out


@pytest.mark.skipif(not (shutil.which("g++") or shutil.which("clang++")), reason="C++17 compiler not installed")
def test_native_build_query(tmp_path):
    kind = "DDT"
    from boxq.native.build import build
    from boxq.native.file_ops import convert
    from boxq.native.table import NativeTable
    values = lookup("PRESENT")
    path = tmp_path / "graph.qnf"
    result = build(values, kind, path, verify=True)
    assert result["n"] == 4
    packed = tmp_path / "graph.qdd"
    convert(path, packed, "pack")
    m = compute(values, kind)
    q = make(4, kind, input=5)
    want = set(iter_matches(TableAutomaton(m, 4), q))
    for file in (path, packed):
        with NativeTable(file) as table:
            for a, b in product(range(16), repeat=2):
                assert table.evaluate(a, b) == m[a, b]
            assert table.run(q)["count"] == len(want)
            assert set(table.run(q, mode="enumerate")["entries"]) == want
    assert not list(tmp_path.glob(".boxq-*"))


@pytest.mark.skipif(not (shutil.which("g++") or shutil.which("clang++")), reason="C++17 compiler not installed")
def test_benchmark_and_search():
    from boxq.paper.benchmark import measure
    from boxq.core.search import measure as search
    from boxq.paper.benchmark import BACKENDS, paper_cases
    rows = list(measure(catalog.select(["PRESENT"]), ["DDT"], backends=BACKENDS, case_factory=paper_cases,
                        queries=["fixed"], repeats=2, warmups=1))
    assert len(rows) == 4
    assert all(r["matches"] == 7 and r["median_us"] >= 0 for r in rows)
    rows = list(search(cases=4, repeats=1))
    assert len(rows) == 2
    assert all(r["cases"] == 4 and r["feasible"] == 2 for r in rows)
