// C ABI for native table queries.
#include "query/cursor.hpp"

namespace {
thread_local std::string error;
} // namespace
extern "C" {
const char *boxq_error() { return error.c_str(); }
void *boxq_open(const char *path, int variant) {
  try {
    endian();
    error.clear();
    return new Engine(path, variant);
  } catch (const std::exception &e) {
    error = e.what();
    return nullptr;
  }
}
void boxq_close(void *p) { delete static_cast<Engine *>(p); }
void *boxq_query(const uint8_t *p, uint64_t size) {
  try {
    error.clear();
    return new Query(p, size);
  } catch (const std::exception &e) {
    error = e.what();
    return nullptr;
  }
}
void boxq_query_close(void *p) { delete static_cast<Query *>(p); }
int boxq_info(void *p, uint64_t *out) {
  try {
    auto &e = *static_cast<Engine *>(p);
    out[0] = e.n();
    out[1] = e.values().size();
    out[2] = e.g ? e.g->states() : e.m->cells;
    out[3] = e.g ? e.g->file->size : e.m->file->size;
    out[4] = e.bounds.size();
    out[5] = e.decoded.capacity() * 16 + (e.m ? e.m->dense.capacity() * 4 : 0);
    out[6] = e.index_bytes();
    out[7] = e.setup_ns;
    out[8] = bool(e.g);
    out[9] = rss();
    return 0;
  } catch (const std::exception &e) {
    error = e.what();
    return -1;
  }
}
int boxq_values(void *p, int64_t *out) {
  try {
    auto &v = static_cast<Engine *>(p)->values();
    std::copy(v.begin(), v.end(), out);
    return 0;
  } catch (const std::exception &e) {
    error = e.what();
    return -1;
  }
}
int boxq_bounds(void *p, uint64_t *out) {
  try {
    error.clear();
    *out = static_cast<Engine *>(p)->make_bounds();
    return 0;
  } catch (const std::exception &e) {
    error = e.what();
    return -1;
  }
}
int boxq_eval(void *p, uint32_t a, uint32_t b, int64_t *out) {
  try {
    auto &e = *static_cast<Engine *>(p);
    check(a < (1u << e.n()) && b < (1u << e.n()), "cell outside table");
    *out = e.g ? e.g->evaluate(a, b) : e.m->get((uint64_t(a) << e.n()) | b);
    return 0;
  } catch (const std::exception &e) {
    error = e.what();
    return -1;
  }
}
int boxq_row(void *p, uint32_t a, int32_t *out) {
  try {
    auto &e = *static_cast<Engine *>(p);
    check(a < (1u << e.n()), "row outside table");
    if (e.g)
      e.g->row_walk(e.g->root, e.n(), a, out);
    else
      for (uint32_t b = 0; b < (1u << e.n()); ++b)
        out[b] = int32_t(e.m->get((uint64_t(a) << e.n()) | b));
    return 0;
  } catch (const std::exception &e) {
    error = e.what();
    return -1;
  }
}
int boxq_run_v2(void *p, void *qp, const uint8_t *allowed, uint64_t d,
                int enumerate, uint64_t maxmemo, uint64_t maxout, int strategy,
                uint64_t memory_bytes, Stats *out) {
  try {
    error.clear();
    auto &e = *static_cast<Engine *>(p);
    auto &q = *static_cast<Query *>(qp);
    check(e.n() == q.n, "query width mismatch");
    check(maxmemo > 0 && maxmemo <= 100000000, "invalid product-state limit");
    check(maxout <= 100000000, "invalid output limit");
    check(strategy >= 0 && strategy <= 2 && memory_bytes >= 1,
          "invalid count strategy/workspace");
    std::vector<Hit>().swap(e.output);
    Filter f(e.values(), allowed, d);
    auto started = Clock::now();
    Stats s;
    if (e.g) {
      GraphRun runner(e, q, f, maxmemo, maxout);
      s = runner.run(enumerate != 0, strategy, memory_bytes);
    } else {
      MatrixRun runner(e, q, f, enumerate != 0, maxout);
      s = runner.run();
    }
    s.elapsed_ns = ns(started);
    *out = s;
    return 0;
  } catch (const std::exception &e) {
    error = e.what();
    return -1;
  }
}
uint64_t boxq_output_size(void *p) {
  return static_cast<Engine *>(p)->output.size();
}
const Hit *boxq_output(void *p) {
  return static_cast<Engine *>(p)->output.data();
}
}
