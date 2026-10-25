#pragma once
#include "pair_run.hpp"

namespace {
struct Cursor {
  struct Frame {
    uint32_t left, right, q, depth, a, b, edge;
  };
  Engine &l;
  Engine *r;
  const Query &q;
  std::unique_ptr<Filter> filter;
  std::unique_ptr<PairLogic> pair;
  std::vector<Frame> stack;
  uint64_t visited = 0, yielded = 0;
  bool done = false;
  Cursor(Engine &ee, Engine *rr, const Query &qq, const uint8_t *allowed,
         uint64_t d, int op)
      : l(ee), r(rr), q(qq) {
    check(l.n() == q.n, "query width mismatch");
    if (r)
      pair = std::make_unique<PairLogic>(l, *r, op);
    else
      filter = std::make_unique<Filter>(l.values(), allowed, d);
    stack.reserve(q.n + 1);
    stack.push_back(
        {l.g ? l.g->root : 0, r && r->g ? r->g->root : 0, q.root, 0, 0, 0, 0});
  }
  bool possible(Frame &f) {
    if (!q.suffix[f.q])
      return false;
    if (pair)
      return pair->possible(f.left, f.right);
    if (!l.g)
      return true;
    if (l.g->term(f.left))
      return filter->accept(l.g->val(f.left));
    return l.bounds.empty() ||
           filter->possible(l.brank(f.left, 0), l.brank(f.left, 1));
  }
  uint64_t next(PairHit *out, uint64_t capacity, uint64_t work = UINT64_MAX) {
    uint64_t n = 0, start = visited;
    while (!stack.empty() && n < capacity && visited - start < work) {
      auto &f = stack.back();
      if (!f.edge) {
        ++visited;
        if (!possible(f)) {
          stack.pop_back();
          continue;
        }
      }
      if (f.depth == q.n) {
        int64_t lv = l.g ? l.g->val(f.left)
                         : l.m->get((uint64_t(f.a) << q.n) | f.b),
                rv = r ? (r->g ? r->g->val(f.right)
                               : r->m->get((uint64_t(f.a) << q.n) | f.b))
                       : 0;
        if (q.final[f.q] &&
            (pair ? relation(pair->op, lv, rv) : filter->accept(lv))) {
          out[n++] = {f.a, f.b, lv, rv};
          ++yielded;
        }
        stack.pop_back();
        continue;
      }
      if (f.edge == 4) {
        stack.pop_back();
        continue;
      }
      unsigned s = f.edge++;
      auto nq = q.next[f.q].c[s];
      if (nq == REJECT)
        continue;
      Frame child{l.g ? l.child(f.left, s) : 0,
                  r && r->g ? r->child(f.right, s) : 0,
                  nq,
                  f.depth + 1,
                  (f.a << 1) | (s >> 1),
                  (f.b << 1) | (s & 1),
                  0};
      stack.push_back(child);
    }
    done = stack.empty();
    return n;
  }
};

} // namespace
