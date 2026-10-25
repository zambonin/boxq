#pragma once
#include "bottom.hpp"

struct Record {
  Quad q;
  uint32_t pos;
};
static_assert(sizeof(Record) == 20);
struct Flat {
  std::vector<Quad> nodes;
  std::vector<uint32_t> slots;
  uint64_t probes = 0, maximum;
  uint32_t base;
  Flat(uint32_t b, uint64_t maximum) : maximum(maximum), base(b) {
    check(maximum < TERM && uint64_t(b) + maximum < TERM,
          "node-id capacity exceeded");
    uint64_t cap = 16;
    while (cap < maximum * 2 + 1)
      cap *= 2;
    slots.assign(cap, 0);
    nodes.reserve(maximum);
  }
  uint32_t get(const Quad &q) {
    uint64_t p = mix(hash(q) + 0x1234d00d98765432ULL) & (slots.size() - 1);
    while (slots[p]) {
      ++probes;
      uint32_t id = slots[p] - 1;
      if (nodes[id] == q)
        return base + id;
      p = (p + 1) & (slots.size() - 1);
    }
    check(nodes.size() < maximum,
          "partition unique-key budget exceeded; retry with a larger budget");
    check(uint64_t(base) + nodes.size() < TERM, "too many internal nodes");
    uint32_t id = uint32_t(nodes.size());
    nodes.push_back(q);
    slots[p] = id + 1;
    return base + id;
  }
};
// Random hash-order writes to a GiB-sized mmap can repeatedly dirty almost
// every page. A second, range-partitioned scatter makes the final frontier a
// sequential write and keeps the anonymous working set below the declared
// budget.
struct Pair {
  uint32_t pos, id;
};
static_assert(sizeof(Pair) == 8);
struct Scatter {
  std::string dir;
  uint64_t total, chunk;
  uint32_t ranges;
  std::vector<std::unique_ptr<std::ofstream>> out;
  std::vector<uint64_t> counts;
  Scatter(const std::string &d, uint64_t cells, uint64_t budget)
      : dir(d), total(cells), chunk(std::max<uint64_t>(4096, budget / 8)) {
    ranges = uint32_t((cells + chunk - 1) / chunk);
    check(ranges <= 512, "scatter partition limit exceeded");
    counts.assign(ranges, 0);
    for (uint32_t i = 0; i < ranges; ++i) {
      auto f = std::make_unique<std::ofstream>(
          dir + "/scatter-" + std::to_string(i) + ".bin", std::ios::binary);
      check(bool(*f), "cannot create scatter file");
      out.push_back(std::move(f));
    }
  }
  void put(uint32_t pos, uint32_t id) {
    check(pos < total, "scatter position outside frontier");
    Pair p{pos, id};
    auto r = uint32_t(pos / chunk);
    write_exact(*out[r], &p, 8);
    ++counts[r];
  }
  void finish() {
    for (auto &f : out)
      flush(*f);
    out.clear();
    std::ofstream frontier(dir + "/frontier.bin", std::ios::binary);
    check(bool(frontier), "cannot create final frontier");
    for (uint32_t r = 0; r < ranges; ++r) {
      uint64_t first = r * chunk, size = std::min(chunk, total - first);
      check(counts[r] == size, "scatter entry count mismatch");
      std::vector<uint32_t> grid(size);
      std::vector<uint8_t> seen(size, 0);
      std::string path = dir + "/scatter-" + std::to_string(r) + ".bin";
      std::ifstream in(path, std::ios::binary);
      Pair p;
      for (uint64_t i = 0; i < size; ++i) {
        read_exact(in, &p, 8);
        check(p.pos >= first && p.pos < first + size, "wrong scatter range");
        auto at = p.pos - first;
        check(!seen[at], "duplicate scatter position");
        seen[at] = 1;
        grid[at] = p.id;
      }
      write_exact(frontier, grid.data(), grid.size() * 4);
      in.close();
      std::filesystem::remove(path);
    }
    flush(frontier);
  }
};
void level(const std::string &input, const std::string &dir, uint32_t side,
           uint32_t base, uint64_t budget) {
  auto started = Clock::now();
  check(side >= 2 && !(side & (side - 1)), "invalid input side");
  check(file_size(input) == uint64_t(side) * side * 4,
        "frontier length mismatch");
  uint32_t outside = side / 2;
  uint64_t candidates = uint64_t(outside) * outside;
  uint64_t max_records = std::max<uint64_t>(16, budget / 40);
  uint32_t parts = 1;
  while ((candidates + parts - 1) / parts > max_records / 2)
    parts *= 2;
  check(parts <= 512, "too many hash partitions; increase --partition-mib");
  std::vector<std::unique_ptr<std::ofstream>> shards;
  std::vector<uint64_t> sizes(parts, 0);
  for (uint32_t i = 0; i < parts; ++i) {
    auto o = std::make_unique<std::ofstream>(
        dir + "/part-" + std::to_string(i) + ".bin", std::ios::binary);
    check(bool(*o), "cannot create shard");
    shards.push_back(std::move(o));
  }
  std::ifstream in(input, std::ios::binary);
  std::vector<uint32_t> r0(side), r1(side);
  uint64_t constant_count = 0;
  Scatter scatter(dir, candidates, budget);
  for (uint32_t y = 0; y < side; y += 2) {
    read_exact(in, r0.data(), side * 4);
    read_exact(in, r1.data(), side * 4);
    for (uint32_t x = 0; x < side; x += 2) {
      Record r{{{r0[x], r0[x + 1], r1[x], r1[x + 1]}},
               uint32_t(uint64_t(y / 2) * outside + x / 2)};
      if (constant(r.q)) {
        scatter.put(r.pos, r.q.c[0]);
        ++constant_count;
      } else {
        uint32_t part = uint32_t(hash(r.q)) & (parts - 1);
        write_exact(*shards[part], &r, sizeof r);
        ++sizes[part];
      }
    }
  }
  for (auto &o : shards) {
    flush(*o);
  }
  shards.clear();
  in.close();
  double partition_seconds = seconds(started);
  auto phase = Clock::now();
  std::ofstream bank(dir + "/nodes.bin", std::ios::binary);
  check(bool(bank), "node output failed");
  uint64_t total = 0, probes = 0, peak_records = 0;
  for (uint32_t p = 0; p < parts; ++p) {
    if (!sizes[p]) {
      std::filesystem::remove(dir + "/part-" + std::to_string(p) + ".bin");
      continue;
    }
    peak_records = std::max(peak_records, sizes[p]);
    Flat index(base + uint32_t(total), std::min(max_records, sizes[p]));
    std::string path = dir + "/part-" + std::to_string(p) + ".bin";
    std::ifstream records(path, std::ios::binary);
    Record r;
    for (uint64_t k = 0; k < sizes[p]; ++k) {
      read_exact(records, &r, sizeof r);
      scatter.put(r.pos, index.get(r.q));
    }
    write_exact(bank, index.nodes.data(), index.nodes.size() * 16);
    total += index.nodes.size();
    probes += index.probes;
    records.close();
    std::filesystem::remove(path);
    std::cerr << "partition " << p + 1 << "/" << parts << "; unique nodes "
              << total << "\n";
  }
  flush(bank);
  double dedup_seconds = seconds(phase);
  phase = Clock::now();
  scatter.finish();
  double scatter_seconds = seconds(phase);
  std::cout << "{\"mode\":\"partitioned-level-scatter-v2\",\"nodes\":" << total
            << ",\"side\":" << outside
            << ",\"constant_blocks\":" << constant_count
            << ",\"partitions\":" << parts
            << ",\"scatter_ranges\":" << scatter.ranges
            << ",\"peak_partition_records\":" << peak_records
            << ",\"hash_probes\":" << probes
            << ",\"partition_seconds\":" << partition_seconds
            << ",\"dedup_seconds\":" << dedup_seconds
            << ",\"scatter_seconds\":" << scatter_seconds
            << ",\"native_seconds\":" << seconds(started)
            << ",\"peak_rss_bytes\":" << rss() << "}\n";
}
