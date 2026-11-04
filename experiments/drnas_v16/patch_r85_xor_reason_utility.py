#!/usr/bin/env python3
"""R85: source-certified XOR diagnostics, actual 1-UIP reason usage, diversity policy.

Apply AFTER R32b, R32n, R32s, R32u and R84 patches to pinned Kissat.
R85 does not change the logic of source XOR inference, native reason
assignment, or the original CNF. Three independent changes:
A) disjoint row guard / trail state counter categories;
B) native deduce.c instrumentation counts a proof-entailed nonbinary reason
   only when it is encountered while constructing the FIRST UIP clause.
   Reference and original clause literal set BOTH verified to reduce false
   positives from reference recycling. Result is a LOWER BOUND, not exact.
C) optional deterministic coverage-diverse choice of 64 source-certified
   candidate rows, contrasted against original lexicographic first 64.
All derived parity rows independently rechecked against the original CNF.
"""
from pathlib import Path
import argparse

def once(s,old,new,label):
    n=s.count(old)
    if n!=1:raise RuntimeError(f"R85_PATCH_ANCHOR {label} count={n}")
    return s.replace(old,new,1)

METRICS=r'''
/* R85 read-only reason utility: never changes native clause or assignment. */
static uint64_t r85_guard_missing_import=0, r85_guard_eliminated=0;
static uint64_t r85_guard_bad_literal=0, r85_guard_out_of_scope=0;
static uint64_t r85_trail_multi_unassigned=0, r85_trail_all_assigned=0;
static uint64_t r85_trail_all_satisfied=0, r85_trail_all_conflicting=0;
static uint64_t r85_trail_one_missing=0;
static uint64_t r85_first_uip_uses=0, r85_reason_matched=0;
static double r85_last_ms=-1;
typedef struct {
   reference ref;
   unsigned size, lits[5];
} r85_reason_identity;
static r85_reason_identity r85_reasons[R32U_MAX_REASON_CLAUSES];
static unsigned r85_nreason=0;
static int r85_reason_equal(const clause *c,const r85_reason_identity *p) {
  if(c->size!=p->size)return 0;
  for(unsigned i=0;i<p->size;i++){
    int seen=0;
    for(unsigned j=0;j<c->size;j++)if(c->lits[j]==p->lits[i])seen++;
    if(seen!=1)return 0;
  }
  return 1;
}
static void r85_register_reason(reference ref,const clause *c) {
  if(c->size>5 || r85_nreason>=R32U_MAX_REASON_CLAUSES)return;
  r85_reason_identity *r=&r85_reasons[r85_nreason++];
  r->ref=ref;r->size=c->size;
  for(unsigned i=0;i<c->size;i++)r->lits[i]=c->lits[i];
}
/* Called ONLY when native Kissat actually resolves an assigned variable
 * using a clause in FIRST UIP conflict analysis, not when it is created. */
void r85_note_first_uip_reason(reference ref,const clause *reason) {
  for(unsigned i=0;i<r85_nreason;i++) {
    const r85_reason_identity *p=&r85_reasons[i];
    if(p->ref==ref && r85_reason_equal(reason,p)) {
      r85_first_uip_uses++;return;
    }
  }
}
static void r85_emit(kissat *solver,int force) {
  const double ms=r32s_now_ms();
  if(!force && r85_last_ms>=0 && ms-r85_last_ms<2000.0)return;
  r85_last_ms=ms;
  printf("c R85_PROGRESS active=%d prepared=%u selected_reason_refs=%u"
    " missing_import=%" PRIu64 " eliminated=%" PRIu64
    " bad_literal=%" PRIu64 " out_of_scope=%" PRIu64
    " multi_unassigned=%" PRIu64 " all_assigned=%" PRIu64
    " all_satisfied=%" PRIu64 " all_conflicting=%" PRIu64
    " one_missing=%" PRIu64
    " attached=%u first_uip_reason_uses=%" PRIu64
    " scans=%u conflicts=%" PRIu64 " decisions=%" PRIu64
    " cpu_ms=%.3f final=%d\n",
    r32u_selected(),r32u_nrows,r85_nreason,
    r85_guard_missing_import,r85_guard_eliminated,
    r85_guard_bad_literal,r85_guard_out_of_scope,
    r85_trail_multi_unassigned,r85_trail_all_assigned,
    r85_trail_all_satisfied,r85_trail_all_conflicting,
    r85_trail_one_missing,r32u_added,r85_first_uip_uses,
    r32u_probed,solver->statistics.conflicts,solver->statistics.decisions,
    ms,force);
  fflush(stdout);
}
'''

def patch_search(root):
    p=root/"src"/"search.c";s=p.read_text()
    s=once(s,
      '#define R32U_MAX_ROWS 64',
      '#define R32U_MAX_ROWS 128',
      'safe_128_array_capacity')
    s=once(s,
      'static void r32u_initialize(kissat *solver) {',
      'static unsigned r85_cap(void) {\n'
      '  const char *p=getenv("R85_CAP");\n'
      '  return p && !strcmp(p,"128") ? 128u : 64u;\n'
      '}\nstatic void r32u_initialize(kissat *solver) {',
      'r85_declares_dynamic_fixed_cap')
    s=once(s,
      'r32u_prepare_source_rows(r32u_rows,R32U_MAX_ROWS);',
      'r32u_prepare_source_rows(r32u_rows,r85_cap());',
      'r85_selected_cap_is_64_or_128')
    s=once(s,'static void r32u_initialize(kissat *solver) {',
       METRICS+'\nstatic void r32u_initialize(kissat *solver) {','new_R85_metrics')
    s=once(s,
      '  r84_last_emit_ms=-1.0;\n',
      '  r84_last_emit_ms=-1.0;\n'
      '  r85_guard_missing_import=r85_guard_eliminated=0;\n'
      '  r85_guard_bad_literal=r85_guard_out_of_scope=0;\n'
      '  r85_trail_multi_unassigned=r85_trail_all_assigned=0;\n'
      '  r85_trail_all_satisfied=r85_trail_all_conflicting=r85_trail_one_missing=0;\n'
      '  r85_first_uip_uses=0;r85_reason_matched=0;r85_nreason=0;\n'
      '  r85_last_ms=-1;\n',
      'reset_R85_counters')
    s=once(s,
      'static void r32u_final(kissat *solver) {\n  r84_emit(solver,1);',
      'static void r32u_final(kissat *solver) {\n'
      '  r85_emit(solver,1);\n  r84_emit(solver,1);',
      'flush_R85_final')
    s=once(s,
      'static void r32u_scan(kissat *solver) {\n  r84_emit(solver,0);',
      'static void r32u_scan(kissat *solver) {\n'
      '  r85_emit(solver,0);\n  r84_emit(solver,0);',
      'flush_R85_before_scan')
    s=once(s,
      '      if(ext>=SIZE_STACK(solver->import)){safe=0;break;}',
      '      if(ext>=SIZE_STACK(solver->import)){\n'
      '        r85_guard_out_of_scope++;safe=0;break;\n      }',
      'count_out_of_scope')
    s=once(s,
      '      if(!imp->imported || imp->eliminated){safe=0;break;}',
      '      if(!imp->imported){r85_guard_missing_import++;safe=0;break;}\n'
      '      if(imp->eliminated){r85_guard_eliminated++;safe=0;break;}',
      'split_import_vs_eliminated')
    s=once(s,
      '      if(lit>=LITS){safe=0;break;}',
      '      if(lit>=LITS){r85_guard_bad_literal++;safe=0;break;}',
      'count_bad_literal')
    s=once(s,
      '        if(missing!=INVALID_LIT){safe=0;break;}',
      '        if(missing!=INVALID_LIT){r85_trail_multi_unassigned++;safe=0;break;}',
      'count_multi_unassigned')
    s=once(s,
      '      if(safe && missing==INVALID_LIT){\n'
      '        // Pure telemetry only.',
      '      if(safe && missing==INVALID_LIT){\n'
      '        r85_trail_all_assigned++;\n'
      '        if(parity)r85_trail_all_conflicting++;\n'
      '        else r85_trail_all_satisfied++;\n'
      '        // Pure telemetry only.',
      'count_full_assigned')
    s=once(s,
      '    r32u_implications++;\n    r84_eligible++;',
      '    r32u_implications++;\n    r85_trail_one_missing++;\n    r84_eligible++;',
      'count_one_unassigned')
    s=once(s,
      '      clause *reason=kissat_dereference_clause(solver,ref);\n'
      '      kissat_assign_reference(solver,target,ref,reason);',
      '      clause *reason=kissat_dereference_clause(solver,ref);\n'
      '      r85_register_reason(ref,reason);\n'
      '      kissat_assign_reference(solver,target,ref,reason);',
      'register_nonbinary_reasons')
    p.write_text(s)

def patch_deduce(root):
    p=root/"src"/"deduce.c";s=p.read_text()
    s=once(s,
      '#include "strengthen.h"',
      '#include "strengthen.h"\n'
      'extern void r85_note_first_uip_reason(reference,const clause *);',
      'declare_nonbinary_reason_usage_hook')
    s=once(s,
      '      clause *reason = kissat_dereference_clause (solver, ref);\n'
      '      for (all_literals_in_clause (lit, reason))',
      '      clause *reason = kissat_dereference_clause (solver, ref);\n'
      '      r85_note_first_uip_reason(ref,reason);\n'
      '      for (all_literals_in_clause (lit, reason))',
      'count_actual_first_uip_resolution_only')
    p.write_text(s)

def patch_selection(root):
    p=root/"src"/"parse.c";s=p.read_text()
    prev=('  unsigned found=0;\n'
          '  for(unsigned j=0;j<total && found<cap;j++) {\n'
          '    if(j && !r32u_canonical_cmp(&candidates[j],&candidates[j-1]))\n'
          '       continue;\n'
          '    dest[found++]=candidates[j];\n'
          '  }\n')
    repl=r'''  unsigned found=0;
  const char *sel=getenv("R85_DIVERSE");
  const int diverse=sel && !strcmp(sel,"1");
  if(diverse) {
    /* COVERAGE-DIVERSE source-only alternative, before the solver runs:
     * 1) reject exact duplicates, 2) favor fresh variable coverage,
     * 3) favor shorter sound rows. NEVER uses SAT label or solve time.
     * Candidate rows still originate from the identical original GF(2)
     * proof basis, with the same fixed cap and guard conditions.
     */
    unsigned chosen[512]={0};
    unsigned freq[R32B_MAXVAR+1]={0};
    while(found<cap && found<total){
      unsigned best=UINT_MAX, best_cost=UINT_MAX;
      for(unsigned j=0;j<total;j++){
        if(chosen[j])continue;
        if(j && !r32u_canonical_cmp(&candidates[j],&candidates[j-1]))
            continue;
        const r32u_source_equation *r=&candidates[j];
        unsigned cost=3*(unsigned)r->width;
        for(unsigned k=0;k<r->width;k++)
           cost+=32*freq[r->vars[k]];
        if(cost<best_cost){best=j;best_cost=cost;}
      }
      if(best==UINT_MAX)break;
      chosen[best]=1;
      dest[found++]=candidates[best];
      for(unsigned k=0;k<candidates[best].width;k++)
         freq[candidates[best].vars[k]]++;
    }
  } else {
    for(unsigned j=0;j<total && found<cap;j++) {
      if(j && !r32u_canonical_cmp(&candidates[j],&candidates[j-1]))
         continue;
      dest[found++]=candidates[j];
    }
  }
  printf("c R85_SELECTION diverse=%d source_candidates=%u selected=%u\n",
         diverse,total,found);
  fflush(stdout);
'''
    s=once(s,prev,repl,"toggle_source_only_diverse_64_selection")
    p.write_text(s)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--kissat-root",type=Path,required=True)
    a=ap.parse_args()
    root=a.kissat_root
    patch_selection(root)
    patch_search(root)
    patch_deduce(root)
    print("R85_XOR_CATEGORY_UIP_REASON_COVERAGE_POLICY_PATCH_PASS",flush=True)
if __name__=="__main__":main()
