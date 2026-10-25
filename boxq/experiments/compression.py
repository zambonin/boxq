"""Offline entropy reference: one-byte codebook indices compressed with XZ."""

import hashlib
import lzma

import numpy as np

from ..core.tables import compute
from .provenance import lookup_digest

PAPER_NAMES = ("AES", "SKINNY_8", "CSS", "DryGASCON256")


def rows(entries, folder=None):
    results = []
    for name, lookup in entries:
        matrix = compute(lookup)
        values, inverse = np.unique(matrix, return_inverse=True)
        if len(values) > 256:
            raise ValueError("the paper XZ reference uses one-byte dictionary indices")
        raw = inverse.astype(np.uint8).tobytes(order="C")
        compressed = lzma.compress(
            raw, format=lzma.FORMAT_XZ, check=lzma.CHECK_CRC64, preset=9 | lzma.PRESET_EXTREME
        )
        if lzma.decompress(compressed) != raw:
            raise RuntimeError("XZ round trip failed")
        if folder is not None:
            (folder / (name + ".indices.bin")).write_bytes(raw)
            (folder / (name + ".indices.xz")).write_bytes(compressed)
        results.append(
            {
                "name": name,
                "input_sha256": lookup_digest(lookup),
                "dictionary": [int(v) for v in values],
                "input_encoding": "row-major uint8 indices into sorted value dictionary",
                "dictionary_in_stream": False,
                "format": "XZ",
                "preset": 9,
                "extreme": True,
                "check": "CRC64",
                "input_bytes": len(raw),
                "xz_bytes": len(compressed),
                "xz_kib": len(compressed) / 1024,
                "stream_sha256": hashlib.sha256(raw).hexdigest(),
                "xz_sha256": hashlib.sha256(compressed).hexdigest(),
            }
        )
    return results
