#pragma once
#include "bottom.hpp"

void verify(const std::string &graphpath, const std::string &lutpath,
            const std::string &mode) {
  auto started = Clock::now();
  Graph g(graphpath);
  check(g.n <= 16, "DDT verification width guard");
  auto lut = read_lut(lutpath, g.n);
  uint32_t N = 1u << g.n;
  std::vector<int32_t> expanded(N);
  std::vector<uint32_t> expected(N);
  std::vector<uint64_t> hist(uint64_t(N) + 1, 0);
  uint64_t cells = 0, rows = 0;
  for (uint32_t a = 0; a < N; ++a) {
    if (mode == "sample" && a >= 16 && a % 1021)
      continue;
    row(lut, a, expected);
    g.row_walk(g.root, g.n, a, expanded.data());
    for (uint32_t b = 0; b < N; ++b) {
      check(expanded[b] >= 0 && uint32_t(expanded[b]) == expected[b],
            "DDT mismatch at " + std::to_string(a) + "," + std::to_string(b));
      if (a)
        ++hist[expanded[b]];
    }
    cells += N;
    ++rows;
    if (a % 4096 == 0)
      std::cerr << "verified row " << a << "/" << N << "\n";
  }
  std::cout << "{\"all_rows\":" << (mode == "full" ? "true" : "false")
            << ",\"rows\":" << rows << ",\"cells\":" << cells
            << ",\"states\":" << g.states() << ",\"spectrum\":{";
  bool comma = false;
  for (uint32_t v = 0; v <= N; ++v) {
    auto c = hist[v];
    if (!c)
      continue;
    if (comma)
      std::cout << ',';
    comma = true;
    std::cout << '"' << v << "\":" << c;
  }
  std::cout << "},\"native_seconds\":" << seconds(started)
            << ",\"peak_rss_bytes\":" << rss() << "}\n";
}
