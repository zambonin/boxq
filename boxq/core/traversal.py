"""Product traversal of a table automaton and a query: enumeration and counting.

The traversal memoizes (table state, query state, depth) and prunes subtrees
whose value bounds cannot satisfy the query. A lazy product of two tables in
the same coordinate system compares them; support differences distinguish
these particular functions in these coordinates and are NOT certificates of
affine/CCZ inequivalence. No comparison matrix or explicit product graph is
built, but memoization grows with the reached product keys.
"""
from __future__ import annotations

from .automaton import TableAutomaton
from .encoding import input_bit, output_bit
from .query import Query


def _advance(table, node, level, sigma):
    if hasattr(table, 'advance'):
        return table.advance(node, level, sigma)
    advance = not table.is_terminal(node) and table.level(node) == level
    return table.child(node, sigma) if advance else node


def _setup(table, query, stats):
    stats.update(
        {
            'product_states': 0,
            'pruned_product_states': 0,
            'expanded_product_states': 0,
            'liveness_calls': 0,
            'enumeration_calls': 0,
            'results': 0,
            'bounds_built': False,
            'bound_states': 0,
            'enumeration_complete': False,
        },
    )
    bounds = None
    if query.possible is not None:
        stats['bounds_built'] = table._bounds is None
        bounds = table.value_bounds()
        stats['bound_states'] = len(bounds)
    return bounds


def iter_matches(table, query, *, stats=None):
    """Stream matching (a,b,value) tuples without a retained O(K) output list.

    Table bounds can be reused. Feasibility memoization is local to this query.
    Stopping iteration early leaves enumeration_complete=False in the counters.
    expanded_product_states counts distinct non-pruned (table, query, depth)
    triples, including rejected final states. Native call/cache counts measure
    different work. Exact paper counters require full exhaustion.
    """
    if stats is None:
        stats = {}
    bounds = _setup(table, query, stats)
    n = table.n
    memo = {}

    def live(node, qstate, level):
        stats['liveness_calls'] += 1
        key = (node, qstate, level)
        if key in memo:
            return memo[key]
        stats['product_states'] += 1
        pruned = bounds is not None and (not query.possible(*bounds[node]))
        if pruned:
            stats['pruned_product_states'] += 1
            answer = False
        elif level == n:
            answer = table.is_terminal(node) and query.final(qstate) and query.accept(table.value(node))
        else:
            answer = False
            for sigma in range(4):
                nq = query.step(level, qstate, sigma)
                if nq is not None and live(_advance(table, node, level, sigma), nq, level + 1):
                    answer = True
                    break
        if not pruned:
            stats['expanded_product_states'] += 1
        memo[key] = answer
        return answer

    def emit(node, qstate, level, a, b):
        stats['enumeration_calls'] += 1
        if level == n:
            stats['results'] += 1
            yield (a, b, table.value(node))
            return
        for sigma in range(4):
            nq = query.step(level, qstate, sigma)
            if nq is None:
                continue
            child = _advance(table, node, level, sigma)
            if live(child, nq, level + 1):
                yield from emit(child, nq, level + 1, a << 1 | input_bit(sigma), b << 1 | output_bit(sigma))
    if live(table.root, query.q0, 0):
        yield from emit(table.root, query.q0, 0, 0, 0)
    stats['enumeration_complete'] = True


def evaluate_detailed(table: TableAutomaton, query: Query):
    """Fully enumerate, returning a list and separately defined work counters.

    O(P+nK) work and O(P+n+K) space plus optional bound preprocessing, under
    constant-cost query transitions/hashing. This wrapper materializes O(K)
    results; iter_matches is the streaming alternative.
    """
    stats = {}
    results = list(iter_matches(table, query, stats=stats))
    return (results, stats)


def count_matches(table, query, *, stats=None):
    """Count answers by memoized suffix multiplicity, without enumerating K words.

    Unlike feasibility, all admissible outgoing edges contribute; edges leading
    to an identical child still count separately. Counts use arbitrary-precision
    Python integers. Counters describe counting, not the paper's enumeration.
    """
    if stats is None:
        stats = {}
    bounds = _setup(table, query, stats)
    memo = {}
    n = table.n
    stats['mode'] = 'count-only'

    def count(node, qstate, level):
        stats['liveness_calls'] += 1
        key = (node, qstate, level)
        if key in memo:
            return memo[key]
        stats['product_states'] += 1
        if bounds is not None and (not query.possible(*bounds[node])):
            stats['pruned_product_states'] += 1
            value = 0
        else:
            stats['expanded_product_states'] += 1
            if level == n:
                value = int(
                    (
                        table.is_terminal(node)
                        and query.final(qstate)
                        and query.accept(table.value(node))
                    ),
                )
            else:
                value = 0
                for sigma in range(4):
                    nq = query.step(level, qstate, sigma)
                    if nq is not None:
                        value += count(_advance(table, node, level, sigma), nq, level + 1)
        memo[key] = value
        return value
    result = count(table.root, query.q0, 0)
    stats['results'] = result
    stats['count_complete'] = True
    return result


OPERATIONS = {
    "left-only": lambda left, right: left != 0 and right == 0,
    "right-only": lambda left, right: left == 0 and right != 0,
    "both": lambda left, right: left != 0 and right != 0,
    "either": lambda left, right: left != 0 or right != 0,
    "support-xor": lambda left, right: (left != 0) != (right != 0),
    "value-equal": lambda left, right: left == right,
    "value-different": lambda left, right: left != right,
}


class _Product:
    _bounds = None

    def __init__(self, left, right, operation):
        if left.n != right.n:
            raise ValueError("cross-table query requires equal widths")
        if operation not in OPERATIONS:
            raise ValueError("unknown cross-table operation")
        self.left, self.right, self.relation = (left, right, OPERATIONS[operation])
        self.n = left.n
        self.root = (left.root, right.root)

    def is_terminal(self, node):
        return self.left.is_terminal(node[0]) and self.right.is_terminal(node[1])

    def advance(self, node, level, symbol):
        return (
            _advance(self.left, node[0], level, symbol),
            _advance(self.right, node[1], level, symbol),
        )

    def value(self, node):
        return int(self.relation(self.left.value(node[0]), self.right.value(node[1])))


def _query(q):
    if q is None:
        return Query("all words", 0, lambda _level, _state, _symbol: 0, bool)
    # Only the word predicate carries over; values belong to two different tables.
    return Query("cross-table words", q.q0, q.step, bool, final=q.final)


def count_compare(left, right, operation="left-only", *, query=None, stats=None):
    return count_matches(_Product(left, right, operation), _query(query), stats=stats)


def iter_compare(left, right, operation="left-only", *, query=None, stats=None):
    product = _Product(left, right, operation)
    for a, b, _ in iter_matches(product, _query(query), stats=stats):
        yield (a, b, left.evaluate(a, b), right.evaluate(a, b))
