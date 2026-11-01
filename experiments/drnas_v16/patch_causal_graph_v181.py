#!/usr/bin/env python3
"""DRNAS SAT V18.1: causal Kissat instrumentation and prespecified restart variants.

Patch ONLY a pinned upstream Kissat search.c. One in-process parameter change
without resetting learned clauses; instrument trace snapshots and mode changes.
No threshold is fitted to the holdout; gate thresholds are exploratory priors
from V17.7 and retrospectively viewed V18.0.
"""
from pathlib import Path
import argparse, hashlib

PINNED = "8af8e56f174b778aef3aa45af9f739b2a5f492c2"

def patch(src: str) -> str:
    if "DRNAS_V181" in src or "V181_TICK" in src:
        raise ValueError("Already instrumented")
    def once(a,b):
        nonlocal src
        if src.count(a) != 1:
            raise ValueError(f"Unexpected pinned Kissat layout {a[:65]}: {src.count(a)}")
        src = src.replace(a,b,1)
    once("#include <inttypes.h>\n",
         "#include <inttypes.h>\n#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n#include <time.h>\n\nextern void kissat_drnas_v181_cut_snapshot(uint64_t out[6]);\n")
    once("int kissat_search (kissat *solver) {\n  REPORT (0, '*');",
r'''int kissat_search (kissat *solver) {
  // V18.1: observe all policies at the same conflict milestones.
  // Mode 'plain' leaves the environment unset (no trace).  'trace' has no intervention.
  const char *drnas_mode = getenv("DRNAS_V181_MODE");
  if (!drnas_mode) drnas_mode = "";
  const bool drnas_active = *drnas_mode != 0;
  uint64_t drnas_target = 0, drnas_start = 0, drnas_begin_restarts = 0;
  int drnas_interval = 25;
  bool drnas_started = false, drnas_sampled = false, drnas_switched = false;
  bool drnas_gate_restarts = false, drnas_gate_glue = false;
  uint64_t drnas_focused_restarts=0, drnas_stable_restarts=0;
  uint64_t drnas_focused_conflicts=0, drnas_stable_conflicts=0;
  uint64_t drnas_focused_modes=0, drnas_stable_modes=0;
  unsigned drnas_next_mark = 0;
  const uint64_t drnas_marks[] = {256,512,1024,2048,4096,8192,16384,
                                  32768,65536,131072,262144,524288,1048576};
  const unsigned drnas_nmarks = sizeof(drnas_marks)/sizeof(drnas_marks[0]);
  if (!strcmp(drnas_mode,"trace") || !*drnas_mode) {
    // No modification.
  } else if (!strcmp(drnas_mode,"switch512_i25"))
    drnas_target = 512;
  else if (!strcmp(drnas_mode,"switch1024_i25"))
    drnas_target = 1024;
  else if (!strcmp(drnas_mode,"switch2048_i10")) {
    drnas_target = 2048; drnas_interval = 10;
  } else if (!strcmp(drnas_mode,"switch2048_i25"))
    drnas_target = 2048;
  else if (!strcmp(drnas_mode,"switch2048_i50")) {
    drnas_target = 2048; drnas_interval = 50;
  } else if (!strcmp(drnas_mode,"switch4096_i25"))
    drnas_target = 4096;
  else if (!strcmp(drnas_mode,"gate_r30_2048_i25"))
    drnas_gate_restarts = true;
  else if (!strcmp(drnas_mode,"gate_g0869_1024_i25"))
    drnas_gate_glue = true;
  else {
    fprintf(stderr, "V181_UNKNOWN_MODE %s\n", drnas_mode); exit(76);
  }
  REPORT (0, '*');''')
    once("    start_search (solver);\n    while (!res) {",
r'''    start_search (solver);
    if (drnas_active && !drnas_started) {
      drnas_start = CONFLICTS;
      drnas_begin_restarts = solver->statistics.restarts;
      drnas_started = true;
      if (solver->stable) drnas_stable_modes++;
      else drnas_focused_modes++;
    }
    while (!res) {''')
    once("      if (conflict)\n        res = kissat_analyze (solver, conflict);\n      else if (solver->iterating)",
r'''      if (conflict) {
        res = kissat_analyze (solver, conflict);
        if (drnas_active && drnas_started && !res) {
          if (solver->stable) drnas_stable_conflicts++;
          else drnas_focused_conflicts++;
          const uint64_t drnas_seen = CONFLICTS - drnas_start;
          const uint64_t drnas_restarts =
            solver->statistics.restarts - drnas_begin_restarts;
          if ((drnas_next_mark < drnas_nmarks &&
               drnas_seen>=drnas_marks[drnas_next_mark]) ||
              (!drnas_sampled && drnas_seen>=512) ||
              (!drnas_switched && drnas_target &&
               drnas_seen>=drnas_target)) {
          const double drnas_fast = AVERAGE(fast_glue);
          const double drnas_slow = AVERAGE(slow_glue);
          const double drnas_ratio =
            drnas_fast/(drnas_slow>1e-9 ? drnas_slow : 1e-9);
          uint64_t drnas_cut[6]={0};
          kissat_drnas_v181_cut_snapshot(drnas_cut);
          while (drnas_next_mark < drnas_nmarks &&
                 drnas_seen >= drnas_marks[drnas_next_mark]) {
            fprintf(stdout,
              "c V181_TICK policy=%s at=%" PRIu64
              " conflicts=%" PRIu64 " restarts=%" PRIu64
              " focused_restarts=%" PRIu64 " stable_restarts=%" PRIu64
              " decisions=%" PRIu64 " propagations=%" PRIu64
              " learned=%" PRIu64 " glue_fast=%.9f glue_slow=%.9f"
              " ratio=%.9f stable=%d focused_modes=%" PRIu64
              " stable_modes=%" PRIu64 " reductions=%" PRIu64
              " rephased=%" PRIu64 " elapsed_cpu_ms=%.3f"
              " focused_conflicts=%" PRIu64
              " stable_conflicts=%" PRIu64
              " cut_n=%" PRIu64 " cut_size=%" PRIu64
              " cut_glue=%" PRIu64 " cut_span=%" PRIu64
              " cut_low=%" PRIu64 " cut_short=%" PRIu64
              " interval=%d\n",
              drnas_mode, drnas_marks[drnas_next_mark],
              drnas_seen, drnas_restarts,
              drnas_focused_restarts,
              drnas_stable_restarts,
              DECISIONS, solver->statistics.propagations,
              solver->statistics.clauses_learned,
              drnas_fast, drnas_slow, drnas_ratio,
              (int)solver->stable, drnas_focused_modes,
              drnas_stable_modes,
              GET(reductions),
              GET(rephased),
              1000.0 * (double)clock() / (double)CLOCKS_PER_SEC,
              drnas_focused_conflicts,drnas_stable_conflicts,
              drnas_cut[0],drnas_cut[1],drnas_cut[2],
              drnas_cut[3],drnas_cut[4],drnas_cut[5],
              GET_OPTION(restartint));
            drnas_next_mark++;
          }
          if (!drnas_sampled && drnas_seen>=512) {
            drnas_sampled = true;
            if (drnas_gate_restarts && drnas_restarts<=30)
              drnas_target=2048;
            if (drnas_gate_glue && drnas_ratio<0.8692513215)
              drnas_target=1024;
            fprintf(stdout,
              "c V181_GATE policy=%s at=%" PRIu64
              " early_restarts=%" PRIu64 " early_glue=%.9f"
              " selected_target=%" PRIu64 "\n",
              drnas_mode,drnas_seen,drnas_restarts,
              drnas_ratio,drnas_target);
          }
          if (!drnas_switched && drnas_target &&
              drnas_seen>=drnas_target) {
            const uint64_t before = solver->statistics.clauses_learned;
            const int previous = GET_OPTION(restartint);
            const int stable = (int)solver->stable;
            kissat_set_option(solver, "restartint", drnas_interval);
            if (!solver->stable)
              kissat_update_focused_restart_limit(solver);
            const uint64_t after = solver->statistics.clauses_learned;
            fprintf(stdout,
              "c V181_SWITCH policy=%s at=%" PRIu64
              " restart_before=%d restart_after=%d"
              " stable=%d learned_before=%" PRIu64
              " learned_after=%" PRIu64 " restarts=%" PRIu64 "\n",
              drnas_mode,drnas_seen,previous,
              GET_OPTION(restartint),stable,before,after,drnas_restarts);
            drnas_switched = true;
          }
          fflush(stdout);
          }
        }
      } else if (solver->iterating)''')
    once("      else if (kissat_switching_search_mode (solver))\n        kissat_switch_search_mode (solver);",
r'''      else if (kissat_switching_search_mode (solver)) {
        const int previous = (int)solver->stable;
        kissat_switch_search_mode (solver);
        if (drnas_active) {
          if (solver->stable) drnas_stable_modes++;
          else drnas_focused_modes++;
          fprintf(stdout,
            "c V181_SEARCH_MODE policy=%s conflicts=%" PRIu64
            " from_stable=%d to_stable=%d restarts=%" PRIu64 "\n",
            drnas_mode, CONFLICTS, previous, (int)solver->stable,
            solver->statistics.restarts);
          fflush(stdout);
        }
      }''')
    once("      else if (kissat_restarting (solver))\n        kissat_restart (solver);",
r'''      else if (kissat_restarting (solver)) {
        if (drnas_active) {
          if (solver->stable) drnas_stable_restarts++;
          else drnas_focused_restarts++;
        }
        kissat_restart (solver);
      }''')
    once("    stop_search (solver);\n  }\n  report_search_result (solver, res);",
r'''    stop_search (solver);
    if (drnas_active) {
      fprintf(stdout,
        "c V181_FINAL policy=%s status=%d conflicts=%" PRIu64
        " restarts=%" PRIu64 " decisions=%" PRIu64
        " propagations=%" PRIu64 " learned=%" PRIu64
        " reductions=%" PRIu64 " focused_restarts=%" PRIu64
        " stable_restarts=%" PRIu64 " switched=%d"
        " interval=%d\n",
        drnas_mode,res,CONFLICTS,solver->statistics.restarts,
        DECISIONS,solver->statistics.propagations,
        solver->statistics.clauses_learned,GET(reductions),
        drnas_focused_restarts,
        drnas_stable_restarts,
        (int)drnas_switched,GET_OPTION(restartint));
      fflush(stdout);
    }
  }
  report_search_result (solver, res);''')
    return src

def patch_learn(src):
    """Instrument learning's 1-UIP clause interface, a conflict-graph cut boundary.

    A learned clause is a 1-UIP cut in the implication graph. We track its size,
    LBD, and backjump span (decision levels). These are *cut proxies*, not
    structural graph minimum cuts; exact reason-edge counts remain unmeasured.
    """
    if "kissat_drnas_v181_cut_snapshot" in src:
        raise ValueError("Already instrumented learn.c")
    def once(a,b):
        nonlocal src
        if src.count(a) != 1:
            raise ValueError(f"learn.c changed near {a[:75]} {src.count(a)}")
        src=src.replace(a,b,1)
    once("#include <inttypes.h>\n",
r'''#include <inttypes.h>
#include <stdlib.h>
static uint64_t v181_cut_n=0, v181_cut_size=0, v181_cut_glue=0;
static uint64_t v181_cut_span=0, v181_cut_low=0, v181_cut_short=0;
void kissat_drnas_v181_cut_snapshot(uint64_t out[6]) {
  out[0]=v181_cut_n;out[1]=v181_cut_size;out[2]=v181_cut_glue;
  out[3]=v181_cut_span;out[4]=v181_cut_low;out[5]=v181_cut_short;
}
''')
    once("  if (!solver->probing)\n    kissat_update_learned (solver, glue, size);",
r'''  // All policies share exactly the same 1-UIP analysis implementation.
  // Sum measurements across learned clauses to expose cut-size and jump changes.
  static int drnas_enabled=-1;
  if (drnas_enabled<0) {
    const char *mode=getenv("DRNAS_V181_MODE");
    drnas_enabled=mode && *mode ? 1:0;
  }
  if (drnas_enabled && !solver->probing) {
    unsigned max_reason_level=0;
    for (all_stack(unsigned,lit,solver->clause)) {
      if (lit==not_uip)continue;
      const unsigned level=LEVEL(lit);
      if (level>max_reason_level)max_reason_level=level;
    }
    const unsigned span=solver->level>max_reason_level ?
                        solver->level-max_reason_level:0;
    v181_cut_n++;v181_cut_size+=size;v181_cut_glue+=(unsigned)glue;
    v181_cut_span+=span;
    if (glue<=2)v181_cut_low++;
    if (size<=2)v181_cut_short++;
  }
  if (!solver->probing)
    kissat_update_learned (solver, glue, size);''')
    return src

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--kissat-root",type=Path,required=True)
    args=p.parse_args()
    target=args.kissat_root/"src"/"search.c"
    original=target.read_text()
    patched=patch(original)
    other=args.kissat_root/"src"/"learn.c"
    learned=patch_learn(other.read_text())
    target.write_text(patched)
    other.write_text(learned)
    print("V181_PINNED_PATCH_PASS",PINNED,
          hashlib.sha256(patched.encode()).hexdigest(),
          hashlib.sha256(learned.encode()).hexdigest(),flush=True)

if __name__=="__main__":main()
