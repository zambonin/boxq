#pragma once
#include "matrix_run.hpp"

namespace {
inline Stats MatrixRun::run() {
  auto &m = *e.m;
  if (m.hybrid && !enumerate) {
    auto &h = *m.hybrid;
    if (q.universal[q.root]) {
      for (uint32_t i = 0; i < h.h.d; ++i)
        if (f.accept(h.values[i]))
          st.count += h.b[i].count;
      st.plan = 8;
      return st;
    }
    bool rows = true;
    uint32_t fixed = 0, free = 0;
    for (unsigned l = 0; l < q.n; ++l) {
      if (q.layer[l + 1] - q.layer[l] != 1) {
        rows = false;
        break;
      }
      uint32_t u = q.layer[l], mask = 0;
      for (unsigned t = 0; t < 4; ++t)
        if (q.next[u].c[t] != REJECT && q.suffix[q.next[u].c[t]])
          mask |= 1u << t;
      rows = rows && (mask == 3 || mask == 12 || mask == 15);
      if (mask == 12)
        fixed |= 1u << (q.n - 1 - l);
      if (mask == 15)
        free |= 1u << (q.n - 1 - l);
    }
    if (rows) {
      st.plan = 9;
      unsigned tail = 0;
      while (tail < q.n && (free & (1u << tail)))
        ++tail;
      uint32_t span = 1u << tail, outer = free & ~(span - 1), sub = 0;
      do {
        uint64_t lo = uint64_t(fixed | sub) << q.n,
                 hi = uint64_t((fixed | sub) + span) << q.n;
        for (uint32_t i = 0; i < h.h.d; ++i)
          if (f.accept(h.values[i]))
            st.count += h.range_count(i, lo, hi);
        ++st.checked;
        if (sub == outer)
          break;
        sub = (sub - outer) & outer;
      } while (true);
      return st;
    }
  }
  uint64_t indexed = 0;
  for (auto &kv : m.index)
    if (f.accept(kv.first))
      indexed += kv.second.size();
  if (!m.index.empty() &&
      (q.universal[q.root] || indexed <= q.suffix[q.root])) {
    st.plan = 2;
    if (q.universal[q.root] && !enumerate) {
      st.count = indexed;
      return st;
    }
    for (auto &kv : m.index)
      if (f.accept(kv.first))
        for (auto pos : kv.second) {
          ++st.checked;
          if (q.universal[q.root] ||
              q.accepts(pos >> q.n, pos & ((1u << q.n) - 1)))
            hit(pos, kv.first);
        }
  } else if (q.universal[q.root]) {
    st.plan = 1;
    if (!enumerate && f.all) {
      st.count = m.cells;
      return st;
    }
    if (!enumerate && !m.dense.empty() && f.one) {
      for (auto v : m.dense)
        st.count += (v == f.equality);
    } else if (!enumerate && !m.dense.empty() && f.nonzero) {
      for (auto v : m.dense)
        st.count += (v != 0);
    } else
      for (uint64_t pos = 0; pos < m.cells; ++pos) {
        auto v = m.get(pos);
        if (f.accept(v))
          hit(pos, v);
      }
    st.checked = m.cells;
  }

  else {
    st.plan = 3;
    // Recognize exact independent-bit rows and diagonals from the DFA itself.
    bool rows = true, diag = true;
    uint32_t fixed = 0, free = 0;
    for (unsigned l = 0; l < q.n; ++l) {
      if (q.layer[l + 1] - q.layer[l] != 1) {
        rows = diag = false;
        break;
      }
      uint32_t u = q.layer[l], mask = 0;
      for (unsigned t = 0; t < 4; ++t)
        if (q.next[u].c[t] != REJECT && q.suffix[q.next[u].c[t]])
          mask |= 1u << t;
      diag = diag && mask == 9;
      rows = rows && (mask == 3 || mask == 12 || mask == 15);
      if (mask == 12)
        fixed |= 1u << (q.n - 1 - l);
      if (mask == 15)
        free |= 1u << (q.n - 1 - l);
    }
    if (rows) {
      st.plan = 4;
      uint32_t sub = 0;
      do {
        uint64_t start = uint64_t(fixed | sub) << q.n;
        for (uint32_t b = 0; b < (1u << q.n); ++b) {
          auto v = m.get(start + b);
          ++st.checked;
          if (f.accept(v))
            hit(start + b, v);
        }
        if (sub == free)
          break;
        sub = (sub - free) & free;
      } while (true);
    } else if (diag) {
      st.plan = 5;
      for (uint32_t a = 0; a < (1u << q.n); ++a) {
        uint64_t pos = (uint64_t(a) << q.n) | a;
        auto v = m.get(pos);
        ++st.checked;
        if (f.accept(v))
          hit(pos, v);
      }
    } else
      walk(q.root, 0, 0, 0);
  }
  st.output_entries = e.output.size();
  return st;
}
} // namespace
