"""Versioned reproduction records, inputs, outputs and environment identity."""

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

import numpy as np

from .. import __version__
from .._json import write_json as write_json

SCHEMA = "boxq-reproduction-v1"


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def lookup_digest(values):
    return hashlib.sha256(json.dumps(list(values), separators=(",", ":")).encode()).hexdigest()


def identity():
    root = Path(__file__).resolve().parents[2]
    revision, dirty = None, None
    try:
        top = subprocess.check_output(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        if Path(top).resolve() == root:
            revision = subprocess.check_output(
                ["git", "-C", str(root), "rev-parse", "HEAD"], text=True
            ).strip()
            dirty = bool(
                subprocess.check_output(
                    ["git", "-C", str(root), "status", "--porcelain"], text=True
                )
            )
    except (OSError, subprocess.CalledProcessError):
        pass
    fingerprint = hashlib.sha256()
    for source in sorted((root / "boxq").rglob("*")):
        if source.is_file() and source.suffix in (".py", ".cpp", ".hpp", ".json", ".txt"):
            fingerprint.update(
                source.relative_to(root).as_posix().encode() + b"\0" + source.read_bytes()
            )
    cpu = platform.processor()
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.exists():
        cpu = next(
            (
                line.partition(":")[2].strip()
                for line in cpuinfo.read_text().splitlines()
                if line.startswith("model name")
            ),
            cpu,
        )
    policies = sorted(
        {
            p.read_text().strip()
            for p in Path("/sys/devices/system/cpu").glob("cpu*/cpufreq/scaling_governor")
        }
    )
    return {
        "schema": SCHEMA,
        "version": __version__,
        "source_commit": revision,
        "source_dirty": dirty,
        "package_sha256": fingerprint.hexdigest(),
        "python": sys.version,
        "numpy": np.__version__,
        "platform": platform.platform(),
        "cpu": cpu,
        "frequency_governors": policies,
        "affinity": sorted(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None,
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
    }


def output_record(path, root):
    path = Path(path)
    return {
        "path": str(path.relative_to(root)),
        "bytes": path.stat().st_size,
        "sha256": digest(path),
    }
