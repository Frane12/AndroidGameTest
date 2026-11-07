#!/usr/bin/env python3
"""Add one-process, read-only early-CDCL trace to native R32k Kissat.

Apply only AFTER patch_r32b_native_shadow.py and patch_r32k_causal_ablation.py.
No restart, watchdog, parallel process, phase change, clause-ordering change,
learning control or decision-control edits. Samples before first conflict,
after learning, and at frozen decision/conflict checkpoints.
"""
import argparse
from pathlib import Path

def once(s,needle,replacement,name):
    count=s.count(needle)
    if count!=1:
        raise RuntimeError(f"R32L_TRACE_ANCHOR_ERROR {name} count={count}")
    return s.replace(needle,replacement,1)

TRACE=r'''// R32l: read-only EARLY CDCL causal instrumentation, no policy changes.
static int r32l_trace_enabled=-1;
static uint64_t r32l_base_conflicts=0,r32l_base_decisions=0;
static unsigned r32l_conf_next=0,r32l_dec_next=0,r32l_first=0;
static const unsigned r32l_marks[4]={1,4,16,64};
static int r32l_on(void) {
  if (r32l_trace_enabled < 0) {
    const char *flag=getenv("R32L_TRACE");
    r32l_trace_enabled=flag && !strcmp(flag,"1");
  }
  return r32l_trace_enabled;
}
static void r32l_event(kissat *solver,const char *kind,unsigned mark) {
  if(!r32l_on())return;
  printf("c R32L_CDCL event=%s mark=%u conflicts=%" PRIu64
         " decisions=%" PRIu64 " propagations=%" PRIu64
         " learned=%" PRIu64 " restarts=%" PRIu64
         " level=%u trail=%zu unassigned=%u\n",
         kind,mark,solver->statistics.conflicts,
         solver->statistics.decisions,
         solver->statistics.propagations,
         solver->statistics.clauses_learned,
         solver->statistics.restarts,
         solver->level,SIZE_ARRAY(solver->trail),solver->unassigned);
  fflush(stdout);
}
static void r32l_reset(kissat *solver) {
  if(!r32l_on())return;
  r32l_base_conflicts=solver->statistics.conflicts;
  r32l_base_decisions=solver->statistics.decisions;
  r32l_conf_next=r32l_dec_next=r32l_first=0;
  r32l_event(solver,"search_start",0);
}
static void r32l_before_conflict(kissat *solver) {
  if(!r32l_on() || r32l_first)return;
  r32l_first=1;
  r32l_event(solver,"first_conflict_before_analysis",1);
}
static void r32l_after_conflict(kissat *solver) {
  if(!r32l_on())return;
  if(r32l_first==1) {
    r32l_first=2;
    r32l_event(solver,"first_conflict_after_analysis",1);
  }
  const uint64_t count=solver->statistics.conflicts-r32l_base_conflicts;
  while(r32l_conf_next<4 && count>=r32l_marks[r32l_conf_next]) {
    r32l_event(solver,"conflict_mark",r32l_marks[r32l_conf_next]);
    ++r32l_conf_next;
  }
}
static void r32l_after_decision(kissat *solver) {
  if(!r32l_on())return;
  const uint64_t count=solver->statistics.decisions-r32l_base_decisions;
  while(r32l_dec_next<4 && count>=r32l_marks[r32l_dec_next]) {
    r32l_event(solver,"decision_mark",r32l_marks[r32l_dec_next]);
    ++r32l_dec_next;
  }
}
'''
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--kissat-root",type=Path,required=True)
    args=ap.parse_args()
    file=args.kissat_root/"src"/"search.c"
    s=file.read_text()
    s=once(s,"int kissat_search (kissat *solver) {",
           TRACE+"\nint kissat_search (kissat *solver) {",
           "inject_trace_functions")
    s=once(s,"int kissat_search (kissat *solver) {\n  // Even easy CNFs solved by preprocessing receive a root-only audit.",
       'int kissat_search (kissat *solver) {\n  r32l_event(solver,"pre_preprocess",0);\n  // Even easy CNFs solved by preprocessing receive a root-only audit.',
       "search_entrance")
    s=once(s,"  if (!res && searching (solver)) {\n    start_search (solver);",
       '  if (!res && searching (solver)) {\n    start_search (solver);\n    r32l_reset(solver);',
       "start_search")
    s=once(s,"      if (conflict)\n        res = kissat_analyze (solver, conflict);",
       '''      if (conflict) {
        r32l_before_conflict (solver);
        res = kissat_analyze (solver, conflict);
        r32l_after_conflict (solver);
      }''',
       "first_conflict_analysis")
    s=once(s,"      else\n        kissat_decide (solver);",
       '''      else {
        kissat_decide (solver);
        r32l_after_decision (solver);
      }''',
       "early_decision")
    s=once(s,"  report_search_result (solver, res);\n  printf(\"c R32B_FINAL",
       '  r32l_event(solver,"final",0);\n  report_search_result (solver, res);\n  printf("c R32B_FINAL',
       "final_telemetry")
    file.write_text(s)
    print("R32L_SINGLE_SOLVER_EARLY_CDCL_PATCH_OK",flush=True)

if __name__=="__main__":
    main()
