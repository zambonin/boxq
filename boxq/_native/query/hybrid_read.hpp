#pragma once
#include "../hybrid_index.hpp"

namespace qn {
inline HybridIndex::HybridIndex(const std::string &path) : file(path) {
  check(file.size >= 64, "short hybrid header");
  memcpy(&h, file.data, 64);
  check(!memcmp(h.magic, "HIX1", 4) && h.version == 1 && h.n >= 1 &&
            h.n <= 16 && h.d >= 1 && h.d <= 65536 && h.implicit < h.d &&
            h.rank_block == 4096 && !h.reserved0 && !h.reserved1,
        "hybrid header guard");
  check(h.cells == (1ULL << (2 * h.n)) && h.file_bytes == file.size &&
            h.data_offset == (64 + 48 * uint64_t(h.d) + 63) / 64 * 64 &&
            h.data_offset <= file.size,
        "hybrid size mismatch");
  b.resize(h.d);
  memcpy(b.data(), file.data + 64, b.size() * 48);
  uint64_t offset = h.data_offset, total = 0;
  for (uint32_t i = 0; i < h.d; ++i) {
    auto &r = b[i];
    values.push_back(r.value);
    check(!r.reserved && r.count <= h.cells && r.value >= INT32_MIN &&
              r.value <= INT32_MAX,
          "hybrid bucket count/value");
    total += r.count;
    if (i == h.implicit) {
      check(!r.kind && !r.offset && !r.bytes && !r.rank_offset,
            "implicit bucket carries payload");
      continue;
    }
    offset = (offset + 7) / 8 * 8;
    check(r.offset == offset && r.bytes <= file.size - offset,
          "hybrid overlapping/truncated payload");
    if (r.kind == 1) {
      check(r.bytes == 4 * r.count && !r.rank_offset, "posting size mismatch");
      uint32_t previous = 0;
      for (uint64_t j = 0; j < r.count; ++j) {
        uint32_t v;
        memcpy(&v, file.data + r.offset + 4 * j, 4);
        check(v < h.cells && (!j || previous < v),
              "unsorted/duplicate posting");
        previous = v;
      }
    } else {
      check(r.kind == 2, "hybrid bucket kind");
      uint64_t words = (h.cells + 63) / 64, blocks = (h.cells + 4095) / 4096;
      check(r.rank_offset == r.offset + words * 8 &&
                r.bytes == words * 8 + (blocks + 1) * 8,
            "bitmap rank size mismatch");
      uint64_t count = 0;
      auto p = reinterpret_cast<const uint64_t *>(file.data + r.offset),
           ranks =
               reinterpret_cast<const uint64_t *>(file.data + r.rank_offset);
      for (uint64_t j = 0; j < words; ++j) {
        if (!(j % 64))
          check(ranks[j / 64] == count, "invalid rank checkpoint");
        count += __builtin_popcountll(p[j]);
      }
      check(count == r.count && ranks[blocks] == count,
            "bitmap cardinality mismatch");
      if (h.cells % 64)
        check(!(p[words - 1] >> (h.cells % 64)), "nonzero bitmap padding");
    }
    offset += r.bytes;
  }
  check(offset == file.size && total == h.cells,
        "hybrid coverage/cardinality mismatch");
  check(std::is_sorted(values.begin(), values.end()) &&
            std::adjacent_find(values.begin(), values.end()) == values.end(),
        "hybrid value order");
  // The implicit bucket is a complement only if explicit buckets are
  // disjoint. Check intersections without allocating an N^2-bit temporary
  // membership map.
  for (uint32_t i = 0; i < h.d; ++i)
    if (i != h.implicit)
      for (uint32_t j = i + 1; j < h.d; ++j)
        if (j != h.implicit) {
          auto &a = b[i];
          auto &z = b[j];
          if (a.kind == 2 && z.kind == 2) {
            auto x = reinterpret_cast<const uint64_t *>(file.data + a.offset),
                 y = reinterpret_cast<const uint64_t *>(file.data + z.offset);
            for (uint64_t k = 0; k < (h.cells + 63) / 64; ++k)
              check(!(x[k] & y[k]), "overlapping value bitmaps");
          } else if (a.kind == 1 && z.kind == 1) {
            auto x = reinterpret_cast<const uint32_t *>(file.data + a.offset),
                 y = reinterpret_cast<const uint32_t *>(file.data + z.offset);
            uint64_t u = 0, v = 0;
            while (u < a.count && v < z.count) {
              check(x[u] != y[v], "overlapping value postings");
              if (x[u] < y[v])
                ++u;
              else
                ++v;
            }
          } else {
            auto &posting = a.kind == 1 ? a : z;
            auto &bitmap = a.kind == 2 ? a : z;
            auto x =
                reinterpret_cast<const uint32_t *>(file.data + posting.offset);
            for (uint64_t k = 0; k < posting.count; ++k)
              check(!(file.data[bitmap.offset + x[k] / 8] & (1u << (x[k] % 8))),
                    "overlapping posting/bitmap");
          }
        }
}
} // namespace qn
