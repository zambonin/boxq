"""Independent NumPy definitions and tuple reduction from the review prototype.

This module deliberately does not call the production constructors or traversals.
"""

import numpy as np


def table(lookup, kind):
    values = np.asarray(lookup, dtype=np.int64)
    size = len(values)
    x = np.arange(size)
    if kind == "DDT":
        result = np.array([np.bincount(values ^ values[x ^ a], minlength=size) for a in x])
        result[0, 0] = 0
    elif kind == "LAT":
        parity = np.array([int(v).bit_count() & 1 for v in x])
        hadamard = (-1.0) ** parity[np.bitwise_and.outer(x, x)]
        output = (-1.0) ** parity[np.bitwise_and.outer(values, x)]
        result = np.rint((hadamard @ output) / 2).astype(np.int64)
        result[0, 0] = 0
    elif kind == "BCT":
        if len(set(lookup)) != size:
            raise ValueError("BCT requires a permutation")
        inverse = np.empty(size, dtype=np.int64)
        inverse[values] = x
        result = np.zeros((size, size), dtype=np.int64)
        for b in x:
            first = inverse[values ^ b]
            for a in x:
                result[a, b] = np.count_nonzero((first ^ inverse[values[x ^ a] ^ b]) == a)
        result[0, :] = result[:, 0] = 0
    else:
        raise ValueError("kind must be DDT, LAT or BCT")
    return result


def graph(matrix):
    values, inverse = np.unique(matrix, return_inverse=True)
    count = len(values)
    grid = inverse.reshape(matrix.shape)
    children = {}
    next_id = count
    while grid.shape[0] > 1:
        unique = {}
        output = np.empty((grid.shape[0] // 2, grid.shape[1] // 2), dtype=np.int64)
        for a in range(output.shape[0]):
            for b in range(output.shape[1]):
                key = tuple(int(v) for v in matrix_quad(grid, a, b))
                if len(set(key)) == 1 and key[0] < count:
                    node = key[0]
                else:
                    if key not in unique:
                        unique[key] = next_id
                        children[next_id] = key
                        next_id += 1
                    node = unique[key]
                output[a, b] = node
        grid = output
    return int(grid[0, 0]), children, [int(v) for v in values]


def matrix_quad(grid, a, b):
    return (
        grid[2 * a, 2 * b],
        grid[2 * a, 2 * b + 1],
        grid[2 * a + 1, 2 * b],
        grid[2 * a + 1, 2 * b + 1],
    )


def state_count(matrix):
    values, inverse = np.unique(matrix, return_inverse=True)
    d = len(values)
    grid = inverse.reshape(matrix.shape)
    count = d
    while grid.shape[0] > 1:
        keys = np.stack(
            (grid[::2, ::2], grid[::2, 1::2], grid[1::2, ::2], grid[1::2, 1::2]), axis=-1
        ).reshape(-1, 4)
        constant = (
            (keys[:, 0] == keys[:, 1])
            & (keys[:, 1] == keys[:, 2])
            & (keys[:, 2] == keys[:, 3])
            & (keys[:, 0] < d)
        )
        out = keys[:, 0].copy()
        if (~constant).any():
            unique, inv = np.unique(keys[~constant], axis=0, return_inverse=True)
            out[~constant] = count + inv
            count += len(unique)
        grid = out.reshape(grid.shape[0] // 2, grid.shape[1] // 2)
    return count


def count_query(matrix, query):
    """Count all non-pruned reachable products, including rejected final states."""
    root, children, values = graph(matrix)
    n = (len(matrix) - 1).bit_length()
    bounds = {}

    def bound(node):
        if node not in bounds:
            if node < len(values):
                bounds[node] = (values[node], values[node])
            else:
                parts = [bound(c) for c in children[node]]
                bounds[node] = (min(p[0] for p in parts), max(p[1] for p in parts))
        return bounds[node]

    bound(root)
    memo = {}
    expanded = set()

    def visit(node, state, depth):
        key = node, state, depth
        if key in memo:
            return memo[key]
        if query.possible is not None and not query.possible(*bounds[node]):
            result = 0
        else:
            expanded.add(key)
            if depth == n:
                result = int(query.final(state) and query.accept(values[node]))
            else:
                result = 0
                for symbol in range(4):
                    next_state = query.step(depth, state, symbol)
                    if next_state is not None:
                        child = node if node < len(values) else children[node][symbol]
                        result += visit(child, next_state, depth + 1)
        memo[key] = result
        return result

    return visit(root, query.q0, 0), len(expanded)


def payload_sizes(matrix, states):
    """Independent dictionary payload producer; dictionaries include signed values."""
    values = sorted(set(int(v) for v in matrix.flat))
    nonzero_values = [v for v in values if v]

    def value_width(alphabet):
        width = 1
        while any(not -(1 << (width - 1)) <= v < (1 << (width - 1)) for v in alphabet):
            width += 1
        return width

    graph = 4 * states * max(1, (states - 1).bit_length())
    graph += len(values) * value_width(values)
    dense = matrix.size * (len(values) - 1).bit_length()
    dense += len(values) * value_width(values)
    bitmap = matrix.size + len(nonzero_values) * value_width(nonzero_values)
    bitmap += int(np.count_nonzero(matrix)) * max(0, len(nonzero_values) - 1).bit_length()
    return {
        "graph_bytes": (graph + 7) // 8,
        "dense_bytes": (dense + 7) // 8,
        "bitmap_bytes": (bitmap + 7) // 8,
    }
