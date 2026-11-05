#!/usr/bin/env python3
"""Patch only a fresh, pinned CaDiCaL 3.0.1 checkout for v9.0 diagnostics.

This is an instrumented research build, NEVER upstream production CaDiCaL.
Real pre-minimization LBD/glue, search propagations and backjump depths.
Patch is strict: stop immediately if expected original source changes.
"""
from pathlib import Path
import sys
root=Path(sys.argv[1]) if len(sys.argv)>1 else Path("cadical-src")
def patch(rel,old,new):
    p=root/"src"/rel
    source=p.read_text()
    count=source.count(old)
    if count!=1: raise RuntimeError(f"{rel}: expected one patch anchor; found {count}: {old[:80]}")
    p.write_text(source.replace(old,new,1))

patch("cadical.hpp", "class Solver {\n\npublic:",
"""// DRNAS v9.0 diagnostic telemetry (NOT a standard upstream API).
// All counters are cumulative and can only be queried between solve() calls.
struct DrnasTelemetry {
  int64_t conflicts = 0, search_propagations = 0, backtracks = 0;
  int64_t learned_clauses = 0, lbd_sum = 0, lbd_le2 = 0, lbd_le4 = 0;
  int64_t jump_depth_sum = 0, jumps = 0;
};

class Solver {

public:""")
patch("cadical.hpp",
      "  int64_t irredundant () const; // Number of active irredundant clauses.",
      """  int64_t irredundant () const; // Number of active irredundant clauses.
  // Experimental diagnostics, only in a separately patched CaDiCaL build.
  DrnasTelemetry drnas_telemetry () const;""")
patch("stats.hpp",
      "  int64_t conflicts = 0; // generated conflicts in 'propagate'",
      """  int64_t conflicts = 0; // generated conflicts in 'propagate'
  // DRNAS v9.0 quality audit: raw first-UIP LBD and actual jump-depth data.
  int64_t drnas_lbd_sum = 0;
  int64_t drnas_lbd_le2 = 0, drnas_lbd_le4 = 0;
  int64_t drnas_jump_depth_sum = 0, drnas_jump_count = 0;""")
patch("analyze.cpp",
      """  stats.learned.literals += size;
  stats.learned.clauses++;
  assert (glue < size);""",
      """  stats.learned.literals += size;
  stats.learned.clauses++;
  // True pre-minimization first-UIP glue/LBD, not clause length.
  // Adds a few integer operations only on conflict analysis (not propagation).
  stats.drnas_lbd_sum += glue;
  stats.drnas_lbd_le2 += (glue <= 2);
  stats.drnas_lbd_le4 += (glue <= 4);
  assert (glue < size);""")
patch("analyze.cpp",
      """  int new_level = determine_actual_backtrack_level (jump);
  UPDATE_AVERAGE (averages.current.level, new_level);
  backtrack (new_level);""",
      """  int new_level = determine_actual_backtrack_level (jump);
  UPDATE_AVERAGE (averages.current.level, new_level);
  // Record actual decision-level drop, including chronological adjustments.
  stats.drnas_jump_count++;
  if (level > new_level)
    stats.drnas_jump_depth_sum += level - new_level;
  backtrack (new_level);""")
patch("solver.cpp",
      """int64_t Solver::irredundant () const {""",
      """DrnasTelemetry Solver::drnas_telemetry () const {
  REQUIRE_VALID_STATE ();
  const Stats &s = internal->stats;
  DrnasTelemetry t;
  t.conflicts = s.conflicts;
  t.search_propagations = s.propagations.search;
  t.backtracks = s.backtracks;
  t.learned_clauses = s.learned.clauses;
  t.lbd_sum = s.drnas_lbd_sum;
  t.lbd_le2 = s.drnas_lbd_le2;
  t.lbd_le4 = s.drnas_lbd_le4;
  t.jump_depth_sum = s.drnas_jump_depth_sum;
  t.jumps = s.drnas_jump_count;
  return t;
}

int64_t Solver::irredundant () const {""")
print("DRNAS_V90_PATCH_OK: six anchored instrumentation edits in 4 files")
