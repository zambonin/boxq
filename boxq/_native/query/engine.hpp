#pragma once
#include "matrix_read.hpp"

namespace {
struct Hit {
  uint32_t a, b;
  int64_t value;
};
static_assert(sizeof(Hit) == 16);
struct Stats {
  uint64_t count, elapsed_ns, memo_entries, memo_hits, checked, pruned,
      output_entries, memo_peak_slots, accepted_shortcuts;
  uint32_t plan, reserved;
  uint64_t cache_bytes, cache_replacements, dp_bytes, dp_nodes;
};
struct Engine {
  std::unique_ptr<Graph> g;
  std::unique_ptr<Matrix> m;
  std::vector<uint64_t> banks;
  std::vector<uint8_t> bounds;
  unsigned rank_bytes = 0;
  std::vector<Quad> decoded;
  std::vector<Hit> output;
  uint64_t setup_ns = 0;
  Engine(const std::string &path, int variant) {
    auto t = Clock::now();
    std::ifstream f(path, std::ios::binary);
    char magic[4];
    read_exact(f, magic, 4);
    if (!memcmp(magic, "QDD1", 4) || !memcmp(magic, "QNF1", 4)) {
      check(variant == 0 || variant == 3,
            "graph variant must be mapped or decoded");
      g = std::make_unique<Graph>(path);
      if (!g->fixed) {
        check(g->n >= 1, "zero-width native graph unsupported");
        for (uint32_t t = 0; t < g->d; ++t)
          for (unsigned c = 0; c < 4; ++c)
            check(bits(g->payload, (4 * uint64_t(t) + c) * g->iw, g->iw) == t,
                  "terminal fields are not absorbing");
        std::vector<uint8_t> depth(g->S, 255), used(g->d, 0);
        depth[g->root] = 0;
        for (uint64_t i = g->S; i; --i) {
          uint32_t u = uint32_t(i - 1);
          check(depth[u] != 255, "unreachable graph state");
          if (g->term(u)) {
            used[u] = 1;
            continue;
          }
          check(depth[u] < g->n, "internal node at word end");
          for (unsigned c = 0; c < 4; ++c) {
            uint32_t v = g->child(u, c);
            uint8_t next = depth[u] + 1;
            if (g->term(v)) {
              depth[v] = 0;
              used[v] = 1;
            } else {
              check(depth[v] == 255 || depth[v] == next,
                    "cross-depth sharing violates declared normal form");
              depth[v] = next;
            }
          }
        }
        banks.assign(g->n + 1, 0);
        uint64_t pos = g->d;
        for (int l = int(g->n) - 1; l >= 0; --l) {
          banks[l + 1] = pos;
          while (pos < g->S && depth[pos] == l)
            ++pos;
          banks[l] = pos;
        }
        if (pos != g->S)
          banks.clear();
      } else
        banks.assign(g->boundaries.begin(), g->boundaries.begin() + g->n + 1);
      if (variant == 3) {
        check(g->S <= 1ULL << 26, "decoded-graph materialization guard");
        decoded.resize(g->S);
        for (uint64_t u = 0; u < g->S; ++u)
          for (unsigned s = 0; s < 4; ++s)
            decoded[u].c[s] = g->child(u, s);
      }
    } else {
      check(variant >= 0 && variant <= 2, "bad matrix variant");
      m = std::make_unique<Matrix>(path, variant);
    }
    setup_ns = ns(t);
  }
  uint32_t n() const { return g ? g->n : m->n; }
  const std::vector<int64_t> &values() const {
    return g ? g->values : m->values;
  }
  uint32_t child(uint32_t u, unsigned s) const {
    return decoded.empty() ? g->child(u, s)
                           : (g->term(u) ? u : decoded[u].c[s]);
  }
  uint32_t brank(uint32_t u, unsigned side) const {
    if (g->term(u))
      return uint32_t(g->rank(u));
    uint32_t v = 0;
    memcpy(&v, bounds.data() + (2 * uint64_t(u) + side) * rank_bytes,
           rank_bytes);
    return v;
  }
  uint64_t make_bounds() {
    check(bool(g), "only a graph has subtree bounds");
    auto t = Clock::now();
    if (bounds.empty()) {
      rank_bytes = g->d <= 256 ? 1 : g->d <= 65536 ? 2 : 4;
      check(g->S <= std::numeric_limits<size_t>::max() / 8,
            "bound allocation overflow");
      bounds.resize(2 * g->S * rank_bytes);
      for (uint64_t u = 0; u < g->S; ++u) {
        uint32_t lo, hi;
        if (g->term(uint32_t(u)))
          lo = hi = g->rank(uint32_t(u));
        else {
          lo = g->d - 1;
          hi = 0;
          for (unsigned s = 0; s < 4; ++s) {
            auto c = child(uint32_t(u), s);
            lo = std::min(lo, brank(c, 0));
            hi = std::max(hi, brank(c, 1));
          }
        }
        memcpy(bounds.data() + 2 * u * rank_bytes, &lo, rank_bytes);
        memcpy(bounds.data() + (2 * u + 1) * rank_bytes, &hi, rank_bytes);
      }
    }
    return ns(t);
  }
  uint64_t index_bytes() const {
    if (!m)
      return 0;
    uint64_t b = 0;
    for (auto &kv : m->index)
      b += 4 * kv.second.capacity();
    return b;
  }
};
} // namespace
