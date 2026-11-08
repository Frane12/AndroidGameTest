#!/usr/bin/env python3
"""C8I: add prospective BVE early-success gate after 16 scheduled candidates."""
from __future__ import annotations
import argparse
import pathlib
import c8h_patch_upstream_cadical173 as base

def replace_once(text, before, after):
    count = text.count(before)
    if count != 1:
        raise RuntimeError("C8I exact source anchor mismatch: " + str(count))
    return text.replace(before, after)

def main(root):
    root = pathlib.Path(root)
    base.main(root)
    elim = root / "src/elim.cpp"
    text = elim.read_text()
    text = replace_once(
        text,
'''static bool c8c_block_candidate (int idx) {''',
'''static bool c8i_early_gate_enabled () {
  static int cached = -1;
  if (cached < 0) {
    const char *s = std::getenv ("DRNAS_C8I_EARLY_GATE16");
    cached = s && !std::strcmp (s, "1");
  }
  return cached;
}
static bool c8i_gate_trace_enabled () {
  const char *s = std::getenv ("DRNAS_C8I_GATE_TRACE");
  return s && !std::strcmp (s, "1");
}

static bool c8c_block_candidate (int idx) {''')
    text = replace_once(
        text,
'''  long long c8c_candidate_sequence = 0;''',
'''  long long c8c_candidate_sequence = 0;
  long long c8i_early_bve_successes = 0;''')
    text = replace_once(
        text,
'''    const bool c8c_skip = c8c_block_candidate (idx);''',
'''    const bool c8i_gate_skip =
        c8i_early_gate_enabled () && c8c_candidate_sequence >= 16 &&
        c8i_early_bve_successes == 0;
    const bool c8c_skip = c8c_block_candidate (idx) || c8i_gate_skip;''')
    text = replace_once(
        text,
'''    ++c8c_candidate_sequence;
    if (c8c_trace_enabled ())''',
'''    if (c8c_candidate_sequence < 16 &&
        stats.all.eliminated > c8c_pre_eliminated)
      ++c8i_early_bve_successes;
    ++c8c_candidate_sequence;
    if (c8i_early_gate_enabled () && c8c_candidate_sequence == 16 &&
        c8i_gate_trace_enabled ())
      std::fprintf (stderr,
        "C8I_GATE_DECISION candidates=16 early_successes=%lld disabled=%d conflicts=%lld\\n",
        c8i_early_bve_successes, (int)(c8i_early_bve_successes == 0),
        (long long)stats.conflicts);
    if (c8c_trace_enabled ())''')
    elim.write_text(text)
    print("C8I_EARLY_BVE_GATE_PATCH_PASS")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source_tree")
    main(parser.parse_args().source_tree)
