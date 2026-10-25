"""Dense dictionary and arithmetic range table encodings."""
from __future__ import annotations

import struct
from functools import reduce
from math import gcd

from ._bits import BitWriter, HEADER, _cell, _check_payload, _header, bits_for_codes, read_bits, read_signed, signed_width

class DensePacked:
    """All cells coded by a sorted signed value dictionary, with direct lookup."""

    def __init__(self, blob):
        n, iw, vw, count, d, c, reserved, payload = _header(blob, b'DNS1')
        if count != 1 << 2 * n or not 1 <= d <= count or c or reserved or (iw != bits_for_codes(d)):
            raise ValueError('invalid dense header')
        _check_payload(payload, d * vw + count * iw)
        self.n, self.iw, self.vw, self.count, self.d = (n, iw, vw, count, d)
        self.data = payload
        values = [read_signed(payload, j * vw, vw) for j in range(d)]
        if values != sorted(set(values)):
            raise ValueError('invalid dictionary')
        if any((read_bits(payload, d * vw + j * iw, iw) >= d for j in range(count))):
            raise ValueError('invalid dense code')

    @classmethod
    def from_matrix(cls, m, n):
        N = 1 << n
        if len(m) != N or any((len(row) != N for row in m)):
            raise ValueError('shape')
        values = sorted(set((v for row in m for v in row)))
        index = {v: i for i, v in enumerate(values)}
        d = len(values)
        iw = bits_for_codes(d)
        vw = signed_width(values)
        w = BitWriter()
        for v in values:
            w.signed(v, vw)
        for row in m:
            for v in row:
                w.put(index[v], iw)
        return cls(HEADER.pack(b'DNS1', n, iw, vw, 0, N * N, d, 0, 0) + bytes(w.data))

    def evaluate(self, a, b):
        cell = _cell(self.n, a, b)
        code = read_bits(self.data, self.d * self.vw + cell * self.iw, self.iw)
        return read_signed(self.data, code * self.vw, self.vw)

    def to_bytes(self):
        return HEADER.pack(b'DNS1', self.n, self.iw, self.vw, 0, self.count, self.d, 0, 0) + self.data


class DenseRangePacked:
    """Fixed-width arithmetic-range coding, including DDT multiplicity/2.

    Values are base + step*code; step is gcd of all differences from base.
    This is a real direct-access range baseline, not a dictionary baseline.
    """

    def __init__(self, blob):
        n, iw, vw, count, reserved, c, d, payload = _header(blob, b'RNG1')
        if count != 1 << 2 * n or reserved or c or d or (len(payload) < 16):
            raise ValueError('invalid range header')
        self.base, self.step = struct.unpack_from('<qQ', payload)
        if self.step == 0:
            raise ValueError('zero arithmetic step')
        self.n, self.iw, self.vw, self.count = (n, iw, vw, count)
        self.data = payload
        _check_payload(payload[16:], count * iw)

    @classmethod
    def from_matrix(cls, m, n):
        N = 1 << n
        if len(m) != N or any((len(row) != N for row in m)):
            raise ValueError('shape')
        values = sorted(set((v for row in m for v in row)))
        base = values[0]
        step = reduce(gcd, (v - base for v in values), 0) or 1
        iw = ((values[-1] - base) // step).bit_length()
        vw = signed_width(values)
        if iw > 64:
            raise ValueError('range width exceeds format')
        writer = BitWriter()
        for row in m:
            for v in row:
                writer.put((v - base) // step, iw)
        return cls(
            HEADER.pack(b'RNG1', n, iw, vw, 0, N * N, 0, 0, 0) + struct.pack('<qQ', base, step) + bytes(writer.data),
        )

    def evaluate(self, a, b):
        cell = _cell(self.n, a, b)
        return self.base + self.step * read_bits(self.data, 128 + cell * self.iw, self.iw)

    def to_bytes(self):
        return HEADER.pack(b'RNG1', self.n, self.iw, self.vw, 0, self.count, 0, 0, 0) + self.data
