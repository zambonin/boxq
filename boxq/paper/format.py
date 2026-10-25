"""Render paper tables without requiring a manuscript checkout or templates."""

from ..formats import text as output
from .tables import TITLES

QUERY_LABELS = {
    "fixed": "fixed input difference",
    "truncated": "truncated (2 MSB input active)",
    "impossible": "impossible (one input bit active)",
    "extremal": r"extremal ($=\Delta$)",
    "weight2": r"Hamming $\mathrm{wt}(a)+\mathrm{wt}(b)\leq 2$",
    "diagonal": r"linear $a=b$",
    "composite": r"composite ($\geq\Delta/2$, $\mathrm{wt}\leq 4$)",
}


def _text(value):
    return output.tex_escape(str(value)).replace("—", "---").replace("–", "--")


def write(table, stream, *, format="tex"):
    """TeX follows the paper layout; CSV/DKVP use stable machine-readable fields.

    Table 1's optional cell shading requires xcolor's table option. All other
    fragments use only ordinary LaTeX tabular, hline, and multicolumn commands.
    """
    if format != "tex":
        output.write(table.rows, stream, format=format)
        return
    number, rows = table.number, table.rows
    stream.write(f"% Table {number}: {TITLES[number]}\n% {table.note}\n")
    if number == 1:
        _present(table, stream)
        return
    if number == 2:
        heads = [r"$a\backslash b$", *[f"{b:03b}" for b in range(8)]]
        cells = [[r["a"], *[str(r[f"b{b}"]) for b in range(8)]] for r in rows]
    elif number == 3:
        heads = ["query", "res.", "prod.", "res.", "prod."]
        cells = [
            [
                QUERY_LABELS[r["query"]],
                *[
                    str(r[k])
                    for k in ("present_results", "present_expanded", "aes_results", "aes_expanded")
                ],
            ]
            for r in rows
        ]
    elif number == 4:
        heads = [
            "DDT query",
            "Packed automaton",
            r"Dense \texttt{int32}",
            "Coordinate index",
            "Adaptive index",
        ]
        cells = [
            [
                _text(r["name"] + ": " + ("fixed input" if r["query"] == "fixed" else r["query"])),
                *[
                    r[k]
                    + (
                        " [" + r[k.replace("_us", "_iqr_us")] + "]"
                        if k.replace("_us", "_iqr_us") in r
                        else ""
                    )
                    for k in ("packed_us", "int32_us", "indexed_us", "adaptive_us")
                ],
            ]
            for r in rows
        ]
    elif number == 5:
        heads = ["table", "query", "S-box", "res.", "zero", "bound"]
        cells = []
        for r in rows:
            lat = r["table"] == "LAT"
            query = r"$|\mathrm{LAT}|\geq\mathrm{lin.}$" if lat else r"value $=\beta$"
            suffix = f"(lin. {r['threshold']})" if lat else rf"($\beta={r['threshold']}$)"
            cells.append(
                [
                    r["table"],
                    query,
                    _text(r["sbox"]) + " " + suffix,
                    str(r["results"]),
                    str(r["zero_expanded"]),
                    str(r["bound_expanded"]),
                ]
            )
    elif number == 6:
        heads = [r"$n$", r"\#S-boxes", "DDT", "LAT", "BCT"]
        cells = [
            [
                str(r["n"]),
                str(r["sboxes"]),
                *[_text(r[k]).replace(" [", "~[") for k in ("DDT", "LAT", "BCT")],
            ]
            for r in rows
        ]
        if rows and "random" in rows[0]:
            heads.insert(3, "Random")
            for cell, row in zip(cells, rows):
                cell.insert(3, row["random"])
    elif number == 7:
        heads = [
            "S-box",
            r"$n$",
            r"$\Delta$",
            "States",
            r"DDT$\times$",
            r"LAT$\times$",
            r"BCT$\times$",
        ]
        cells = [
            [
                _text(r["sbox"]),
                str(r["n"]),
                str(r["delta"]),
                f"{r['states']:,}",
                *[_text(r[k]) for k in ("DDT", "LAT", "BCT")],
            ]
            for r in rows
        ]
    elif number == 8:
        heads = ["S-box", r"$n$", r"$\Delta$", "Autom.", "Dense", "Bitmap"]
        cells = [
            [
                _text(r["sbox"]),
                str(r["n"]),
                str(r["delta"]),
                *[_text(r[k]).replace(" ", "~") for k in ("graph", "dense", "bitmap")],
            ]
            for r in rows
        ]
    elif number == 9:
        heads = ["S-box", "Quaternary", "Binary", "Row-major"]
        cells = [
            [_text(r["sbox"]), *[str(r[k]) for k in ("quaternary", "binary", "row_major")]]
            for r in rows
        ]
    stream.write(r"\begin{tabular}{l" + "r" * (len(heads) - 1) + "}\n\\hline\n")
    if number == 3:
        stream.write(
            r" & \multicolumn{2}{c}{PRESENT ($n=4$)} & \multicolumn{2}{c}{AES ($n=8$)} \\" + "\n"
        )
    stream.write(" & ".join(heads) + r" \\" + "\n\\hline\n")
    for row in cells:
        stream.write(" & ".join(row) + r" \\" + "\n")
    stream.write("\\hline\n\\end{tabular}\n")


def _present(table, stream):
    rows, blocks = table.rows, table.extra["blocks"]
    # The article's six gray levels; membership is computed from the block counts.
    frequencies = sorted(set(blocks.values()))
    shades = dict(zip(frequencies, (6, 13, 24, 36, 46, 60)))
    if len(frequencies) != len(shades):
        raise ValueError("unexpected number of PRESENT block-frequency groups")
    stream.write("% Requires \\usepackage[table]{xcolor}. Zeros are shown as dots.\n")
    stream.write(r"\begin{tabular}{*{16}{c}}" + "\n")
    for a, row in enumerate(rows):
        cells = []
        for b in range(16):
            i, j = a // 2 * 2, b // 2 * 2
            block = tuple(rows[i + di][f"b{j + dj}"] for di in (0, 1) for dj in (0, 1))
            value = row[f"b{b}"]
            cells.append(
                rf"\cellcolor{{black!{shades[blocks[block]]}}}"
                + (str(value) if value else r"$\cdot$")
            )
        stream.write(" & ".join(cells) + (r"\\[1pt]" if a < 15 else "") + "\n")
    stream.write("\\end{tabular}\n")
