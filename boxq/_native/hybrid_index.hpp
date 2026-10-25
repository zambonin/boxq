#pragma once
#include "core/graph_read.hpp"
// HIX1: mutually exclusive value buckets, most frequent bucket implicit.
// Sparse buckets are sorted uint32 coordinates; dense buckets use bitmaps with
// rank checkpoints. Layout is explicitly little-endian and restricted to n<=16.
namespace qn {
struct HixHeader {
  char magic[4];
  uint32_t version, n, d, implicit, rank_block;
  uint64_t cells, data_offset, file_bytes, reserved0, reserved1;
};
static_assert(sizeof(HixHeader) == 64);
struct HixBucket {
  int64_t value;
  uint64_t count, offset, bytes, rank_offset;
  uint32_t kind, reserved;
};
static_assert(sizeof(HixBucket) == 48);
struct HybridIndex {
  MapFile file;
  HixHeader h{};
  std::vector<HixBucket> b;
  std::vector<int64_t> values;
  explicit HybridIndex(const std::string &path);

  uint64_t rank(uint32_t i, uint64_t end) const {
    auto &r = b[i];
    check(end <= h.cells, "rank endpoint outside table");
    if (r.kind == 1) {
      auto p = reinterpret_cast<const uint32_t *>(file.data + r.offset);
      if (end == h.cells)
        return r.count;
      return std::lower_bound(p, p + r.count, uint32_t(end)) - p;
    }
    check(r.kind == 2, "implicit rank needs subtraction");
    auto p = reinterpret_cast<const uint64_t *>(file.data + r.offset);
    auto ranks = reinterpret_cast<const uint64_t *>(file.data + r.rank_offset);
    uint64_t block = end / 4096, pos = block * 64, word = end / 64,
             z = ranks[block];
    for (; pos < word; ++pos)
      z += __builtin_popcountll(p[pos]);
    if (end % 64)
      z += __builtin_popcountll(p[word] & ((1ULL << (end % 64)) - 1));
    return z;
  }
  uint64_t range_count(uint32_t i, uint64_t lo, uint64_t hi) const {
    if (i != h.implicit)
      return rank(i, hi) - rank(i, lo);
    uint64_t count = hi - lo;
    for (uint32_t j = 0; j < h.d; ++j)
      if (j != i)
        count -= range_count(j, lo, hi);
    return count;
  }
  bool contains(uint32_t i, uint64_t k) const {
    auto &r = b[i];
    if (r.kind == 2)
      return (file.data[r.offset + k / 8] >> (k % 8)) & 1;
    if (r.kind == 1) {
      auto p = reinterpret_cast<const uint32_t *>(file.data + r.offset);
      return std::binary_search(p, p + r.count, uint32_t(k));
    }
    throw std::runtime_error("implicit contains unsupported");
  }
  int64_t get(uint64_t k) const {
    check(k < h.cells, "hybrid coordinate outside table");
    for (uint32_t i = 0; i < h.d; ++i)
      if (i != h.implicit && contains(i, k))
        return b[i].value;
    return b[h.implicit].value;
  }
};
} // namespace qn
