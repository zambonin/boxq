"""Independent 16-bit experiment input from the Midori specification.

Banik et al., Midori: A Block Cipher for Low Energy, ASIACRYPT 2015,
Table 3 and Section 3.1, printed pages 420--421.
https://doi.org/10.1007/978-3-662-48800-3_17

One column, four Sb0 applications, MixColumn, four Sb0 applications.
The intermediate subkey is fixed to zero. This is not full-cipher encryption.
"""

SB0 = (0xC, 0xA, 0xD, 0x3, 0xE, 0xB, 0xF, 0x7, 0x8, 0x9, 0x1, 0x5, 0x0, 0x2, 0x4, 0x6)


def midori64_super_sbox(value):
    if type(value) is not int or not 0 <= value < 65536:
        raise ValueError("value must be a 16-bit integer")
    cells = [SB0[(value >> shift) & 15] for shift in (12, 8, 4, 0)]
    parity = cells[0] ^ cells[1] ^ cells[2] ^ cells[3]
    result = 0
    for cell in cells:
        result = (result << 4) | SB0[parity ^ cell]
    return result


def lookup():
    """The complete zero-intermediate-key, MSB-first experimental lookup."""
    return [midori64_super_sbox(value) for value in range(65536)]
