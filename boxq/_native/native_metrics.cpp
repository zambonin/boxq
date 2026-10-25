// Exact graph-only aggregates. Multiplicity is propagated once per stored edge;
// early terminals account for all unread suffixes. Counts are disk backed.
#include "core/graph_read.hpp"
#include <iostream>
using namespace qn;
int main(int argc, char **argv) {
  try {
    check(argc == 3, "native_metrics GRAPH.qnf SCRATCH_FILE");
    Graph g(argv[1]);
    check(g.fixed, "metrics requires QNF1 level metadata");
    if (std::string(argv[2]) == "levels") {
      std::set<int64_t> constant_values;
      if (g.term(g.root))
        constant_values.insert(g.val(g.root));
      std::cout << "{\"n\":" << g.n << ",\"levels\":[";
      for (unsigned depth = 0; depth <= g.n; ++depth) {
        uint64_t internal = depth < g.n ? g.boundaries[depth] - g.boundaries[depth + 1] : 0;
        uint64_t blocks = 1ULL << (2 * depth);
        uint64_t distinct = internal + constant_values.size();
        if (depth)
          std::cout << ',';
        std::cout << "{\"block_side\":" << (1ULL << (g.n - depth))
                  << ",\"blocks\":" << blocks << ",\"distinct_blocks\":" << distinct
                  << ",\"nonconstant_states\":" << internal
                  << ",\"constant_values\":" << constant_values.size() << '}';
        if (depth < g.n)
          for (uint64_t u = g.boundaries[depth + 1]; u < g.boundaries[depth]; ++u)
            for (unsigned symbol = 0; symbol < 4; ++symbol) {
              auto child = g.child(u, symbol);
              if (g.term(child))
                constant_values.insert(g.val(child));
            }
      }
      std::cout << "]}\n";
      return 0;
    }
    auto started = Clock::now();
    std::map<int64_t, uint64_t> hist;
    uint32_t branch = UINT32_MAX;
    if (g.term(g.root)) {
      hist[g.val(g.root)] = 1ULL << (2 * g.n);
      if (g.val(g.root))
        branch = 0;
    } else {
      MapFile weights(argv[2], true, g.S * 8);
      if (weights.data == nullptr)
        throw std::runtime_error("empty metrics scratch mapping");
      auto count = reinterpret_cast<uint64_t *>(weights.data);
      std::vector<uint8_t> minimum(g.S, 255);
      count[g.root] = 1;
      minimum[g.root] = 0;
      for (unsigned level = 0; level < g.n; ++level) {
        for (uint64_t u = g.boundaries[level + 1]; u < g.boundaries[level];
             ++u) {
          uint64_t multiplicity = count[u];
          check(multiplicity > 0, "unreachable node in metrics");
          for (unsigned s = 0; s < 4; ++s) {
            auto c = g.child(u, s);
            uint32_t weight = minimum[u] + __builtin_popcount(s);
            if (g.term(c)) {
              auto v = g.val(c);
              hist[v] += multiplicity << (2 * (g.n - level - 1));
              if (v)
                branch = std::min(branch, weight);
            } else {
              count[c] += multiplicity;
              minimum[c] = std::min(minimum[c], uint8_t(weight));
            }
          }
        }
        std::cerr << "graph metrics level " << level << "/" << g.n << "\n";
      }
    }
    uint64_t total = 0, mass = 0;
    for (auto [v, c] : hist) {
      check(v >= 0,
            "this metrics command expects a normalized nonnegative DDT");
      total += c;
      mass += uint64_t(v) * c;
    }
    check(total == (1ULL << (2 * g.n)),
          "graph histogram mass of coordinates mismatch");
    std::cout << "{\"states\":" << g.states() << ",\"cells\":" << total
              << ",\"value_mass\":" << mass
              << ",\"minimum_nonzero_combined_weight\":"
              << (branch == UINT32_MAX ? -1 : int(branch))
              << ",\"histogram_all_normalized_coordinates\":{";
    bool comma = false;
    for (auto [v, c] : hist) {
      if (comma)
        std::cout << ',';
      comma = true;
      std::cout << '"' << v << "\":" << c;
    }
    std::cout << "},\"native_seconds\":" << seconds(started)
              << ",\"scratch_bytes\":" << 8 * g.S
              << ",\"minimum_array_bytes\":" << g.S
              << ",\"peak_rss_bytes\":" << rss() << "}\n";
    return 0;
  } catch (const std::exception &e) {
    std::cerr << "ERROR: " << e.what() << '\n';
    return 2;
  }
}
