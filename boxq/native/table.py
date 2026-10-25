"""Native table handles, compiled query automata and count/enumeration runs.

The ctypes declarations must match _native/native_query.cpp field by field.
No library is compiled until a table or a query is created.
"""
from __future__ import annotations

import ctypes as C
from pathlib import Path
import struct

from .tools import native_tools


class Stats(C.Structure):
    _fields_ = [(k, C.c_uint64) for k in (
        'count',
        'elapsed_ns',
        'memo_entries',
        'memo_hits',
        'checked',
        'pruned',
        'output_entries',
        'memo_peak_slots',
        'accepted_shortcuts',
    )] + [('plan', C.c_uint32), ('reserved', C.c_uint32)] + [(k, C.c_uint64) for k in ('cache_bytes', 'cache_replacements', 'dp_bytes', 'dp_nodes')]


class Hit(C.Structure):
    _fields_ = [('a', C.c_uint32), ('b', C.c_uint32), ('value', C.c_int64)]


_LIBS = {}
_REQUESTS = {}


def library(cache=None):
    import os
    request = (
        str(cache),
        os.environ.get('BOXQ_CACHE'),
        os.environ.get('CXX'),
    )
    if request in _REQUESTS:
        return _REQUESTS[request]
    path, metadata = native_tools(cache, shared=True)
    if str(path) not in _LIBS:
        lib = C.CDLL(str(path))
        lib.boxq_error.restype = C.c_char_p
        lib.boxq_open.argtypes = [C.c_char_p, C.c_int]
        lib.boxq_open.restype = C.c_void_p
        lib.boxq_close.argtypes = [C.c_void_p]
        lib.boxq_query.argtypes = [C.c_void_p, C.c_uint64]
        lib.boxq_query.restype = C.c_void_p
        lib.boxq_query_close.argtypes = [C.c_void_p]
        lib.boxq_info.argtypes = [C.c_void_p, C.POINTER(C.c_uint64)]
        lib.boxq_values.argtypes = [C.c_void_p, C.POINTER(C.c_int64)]
        lib.boxq_bounds.argtypes = [C.c_void_p, C.POINTER(C.c_uint64)]
        lib.boxq_eval.argtypes = [C.c_void_p, C.c_uint32, C.c_uint32, C.POINTER(C.c_int64)]
        lib.boxq_run_v2.argtypes = [
            C.c_void_p,
            C.c_void_p,
            C.POINTER(C.c_uint8),
            C.c_uint64,
            C.c_int,
            C.c_uint64,
            C.c_uint64,
            C.c_int,
            C.c_uint64,
            C.POINTER(Stats),
        ]
        lib.boxq_output_size.argtypes = [C.c_void_p]
        lib.boxq_output_size.restype = C.c_uint64
        lib.boxq_output.argtypes = [C.c_void_p]
        lib.boxq_output.restype = C.POINTER(Hit)
        _LIBS[str(path)] = lib
    _REQUESTS[request] = (_LIBS[str(path)], metadata)
    return _REQUESTS[request]


def checked(lib, value):
    if value < 0:
        raise RuntimeError(lib.boxq_error().decode())
    return value


def compile_layers(query, n, max_states=200000):
    """Unroll the word predicate, independently of table values, at exactly n symbols."""
    if type(n) is not int or not 1 <= n <= 20:
        raise ValueError('native query width must be 1..20')
    if not 1 <= max_states <= 1000000:
        raise ValueError('max query states must be 1..1000000')
    states = [query.q0]
    layers = [0, 1]
    trans = []
    for level in range(n):
        next_ids = {}
        start, end = layers[level:level + 2]
        for u in range(start, end):
            row = []
            for symbol in range(4):
                nxt = query.step(level, states[u], symbol)
                if nxt is None:
                    row.append(4294967295)
                    continue
                if nxt not in next_ids:
                    if len(states) >= max_states:
                        raise ValueError('compiled query exceeds native state limit')
                    next_ids[nxt] = len(states)
                    states.append(nxt)
                row.append(next_ids[nxt])
            trans.append(row)
        layers.append(len(states))
    final = bytearray(len(states))
    for u in range(layers[-2], layers[-1]):
        final[u] = bool(query.final(states[u]))
        trans.append([4294967295] * 4)
    flat = [v for row in trans for v in row]
    return struct.pack('<4sIII', b'QRY1', n, len(states), 0) + struct.pack('<' + 'I' * len(layers), *layers) + struct.pack('<' + 'I' * len(flat), *flat) + bytes(final)


class NativeQuery:

    def __init__(self, query, n, *, cache=None, max_states=200000):
        self.lib, self.compiler = library(cache)
        self.query = query
        self.n = n
        self.blob = compile_layers(query, n, max_states)
        self._handle = self.lib.boxq_query(self.blob, len(self.blob))
        if not self._handle:
            raise ValueError(self.lib.boxq_error().decode())

    def close(self):
        if getattr(self, '_handle', None):
            self.lib.boxq_query_close(self._handle)
            self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass


class NativeTable:
    VARIANTS = {'mapped': 0, 'int32': 1, 'indexed': 2, 'decoded-graph': 3}
    INFO = (
        'n',
        'value_codes',
        'states_or_cells',
        'mapped_file_bytes',
        'bounds_bytes',
        'decoded_array_bytes',
        'index_coordinates_capacity_bytes',
        'open_setup_ns',
        'is_graph',
        'process_peak_rss_bytes',
    )

    def __init__(self, path, *, variant='mapped', cache=None):
        if variant not in self.VARIANTS:
            raise ValueError('unknown native variant')
        self.path = Path(path).expanduser().resolve()
        self.variant = variant
        self.cache = cache
        self.lib, self.compiler = library(cache)
        self._handle = self.lib.boxq_open(str(self.path).encode(), self.VARIANTS[variant])
        if not self._handle:
            raise ValueError(self.lib.boxq_error().decode())
        info = self.info()
        self.n = info['n']
        self.is_graph = bool(info['is_graph'])
        values = (C.c_int64 * info['value_codes'])()
        checked(self.lib, self.lib.boxq_values(self._handle, values))
        self.values = tuple(values)

    def close(self):
        if getattr(self, '_handle', None):
            self.lib.boxq_close(self._handle)
            self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def _open(self):
        if not self._handle:
            raise ValueError('native table is closed')

    def info(self):
        self._open()
        out = (C.c_uint64 * 10)()
        checked(self.lib, self.lib.boxq_info(self._handle, out))
        return dict(zip(self.INFO, map(int, out)))

    def value_bounds(self):
        self._open()
        t = C.c_uint64()
        checked(self.lib, self.lib.boxq_bounds(self._handle, C.byref(t)))
        return {'preprocessing_ns': t.value, 'bytes': self.info()['bounds_bytes']}

    def evaluate(self, a, b):
        self._open()
        if (
            type(a) is not int
            or type(b) is not int
            or not 0 <= a < 1 << self.n
            or not 0 <= b < 1 << self.n
        ):
            raise IndexError('cell outside table')
        v = C.c_int64()
        checked(self.lib, self.lib.boxq_eval(self._handle, a, b, C.byref(v)))
        return v.value

    def run(
        self,
        query,
        *,
        mode='count',
        bounds=True,
        max_product_states=2000000,
        max_output=1000000,
        strategy='auto',
        memory_mib=768,
    ):
        self._open()
        if strategy not in {'auto', 'bounded', 'dense'}:
            raise ValueError('unknown count strategy')
        if type(memory_mib) is not int or not 1 <= memory_mib <= 65536:
            raise ValueError('memory_mib must be 1..65536')
        if mode not in {'count', 'enumerate'}:
            raise ValueError('mode must be count/enumerate')
        if not 1 <= max_product_states <= 100000000:
            raise ValueError('invalid product-state limit')
        if not 0 <= max_output <= 100000000:
            raise ValueError('invalid output cap')
        own = not isinstance(query, NativeQuery)
        compiled = NativeQuery(query, self.n, cache=self.cache) if own else query
        if compiled.lib is not self.lib:
            if own:
                compiled.close()
            raise ValueError('query and table use different compiled backends')
        if not compiled._handle:
            raise ValueError('native query is closed')
        prep = 0
        try:
            if bounds and self.is_graph and (not self.info()['bounds_bytes']):
                prep = self.value_bounds()['preprocessing_ns']
            elif not bounds and self.info()['bounds_bytes']:
                raise ValueError(
                    'bounds already initialized; open a fresh native handle for a no-bound comparison',
                )
            mask = (C.c_uint8 * len(self.values))(*(bool(compiled.query.accept(v)) for v in self.values))
            stats = Stats()
            checked(
                self.lib,
                self.lib.boxq_run_v2(
                    self._handle,
                    compiled._handle,
                    mask,
                    len(mask),
                    mode == 'enumerate',
                    max_product_states,
                    max_output,
                    {'auto': 0, 'bounded': 1, 'dense': 2}[strategy],
                    memory_mib << 20,
                    C.byref(stats),
                ),
            )
            r = {name: int(getattr(stats, name)) for name, _ in stats._fields_ if name != 'reserved'}
            r.update(
                {
                    'mode': mode,
                    'bound_preprocessing_ns': prep,
                    'native_elapsed_includes': 'per-query memo and output construction; excludes file load, DFA compilation, filter preparation, bounds and Python result conversion',
                    'plan_name': {
                        0: 'graph-product',
                        1: 'sequential-matrix',
                        2: 'value-index',
                        3: 'word-candidates',
                        4: 'direct-rows',
                        5: 'direct-diagonal',
                        6: 'layer-dense-count',
                        7: 'cross-table-product',
                        8: 'hybrid-cardinalities',
                        9: 'hybrid-row-ranks',
                    }[r['plan']],
                },
            )
            if mode == 'enumerate':
                size = self.lib.boxq_output_size(self._handle)
                ptr = self.lib.boxq_output(self._handle)
                r['entries'] = [(ptr[i].a, ptr[i].b, ptr[i].value) for i in range(size)]
            return r
        finally:
            if own:
                compiled.close()
