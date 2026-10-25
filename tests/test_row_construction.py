"""The paper's streaming construction matches the dense canonical diagram."""

import pytest

from boxq.core.automaton import TableAutomaton
from boxq.core.catalog import lookup
from boxq.core.tables import compute
from boxq.formats.graph import PackedAutomaton


@pytest.mark.parametrize("name", ("SEA", "PRESENT", "SKINNY_8"))
def test_row_stream_matches_dense_cells_and_canonical_bytes(name):
    matrix = compute(lookup(name))
    n = (len(matrix) - 1).bit_length()
    dense = TableAutomaton(matrix, n)
    consumed = []

    def rows():
        for index, row in enumerate(matrix):
            consumed.append(index)
            yield row

    streamed = TableAutomaton.from_rows(rows(), n)
    assert consumed == list(range(len(matrix)))
    assert streamed.num_states() == dense.num_states()
    assert PackedAutomaton.from_automaton(streamed).to_bytes() == (
        PackedAutomaton.from_automaton(dense).to_bytes()
    )
    assert all(
        streamed.evaluate(a, b) == int(matrix[a, b])
        for a in range(len(matrix))
        for b in range(len(matrix))
    )


@pytest.mark.parametrize("rows", ([], [[0, 0]], [[0, 0]] * 3, [[0], [0]]))
def test_row_stream_rejects_incomplete_or_misdimensioned_input(rows):
    with pytest.raises(ValueError):
        TableAutomaton.from_rows(iter(rows), 1)
