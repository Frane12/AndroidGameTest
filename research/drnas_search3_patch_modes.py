#!/usr/bin/env python3
"""SEARCH3: pinned CaDiCaL 3.0.1 isolated initial VMTF and EVSIDS ablation.
Extend previously tested SEARCH2 patch; original solver and DIMACS unchanged.
"""
from pathlib import Path
import subprocess,sys
root=Path(sys.argv[1]) if len(sys.argv)>1 else Path("cadical-search3")
subprocess.run([sys.executable,"research/drnas_search2_patch_cadical.py",str(root)],check=True)
def patch(file,old,new):
 p=root/"src"/file
 s=p.read_text()
 hits=s.count(old)
 if hits!=1:raise RuntimeError(f"SEARCH3_PATCH_FAIL_CLOSED {file} anchor {hits}: {old[:85]}")
 p.write_text(s.replace(old,new,1))
patch("cadical.hpp",
      "void drnas_seed_initial_order (const std::vector<int> &external_order);",
      "void drnas_seed_initial_order (const std::vector<int> &external_order, int mode);")
patch("internal.hpp",
      "void drnas_seed_initial_priorities (const vector<int> &internal_order);",
      "void drnas_seed_initial_priorities (const vector<int> &internal_order, int mode);")
patch("score.cpp",
      "void Internal::drnas_seed_initial_priorities (const vector<int> &order) {",
      """void Internal::drnas_seed_initial_priorities (const vector<int> &order, int mode) {
  assert (mode > 0 && mode < 4);""")
patch("score.cpp","if (opts.bump)\n      bump_queue (idx);",
      "if (opts.bump && (mode & 1))\n      bump_queue (idx);")
patch("score.cpp",
      """score (idx) = ++rank * unit;
    if (scores.contains (idx))
      scores.update (idx);""",
      """++rank;
    if (mode & 2) {
      score (idx) = rank * unit;
      if (scores.contains (idx))
        scores.update (idx);
    }""")
patch("solver.cpp",
      "void Solver::drnas_seed_initial_order (const std::vector<int> &external_order) {",
      """void Solver::drnas_seed_initial_order (const std::vector<int> &external_order, int mode) {
  REQUIRE (mode >= 1 && mode <= 3, "SEARCH3 invalid mechanism mode");""")
patch("solver.cpp",
      "internal->drnas_seed_initial_priorities (internal_ids);",
      "internal->drnas_seed_initial_priorities (internal_ids, mode);")
print("SEARCH3_PATCH_PASS CaDiCaL301 original native VMTF=1 EVSIDS=2 BOTH=3")
