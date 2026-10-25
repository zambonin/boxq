"""Query automata: word predicates over paired bits and table-value predicates.

A query reads one symbol per input/output bit pair, most significant first
(see :mod:`boxq.core.encoding`). Patterns build the paper's query families;
bit masks are integer masks on the original (a, b) coordinates, and each
affine equation (A, B, c) means parity(A & a) XOR parity(B & b) == c, without
changing coordinates. ``make`` assembles command-line restrictions into one
word predicate and one value predicate.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable, Tuple

from .encoding import input_bit, output_bit
from .regex import compile_regex

Result = Tuple[int, int, int]


@dataclass(frozen=True)
class Query:
    """A word automaton with an independent table-value predicate.

    ``step(depth, state, symbol)`` reads one paired input/output bit, encoded
    as ``2 * input_bit + output_bit``. Depth starts at zero and states must
    be hashable so a traversal can memoize them. Returning ``None`` rejects
    that transition. ``final(state)`` is checked after the full table width;
    a surviving prefix is not necessarily an accepting word.

    ``accept(value)`` selects terminal values. ``possible(lo, hi)`` may reject
    a whole subtree only when no value in that inclusive interval can pass
    ``accept``; leaving it as ``None`` disables that optional pruning rule.
    Predicates must be deterministic for a query's lifetime.
    """

    name: str
    q0: object
    step: Callable[[int, object, int], object]
    accept: Callable[[int], bool]
    # Safe over-approximation: False must imply that no value in [lo, hi]
    # can pass accept. None disables value pruning for a custom predicate.
    possible: Callable[[int, int], bool] | None = None
    # A surviving prefix need not be an accepting word (regex/parity queries).
    final: Callable[[object], bool] = lambda state: True


def fixed_input(a: int, n: int) -> Query:
    """All possible output differences for a fixed input difference ``a``."""

    def step(level, _q, sigma):
        return 0 if input_bit(sigma) == a >> n - 1 - level & 1 else None

    return Query(
        f"fixed input a={a:0{n}b}", 0, step, lambda v: v != 0, lambda lo, hi: lo != 0 or hi != 0
    )


def truncated(active_input: set, n: int) -> Query:
    """Input positions in ``active_input`` must be active; others free."""

    def step(level, _q, sigma):
        if level in active_input and input_bit(sigma) != 1:
            return None
        return 0

    return Query("truncated", 0, step, lambda v: v != 0, lambda lo, hi: lo != 0 or hi != 0)


def impossible(base: Query) -> Query:
    """Cells matching ``base``'s pattern that are *zero* (impossible)."""
    return Query(
        "impossible " + base.name,
        base.q0,
        base.step,
        lambda v: v == 0,
        lambda lo, hi: lo <= 0 <= hi,
        base.final,
    )


def value_equals(value: int) -> Query:
    return Query(
        f"value == {value}",
        0,
        lambda _level, _state, _symbol: 0,
        lambda v: v == value,
        lambda lo, hi: lo <= value <= hi,
    )


def magnitude_at_least(tau: int) -> Query:
    """High-|value| cells (e.g. high-bias linear approximations on a LAT)."""
    return Query(
        f"|value| >= {tau}",
        0,
        lambda _level, _state, _symbol: 0,
        lambda v: abs(v) >= tau,
        lambda lo, hi: max(abs(lo), abs(hi)) >= tau,
    )


def hamming_weight_at_most(w: int) -> Query:
    """Differentials with wt(a) + wt(b) <= w via a popcount counter automaton."""

    def step(_level, acc, sigma):
        acc2 = acc + input_bit(sigma) + output_bit(sigma)
        return acc2 if acc2 <= w else None

    return Query(
        f"wt(a)+wt(b) <= {w}", 0, step, lambda v: v != 0, lambda lo, hi: lo != 0 or hi != 0
    )


def diagonal(n: int) -> Query:
    """The linear relation a = b, recognised by (0|3)^n."""
    return Query(
        "linear a = b",
        0,
        lambda _level, _state, symbol: 0 if symbol in (0, 3) else None,
        lambda v: v != 0,
        lambda lo, hi: lo != 0 or hi != 0,
    )


def conjoin(name: str, qa: Query, qb: Query, accept: Callable[[int], bool]) -> Query:
    """Product of two query automata with a combined value test."""

    def step(level, state, sigma):
        sa, sb = state
        na = qa.step(level, sa, sigma)
        if na is None:
            return None
        nb = qb.step(level, sb, sigma)
        if nb is None:
            return None
        return (na, nb)

    return Query(
        name,
        (qa.q0, qb.q0),
        step,
        accept,
        final=lambda state: qa.final(state[0]) and qb.final(state[1]),
    )


def bit_masks(n: int, input_mask: str | None=None, output_mask: str | None=None) -> Query:
    if type(n) is not int or not 1 <= n <= 32:
        raise ValueError('n must be 1..32')
    masks = []
    for text in (input_mask, output_mask):
        text = '*' * n if text is None else text
        if not isinstance(text, str) or len(text) != n or any((c not in '01*' for c in text)):
            raise ValueError('each mask must have n symbols from 0,1,* (MSB first)')
        masks.append(text)

    def step(level, state, sigma):
        ai, bi = (str(sigma >> 1), str(sigma & 1))
        return 0 if masks[0][level] in ('*', ai) and masks[1][level] in ('*', bi) else None
    return Query(
        'bit masks ' + ','.join(masks),
        0,
        step,
        lambda v: v != 0,
        lambda lo, hi: lo != 0 or hi != 0,
    )


def affine_constraints(n: int, equations) -> Query:
    if type(n) is not int or not 1 <= n <= 32:
        raise ValueError('n must be 1..32')
    basis = {}
    inconsistent = False
    for eq in equations:
        if not isinstance(eq, (tuple, list)) or len(eq) != 3:
            raise ValueError('equation must be (input_mask,output_mask,rhs)')
        a, b, rhs = eq
        if (
            any((type(v) is not int for v in eq))
            or not 0 <= a < 1 << n
            or not 0 <= b < 1 << n
            or rhs not in (0, 1)
        ):
            raise ValueError('equation masks must fit n bits and rhs must be 0 or 1')
        row = a << n | b
        while row:
            pivot = row.bit_length() - 1
            if pivot not in basis:
                basis[pivot] = (row, rhs)
                break
            other, r = basis[pivot]
            row ^= other
            rhs ^= r
        if row == 0 and rhs:
            inconsistent = True
    if inconsistent:
        return Query(
            'inconsistent affine system',
            0,
            lambda _level, _state, _symbol: None,
            lambda v: False,
            final=lambda s: False,
        )
    rows = [basis[p] for p in sorted(basis, reverse=True)]
    rhs = sum((r << i for i, (_, r) in enumerate(rows)))
    contributes = []
    for level in range(n):
        bit = n - level - 1
        ai = bi = 0
        for i, (row, _) in enumerate(rows):
            ai |= (row >> bit + n & 1) << i
            bi |= (row >> bit & 1) << i
        contributes.append((0, bi, ai, ai ^ bi))

    def step(level, syndrome, symbol):
        return syndrome ^ contributes[level][symbol]
    return Query(
        f'affine system rank {len(rows)}',
        0,
        step,
        lambda v: v != 0,
        lambda lo, hi: lo != 0 or hi != 0,
        lambda syndrome: syndrome == rhs,
    )


def union_words(qa: Query, qb: Query, *, accept=None) -> Query:
    """Union of WORD predicates, with one explicitly chosen value predicate.

    This does not mean union of two independent (word,value) relations. The
    original accept/possible fields are deliberately replaced, not combined.
    None is a dead query state by the Query protocol; its side stays dead.
    """

    def step(level, state, symbol):
        a, b = state
        na = None if a is None else qa.step(level, a, symbol)
        nb = None if b is None else qb.step(level, b, symbol)
        return None if na is None and nb is None else (na, nb)

    def final(state):
        a, b = state
        return a is not None and qa.final(a) or (b is not None and qb.final(b))
    return Query('word union', (qa.q0, qb.q0), step, accept or (lambda v: v != 0), final=final)


def complement_words(q: Query, *, accept=None) -> Query:
    """Complement the word predicate within the table's exact-length universe."""

    def step(level, state, symbol):
        dead, old = state
        if dead:
            return (True, None)
        nxt = q.step(level, old, symbol)
        return (nxt is None, nxt)
    return Query(
        'word complement',
        (False, q.q0),
        step,
        accept or (lambda v: v != 0),
        final=lambda state: state[0] or not q.final(state[1]),
    )


def _value_predicates(value, magnitude, at_least):
    """Choose a terminal filter and its conservative inclusive-interval bound."""
    if value is not None:
        return (lambda entry: entry == value), (lambda lo, hi: lo <= value <= hi)
    if magnitude is not None:
        if magnitude < 0:
            raise ValueError("magnitude threshold must be nonnegative")
        return (lambda entry: abs(entry) >= magnitude), (
            lambda lo, hi: max(abs(lo), abs(hi)) >= magnitude
        )
    if at_least is not None:
        return (lambda entry: entry >= at_least), (lambda lo, hi: hi >= at_least)
    return (lambda entry: entry != 0), (lambda lo, hi: lo != 0 or hi != 0)


def make(
    n,
    kind="DDT",
    *,
    m=None,
    regex=None,
    input=None,
    output=None,
    input_mask=None,
    output_mask=None,
    max_weight=None,
    same=False,
    linear=(),
    value=None,
    at_least=None,
    magnitude=None,
    include_trivial=False,
):
    """Return one query over words of max(n, m) symbols.

    ``n`` and ``m`` are the input and output widths; ``m`` defaults to ``n``.
    For a rectangular table the shorter coordinate is zero-extended, and a
    leading-zero mask keeps every match inside the 2^n x 2^m domain. Masks,
    fixed coordinates and linear coefficients use their own widths.
    """
    m = n if m is None else m
    width = max(n, m)
    parts = []
    if regex is not None:
        parts.append(compile_regex(regex).query())
    masks = []
    for bits, fixed, mask in ((n, input, input_mask), (m, output, output_mask)):
        if mask is not None and (len(mask) != bits or any(c not in "01*" for c in mask)):
            raise ValueError(f"masks must have {bits} symbols from 0,1,*")
        if fixed is not None:
            if not 0 <= fixed < 1 << bits:
                raise ValueError("input/output coordinate is outside the table")
            explicit = f"{fixed:0{bits}b}"
            if mask is not None and any(c != "*" and c != b for c, b in zip(mask, explicit)):
                raise ValueError("fixed coordinate contradicts its mask")
            mask = explicit
        if mask is not None or bits < width:
            mask = "0" * (width - bits) + (mask or "*" * bits)
        masks.append(mask)
    if any(mask is not None for mask in masks):
        parts.append(bit_masks(width, *masks))
    if max_weight is not None:
        if max_weight < 0:
            raise ValueError("weight must be nonnegative")
        parts.append(hamming_weight_at_most(max_weight))
    if same:
        parts.append(diagonal(width))
    if linear:
        if any(not 0 <= a < 1 << n or not 0 <= b < 1 << m for a, b, _ in linear):
            raise ValueError("linear coefficients exceed the input/output widths")
        parts.append(affine_constraints(width, linear))
    if not include_trivial:

        def final(state):
            a, b = state
            return a if kind == "DDT" else (a and b) if kind == "BCT" else (a or b)

        parts.append(
            Query(
                "domain",
                (False, False),
                lambda _level, state, symbol: (
                    state[0] or bool(symbol & 2),
                    state[1] or bool(symbol & 1),
                ),
                lambda v: True,
                final=final,
            )
        )
    accept, possible = _value_predicates(value, magnitude, at_least)
    query = Query("all", 0, lambda _level, _state, _symbol: 0, accept)
    for part in parts:
        query = conjoin("constraints", query, part, accept)
    return replace(query, possible=possible)
