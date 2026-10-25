#pragma once
#include "dfa.hpp"
#include "hybrid_read.hpp"

namespace {
struct Matrix {
  std::unique_ptr<HybridIndex> hybrid;
  unsigned rawbytes = 0;
  std::unique_ptr<MapFile> file;
  uint32_t n, d = 0;
  uint64_t cells, nnz = 0, block = 0, rb = 0, dict_off = 0, codes_off = 0,
                  rank_off = 0;
  unsigned iw, vw;
  int kind;
  int64_t base = 0;
  uint64_t step = 1;
  const uint8_t *p;
  std::vector<int64_t> values;
  std::vector<int32_t> dense;
  std::map<int64_t, std::vector<uint32_t>> index;
  Matrix(const std::string &path, int variant);

  uint64_t popbits(uint64_t start, uint64_t length) const {
    uint64_t sum = 0;
    while (length) {
      unsigned take = unsigned(std::min<uint64_t>(64, length));
      sum += __builtin_popcountll(bits(p, start, take));
      start += take;
      length -= take;
    }
    return sum;
  }
  int64_t get_packed(uint64_t k) const {
    if (hybrid)
      return hybrid->get(k);
    if (rawbytes) {
      if (rawbytes == 2) {
        int16_t v;
        memcpy(&v, p + 2 * k, 2);
        return v;
      }
      int32_t v;
      memcpy(&v, p + 4 * k, 4);
      return v;
    }
    if (kind == 0)
      return base + step * bits(p, k * iw, iw);
    if (kind == 1) {
      auto v = bits(p, codes_off + k * iw, iw);
      check(v < d, "bad dense code");
      return values[v];
    }
    if (!bits(p, k, 1))
      return 0;
    uint64_t r = block ? bits(p, rank_off + (k / block) * rb, rb) +
                             popbits((k / block) * block, k % block)
                       : popbits(0, k);
    check(r < nnz, "bad rank prefix");
    auto code = bits(p, codes_off + r * iw, iw);
    check(code < d, "bad bitmap code");
    return sbits(p, dict_off + code * vw, vw);
  }
  int64_t get(uint64_t k) const {
    return dense.empty() ? get_packed(k) : dense[k];
  }
};
} // namespace
