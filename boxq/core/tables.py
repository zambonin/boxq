"""Dense DDT/LAT/BCT construction for lookup tables.

``compute`` uses the article's masks by default: DDT/LAT origin cleared;
BCT both axes cleared. ``raw=True`` retains the mathematical table instead.
For inputs above nine bits, use the native file builder, not a dense allocation.
A rectangular lookup (``m != n``) gives a 2^n x 2^m DDT or LAT; ``padded``
embeds it in the square table that the automaton construction expects.
"""
from __future__ import annotations
import numpy as np


def compute(lookup, kind="DDT", *, raw=False):
    """Return a signed int32 NumPy matrix of 2^n rows and 2^m columns.

    The output width ``m`` is read from a Lookup and otherwise equals ``n``.
    No input is modified.
    """
    values = list(lookup)
    n = len(values)
    outputs = 1 << getattr(lookup, "m", max(0, (n - 1).bit_length()))
    if n < 2 or n & (n - 1) or any(type(v) is not int or not 0 <= v < outputs for v in values):
        raise ValueError("expected a lookup of positive bit width")
    if n > 512:
        raise ValueError(
            "dense commands are limited to 9-bit inputs; 'boxq experiment large' builds 16-bit DDTs"
        )
    kind = kind.upper()
    if kind not in ("DDT", "LAT", "BCT"):
        raise ValueError("kind must be DDT, LAT or BCT")
    x = np.arange(n, dtype=np.int64)
    lut = np.asarray(values, dtype=np.int64)
    result = np.empty((n, outputs), dtype=np.int32)
    if kind == "DDT":
        for a in range(n):
            result[a] = np.bincount(lut ^ lut[x ^ a], minlength=outputs)
    elif kind == "LAT":
        # For each input mask, accumulate input parity by output value,
        # then transform in the output-mask dimension. Works for nonpermutations.
        parity = np.array([i.bit_count() & 1 for i in range(n)], dtype=np.int32)
        for a in range(n):
            result[a] = np.bincount(lut, weights=1 - 2 * parity[a & x], minlength=outputs)
        h = 1
        while h < outputs:
            blocks = result.reshape(n, -1, 2 * h)
            left, right = blocks[:, :, :h].copy(), blocks[:, :, h:].copy()
            blocks[:, :, :h] = left + right
            blocks[:, :, h:] = left - right
            h *= 2
        result //= 2  # signed half-Walsh, not absolute values
    else:
        if outputs != n or len(set(values)) != n:
            raise ValueError("BCT is only defined here for permutations")
        inv = np.empty(n, dtype=np.int64)
        inv[lut] = x
        # Literal inverse-permutation definition, vectorized over (b,x).
        first = inv[lut[None, :] ^ x[:, None]]
        for a in range(n):
            second = inv[lut[x ^ a][None, :] ^ x[:, None]]
            result[a] = np.count_nonzero((first ^ second) == a, axis=1)
    if not raw:
        result[0, 0] = 0
        if kind == "BCT":
            result[0, :] = result[:, 0] = 0
    return result


def padded(matrix):
    """Embed a 2^n x 2^m table in a zero-filled square of side 2^max(n, m).

    Cells outside the original rows and columns are zero; queries exclude
    them with leading-zero masks on the shorter coordinate.
    """
    rows, columns = matrix.shape
    if rows == columns:
        return matrix
    side = max(rows, columns)
    square = np.zeros((side, side), dtype=matrix.dtype)
    square[:rows, :columns] = matrix
    return square
