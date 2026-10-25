"""Archive paper tables, supporting experiments and per-result provenance.

run() orchestrates producers, paper.tables renders their results, and
experiments.reference provides independent matrix/reduction definitions.
Reused records retain their original producer identity and timing environment.
"""

from pathlib import Path

from ..core.catalog import data_path
from ..paper.tables import PaperTable, generate
from ..paper.format import write
from ..paper.examples import example_numbers
from .commands import execute
from .provenance import identity, write_json, digest, output_record
from .records import read, large_records


def run(folder, *, small_only=False, large_folder=None, reuse=None, repeats=15, cpu=None):
    if small_only and large_folder:
        raise ValueError("choose --small-only or --large-results")
    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    producer = identity()
    if cpu is None:
        import os

        cpu = min(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else None
    datasets = {}
    for kind in ("catalog", "random", "timing", "present"):
        prior = Path(reuse) / (kind + ".json") if reuse else None
        if prior and prior.is_file():
            datasets[kind] = read(prior)
            write_json(folder / (kind + ".json"), datasets[kind])
        else:
            datasets[kind] = execute(kind, folder, repeats=repeats, cpu=cpu)
    for kind in ("variants", "compression", "queries"):
        datasets[kind] = execute(kind, folder)
    large = {}
    if not small_only:
        if large_folder:
            large = large_records(large_folder)
        else:
            from .large import run as build_large

            large_folder = folder / "large"
            large = build_large(large_folder)
    tables = generate(
        range(1, 10),
        without_fi=small_only,
        stats_rows=datasets["catalog"]["rows"],
        random_results=datasets["random"],
        large_results=large,
        timing=PaperTable(4, datasets["timing"]["rows"], datasets["timing"]["note"]),
    )
    dependencies = {
        1: ("catalog",),
        2: ("catalog",),
        3: ("queries",),
        4: ("timing",),
        5: ("queries",),
        6: ("catalog", "random"),
        7: ("catalog",),
        8: ("catalog",),
        9: ("variants",),
    }
    manifest = {
        "schema": "boxq-reproduction-v1",
        "producer": producer,
        "scope": "small-only" if small_only else "complete paper experiments",
        "requested_repeats": repeats,
        "requested_cpu": cpu,
        "catalog": {"path": str(data_path()), "sha256": digest(data_path())},
        "results": [],
    }
    for table in tables:
        outputs = []
        for fmt in ("csv", "tex", "dkvp"):
            path = folder / f"table-{table.number}.{fmt}"
            with path.open("w") as stream:
                write(table, stream, format=fmt)
            outputs.append(output_record(path, folder))
        inputs = [
            output_record(folder / (kind + ".json"), folder) for kind in dependencies[table.number]
        ]
        if table.number in (6, 7, 8):
            inputs.extend(
                {
                    "name": name,
                    "input_sha256": record["input_sha256"],
                    "producer": record["producer"],
                    "summary": record["summary"],
                    "record": str(
                        Path(large_folder).resolve() / (name.lower().replace(":", "-") + ".json")
                    ),
                    "record_sha256": digest(
                        Path(large_folder) / (name.lower().replace(":", "-") + ".json")
                    ),
                }
                for name, record in large.items()
            )
        manifest["results"].append(
            {
                "table": table.number,
                "command": f"boxq reproduce --output-dir {folder}"
                + (" --small-only" if small_only else f" --large-results {large_folder}")
                + (f" --reuse {Path(reuse).resolve()}" if reuse else "")
                + f" --repeats {repeats}"
                + (f" --cpu {cpu}" if cpu is not None else ""),
                "producer": producer,
                "inputs": inputs,
                "outputs": outputs,
                "computation_producers": {
                    kind: datasets[kind]["producer"] for kind in dependencies[table.number]
                },
            }
        )
    write_json(
        folder / "numbers.json",
        {"producer": producer, "rows": list(example_numbers(fi_record=large.get("FI:0000")))},
    )
    manifest["supporting_results"] = [
        output_record(folder / (name + ".json"), folder) for name in (*datasets, "numbers")
    ]
    write_json(folder / "manifest.json", manifest)
    print(f"wrote {folder / 'manifest.json'}")
    return manifest
