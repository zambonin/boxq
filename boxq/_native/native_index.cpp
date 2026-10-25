// Deliberately reuse the format reader, not the table construction oracle.
#include "query/filter.hpp"
#include <iomanip>
#include <iostream>
int main(int argc, char **argv) {
  try {
    endian();
    check(argc == 3, "native_index INPUT OUTPUT");
    auto t = Clock::now();
    Matrix m(argv[1], 0);
    check(!m.hybrid, "input is already a hybrid index");
    std::map<int64_t, uint64_t> hist;
    for (uint64_t k = 0; k < m.cells; ++k)
      ++hist[m.get(k)];
    HixHeader h{};
    memcpy(h.magic, "HIX1", 4);
    h.version = 1;
    h.n = m.n;
    h.d = hist.size();
    h.rank_block = 4096;
    h.cells = m.cells;
    h.data_offset = (64 + 48 * uint64_t(h.d) + 63) / 64 * 64;
    std::vector<HixBucket> b;
    uint64_t best = 0;
    for (auto &kv : hist) {
      if (kv.second > best) {
        h.implicit = b.size();
        best = kv.second;
      }
      HixBucket r{};
      r.value = kv.first;
      r.count = kv.second;
      b.push_back(r);
    }
    uint64_t end = h.data_offset;
    for (uint32_t i = 0; i < h.d; ++i) {
      if (i == h.implicit)
        continue;
      auto &r = b[i];
      end = (end + 7) / 8 * 8;
      r.offset = end;
      uint64_t bitsbytes = ((m.cells + 63) / 64) * 8,
               rankbytes = ((m.cells + 4095) / 4096 + 1) * 8;
      r.kind = 4 * r.count < bitsbytes + rankbytes ? 1 : 2;
      r.bytes = r.kind == 1 ? 4 * r.count : bitsbytes + rankbytes;
      r.rank_offset = r.kind == 2 ? end + bitsbytes : 0;
      end += r.bytes;
    }
    h.file_bytes = end;
    {
      MapFile out(argv[2], true, end);
      memcpy(out.data, &h, 64);
      memcpy(out.data + 64, b.data(), 48 * b.size());
      std::vector<uint64_t> seen(h.d);
      std::map<int64_t, uint32_t> ids;
      for (uint32_t i = 0; i < h.d; ++i)
        ids[b[i].value] = i;
      std::vector<uint32_t> codes;
      int64_t low = hist.begin()->first, high = hist.rbegin()->first;
      if (high - low <= 1000000) {
        codes.resize(high - low + 1);
        for (auto &kv : ids)
          codes[kv.first - low] = kv.second;
      }
      for (uint64_t k = 0; k < m.cells; ++k) {
        int64_t v = m.get(k);
        uint32_t i = codes.empty() ? ids.at(v) : codes[v - low];
        if (i == h.implicit)
          continue;
        auto &r = b[i];
        if (r.kind == 1) {
          uint32_t pos = k;
          memcpy(out.data + r.offset + 4 * seen[i], &pos, 4);
          ++seen[i];
        } else
          out.data[r.offset + k / 8] |= uint8_t(1u << (k % 8));
      }
      for (uint32_t i = 0; i < h.d; ++i) {
        auto &r = b[i];
        if (r.kind != 2)
          continue;
        auto p = reinterpret_cast<const uint64_t *>(out.data + r.offset);
        auto ranks = reinterpret_cast<uint64_t *>(out.data + r.rank_offset);
        uint64_t count = 0, words = (m.cells + 63) / 64;
        for (uint64_t j = 0; j < words; ++j) {
          if (!(j % 64))
            ranks[j / 64] = count;
          count += __builtin_popcountll(p[j]);
        }
        ranks[(m.cells + 4095) / 4096] = count;
        check(count == r.count, "index cardinality disagreement");
      }
      out.sync();
    }
    HybridIndex checked(argv[2]);
    if (m.cells <= (1 << 22)) {
      for (uint64_t k = 0; k < m.cells; ++k)
        check(checked.get(k) == m.get(k), "index round trip failed");
    }
    std::cout << std::setprecision(12) << "{\"format\":\"HIX1\",\"n\":" << m.n
              << ",\"cells\":" << m.cells << ",\"file_bytes\":" << end
              << ",\"implicit_value\":" << b[h.implicit].value
              << ",\"complete_roundtrip\":"
              << (m.cells <= (1 << 22) ? "true" : "false") << ",\"buckets\":[";
    for (uint32_t i = 0; i < h.d; ++i) {
      if (i)
        std::cout << ',';
      auto &r = b[i];
      std::cout << "{\"value\":" << r.value << ",\"count\":" << r.count
                << ",\"kind\":" << r.kind << ",\"payload_bytes\":" << r.bytes
                << '}';
    }
    std::cout << "],\"native_seconds\":" << seconds(t)
              << ",\"peak_rss_bytes\":" << rss() << "}\n";
    return 0;
  } catch (const std::exception &e) {
    std::cerr << e.what() << '\n';
    return 2;
  }
}
