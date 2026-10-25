"""Generate all nine paper tables from computations and verified run records.

Table metadata, the PRESENT block counts and the article's payload units
are kept here; paper.format renders the returned tables.
"""

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
import statistics

from ..core import catalog
from ..analysis import reports
from ..analysis import queries as query_reports
from ..core.tables import compute

DETERMINISTIC = (1, 2, 3, 5, 6, 7, 8, 9)
TITLES = {
    1: "PRESENT DDT and repeated 2 x 2 blocks",
    2: "SEA DDT",
    3: "PRESENT and AES DDT query results",
    4: "Native count-query medians (microseconds)",
    5: "PRESENT and AES LAT/BCT query results",
    6: "State ratios by width (catalog names, including aliases)",
    7: "Selected S-box state counts and ratios",
    8: "Header-free packed payload sizes",
    9: "Quaternary, binary and row-major encoding variants",
}
QUERY_ORDER = ("fixed", "truncated", "impossible", "extremal", "weight2", "diagonal", "composite")
DISPLAY_NAMES = {
    "APN_6": "APN (6-bit)",
    "SKINNY_8": "SKINNY (8-bit)",
    "FI:0000": "MISTY1 FI",
    "Midori64:0000": "Midori64 super S-box",
}


@dataclass
class PaperTable:
    number: int
    rows: list[dict]
    note: str = "computed from bundled lookup values"
    extra: dict = field(default_factory=dict)


def present_blocks(matrix):
    """Counts of complete aligned blocks, including the all-zero block."""
    return Counter(
        tuple(int(matrix[a + i, b + j]) for i in (0, 1) for j in (0, 1))
        for a in range(0, len(matrix), 2)
        for b in range(0, len(matrix), 2)
    )


def format_payload(value, name, column):
    """The article's units/precision, with no embedded result values."""
    if name in ("FI:0000", "Midori64:0000"):
        unit, places = "MiB", 1
    elif name in ("SEA", "PRESENT", "Noekeon", "Ascon"):
        unit, places = "B", 0
    else:
        unit = "KiB"
        if column == "graph_bytes":
            places = 2 if name in ("APN_6", "WAGE", "SKINNY_8", "CSS", "DryGASCON256") else 1
        elif column == "bitmap_bytes":
            places = 2 if name in ("APN_6", "WAGE") else 1
        else:
            places = 1
    divisor = {"B": 1, "KiB": 1024, "MiB": 1024**2}[unit]
    return f"{Decimal(value) / divisor:.{places}f} {unit}"


def _ratio(values):
    text = f"{statistics.median(values):.1f}"
    return text if len(values) == 1 else f"{text} [{min(values):.1f}–{max(values):.1f}]"


def generate(
    numbers,
    *,
    without_fi=False,
    stats_rows=None,
    random_results=None,
    large_results=None,
    timing=None,
):
    """Return selected tables in article order. Check missing inputs before work.

    Table 4 needs measured ``timing``; Tables 6-8 need verified
    ``large_results`` unless ``without_fi`` explicitly omits the FI row.
    """
    numbers = tuple(sorted(set(numbers)))
    if not numbers or set(numbers) - set(TITLES):
        raise ValueError("select table numbers 1..9")
    if without_fi and large_results:
        raise ValueError("choose large results or without_fi, not both")
    if set(numbers) & {6, 7, 8} and not without_fi and not large_results:
        raise ValueError("Tables 6–8 include FI: supply verified large results or use without_fi")
    if 4 in numbers and timing is None:
        raise ValueError("Table 4 needs measured timing results")
    large = {name: record["summary"] for name, record in (large_results or {}).items()}
    fi = large.get("FI:0000")

    # One corpus pass per invocation; aliases reuse summaries, not graphs.
    if stats_rows is None and set(numbers) & {6, 7, 8}:
        entries = catalog.select(all_names=6 in numbers, selected=6 not in numbers)
        kinds = ("DDT", "LAT", "BCT") if set(numbers) & {6, 7} else ("DDT",)
        stats_rows = list(reports.stats(entries, kinds))
    stats_rows = stats_rows or []
    stats_index = {(r["name"], r["table"]): r for r in stats_rows}
    query_rows = []
    if set(numbers) & {3, 5}:
        kinds = (["DDT"] if 3 in numbers else []) + (["LAT", "BCT"] if 5 in numbers else [])
        query_rows = list(query_reports.query_summary(catalog.select(["PRESENT", "AES"]), kinds))
    qindex = {(r["name"], r["table"], r["query"]): r for r in query_rows}
    tables = []
    note = "computed; catalog aliases count separately; FI:0000 DDT read from supplied graph"
    if without_fi:
        note = "computed; CATALOG ONLY — FI row deliberately omitted (--small-only)"
    for number in numbers:
        if number in (1, 2):
            matrix = compute(catalog.lookup("PRESENT" if number == 1 else "SEA"))
            rows = [
                {
                    **({"a": f"{a:03b}"} if number == 2 else {}),
                    **{f"b{b}": int(v) for b, v in enumerate(row)},
                }
                for a, row in enumerate(matrix)
            ]
            extra = {"blocks": present_blocks(matrix)} if number == 1 else {}
            tables.append(PaperTable(number, rows, extra=extra))
        elif number == 3:
            rows = []
            for query in QUERY_ORDER:
                row = {"query": query}
                for box in ("PRESENT", "AES"):
                    result = qindex[box, "DDT", query]
                    row[box.lower() + "_results"] = result["matches"]
                    row[box.lower() + "_expanded"] = result["expanded"]
                rows.append(row)
            tables.append(PaperTable(3, rows))
        elif number == 4:
            tables.append(timing)
        elif number == 5:
            from ..experiments.query_checks import pruning_rows

            tables.append(PaperTable(5, pruning_rows(catalog.select(["PRESENT", "AES"]))))
        elif number == 6:
            groups = defaultdict(list)
            for r in stats_rows:
                groups[r["n"], r["table"]].append(r["ratio"])
            rows = [
                dict(
                    n=n,
                    sboxes=len(groups[n, "DDT"]),
                    **{k: _ratio(groups[n, k]) for k in ("DDT", "LAT", "BCT")},
                )
                for n in sorted({r["n"] for r in stats_rows})
            ]
            if fi:
                rows.append(dict(n=16, sboxes=1, DDT=f"{fi['ratio']:.1f}", LAT="—", BCT="—"))
            if random_results:
                randoms = {r["n"]: r["median"] for r in random_results["rows"]}
                if "Random16" in large:
                    randoms[16] = large["Random16"]["ratio"]
                for row in rows:
                    row["random"] = f"{randoms[row['n']]:.1f}" if row["n"] in randoms else "—"
            tables.append(PaperTable(6, rows, note))
        elif number in (7, 8):
            rows = []
            for name in [
                *catalog.SELECTED,
                *[k for k in ("FI:0000", "Midori64:0000") if k in large],
            ]:
                r = large[name] if name in large else stats_index[name, "DDT"]
                row = dict(sbox=DISPLAY_NAMES.get(name, name), n=r["n"], delta=r["maximum"])
                if number == 7:
                    row.update(states=r["states"], DDT=f"{r['ratio']:.1f}")
                    row.update(
                        {
                            k: "—" if name in large else f"{stats_index[name, k]['ratio']:.1f}"
                            for k in ("LAT", "BCT")
                        }
                    )
                else:
                    row.update(
                        {
                            k: format_payload(r[k + "_bytes"], name, k + "_bytes")
                            for k in ("graph", "dense", "bitmap")
                        }
                    )
                rows.append(row)
            tables.append(PaperTable(number, rows, note))
        elif number == 9:
            from ..experiments.variants import rows as variants, PAPER_NAMES

            tables.append(PaperTable(9, variants(catalog.select(PAPER_NAMES))))
    return tables
