"""Quadrant encoding conventions for cryptanalytic tables.

A 2^n x 2^n table indexed by (a, b) is encoded over the quaternary alphabet
Sigma = {0, 1, 2, 3}. At level i (most significant first) the symbol packs one
bit of the row index a and one bit of the column index b as

    sigma = 2 * a_i + b_i,

so the *input* bit is the high bit and the *output* bit the low bit. This is the
single source of truth for the convention used throughout the package; every
other module imports these helpers rather than re-deriving the bit layout.

Consequences (used when building query automata):
    input  inactive (a_i = 0) -> symbols {0, 1}      input  active (a_i = 1) -> {2, 3}
    output inactive (b_i = 0) -> symbols {0, 2}      output active (b_i = 1) -> {1, 3}
"""
from __future__ import annotations
ALPHABET = (0, 1, 2, 3)


def symbol(a_bit: int, b_bit: int) -> int:
    """Pack an (input, output) bit pair into a quaternary symbol."""
    return 2 * a_bit + b_bit


def input_bit(sigma: int) -> int:
    """Recover the input (row) bit from a symbol."""
    return sigma >> 1


def output_bit(sigma: int) -> int:
    """Recover the output (column) bit from a symbol."""
    return sigma & 1


def word_of(a: int, b: int, n: int) -> tuple[int, ...]:
    """Encode the cell (a, b) of a 2^n x 2^n table as a length-n word."""
    return tuple((symbol(a >> n - 1 - i & 1, b >> n - 1 - i & 1) for i in range(n)))


def cell_of(word) -> tuple[int, int]:
    """Inverse of :func:`word_of`: decode a word back to the pair (a, b)."""
    a = b = 0
    for sigma in word:
        a = a << 1 | input_bit(sigma)
        b = b << 1 | output_bit(sigma)
    return (a, b)
