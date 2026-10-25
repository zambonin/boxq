"""Algebraic degrees and alias-weighting sensitivity for the paper corpus."""

import numpy as np
import statistics


def degree(lookup):
    n = (len(lookup) - 1).bit_length()
    coefficients = np.asarray(lookup, dtype=np.int64).copy()
    for bit in range(n):
        for mask in range(len(lookup)):
            if mask & (1 << bit):
                coefficients[mask] ^= coefficients[mask ^ (1 << bit)]
    coordinate = [
        max(
            (
                mask.bit_count()
                for mask, value in enumerate(coefficients)
                if int(value) & (1 << bit)
            ),
            default=0,
        )
        for bit in range(n)
    ]
    return {"algebraic_degree": max(coordinate), "coordinate_degrees": coordinate}


def weighting(rows):
    groups = {}
    for row in rows:
        key = row["n"], row["table"]
        entry = groups.setdefault(key, {"all": [], "unique": {}})
        entry["all"].append(row["ratio"])
        entry["unique"][row["input_sha256"]] = row["ratio"]
    return [
        {
            "n": n,
            "table": kind,
            "names": len(g["all"]),
            "distinct_lookups": len(g["unique"]),
            "named_median": statistics.median(g["all"]),
            "unique_median": statistics.median(g["unique"].values()),
        }
        for (n, kind), g in sorted(groups.items())
    ]
