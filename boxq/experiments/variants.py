"""Alternative bit orders and branching factors, independently reduced."""

import numpy as np

from ..core.tables import compute
from ..formats._bits import signed_width
from .provenance import lookup_digest

PAPER_NAMES = ("PRESENT", "Ascon", "APN_6", "AES", "SKINNY_8", "Safer", "CSS")


def vector(matrix, interleaved=True):
    if not interleaved:
        return matrix.ravel()
    n = (len(matrix) - 1).bit_length()
    a, b = np.meshgrid(np.arange(len(matrix)), np.arange(len(matrix)), indexing="ij")
    words = np.zeros_like(a)
    for bit in range(n):
        words |= ((a >> bit) & 1) << (2 * bit + 1)
        words |= ((b >> bit) & 1) << (2 * bit)
    out = np.empty(matrix.size, dtype=np.int64)
    out[words.ravel()] = matrix.ravel()
    return out


def nodes(values, arity=4, full=False, crosslevel=False):
    alphabet, current = np.unique(values, return_inverse=True)
    d = len(alphabet)
    total = d
    registry = {}
    while len(current) > 1:
        keys = current.reshape(-1, arity)
        constant = np.all(keys == keys[:, 0, None], axis=1)
        if not full:
            constant &= keys[:, 0] < d
        out = keys[:, 0].copy()
        if crosslevel:
            for i in np.flatnonzero(~constant):
                key = tuple(int(v) for v in keys[i])
                if key not in registry:
                    registry[key] = total
                    total += 1
                out[i] = registry[key]
        elif (~constant).any():
            unique, inverse = np.unique(keys[~constant], axis=0, return_inverse=True)
            out[~constant] = total + inverse
            total += len(unique)
        current = out
    return total


def rows(entries):
    results = []
    for name, lookup in entries:
        matrix = compute(lookup)
        interleaved = vector(matrix)
        q = nodes(interleaved)
        b = nodes(interleaved, arity=2)
        row = nodes(vector(matrix, False))
        values = [int(v) for v in np.unique(matrix)]
        dictionary_bits = len(values) * signed_width(values)
        results.append(
            {
                "sbox": name,
                "input_sha256": lookup_digest(lookup),
                "quaternary": q,
                "binary": b,
                "row_major": row,
                "quaternary_bytes": (4 * q * max(1, (q - 1).bit_length()) + dictionary_bits + 7)
                // 8,
                "binary_bytes": (2 * b * max(1, (b - 1).bit_length()) + dictionary_bits + 7) // 8,
                "binary_full": nodes(interleaved, arity=2, full=True),
                "crosslevel": nodes(interleaved, crosslevel=True),
            }
        )
    return results
