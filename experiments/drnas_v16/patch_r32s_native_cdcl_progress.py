#!/usr/bin/env python3
"""Read-only long-horizon CDCL progress tracing inside ONE pinned Kissat.

Apply after patch_r32b_native_shadow.py and patch_r32n_leave_one_out.py.
Never modifies clause databases, heuristics, restarts, assumptions or policy.
Flush early/preprocessing milestones and conflict-count marks so that even
120-second timeout attempts have interpretable partial solver progress.
"""
import argparse
from pathlib import Path

def change(s,old,new,label):
    n=s.count(old)
    if n!=1:raise RuntimeError(f"R32S_PATCH_ANCHOR {label}: count {n}")
    return s.replace(old,new,1)

HELPERS=r'''// DRNAS R32s: read-only progress trace; one native Kissat only.
#include <time.h>
static int r32s_enabled=-1;
static unsigned r32s_next_mark;
static double r32s_epoch;
static int r32s_on(void) {
  if(r32s_enabled<0) {
    const char *env=getenv("R32S_PASSIVE_TRACE");
    r32s_enabled=env && !strcmp(env,"1");
  }
  return r32s_enabled;
}
static double r32s_now_ms(void) {
  return (double)clock() * (1000.0 / CLOCKS_PER_SEC);
}
static void r32s_emit(kissat *solver,const char *event,unsigned mark) {
  if(!r32s_on())return;
  printf("c R32S_TRACE event=%s mark=%u cpu_ms=%.3f conflicts=%" PRIu64
         " decisions=%" PRIu64 " propagations=%" PRIu64
         " restarts=%" PRIu64 " learned=%" PRIu64 " trail=%zu\n",
         event,mark,r32s_now_ms()-r32s_epoch,
         solver->statistics.conflicts,solver->statistics.decisions,
         solver->statistics.propagations,solver->statistics.restarts,
         solver->statistics.clauses_learned,SIZE_ARRAY(solver->trail));
  fflush(stdout);
}
static void r32s_tick(kissat *solver) {
  if(!r32s_on())return;
  static const uint64_t marks[] = {1,10,100,1000,10000,100000,1000000,
                                   10000000,100000000};
  while(r32s_next_mark<9 &&
        solver->statistics.conflicts>=marks[r32s_next_mark]) {
    r32s_emit(solver,"conflict_milestone",
              (unsigned)marks[r32s_next_mark]);
    ++r32s_next_mark;
  }
}
'''
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--kissat-root",type=Path,required=True)
    a=p.parse_args()
    path=a.kissat_root/"src"/"search.c"
    s=path.read_text()
    s=change(s,"int kissat_search (kissat *solver) {",
        HELPERS+"\nint kissat_search (kissat *solver) {","insert_helpers")
    s=change(s,
        "  // Even easy CNFs solved by preprocessing receive a root-only audit.\n"
        "  r32b_shadow_native_probe(NULL,0,9999);\n"
        "  REPORT (0, '*');",
        "  // Even easy CNFs solved by preprocessing receive a root-only audit.\n"
        "  r32b_shadow_native_probe(NULL,0,9999);\n"
        "  if(r32s_on()) { r32s_next_mark=0; r32s_epoch=r32s_now_ms(); }\n"
        "  r32s_emit(solver,\"entry\",0);\n"
        "  REPORT (0, '*');",
        "mark_entry")
    s=change(s,
        "  if (!res && GET_OPTION (luckyearly))\n"
        "    res = kissat_lucky (solver);\n"
        "  if (!res && kissat_preprocessing (solver))\n"
        "    res = kissat_preprocess (solver);\n"
        "  if (!res && GET_OPTION (luckylate))\n"
        "    res = kissat_lucky (solver);",
        "  if (!res && GET_OPTION (luckyearly)) {\n"
        "    r32s_emit(solver,\"lucky_early_start\",0);\n"
        "    res = kissat_lucky (solver);\n"
        "    r32s_emit(solver,\"lucky_early_end\",0);\n"
        "  }\n"
        "  if (!res && kissat_preprocessing (solver)) {\n"
        "    r32s_emit(solver,\"preprocess_start\",0);\n"
        "    res = kissat_preprocess (solver);\n"
        "    r32s_emit(solver,\"preprocess_end\",0);\n"
        "  }\n"
        "  if (!res && GET_OPTION (luckylate)) {\n"
        "    r32s_emit(solver,\"lucky_late_start\",0);\n"
        "    res = kissat_lucky (solver);\n"
        "    r32s_emit(solver,\"lucky_late_end\",0);\n"
        "  }",
        "observe_preprocessing")
    s=change(s,
        "  if (!res && searching (solver)) {\n"
        "    start_search (solver);",
        "  if (!res && searching (solver)) {\n"
        "    start_search (solver);\n"
        "    r32s_emit(solver,\"cdcl_start\",0);",
        "mark_cdcl_start")
    s=change(s,
        "      if (conflict)\n"
        "        res = kissat_analyze (solver, conflict);",
        "      if (conflict) {\n"
        "        res = kissat_analyze (solver, conflict);\n"
        "        r32s_tick(solver);\n"
        "      }",
        "mark_analyzed_conflicts")
    s=change(s,
        "  report_search_result (solver, res);\n"
        "  printf(\"c R32B_FINAL status=",
        "  r32s_emit(solver,\"finished\",0);\n"
        "  report_search_result (solver, res);\n"
        "  printf(\"c R32B_FINAL status=",
        "mark_finish")
    path.write_text(s)
    print("R32S_READ_ONLY_NATIVE_CDCL_TRACE_PATCH_OK",flush=True)

if __name__=="__main__":main()
