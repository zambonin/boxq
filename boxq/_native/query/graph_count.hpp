#pragma once
#include "graph_run.hpp"

namespace {
inline uint64_t GraphRun::banked_count(uint64_t memory_bytes) {
  // Same-level canonical IDs form contiguous banks in QNF and in its packed
  // conversion. Only adjacent levels are live. Each bank uses the smallest
  // native integer field holding the query's accepted suffix count.
  std::vector<uint8_t> previous;
  uint64_t prev_start = 0, peak = 0;
  unsigned pw = 1;
  for (int level = int(q.n) - 1; level >= 0; --level) {
    auto start = e.banks[level + 1], end = e.banks[level];
    auto v = q.layer[level];
    unsigned w = width(q.suffix[v]);
    uint64_t bytes = (end - start) * w;
    check(bytes <= memory_bytes && previous.size() <= memory_bytes - bytes,
          "layer count workspace exceeds --memory-mib");
    peak = std::max(peak, bytes + previous.size());
    std::vector<uint8_t> current(bytes);
    for (uint64_t u = start; u < end; ++u) {
      uint64_t sum = 0;
      for (unsigned s = 0; s < 4; ++s) {
        auto nv = q.next[v].c[s];
        if (nv == REJECT || !q.suffix[nv])
          continue;
        auto c = e.child(uint32_t(u), s);
        if (e.g->term(c)) {
          if (f.accept(e.g->val(c)))
            sum += q.suffix[nv];
        } else {
          check(c >= prev_start &&
                    (uint64_t(c) - prev_start) * pw + pw <= previous.size(),
                "child outside adjacent count bank");
          uint64_t x = 0;
          memcpy(&x, previous.data() + (c - prev_start) * pw, pw);
          sum += x;
        }
      }
      memcpy(current.data() + (u - start) * w, &sum, w);
    }
    previous = std::move(current);
    prev_start = start;
    pw = w;
  }
  uint64_t result = 0;
  memcpy(&result, previous.data() + (e.g->root - prev_start) * pw, pw);
  st.plan = 6;
  st.dp_bytes = peak;
  st.dp_nodes = e.g->fixed ? e.g->S : e.g->S - e.g->d;
  st.checked = st.dp_nodes;
  return result;
}

inline uint64_t GraphRun::dense_count(uint64_t memory_bytes) {
  check(single_layer(), "dense count needs one DFA state per layer");
  auto &g = *e.g;
  if (g.term(g.root))
    return f.accept(g.val(g.root)) ? q.suffix[q.root] : 0;
  if (f.all)
    return q.suffix[q.root];
  if (!e.banks.empty())
    return banked_count(memory_bytes);
  uint64_t needed = g.S * 4 + (g.fixed ? 0 : g.S);
  check(needed <= memory_bytes,
        "dense count workspace exceeds --memory-mib; increase deliberately "
        "or use bounded strategy");
  std::vector<uint32_t> counts(g.S);
  std::map<uint32_t, uint64_t> wide;
  std::vector<uint8_t> depths;
  if (!g.fixed) {
    depths.assign(g.S, 255);
    depths[g.root] = 0;
    for (uint64_t i = g.S; i; --i) {
      uint32_t u = i - 1;
      if (g.term(u))
        continue;
      check(depths[u] != 255, "unreachable graph state");
      for (unsigned s = 0; s < 4; ++s) {
        auto v = e.child(u, s);
        if (!g.term(v)) {
          check(depths[v] == 255 || depths[v] == depths[u] + 1,
                "inconsistent depth");
          depths[v] = depths[u] + 1;
        }
      }
    }
  }
  unsigned level = q.n - 1;
  for (uint64_t i = 0; i < g.S; ++i) {
    uint32_t u = uint32_t(i);
    if (g.term(u))
      continue;
    if (g.fixed) {
      while (level && i >= g.boundaries[level])
        --level;
    } else
      level = depths[u];
    uint32_t v = q.layer[level];
    uint64_t sum = 0;
    for (unsigned s = 0; s < 4; ++s) {
      auto nv = q.next[v].c[s];
      if (nv == REJECT || !q.suffix[nv])
        continue;
      auto c = e.child(u, s);
      if (g.term(c)) {
        if (f.accept(g.val(c)))
          sum += q.suffix[nv];
      } else {
        auto w = wide.find(c);
        sum += w == wide.end() ? counts[c] : w->second;
      }
    }
    if (sum > UINT32_MAX)
      wide[u] = sum;
    else
      counts[u] = uint32_t(sum);
  }
  st.plan = 6;
  st.dp_bytes = needed;
  st.dp_nodes = g.S;
  st.checked = g.S;
  auto w = wide.find(g.root);
  return w == wide.end() ? counts[g.root] : w->second;
}
} // namespace
