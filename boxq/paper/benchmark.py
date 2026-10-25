"""Live Table 4 benchmark with optional archival of individual repetitions.

Native count queries are timed with preprocessing outside the timers; every
answer is checked against an independent NumPy mask before it is accepted.
"""

from collections import defaultdict
from contextlib import ExitStack
from pathlib import Path
import random
import statistics
import tempfile
import time

import numpy as np

from ..analysis.layouts import BACKENDS as LAYOUTS, affinity, layout_files
from ..core import catalog
from ..core.tables import compute
from ..native.table import NativeQuery, NativeTable
from .tables import PaperTable

CASES = (("AES", "fixed"), ("AES", "extremal"), ("CSS", "composite"), ("DryGASCON256", "truncated"))
BACKENDS = ("packed", "int32", "indexed", "adaptive")


def paper_cases(matrix):
    """The original Table 4 word-automaton constructors and value predicates.

    The seven illustrative counter queries use a different constructor policy
    in analysis.queries.presets. Equivalent predicates need not have equal DFA layouts.
    """
    import numpy as np
    from ..core.regex import compile_regex
    from ..core.query import conjoin, hamming_weight_at_most

    n = (len(matrix) - 1).bit_length()
    x = np.arange(len(matrix))
    a = x[:, None]
    w = np.array([int(v).bit_count() for v in x])
    maximum = int(np.abs(matrix).max())
    threshold = max(1, maximum // 2)
    fixed_word = "".join("[23]" if 5 & (1 << bit) else "[01]" for bit in range(n - 1, -1, -1))
    return [
        ("fixed", compile_regex(fixed_word).query(), (a == 5) & (matrix != 0), None),
        (
            "extremal",
            compile_regex(".*").query(
                accept=lambda v: abs(v) >= maximum,
                possible=lambda lo, hi: max(abs(lo), abs(hi)) >= maximum,
            ),
            np.abs(matrix) >= maximum,
            maximum,
        ),
        (
            "truncated",
            compile_regex("[23]{2}.*").query(),
            (a >= 3 * len(matrix) // 4) & (matrix != 0),
            None,
        ),
        (
            "composite",
            conjoin(
                "composite",
                compile_regex(".*").query(),
                hamming_weight_at_most(4),
                lambda v: abs(v) >= threshold,
            ),
            (w[:, None] + w[None, :] <= 4) & (np.abs(matrix) >= threshold),
            threshold,
        ),
    ]


def measure(
    entries,
    kinds,
    *,
    backends,
    case_factory,
    queries=None,
    repeats=15,
    warmups=2,
    cpu=None,
    records=None,
):
    """Yield count-query medians; an optional sink retains checked samples and setup.

    ``case_factory(matrix)`` returns (label, query, mask, threshold) cases whose
    NumPy masks independently define the expected match counts.
    """
    if not 1 <= repeats <= 1000 or not 0 <= warmups <= 100:
        raise ValueError("repeats must be 1..1000; warmups 0..100")
    rng = random.Random(0)
    with affinity(cpu):
        for name, lookup in entries:
            n = (len(lookup) - 1).bit_length()
            for kind in kinds:
                if kind == "BCT" and len(set(lookup)) != len(lookup):
                    continue
                matrix = compute(lookup, kind)
                cases = [c for c in case_factory(matrix) if not queries or c[0] in queries]
                if not cases:
                    raise ValueError("no matching benchmark query")
                with tempfile.TemporaryDirectory(prefix="boxq-bench-") as tmp, ExitStack() as stack:
                    before = time.perf_counter()
                    paths = layout_files(matrix, Path(tmp), {LAYOUTS[b][0] for b in backends})
                    layout_seconds = time.perf_counter() - before
                    handles, setup = {}, {}
                    for backend in backends:
                        file, variant = LAYOUTS[backend]
                        table = stack.enter_context(NativeTable(paths[file], variant=variant))
                        bounds = table.value_bounds() if table.is_graph else {"preprocessing_ns": 0}
                        handles[backend] = table
                        setup[backend] = {
                            **table.info(),
                            "bounds_us": bounds["preprocessing_ns"] / 1000,
                        }
                    for label, query, mask, threshold in cases:
                        compiled = stack.enter_context(NativeQuery(query, n))
                        expected = int(np.count_nonzero(mask))
                        samples, workspace = defaultdict(list), defaultdict(int)
                        raw = []
                        for iteration in range(warmups + repeats):
                            order = list(backends)
                            rng.shuffle(order)
                            for backend in order:
                                result = handles[backend].run(compiled, mode="count")
                                if result["count"] != expected:
                                    raise RuntimeError(
                                        "native result differs from independent matrix predicate"
                                    )
                                if iteration >= warmups:
                                    samples[backend].append(result["elapsed_ns"])
                                    if records is not None:
                                        raw.append(
                                            {
                                                "iteration": iteration - warmups,
                                                "backend_order": order.copy(),
                                                "backend": backend,
                                                **result,
                                            }
                                        )
                                    workspace[backend] = max(
                                        workspace[backend],
                                        result["cache_bytes"],
                                        result["memo_peak_slots"] * 16,
                                        result["dp_bytes"],
                                    )
                        if records is not None:
                            from ..native.tools import native_tools

                            records.append(
                                {
                                    "name": name,
                                    "table": kind,
                                    "query": label,
                                    "n": n,
                                    "mode": "count",
                                    "matches": expected,
                                    "repeats": repeats,
                                    "warmups": warmups,
                                    "cpu": cpu,
                                    "threshold": threshold,
                                    "layout_seconds": layout_seconds,
                                    "setup": setup,
                                    "samples": raw,
                                    "compiler": native_tools(shared=True)[1],
                                    "order_seed": 0,
                                }
                            )
                        for backend in backends:
                            info = setup[backend]
                            retained = sum(
                                info[key]
                                for key in (
                                    "mapped_file_bytes",
                                    "bounds_bytes",
                                    "decoded_array_bytes",
                                    "index_coordinates_capacity_bytes",
                                )
                            )
                            vals = [v / 1000 for v in samples[backend]]
                            q1, q3 = np.quantile(vals, [0.25, 0.75])
                            yield {
                                "name": name,
                                "n": n,
                                "table": kind,
                                "query": label,
                                "backend": backend,
                                "mode": "count",
                                "matches": expected,
                                "median_us": statistics.median(samples[backend]) / 1000,
                                "min_us": min(vals),
                                "max_us": max(vals),
                                "q1_us": float(q1),
                                "q3_us": float(q3),
                                "iqr_us": float(q3 - q1),
                                "data_bytes": retained + workspace[backend],
                                "repeats": repeats,
                                "open_us": info["open_setup_ns"] / 1000,
                                "bounds_us": info["bounds_us"],
                                "layout_seconds": layout_seconds,
                            }


def measure_table4(*, repeats=15, warmups=1, cpu=None, records=None):
    """Run all 16 configurations now and return only median microseconds.

    Setup is outside the native timers. Every answer is checked against the
    independently expressed matrix predicate before its timing is accepted.
    """
    medians, spreads = {}, {}
    for name in dict.fromkeys(name for name, _ in CASES):
        labels = [query for box, query in CASES if box == name]
        for row in measure(
            catalog.select([name]),
            ["DDT"],
            backends=BACKENDS,
            queries=labels,
            repeats=repeats,
            warmups=warmups,
            cpu=cpu,
            case_factory=paper_cases,
            records=records,
        ):
            medians[name, row["query"], row["backend"]] = row["median_us"]
            spreads[name, row["query"], row["backend"]] = row["iqr_us"]
    rows = [
        dict(
            name=name,
            query=query,
            **{backend + "_us": f"{medians[name, query, backend]:.3f}" for backend in BACKENDS},
            **{backend + "_iqr_us": f"{spreads[name, query, backend]:.3f}" for backend in BACKENDS},
        )
        for name, query in CASES
    ]
    return PaperTable(
        4,
        rows,
        note=(
            f"fresh benchmark; {repeats} repetitions; {warmups} untimed warm-ups; "
            "warm native count medians in microseconds; preprocessing excluded; "
            + (
                "checked raw timings retained"
                if records is not None
                else "raw timings are not saved"
            )
        ),
    )
