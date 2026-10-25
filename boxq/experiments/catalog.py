"""Full corpus verification and retained per-S-box results, including aliases."""

import hashlib
import sys

import numpy as np

from ..core.automaton import TableAutomaton
from ..core.catalog import select
from ..core.tables import compute
from ..core.metrics import differential_branch_number
from ..analysis.reports import summarize
from . import reference
from .properties import degree, weighting
from .variants import nodes, vector
from .provenance import lookup_digest


def run(entries=None, *, verify=True):
    entries = select(all_names=True) if entries is None else list(entries)
    cached = {}
    degrees = {}
    rows = []
    for index, (name, lookup) in enumerate(entries):
        n = (len(lookup) - 1).bit_length()
        token = lookup_digest(lookup)
        permutation = len(set(lookup)) == len(lookup)
        if token not in degrees:
            degrees[token] = degree(lookup)
        for kind in ("DDT", "LAT", "BCT"):
            if kind == "BCT" and not permutation:
                continue
            key = token, kind
            if key not in cached:
                matrix = compute(lookup, kind)
                graph = TableAutomaton.from_rows(iter(matrix), n)
                checked = 0
                if verify:
                    independent = reference.table(lookup, kind)
                    if not np.array_equal(matrix, independent):
                        raise RuntimeError(f"independent matrix mismatch for {name}/{kind}")
                    if reference.state_count(independent) != graph.num_states():
                        raise RuntimeError(f"independent state count mismatch for {name}/{kind}")
                    for a in range(len(lookup)):
                        for b in range(len(lookup)):
                            if graph.evaluate(a, b) != int(matrix[a, b]):
                                raise RuntimeError(f"graph cell mismatch for {name}/{kind}/{a}/{b}")
                            checked += 1
                values, counts = np.unique(matrix, return_counts=True)
                histogram = {int(v): int(c) for v, c in zip(values, counts)}
                row = {
                    **summarize(name, kind, n, graph.num_states(), histogram),
                    "input_sha256": token,
                    "canonical_name": name,
                    "permutation": permutation,
                    "cells_checked": checked,
                    "matrix_sha256": hashlib.sha256(matrix.astype("<i4").tobytes()).hexdigest(),
                    "histogram": histogram,
                    "nonzero": int(np.count_nonzero(matrix)),
                    "independent_verified": verify,
                }
                if verify:
                    payload = reference.payload_sizes(independent, graph.num_states())
                    if any(row[key] != value for key, value in payload.items()):
                        raise RuntimeError(f"independent payload mismatch for {name}/{kind}")
                    row["payload_independently_verified"] = True
                if kind == "DDT":
                    row.update(
                        degrees[token],
                        branch_number=differential_branch_number(graph),
                        crosslevel_states=nodes(vector(matrix), crosslevel=True),
                    )
                cached[key] = row
            rows.append({**cached[key], "name": name})
        if index % 10 == 0:
            print(
                f"verified catalog entry {index + 1}/{len(entries)}: {name}",
                file=sys.stderr,
                flush=True,
            )
    ddts = [r for r in rows if r["table"] == "DDT"]
    return {
        "rows": rows,
        "aliases": weighting(rows),
        "names": len(entries),
        "distinct_lookups": len(degrees),
        "permutation_names": sum(len(set(lut)) == len(lut) for _, lut in entries),
        "crosslevel_smaller_names_le8": sum(
            r["n"] <= 8 and r["crosslevel_states"] < r["states"] for r in ddts
        ),
        "crosslevel_checked_names_le8": sum(r["n"] <= 8 for r in ddts),
    }
