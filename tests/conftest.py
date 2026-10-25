"""Shared publication fixtures."""

import pytest

from boxq.paper.tables import DETERMINISTIC
from boxq.paper.tables import generate
from boxq.paper import benchmark as paper_benchmark


@pytest.fixture(scope="module")
def small_tables():
    return {t.number: t for t in generate(DETERMINISTIC, without_fi=True)}


@pytest.fixture
def fake_benchmark(monkeypatch):
    """Synthetic medians for dispatch/format tests, never saved observations."""
    calls = []

    def measure(entries, kinds, **options):
        calls.append((entries, kinds, options))
        name = entries[0][0]
        for query in options["queries"]:
            for backend in options["backends"]:
                yield dict(
                    name=name, query=query, backend=backend, median_us=len(calls) / 10, iqr_us=0.02
                )

    monkeypatch.setattr(paper_benchmark, "measure", measure)
    return calls
