"""Native file conversion, metrics, and tool invocation."""

from pathlib import Path
import json
import os
import subprocess
import tempfile
import time

from .tools import native_tools


def call(tool, *args, quiet=False):
    executable, compiler = native_tools(tool=tool)
    started = time.perf_counter()
    proc = subprocess.run(
        [str(executable), *map(str, args)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE if quiet else None,
    )
    if proc.returncode:
        raise RuntimeError(
            f"native {tool or 'build'} failed with exit {proc.returncode}"
            + (":\n" + proc.stderr if quiet else "")
        )
    return {
        **json.loads(proc.stdout),
        "wall_seconds": time.perf_counter() - started,
        "compiler": compiler,
    }


def convert(source, output, operation):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output:
        raise ValueError("input and output must be different files")
    if operation not in ("pack", "index"):
        raise ValueError("operation must be pack or index")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output.parent, prefix=".boxq-") as tmp:
        target = Path(tmp) / output.name
        result = call(operation, source, target, quiet=True)
        os.replace(target, output)
    return result


def histogram(file):
    """Graph-only histogram for a nonnegative QNF1 table; uses disk-backed counts."""
    file = Path(file).expanduser().resolve()
    with file.open("rb") as stream:
        if stream.read(4) != b"QNF1":
            raise ValueError("large graph statistics require a .qnf file")
    with tempfile.TemporaryDirectory(dir=file.parent, prefix=".boxq-metrics-") as tmp:
        result = call("metrics", file, Path(tmp) / "counts.bin")
    return result


def level_statistics(file):
    """Count distinct aligned blocks of each side length directly from QNF1."""
    return call("metrics", Path(file).expanduser().resolve(), "levels", quiet=True)
