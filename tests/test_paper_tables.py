"""Deterministic paper tables and writers."""

import csv
import io

import pytest

from boxq.core.catalog import lookup
from boxq.core.tables import compute
from boxq.paper.examples import example_numbers
from boxq.paper.format import write
from boxq.paper.tables import DETERMINISTIC, generate, present_blocks


def test_exact_queries(small_tables):
    assert [tuple(r.values())[1:] for r in small_tables[3].rows] == [
        (7, 16, 127, 146),
        (26, 19, 8128, 1403),
        (12, 11, 129, 135),
        (24, 28, 255, 779),
        (0, 24, 24, 232),
        (5, 15, 116, 146),
        (63, 49, 1091, 1492),
    ]
    assert [(r["threshold"], r["results"], r["expanded"]) for r in small_tables[5].rows] == [
        (4, 36, 53),
        (16, 1275, 17098),
        (16, 2, 43),
        (6, 510, 5459),
    ]


def test_aggregates_and_selected_order(small_tables):
    rows = small_tables[6].rows
    assert [(r["n"], r["sboxes"]) for r in rows] == [
        (3, 3),
        (4, 215),
        (5, 7),
        (6, 3),
        (7, 1),
        (8, 58),
        (9, 1),
    ]
    assert rows[1] == dict(
        n=4, sboxes=215, DDT="5.2 [4.6–8.8]", LAT="3.8 [3.2–5.8]", BCT="3.9 [3.2–8.3]"
    )
    assert rows[-1] == dict(n=9, sboxes=1, DDT="217.4", LAT="75.6", BCT="27.4")
    assert [r["states"] for r in small_tables[7].rows] == [
        9,
        39,
        34,
        107,
        356,
        1516,
        5393,
        5388,
        5590,
        5652,
        915,
        5654,
        240,
        1206,
    ]
    assert [tuple(r[k] for k in ("graph", "dense", "bitmap")) for r in small_tables[8].rows] == [
        ("19 B", "9 B", "9 B"),
        ("119 B", "66 B", "45 B"),
        ("104 B", "66 B", "45 B"),
        ("377 B", "259 B", "209 B"),
        ("1.57 KiB", "0.5 KiB", "0.50 KiB"),
        ("8.15 KiB", "6.0 KiB", "3.56 KiB"),
        ("34.2 KiB", "16.0 KiB", "12.0 KiB"),
        ("34.2 KiB", "16.0 KiB", "12.0 KiB"),
        ("35.5 KiB", "24.0 KiB", "14.7 KiB"),
        ("35.9 KiB", "24.0 KiB", "17.6 KiB"),
        ("4.48 KiB", "32.0 KiB", "13.6 KiB"),
        ("35.9 KiB", "32.0 KiB", "19.0 KiB"),
        ("0.94 KiB", "24.0 KiB", "8.6 KiB"),
        ("6.49 KiB", "96.0 KiB", "44.6 KiB"),
    ]


@pytest.mark.parametrize("number", DETERMINISTIC)
@pytest.mark.parametrize("format", ["tex", "csv", "dkvp"])
def test_writers(number, format, small_tables):
    table = small_tables[number]
    out = io.StringIO()
    write(table, out, format=format)
    text = out.getvalue()
    if format == "tex":
        assert r"\begin{tabular}" in text and r"\end{tabular}" in text
        assert r"\revpurple" not in text
        if number == 1:
            assert text.count(r"\cellcolor") == 256
        if number in (6, 7, 8):
            assert "FI row deliberately omitted" in text
    elif format == "csv":
        parsed = list(csv.DictReader(io.StringIO(text)))
        assert len(parsed) == len(table.rows)
        if number == 2:
            assert parsed[0]["a"] == "000"
    else:
        assert len(text.splitlines()) == len(table.rows)
        assert all("=" in line for line in text.splitlines())


def test_blocks_and_prose():
    counts = present_blocks(compute(lookup("PRESENT")))
    assert sum(counts.values()) == 64 and len(counts) == 16
    assert counts[(0, 0, 0, 0)] == 11
    assert sum(c for _, c in counts.most_common(3)) == 25
    r = {r["name"]: r["value"] for r in example_numbers()}
    assert r["catalog_names"] == 288 and r["distinct_lookups"] == 259
    assert r["aes_extremal_without_threshold_bound"] == 5393
    assert r["skipjack_extremal_expanded"] == 16
    assert r["sea_states"] == 9 and r["encoding_a5_b3"] == "213"
    assert r["figure1_highlight_a"] == 6 and r["figure1_highlight_b"] == 4


def test_missing_inputs_fail_before_work():
    for numbers in ([6], [7, 8]):
        with pytest.raises(ValueError, match="FI"):
            generate(numbers)
    with pytest.raises(ValueError, match="timing"):
        generate([4])
    with pytest.raises(ValueError):
        generate([7], large_results={"FI:0000": {}}, without_fi=True)
