"""Sparse bitmap encoding with optional rank index."""
from __future__ import annotations

from ._bits import BitWriter, HEADER, _cell, _check_payload, _header, bits_for_codes, read_bits, read_signed, signed_width

class BitmapPacked:
    """Presence map + NONZERO dictionary codes, optionally with a rank index.

    The indexed form uses prefix counts every 512 cells by default. Nonindexed
    random lookup scans/counts the preceding presence prefix; it is not O(1).
    """

    def __init__(self, blob):
        n, iw, vw, nnz, d, block, rank_bits, payload = _header(blob, b'BMP1')
        cells = 1 << 2 * n
        if nnz > cells or d > nnz or bool(d) != bool(nnz) or (iw != bits_for_codes(d)):
            raise ValueError('invalid bitmap dictionary')
        if block and (block < 8 or block > 65536 or block & block - 1):
            raise ValueError('rank block must be a power of two from 8 to 65536')
        ranks = (cells + block - 1) // block + 1 if block else 0
        if rank_bits != (max(1, nnz.bit_length()) if block else 0):
            raise ValueError('invalid rank width')
        _check_payload(payload, cells + d * vw + nnz * iw + ranks * rank_bits)
        self.n, self.iw, self.vw, self.nnz, self.d = (n, iw, vw, nnz, d)
        self.block, self.rb, self.cells, self.ranks = (block, rank_bits, cells, ranks)
        self.data = payload
        self.dictionary_offset = cells
        self.codes_offset = cells + d * vw
        self.rank_offset = self.codes_offset + nnz * iw
        vals = [self._value(i) for i in range(d)]
        if vals != sorted(set(vals)) or 0 in vals:
            raise ValueError('invalid nonzero dictionary')
        presence = read_bits(payload, 0, cells)
        if presence.bit_count() != nnz:
            raise ValueError('incorrect nonzero count')
        if any((read_bits(payload, self.codes_offset + i * iw, iw) >= d for i in range(nnz))):
            raise ValueError('invalid bitmap code')
        if block:
            count = 0
            for j in range(ranks):
                if read_bits(payload, self.rank_offset + j * rank_bits, rank_bits) != count:
                    raise ValueError('incorrect rank prefix')
                start = j * block
                length = min(block, max(0, cells - start))
                count += read_bits(payload, start, length).bit_count()

    @classmethod
    def from_matrix(cls, m, n, *, rank_block=512):
        N = 1 << n
        if len(m) != N or any((len(row) != N for row in m)):
            raise ValueError('shape')
        values = sorted(set((v for row in m for v in row if v != 0)))
        d = len(values)
        codes = {v: i for i, v in enumerate(values)}
        iw = bits_for_codes(d)
        vw = signed_width(values)
        if rank_block and (rank_block < 8 or rank_block > 65536 or rank_block & rank_block - 1):
            raise ValueError('invalid rank block')
        writer = BitWriter()
        prefix = [0]
        nnz = 0
        for pos, v in enumerate((v for row in m for v in row)):
            writer.put(int(v != 0), 1)
            nnz += v != 0
            if rank_block and (pos + 1) % rank_block == 0:
                prefix.append(nnz)
        if rank_block and N * N % rank_block:
            prefix.append(nnz)
        for v in values:
            writer.signed(v, vw)
        for row in m:
            for v in row:
                if v:
                    writer.put(codes[v], iw)
        rb = max(1, nnz.bit_length()) if rank_block else 0
        if rank_block:
            for count in prefix:
                writer.put(count, rb)
        return cls(HEADER.pack(b'BMP1', n, iw, vw, 0, nnz, d, rank_block, rb) + bytes(writer.data))

    def _value(self, code):
        return read_signed(self.data, self.dictionary_offset + code * self.vw, self.vw)

    def rank(self, pos):
        """Number of nonzero cells strictly before pos."""
        if not 0 <= pos <= self.cells:
            raise IndexError(pos)
        if not self.block:
            return read_bits(self.data, 0, pos).bit_count()
        j = pos // self.block
        start = j * self.block
        prefix = read_bits(self.data, self.rank_offset + j * self.rb, self.rb)
        return prefix + read_bits(self.data, start, pos - start).bit_count()

    def evaluate(self, a, b):
        pos = _cell(self.n, a, b)
        if not read_bits(self.data, pos, 1):
            return 0
        code = read_bits(self.data, self.codes_offset + self.rank(pos) * self.iw, self.iw)
        return self._value(code)

    def to_bytes(self):
        return HEADER.pack(b'BMP1', self.n, self.iw, self.vw, 0, self.nnz, self.d, self.block, self.rb) + self.data
