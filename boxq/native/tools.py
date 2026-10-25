"""Compile the requested native tool once, in an ordinary local build cache."""

from pathlib import Path
import hashlib
import os
import platform
import shutil
import subprocess
import tempfile

FLAGS = ["-O3", "-std=c++17", "-Wall", "-Wextra"]
TOOLS = {
    None: "large_builder",
    "pack": "native_pack",
    "metrics": "native_metrics",
    "index": "native_index",
    "present": "native_present",
}


def native_tools(cache=None, compiler=None, *, shared=False, tool=None):
    if os.name != "posix":
        raise RuntimeError("native commands need a 64-bit POSIX host with GCC or Clang")
    name = "native_query" if shared else TOOLS[tool]
    root = Path(__file__).resolve().parents[1] / "_native"
    cc = shutil.which(compiler or os.environ.get("CXX", "g++")) or shutil.which("clang++")
    if cc is None:
        raise RuntimeError("install a C++17 compiler (g++ or clang++) for this command")
    flags = FLAGS + (["-shared", "-fPIC"] if shared else [])
    version = subprocess.check_output([cc, "--version"], text=True).splitlines()[0]
    identity = repr((cc, version, flags, platform.machine(), platform.system())).encode()
    # This is cache invalidation, not a run/provenance archive. No result files.
    for source in sorted(root.rglob("*")):
        if source.is_file() and source.suffix in (".hpp", ".cpp"):
            identity += source.relative_to(root).as_posix().encode() + b"\0" + source.read_bytes()
    key = hashlib.sha256(identity).hexdigest()[:20]
    base = Path(cache or os.environ.get("BOXQ_CACHE", ".cache/boxq")) / key
    base.mkdir(parents=True, exist_ok=True)
    suffix = ".dylib" if platform.system() == "Darwin" else ".so"
    target = base / (name + (suffix if shared else ""))
    if not target.exists():
        with tempfile.TemporaryDirectory(dir=base, prefix="compile-") as temporary:
            built = Path(temporary) / target.name
            proc = subprocess.run(
                [cc, *flags, str(root / (name + ".cpp")), "-o", str(built)],
                text=True,
                capture_output=True,
            )
            if proc.returncode:
                raise RuntimeError("C++ compilation failed:\n" + proc.stderr)
            os.replace(built, target)
    return target.resolve(), {
        "compiler": version,
        "flags": flags,
        "build_key": key,
        "executable_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
    }
