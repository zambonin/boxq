#pragma once
#include "graph_count.hpp"

namespace {
struct MatrixRun {
  Engine &e;
  const Query &q;
  const Filter &f;
  Stats st{};
  uint64_t limit;
  bool enumerate;
  MatrixRun(Engine &ee, const Query &qq, const Filter &ff, bool en,
            uint64_t lim)
      : e(ee), q(qq), f(ff), limit(lim), enumerate(en) {}
  void hit(uint64_t pos, int64_t value) {
    ++st.count;
    if (enumerate) {
      check(e.output.size() < limit, "enumeration output limit exceeded");
      e.output.push_back(
          {uint32_t(pos >> q.n), uint32_t(pos & ((1u << q.n) - 1)), value});
    }
  }
  void walk(uint32_t v, unsigned level, uint32_t a, uint32_t b) {
    if (!q.suffix[v])
      return;
    if (level == q.n) {
      uint64_t pos = (uint64_t(a) << q.n) | b;
      auto value = e.m->get(pos);
      ++st.checked;
      if (f.accept(value))
        hit(pos, value);
      return;
    }
    for (unsigned s = 0; s < 4; ++s) {
      auto nv = q.next[v].c[s];
      if (nv != REJECT)
        walk(nv, level + 1, (a << 1) | (s >> 1), (b << 1) | (s & 1));
    }
  }
  Stats run();
};
} // namespace
