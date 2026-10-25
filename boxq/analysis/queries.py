"""Standard query families and independent result checks."""
from dataclasses import replace

import numpy as np

from ..core.automaton import TableAutomaton
from ..core.tables import compute
from ..core import query as q
from ..core.traversal import evaluate_detailed


def presets(matrix, kind="DDT"):
    """The seven DDT examples, or the LAT/BCT extremal example with zero-only pruning.

    The corresponding NumPy masks are independent of the word-automaton code.
    """
    n = (len(matrix) - 1).bit_length()
    N = 1 << n
    x = np.arange(N)
    a, b = x[:, None], x[None, :]
    w = np.array([int(v).bit_count() for v in x])
    maximum = int(np.abs(matrix).max())
    high = max(1, maximum)
    nz = matrix != 0
    threshold = max(1, maximum // 2)
    fixed = int(("01" * n)[-n:], 2)
    extremal = q.magnitude_at_least(high) if kind == "LAT" else q.value_equals(high)
    if kind != "DDT":
        extremal = replace(extremal, possible=lambda lo, hi: lo != 0 or hi != 0)
        return [("extremal", extremal, np.abs(matrix) >= high, high)]
    imp = replace(q.impossible(q.fixed_input(1, n)), possible=None)
    impossible_mask = (a == 1) & (matrix == 0)
    composite = replace(q.hamming_weight_at_most(4), accept=lambda v: abs(v) >= threshold,
                        possible=lambda lo, hi: max(abs(lo), abs(hi)) >= threshold)
    result = [
        ("fixed", q.fixed_input(fixed, n), (a == fixed) & nz, None),
        ("truncated", q.truncated(set(range(min(n, 2))), n), (a >= N - N // (1 << min(n, 2))) & nz, None),
        ("impossible", imp, impossible_mask, 0),
        ("extremal", extremal, np.abs(matrix) >= high, high),
        ("weight2", q.hamming_weight_at_most(2), (w[:, None] + w[None, :] <= 2) & nz, None),
        ("diagonal", q.diagonal(n), (a == b) & nz, None),
        ("composite", composite, (w[:, None] + w[None, :] <= 4) & (np.abs(matrix) >= threshold), threshold),
    ]
    return result


def query_summary(entries, kinds=("DDT",)):
    for name, lookup in entries:
        n = (len(lookup) - 1).bit_length()
        for kind in kinds:
            if kind == "BCT" and len(set(lookup)) != len(lookup):
                continue
            matrix = compute(lookup, kind)
            graph = TableAutomaton(matrix, n)
            for label, query, mask, threshold in presets(matrix, kind):
                hits, counters = evaluate_detailed(graph, query)
                # Compare exact sets, not just agreement between two counters.
                want = {(int(a), int(b), int(matrix[a, b])) for a, b in np.argwhere(mask)}
                if set(hits) != want:
                    raise RuntimeError("query/independent matrix result disagreement")
                yield {"name": name, "n": n, "table": kind, "query": label,
                       "threshold": threshold, "matches": len(hits),
                       "expanded": counters["expanded_product_states"],
                       "checked": counters["product_states"]}
