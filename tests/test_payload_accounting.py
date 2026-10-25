"""Payload models agree with independently serialized, header-free objects."""

import numpy as np
import pytest

from boxq.core.catalog import lookup
from boxq.core.tables import compute
from boxq.core.automaton import TableAutomaton
from boxq.analysis.reports import payload_sizes
from boxq.formats.graph import PackedAutomaton
from boxq.formats.dense import DensePacked
from boxq.formats.bitmap import BitmapPacked
from boxq.experiments.reference import payload_sizes as independent_sizes


@pytest.mark.parametrize("name", ["SEA", "PRESENT", "Ascon", "CSS"])
@pytest.mark.parametrize("kind", ["DDT", "LAT", "BCT"])
def test_models_match_actual_packed_streams(name, kind):
    matrix = compute(lookup(name), kind)
    n = (len(matrix) - 1).bit_length()
    graph = TableAutomaton(matrix, n)
    values, counts = np.unique(matrix, return_counts=True)
    sizes = payload_sizes(
        n, graph.num_states(), {int(v): int(c) for v, c in zip(values, counts)}, kind
    )
    assert sizes == independent_sizes(matrix, graph.num_states())
    assert sizes["graph_bytes"] == len(PackedAutomaton.from_automaton(graph).data)
    assert sizes["dense_bytes"] == len(DensePacked.from_matrix(matrix.tolist(), n).data)
    assert sizes["bitmap_bytes"] == len(
        BitmapPacked.from_matrix(matrix.tolist(), n, rank_block=0).data
    )
