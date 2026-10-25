"""Statistics and standard query families, computed from lookup values."""

import numpy as np
from ..core.automaton import TableAutomaton
from ..formats._bits import signed_width
from ..core.tables import compute, padded


def payload_sizes(n, states, histogram, kind="DDT", *, m=None):
    """Header-free sizes with ONE final byte rounding per representation.

    Dense cells store indices into the complete signed value dictionary.
    Bitmap omits zeros and uses a dictionary of nonzero signed values.
    Bounds, rank directories, query workspace and Python objects are excluded.
    """
    values = sorted(v for v, count in histogram.items() if count)
    positive = [v for v in values if v != 0]
    nonzero = sum(c for v, c in histogram.items() if v != 0)
    cells = 1 << (n + (n if m is None else m))
    iw = max(1, (states - 1).bit_length())
    graph = 4 * states * iw + len(values) * signed_width(values)
    dense = cells * max(0, (len(values) - 1).bit_length()) + len(values) * signed_width(values)
    bitmap = cells + len(positive) * signed_width(positive)
    bitmap += nonzero * max(0, (len(positive) - 1).bit_length())
    return {
        "graph_bytes": (graph + 7) // 8,
        "dense_bytes": (dense + 7) // 8,
        "bitmap_bytes": (bitmap + 7) // 8,
    }


def summarize(name, kind, n, states, histogram, *, m=None):
    """Summarize a 2^n x 2^m table; ``m`` appears only for rectangular tables."""
    return {
        "name": name,
        "n": n,
        **({"m": m} if m is not None and m != n else {}),
        "table": kind,
        "maximum": max(abs(v) for v in histogram),
        "states": states,
        "ratio": (1 << (n + (n if m is None else m))) / states,
        **payload_sizes(n, states, histogram, kind, m=m),
    }


def stats(entries, kinds=("DDT", "LAT", "BCT")):
    # Cache only the tiny summary across aliases, not the full matrices/graphs.
    cached = {}
    for name, lookup in entries:
        n = (len(lookup) - 1).bit_length()
        m = getattr(lookup, "m", n)
        for kind in kinds:
            if kind == "BCT" and (m != n or len(set(lookup)) != len(lookup)):
                continue
            key = (tuple(lookup), m, kind)
            if key not in cached:
                matrix = compute(lookup, kind)
                # A rectangular table is stored as its zero-padded square automaton.
                graph = TableAutomaton(padded(matrix), max(n, m))
                values, counts = np.unique(matrix, return_counts=True)
                hist = {int(v): int(c) for v, c in zip(values, counts)}
                cached[key] = summarize(name, kind, n, graph.num_states(), hist, m=m)
            yield {**cached[key], "name": name}


def spectrum(matrix, kind):
    domain = (
        matrix[1:, :] if kind == "DDT" else matrix[1:, 1:] if kind == "BCT" else matrix.ravel()[1:]
    )
    values, counts = np.unique(domain, return_counts=True)
    return [{"value": int(v), "count": int(c)} for v, c in zip(values, counts)]
