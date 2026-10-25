#pragma once
#include "common.hpp"

namespace qn {
struct Header {
  char magic[4];
  uint32_t version, n, flags;
  uint64_t nodes, root, terminals, data_offset, reserved0, reserved1;
};
static_assert(sizeof(Header) == 64);
struct Graph {
  std::unique_ptr<MapFile> file;
  uint32_t n = 0, root = 0;
  uint64_t S = 0;
  uint32_t d = 0;
  std::vector<int64_t> values;
  bool fixed = false;
  unsigned iw = 0, vw = 0;
  const uint8_t *payload = nullptr;
  std::array<uint64_t, 21> boundaries{};
  Graph(const std::string &p, bool validate = true);
  uint64_t states() const { return fixed ? S + d : S; }
  bool term(uint32_t u) const { return fixed ? bool(u & TERM) : u < d; }
  uint32_t child(uint32_t u, unsigned s) const {
    if (term(u))
      return u;
    if (fixed)
      return reinterpret_cast<const Quad *>(payload)[u].c[s];
    return uint32_t(bits(payload, (uint64_t(u) * 4 + s) * iw, iw));
  }
  int64_t val(uint32_t u) const { return fixed ? value(u) : values[u]; }
  int rank(uint32_t u) const {
    if (!fixed)
      return int(u);
    return int(std::lower_bound(values.begin(), values.end(), val(u)) -
               values.begin());
  }
  uint32_t terminal_ref(uint32_t i) const {
    return fixed ? terminal(values[i]) : i;
  }
  void validate_structure() const {
    check(term(root) || (root < S), "invalid root");
    if (fixed) {
      check(term(root) ? S == 0
                       : (boundaries[0] - boundaries[1] == 1 && root == S - 1),
            "bad root level");
      for (unsigned l = 0; l < n; ++l)
        for (uint64_t u = boundaries[l + 1]; u < boundaries[l]; ++u) {
          Quad q{};
          for (unsigned s = 0; s < 4; ++s) {
            auto c = child(u, s);
            q.c[s] = c;
            if (term(c))
              check(std::binary_search(values.begin(), values.end(), val(c)),
                    "unknown terminal");
            else
              check(l + 1 < n && c >= boundaries[l + 2] &&
                        c < boundaries[l + 1],
                    "edge skipped/changed level");
          }
          check(!constant(q), "unreduced constant block");
        }
      if (term(root))
        check(std::binary_search(values.begin(), values.end(), val(root)),
              "root terminal absent");
    } else {
      for (uint64_t u = 0; u < S; ++u) {
        bool equal = true;
        auto first = child(u, 0);
        for (unsigned s = 0; s < 4; ++s) {
          auto c = child(u, s);
          check(u < d ? c == u : c < u, "non-topological edge");
          equal = equal && c == first;
        }
        check(u < d || !equal || first >= d, "unreduced constant block");
      }
    }
  }
  int64_t evaluate(uint32_t a, uint32_t b) const {
    uint32_t u = root;
    for (unsigned i = n; i && !term(u); --i)
      u = child(u, 2 * ((a >> (i - 1)) & 1) + ((b >> (i - 1)) & 1));
    check(term(u), "internal state after word end");
    return val(u);
  }
  void row_walk(uint32_t u, unsigned rem, uint32_t a, int32_t *out) const {
    if (term(u)) {
      std::fill(out, out + (1ULL << rem), int32_t(val(u)));
      return;
    }
    check(rem > 0, "row walk beyond depth");
    uint32_t high = 2 * ((a >> (rem - 1)) & 1);
    uint32_t half = 1u << (rem - 1);
    row_walk(child(u, high), rem - 1, a, out);
    row_walk(child(u, high + 1), rem - 1, a, out + half);
  }
};
} // namespace qn
