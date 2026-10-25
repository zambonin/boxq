"""Recovered constructors and graph sharing are checked against dense definitions."""

import shutil

import pytest

from boxq.core.catalog import lookup
from boxq.core.tables import compute
from boxq.core.automaton import TableAutomaton
from boxq.native.build import build
from boxq.native.file_ops import level_statistics
from boxq.native.table import NativeTable


@pytest.mark.skipif(not shutil.which("g++"), reason="C++17 compiler required")
def test_native_construction_and_sharing(tmp_path):
    kind = "DDT"
    lut = lookup("PRESENT")
    matrix = compute(lut, kind)
    file = tmp_path / "present.qnf"
    result = build(lut, kind, file, verify=True, partition_mib=16)
    assert result["states"] == TableAutomaton(matrix, 4).num_states()
    with NativeTable(file) as table:
        assert all(table.evaluate(a, b) == int(matrix[a, b]) for a in range(16) for b in range(16))
    with pytest.raises(ValueError, match="DDTs only"):
        build(lut, "LAT", tmp_path / "lat.qnf")
    sharing = level_statistics(file)
    for row in sharing["levels"]:
        side = row["block_side"]
        patterns = {
            tuple(matrix[a : a + side, b : b + side].flat)
            for a in range(0, 16, side)
            for b in range(0, 16, side)
        }
        assert row["distinct_blocks"] == len(patterns)
        assert row["blocks"] == (16 // side) ** 2
