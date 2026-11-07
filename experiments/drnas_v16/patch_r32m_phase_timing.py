#!/usr/bin/env python3
"""R32m: native phase-local CPU timing, one Kissat only, no policy alteration.

Apply after R32b original-source capture, R32k certified GF2 unit variants,
and R32l early-CDCL read-only instrumentation to the pinned Kissat SHA.
All Kissat control-flow branches are unchanged; each original branch body
executes only when it did before. CPU phase times are independent of external
Python subprocess wall time and must not be conflated with parse/injection.
"""
from pathlib import Path
import argparse

def once(s,old,new,name):
    count=s.count(old)
    if count!=1:
        raise RuntimeError(f"R32M_PATCH_ANCHOR {name} count={count}")
    return s.replace(old,new,1)

HELPERS=r'''// R32m: read-only solver-internal CPU clock per phase. No solver mutations.
#include <time.h>
static int r32m_trace_enabled=-1;
static int r32m_enabled(void) {
  if (r32m_trace_enabled<0) {
    const char *env=getenv("R32M_PHASES");
    r32m_trace_enabled=env && !strcmp(env,"1");
  }
  return r32m_trace_enabled;
}
static double r32m_cpu_us(void) {
  return (double)clock() * (1000000.0 / CLOCKS_PER_SEC);
}
typedef struct {
  double us;
  uint64_t conflicts,decisions,propagations,learned;
} r32m_phase_start;
static r32m_phase_start r32m_start(kissat *solver) {
  r32m_phase_start q;
  q.us=r32m_enabled()?r32m_cpu_us():0;
  q.conflicts=solver->statistics.conflicts;
  q.decisions=solver->statistics.decisions;
  q.propagations=solver->statistics.propagations;
  q.learned=solver->statistics.clauses_learned;
  return q;
}
static void r32m_end(kissat *solver,const char *phase,int ran,int res,
                      r32m_phase_start q) {
  if(!r32m_enabled())return;
  const double elapsed=ran?r32m_cpu_us()-q.us:0;
  printf("c R32M_PHASE phase=%s ran=%d result=%d cpu_us=%.0f"
         " conflict_delta=%" PRIu64 " decision_delta=%" PRIu64
         " propagation_delta=%" PRIu64 " learned_delta=%" PRIu64
         " trail=%zu unassigned=%u\n",phase,ran,res,elapsed,
         solver->statistics.conflicts-q.conflicts,
         solver->statistics.decisions-q.decisions,
         solver->statistics.propagations-q.propagations,
         solver->statistics.clauses_learned-q.learned,
         SIZE_ARRAY(solver->trail),solver->unassigned);
  fflush(stdout);
}
'''
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--kissat-root",type=Path,required=True)
    args=ap.parse_args()
    path=args.kissat_root/"src"/"search.c"
    s=path.read_text()
    s=once(s, "int kissat_search (kissat *solver) {", HELPERS+"\nint kissat_search (kissat *solver) {","helper_definition")
    s=once(s,
'''  if (solver->inconsistent)
    res = 20;
  if (!res && GET_OPTION (luckyearly))
    res = kissat_lucky (solver);
  if (!res && kissat_preprocessing (solver))
    res = kissat_preprocess (solver);
  if (!res && GET_OPTION (luckylate))
    res = kissat_lucky (solver);
  if (!res)
    kissat_classify (solver);
  if (!res && searching (solver)) {
    start_search (solver);
    r32l_reset(solver);''',
'''  if (solver->inconsistent)
    res = 20;
  {
    const int ran = !res && GET_OPTION (luckyearly);
    const r32m_phase_start p = r32m_start(solver);
    if (ran) res = kissat_lucky (solver);
    r32m_end(solver,"lucky_early",ran,res,p);
  }
  {
    const int ran = !res && kissat_preprocessing (solver);
    const r32m_phase_start p = r32m_start(solver);
    if (ran) res = kissat_preprocess (solver);
    r32m_end(solver,"preprocess",ran,res,p);
  }
  {
    const int ran = !res && GET_OPTION (luckylate);
    const r32m_phase_start p = r32m_start(solver);
    if (ran) res = kissat_lucky (solver);
    r32m_end(solver,"lucky_late",ran,res,p);
  }
  {
    const int ran = !res;
    const r32m_phase_start p = r32m_start(solver);
    if (ran) kissat_classify (solver);
    r32m_end(solver,"classify",ran,res,p);
  }
  {
  const int ran = !res && searching (solver);
  const r32m_phase_start cdcl_start=r32m_start(solver);
  if (ran) {
    start_search (solver);
    r32l_reset(solver);''',
    "wrap_all_search_phases")
    s=once(s,
'''    stop_search (solver);
  }
  r32l_event(solver,"final",0);''',
'''    stop_search (solver);
  }
  r32m_end(solver,"cdcl",ran,res,cdcl_start);
  }
  r32l_event(solver,"final",0);''',
"cdcl_end")
    path.write_text(s)
    print("R32M_SINGLE_SOLVER_PHASE_TIMING_PATCH_OK",flush=True)

if __name__=="__main__":
    main()
