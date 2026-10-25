"""Three-round PRESENT fixed-endpoint characteristic search and fresh timings.

The objective is the product of local DDT probabilities, not a differential hull.
All backends share the same endpoints, search policy and local row cache.
"""

from itertools import product
from pathlib import Path
import statistics
import struct
import tempfile
import numpy as np
from .catalog import lookup
from .tables import compute
from ..native.file_ops import call
from ..analysis.layouts import BACKENDS, layout_files, affinity

S = tuple(lookup("PRESENT"))
P = tuple(63 if i == 63 else 16 * i % 63 for i in range(64))


def weight(value):
    if value <= 0 or value & (value - 1):
        raise ValueError("PRESENT multiplicities must be powers of two")
    return 4 - (value.bit_length() - 1)


def matrix():
    m = [[0] * 16 for _ in range(16)]
    for a in range(16):
        for x in range(16):
            m[a][S[x] ^ S[x ^ a]] += 1
    return m


def permute(x):
    return sum(((x >> i & 1) << P[i] for i in range(64)))


def inv_permute(x):
    return sum(((x >> P[i] & 1) << i for i in range(64)))


def endpoint_cases(count):
    if type(count) is not int or not 1 <= count <= 240:
        raise ValueError("cases must be 1..240")
    m = matrix()
    rows = [[(b, c) for b, c in enumerate(row) if c] for row in m]
    cases = []
    for i in range(count):
        x = 1 + i // 16 << 4 * (i % 16)
        if i % 2 == 0:
            y = x
            for r in range(3):
                z = 0
                for j in range(16):
                    choices = rows[y >> 4 * j & 15]
                    b, _ = choices[(i + r + j) % len(choices)]
                    z |= b << 4 * j
                y = permute(z)
            label = "derived-positive-endpoint"
        else:
            y = 1 << 13 * i % 64
            label = "single-bit-endpoint"
        cases.append(dict(input=x, output=y, case_type=label))
    return cases


def independent(case, m):
    """Exhaustive first-two-round Cartesian expansion; no optimizing pruning."""
    rows = [[(b, weight(c)) for b, c in enumerate(row) if c] for row in m]
    target = inv_permute(case["output"])
    best = None
    ways = 0
    trails = 0
    witness = None

    def choices(x):
        active = [(j, rows[x >> 4 * j & 15]) for j in range(16) if x >> 4 * j & 15]
        for branch in product(*(r for j, r in active)):
            z = sum((b << 4 * j for (j, _), (b, w) in zip(active, branch)))
            yield (permute(z), sum((w for b, w in branch)))

    for x1, w1 in choices(case["input"]):
        for x2, w2 in choices(x1):
            trails += 1
            w = w1 + w2
            for j in range(16):
                c = m[x2 >> 4 * j & 15][target >> 4 * j & 15]
                if not c:
                    break
                w += weight(c)
            else:
                path = [x1, x2, case["output"]]
                if best is None or w < best:
                    best = w
                    ways = 1
                    witness = path
                elif w == best:
                    ways += 1
                    witness = min(witness, path)
    return dict(
        weight=-1 if best is None else best,
        optimal_characteristics=ways,
        witness=[0, 0, 0] if witness is None else witness,
        enumerated_two_round_prefixes=trails,
    )


def measure(*, backends=("packed", "int32"), cases=240, repeats=15, cpu=None, records=None):
    if not 1 <= repeats <= 1000:
        raise ValueError("repeats must be 1..1000")
    inputs = endpoint_cases(cases)
    expected = [independent(case, matrix()) for case in inputs]
    with affinity(cpu), tempfile.TemporaryDirectory(prefix="boxq-search-") as tmp:
        folder = Path(tmp)
        paths = layout_files(compute(list(S)), folder, {BACKENDS[b][0] for b in backends})
        casefile = folder / "cases.bin"
        casefile.write_bytes(b"".join(struct.pack("<QQ", c["input"], c["output"]) for c in inputs))
        for backend in backends:
            layout, variant = BACKENDS[backend]
            variant_id = {"mapped": 0, "int32": 1, "indexed": 2, "decoded-graph": 3}[variant]
            report = call(
                "present", paths[layout], casefile, repeats, 10_000_000, variant_id, quiet=True
            )
            for sample in report["samples"]:
                want = expected[sample["case"]]
                if any(
                    sample[key] != want[key]
                    for key in ("weight", "optimal_characteristics", "witness")
                ):
                    raise RuntimeError("PRESENT search disagrees with exhaustive reference")
            times = [r["elapsed_ns"] / 1000 for r in report["samples"]]
            if records is not None:
                records.append(
                    {
                        "backend": backend,
                        "cpu": cpu,
                        "endpoints": inputs,
                        "expected": expected,
                        "native": report,
                        "row_cache": "per-case 16 input rows, identical for both backends",
                        "objective": "minimum sum of negative log2 local DDT probabilities",
                    }
                )
            q1, q3 = np.quantile(times, [0.25, 0.75])
            yield {
                "backend": backend,
                "rounds": 3,
                "cases": cases,
                "feasible": sum(r["weight"] >= 0 for r in expected),
                "infeasible": sum(r["weight"] < 0 for r in expected),
                "repeats": repeats,
                "median_us": statistics.median(times),
                "min_us": min(times),
                "max_us": max(times),
                "q1_us": float(q1),
                "q3_us": float(q3),
                "iqr_us": float(q3 - q1),
            }
