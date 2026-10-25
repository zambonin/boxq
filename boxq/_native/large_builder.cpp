#include "build/bottom.hpp"
#include "build/level.hpp"
#include "build/verify.hpp"

int main(int argc, char **argv) {
  try {
    endian();
    check(argc >= 2, "mode required");
    std::string mode = argv[1];
    std::cout << std::setprecision(12);
    if (mode == "bottom") {
      check(argc == 6, "bottom LUT OUTPUT N MAX_UNIQUE");
      auto n = unsigned(std::stoul(argv[4]));
      check(n >= 1 && n <= 16, "builder width must be 1..16");
      bottom(argv[2], argv[3], n, std::stoull(argv[5]));
    } else if (mode == "level") {
      check(argc == 7, "level INPUT OUTPUT SIDE BASE BUDGET_BYTES");
      level(argv[2], argv[3], uint32_t(std::stoul(argv[4])),
            uint32_t(std::stoul(argv[5])), std::stoull(argv[6]));
    } else if (mode == "verify") {
      check(argc == 5, "verify GRAPH LUT full|sample");
      std::string v = argv[4];
      check(v == "full" || v == "sample", "bad verification mode");
      verify(argv[2], argv[3], v);
    } else
      throw std::runtime_error("unknown mode");
    return 0;
  } catch (const std::exception &e) {
    std::cerr << "ERROR: " << e.what() << '\n';
    return 2;
  }
}
