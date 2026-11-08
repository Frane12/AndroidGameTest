#!/usr/bin/env python3
"""C8H: add a sound skip-all-BVE control and learned-clause window telemetry."""
from __future__ import annotations
import argparse
import pathlib
import c8c_patch_upstream_cadical173 as base

def replace_once(text, before, after):
    count = text.count(before)
    if count != 1:
        raise RuntimeError("C8H exact upstream anchor mismatch: " + str(count))
    return text.replace(before, after)

def main(root):
    root = pathlib.Path(root)
    base.main(root)

    elim = root / "src/elim.cpp"
    text = elim.read_text()
    text = replace_once(
        text,
'''static bool c8c_block_candidate (int idx) {
  const char *s = std::getenv ("DRNAS_C8C_SKIP_VARS");''',
'''static bool c8c_block_candidate (int idx) {
  const char *all = std::getenv ("DRNAS_C8C_SKIP_ALL_BVE");
  if (all && !std::strcmp (all, "1"))
    return true;
  const char *s = std::getenv ("DRNAS_C8C_SKIP_VARS");''')
    elim.write_text(text)

    analyze = root / "src/analyze.cpp"
    text = analyze.read_text()
    text = replace_once(
        text,
'''#include "internal.hpp"

namespace CaDiCaL {
''',
'''#include "internal.hpp"
#include <cstdio>
#include <cstdlib>
#include <cstring>

namespace CaDiCaL {

static bool c8h_learned_trace_enabled () {
  const char *s = std::getenv ("DRNAS_C8H_LEARNED_TRACE");
  return s && !std::strcmp (s, "1");
}

static long long c8h_learned_min_conflict () {
  const char *s = std::getenv ("DRNAS_C8H_MIN_CONFLICT");
  if (!s || !*s)
    return 0;
  char *end = 0;
  long long value = std::strtoll (s, &end, 10);
  return end && !*end ? value : 0;
}
''')
    text = replace_once(
        text,
'''  int size = (int) clause.size ();
  const int glue = (int) levels.size () - 1;''',
'''  int size = (int) clause.size ();
  const int c8h_uip_size = size;
  const int glue = (int) levels.size () - 1;''')
    text = replace_once(
        text,
'''  // Update actual size statistics.
  //
  stats.units += (size == 1);''',
'''  // C8H observational telemetry: raw 1st-UIP size, final minimized size,
  // glue/LBD, conflict index, and learned-clause sequence. Disabled by default.
  //
  if (c8h_learned_trace_enabled () &&
      (long long) stats.conflicts >= c8h_learned_min_conflict ())
    std::fprintf (stderr,
        "C8H_LEARNED conflict=%lld learned=%lld uip_size=%d final_size=%d glue=%d\\n",
        (long long) stats.conflicts, (long long) stats.learned.clauses,
        c8h_uip_size, size, glue);

  // Update actual size statistics.
  //
  stats.units += (size == 1);''')
    analyze.write_text(text)
    print("C8H_SOURCE_PATCH_PASS")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source_tree")
    main(parser.parse_args().source_tree)
