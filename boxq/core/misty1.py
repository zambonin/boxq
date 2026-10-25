"""MISTY1 FI with an explicit 16-bit subkey, following RFC 2994."""
from __future__ import annotations


def _word(value: int, bits: int) -> int:
    if type(value) is not int or not 0 <= value < 1 << bits:
        raise ValueError(f'expected unsigned {bits}-bit integer')
    return value


class Misty1:
    """Evaluate FI with caller-supplied S7/S9 permutations."""

    def __init__(self, s7, s9):
        self.s7, self.s9 = (tuple(s7), tuple(s9))
        for table, size in [(self.s7, 128), (self.s9, 512)]:
            if (
                len(table) != size
                or any((type(v) is not int for v in table))
                or set(table) != set(range(size))
            ):
                raise ValueError('S7 and S9 must be permutations of the prescribed widths')

    def _fi(self, value: int, subkey: int) -> int:
        d9, d7 = (value >> 7, value & 127)
        d9 = self.s9[d9] ^ d7
        d7 = (self.s7[d7] ^ d9) & 127
        d7 ^= subkey >> 9
        d9 ^= subkey & 511
        d9 = self.s9[d9] ^ d7
        return d7 << 9 | d9

    def fi(self, value: int, subkey: int) -> int:
        """RFC FI with an explicit 16-bit subkey (there is no implicit key)."""
        return self._fi(_word(value, 16), _word(subkey, 16))

    def fi_lookup(self, subkey: int) -> list[int]:
        """Return all 2^16 FI outputs in input order for the supplied subkey."""
        _word(subkey, 16)
        return [self._fi(x, subkey) for x in range(1 << 16)]
