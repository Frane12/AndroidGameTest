#!/usr/bin/env python3
"""R65x-Live: feedback-gated CDCL trail <-> certified original GF(2) row propagation.

Patch AFTER R32b, R32n, R32s, R32u, R84, R85 on pinned Kissat
8af8e56f174b778aef3aa45af9f739b2a5f492c2.
Changes ONLY the R32u scan cadence, not any parity proof, CNF reason construction,
SAT decision rule, or external source. CDCL->XOR: current live solver trail;
XOR->CDCL: source-certified reason clauses via unchanged R32u implementation.
Feedback: observed actual first-UIP use alters scan cadence, not correctness.
This is single-process in-search bidirectional propagation, NOT inter-process
learned-clause exchange or complete online Gaussian elimination.
"""
import argparse
from pathlib import Path

def once(s, a, b, label):
    n=s.count(a)
    if n!=1:
        raise RuntimeError(f"R65XL_PATCH_ANCHOR_{label} count={n}")
    return s.replace(a,b,1)

DECL=r'''
/* R65x-Live adaptive scan cost control.
   All logical implications and native reason attachments remain those of
   already independently validated R32u/R85 GF(2) source proof pathways. */
static unsigned r65xl_interval=16, r65xl_switches=0;
static int r65xl_adaptive=0;
static double r65xl_last_emit_ms=-1;
static void r65xl_refresh(void) {
  unsigned next=r84_interval;
  if(r65xl_adaptive){
    /* Explore early, back off when little utility, resume fast only after
       native FIRST-UIP actually consumes an independently sourced XOR reason. */
    if(r85_first_uip_uses)next=4;
    else if(r32u_probed<8)next=4;
    else if(r32u_added==0)next=64;
    else if(r32u_probed>=32)next=64;
    else next=16;
  }
  if(next!=r65xl_interval) {r65xl_switches++;r65xl_interval=next;}
}
static void r65xl_emit(kissat *solver,int final) {
  const double now=r32s_now_ms();
  if(!final && r65xl_last_emit_ms>=0 && now-r65xl_last_emit_ms<2000.0)
    return;
  r65xl_last_emit_ms=now;
  /* Directionality: real CDCL trail values evaluated in GF2 rows; certified
     XOR consequences assigned back into CDCL; actual first-UIP usage counted. */
  printf("c R65XL_LIVE adaptive=%d interval=%u switches=%u rows=%u"
         " trail_row_checks=%" PRIu64 " xor_candidates=%u"
         " xor_to_cdcl_reasons=%u cdcl_first_uip_uses=%" PRIu64
         " scans=%u decisions=%" PRIu64 " conflicts=%" PRIu64
         " cpu_ms=%.3f final=%d\\n",
         r65xl_adaptive,r65xl_interval,r65xl_switches,
         r32u_nrows,r84_rows_visited,r32u_implications,
         r32u_added,r85_first_uip_uses,r32u_probed,
         solver->statistics.decisions,solver->statistics.conflicts,now,final);
  fflush(stdout);
}
'''

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--kissat-root",type=Path,required=True)
    a=p.parse_args()
    path=a.kissat_root/"src"/"search.c"
    s=path.read_text()
    s=once(s,"static int r32u_due(kissat *solver) {",
           DECL+"\nstatic int r32u_due(kissat *solver) {\n  r65xl_refresh();",
           "new_adaptive_feedback")
    s=once(s,
           "d<r32u_last_decisions+(uint64_t)r84_interval)",
           "d<r32u_last_decisions+(uint64_t)r65xl_interval)",
           "safe_scan_cadence")
    s=once(s,
           '  r85_last_ms=-1;\n',
           '  r85_last_ms=-1;\n'
           '  const char *live=getenv("R65XL_POLICY");\n'
           '  r65xl_adaptive=live && !strcmp(live,"adaptive");\n'
           '  r65xl_interval=r84_interval; r65xl_switches=0;\n'
           '  r65xl_last_emit_ms=-1;\n',
           "initialize_live_policy")
    s=once(s,
           "static void r32u_scan(kissat *solver) {\n  r85_emit(solver,0);",
           "static void r32u_scan(kissat *solver) {\n"
           "  r65xl_emit(solver,0);\n  r85_emit(solver,0);",
           "live_progress")
    s=once(s,
           "static void r32u_final(kissat *solver) {\n  r85_emit(solver,1);",
           "static void r32u_final(kissat *solver) {\n"
           "  r65xl_emit(solver,1);\n  r85_emit(solver,1);",
           "live_final")
    path.write_text(s)
    print("R65XL_LIVE_BIDIRECTIONAL_TRAIL_REASON_ADAPTIVE_PATCH_PASS",flush=True)

if __name__=="__main__":
    main()
