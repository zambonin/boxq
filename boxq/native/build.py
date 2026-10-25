"""Native table construction using bounded temporary stages."""

from collections import Counter
from pathlib import Path
import os
import shutil
import struct
import sys
import tempfile
import time

from .file_ops import call
from .tools import native_tools


def build(lookup, kind, output, *, packed=False, partition_mib=128, verify=False):
    """Write a DDT as QNF1 or QDD1. Work budget covers hash partitions, not total RSS.

    The external-memory builder serves the 16-bit DDTs of the paper; build
    LAT and BCT automata of at most nine bits with the Python constructor.
    """
    n = (len(lookup) - 1).bit_length()
    if not 1 <= n <= 16 or len(lookup) != 1 << n:
        raise ValueError("native construction supports square 1..16-bit inputs")
    if any(type(v) is not int or not 0 <= v < len(lookup) for v in lookup):
        raise ValueError("invalid lookup value")
    if kind != "DDT":
        raise ValueError("native construction builds DDTs only")
    if not 16 <= partition_mib <= 4096:
        raise ValueError("partition_mib must be in 16..4096")
    output = Path(output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".boxq-build-") as tmp:
        work = Path(tmp)
        lutfile = work / "lookup.bin"
        lutfile.write_bytes(struct.pack(">" + "I" * len(lookup), *lookup))
        # Compile before the build clock; data production is timed separately.
        native_tools()
        started = time.perf_counter()
        folders, stages, base = {}, {}, 0
        for level in range(n - 1, -1, -1):
            folder = work / f"level-{level}"
            folder.mkdir()
            folders[level] = folder
            need = (4 if level == n - 1 else 24) * (1 << (2 * level)) + (64 << 20)
            if shutil.disk_usage(work).free < need:
                raise RuntimeError("not enough scratch disk for the next level")
            print(f"building {kind}: level {level + 1}/{n}", file=sys.stderr)
            if level == n - 1:
                limit = max(1024, partition_mib * (1 << 20) // 128)
                args = ["bottom", lutfile, folder, n, limit]
            else:
                args = [
                    "level",
                    folders[level + 1] / "frontier.bin",
                    folder,
                    1 << (level + 1),
                    base,
                    partition_mib << 20,
                ]
            stages[level] = call(None, *args)
            base += stages[level]["nodes"]
        values = stages[n - 1]["values"]
        graph = work / "graph.qnf"
        states = _assemble(graph, n, folders, stages, values)
        elapsed = time.perf_counter() - started
        hist = Counter({int(v): c for v, c in stages[n - 1]["spectrum"].items()})
        hist[0] += 1 << n  # bottom DDT counts a!=0; expose normalized full table
        verification = call(None, "verify", graph, lutfile, "full") if verify else None
        final = graph
        packing = None
        if packed:
            final = work / "graph.qdd"
            packing = call("pack", graph, final)
        os.replace(final, output)
    return {
        "n": n,
        "table": kind,
        "states": states,
        "maximum": max(abs(v) for v in values),
        "file_bytes": output.stat().st_size,
        "build_seconds": elapsed,
        "histogram": dict(hist),
        "stages": stages,
        "verification": verification,
        "packing": packing,
    }


def _assemble(output, n, folders, stages, values):
    """Write the QNF1 header and concatenate the per-level node banks."""
    boundaries, total = [0] * 21, 0
    for level in range(n - 1, -1, -1):
        total += stages[level]["nodes"]
        boundaries[level] = total
    root, = struct.unpack("<I", (folders[0] / "frontier.bin").read_bytes())
    offset = (232 + 4 * len(values) + 63) // 64 * 64
    header = struct.pack("<4sIIIQQQQQQ", b"QNF1", 1, n, 1, total, root, len(values), offset, 0, 0)
    header += struct.pack("<21Q", *boundaries) + struct.pack("<" + "i" * len(values), *values)
    with output.open("wb") as stream:
        stream.write(header + bytes(offset - len(header)))
        for level in range(n - 1, -1, -1):
            with (folders[level] / "nodes.bin").open("rb") as bank:
                shutil.copyfileobj(bank, stream, 8 << 20)
    return total + len(values)
