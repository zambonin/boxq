"""Shared bit fields and header validation for packed table formats."""
from __future__ import annotations
import struct

HEADER = struct.Struct('<4sBBBBQQQQ')
MAX_WIDTH = 64

def bits_for_codes(count):
    return max(0, (count - 1).bit_length()) if count else 0


def signed_width(values):
    width = max((v.bit_length() + 1 if v >= 0 else (~v).bit_length() + 1 for v in values), default=1)
    if width > MAX_WIDTH:
        raise ValueError('format supports signed values of at most 64 bits')
    return width


class BitWriter:

    def __init__(self):
        self.data = bytearray()
        self.bits = 0

    def put(self, value, width):
        if not 0 <= width <= 64 or value < 0 or value >= 1 << width:
            raise ValueError('unsigned value does not fit field')
        left = width
        while left:
            byte, shift = divmod(self.bits, 8)
            if byte == len(self.data):
                self.data.append(0)
            take = min(left, 8 - shift)
            self.data[byte] |= (value & (1 << take) - 1) << shift
            value >>= take
            left -= take
            self.bits += take

    def signed(self, value, width):
        self.put(value & (1 << width) - 1, width)


def read_bits(data, offset, width):
    if width == 0:
        return 0
    start, shift = divmod(offset, 8)
    stop = (offset + width + 7) // 8
    if offset < 0 or width < 0 or stop > len(data):
        raise ValueError('truncated field')
    return int.from_bytes(data[start:stop], 'little') >> shift & (1 << width) - 1


def read_signed(data, offset, width):
    v = read_bits(data, offset, width)
    return v - (1 << width) if v & 1 << width - 1 else v


def _check_payload(payload, bits):
    if len(payload) != (bits + 7) // 8:
        raise ValueError('payload length mismatch')
    if bits % 8 and payload[-1] >> bits % 8:
        raise ValueError('nonzero padding')


def _header(blob, magic):
    blob = bytes(blob)
    if len(blob) < HEADER.size:
        raise ValueError('truncated header')
    m, n, iw, vw, flags, a, b, c, d = HEADER.unpack_from(blob)
    if m != magic or flags or (not 0 <= n <= 20) or (not 0 <= iw <= 64) or (not 1 <= vw <= 64):
        raise ValueError('unsupported format or header fields')
    return (n, iw, vw, a, b, c, d, blob[HEADER.size:])


def _cell(n, a, b):
    if type(a) is not int or type(b) is not int or (not 0 <= a < 1 << n) or (not 0 <= b < 1 << n):
        raise IndexError('cell outside represented table')
    return a << n | b
