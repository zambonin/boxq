#pragma once
#include "filter.hpp"

namespace {
// Bounded direct-mapped cache: collisions evict only cached results, never
// prune a search branch. Exactness is independent of cache size.
struct BoundedMemo {
  struct Cell {
    uint64_t key = UINT64_MAX, value = 0;
  };
  std::vector<Cell> cells;
  uint64_t limit, used = 0, replacements = 0, peak_slots = 0;
  explicit BoundedMemo(uint64_t l) : limit(1) {
    while (limit <= l / 2)
      limit *= 2;
  }
  bool get(uint64_t key, uint64_t &v) const {
    if (cells.empty())
      return false;
    auto &c = cells[mix(key) & (cells.size() - 1)];
    if (c.key != key)
      return false;
    v = c.value;
    return true;
  }
  void grow(uint64_t cap) {
    auto old = std::move(cells);
    cells.resize(cap);
    peak_slots = std::max(peak_slots, old.size() + cap);
    used = 0;
    for (auto c : old)
      if (c.key != UINT64_MAX) {
        auto &slot = cells[mix(c.key) & (cap - 1)];
        if (slot.key == UINT64_MAX)
          ++used;
        slot = c;
      }
  }
  void put(uint64_t key, uint64_t v) {
    if (cells.empty())
      grow(std::min<uint64_t>(limit, 64));
    else if (used * 4 >= cells.size() * 3 && cells.size() < limit)
      grow(cells.size() * 2);
    auto &c = cells[mix(key) & (cells.size() - 1)];
    if (c.key == UINT64_MAX)
      ++used;
    else if (c.key != key)
      ++replacements;
    c = {key, v};
  }
};
struct GraphRun {
  Engine &e;
  const Query &q;
  const Filter &f;
  Stats st{};
  uint64_t memo_limit, output_limit;
  BoundedMemo memo;
  GraphRun(Engine &ee, const Query &qq, const Filter &ff, uint64_t ml,
           uint64_t ol)
      : e(ee), q(qq), f(ff), memo_limit(ml), output_limit(ol), memo(ml) {}
  uint64_t count(uint32_t u, uint32_t v) {
    ++st.checked;
    if (!q.suffix[v])
      return 0;
    if (e.g->term(u))
      return f.accept(e.g->val(u)) ? q.suffix[v] : 0;
    if (f.all) {
      ++st.accepted_shortcuts;
      return q.suffix[v];
    }
    if (!e.bounds.empty()) {
      auto lo = e.brank(u, 0), hi = e.brank(u, 1);
      if (!f.possible(lo, hi)) {
        ++st.pruned;
        return 0;
      }
      if (f.certain(lo, hi)) {
        ++st.accepted_shortcuts;
        return q.suffix[v];
      }
    }
    uint64_t key = (uint64_t(u) << 32) | v, answer;
    if (memo.get(key, answer)) {
      ++st.memo_hits;
      return answer;
    }
    uint64_t total = 0;
    for (unsigned s = 0; s < 4; ++s) {
      auto nv = q.next[v].c[s];
      if (nv != REJECT)
        total += count(e.child(u, s), nv);
    }
    memo.put(key, total);
    return total;
  }
  bool single_layer() const {
    for (unsigned l = 0; l <= q.n; ++l)
      if (q.layer[l + 1] - q.layer[l] != 1)
        return false;
    return true;
  }
  // A position-only word mask has exactly one live DFA state per layer. A
  // bottom-up dynamic program therefore needs no hashed graph/query product.
  // Counts below the top 16 remaining symbols fit uint32; only a small top
  // fringe uses uint64. Both the graph and its levels retain the v0.6
  // semantics.
  static unsigned width(uint64_t bound) {
    return bound <= UINT8_MAX    ? 1
           : bound <= UINT16_MAX ? 2
           : bound <= UINT32_MAX ? 4
                                 : 8;
  }
  uint64_t banked_count(uint64_t memory_bytes);
  uint64_t dense_count(uint64_t memory_bytes);
  void emit(uint32_t u, uint32_t v, unsigned level, uint32_t a, uint32_t b) {
    if (e.output.size() >= output_limit)
      return;
    if (level == q.n) {
      e.output.push_back({a, b, e.g->val(u)});
      return;
    }
    for (unsigned s = 0; s < 4; ++s) {
      auto nv = q.next[v].c[s];
      if (nv != REJECT && count(e.child(u, s), nv))
        emit(e.child(u, s), nv, level + 1, (a << 1) | (s >> 1),
             (b << 1) | (s & 1));
    }
  }
  Stats run(bool enumerate, int strategy = 0,
            uint64_t memory_bytes = 512ULL << 20) {
    if (strategy == 2 && !enumerate)
      check(single_layer(),
            "dense strategy needs one live DFA state per level");
    bool dense = !enumerate && single_layer() &&
                 (strategy == 2 ||
                  (strategy == 0 && (f.nonzero || f.all) &&
                   q.suffix[q.root] >= (1ULL << 20) && e.g->states() > 100000));
    st.count = dense ? dense_count(memory_bytes) : count(e.g->root, q.root);
    if (enumerate) {
      check(st.count <= output_limit,
            "enumeration output limit exceeded; count first or use streaming");
      e.output.reserve(st.count);
      if (st.count)
        emit(e.g->root, q.root, 0, 0, 0);
    }
    st.memo_entries = memo.used;
    st.memo_peak_slots = memo.peak_slots;
    st.cache_bytes = 16 * memo.cells.size();
    st.cache_replacements = memo.replacements;
    st.output_entries = e.output.size();
    return st;
  }
};
} // namespace
