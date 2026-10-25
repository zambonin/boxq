"""The table automaton: a reduced, ordered, multi-terminal quaternary diagram.

A square integer table ``T`` over ``2^n x 2^n`` cells is represented as an
ordered multi-terminal decision diagram over the interleaved variable order
``a_{n-1}, b_{n-1}, ..., a_0, b_0`` (see :mod:`boxq.core.encoding`). Each internal
node carries its level and four children (one per symbol); terminals carry an
integer value. Three reductions make the diagram canonical for a fixed order:

1. terminals are shared, one per distinct value (a single *dead* terminal for 0);
2. a node whose four children are the same terminal is replaced by that terminal;
   identical nonterminal children do not remove a level;
3. two internal nodes *at the same level* with identical children are merged.

The level qualifier in rule (3) is essential: node identity is ``(level,
children)``, exactly as in an ordered BDD. Omitting it merges nodes across depths
and changes the specified level-respecting normal form.

The construction is table-agnostic; :mod:`boxq.core.tables` supplies the DDT, LAT,
and BCT matrices that instantiate it, padding a rectangular table to a square.
"""

from __future__ import annotations

import operator
from typing import Sequence


class TableAutomaton:
    """Reduced quaternary MTBDD for a ``2^n x 2^n`` integer table."""

    __slots__ = (
        "n",
        "_kind",
        "_kids",
        "_val",
        "_lvl",
        "_index",
        "root",
        "_reachable",
        "_bounds",
    )

    def __init__(self, table: Sequence[Sequence[int]], n: int) -> None:
        if not isinstance(n, int) or n < 0:
            raise ValueError("n must be a nonnegative integer")
        side = 1 << n
        if len(table) != side or any((len(row) != side for row in table)):
            raise ValueError("table shape must be 2^n by 2^n")
        self._initialize(n)
        self.root = self._build(table, list(range(1 << n)), list(range(1 << n)), 0)
        self._reachable = self._reach()

    @classmethod
    def from_rows(cls, rows, n: int):
        """Consume exactly 2^n rows once, using O(2^n) frontier references.

        A pending stripe of height 2^h contains 2^(n-h) node references.
        Pairing consecutive stripes joins four children in quadrant order.
        Hash-consing storage remains O(|S|) and can dominate resident memory.
        This eliminates the dense input matrix, not the quadratic table work.
        """
        if type(n) is not int or not 0 <= n <= 20:
            raise ValueError("n must be an integer from 0 to 20")
        obj = cls.__new__(cls)
        obj._initialize(n)
        N = 1 << n
        pending = {}
        count = 0
        for row in rows:
            if count >= N:
                raise ValueError("too many rows")
            # Require a finite sequence, avoiding an unbounded row iterator.
            if len(row) != N:
                raise ValueError("incorrect row width")
            stripe = [obj._terminal(v) for v in row]
            count += 1
            h = 0
            while h in pending:
                top = pending.pop(h)
                level = n - h - 1
                merged = []
                for j in range(0, len(stripe), 2):
                    children = (top[j], top[j + 1], stripe[j], stripe[j + 1])
                    if len(set(children)) == 1 and obj.is_terminal(children[0]):
                        merged.append(children[0])
                    else:
                        merged.append(obj._internal(children, level))
                stripe = merged
                h += 1
            pending[h] = stripe
        if count != N:
            raise ValueError("too few rows")
        if set(pending) != {n} or len(pending[n]) != 1:
            raise RuntimeError("invalid construction frontier")
        obj.root = pending[n][0]
        obj._reachable = obj._reach()
        return obj

    # ---- construction -----------------------------------------------------

    def _initialize(self, n):
        self.n = n
        # node id -> 'T' (terminal) | 'N' (internal)
        self._kind: dict[int, str] = {}
        # internal id -> (c0, c1, c2, c3)
        self._kids: dict[int, tuple] = {}
        # terminal id -> value
        self._val: dict[int, int] = {}
        # node id -> level (terminals: n)
        self._lvl: dict[int, int] = {}
        # canonical key -> node id
        self._index: dict[tuple, int] = {}
        self._bounds = None

    def _terminal(self, value: int) -> int:
        if isinstance(value, bool):
            raise TypeError("table entries must be integers, not booleans")
        value = operator.index(value)
        key = ("T", value)
        node = self._index.get(key)
        if node is None:
            node = len(self._index)
            self._index[key] = node
            self._kind[node] = "T"
            self._val[node] = value
            self._lvl[node] = self.n
        return node

    def _internal(self, children: tuple, level: int) -> int:
        key = ("N", level, children)
        node = self._index.get(key)
        if node is None:
            node = len(self._index)
            self._index[key] = node
            self._kind[node] = "N"
            self._kids[node] = children
            self._lvl[node] = level
        return node

    def _build(self, table, rows, cols, level) -> int:
        if level == self.n:
            return self._terminal(table[rows[0]][cols[0]])
        half = len(rows) // 2
        top, bot = (rows[:half], rows[half:])
        left, right = (cols[:half], cols[half:])
        children = (
            self._build(table, top, left, level + 1),
            self._build(table, top, right, level + 1),
            self._build(table, bot, left, level + 1),
            self._build(table, bot, right, level + 1),
        )
        if children[0] == children[1] == children[2] == children[3] and self.is_terminal(
            children[0]
        ):
            # constant-block elimination
            return children[0]
        return self._internal(children, level)

    def _reach(self) -> frozenset:
        seen, stack = (set(), [self.root])
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            if self._kind[node] == "N":
                stack.extend(self._kids[node])
        return frozenset(seen)

    # ---- accessors (used by queries and figure generation) ----------------

    def is_terminal(self, node: int) -> bool:
        return self._kind[node] == "T"

    def level(self, node: int) -> int:
        return self._lvl[node]

    def value(self, node: int) -> int:
        return self._val[node]

    def child(self, node: int, sigma: int) -> int:
        return self._kids[node][sigma]

    def nodes(self):
        return iter(self._reachable)

    def terminals(self):
        return (u for u in self._reachable if self._kind[u] == "T")

    def evaluate(self, a: int, b: int) -> int:
        """Return ``T[a][b]``; indices must lie inside the represented matrix."""
        if not (0 <= a < 1 << self.n and 0 <= b < 1 << self.n):
            raise IndexError("cell outside represented matrix")
        node = self.root
        for i in range(self.n):
            if self._kind[node] == "T":
                return self._val[node]
            if self._lvl[node] == i:
                a_bit = a >> self.n - 1 - i & 1
                b_bit = b >> self.n - 1 - i & 1
                node = self._kids[node][2 * a_bit + b_bit]
        return self._val[node]

    # ---- metrics ----------------------------------------------------------

    def num_states(self) -> int:
        """Reachable nodes, counting internal, accepting, and the dead terminal."""
        return len(self._reachable)

    def distinct_values(self) -> int:
        return len({self._val[u] for u in self.terminals()})

    def value_bounds(self) -> dict[int, tuple[int, int]]:
        """Cache (minimum, maximum) reachable value per state, in one DAG pass.

        This is an additional Python index, NOT part of the base packed payload.
        Its construction and memory must be accounted for separately.
        """
        if self._bounds is None:
            bounds = {}

            def visit(node):
                if node in bounds:
                    return bounds[node]
                if self.is_terminal(node):
                    value = self.value(node)
                    pair = (value, value)
                else:
                    children = [visit(c) for c in self._kids[node]]
                    pair = (min((lo for lo, hi in children)), max((hi for lo, hi in children)))
                bounds[node] = pair
                return pair

            visit(self.root)
            self._bounds = bounds
        return self._bounds
