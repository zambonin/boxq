"""Exact graph recurrences; not a claim of speed over cached matrix summaries."""
from collections import Counter
from functools import lru_cache
from math import inf
from .automaton import TableAutomaton


def _histogram(aut: TableAutomaton, zero_input: bool) -> Counter:
    symbols = (0, 1) if zero_input else (0, 1, 2, 3)
    memo = {}

    def visit(node, depth):
        if aut.is_terminal(node):
            # A constant suffix block represents many cells, not one path.
            return Counter({aut.value(node): len(symbols) ** (aut.n - depth)})
        if node in memo:
            return memo[node]
        if aut.level(node) != depth:
            raise ValueError('histogram expects the level-preserving normal form')
        counts = Counter()
        for symbol in symbols:
            counts.update(visit(aut.child(node, symbol), depth + 1))
        memo[node] = counts
        return counts
    return visit(aut.root, 0)


def value_histogram(aut: TableAutomaton) -> Counter:
    """Count all represented cells by value, including zero and masked cells."""
    return _histogram(aut, False)


def differential_spectrum(aut: TableAutomaton) -> Counter:
    """Count values only for a != 0; accepts raw or origin-masked DDTs.

    For an origin-masked DDT the removed row histogram is just {0: 2^n},
    reproducing the subtraction in the manuscript. Counting that row explicitly
    also prevents silently relying on the mask when a raw table is supplied.
    """
    counts = value_histogram(aut)
    counts.subtract(_histogram(aut, True))
    return Counter({v: count for v, count in counts.items() if count})


def differential_branch_number(aut: TableAutomaton):
    """Minimum wt(a)+wt(b) for a != 0 and nonzero table value.

    The input-activity flag permits either a raw or masked DDT; an empty
    feasible set returns infinity. No complete list of cells is generated.
    """

    @lru_cache(None)
    def visit(node, depth, active):
        if aut.is_terminal(node):
            if aut.value(node) == 0:
                return inf
            if active:
                return 0
            return 1 if depth < aut.n else inf
        if aut.level(node) != depth:
            raise ValueError('branch number expects the level-preserving normal form')
        return min(
            (s.bit_count() + visit(aut.child(node, s), depth + 1, active or bool(s & 2)) for s in range(4)),
        )
    return visit(aut.root, 0, False)
