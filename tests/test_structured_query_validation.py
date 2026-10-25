"""Correctness checks on structured S-boxes, without publication measurements."""

import shutil

import numpy as np
import pytest

from boxq.analysis.queries import presets
from boxq.core.automaton import TableAutomaton
from boxq.core.catalog import lookup
from boxq.core.traversal import count_matches, evaluate_detailed
from boxq.core.tables import compute
from boxq.experiments.reference import count_query, table as reference_table
from boxq.formats.graph import PackedAutomaton
from boxq.native.table import NativeTable


FAMILIES = ("fixed", "truncated", "impossible", "extremal", "weight2", "diagonal", "composite")


@pytest.fixture(scope="module", params=("CSS", "SKINNY_8"))
def structured_table(request):
    lut = lookup(request.param)
    matrix = compute(lut, "DDT")
    np.testing.assert_array_equal(matrix, reference_table(lut, "DDT"))
    assert matrix.shape == (256, 256)
    graph = TableAutomaton(matrix, 8)
    cases = {
        label: (
            query,
            {(int(a), int(b), int(matrix[a, b])) for a, b in np.argwhere(mask)},
        )
        for label, query, mask, _ in presets(matrix)
    }
    assert tuple(cases) == FAMILIES
    return matrix, graph, cases


@pytest.fixture(scope="module")
def packed_table(structured_table, tmp_path_factory):
    _, graph, _ = structured_table
    directory = tmp_path_factory.mktemp("structured-query")
    path = directory / "table.qdd"
    path.write_bytes(PackedAutomaton.from_automaton(graph).to_bytes())
    return path, directory / "native-cache"


@pytest.mark.parametrize("family", FAMILIES)
def test_python_queries_match_exhaustive_results(structured_table, family):
    matrix, graph, cases = structured_table
    query, expected = cases[family]
    entries, counters = evaluate_detailed(graph, query)
    assert len(entries) == len(expected)
    assert set(entries) == expected
    assert count_matches(graph, query) == len(expected)
    # The independent tuple graph also checks distinct expanded products,
    # including final query states that reject the candidate word.
    assert count_query(matrix, query) == (len(expected), counters["expanded_product_states"])


@pytest.mark.skipif(
    not (shutil.which("g++") or shutil.which("clang++")), reason="C++17 compiler required"
)
@pytest.mark.parametrize("bounds", (False, True))
@pytest.mark.parametrize("family", FAMILIES)
def test_native_queries_match_exhaustive_results(structured_table, packed_table, family, bounds):
    matrix, _, cases = structured_table
    query, expected = cases[family]
    path, cache = packed_table
    with NativeTable(path, cache=cache) as table:
        counted = table.run(query, bounds=bounds)
        enumerated = table.run(query, mode="enumerate", bounds=bounds, max_output=matrix.size)
    assert counted["count"] == len(expected)
    assert enumerated["count"] == len(expected)
    assert enumerated["output_entries"] == len(expected)
    assert len(enumerated["entries"]) == len(expected)
    assert set(enumerated["entries"]) == expected
