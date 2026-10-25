#pragma once
#include "../query/cursor.hpp"
#include <functional>

namespace {
uint64_t player(uint64_t x) {
  uint64_t y = 0;
  while (x) {
    unsigned i = __builtin_ctzll(x);
    x &= x - 1;
    y |= 1ULL << (i == 63 ? 63 : 16 * i % 63);
  }
  return y;
}
uint64_t inverse_player(uint64_t x) {
  uint64_t y = 0;
  while (x) {
    unsigned i = __builtin_ctzll(x);
    x &= x - 1;
    y |= 1ULL << (i == 63 ? 63 : 4 * i % 63);
  }
  return y;
}
unsigned wt(int64_t v) {
  check(v > 0 && !(v & (v - 1)), "non-power-two PRESENT multiplicity");
  return 4 - __builtin_ctzll(uint64_t(v));
}
Query row_query(unsigned a) {
  std::vector<uint8_t> b(16 + 4 * 6 + 17 * 5);
  memcpy(b.data(), "QRY1", 4);
  uint32_t n = 4, total = 5, root = 0;
  memcpy(b.data() + 4, &n, 4);
  memcpy(b.data() + 8, &total, 4);
  memcpy(b.data() + 12, &root, 4);
  for (uint32_t i = 0; i < 6; ++i)
    memcpy(b.data() + 16 + 4 * i, &i, 4);
  for (unsigned i = 0; i < 5; ++i)
    for (unsigned s = 0; s < 4; ++s) {
      uint32_t q = i < 4 && (s >> 1) == ((a >> (3 - i)) & 1) ? i + 1 : REJECT;
      memcpy(b.data() + 40 + 16 * i + 4 * s, &q, 4);
    }
  b.back() = 1;
  return Query(b.data(), b.size());
}
struct PresentProvider {
  Engine &e;
  std::array<std::vector<std::pair<unsigned, unsigned>>, 16> cache;
  std::array<bool, 16> ready{};
  uint64_t row_queries = 0, cache_hits = 0, point_queries = 0;
  explicit PresentProvider(Engine &x) : e(x) {}
  int64_t point(unsigned a, unsigned b) {
    ++point_queries;
    if (!a)
      return b ? 0 : 16;
    return e.g ? e.g->evaluate(a, b) : e.m->get(16 * a + b);
  }
  const std::vector<std::pair<unsigned, unsigned>> &row(unsigned a) {
    if (ready[a]) {
      ++cache_hits;
      return cache[a];
    }
    ready[a] = true;
    ++row_queries;
    auto &v = cache[a];
    if (!a) {
      v.push_back({0, 0});
      return v;
    }
    if (e.g) {
      auto q = row_query(a);
      std::vector<uint8_t> allowed;
      for (auto z : e.values())
        allowed.push_back(z != 0);
      Cursor c(e, nullptr, q, allowed.data(), allowed.size(), 0);
      PairHit hit[16];
      auto k = c.next(hit, 16);
      for (uint64_t i = 0; i < k; ++i)
        v.push_back({hit[i].b, wt(hit[i].left)});
    } else
      for (unsigned b = 0; b < 16; ++b) {
        auto x = point(a, b);
        if (x)
          v.push_back({b, wt(x)});
      }
    std::sort(v.begin(), v.end());
    return v;
  }
};
struct EndpointSolver {
  PresentProvider provider;
  uint64_t target, pretarget, limit, visits = 0, ways = 0;
  unsigned best = UINT32_MAX;
  std::array<uint64_t, 3> witness{};
  EndpointSolver(Engine &e, uint64_t y, uint64_t cap)
      : provider(e), target(y), pretarget(inverse_player(y)), limit(cap) {}
  void visit(uint64_t input, unsigned round, unsigned cost, uint64_t first) {
    unsigned active = 0;
    for (unsigned i = 0; i < 16; ++i)
      active += ((input >> (4 * i)) & 15) != 0;
    if (cost + 2 * active > best)
      return;
    std::function<void(unsigned, uint64_t, unsigned)> rec =
        [&](unsigned nibble, uint64_t output, unsigned w) {
          if (w > best)
            return;
          if (nibble == 16) {
            check(++visits <= limit,
                  "PRESENT search state budget exceeded; no optimality claim");
            uint64_t next = player(output);
            if (round == 0) {
              visit(next, 1, w, next);
              return;
            }
            unsigned finalweight = w;
            for (unsigned j = 0; j < 16; ++j) {
              auto c = provider.point((next >> (4 * j)) & 15,
                                      (pretarget >> (4 * j)) & 15);
              if (!c)
                return;
              finalweight += wt(c);
              if (finalweight > best)
                return;
            }
            std::array<uint64_t, 3> path{first, next, target};
            if (finalweight < best) {
              best = finalweight;
              ways = 1;
              witness = path;
            } else if (finalweight == best) {
              ++ways;
              if (path < witness)
                witness = path;
            }
            return;
          }
          auto a = (input >> (4 * nibble)) & 15;
          if (!a) {
            rec(nibble + 1, output, w);
            return;
          }
          for (auto bw : provider.row(a))
            rec(nibble + 1, output | (uint64_t(bw.first) << (4 * nibble)),
                w + bw.second);
        };
    rec(0, 0, cost);
  }
};
} // namespace
