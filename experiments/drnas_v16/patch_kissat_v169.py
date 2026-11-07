#!/usr/bin/env python3
"""Patch EXACT pinned Kissat 4.0.4 search.c to switch strategy in-place.

Unlike repeated kissat_solve(), this executes once inside ONE search loop.
Learned clauses, trail, phases, queue, assignment, and solver pointer persist.
A c DRNAS_SWITCH line shows the switch was performed and statistics retained.
Ordinary Kissat runs with no DRNAS_SWITCH_MODE environment var are unchanged.

Fail closed: refuse unknown source layout. This is a research-only patch.
"""
from pathlib import Path
import argparse
import hashlib

PINNED="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
IMPORT="#include <inttypes.h>\n"
HOOK="""#include <stdlib.h>
#include <stdio.h>
#include <string.h>
"""
ENTRY="""int kissat_search (kissat *solver) {
  REPORT (0, '*');"""
ENTRY_REPLACE="""int kissat_search (kissat *solver) {
  // DRNAS: same solver, same learned clause database, no second solve().
  // Only explicit two-mode probe/continuation runs activate this branch.
  const char *drnas_mode = getenv ("DRNAS_SWITCH_MODE");
  bool drnas_armed = drnas_mode && (!strcmp (drnas_mode, "baseline") ||
                                   !strcmp (drnas_mode, "restart-only"));
  unsigned long drnas_threshold = 20000;
  const char *drnas_threshold_env = getenv ("DRNAS_SWITCH_CONFLICTS");
  if (drnas_armed && drnas_threshold_env) {
    char *end = 0;
    unsigned long val = strtoul (drnas_threshold_env, &end, 10);
    if (!*drnas_threshold_env || !end || *end || val < 1000 ||
        val > 100000000UL) {
      fprintf (stderr, "DRNAS: invalid conflict threshold\\n");
      abort ();
    }
    drnas_threshold = val;
  }
  REPORT (0, '*');"""
OLD="""      if (conflict)
        res = kissat_analyze (solver, conflict);
      else if (solver->iterating)"""
NEW="""      if (conflict) {
        res = kissat_analyze (solver, conflict);
        // Switch ONLY after an analyzed conflict, never in propagation,
        // without releasing/reinitializing the Kissat solver.
        if (!res && drnas_armed && CONFLICTS >= drnas_threshold) {
          const int target_before = GET_OPTION (target);
          const int restart_before = GET_OPTION (restartint);
          const uint64_t learned_before = solver->statistics.clauses_learned;
          const uint64_t conflicts_before = CONFLICTS;
          const uint64_t restarts_before = solver->statistics.restarts;
          kissat_set_option (solver, "target", 1);
          kissat_set_option (solver, "restartint",
                             !strcmp (drnas_mode, "baseline") ? 1 : 50);
          // Update next focused-restart limit so interval change is
          // effective now, not only after an unrelated scheduled restart.
          if (!solver->stable)
            kissat_update_focused_restart_limit (solver);
          fprintf (stdout,
            "c DRNAS_SWITCH conflicts=%" PRIu64
            " learned_before=%" PRIu64
            " learned_after=%" PRIu64
            " restarts=%" PRIu64
            " from_target=%d to_target=%d"
            " from_restartint=%d to_restartint=%d"
            " mode=%s\\n",
            conflicts_before, learned_before,
            solver->statistics.clauses_learned,
            restarts_before, target_before, GET_OPTION (target),
            restart_before, GET_OPTION (restartint), drnas_mode);
          fflush (stdout);
          drnas_armed = false;
        }
      } else if (solver->iterating)"""

def exact_replace(src,old,new,description):
    if src.count(old)!=1:
        raise RuntimeError(f"Upstream layout drift at {description}: count={src.count(old)}")
    return src.replace(old,new,1)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--kissat-root",required=True,type=Path)
    a=p.parse_args()
    source=a.kissat_root/"src"/"search.c"
    original=source.read_text(encoding="utf8")
    if "DRNAS_SWITCH" in original:
        raise RuntimeError("Already patched; refuse double instrumentation")
    patched=exact_replace(original,IMPORT,IMPORT+HOOK,"include")
    patched=exact_replace(patched,ENTRY,ENTRY_REPLACE,"search entry")
    patched=exact_replace(patched,OLD,NEW,"analysis and strategy switch")
    source.write_text(patched,encoding="utf8")
    print("DRNAS_INPROCESS_PATCH_APPLIED",source,
          "original_sha256",hashlib.sha256(original.encode()).hexdigest(),
          "patched_sha256",hashlib.sha256(patched.encode()).hexdigest(),
          "pinned",PINNED,flush=True)

if __name__=="__main__":
    main()
