#!/usr/bin/env python3
"""DRNAS V18.2: lightweight in-process safety monitor for pinned Kissat.

256-conflict sampling. No external solver or second SAT search. Decisions:
after THREE consecutive degraded windows restore original restartint=1.
The 0.5% CPU budget is an instrumented target, not a guarantee about whole
executable overhead. A matching patched-monitor and unmodified upstream
control permit independent end-to-end benchmarking.
"""
from pathlib import Path
import argparse, hashlib
PINNED="8af8e56f174b778aef3aa45af9f739b2a5f492c2"

def patch(src:str)->str:
    if "DRNAS_V182" in src: raise ValueError("Already patched")
    def once(a,b):
        nonlocal src
        n=src.count(a)
        if n!=1: raise ValueError(f"Expected exactly 1 anchor, got {n}: {a[:70]}")
        src=src.replace(a,b,1)
    once("#include <inttypes.h>\n",
r'''#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define DRNAS_V182_WINDOW 256u
#define DRNAS_V182_RECORD_CAP 64u
typedef struct {
  uint64_t conflict, cpu_ns, restarts, focused_restarts, learned;
  uint64_t propagations, decisions;
  double lbd_ratio, window_cost_ns, prop_per_conflict;
  unsigned bad_streak;
  int stable, interval;
} drnas_v182_record;

static uint64_t drnas_v182_cpu_ns(void) {
  struct timespec t;
  if (clock_gettime(CLOCK_PROCESS_CPUTIME_ID, &t))
    return 0;
  return ((uint64_t)t.tv_sec)*1000000000ull+(uint64_t)t.tv_nsec;
}
''')
    once("int kissat_search (kissat *solver) {\n  REPORT (0, '*');",
r'''int kissat_search (kissat *solver) {
  const char *drnas_v182_mode=getenv("DRNAS_V182_MODE");
  if (!drnas_v182_mode) drnas_v182_mode="";
  const bool v182_on=*drnas_v182_mode!=0;
  const bool v182_gate=!strcmp(drnas_v182_mode,"gate_no_guard") ||
                       !strcmp(drnas_v182_mode,"adaptive_gate");
  const bool v182_guard=!strcmp(drnas_v182_mode,"adaptive_gate") ||
                        !strcmp(drnas_v182_mode,"adaptive_force");
  uint64_t v182_switch_at=0, v182_start_conflict=0, v182_start_cpu=0;
  uint64_t v182_last_cpu=0, v182_monitor_ns=0, v182_focused_restarts=0;
  uint64_t v182_focus_at_switch=0;
  uint64_t v182_prev_props=0, v182_next_sample=DRNAS_V182_WINDOW;
  uint64_t v182_samples=0, v182_last_conflict=0, v182_switch_conflict=0;
  uint64_t v182_fallback_conflict=0, v182_budget_conflict=0;
  double v182_base_cost=0, v182_base_glue=0, v182_base_prop=0;
  double v182_glue512=0;
  unsigned v182_base_count=0, v182_bad_streak=0, v182_fallbacks=0;
  unsigned v182_nrecords=0;
  bool v182_switched=false, v182_budget_aborted=false;
  bool v182_active_search=false, v182_gated=false;
  int v182_interval=25;
  drnas_v182_record v182_records[DRNAS_V182_RECORD_CAP];
  if (v182_on) {
    if (!strcmp(drnas_v182_mode,"monitor")) {
      // Pure monitor: no solver option changes.
    } else if (!strcmp(drnas_v182_mode,"fixed10"))
      {v182_switch_at=2048;v182_interval=10;}
    else if (!strcmp(drnas_v182_mode,"fixed25"))
      {v182_switch_at=2048;v182_interval=25;}
    else if (!strcmp(drnas_v182_mode,"fixed50"))
      {v182_switch_at=2048;v182_interval=50;}
    else if (!strcmp(drnas_v182_mode,"adaptive_force"))
      {v182_switch_at=2048;}
    else if (v182_gate) {
      // Delayed decision at conflict 512.
    } else {
      fprintf(stderr,"V182_UNKNOWN_POLICY %s\n",drnas_v182_mode);
      exit(77);
    }
  }
  REPORT (0, '*');''')
    once("    start_search (solver);\n    while (!res) {",
r'''    start_search (solver);
    if (v182_on) {
      v182_active_search=true;
      v182_start_conflict=CONFLICTS;
      v182_start_cpu=drnas_v182_cpu_ns();
      v182_last_cpu=v182_start_cpu;
      v182_prev_props=solver->statistics.propagations;
    }
    while (!res) {''')
    once("      if (conflict)\n        res = kissat_analyze (solver, conflict);\n      else if (solver->iterating)",
r'''      if (conflict) {
        res=kissat_analyze(solver,conflict);
        // One cheap branch per conflict; heavy metrics only every 256 conflicts.
        if (v182_on && v182_active_search && !res &&
            !v182_budget_aborted &&
            CONFLICTS-v182_start_conflict>=v182_next_sample) {
          const uint64_t t0=drnas_v182_cpu_ns();
          const uint64_t seen=CONFLICTS-v182_start_conflict;
          const uint64_t dt=(t0>=v182_last_cpu)?t0-v182_last_cpu:0;
          const uint64_t dc=seen-v182_last_conflict;
          const uint64_t delta_props=
            solver->statistics.propagations-v182_prev_props;
          const double window_cost=(double)dt/(double)(dc?dc:1);
          const double window_props=(double)delta_props/(double)(dc?dc:1);
          const double f=AVERAGE(fast_glue);
          const double s=AVERAGE(slow_glue);
          const double glue=f/(s>1e-9?s:1e-9);
          v182_samples++;
          if (seen<=1024) {
            v182_base_cost+=window_cost;
            v182_base_prop+=window_props;
            v182_base_glue+=glue;
            v182_base_count++;
          }
          if (seen>=512 && !v182_gated) {
            v182_glue512=glue;
            v182_gated=true;
            if (v182_gate && glue<0.8692513215)
              v182_switch_at=1024;
          }
          // Forced intervention is purely a parameter change in this process.
          if (!v182_switched && v182_switch_at &&
              seen>=v182_switch_at) {
            kissat_set_option(solver,"restartint",v182_interval);
            if (!solver->stable)
              kissat_update_focused_restart_limit(solver);
            v182_switched=true;
            v182_switch_conflict=seen;
            v182_focus_at_switch=v182_focused_restarts;
          } else if (v182_switched && v182_guard &&
                     !v182_fallbacks && seen>v182_switch_conflict &&
                     v182_base_count>=4 &&
                     v182_focused_restarts>v182_focus_at_switch) {
            const double base_cost=v182_base_cost/(double)v182_base_count;
            const double base_prop=v182_base_prop/(double)v182_base_count;
            const double base_glue=v182_base_glue/(double)v182_base_count;
            const bool cost_bad=window_cost>1.30*base_cost;
            const bool learning_bad=glue>1.05*base_glue;
            const bool propagation_bad=window_props>1.30*base_prop;
            const bool severe=window_cost>1.90*base_cost;
            const bool bad=(cost_bad&&(learning_bad||propagation_bad))||severe;
            if (bad) v182_bad_streak++;
            else v182_bad_streak=0;
            if (v182_bad_streak>=3) {
              kissat_set_option(solver,"restartint",1);
              if (!solver->stable)
                kissat_update_focused_restart_limit(solver);
              v182_fallbacks++;
              v182_fallback_conflict=seen;
            }
          }
          if (v182_nrecords<DRNAS_V182_RECORD_CAP &&
              (seen<=2048 || ((seen&(seen-1))==0) ||
               v182_bad_streak>=2 || v182_fallback_conflict==seen)) {
            drnas_v182_record *r=&v182_records[v182_nrecords++];
            r->conflict=seen;
            r->cpu_ns=(t0>=v182_start_cpu?t0-v182_start_cpu:0);
            r->restarts=solver->statistics.restarts;
            r->focused_restarts=v182_focused_restarts;
            r->learned=solver->statistics.clauses_learned;
            r->propagations=solver->statistics.propagations;
            r->decisions=DECISIONS;
            r->lbd_ratio=glue;
            r->window_cost_ns=window_cost;
            r->prop_per_conflict=window_props;
            r->bad_streak=v182_bad_streak;
            r->stable=(int)solver->stable;
            r->interval=GET_OPTION(restartint);
          }
          const uint64_t t1=drnas_v182_cpu_ns();
          if (t1>=t0)v182_monitor_ns+=t1-t0;
          v182_last_cpu=t1;
          v182_last_conflict=seen;
          v182_prev_props=solver->statistics.propagations;
          v182_next_sample=seen+DRNAS_V182_WINDOW;
          // CPU-budget circuit breaker: if monitor instrumentation exceeds
          // 0.5% after 100ms calibration, disable costly checks and restore.
          const uint64_t elapsed=(t1>v182_start_cpu?t1-v182_start_cpu:0);
          if (elapsed>100000000ull && v182_monitor_ns>elapsed/200ull) {
            v182_budget_aborted=true;
            v182_budget_conflict=seen;
            if (v182_switched && v182_guard && !v182_fallbacks) {
              kissat_set_option(solver,"restartint",1);
              if (!solver->stable)
                kissat_update_focused_restart_limit(solver);
              v182_fallbacks++;
              v182_fallback_conflict=seen;
            }
          }
        }
      } else if (solver->iterating)''')
    once("      else if (kissat_restarting (solver))\n        kissat_restart (solver);",
r'''      else if (kissat_restarting (solver)) {
        if (v182_on && !solver->stable)
          v182_focused_restarts++;
        kissat_restart (solver);
      }''')
    once("    stop_search (solver);\n  }\n  report_search_result (solver, res);",
r'''    stop_search (solver);
    if (v182_on) {
      const uint64_t end_cpu=drnas_v182_cpu_ns();
      const uint64_t cpu_ns=(end_cpu>v182_start_cpu)?
                            end_cpu-v182_start_cpu:0;
      const double percent=cpu_ns?
          100.0*(double)v182_monitor_ns/(double)cpu_ns:0.0;
      printf("c V182_RESULT policy=%s cpu_ns=%" PRIu64
             " monitor_ns=%" PRIu64 " monitor_pct=%.7f"
             " samples=%" PRIu64
             " switch_at=%" PRIu64 " interval=%d"
             " fallback_at=%" PRIu64 " fallbacks=%u"
             " bad_streak=%u budget_abort=%d budget_at=%" PRIu64
             " early_glue=%.9f conflicts=%" PRIu64
             " restarts=%" PRIu64 " focused_restarts=%" PRIu64
             " learned=%" PRIu64 "\n",
             drnas_v182_mode,cpu_ns,v182_monitor_ns,percent,
             v182_samples,v182_switch_conflict,v182_interval,
             v182_fallback_conflict,v182_fallbacks,v182_bad_streak,
             (int)v182_budget_aborted,v182_budget_conflict,v182_glue512,
             CONFLICTS,solver->statistics.restarts,v182_focused_restarts,
             solver->statistics.clauses_learned);
      for (unsigned i=0;i<v182_nrecords;i++) {
        const drnas_v182_record *r=&v182_records[i];
        printf("c V182_SAMPLE policy=%s conflict=%" PRIu64
               " cpu_ns=%" PRIu64 " restarts=%" PRIu64
               " focused_restarts=%" PRIu64
               " learned=%" PRIu64 " propagations=%" PRIu64
               " decisions=%" PRIu64
               " glue=%.9f cost_ns=%.5f prop_per_conf=%.5f"
               " bad=%u stable=%d interval=%d\n",
               drnas_v182_mode,r->conflict,r->cpu_ns,r->restarts,
               r->focused_restarts,r->learned,r->propagations,
               r->decisions,r->lbd_ratio,r->window_cost_ns,
               r->prop_per_conflict,r->bad_streak,r->stable,r->interval);
      }
      fflush(stdout);
    }
  }
  report_search_result (solver, res);''')
    return src

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--kissat-root",type=Path,required=True)
    args=parser.parse_args()
    path=args.kissat_root/"src"/"search.c"
    result=patch(path.read_text())
    path.write_text(result)
    print("V182_PATCH_PASS",PINNED,hashlib.sha256(result.encode()).hexdigest(),flush=True)

if __name__=="__main__":main()
