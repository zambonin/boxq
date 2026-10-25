"""Command dispatch, text-producing commands and error handling."""

from itertools import islice
import sys
from ..analysis import reports
from ..core import catalog
from ..core.automaton import TableAutomaton
from ..core.tables import compute, padded
from ..formats import text as output
from .parser import KINDS, parser


def _entries(args):
    if args.names and (args.all or args.selected):
        raise ValueError("choose explicit names or --all/--selected, not both")
    return catalog.select(
        args.names, all_names=args.all, selected=args.selected, unique=args.unique
    )


def records(args):
    if args.command == "list":
        for name in catalog.names(extras=args.extras):
            values = catalog.lookup(name)
            permutation = len(set(values)) == len(values)
            yield {"name": name, "n": (len(values) - 1).bit_length(), "permutation": permutation}
    elif args.command == "matrix":
        matrix = compute(catalog.lookup(args.name), args.kind, raw=args.raw)
        for a, row in enumerate(matrix):
            if args.entries:
                for b, v in enumerate(row):
                    yield {"a": a, "b": b, "value": int(v)}
            else:
                yield {"a": a, **{f"b{b}": int(v) for b, v in enumerate(row)}}
    elif args.command == "stats":
        yield from reports.stats(_entries(args), args.kind or KINDS)
    elif args.command == "spectrum":
        yield from reports.spectrum(compute(catalog.lookup(args.name), args.kind), args.kind)
    elif args.command == "query":
        yield from _query(args)


def _table(name, kind):
    """Resolve a name and build its automaton over the zero-padded square table."""
    lookup = catalog.lookup(name)
    return lookup, TableAutomaton(padded(compute(lookup, kind)), max(lookup.n, lookup.m))


def _query(args):
    from ..core.query import make
    from ..core.traversal import count_compare, count_matches, iter_compare, iter_matches

    if args.against and any(v is not None for v in (args.value, args.at_least, args.magnitude)):
        raise ValueError(
            "--operation defines the two-table value relation; omit single-table value filters"
        )
    lookup, table = _table(args.name, args.kind)
    right = None
    if args.against:
        other, right = _table(args.against, args.kind)
        if (other.n, other.m) != (lookup.n, lookup.m):
            raise ValueError("cross-table queries require equal input and output widths")
    query = make(
        lookup.n, args.kind, m=lookup.m, regex=args.regex, input=args.input,
        output=args.difference, input_mask=args.input_mask, output_mask=args.output_mask,
        max_weight=args.max_weight, same=args.diagonal, linear=args.linear, value=args.value,
        at_least=args.at_least, magnitude=args.magnitude, include_trivial=args.include_trivial,
    )
    if args.mode == "count":
        if right is not None:
            yield {"count": count_compare(table, right, args.operation, query=query)}
        else:
            yield {"count": count_matches(table, query)}
        return
    if right is not None:
        hits = iter_compare(table, right, args.operation, query=query)
    else:
        hits = iter_matches(table, query)
    if args.limit is not None:
        if args.limit < 0:
            raise ValueError("limit must be nonnegative")
        hits = islice(hits, args.limit)
        print(f"entry output capped at {args.limit}; this is not a total count", file=sys.stderr)
    for hit in hits:
        fields = ("a", "b", "left", "right") if right is not None else ("a", "b", "value")
        yield dict(zip(fields, hit))


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        if args.command in ("experiment", "reproduce"):
            from ..experiments.commands import run

            run(args)
            return
        if args.command == "generate-sboxes":
            from ..core.catalog_generation import generate

            generate(
                rfc_file=args.rfc_file,
                sage_file=args.sage_file,
                sage_license_file=args.sage_license_file,
                output=args.output,
                check=args.check,
            )
            return
        if not 0 <= args.precision <= 15:
            raise ValueError("precision must be 0..15")
        columns = [c.strip() for c in args.columns.split(",")] if args.columns else None
        with output.destination(args.output) as stream:
            output.write(
                records(args), stream, format=args.format, columns=columns, precision=args.precision
            )
    except BrokenPipeError:
        # A caller such as `head` stopped consuming the stream.
        import os

        sys.stdout = open(os.devnull, "w")
    except (ValueError, TypeError, OSError, RuntimeError) as exc:
        print(f"boxq: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    except KeyboardInterrupt:
        print("boxq: interrupted", file=sys.stderr)
        raise SystemExit(130) from None
