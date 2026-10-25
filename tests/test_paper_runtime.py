"""Native paper benchmark execution and cleanup."""
from pathlib import Path
import json
import os
import shutil
import subprocess
import sys

import numpy as np
import pytest

from boxq.core.catalog import lookup
from boxq.core.tables import compute
from boxq.paper import benchmark as paper_benchmark
from boxq.native.table import compile_layers


def test_paper_benchmark_constructor_words():
    from boxq.core.regex import compile_regex
    m = compute(lookup("AES"))
    cases = {label: (q, mask) for label, q, mask, _ in paper_benchmark.paper_cases(m)}
    assert compile_layers(cases["fixed"][0], 8) == compile_layers(compile_regex("[01]"*5+"[23][01][23]").query(), 8)
    assert int(np.count_nonzero(cases["composite"][1])) == 1091


@pytest.mark.skipif(not (shutil.which("g++") or shutil.which("clang++")), reason="C++17 not available")
def test_real_table4_experiment_leaves_only_its_record(tmp_path):
    # Run the experiment as users do. Compilation caches and temporary
    # layouts are isolated; only timing.json is written to the output folder.
    working, scratch, cache, output = (tmp_path / name for name in ("working", "scratch", "cache", "out"))
    working.mkdir()
    scratch.mkdir()
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1]),
           "PYTHONDONTWRITEBYTECODE": "1", "BOXQ_CACHE": str(cache), "TMPDIR": str(scratch)}
    result = subprocess.run(
        [sys.executable, "-m", "boxq", "experiment", "timing", "--repeats", "2",
         "--output-dir", str(output)],
        cwd=working, env=env, text=True, capture_output=True, timeout=120)
    assert result.returncode == 0, result.stderr
    rows = json.loads((output / "timing.json").read_text())["rows"]
    assert [(r["name"], r["query"]) for r in rows] == list(paper_benchmark.CASES)
    assert all(float(r[b + "_us"]) >= 0 for r in rows for b in paper_benchmark.BACKENDS)
    assert [p.name for p in output.iterdir()] == ["timing.json"]
    assert list(working.iterdir()) == []
    assert list(scratch.iterdir()) == []


def test_failed_benchmark_cleans_temporary_layouts(tmp_path, monkeypatch):
    import tempfile
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(scratch))
    target = tmp_path / "table-4.tex"
    target.write_text("prior table")

    def fail_during_setup(matrix, folder, needed):
        (folder / "partial-layout").write_bytes(b"partial")
        raise RuntimeError("injected benchmark failure")

    monkeypatch.setattr(paper_benchmark, "layout_files", fail_during_setup)
    with pytest.raises(RuntimeError, match="injected"):
        paper_benchmark.measure_table4(repeats=1)
    assert target.read_text() == "prior table"
    assert list(scratch.iterdir()) == []
    assert not list(tmp_path.rglob("*.json"))
