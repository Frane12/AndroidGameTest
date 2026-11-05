#!/usr/bin/env python3
"""Exact-pin Kissat 4.0.4 live-telemetry guard. No solver reconstruction."""
from pathlib import Path
import argparse,hashlib

PINNED="8af8e56f174b778aef3aa45af9f739b2a5f492c2"

def once(src, old, new, desc):
    if src.count(old)!=1:
        raise RuntimeError(f"Unexpected upstream layout {desc}: {src.count(old)}")
    return src.replace(old,new,1)

def patch(src):
    if "DRNAS_LIVE" in src: raise RuntimeError("already patched")
    src=once(src,"#include <inttypes.h>\n",
       "#include <inttypes.h>\n#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n","headers")
    src=once(src,"int kissat_search (kissat *solver) {\n  REPORT (0, '*');",
"""int kissat_search (kissat *solver) {
  const char *drnas_env = getenv ("DRNAS_LIVE_MODE");
  const bool drnas_observe = drnas_env && !strcmp (drnas_env, "observe");
  const bool drnas_adapt = drnas_env && !strcmp (drnas_env, "adapt");
  const bool drnas_enabled = drnas_observe || drnas_adapt;
  uint64_t drnas_start_conflicts = 0, drnas_start_props = 0;
  uint64_t drnas_start_decisions = 0;
  uint64_t drnas_props_1024 = 0, drnas_decisions_1024 = 0;
  int drnas_stage = 0;
  REPORT (0, '*');""","entry")
    src=once(src,"    start_search (solver);\n    while (!res) {",
"""    start_search (solver);
    if (drnas_enabled) {
      drnas_start_conflicts = CONFLICTS;
      drnas_start_props = solver->statistics.propagations;
      drnas_start_decisions = DECISIONS;
    }
    while (!res) {""","search begin")
    src=once(src,
"""      if (conflict)
        res = kissat_analyze (solver, conflict);
      else if (solver->iterating)""",
"""      if (conflict) {
        res = kissat_analyze (solver, conflict);
        if (!res && drnas_enabled) {
          const uint64_t seen = CONFLICTS - drnas_start_conflicts;
          if (drnas_stage == 0 && seen >= 1024) {
            drnas_props_1024 = solver->statistics.propagations;
            drnas_decisions_1024 = DECISIONS;
            drnas_stage = 1;
          }
          if (drnas_stage == 1 && seen >= 4096) {
            const double early_prop =
              (double)(drnas_props_1024 - drnas_start_props) / 1024.0;
            const double late_prop =
              (double)(solver->statistics.propagations - drnas_props_1024) /
              (double)(seen - 1024);
            const double early_dec =
              (double)(drnas_decisions_1024 - drnas_start_decisions) / 1024.0;
            const double late_dec =
              (double)(DECISIONS - drnas_decisions_1024) /
              (double)(seen - 1024);
            const int before = GET_OPTION (restartint);
            // Frozen before 172xxx holdout: require both deteriorating signals.
            const bool stagnant =
              early_prop > 0 && late_prop <= 0.75 * early_prop &&
              late_dec >= 1.05 * early_dec;
            const bool change = drnas_adapt && stagnant && before != 50;
            const uint64_t learned_before = solver->statistics.clauses_learned;
            if (change) {
              kissat_set_option (solver, "restartint", 50);
              if (!solver->stable)
                kissat_update_focused_restart_limit (solver);
            }
            fprintf (stdout,
              "c DRNAS_LIVE seen=%" PRIu64
              " early_prop=%.6f late_prop=%.6f"
              " early_dec=%.6f late_dec=%.6f"
              " stagnant=%d changed=%d"
              " restart_before=%d restart_after=%d"
              " learned_before=%" PRIu64 " learned_after=%" PRIu64 "\\n",
              seen, early_prop, late_prop, early_dec, late_dec,
              stagnant, change, before, GET_OPTION (restartint),
              learned_before, solver->statistics.clauses_learned);
            fflush (stdout);
            drnas_stage = 2;
          }
        }
      } else if (solver->iterating)""","analysis")
    return src

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--kissat-root",required=True,type=Path)
    a=p.parse_args()
    path=a.kissat_root/"src"/"search.c"
    before=path.read_text()
    after=patch(before)
    path.write_text(after)
    print("V172_PINNED_PATCH_PASS", PINNED,hashlib.sha256(before.encode()).hexdigest(),
          hashlib.sha256(after.encode()).hexdigest(),flush=True)

if __name__=="__main__": main()
