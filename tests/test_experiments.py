"""Scientific producers and archival failure paths beyond CLI formatting."""

import numpy as np
import pytest

from boxq.core.catalog import lookup, select
from boxq.core.automaton import TableAutomaton
from boxq.core.tables import compute
from boxq.experiments import reference
from boxq.experiments.properties import degree
from boxq.experiments.query_checks import illustrative_rows, pruning_rows
from boxq.experiments.records import large_records
from boxq.experiments.provenance import write_json
from boxq.experiments.variants import rows
from boxq.paper.benchmark import measure_table4


@pytest.mark.parametrize("kind", ("DDT", "LAT", "BCT"))
def test_independent_definitions_on_arbitrary_permutations(kind):
    for values in (list(range(8)), np.random.default_rng(17).permutation(16).tolist()):
        matrix = compute(values, kind)
        assert np.array_equal(matrix, reference.table(values, kind))
        assert (
            reference.state_count(matrix)
            == TableAutomaton(matrix, (len(values) - 1).bit_length()).num_states()
        )


def test_queries_include_rejected_final_states():
    entries = select(("PRESENT", "AES"))
    counts = {(r["name"], r["query"]): r["expanded"] for r in illustrative_rows(entries)}
    assert counts["PRESENT", "impossible"] == 11
    assert counts["AES", "impossible"] == 135
    assert [(r["zero_expanded"], r["bound_expanded"]) for r in pruning_rows(entries)] == [
        (53, 34),
        (17098, 3373),
        (43, 8),
        (5459, 1255),
    ]


def test_variant_and_degree_landmarks():
    result = rows(select(("PRESENT", "CSS")))
    assert [(r["quaternary"], r["binary"], r["row_major"]) for r in result] == [
        (39, 84, 50),
        (240, 470, 291),
    ]
    assert degree(list(range(16)))["algebraic_degree"] == 1
    assert degree(lookup("PRESENT"))["algebraic_degree"] == 3
    assert degree(lookup("AES"))["algebraic_degree"] == 7


def test_incomplete_large_job_is_not_reusable(tmp_path):
    write_json(
        tmp_path / "fi-0000.json",
        {
            "producer": {"schema": "boxq-reproduction-v1"},
            "name": "FI:0000",
            "status": "complete",
            "construction": {"verification": {"all_rows": False, "cells": 3 * 65536}},
        },
    )
    with pytest.raises(ValueError, match="incomplete"):
        large_records(tmp_path)


def test_archival_benchmark_sink(fake_benchmark):
    records = []
    table = measure_table4(repeats=2, records=records)
    assert "retained" in table.note
    assert all(options["records"] is records for _, _, options in fake_benchmark)
    assert all(r["packed_iqr_us"] == "0.020" for r in table.rows)


def test_experiment_command_returns_no_exit_payload(tmp_path):
    # The console script passes main()'s result to sys.exit; None means status 0.
    from boxq.cli.main import main

    assert main(["experiment", "compression", "--names", "PRESENT", "--output-dir", str(tmp_path)]) is None
    assert (tmp_path / "compression.json").is_file()
