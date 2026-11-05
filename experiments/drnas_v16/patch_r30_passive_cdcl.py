#!/usr/bin/env python3
"""R30 PASSIVE native Kissat snapshots at conflict-free BCP boundaries.

No SAT policy modification. The only native changes are a read-only snapshot
routine and one call after conflict-free propagation in the search loop.
Internal trail literals are mapped back to external DIMACS IDs; unknown
mappings/truncated snapshots are explicitly marked and never used to claim
a full same-trail GF(2)/BCP comparison.
"""
import argparse
from pathlib import Path
import hashlib

UPSTREAM = "8af8e56f174b778aef3aa45af9f739b2a5f492c2"
MARKS = (0, 256, 1024, 4096)
SNAP_MAX = 1024

def change_once(s, before, after, what):
    count=s.count(before)
    if count!=1:
        raise RuntimeError("R30_SOURCE_ANCHOR_CHANGED "+what+" matches="+str(count))
    return s.replace(before,after,1)

def patch(source):
    helper=r'''
// DRNAS R30: PASSIVE ONLY. No variable phases, restarts, clauses,
// decisions, or propagation state are changed by these snapshots.
// Capture only after a conflict-free propagation return from the
// original search loop, never on an inconsistent active trail.
// Exported original DIMACS assignments may omit eliminated variables.
static unsigned drnas_r30_checkpoint = 0;
static void drnas_r30_snapshot (kissat *solver) {
  static const uint64_t marks[4] = {0,256,1024,4096};
  if (drnas_r30_checkpoint >= 4) return;
  const uint64_t conflicts = solver->statistics.conflicts;
  if (conflicts < marks[drnas_r30_checkpoint]) return;
  const unsigned mark = (unsigned) marks[drnas_r30_checkpoint++];
  const size_t total = SIZE_ARRAY (solver->trail);
  const bool bounded = total <= 1024;
  size_t mapped=0, unmapped=0, decisions=0, reason_binary=0;
  const unsigned *trail = BEGIN_ARRAY (solver->trail);
  for (size_t i=0;i<total;i++) {
    unsigned lit=trail[i];
    int ext=kissat_export_literal(solver,lit);
    if (ext) mapped++; else unmapped++;
    const assigned *a=solver->assigned + IDX(lit);
    if (a->reason == DECISION_REASON) decisions++;
    if (a->binary) reason_binary++;
  }
  printf ("c R30_TRACE mark=%u conflict=%" PRIu64
          " decisions=%" PRIu64 " restarts=%" PRIu64
          " propagations=%" PRIu64 " learned=%" PRIu64
          " stable=%u trail_total=%zu mapped=%zu unmapped=%zu"
          " trail_decisions=%zu trail_binary_reasons=%zu"
          " complete=%u\n",
          mark, conflicts, solver->statistics.decisions,
          solver->statistics.restarts,
          solver->statistics.propagations,
          solver->statistics.clauses_learned,
          (unsigned) solver->stable,total,mapped,unmapped,
          decisions,reason_binary,(unsigned) (bounded && !unmapped));
  // Full snapshot only: a truncated trail would create a false algebraic
  // "gap" relative to a different condition. Parseable original DIMACS
  // signed literals and current levels are preserved without modification.
  printf ("c R30_TRAIL mark=%u literals=",mark);
  if (bounded && !unmapped) {
    for (size_t i=0;i<total;i++) {
      unsigned lit=trail[i];
      const assigned *a=solver->assigned + IDX(lit);
      int ext=kissat_export_literal(solver,lit);
      if (i) putchar (',');
      printf ("%d:%u:%u",ext,a->level,
              (unsigned) (a->reason == DECISION_REASON ? 1 :
                          a->binary ? 2 : a->level == 0 ? 0 : 3));
    }
  }
  putchar ('\n');
  fflush (stdout);
}

'''
    source=change_once(source, "int kissat_search (kissat *solver) {",
                       helper+"int kissat_search (kissat *solver) {",
                       "search_entry")
    source=change_once(source,
        "      clause *conflict = kissat_search_propagate (solver);\n      if (conflict)",
        "      clause *conflict = kissat_search_propagate (solver);\n"
        "      if (!conflict) drnas_r30_snapshot (solver);\n"
        "      if (conflict)",
        "after_propagate")
    if source.count("c R30_TRACE")!=1 or source.count("c R30_TRAIL")!=1:
        raise RuntimeError("R30_MARKER_MISSING")
    return source

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--kissat-root",required=True,type=Path)
    a=ap.parse_args()
    f=a.kissat_root/"src"/"search.c"
    original=f.read_text()
    changed=patch(original)
    f.write_text(changed)
    print("R30_PASSIVE_PATCH_OK",UPSTREAM,"search_sha256="+
          hashlib.sha256(changed.encode()).hexdigest(),flush=True)

if __name__=="__main__":
    main()
