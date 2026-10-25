"""Exhaustive and sampled random-permutation baselines with retained inputs."""

from itertools import permutations
import statistics

import numpy as np

from ..core.tables import compute
from .reference import state_count
from .provenance import lookup_digest


def run(*, widths=range(3, 10), seed=1):
    """Keep the prototype's sequential seed-1 stream for widths four to eight.

    Width nine continues the same stream with five samples. Width three is
    exhaustive and consumes no random numbers. The separate 16-bit experiment
    uses seed 2026 and the fully verified native builder.
    """
    widths = tuple(sorted(set(widths)))
    if set(widths) - set(range(3, 10)):
        raise ValueError("small random widths must be 3..9")
    rng = np.random.default_rng(seed)
    rows = []
    for n in range(3, max(widths, default=3) + 1):
        count = 40320 if n == 3 else 200 if n < 8 else 60 if n == 8 else 5
        inputs = (
            permutations(range(8))
            if n == 3
            else (rng.permutation(1 << n).tolist() for _ in range(count))
        )
        samples = []
        for index, values in enumerate(inputs):
            if n not in widths:
                continue
            states = state_count(compute(list(values), "DDT"))
            samples.append(
                {
                    "sample": index,
                    "input": list(values),
                    "input_sha256": lookup_digest(values),
                    "states": states,
                    "ratio": (1 << (2 * n)) / states,
                }
            )
        if samples:
            ratios = [s["ratio"] for s in samples]
            rows.append(
                {
                    "n": n,
                    "seed": None if n == 3 else seed,
                    "rng": "exhaustive lexicographic" if n == 3 else "NumPy PCG64",
                    "samples": samples,
                    "count": count,
                    "median": statistics.median(ratios),
                    "min": min(ratios),
                    "max": max(ratios),
                }
            )
    return {"rows": rows, "seed": seed, "stream": "one sequential PCG64 stream through widths 4..9"}
