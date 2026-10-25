"""Build the top-level command parser and its shared argument types."""

from argparse import ArgumentParser, ArgumentTypeError
from .. import __version__


KINDS = ("DDT", "LAT", "BCT")


def integer(value):
    try:
        return int(value, 0)
    except ValueError as exc:
        raise ArgumentTypeError("expected an integer, e.g. 5 or 0x05") from exc


def equation(value):
    try:
        fields = tuple(int(v, 0) for v in value.split(":"))
    except ValueError as exc:
        raise ArgumentTypeError("expected A:B:RHS, e.g. 0x3:0x5:1") from exc
    if len(fields) != 3 or fields[2] not in (0, 1):
        raise ArgumentTypeError("expected A:B:RHS with RHS 0 or 1")
    return fields


def export_options(parser):
    parser.add_argument("-f", "--format", choices=("csv", "dkvp", "tex"), default="csv")
    parser.add_argument("-o", "--output", help="write one file; default stdout")
    parser.add_argument("--columns", help="comma-separated output fields")
    parser.add_argument("--precision", type=int, default=6, help="decimal places, default 6")


def selection_options(parser):
    parser.add_argument("names", nargs="*", help="S-box names, FI:0000, or @lookup.json")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--all", action="store_true", help="all 288 catalog names")
    group.add_argument("--selected", action="store_true", help="14 S-boxes selected in the article")
    parser.add_argument("--unique", action="store_true", help="collapse lookup aliases")


def parser():
    root = ArgumentParser(
        prog="boxq", description="Compute cryptanalytic tables and export CSV, DKVP, or TeX."
    )
    root.add_argument("--version", action="version", version=__version__)
    sub = root.add_subparsers(dest="command", required=True)
    p = sub.add_parser("list", help="list available S-boxes")
    p.add_argument(
        "--extras", action="store_true", help="also list the bundled MISTY1 S7/S9 inputs"
    )
    export_options(p)
    p = sub.add_parser(
        "generate-sboxes",
        help="extract pinned S-box source declarations without installing SageMath",
    )
    p.add_argument("--sage-file", help="local pinned SageMath10.9 sboxes.py source")
    p.add_argument("--sage-license-file", help="local COPYING.txt at the same pinned revision")
    p.add_argument("--output", help="generated catalog JSON destination")
    p.add_argument("--rfc-file", help="use a local copy of RFC 2994 plaintext")
    p.add_argument("--check", action="store_true", help="verify the bundled JSON without writing")
    p = sub.add_parser("matrix", help="output a complete DDT, LAT, or BCT")
    p.add_argument("name")
    p.add_argument("--kind", choices=KINDS, default="DDT", type=str.upper)
    p.add_argument("--raw", action="store_true", help="retain trivial entries")
    p.add_argument("--entries", action="store_true", help="rows a,b,value instead of a wide matrix")
    export_options(p)
    p = sub.add_parser("stats", help="state counts, ratios and header-free payload costs")
    selection_options(p)
    p.add_argument(
        "--kind", nargs="+", choices=KINDS, type=str.upper, help="table kinds; default DDT LAT BCT"
    )
    export_options(p)
    p = sub.add_parser("spectrum", help="value frequencies on the nontrivial table domain")
    p.add_argument("name", nargs="?", default="PRESENT")
    p.add_argument("--kind", choices=KINDS, default="DDT", type=str.upper)
    export_options(p)
    p = sub.add_parser("query", help="compose word and value constraints; count or stream matches")
    p.add_argument("name", nargs="?", default="PRESENT")
    p.add_argument("--kind", choices=KINDS, default="DDT", type=str.upper)
    p.add_argument("--mode", choices=("count", "entries"), default="count")
    p.add_argument("--against", help="compare with another S-box in the same coordinates")
    p.add_argument(
        "--operation",
        choices=(
            "left-only",
            "right-only",
            "both",
            "either",
            "support-xor",
            "value-equal",
            "value-different",
        ),
        default="left-only",
    )
    p.add_argument("--input", type=integer)
    p.add_argument("--output-difference", dest="difference", type=integer)
    p.add_argument("--input-mask")
    p.add_argument("--output-mask")
    p.add_argument("--regex")
    p.add_argument("--max-weight", type=int)
    p.add_argument("--diagonal", action="store_true")
    p.add_argument("--linear", type=equation, action="append", default=[])
    p.add_argument(
        "--include-trivial", action="store_true", help="include cleared coordinates as stored"
    )
    v = p.add_mutually_exclusive_group()
    v.add_argument("--value", type=int)
    v.add_argument("--at-least", type=int)
    v.add_argument("--magnitude", type=int)
    p.add_argument("--limit", type=int, help="limit emitted entries; not a total count")
    export_options(p)
    from ..experiments.commands import register as register_experiments

    register_experiments(sub)
    return root
