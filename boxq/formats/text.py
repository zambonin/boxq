"""Three small record writers. Output goes to stdout or one requested file."""
from contextlib import contextmanager
import csv
import math
import os
from pathlib import Path
import sys
import tempfile


@contextmanager
def destination(path=None):
    """A failed computation must not replace a previously written output file."""
    if path is None or str(path) == "-":
        yield sys.stdout
        return
    target = Path(path).expanduser()
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=target.parent,
                                         prefix="." + target.name, delete=False) as stream:
            temporary = Path(stream.name)
            yield stream
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def text(value, precision=6):
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if not math.isfinite(value):
            return str(value)
        formatted = f"{value:.{precision}f}"
        return formatted.rstrip("0").rstrip(".") if "." in formatted else formatted
    return str(value)


def tex_escape(value):
    escapes = {"\\": r"\textbackslash{}", "&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#",
               "_": r"\_", "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}
    return "".join(escapes.get(c, c) for c in value)


def write(rows, stream, *, format="csv", columns=None, precision=6):
    """Write flat dictionaries. CSV/DKVP share field names; TeX is a tabular fragment.

    Plain DKVP has no quoting. Refuse delimiters rather than silently corrupting
    user-supplied names; use CSV when values contain comma, equals or newline.
    """
    iterator = iter(rows)
    first = next(iterator, None)
    columns = list(columns or (first.keys() if first is not None else []))
    if first is not None and any(c not in first for c in columns):
        raise ValueError("unknown output column; available: " + ", ".join(first))
    if not columns:
        return
    def records():
        if first is not None:
            yield first
        yield from iterator
    if format == "csv":
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(columns)
        for row in records():
            writer.writerow([text(row.get(c), precision) for c in columns])
    elif format == "dkvp":
        for row in records():
            fields = [(c, text(row.get(c), precision)) for c in columns]
            if any(any(ch in v for ch in ",=\r\n") for pair in fields for v in pair):
                raise ValueError("DKVP cannot safely represent this field; select --format csv")
            stream.write(",".join(f"{k}={v}" for k, v in fields) + "\n")
    elif format == "tex":
        stream.write(r"\begin{tabular}{" + "l" * len(columns) + "}\n\\hline\n")
        stream.write(" & ".join(tex_escape(c) for c in columns) + r" \\" + "\n\\hline\n")
        for row in records():
            stream.write(" & ".join(tex_escape(text(row.get(c), precision)) for c in columns) + r" \\" + "\n")
        stream.write("\\hline\n\\end{tabular}\n")
    else:
        raise ValueError("format must be csv, dkvp, or tex")
