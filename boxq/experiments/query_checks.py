"""Both pruning policies with independent matrix and reference-oracle checks."""

from dataclasses import replace

import numpy as np

from ..core.automaton import TableAutomaton
from ..core.tables import compute
from ..core.traversal import evaluate_detailed
from ..analysis.queries import presets
from .reference import count_query

COUNTER_POLICY = (
    "distinct non-pruned (table_state, query_state, depth), including rejected final states"
)


def pruning_rows(entries):
    rows = []
    for kind in ("LAT", "BCT"):
        for name, lookup in entries:
            matrix = compute(lookup, kind)
            n = (len(matrix) - 1).bit_length()
            _, zero_query, mask, threshold = presets(matrix, kind)[0]
            strong = (
                (lambda lo, hi: max(abs(lo), abs(hi)) >= threshold)
                if kind == "LAT"
                else (lambda lo, hi: hi >= threshold)
            )
            bound_query = replace(zero_query, possible=strong)
            graph = TableAutomaton(matrix, n)
            expected = {(int(a), int(b), int(matrix[a, b])) for a, b in np.argwhere(mask)}
            expanded = []
            for query in (zero_query, bound_query):
                hits, stats = evaluate_detailed(graph, query)
                independent_count, independent_expanded = count_query(matrix, query)
                if (
                    set(hits) != expected
                    or independent_count != len(expected)
                    or independent_expanded != stats["expanded_product_states"]
                ):
                    raise RuntimeError(
                        "pruning result or work counter differs from independent reference"
                    )
                expanded.append(stats["expanded_product_states"])
            rows.append(
                {
                    "table": kind,
                    "sbox": name,
                    "threshold": threshold,
                    "results": len(expected),
                    "expanded": expanded[0],
                    "zero_expanded": expanded[0],
                    "bound_expanded": expanded[1],
                }
            )
    return rows


def illustrative_rows(entries):
    """Validate Table 3 work counts with an independent tuple-graph traversal."""
    from ..analysis.queries import query_summary

    rows = list(query_summary(entries, ("DDT",)))
    index = {(r["name"], r["query"]): r for r in rows}
    for name, lookup in entries:
        matrix = compute(lookup, "DDT")
        for label, query, _, _ in presets(matrix):
            row = index[name, label]
            if count_query(matrix, query) != (row["matches"], row["expanded"]):
                raise RuntimeError("illustrative query work differs from the independent oracle")
    return rows
