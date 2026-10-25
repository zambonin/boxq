// Streaming QNF1 -> QDD1 serialization, preserving native deterministic node
// order.
#include "core/graph_read.hpp"
#include <iostream>
using namespace qn;
struct Writer {
  std::ofstream out;
  std::vector<uint8_t> buffer;
  size_t used = 0;
  uint64_t acc = 0;
  unsigned held = 0;
  Writer(const std::string &p) : out(p, std::ios::binary), buffer(1 << 20) {
    check(bool(out), "cannot create packed output");
  }
  void raw(const void *p, size_t n) { write_exact(out, p, n); }
  void byte(uint8_t b) {
    buffer[used++] = b;
    if (used == buffer.size()) {
      raw(buffer.data(), used);
      used = 0;
    }
  }
  void put(uint64_t v, unsigned w) {
    check(w <= 31, "packing width guard");
    acc |= v << held;
    held += w;
    while (held >= 8) {
      byte(uint8_t(acc));
      acc >>= 8;
      held -= 8;
    }
  }
  void finish() {
    if (held)
      byte(uint8_t(acc));
    if (used)
      raw(buffer.data(), used);
    out.flush();
    check(bool(out), "packed flush failed");
    out.close();
  }
};
int main(int argc, char **argv) {
  try {
    check(argc == 3, "native_pack INPUT.qnf OUTPUT.qdd");
    endian();
    auto started = Clock::now();
    Graph g(argv[1]);
    check(g.fixed, "packing input must be QNF1");
    uint64_t S = g.states();
    unsigned iw = 1;
    while ((1ULL << iw) < S)
      ++iw;
    unsigned vw = 1;
    for (auto v : g.values) {
      while (v < -(1LL << (vw - 1)) || v >= (1LL << (vw - 1)))
        ++vw;
    }
    check(vw <= 31, "value-width guard");
    Writer w(argv[2]);
    uint8_t header[40] = {};
    memcpy(header, "QDD1", 4);
    header[4] = uint8_t(g.n);
    header[5] = uint8_t(iw);
    header[6] = uint8_t(vw);
    uint64_t d = g.d;
    uint64_t root = g.term(g.root) ? g.rank(g.root) : g.root + d;
    memcpy(header + 8, &S, 8);
    memcpy(header + 16, &d, 8);
    memcpy(header + 24, &root, 8);
    w.raw(header, 40);
    for (uint64_t u = 0; u < d; ++u)
      for (unsigned s = 0; s < 4; ++s)
        w.put(u, iw);
    for (uint64_t u = 0; u < g.S; ++u)
      for (unsigned s = 0; s < 4; ++s) {
        auto c = g.child(uint32_t(u), s);
        w.put(g.term(c) ? g.rank(c) : c + d, iw);
      }
    for (auto v : g.values)
      w.put(uint64_t(v) & ((1ULL << vw) - 1), vw);
    w.finish();
    // Verify the explicit node-ID bijection and every physical successor field.
    // This lifts the source graph's cell verification to the packed
    // representation.
    auto pack_seconds = seconds(started);
    auto check_started = Clock::now();
    Graph target(argv[2], false);
    check(target.n == g.n && target.S == S && target.values == g.values &&
              target.root == root,
          "packed header/dictionary mismatch");
    for (uint64_t u = 0; u < d; ++u)
      for (unsigned c = 0; c < 4; ++c)
        check(bits(target.payload, (4 * u + c) * iw, iw) == u,
              "packed terminal edge mismatch");
    for (uint64_t u = 0; u < g.S; ++u)
      for (unsigned c = 0; c < 4; ++c) {
        auto v = g.child(uint32_t(u), c);
        uint64_t mapped = g.term(v) ? g.rank(v) : v + d;
        check(bits(target.payload, (4 * (u + d) + c) * iw, iw) == mapped,
              "packed internal edge mismatch");
      }
    auto check_seconds = seconds(check_started);
    std::cout << "{\"format\":\"QDD1\",\"node_order\":\"native-bottom-up-"
                 "partition-order-v1\",\"states\":"
              << S << ",\"index_bits\":" << iw << ",\"value_bits\":" << vw
              << ",\"bytes\":" << file_size(argv[2])
              << ",\"successor_fields_verified\":" << 4 * S
              << ",\"isomorphism_verified\":true,\"packing_seconds\":"
              << pack_seconds << ",\"isomorphism_seconds\":" << check_seconds
              << ",\"native_seconds\":" << seconds(started)
              << ",\"peak_rss_bytes\":" << rss() << "}\n";
    return 0;
  } catch (const std::exception &e) {
    std::cerr << "ERROR: " << e.what() << '\n';
    return 2;
  }
}
