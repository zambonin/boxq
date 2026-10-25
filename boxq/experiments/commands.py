"""Explicit reproducible experiment commands; result files are opt-in outputs."""

from pathlib import Path

from .provenance import identity, write_json


def register(sub):
    parser = sub.add_parser("experiment", help="run and retain a paper experiment")
    parser.add_argument(
        "experiment",
        choices=(
            "catalog",
            "random",
            "variants",
            "compression",
            "large",
            "sharing",
            "timing",
            "present",
            "queries",
        ),
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--names", nargs="+")
    parser.add_argument("--widths", nargs="+", type=int, default=list(range(3, 10)))
    parser.add_argument("--seed", type=int)
    parser.add_argument("--partition-mib", type=int, default=128)
    parser.add_argument("--graph", help="verified QNF graph for per-level sharing")
    parser.add_argument("--repeats", type=int, default=15)
    parser.add_argument("--cpu", type=int)
    parser = sub.add_parser("reproduce", help="archive all nine tables and supporting experiments")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument(
        "--small-only", action="store_true", help="explicitly omit the 16-bit experiments"
    )
    parser.add_argument("--large-results", help="reuse a fully verified large experiment directory")
    parser.add_argument(
        "--reuse", help="reuse catalog/random/timing/present JSON from this directory"
    )
    parser.add_argument("--repeats", type=int, default=15)
    parser.add_argument("--cpu", type=int)


def execute(
    kind,
    folder,
    *,
    names=None,
    widths=range(3, 10),
    seed=None,
    partition_mib=128,
    graph=None,
    repeats=15,
    cpu=None,
):
    from ..core.catalog import select

    folder = Path(folder).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    producer = identity()
    if kind == "large":
        from .large import run, LARGE_INPUTS

        return run(
            folder,
            names=names or LARGE_INPUTS,
            seed=2026 if seed is None else seed,
            partition_mib=partition_mib,
        )
    if kind == "catalog":
        from .catalog import run

        result = run(select(names) if names else None)
    elif kind == "random":
        from .random import run

        result = run(widths=widths, seed=1 if seed is None else seed)
    elif kind == "variants":
        from .variants import rows, PAPER_NAMES

        result = {"rows": rows(select(names or PAPER_NAMES))}
    elif kind == "compression":
        from .compression import rows

        result = {
            "rows": rows(select(names or ("AES", "SKINNY_8", "CSS", "DryGASCON256")), folder=folder)
        }
    elif kind == "sharing":
        from ..native.file_ops import level_statistics
        from .provenance import digest

        if not graph:
            raise ValueError("sharing requires --graph")
        result = {"graph_sha256": digest(graph), "metrics": level_statistics(graph)}
    elif kind == "queries":
        from .query_checks import illustrative_rows, pruning_rows, COUNTER_POLICY

        entries = select(names or ("PRESENT", "AES"))
        result = {
            "counter_policy": COUNTER_POLICY,
            "illustrative": illustrative_rows(entries),
            "pruning": pruning_rows(entries),
            "constructors": "analysis.queries.presets; layered query step; depth n only",
            "fixed_input": "alternating 01 mask: PRESENT 0x5, AES 0x55",
        }
    elif kind in ("timing", "present"):
        records = []
        if kind == "timing":
            from ..paper.benchmark import measure_table4

            table = measure_table4(repeats=repeats, warmups=1, cpu=cpu, records=records)
            result = {"rows": table.rows, "note": table.note, "records": records, "cpu": cpu}
        else:
            from ..core.search import measure

            result = {
                "rows": list(measure(repeats=repeats, cpu=cpu, records=records)),
                "records": records,
                "cpu": cpu,
            }
    else:
        raise ValueError("unknown experiment")
    value = {"producer": producer, **result}
    write_json(folder / (kind + ".json"), value)
    return value


def run(args):
    if args.command == "reproduce":
        from .reproduce import run as reproduce

        return reproduce(
            args.output_dir,
            small_only=args.small_only,
            large_folder=args.large_results,
            reuse=args.reuse,
            repeats=args.repeats,
            cpu=args.cpu,
        )
    return execute(
        args.experiment,
        args.output_dir,
        names=args.names,
        widths=args.widths,
        seed=args.seed,
        partition_mib=args.partition_mib,
        graph=args.graph,
        repeats=args.repeats,
        cpu=args.cpu,
    )
