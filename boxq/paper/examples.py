"""Compute numerical examples outside the printed tables."""
from dataclasses import replace
import numpy as np
from ..core import catalog, query as queries
from ..core.traversal import evaluate_detailed
from ..core.automaton import TableAutomaton
from ..core.encoding import word_of, cell_of
from ..core.metrics import differential_spectrum
from ..core.tables import compute
from .tables import present_blocks


def example_numbers(*, fi_record=None):
    """Deterministic numerical examples outside table cells; no saved observations.

    ``fi_record`` is the verified FI:0000 large-experiment record, whose
    summary and histogram were computed from the fully checked graph.
    """
    matrix = compute(catalog.lookup("PRESENT"))
    blocks = present_blocks(matrix)
    sea = TableAutomaton(compute(catalog.lookup("SEA")), 3)
    counts = {
        "catalog_names": len(catalog.names()),
        "distinct_lookups": len(catalog.select(all_names=True, unique=True)),
        "permutation_names": sum(len(set(lut)) == len(lut) for _, lut in catalog.select(all_names=True)),
        "distinct_permutations": sum(len(set(lut)) == len(lut) for _, lut in catalog.select(all_names=True, unique=True)),
        "present_blocks": sum(blocks.values()), "present_distinct_blocks": len(blocks),
        "present_zero_blocks": blocks[(0, 0, 0, 0)],
        "present_top_three_blocks": sum(c for _, c in blocks.most_common(3)),
        "sea_states": sea.num_states(), "sea_terminals": sea.distinct_values(),
        "sea_internal_states": sea.num_states() - sea.distinct_values(),
        "sea_nonzero_entries": int(np.count_nonzero(compute(catalog.lookup("SEA")))),
        "aes_lat_distinct_values": len(np.unique(compute(catalog.lookup("AES"), "LAT"))),
        "noekeon_present_spectra_equal": differential_spectrum(TableAutomaton(compute(catalog.lookup("Noekeon")), 4))
            == differential_spectrum(TableAutomaton(matrix, 4)),
    }
    for name in ("AES", "Skipjack"):
        graph = TableAutomaton(compute(catalog.lookup(name)), 8)
        maximum = max(graph.value(s) for s in graph.nodes() if graph.is_terminal(s))
        hits, stats = evaluate_detailed(graph, queries.value_equals(maximum))
        counts[name.lower() + "_extremal_results"] = len(hits)
        counts[name.lower() + "_extremal_expanded"] = stats["expanded_product_states"]
        if name == "AES":
            q = replace(queries.value_equals(maximum), possible=lambda lo, hi: lo != 0 or hi != 0)
            _, unbounded = evaluate_detailed(graph, q)
            counts["aes_extremal_without_threshold_bound"] = unbounded["expanded_product_states"]
    for name, value in counts.items():
        yield dict(name=name, value=value, unit="", source="computed")
    yield dict(name="encoding_a5_b3", value="".join(map(str, word_of(5, 3, 3))), unit="word", source="computed")
    yield dict(name="figure1_highlight_a", value=cell_of((3, 2, 0))[0], unit="", source="decoded word 320")
    yield dict(name="figure1_highlight_b", value=cell_of((3, 2, 0))[1], unit="", source="decoded word 320")
    if fi_record:
        summary = fi_record["summary"]
        for key in ("n", "maximum", "states", "ratio", "graph_bytes", "dense_bytes", "bitmap_bytes"):
            unit = "bytes" if key.endswith("_bytes") else ""
            yield dict(name="fi_" + key, value=summary[key], unit=unit, source="graph")
        histogram = fi_record["metrics"]["histogram_all_normalized_coordinates"]
        yield dict(name="fi_cells", value=sum(histogram.values()), unit="cells", source="graph")
