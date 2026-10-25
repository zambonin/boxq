#pragma once
#include "../core/graph_read.hpp"

using namespace qn;
namespace {
constexpr uint32_t REJECT = 0xffffffffu;
struct Query {
  uint32_t n, total, root;
  std::vector<Quad> next;
  std::vector<uint8_t> final, universal;
  std::vector<uint64_t> suffix;
  std::vector<uint32_t> layer;
  Query(const uint8_t *p, uint64_t size) {
    check(size >= 16 && !memcmp(p, "QRY1", 4), "bad query header");
    memcpy(&n, p + 4, 4);
    memcpy(&total, p + 8, 4);
    memcpy(&root, p + 12, 4);
    check(n >= 1 && n <= 20 && total > 0 && total <= 1000000 && root < total,
          "query size guard");
    uint64_t off = 16 + 4 * (uint64_t(n) + 2);
    check(size == off + 17 * uint64_t(total), "query length mismatch");
    layer.resize(n + 2);
    memcpy(layer.data(), p + 16, 4 * (n + 2));
    check(layer[0] == 0 && layer[n + 1] == total && root < layer[1],
          "invalid query layers");
    for (uint32_t i = 0; i <= n; ++i)
      check(layer[i] <= layer[i + 1] && layer[i + 1] <= total,
            "unordered query layers");
    next.resize(total);
    memcpy(next.data(), p + off, 16 * total);
    final.assign(p + off + 16 * total, p + off + 17 * total);
    suffix.assign(total, 0);
    universal.assign(total, 0);
    for (int l = int(n); l >= 0; --l)
      for (uint32_t q = layer[l]; q < layer[l + 1]; ++q) {
        check(final[q] <= 1, "bad acceptance bit");
        if (unsigned(l) == n) {
          for (auto c : next[q].c)
            check(c == REJECT, "transition beyond final layer");
          suffix[q] = final[q];
          universal[q] = final[q];
        } else {
          check(!final[q], "early acceptance bit");
          bool all = true;
          for (auto c : next[q].c) {
            if (c == REJECT) {
              all = false;
              continue;
            }
            check(c >= layer[l + 1] && c < layer[l + 2],
                  "query edge skips layer");
            suffix[q] += suffix[c];
            all = all && universal[c];
          }
          universal[q] = all;
        }
      }
  }
  bool accepts(uint32_t a, uint32_t b) const {
    uint32_t q = root;
    for (uint32_t i = n; i; --i) {
      q = next[q].c[2 * ((a >> (i - 1)) & 1) + ((b >> (i - 1)) & 1)];
      if (q == REJECT)
        return false;
    }
    return final[q];
  }
};
} // namespace
