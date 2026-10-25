#pragma once
#include "graph.hpp"

namespace qn {
inline Graph::Graph(const std::string &p, bool validate)
    : file(new MapFile(p)) {
  endian();
  check(file->size >= 40, "short graph header");
  auto b = file->data;
  if (std::memcmp(b, "QNF1", 4) == 0) {
    fixed = true;
    check(file->size >= 232, "short QNF1 header");
    Header h{};
    std::memcpy(&h, b, 64);
    check(h.version == 1 && h.flags == 1 && h.n >= 1 && h.n <= 20 &&
              h.nodes < TERM && h.root <= UINT32_MAX && h.terminals >= 1 &&
              h.terminals <= uint64_t(1) << (2 * h.n) && !h.reserved0 &&
              !h.reserved1,
          "bad QNF1 header");
    n = h.n;
    S = h.nodes;
    root = uint32_t(h.root);
    d = uint32_t(h.terminals);
    check(h.terminals <= UINT32_MAX, "too many terminals");
    check(h.data_offset >= 232 + 4 * uint64_t(d) &&
              h.data_offset <= file->size && h.data_offset % 64 == 0 &&
              file->size - h.data_offset == 16 * S,
          "QNF1 length mismatch");
    std::memcpy(boundaries.data(), b + 64, 168);
    check(boundaries[n] == 0 && boundaries[0] == S,
          "level boundaries mismatch");
    for (unsigned i = n + 1; i < 21; ++i)
      check(boundaries[i] == 0, "unused boundary is nonzero");
    for (unsigned i = 0; i < n; ++i)
      check(boundaries[i] >= boundaries[i + 1] && boundaries[i] <= S,
            "unordered boundaries");
    for (uint32_t i = 0; i < d; ++i) {
      int32_t v;
      std::memcpy(&v, b + 232 + 4 * i, 4);
      values.push_back(v);
    }
    for (uint64_t i = 232 + 4 * uint64_t(d); i < h.data_offset; ++i)
      check(b[i] == 0, "nonzero header padding");
    payload = b + h.data_offset;
  } else {
    check(std::memcmp(b, "QDD1", 4) == 0, "expected QNF1 or QDD1 automaton");
    n = b[4];
    iw = b[5];
    vw = b[6];
    check(n <= 20 && iw >= 1 && iw <= 31 && vw >= 1 && vw <= 31 && !b[7],
          "unsupported QDD1 native bounds");
    uint64_t dd, r, z;
    std::memcpy(&S, b + 8, 8);
    std::memcpy(&dd, b + 16, 8);
    std::memcpy(&r, b + 24, 8);
    std::memcpy(&z, b + 32, 8);
    check(S < TERM && dd >= 1 && dd <= S && r < S && !z, "bad QDD1 dimensions");
    d = uint32_t(dd);
    root = uint32_t(r);
    check(file->size == 40 + (4 * S * iw + d * uint64_t(vw) + 7) / 8,
          "QDD1 length mismatch");
    payload = b + 40;
    for (uint32_t t = 0; t < d; ++t)
      values.push_back(sbits(payload, 4 * S * iw + t * uint64_t(vw), vw));
  }
  check(std::is_sorted(values.begin(), values.end()) &&
            std::adjacent_find(values.begin(), values.end()) == values.end(),
        "terminal dictionary order");
  if (validate)
    validate_structure();
}
} // namespace qn
