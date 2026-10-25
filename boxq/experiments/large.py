"""Build, fully verify, inspect and pack the three large paper inputs."""

from pathlib import Path
import time

import numpy as np

from ..core.catalog import lookup
from ..analysis.reports import summarize
from ..native.build import build
from ..native.file_ops import convert, histogram, level_statistics
from .provenance import identity, lookup_digest, output_record, write_json, digest


LARGE_INPUTS = ("FI:0000", "Random16", "Midori64:0000")


def run(folder, *, names=LARGE_INPUTS, seed=2026, partition_mib=128, resume=True):
    """Retain every measured stage; failed/partial jobs are never complete records."""
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    producer = identity()
    inputs = {
        name: (
            np.random.default_rng(seed).permutation(65536).tolist()
            if name == "Random16"
            else lookup(name)
        )
        for name in names
    }
    results = {}
    for name, values in inputs.items():
        slug = name.lower().replace(":", "-")
        record_path = folder / (slug + ".json")
        input_hash = lookup_digest(values)
        if resume and record_path.exists():
            import json

            prior = json.loads(record_path.read_text())
            if prior.get("status") == "complete" and prior["input_sha256"] == input_hash:
                if all(
                    (folder / f["path"]).is_file() and digest(folder / f["path"]) == f["sha256"]
                    for f in prior["outputs"]
                ):
                    results[name] = prior
                    continue
        lookup_file = folder / (slug + ".lookup.json")
        write_json(lookup_file, values)
        graph = folder / (slug + ".qnf")
        packed = folder / (slug + ".qdd")
        record = {
            "producer": producer,
            "name": name,
            "n": 16,
            "table": "DDT",
            "input_sha256": input_hash,
            "seed": seed if name == "Random16" else None,
            "status": "running",
            "partition_mib": max(partition_mib, 1024) if name == "Midori64:0000" else partition_mib,
        }
        write_json(record_path, record)
        started = time.perf_counter()
        try:
            construction = build(
                values,
                "DDT",
                graph,
                verify=True,
                partition_mib=max(partition_mib, 1024)
                if name == "Midori64:0000"
                else partition_mib,
            )
            verification = construction["verification"]
            if not verification["all_rows"] or verification["cells"] != 2**32:
                raise RuntimeError("full-cell verification evidence is incomplete")
            metrics = histogram(graph)
            counts = {
                int(v): int(c) for v, c in metrics["histogram_all_normalized_coordinates"].items()
            }
            if (
                sum(counts.values()) != 2**32
                or sum(v * c for v, c in counts.items()) != 65536 * 65535
            ):
                raise RuntimeError("normalized DDT histogram identity failed")
            sharing = level_statistics(graph)
            packing = convert(graph, packed, "pack")
            summary = summarize(name, "DDT", 16, construction["states"], counts)
            if packed.stat().st_size != summary["graph_bytes"] + 40:
                raise RuntimeError("packed file size differs from the modeled graph payload")
            record.update(
                status="complete",
                construction=construction,
                metrics=metrics,
                sharing=sharing,
                packing=packing,
                summary=summary,
                total_wall_seconds=time.perf_counter() - started,
                outputs=[output_record(p, folder) for p in (lookup_file, graph, packed)],
            )
            write_json(record_path, record)
            results[name] = record
        except Exception as exc:
            record.update(
                status="failed",
                error=f"{type(exc).__name__}: {exc}",
                total_wall_seconds=time.perf_counter() - started,
            )
            write_json(record_path, record)
            raise
    return results
