"""Bounded regular expressions over the symbols 0 through 3.

A pattern is parsed, built as a Thompson epsilon-NFA and determinized into
a RegexDFA, whose ``query`` gives a word predicate for the table traversal.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass


class RegexError(ValueError):
    """Invalid or deliberately unsupported regular-expression syntax."""


class RegexLimitError(ValueError):
    """The requested automaton exceeds a caller-specified construction limit."""


class _Parser:

    def __init__(self, text: str):
        if not isinstance(text, str):
            raise RegexError('pattern must be a string')
        if len(text) > 4096:
            raise RegexLimitError('pattern length limit is 4096 characters')
        self.text = ''.join(text.split())
        if self.text.startswith('^'):
            self.text = self.text[1:]
        if self.text.endswith('$'):
            self.text = self.text[:-1]
        self.pos = 0
        self.depth = 0

    def peek(self):
        return self.text[self.pos:self.pos + 1]

    def parse(self):
        node = self.union()
        if self.pos != len(self.text):
            raise RegexError(f'unexpected {self.peek()!r} at offset {self.pos}')
        return node

    def union(self):
        branches = [self.concat()]
        while self.peek() == '|':
            self.pos += 1
            branches.append(self.concat())
        return branches[0] if len(branches) == 1 else ('union', tuple(branches))

    def concat(self):
        seq = []
        while self.peek() and self.peek() not in ')|':
            seq.append(self.repeat())
        return ('concat', tuple(seq))

    def repeat(self):
        node = self.atom()
        ch = self.peek()
        if ch and ch in '*+?':
            self.pos += 1
            lo, hi = {'*': (0, None), '+': (1, None), '?': (0, 1)}[ch]
            node = ('repeat', node, lo, hi)
        elif ch == '{':
            self.pos += 1
            start = self.pos
            while self.peek().isdigit():
                self.pos += 1
            if start == self.pos:
                raise RegexError('expected repetition lower bound')
            lo = int(self.text[start:self.pos])
            hi = lo
            if self.peek() == ',':
                self.pos += 1
                start = self.pos
                while self.peek().isdigit():
                    self.pos += 1
                hi = int(self.text[start:self.pos]) if start != self.pos else None
            if self.peek() != '}':
                raise RegexError('unterminated repetition')
            self.pos += 1
            if hi is not None and hi < lo:
                raise RegexError('reversed repetition range')
            if lo > 1024 or (hi is not None and hi > 1024):
                raise RegexLimitError('individual repetition bound exceeds 1024')
            node = ('repeat', node, lo, hi)
        if self.peek() and self.peek() in '*+?{':
            raise RegexError('stacked/lazy/possessive quantifiers are unsupported')
        return node

    def atom(self):
        ch = self.peek()
        self.pos += 1
        if ch in ('0', '1', '2', '3'):
            return ('chars', (int(ch),))
        if ch == '.':
            return ('chars', (0, 1, 2, 3))
        if ch == '(':
            self.depth += 1
            if self.depth > 96:
                raise RegexLimitError('group nesting exceeds 96')
            node = self.union()
            if self.peek() != ')':
                raise RegexError('unclosed group')
            self.pos += 1
            self.depth -= 1
            return node
        if ch == '[':
            inverse = self.peek() == '^'
            if inverse:
                self.pos += 1
            chars = set()
            while self.peek() and self.peek() != ']':
                first = self.peek()
                self.pos += 1
                if first not in '0123':
                    raise RegexError('classes contain only symbols 0..3')
                if self.peek() == '-':
                    self.pos += 1
                    last = self.peek()
                    self.pos += 1
                    if last not in ('0', '1', '2', '3') or last < first:
                        raise RegexError('invalid class range')
                    chars.update(range(int(first), int(last) + 1))
                else:
                    chars.add(int(first))
            if self.peek() != ']' or not chars:
                raise RegexError('empty/unclosed character class')
            self.pos += 1
            return ('chars', tuple(sorted({0, 1, 2, 3} - chars if inverse else chars)))
        raise RegexError(f'unsupported symbol {ch!r} at offset {self.pos - 1}')


class _NFA:

    def __init__(self, limit):
        self.edges = []
        self.limit = limit

    def state(self):
        if len(self.edges) >= self.limit:
            raise RegexLimitError(f'epsilon-NFA exceeds {self.limit} states')
        self.edges.append([])
        return len(self.edges) - 1

    def edge(self, a, b, symbol=None):
        self.edges[a].append((symbol, b))

    def build(self, node):
        tag = node[0]
        start, end = (self.state(), self.state())
        if tag == 'chars':
            for c in node[1]:
                self.edge(start, end, c)
        elif tag == 'concat':
            cursor = start
            for child in node[1]:
                a, b = self.build(child)
                self.edge(cursor, a)
                cursor = b
            self.edge(cursor, end)
        elif tag == 'union':
            for child in node[1]:
                a, b = self.build(child)
                self.edge(start, a)
                self.edge(b, end)
        else:
            _, child, lo, hi = node
            cursor = start
            for _ in range(lo):
                a, b = self.build(child)
                self.edge(cursor, a)
                cursor = b
            if hi is None:
                self.edge(cursor, end)
                a, b = self.build(child)
                self.edge(cursor, a)
                self.edge(b, cursor)
            else:
                for _ in range(hi - lo):
                    self.edge(cursor, end)
                    a, b = self.build(child)
                    self.edge(cursor, a)
                    cursor = b
                self.edge(cursor, end)
        return (start, end)

    def closure(self, states):
        found = set(states)
        pending = list(found)
        while pending:
            for symbol, dst in self.edges[pending.pop()]:
                if symbol is None and dst not in found:
                    found.add(dst)
                    pending.append(dst)
        return frozenset(found)


@dataclass(frozen=True)
class RegexDFA:
    pattern: str
    transitions: tuple[tuple[int | None, ...], ...]
    accepting: frozenset[int]

    def step(self, level, state, symbol):
        return self.transitions[state][symbol]

    def final(self, state):
        return state in self.accepting

    def query(self, *, accept=None, possible=None):
        from .query import Query

        if accept is None:

            def accept(value):
                return value != 0

            if possible is None:

                def possible(lo, hi):
                    return lo != 0 or hi != 0

        return Query("regex " + self.pattern, 0, self.step, accept, possible, self.final)


def compile_regex(pattern: str, *, max_states: int = 4096, max_nfa_states: int = 16384) -> RegexDFA:
    for label, limit in (("max_states", max_states), ("max_nfa_states", max_nfa_states)):
        if type(limit) is not int or limit < 1:
            raise ValueError(label + " must be a positive integer")
    ast = _Parser(pattern).parse()
    nfa = _NFA(max_nfa_states)
    first, last = nfa.build(ast)
    initial = nfa.closure([first])
    states = {initial: 0}
    pending = deque([initial])
    transitions = []
    accepting = set()
    while pending:
        current = pending.popleft()
        row = []
        if last in current:
            accepting.add(states[current])
        moves = [set() for _ in range(4)]
        for state in current:
            for symbol, dst in nfa.edges[state]:
                if symbol is not None:
                    moves[symbol].add(dst)
        for move in moves:
            target = nfa.closure(move)
            if not target:
                row.append(None)
                continue
            if target not in states:
                if len(states) >= max_states:
                    raise RegexLimitError(f"DFA exceeds {max_states} states")
                states[target] = len(states)
                pending.append(target)
            row.append(states[target])
        transitions.append(tuple(row))
    return RegexDFA(pattern, tuple(transitions), frozenset(accepting))
