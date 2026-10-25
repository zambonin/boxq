#pragma once
#include "engine.hpp"

namespace {
struct Filter {
  const std::vector<int64_t> &values;
  std::vector<uint8_t> allowed;
  std::vector<uint32_t> prefix;
  std::vector<uint8_t> direct;
  int64_t base = 0, equality = 0;
  bool all = false, nonzero = false, one = false;
  Filter(const std::vector<int64_t> &v, const uint8_t *a, uint64_t d)
      : values(v), allowed(a, a + d) {
    check(d == v.size(), "value filter dictionary mismatch");
    prefix.push_back(0);
    all = true;
    nonzero = true;
    for (size_t i = 0; i < d; ++i) {
      check(a[i] <= 1, "invalid filter bit");
      prefix.push_back(prefix.back() + a[i]);
      all = all && a[i];
      nonzero = nonzero && (bool(a[i]) == (v[i] != 0));
    }
    one = prefix.back() == 1;
    if (one)
      for (size_t i = 0; i < d; ++i)
        if (a[i])
          equality = v[i];
    if (!v.empty() && v.back() - v.front() <= 1 << 20) {
      base = v.front();
      direct.assign(size_t(v.back() - base + 1), 0);
      for (size_t i = 0; i < d; ++i)
        direct[v[i] - base] = a[i];
    }
  }
  bool accept(int64_t v) const {
    if (all)
      return true;
    if (nonzero)
      return v != 0;
    if (!direct.empty())
      return v >= base && uint64_t(v - base) < direct.size() &&
             direct[v - base];
    auto i = std::lower_bound(values.begin(), values.end(), v);
    return i != values.end() && *i == v && allowed[i - values.begin()];
  }
  bool possible(uint32_t lo, uint32_t hi) const {
    return prefix[hi + 1] != prefix[lo];
  }
  bool certain(uint32_t lo, uint32_t hi) const {
    return prefix[hi + 1] - prefix[lo] == hi - lo + 1;
  }
};

} // namespace
