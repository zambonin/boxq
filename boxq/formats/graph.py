"""Packed reduced quaternary automata."""
from __future__ import annotations

from ._bits import BitWriter, HEADER, _cell, _check_payload, _header, bits_for_codes, read_bits, read_signed, signed_width


class PackedAutomaton:
    """Immutable packed successor array; no resident unpacked graph is retained."""

    def __init__(self, blob):
        if not isinstance(blob, bytes):
            blob = bytes(blob)
        n, iw, vw, S, d, root, reserved, payload = _header(blob, b'QDD1')
        if not 1 <= d <= S or root >= S or reserved or (iw != max(1, bits_for_codes(S))):
            raise ValueError('invalid graph header')
        _check_payload(payload, 4 * S * iw + d * vw)
        self.n, self.iw, self.vw, self.S, self.d, self.root = (n, iw, vw, S, d, root)
        self.data = payload
        self._validate()

    @classmethod
    def from_automaton(cls, aut):
        terminals = sorted(aut.terminals(), key=aut.value)
        mapping = {node: i for i, node in enumerate(terminals)}
        ordered = list(terminals)
        for level in range(aut.n - 1, -1, -1):
            nodes = [u for u in aut.nodes() if not aut.is_terminal(u) and aut.level(u) == level]
            nodes.sort(key=lambda u: tuple((mapping[aut.child(u, s)] for s in range(4))))
            for node in nodes:
                mapping[node] = len(ordered)
                ordered.append(node)
        S, d = (len(ordered), len(terminals))
        iw = max(1, bits_for_codes(S))
        vw = signed_width([aut.value(u) for u in terminals])
        w = BitWriter()
        for u in ordered:
            for s in range(4):
                w.put(mapping[u] if aut.is_terminal(u) else mapping[aut.child(u, s)], iw)
        for u in terminals:
            w.signed(aut.value(u), vw)
        header = HEADER.pack(b'QDD1', aut.n, iw, vw, 0, S, d, mapping[aut.root], 0)
        return cls(header + bytes(w.data))

    def to_bytes(self):
        return HEADER.pack(b'QDD1', self.n, self.iw, self.vw, 0, self.S, self.d, self.root, 0) + self.data

    def _validate(self):
        """Require sorted absorbing terminals, reduced acyclic order and one depth per state."""
        vals = [self.value(u) for u in range(self.d)]
        if vals != sorted(set(vals)):
            raise ValueError('terminal values are not sorted and unique')
        for u in range(self.S):
            children = [self.child(u, s) for s in range(4)]
            if u < self.d:
                if children != [u] * 4:
                    raise ValueError('terminal is not absorbing')
            elif any((c >= u for c in children)):
                raise ValueError('graph is not in acyclic canonical order')
            elif len(set(children)) == 1 and children[0] < self.d:
                raise ValueError('unreduced constant node')
        depths = {}
        stack = [(self.root, 0)]
        seen = set()
        while stack:
            u, level = stack.pop()
            seen.add(u)
            if self.is_terminal(u):
                continue
            if level >= self.n:
                raise ValueError('internal state beyond word length')
            if u in depths:
                if depths[u] != level:
                    raise ValueError('internal state shared across depths')
                continue
            depths[u] = level
            stack.extend(((self.child(u, s), level + 1) for s in range(4)))
        if len(seen) != self.S:
            raise ValueError('unreachable states in serialized graph')

    def is_terminal(self, node):
        return node < self.d

    def child(self, node, sigma):
        if not 0 <= node < self.S or not 0 <= sigma < 4:
            raise IndexError('state or symbol')
        return read_bits(self.data, (4 * node + sigma) * self.iw, self.iw)

    def value(self, node):
        if not 0 <= node < self.d:
            raise ValueError('not a terminal')
        return read_signed(self.data, 4 * self.S * self.iw + node * self.vw, self.vw)

    def evaluate(self, a, b):
        _cell(self.n, a, b)
        u = self.root
        for bit in range(self.n - 1, -1, -1):
            if self.is_terminal(u):
                break
            u = self.child(u, 2 * (a >> bit & 1) + (b >> bit & 1))
        return self.value(u)
