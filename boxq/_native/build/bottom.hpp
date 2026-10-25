#pragma once
#include "../core/graph_read.hpp"
#include <iomanip>
#include <iostream>
#include <unordered_map>

using namespace qn;

struct Hash {
  size_t operator()(const Quad &q) const { return hash(q); }
};
std::vector<uint32_t> read_lut(const std::string &p, unsigned n) {
  uint64_t N = 1ULL << n;
  check(file_size(p) == 4 * N, "LUT size mismatch");
  std::ifstream in(p, std::ios::binary);
  std::vector<uint8_t> b(4 * N);
  read_exact(in, b.data(), b.size());
  std::vector<uint32_t> v(N);
  for (uint64_t i = 0; i < N; ++i) {
    v[i] = (uint32_t(b[4 * i]) << 24) | (uint32_t(b[4 * i + 1]) << 16) |
           (uint32_t(b[4 * i + 2]) << 8) | b[4 * i + 3];
    check(v[i] < N, "non-square lookup");
  }
  return v;
}
void row(const std::vector<uint32_t> &f, uint32_t a, std::vector<uint32_t> &r) {
  std::fill(r.begin(), r.end(), 0);
  if (a == 0)
    return;
  for (uint32_t x = 0; x < f.size(); ++x)
    ++r[f[x] ^ f[x ^ a]];
}
void flush(std::ofstream &o) {
  o.flush();
  check(bool(o), "failed flushing output");
  o.close();
  check(!o.fail(), "failed closing output");
}
void bottom(const std::string &lutpath, const std::string &dir, unsigned n,
            uint64_t limit) {
  auto started = Clock::now();
  auto f = read_lut(lutpath, n);
  uint32_t N = 1u << n;
  std::vector<uint32_t> r0(N), r1(N), out(N / 2);
  std::vector<uint64_t> hist(N + 1, 0);
  std::vector<uint8_t> seen(N + 1, 0);
  std::unordered_map<Quad, uint32_t, Hash> index;
  std::vector<Quad> nodes;
  std::ofstream front(dir + "/frontier.bin", std::ios::binary),
      bank(dir + "/nodes.bin", std::ios::binary);
  check(bool(front) && bool(bank), "bottom outputs failed");
  for (uint32_t a = 0; a < N; a += 2) {
    row(f, a, r0);
    row(f, a + 1, r1);
    for (uint32_t b = 0; b < N; ++b) {
      if (a)
        ++hist[r0[b]];
      ++hist[r1[b]];
      seen[r0[b]] = 1;
      seen[r1[b]] = 1;
    }
    for (uint32_t j = 0; j < N; j += 2) {
      Quad q{{terminal(r0[j]), terminal(r0[j + 1]), terminal(r1[j]),
              terminal(r1[j + 1])}};
      uint32_t id;
      if (constant(q))
        id = q.c[0];
      else {
        auto found = index.find(q);
        if (found != index.end())
          id = found->second;
        else {
          check(nodes.size() < limit, "bottom unique-block budget exceeded; no "
                                      "partial result is certified");
          id = uint32_t(nodes.size());
          nodes.push_back(q);
          index.emplace(q, id);
        }
      }
      out[j / 2] = id;
    }
    write_exact(front, out.data(), 4 * out.size());
    if ((a & 4095) == 0)
      std::cerr << "DDT rows " << a << "/" << N << "; bottom nodes "
                << nodes.size() << "\n";
  }
  write_exact(bank, nodes.data(), 16 * nodes.size());
  flush(front);
  flush(bank);
  std::map<uint32_t, uint64_t> sparse;
  std::set<int32_t> values;
  for (uint32_t v = 0; v <= N; ++v) {
    if (hist[v])
      sparse[v] = hist[v];
    if (seen[v])
      values.insert(v);
  }
  std::cout << "{\"mode\":\"bottom-ddt\",\"nodes\":" << nodes.size()
            << ",\"side\":" << N / 2 << ",\"rows\":" << N
            << ",\"nontrivial_cells\":" << uint64_t(N) * (N - 1)
            << ",\"delta\":" << sparse.rbegin()->first << ",\"spectrum\":{";
  bool comma = false;
  for (auto [v, c] : sparse) {
    if (comma)
      std::cout << ',';
    comma = true;
    std::cout << '"' << v << "\":" << c;
  }
  std::cout << "},\"values\":[";
  comma = false;
  for (auto v : values) {
    if (comma)
      std::cout << ',';
    comma = true;
    std::cout << v;
  }
  std::cout << "],\"native_seconds\":" << seconds(started)
            << ",\"peak_rss_bytes\":" << rss() << "}\n";
}
