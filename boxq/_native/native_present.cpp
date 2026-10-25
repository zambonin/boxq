#include "present/solver.hpp"
#include <iomanip>
#include <iostream>

int main(int argc, char **argv) {
  try {
    endian();
    check(argc == 6,
          "native_present TABLE CASES.bin REPEATS STATE_CAP VARIANT");
    Engine e(argv[1], std::stoi(argv[5]));
    check(e.n() == 4, "PRESENT requires n=4");
    unsigned repeats = std::stoul(argv[3]);
    uint64_t cap = std::stoull(argv[4]);
    check(repeats >= 1 && repeats <= 1000 && cap >= 1, "search limits");
    static const unsigned S[16] = {12, 5,  6,  11, 9, 0, 10, 13,
                                   3,  14, 15, 8,  4, 7, 1,  2};
    for (unsigned a = 0; a < 16; ++a)
      for (unsigned b = 0; b < 16; ++b) {
        int want = 0;
        if (a)
          for (unsigned x = 0; x < 16; ++x)
            want += (S[x] ^ S[x ^ a]) == b;
        auto got = e.g ? e.g->evaluate(a, b) : e.m->get(16 * a + b);
        check(got == want, "input is not the normalized PRESENT DDT");
      }
    auto prep = Clock::now();
    if (e.g)
      e.make_bounds();
    auto bounds_ns = ns(prep);
    MapFile cases(argv[2]);
    check(cases.size && cases.size % 16 == 0 && cases.size <= 16 * 4096,
          "case file dimensions");
    std::vector<std::array<uint64_t, 2>> inputs(cases.size / 16);
    memcpy(inputs.data(), cases.data, cases.size);
    std::cout << "{\"complete\":true,\"rounds\":3,\"open_setup_ns\":"
              << e.setup_ns << ",\"bounds_ns\":" << bounds_ns
              << ",\"row_policy\":\"lazy row cache per endpoint; native graph "
                 "cursor or direct matrix row\",\"samples\":[";
    bool comma = false;
    for (unsigned rep = 0; rep < repeats; ++rep)
      for (unsigned i = 0; i < inputs.size(); ++i) {
        EndpointSolver solver(e, inputs[i][1], cap);
        auto start = Clock::now();
        solver.visit(inputs[i][0], 0, 0, 0);
        auto elapsed = ns(start);
        if (comma)
          std::cout << ',';
        comma = true;
        std::cout << "{\"case\":" << i << ",\"repetition\":" << rep
                  << ",\"weight\":"
                  << (solver.best == UINT32_MAX ? -1 : int(solver.best))
                  << ",\"optimal_characteristics\":" << solver.ways
                  << ",\"elapsed_ns\":" << elapsed
                  << ",\"visited_round_transitions\":" << solver.visits
                  << ",\"row_queries\":" << solver.provider.row_queries
                  << ",\"row_cache_hits\":" << solver.provider.cache_hits
                  << ",\"point_queries\":" << solver.provider.point_queries
                  << ",\"witness\":[" << solver.witness[0] << ','
                  << solver.witness[1] << ',' << solver.witness[2] << "]}";
      }
    std::cout << "],\"peak_rss_bytes\":" << rss() << "}\n";
  } catch (const std::exception &e) {
    std::cerr << e.what() << '\n';
    return 2;
  }
}
