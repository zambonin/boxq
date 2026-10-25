#pragma once
#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fcntl.h>
#include <filesystem>
#include <fstream>
#include <limits>
#include <map>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
#include <sys/mman.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <unistd.h>
#include <vector>

namespace qn {
using Clock = std::chrono::steady_clock;
inline double seconds(Clock::time_point t) {
  return std::chrono::duration<double>(Clock::now() - t).count();
}
inline uint64_t ns(Clock::time_point t) {
  return std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now() - t)
      .count();
}
inline void check(bool b, const char *s) {
  if (!b)
    throw std::runtime_error(s);
}
inline void check(bool b, const std::string &s) {
  if (!b)
    throw std::runtime_error(s);
}
inline void endian() {
  uint16_t x = 1;
  check(*reinterpret_cast<uint8_t *>(&x) == 1,
        "native layout currently needs a little-endian host");
}
constexpr uint32_t TERM = 0x80000000u;
inline uint32_t terminal(int64_t x) {
  check(x >= -(1LL << 30) && x < (1LL << 30),
        "terminal outside native signed 31-bit range");
  return TERM | uint32_t(x < 0 ? -2 * x - 1 : 2 * x);
}
inline int32_t value(uint32_t t) {
  uint32_t z = t & ~TERM;
  return (z & 1) ? -int32_t(z / 2) - 1 : int32_t(z / 2);
}
struct Quad {
  uint32_t c[4];
  bool operator==(const Quad &x) const { return std::memcmp(c, x.c, 16) == 0; }
};
static_assert(sizeof(Quad) == 16);
inline uint64_t mix(uint64_t x) {
  x ^= x >> 30;
  x *= 0xbf58476d1ce4e5b9ULL;
  x ^= x >> 27;
  x *= 0x94d049bb133111ebULL;
  return x ^ (x >> 31);
}
inline uint64_t hash(const Quad &q) {
  return mix((uint64_t(q.c[0]) << 32) | q.c[1]) ^
         mix(((uint64_t(q.c[2]) << 32) | q.c[3]) + 0x9e3779b97f4a7c15ULL);
}
inline bool constant(const Quad &q) {
  return (q.c[0] & TERM) && q.c[0] == q.c[1] && q.c[0] == q.c[2] &&
         q.c[0] == q.c[3];
}
struct MapFile {
  int fd = -1;
  uint8_t *data = nullptr;
  uint64_t size = 0;
  bool writable = false;
  MapFile() = default;
  MapFile(const MapFile &) = delete;
  MapFile &operator=(const MapFile &) = delete;
  MapFile(const std::string &path, bool write = false, uint64_t create_size = 0)
      : writable(write) {
    fd = open(path.c_str(), write ? (O_RDWR | O_CREAT | O_EXCL) : O_RDONLY,
              0600);
    check(fd >= 0, "cannot open mapping: " + path);
    try {
      if (write)
        check(ftruncate(fd, off_t(create_size)) == 0,
              "cannot size mapping: " + path);
      struct stat st{};
      check(fstat(fd, &st) == 0 && st.st_size >= 0, "fstat failed");
      size = uint64_t(st.st_size);
      if (size) {
        void *p =
            mmap(nullptr, size, write ? (PROT_READ | PROT_WRITE) : PROT_READ,
                 write ? MAP_SHARED : MAP_PRIVATE, fd, 0);
        check(p != MAP_FAILED, "mmap failed: " + path);
        data = static_cast<uint8_t *>(p);
      }
    } catch (...) {
      close(fd);
      fd = -1;
      throw;
    }
  }
  ~MapFile() {
    if (data)
      munmap(data, size);
    if (fd >= 0)
      close(fd);
  }
  void sync() {
    if (data && writable)
      check(msync(data, size, MS_SYNC) == 0, "msync failed");
    if (writable)
      check(fsync(fd) == 0, "fsync failed");
  }
};
inline void read_exact(std::istream &in, void *p, size_t n) {
  in.read(static_cast<char *>(p), n);
  check(size_t(in.gcount()) == n, "truncated input");
}
inline void write_exact(std::ostream &out, const void *p, size_t n) {
  out.write(static_cast<const char *>(p), n);
  check(bool(out), "write failed (check free disk space)");
}
inline uint64_t file_size(const std::string &p) {
  return std::filesystem::file_size(p);
}
inline uint64_t rss() {
#ifdef __linux__
  std::ifstream status("/proc/self/status");
  std::string line;
  while (std::getline(status, line)) {
    if (line.rfind("VmHWM:", 0) == 0)
      return std::stoull(line.substr(6)) * 1024;
  }
#endif
  struct rusage r{};
  getrusage(RUSAGE_SELF, &r);
#ifdef __APPLE__
  return uint64_t(r.ru_maxrss);
#else
  return uint64_t(r.ru_maxrss) * 1024;
#endif
}
inline uint64_t bits(const uint8_t *p, uint64_t bit, unsigned w) {
  if (!w)
    return 0;
  uint64_t b = bit / 8;
  unsigned sh = bit % 8;
  uint64_t z = 0;
  unsigned bytes = (sh + w + 7) / 8;
  for (unsigned i = 0; i < std::min(8u, bytes); ++i)
    z |= uint64_t(p[b + i]) << (8 * i);
  z >>= sh;
  if (bytes == 9)
    z |= uint64_t(p[b + 8]) << (64 - sh);
  return w == 64 ? z : z & ((1ULL << w) - 1);
}
inline int64_t sbits(const uint8_t *p, uint64_t bit, unsigned w) {
  if (!w)
    return 0;
  uint64_t z = bits(p, bit, w);
  if (w < 64 && (z & (1ULL << (w - 1))))
    z |= ~((1ULL << w) - 1);
  return int64_t(z);
}
// QNF1 header: 64-byte fixed prefix, 21 uint64 level boundaries, d int32
// values, padding to 64-byte alignment, then 16-byte nodes in bottom-up level
// order.
} // namespace qn
