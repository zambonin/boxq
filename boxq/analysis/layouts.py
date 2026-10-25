"""Benchmark backend layouts and optional CPU affinity."""
from contextlib import contextmanager
import os

from ..core.automaton import TableAutomaton
from ..native.file_ops import call
from ..formats.graph import PackedAutomaton
from ..formats.dense import DenseRangePacked


# Table 4 and the PRESENT search: layout file and native variant per backend.
BACKENDS = {
    "packed": ("graph", "mapped"),
    "int32": ("range", "int32"),
    "indexed": ("range", "indexed"),
    "adaptive": ("index", "mapped"),
}


@contextmanager
def affinity(cpu):
    old = None
    if cpu is not None:
        if not hasattr(os, "sched_getaffinity") or cpu not in os.sched_getaffinity(0):
            raise ValueError("requested CPU is not available for affinity pinning")
        old = os.sched_getaffinity(0)
        os.sched_setaffinity(0, {cpu})
    try:
        yield
    finally:
        if old is not None:
            os.sched_setaffinity(0, old)


def layout_files(matrix, folder, needed):
    """Create only requested layouts in caller-owned scratch space."""
    n = (len(matrix) - 1).bit_length()
    plain = matrix.tolist()
    paths = {}
    if "index" in needed:
        needed = set(needed) | {"range"}
    for name in needed:
        if name == "index":
            continue
        if name == "graph":
            obj = PackedAutomaton.from_automaton(TableAutomaton(plain, n))
        elif name == "range":
            obj = DenseRangePacked.from_matrix(plain, n)
        else:
            raise ValueError(f"unknown layout {name}")
        paths[name] = folder / name
        paths[name].write_bytes(obj.to_bytes())
    if "index" in needed:
        paths["index"] = folder / "index"
        call("index", paths["range"], paths["index"], quiet=True)
    return paths
