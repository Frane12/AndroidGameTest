#!/usr/bin/env python3
"""Pin-checked research-only CaDiCaL rel-3.0.1 source instrumentation.
Directly changes INITIAL VMTF / EVSIDS priorities in the existing native CDCL
engine, not external CNF variable renaming. Neither original CNF nor upstream
installation nor frozen baseline binary is modified.
"""
from pathlib import Path
import hashlib,sys
base=Path(sys.argv[1]) if len(sys.argv)>1 else Path("cadical-search2")
root=base/"src"
need_commit="c60730422e758ef1cebe7aeddf2dda31c996bf04"
import subprocess
commit=subprocess.check_output(["git","-C",str(base),"rev-parse","HEAD"],text=True).strip()
if commit!=need_commit:raise RuntimeError("SEARCH2_PATCH_FAIL_CLOSED upstream commit drift "+commit)
def patch(filename,old,new):
 p=root/filename
 body=p.read_text()
 count=body.count(old)
 if count!=1:raise RuntimeError("SEARCH2_PATCH_FAIL_CLOSED missing or ambiguous "+filename+" "+str(count)+" "+old[:110])
 p.write_text(body.replace(old,new,1))

patch("cadical.hpp","class Solver {\n\npublic:",
"""struct DrnasSearch2Telemetry {
  int64_t conflicts = 0, decisions = 0, search_propagations = 0;
  int64_t total_propagations = 0;
};

class Solver {

public:""")
patch("cadical.hpp","  int solve ();",
"""  int solve ();

  // DRNAS SEARCH2 only: experimental PRIORITIES, not added clauses.
  // external_order is LOW priority -> HIGH priority.
  void drnas_seed_initial_order (const std::vector<int> &external_order);
  DrnasSearch2Telemetry drnas_search2_telemetry () const;""")
patch("internal.hpp","  void init_scores (int old_max_var, int new_max_var);",
"""  void init_scores (int old_max_var, int new_max_var);
  // Research-only single pass seed; does not interfere with future CDCL bumping.
  void drnas_seed_initial_priorities (const vector<int> &internal_order);""")
patch("score.cpp","} // namespace CaDiCaL",
"""// DRNAS SEARCH2: seed BOTH CaDiCaL's focused VMTF queue and stable EVSIDS
// heap before the first solve. Existing conflict bumping remains unchanged.
// Caller supplies a complete uniqueness-checked subset of internal variables,
// from LOW to HIGH importance. No source clauses/assignments are changed.
void Internal::drnas_seed_initial_priorities (const vector<int> &order) {
  assert (!level);
  vector<unsigned char> used (max_var + 1, 0);
  const double unit = order.empty () ? 0.0 : 0.125 / order.size ();
  unsigned rank = 0;
  for (int idx : order) {
    assert (idx > 0 && idx <= max_var);
    assert (!used[idx]);
    used[idx] = 1;
    // VMTF naturally prefers variables most recently bumped.
    if (opts.bump)
      bump_queue (idx);
    // Stable EVSIDS starts with a small bonus, later learned conflicts win.
    score (idx) = ++rank * unit;
    if (scores.contains (idx))
      scores.update (idx);
  }
}

} // namespace CaDiCaL""")
patch("solver.cpp","int Solver::active () const {",
"""// DRNAS SEARCH2 experimental public-to-internal variable mapping.
void Solver::drnas_seed_initial_order (const std::vector<int> &external_order) {
  REQUIRE_VALID_STATE ();
  REQUIRE (state () == CONFIGURING || state () == STEADY,
           "SEARCH2 priorities must be seeded before first solve");
  std::vector<unsigned char> seen (external->e2i.size (), 0);
  std::vector<int> internal_ids;
  internal_ids.reserve (external_order.size ());
  for (int elit : external_order) {
    REQUIRE (elit > 0 && (size_t) elit < external->e2i.size (),
             "SEARCH2 invalid external variable");
    REQUIRE (!seen[elit], "SEARCH2 repeated external variable");
    seen[elit] = 1;
    int idx = external->e2i[elit];
    if (idx)
      internal_ids.push_back (idx);
  }
  internal->drnas_seed_initial_priorities (internal_ids);
}

DrnasSearch2Telemetry Solver::drnas_search2_telemetry () const {
  REQUIRE_VALID_STATE ();
  const Stats &s = internal->stats;
  DrnasSearch2Telemetry t;
  t.conflicts = s.conflicts;
  t.decisions = s.decisions;
  t.search_propagations = s.propagations.search;
  t.total_propagations = s.propagations.search + s.propagations.probe;
  return t;
}

int Solver::active () const {""")
print("SEARCH2_PATCH_PASS pinned_cadical_commit="+commit+
      " source_files=cadical.hpp,internal.hpp,score.cpp,solver.cpp "+
      "engine=VMTF+EVSIDS no_original_cnf_mutation=1")
