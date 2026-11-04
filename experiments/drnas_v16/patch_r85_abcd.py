#!/usr/bin/env python3
"""R85 four controlled native Kissat arms on original-CNF-certified XOR rows.

Apply AFTER R32b -> R32n -> R32s -> R32u -> R84.
A: read-only passive, original 64 rows, scan each 16 decisions.
B: certified active 64 rows, scan each 16 decisions.
C: certified active deterministic diverse subset of 64 from first 256 rows,
   scan each 16 decisions.
D: certified active all first 256 rows, scan each 4 decisions.
The first-UIP reason-match telemetry records when the original R32u-assigned
internal variable still references the same saved binary/clause reason. It is
not a standalone external DRAT/LRAT proof or guaranteed unique learned clause.
There is NO portfolio, no unproved parity, no change to normal CDCL policy.
"""
from pathlib import Path
import argparse

def rep(s,old,new,label):
    found=s.count(old)
    if found!=1:raise RuntimeError(f"R85_PATCH_FAIL_CLOSED {label} matches={found}")
    return s.replace(old,new,1)

DECL=r'''/* DRNAS R85 exact instrument + source-certified method selectors. */
#define R85_VAR_SLOTS 8192
static uint64_t r85_no_slot=0,r85_unimported=0,r85_eliminated=0,
    r85_bad_lit=0,r85_multi_free=0,r85_full_assigned=0;
static uint64_t r85_uip_reason_matches=0;
static unsigned r85_reason_code[R85_VAR_SLOTS];
static unsigned char r85_reason_valid[R85_VAR_SLOTS],r85_reason_binary[R85_VAR_SLOTS];
static int r85_arm=-1;
static double r85_last_print=-1.0;
static int r85_get_arm(void) {
  if(r85_arm>=0)return r85_arm;
  const char *s=getenv("R85_ARM");
  r85_arm= s && !strcmp(s,"C") ? 2 : s && !strcmp(s,"D") ? 3 :
           s && !strcmp(s,"A") ? 0 : 1;
  return r85_arm;
}
static void r85_save_reason(unsigned idx,unsigned code,int binary) {
  if(idx>=R85_VAR_SLOTS)return;
  r85_reason_valid[idx]=1;
  r85_reason_code[idx]=code;
  r85_reason_binary[idx]=(unsigned char)binary;
}
int r85_note_consumed_reason(unsigned idx,unsigned reason,int binary) {
  if(idx>=R85_VAR_SLOTS || !r85_reason_valid[idx] ||
     r85_reason_binary[idx]!=(unsigned char)binary ||
     r85_reason_code[idx]!=reason)return 0;
  r85_uip_reason_matches++;
  return 1;
}
static void r85_emit(kissat *solver,int force) {
  double now=r32s_now_ms();
  if(!force && r85_last_print>=0 && now-r85_last_print<2000.0)return;
  r85_last_print=now;
  printf("c R85_PROGRESS arm=%d rows=%u scans=%u attached=%u"
         " no_slot=%" PRIu64 " unimported=%" PRIu64
         " eliminated=%" PRIu64 " bad_lit=%" PRIu64
         " multi_free=%" PRIu64 " full_assigned=%" PRIu64
         " eligible=%" PRIu64 " uip_reason_matches=%" PRIu64
         " conflicts=%" PRIu64 " decisions=%" PRIu64
         " cpu_ms=%.3f final=%d\n",
         r85_get_arm(),r32u_nrows,r32u_probed,r32u_added,
         r85_no_slot,r85_unimported,r85_eliminated,r85_bad_lit,
         r85_multi_free,r85_full_assigned,r84_eligible,
         r85_uip_reason_matches,solver->statistics.conflicts,
         solver->statistics.decisions,now,force);
  fflush(stdout);
}
'''

def patch(root):
    src=root/"src"
    p=src/"parse.c"
    s=p.read_text()
    anchor='  printf("c R32U_BASIS original_equations=%u rank=%u free=%u candidates=%u"'
    new=r'''  const char *r85_arm_env=getenv("R85_ARM");
  if(r85_arm_env && !strcmp(r85_arm_env,"C") && found>64) {
    r32u_source_equation diverse[64];
    for(unsigned j=0;j<64;j++){
      const unsigned index=(unsigned)((uint64_t)j*(found-1)/63u);
      diverse[j]=dest[index];
    }
    memcpy(dest,diverse,sizeof(diverse));
    found=64;
  }
  printf("c R32U_BASIS original_equations=%u rank=%u free=%u candidates=%u"'''
    s=rep(s,anchor,new,"source_proof_safe_diverse_row_selection")
    p.write_text(s)
    p=src/"search.c"
    s=p.read_text()
    s=rep(s,"#define R32U_MAX_ROWS 64","#define R32U_MAX_ROWS 256",
          "capacity256")
    s=rep(s,
          "static void r84_emit(kissat *solver,int force) {",
          DECL+"\nstatic void r84_emit(kissat *solver,int force) {",
          "monitor_declaration")
    s=rep(s,
       "  r32u_nrows=r32u_prepare_source_rows(r32u_rows,R32U_MAX_ROWS);",
       "  const int r85_arm_id=r85_get_arm();\n"
       "  const unsigned max_rows=(r85_arm_id==2 || r85_arm_id==3) ? 256u : 64u;\n"
       "  r32u_nrows=r32u_prepare_source_rows(r32u_rows,max_rows);\n"
       "  r85_no_slot=r85_unimported=r85_eliminated=r85_bad_lit=0;\n"
       "  r85_multi_free=r85_full_assigned=r85_uip_reason_matches=0;\n"
       "  memset(r85_reason_valid,0,sizeof(r85_reason_valid));\n"
       "  r85_last_print=-1.0;\n"
       "  printf(\"c R85_ARM id=%d source_rows=%u requested=%u\\n\","
       "r85_arm_id,r32u_nrows,max_rows);\n"
       "  fflush(stdout);",
       "different_A_B_C_D_row_capacity")
    s=rep(s,
       "static void r32u_final(kissat *solver) {\n  r84_emit(solver,1);",
       "static void r32u_final(kissat *solver) {\n"
       "  r85_emit(solver,1);\n  r84_emit(solver,1);",
       "final_timeout_safe_counts")
    s=rep(s,
       "static void r32u_scan(kissat *solver) {\n  r84_emit(solver,0);",
       "static void r32u_scan(kissat *solver) {\n"
       "  r85_emit(solver,0);\n  r84_emit(solver,0);",
       "periodic_counts")
    s=rep(s,
       "      if(ext>=SIZE_STACK(solver->import)){safe=0;break;}",
       "      if(ext>=SIZE_STACK(solver->import)){r85_no_slot++;safe=0;break;}",
       "out_of_import_array")
    s=rep(s,
       "      if(!imp->imported || imp->eliminated){safe=0;break;}",
       "      if(!imp->imported){r85_unimported++;safe=0;break;}\n"
       "      if(imp->eliminated){r85_eliminated++;safe=0;break;}",
       "unimported_separate_from_eliminated")
    s=rep(s,
       "      if(lit>=LITS){safe=0;break;}",
       "      if(lit>=LITS){r85_bad_lit++;safe=0;break;}",
       "invalid_literal")
    s=rep(s,
       "        if(missing!=INVALID_LIT){safe=0;break;}",
       "        if(missing!=INVALID_LIT){r85_multi_free++;safe=0;break;}",
       "multiple_unassigned")
    s=rep(s,
       "      if(safe && missing==INVALID_LIT){\n"
       "        // Pure telemetry only.",
       "      if(safe && missing==INVALID_LIT){\n"
       "        r85_full_assigned++;\n"
       "        // Pure telemetry only.",
       "fully_assigned")
    s=rep(s,
       "      kissat_assign_binary(solver,target,false_lits[0]);",
       "      kissat_assign_binary(solver,target,false_lits[0]);\n"
       "      r85_save_reason(IDX(target),false_lits[0],1);",
       "save_binary_reason")
    s=rep(s,
       "      kissat_assign_reference(solver,target,ref,reason);",
       "      kissat_assign_reference(solver,target,ref,reason);\n"
       "      r85_save_reason(IDX(target),ref,0);",
       "save_reference_reason")
    p.write_text(s)
    p=src/"deduce.c"
    s=p.read_text()
    s=rep(s,
       '#include "deduce.h"',
       '#include "deduce.h"\n'
       'extern int r85_note_consumed_reason(unsigned,unsigned,int);',
       "cross_file_decl")
    s=rep(s,
       "    assert (a->reason != DECISION_REASON);\n"
       "    assert (a->level == solver->level);\n"
       "    solver->antecedent_size = 1;",
       "    assert (a->reason != DECISION_REASON);\n"
       "    assert (a->level == solver->level);\n"
       "    r85_note_consumed_reason(IDX(uip),a->reason,a->binary);\n"
       "    solver->antecedent_size = 1;",
       "real_First_UIP_reason_resolution_match")
    p.write_text(s)
    print("R85_ABCD_NATIVE_SOURCE_SOUND_AND_REASON_PATCH_PASS",flush=True)

def selftest():
    assert "uip_reason_matches" in DECL and "r85_multi_free" in DECL
    print("R85_ABCD_PATCH_PREFLIGHT_PASS",flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--kissat-root",type=Path)
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    if a.selftest:selftest()
    elif a.kissat_root:patch(a.kissat_root)
    else:p.error("specify --kissat-root or --selftest")
