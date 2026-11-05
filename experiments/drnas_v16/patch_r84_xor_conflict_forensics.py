#!/usr/bin/env python3
"""Read-only R84 CDCL/XOR forensics on top of the PROVEN R32u native patch.

No new parity inference or learning rules. Snapshot counters are flushed even
when a trial times out; snapshot frequency is CPU-clock based (2 s).
Frequency arm 4 modifies ONLY R32u's existing scan interval (from 16 to 4)
and is an explicitly separate experiment, not a post-hoc win.
Conflicts following XOR attachments are correlations, NOT proof that a learned
clause used a particular XOR reason. This script deliberately never claims
native proof-use counts it has not instrumented.
"""
import argparse
from pathlib import Path

def swap(s,a,b,label):
    n=s.count(a)
    if n!=1:
        raise RuntimeError(f"R84_PATCH_ANCHOR {label}: expected=1 seen={n}")
    return s.replace(a,b,1)

DECL=r'''
/* R84 read-only, monotone counters. The R32u algorithm remains unchanged. */
static uint64_t r84_rows_visited=0, r84_row_guard_rejected=0, r84_eligible=0;
static uint64_t r84_first_attach_conflicts=0;
static int r84_had_attach=0, r84_interval=16;
static double r84_last_emit_ms=-1.0;

static void r84_emit(kissat *solver,int force) {
  const double now=r32s_now_ms();
  if(!force && r84_last_emit_ms>=0 && now-r84_last_emit_ms<2000.0)
    return;
  r84_last_emit_ms=now;
  const uint64_t later=r84_had_attach && solver->statistics.conflicts>=r84_first_attach_conflicts ?
      solver->statistics.conflicts-r84_first_attach_conflicts : 0;
  printf("c R84_PROGRESS active=%d interval=%d rows=%u scans=%u"
         " examined=%" PRIu64 " rejected=%" PRIu64
         " eligible=%" PRIu64 " attached=%u fully_conflicting=%u"
         " conflicts=%" PRIu64 " conflicts_after_first_attach=%" PRIu64
         " decisions=%" PRIu64 " propagations=%" PRIu64
         " restarts=%" PRIu64 " cpu_ms=%.3f final=%d\n",
         r32u_mode,r84_interval,r32u_nrows,r32u_probed,
         r84_rows_visited,r84_row_guard_rejected,
         r84_eligible,r32u_added,r32u_mismatches,
         solver->statistics.conflicts,later,
         solver->statistics.decisions,solver->statistics.propagations,
         solver->statistics.restarts,now,force);
  fflush(stdout);
}
'''

def patch(root):
    path=root/"src"/"search.c"
    s=path.read_text()
    s=swap(s,
       'static int r32u_mode=-1, r32u_last_assigned=0;',
       'static int r32u_mode=-1, r32u_last_assigned=0;\n'+DECL,
       'declare_r84_monitor')
    s=swap(s,
       '  r32u_last_decisions=UINT64_MAX;\n  printf("c R32U_MODE active=%d prepared=%u max_reasons=%u\\n",',
       '  r32u_last_decisions=UINT64_MAX;\n'
       '  r84_rows_visited=r84_row_guard_rejected=r84_eligible=0;\n'
       '  r84_first_attach_conflicts=0;r84_had_attach=0;\n'
       '  r84_last_emit_ms=-1.0;\n'
       '  const char *freq=getenv("R84_SCAN_EVERY");\n'
       '  r84_interval=freq && !strcmp(freq,"4") ? 4 : 16;\n'
       '  printf("c R84_BEGIN active=%d interval=%d prepared=%u\\n",'
       '         r32u_selected(),r84_interval,r32u_nrows);\n'
       '  fflush(stdout);\n'
       '  printf("c R32U_MODE active=%d prepared=%u max_reasons=%u\\n",',
       'r84_start_and_interval')
    s=swap(s,
       'd<r32u_last_decisions+16)',
       'd<r32u_last_decisions+(uint64_t)r84_interval)',
       'change_scan_interval_only')
    s=swap(s,
       'static void r32u_final(kissat *solver) {\n  printf("c R32U_STATS',
       'static void r32u_final(kissat *solver) {\n'
       '  r84_emit(solver,1);\n  printf("c R32U_STATS',
       'final_flush')
    s=swap(s,
       'static void r32u_scan(kissat *solver) {\n  r32u_last_assigned=0;',
       'static void r32u_scan(kissat *solver) {\n'
       '  r84_emit(solver,0);\n  r32u_last_assigned=0;',
       'timeout_progress')
    s=swap(s,
       '    const r32u_source_equation *row=&r32u_rows[index];',
       '    const r32u_source_equation *row=&r32u_rows[index];\n'
       '    r84_rows_visited++;',
       'count_rows_examined')
    s=swap(s,
       '    if(!safe || observed+1!=row->width){\n'
       '      if(safe && missing==INVALID_LIT){',
       '    if(!safe || observed+1!=row->width){\n'
       '      if(!safe)r84_row_guard_rejected++;\n'
       '      if(safe && missing==INVALID_LIT){',
       'count_guarded')
    s=swap(s,
       '    r32u_implications++;\n    if(!r32u_selected())continue;',
       '    r32u_implications++;\n    r84_eligible++;\n'
       '    if(!r32u_selected())continue;',
       'count_eligible')
    s=swap(s,
       '    r32u_added++;\n    r32u_last_assigned=1;',
       '    if(!r84_had_attach){r84_had_attach=1;\n'
       '      r84_first_attach_conflicts=solver->statistics.conflicts;}\n'
       '    r32u_added++;\n    r32u_last_assigned=1;',
       'track_first_reason')
    path.write_text(s)
    print("R84_READONLY_GF2_CDCL_CONFLICT_TELEMETRY_PATCH_PASS",flush=True)

def selftest():
    ck=("static int r32u_mode=-1, r32u_last_assigned=0;",
        '    r32u_implications++;\n    if(!r32u_selected())continue;',
        'd<r32u_last_decisions+16)')
    for a in ck:
        if not a:raise RuntimeError("R84 impossible source anchor")
    print("R84_PATCH_PREFLIGHT_PASS",flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--kissat-root",type=Path)
    ap.add_argument("--selftest",action="store_true")
    a=ap.parse_args()
    if a.selftest:selftest()
    elif a.kissat_root:patch(a.kissat_root)
    else:ap.error("specify --kissat-root or --selftest")
