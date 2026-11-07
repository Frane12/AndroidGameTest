#!/usr/bin/env python3
"""V13.1 exact 256th-conflict counter snapshot in a pinned, instrumented CaDiCaL.
Research-only extension after patch_cadical_v90.py. The executable must be built
once per run and pinned across benchmark shards. Do not modify upstream source.
The snapshot is taken immediately after conflict counter increment, BEFORE
analysis of that conflict may add a learned clause or update its LBD.
"""
from pathlib import Path
import sys

root=Path(sys.argv[1] if len(sys.argv)>1 else "cadical-src")/"src"

def patch(rel,old,new):
    p=root/rel
    s=p.read_text()
    n=s.count(old)
    if n!=1:
        raise RuntimeError(f"V131 {rel}: expected exactly one anchor, found {n}: {old[:110]!r}")
    p.write_text(s.replace(old,new,1))

patch("stats.hpp",
      "  int64_t drnas_jump_depth_sum = 0, drnas_jump_count = 0;",
      """  int64_t drnas_jump_depth_sum = 0, drnas_jump_count = 0;
  // Research-only snapshot at the 256th conflict counter increment.
  bool drnas_prefix256_valid = false;
  int64_t drnas_prefix256_props = 0, drnas_prefix256_backtracks = 0;
  int64_t drnas_prefix256_learned = 0, drnas_prefix256_lbd_sum = 0;
  int64_t drnas_prefix256_lbd2 = 0, drnas_prefix256_lbd4 = 0;
  int64_t drnas_prefix256_jump_sum = 0, drnas_prefix256_jumps = 0;""")
patch("internal.hpp",
      "  void limit_conflicts (int);     // Force conflict limit.",
      """  void limit_conflicts (int);     // Force conflict limit.
  void drnas_capture_prefix256 (); // Research-only exact counter snapshot.""")
patch("limit.cpp",
      "void Internal::limit_conflicts (int l) {",
      """// Capture only once at the 256th observed conflict, not at solve() return.
void Internal::drnas_capture_prefix256 () {
  if (stats.conflicts != 256 || stats.drnas_prefix256_valid) return;
  stats.drnas_prefix256_valid = true;
  stats.drnas_prefix256_props = stats.propagations.search;
  stats.drnas_prefix256_backtracks = stats.backtracks;
  stats.drnas_prefix256_learned = stats.learned.clauses;
  stats.drnas_prefix256_lbd_sum = stats.drnas_lbd_sum;
  stats.drnas_prefix256_lbd2 = stats.drnas_lbd_le2;
  stats.drnas_prefix256_lbd4 = stats.drnas_lbd_le4;
  stats.drnas_prefix256_jump_sum = stats.drnas_jump_depth_sum;
  stats.drnas_prefix256_jumps = stats.drnas_jump_count;
}

void Internal::limit_conflicts (int l) {""")
patch("propagate.cpp",
      "      stats.conflicts++;",
      """      stats.conflicts++;
      drnas_capture_prefix256 ();""")
patch("analyze.cpp",
      "      stats.conflicts++;",
      """      stats.conflicts++;
      drnas_capture_prefix256 ();""")
patch("analyze.cpp",
      "          ++stats.conflicts;",
      """          ++stats.conflicts;
          drnas_capture_prefix256 ();""")
patch("cadical.hpp",
      "  DrnasTelemetry drnas_telemetry () const;",
      """  DrnasTelemetry drnas_telemetry () const;
  // Snapshot of counter values immediately at conflict number 256.
  // If solving finished earlier, returns live counters (<256).
  DrnasTelemetry drnas_prefix_256 () const;""")
patch("solver.cpp",
      "DrnasTelemetry Solver::drnas_telemetry () const {",
      """DrnasTelemetry Solver::drnas_prefix_256 () const {
  REQUIRE_VALID_STATE ();
  const Stats &s = internal->stats;
  if (!s.drnas_prefix256_valid) return drnas_telemetry ();
  DrnasTelemetry t;
  t.conflicts = 256;
  t.search_propagations = s.drnas_prefix256_props;
  t.backtracks = s.drnas_prefix256_backtracks;
  t.learned_clauses = s.drnas_prefix256_learned;
  t.lbd_sum = s.drnas_prefix256_lbd_sum;
  t.lbd_le2 = s.drnas_prefix256_lbd2;
  t.lbd_le4 = s.drnas_prefix256_lbd4;
  t.jump_depth_sum = s.drnas_prefix256_jump_sum;
  t.jumps = s.drnas_prefix256_jumps;
  return t;
}

DrnasTelemetry Solver::drnas_telemetry () const {""")
print("V131_EXACT256_PATCH_PASS eight strict source edits; 256th-conflict snapshot",flush=True)
