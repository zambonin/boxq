#pragma once
#include "matrix.hpp"

namespace {
struct RawHeader {
  char magic[4];
  uint32_t version, n, bytes;
  uint64_t cells, reserved;
};
static_assert(sizeof(RawHeader) == 32);
inline Matrix::Matrix(const std::string &path, int variant)
    : file(new MapFile(path)) {
  if (file->size >= 32 && !memcmp(file->data, "RAW1", 4)) {
    RawHeader rh{};
    memcpy(&rh, file->data, 32);
    check(rh.version == 1 && rh.n >= 1 && rh.n <= 16 &&
              (rh.bytes == 2 || rh.bytes == 4) && !rh.reserved &&
              rh.cells == (1ULL << (2 * rh.n)) &&
              file->size == 32 + rh.cells * rh.bytes,
          "raw matrix header mismatch");
    n = rh.n;
    cells = rh.cells;
    rawbytes = rh.bytes;
    p = file->data + 32;
    kind = 4;
    if (rawbytes == 2) {
      std::vector<uint8_t> seen(65536, 0);
      for (uint64_t i = 0; i < cells; ++i) {
        int16_t v;
        memcpy(&v, p + 2 * i, 2);
        seen[int(v) + 32768] = 1;
      }
      for (int k = 0; k < 65536; ++k)
        if (seen[k])
          values.push_back(k - 32768);
    } else {
      std::set<int64_t> vals;
      for (uint64_t i = 0; i < cells; ++i) {
        int32_t v;
        memcpy(&v, p + 4 * i, 4);
        vals.insert(v);
      }
      values.assign(vals.begin(), vals.end());
    }
    check(!variant, "raw matrix supports mapped variant only");
    return;
  }
  if (file->size >= 4 && !memcmp(file->data, "HIX1", 4)) {
    check(!variant, "hybrid index supports mapped variant only");
    hybrid = std::make_unique<HybridIndex>(path);
    n = hybrid->h.n;
    cells = hybrid->h.cells;
    values = hybrid->values;
    kind = 3;
    return;
  }
  check(file->size >= 40, "short matrix header");
  auto h = file->data;
  n = h[4];
  iw = h[5];
  vw = h[6];
  check(n >= 1 && n <= 16 && iw <= 31 && vw >= 1 && vw <= 31 && !h[7],
        "native matrix format guard");
  cells = 1ULL << (2 * n);
  uint64_t a, b, c, e;
  memcpy(&a, h + 8, 8);
  memcpy(&b, h + 16, 8);
  memcpy(&c, h + 24, 8);
  memcpy(&e, h + 32, 8);
  p = h + 40;
  if (!memcmp(h, "RNG1", 4)) {
    kind = 0;
    check(a == cells && !b && !c && !e &&
              file->size == 56 + (cells * iw + 7) / 8,
          "range length/header mismatch");
    memcpy(&base, p, 8);
    memcpy(&step, p + 8, 8);
    check(step > 0 && base >= INT32_MIN && base <= INT32_MAX && iw <= 16,
          "unsupported range");
    check((uint64_t(1) << iw) - 1 <= uint64_t(INT32_MAX - base) / step,
          "range exceeds int32");
    p += 16;
    for (uint64_t v = 0; v < (1ULL << iw); ++v)
      values.push_back(base + step * v);
  } else if (!memcmp(h, "DNS1", 4)) {
    kind = 1;
    check(a == cells && b >= 1 && b <= cells && !c && !e,
          "bad dense dictionary header");
    check(b <= 1000000, "dictionary guard");
    d = uint32_t(b);
    codes_off = d * uint64_t(vw);
    check(file->size == 40 + (codes_off + cells * iw + 7) / 8,
          "dense length mismatch");
    for (uint32_t i = 0; i < d; ++i)
      values.push_back(sbits(p, i * uint64_t(vw), vw));
  } else if (!memcmp(h, "BMP1", 4)) {
    kind = 2;
    nnz = a;
    check(a <= cells && b <= a && b <= 1000000 && ((b == 0) == (a == 0)),
          "bad bitmap dictionary");
    d = uint32_t(b);
    block = c;
    rb = e;
    check((!block && !rb) || (block >= 8 && block <= 65536 &&
                              !(block & (block - 1)) && rb >= 1 && rb <= 64),
          "invalid rank layout");
    dict_off = cells;
    codes_off = cells + d * uint64_t(vw);
    rank_off = codes_off + nnz * iw;
    uint64_t ranks = block ? (cells + block - 1) / block + 1 : 0;
    check(file->size == 40 + (rank_off + ranks * rb + 7) / 8,
          "bitmap length mismatch");
    values.push_back(0);
    for (uint32_t i = 0; i < d; ++i)
      values.push_back(sbits(p, dict_off + i * uint64_t(vw), vw));
    std::sort(values.begin(), values.end());
  } else
    throw std::runtime_error("unknown native matrix format");
  check(std::is_sorted(values.begin(), values.end()) &&
            std::adjacent_find(values.begin(), values.end()) == values.end(),
        "matrix dictionary order");
  if (variant) {
    check(cells <= 1ULL << 26, "dense/indexed materialization guard exceeded");
    dense.resize(cells);
    for (uint64_t k = 0; k < cells; ++k)
      dense[k] = int32_t(get_packed(k));
    if (variant == 2) {
      for (uint64_t k = 0; k < cells; ++k)
        index[dense[k]].push_back(uint32_t(k));
    }
  }
}
} // namespace
