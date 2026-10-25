#pragma once
#include "pair_logic.hpp"

namespace {
struct PairRun {
  PairLogic logic;
  const Query &q;
  Stats st{};
  PairMemo memo;
  PairRun(Engine &l, Engine &r, const Query &qq, int op, uint64_t cap)
      : logic(l, r, op), q(qq), memo(cap) {
    check(q.n == l.n(), "query width mismatch");
  }
  uint64_t count(uint32_t a, uint32_t b, uint32_t v) {
    ++st.checked;
    if (!q.suffix[v] || !logic.possible(a, b)) {
      ++st.pruned;
      return 0;
    }
    auto &l = logic.l;
    auto &r = logic.r;
    if (l.g->term(a) && r.g->term(b))
      return relation(logic.op, l.g->val(a), r.g->val(b)) ? q.suffix[v] : 0;
    if (&l == &r && a == b && logic.op == 5) {
      ++st.accepted_shortcuts;
      return q.suffix[v];
    }
    uint64_t k = (uint64_t(a) << 32) | b, z;
    if (memo.get(k, v, z)) {
      ++st.memo_hits;
      return z;
    }
    z = 0;
    for (unsigned s = 0; s < 4; ++s) {
      auto nv = q.next[v].c[s];
      if (nv != REJECT)
        z += count(l.child(a, s), r.child(b, s), nv);
    }
    memo.put(k, v, z);
    return z;
  }
  uint64_t scan(uint32_t left, uint32_t right, uint32_t v, unsigned level,
                uint32_t a, uint32_t b) {
    ++st.checked;
    if (!q.suffix[v] || !logic.possible(left, right))
      return 0;
    auto &l = logic.l;
    auto &r = logic.r;
    if (level == q.n) {
      auto x = l.g ? l.g->val(left) : l.m->get((uint64_t(a) << q.n) | b);
      auto y = r.g ? r.g->val(right) : r.m->get((uint64_t(a) << q.n) | b);
      return relation(logic.op, x, y);
    }
    uint64_t sum = 0;
    for (unsigned s = 0; s < 4; ++s) {
      auto nv = q.next[v].c[s];
      if (nv != REJECT)
        sum += scan(l.g ? l.child(left, s) : 0, r.g ? r.child(right, s) : 0, nv,
                    level + 1, (a << 1) | (s >> 1), (b << 1) | (s & 1));
    }
    return sum;
  }
  Stats run() {
    auto start = Clock::now();
    bool graphs = logic.l.g && logic.r.g;
    st.count = graphs ? count(logic.l.g->root, logic.r.g->root, q.root)
                      : scan(logic.l.g ? logic.l.g->root : 0,
                             logic.r.g ? logic.r.g->root : 0, q.root, 0, 0, 0);
    st.memo_entries = memo.used;
    st.memo_peak_slots = memo.peak_slots;
    st.cache_bytes = sizeof(PairMemo::Cell) * memo.v.size();
    st.cache_replacements = memo.replaced;
    st.elapsed_ns = ns(start);
    st.plan = graphs ? 7 : 10;
    return st;
  }
};
} // namespace
