#pragma once
#include "matrix_execute.hpp"

namespace {
struct PairHit {
  uint32_t a, b;
  int64_t left, right;
};
static_assert(sizeof(PairHit) == 24);
bool relation(int op, int64_t l, int64_t r) {
  switch (op) {
  case 0:
    return l != 0 && r == 0;
  case 1:
    return l == 0 && r != 0;
  case 2:
    return l != 0 && r != 0;
  case 3:
    return l != 0 || r != 0;
  case 4:
    return (l != 0) != (r != 0);
  case 5:
    return l == r;
  case 6:
    return l != r;
  default:
    throw std::runtime_error("unknown cross-table operation");
  }
}
struct PairLogic {
  Engine &l;
  Engine &r;
  int op;
  PairLogic(Engine &a, Engine &b, int o) : l(a), r(b), op(o) {
    check(o >= 0 && o <= 6, "invalid cross-table operation");
    check(l.n() == r.n(), "table widths differ");
  }
  std::pair<int64_t, int64_t> range(Engine &e, uint32_t u) {
    if (!e.g)
      return {INT64_MIN, INT64_MAX};
    if (e.g->term(u)) {
      auto v = e.g->val(u);
      return {v, v};
    }
    if (e.bounds.empty())
      return {e.values().front(), e.values().back()};
    return {e.values()[e.brank(u, 0)], e.values()[e.brank(u, 1)]};
  }
  bool possible(uint32_t a, uint32_t b) {
    auto x = range(l, a), y = range(r, b);
    if (&l == &r && a == b && (op == 0 || op == 1 || op == 4 || op == 6))
      return false;
    if (x.first == x.second && y.first == y.second)
      return relation(op, x.first, y.first);
    bool lp = x.first != 0 || x.second != 0, rp = y.first != 0 || y.second != 0;
    bool lc = x.first > 0 || x.second < 0, rc = y.first > 0 || y.second < 0;
    switch (op) {
    case 0:
      return lp && !rc;
    case 1:
      return rp && !lc;
    case 2:
      return lp && rp;
    case 3:
      return lp || rp;
    case 4:
      return (lp && !rc) || (rp && !lc);
    case 5:
      return x.first <= y.second && y.first <= x.second;
    case 6:
      return true;
    }
    return false;
  }
};
struct PairMemo {
  struct Cell {
    uint64_t pair = UINT64_MAX, result = 0;
    uint32_t q = REJECT, pad = 0;
  };
  std::vector<Cell> v;
  uint64_t limit, used = 0, replaced = 0, peak_slots = 0;
  explicit PairMemo(uint64_t l) : limit(1) {
    while (limit <= l / 2)
      limit *= 2;
  }
  uint64_t slot(uint64_t k, uint32_t q) const {
    return mix(k ^ mix(q)) & (v.size() - 1);
  }
  bool get(uint64_t k, uint32_t q, uint64_t &answer) {
    if (v.empty())
      return false;
    auto &c = v[slot(k, q)];
    if (c.pair != k || c.q != q)
      return false;
    answer = c.result;
    return true;
  }
  void grow(uint64_t cap) {
    auto old = std::move(v);
    v.resize(cap);
    peak_slots = std::max(peak_slots, old.size() + cap);
    used = 0;
    for (auto c : old)
      if (c.pair != UINT64_MAX) {
        auto &to = v[slot(c.pair, c.q)];
        if (to.pair == UINT64_MAX)
          ++used;
        to = c;
      }
  }
  void put(uint64_t k, uint32_t q, uint64_t a) {
    if (v.empty())
      grow(std::min<uint64_t>(limit, 64));
    else if (used * 4 >= v.size() * 3 && v.size() < limit)
      grow(v.size() * 2);
    auto &c = v[slot(k, q)];
    if (c.pair == UINT64_MAX)
      ++used;
    else if (c.pair != k || c.q != q)
      ++replaced;
    c = {k, a, q, 0};
  }
};
} // namespace
