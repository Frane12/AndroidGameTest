#!/usr/bin/env python3
"""R32u: native CDCL-TRAIL-conditioned GF(2) implications WITH CNF reasons.

Build after R32b original-CNF capture and R32n optional static unit patch.
Only complete original parity encodings accepted; no hidden resolvent algebra
in first experimental version. At the start of searching, compute a frozen
GF2 RREF over source clauses. During CDCL, when a short entailed equation has
exactly one unassigned variable, inject *a parity-entailed clause* and use it
as the reason for the new assignment. Every CNF reason is logically implied
by the XOR row, which is itself implied by the untouched original CNF.
Root unit / eliminated-variable / unknown structural cases safely abstain.
Never assign a literal without a reason. No concurrent solver, no watchdog.
"""

from pathlib import Path
import argparse

def once(s,a,b,where):
    n=s.count(a)
    if n!=1:raise RuntimeError(f"R32U_KISSAT_ANCHOR {where} count={n}")
    return s.replace(a,b,1)

API=r'''/* R32u shared pure-original-source GF2 row ABI, fixed maximal width. */
#ifndef R32U_NATIVE_API_H
#define R32U_NATIVE_API_H
typedef struct {
  unsigned char width, rhs;
  unsigned short vars[5];
} r32u_source_equation;
unsigned r32u_prepare_source_rows(r32u_source_equation *, unsigned);
#endif
'''

SOURCE=r'''/* R32u source-only complete parity root rows.
 * Executed once at first search entry, using SHA-original DIMACS capture.
 * No equation inferred from solver heuristics, learned clauses, SAT labels.
 */
#include "r32u_native_api.h"
static int r32u_canonical_cmp(const void *ap,const void *bp) {
  const r32u_source_equation *a=ap,*b=bp;
  if(a->width!=b->width)return (int)a->width-(int)b->width;
  for(unsigned k=0;k<a->width;k++) if(a->vars[k]!=b->vars[k])
     return (int)a->vars[k]-(int)b->vars[k];
  return (int)a->rhs-(int)b->rhs;
}
unsigned r32u_prepare_source_rows(r32u_source_equation *dest,unsigned cap) {
  if(!r32b_active || r32b_guard || !dest || !cap)return 0;
  if(!r32b_looked)r32b_discover();
  // Restrict this first proof protocol to original complete parity
  // encodings; no binary-resolvent-recovered hidden XOR axioms.
  if(r32b_guard || r32b_nresolved) {
    printf("c R32U_GUARD source=hidden_resolvent_or_input_guard resolved=%u\n",
           r32b_nresolved);
    return 0;
  }
  r32b_gap gap=r32b_compute(NULL,0);
  if(gap.contradiction || r32b_guard) {
    printf("c R32U_GUARD source=root_contradiction_or_cap contradiction=%u\n",
           gap.contradiction);return 0;
  }
  r32u_source_equation candidates[512];
  unsigned total=0;
  const unsigned words=(r32b_varmax+63)/64;
  for(unsigned j=0;j<gap.rank;j++){
    const uint64_t *bits=r32b_basis[j];
    unsigned pop=0;
    for(unsigned w=0;w<words;w++)pop+=__builtin_popcountll(bits[w]);
    if(pop<2 || pop>5)continue;
    r32u_source_equation row={0};
    row.width=(unsigned char)pop;
    row.rhs=r32b_basis_rhs[j];
    unsigned k=0;
    for(unsigned v=1;v<=r32b_varmax;v++) {
      if(bits[(v-1)>>6] & (1ULL<<((v-1)&63)))
         row.vars[k++]=(unsigned short)v;
    }
    if(k!=pop)continue;
    // Original complete equations are already propagated by usual BCP;
    // study only newly derived short GF2 relations.
    int direct=0;
    for(unsigned e=0;e<r32b_neq;e++){
      const r32b_eq *src=&r32b_eqs[e];
      if(src->k!=pop || src->rhs!=row.rhs)continue;
      unsigned match=1;
      for(unsigned i=0;i<pop;i++)
        if(src->v[i]!=row.vars[i]){match=0;break;}
      if(match){direct=1;break;}
    }
    if(direct)continue;
    if(total<512)candidates[total++]=row;
  }
  qsort(candidates,total,sizeof(*candidates),r32u_canonical_cmp);
  unsigned found=0;
  for(unsigned j=0;j<total && found<cap;j++) {
    if(j && !r32u_canonical_cmp(&candidates[j],&candidates[j-1]))
       continue;
    dest[found++]=candidates[j];
  }
  printf("c R32U_BASIS original_equations=%u rank=%u free=%u candidates=%u"
         " selected=%u root_units=%u\n",
         r32b_neq,gap.rank,r32b_varmax-gap.rank,total,found,gap.bcp_units);
  for(unsigned i=0;i<found;i++){
    const r32u_source_equation *r=dest+i;
    printf("c R32U_SOURCE_ROW rhs=%u vars=",r->rhs);
    for(unsigned j=0;j<r->width;j++)
      printf("%s%u",j?",":"",r->vars[j]);
    putchar('\n');
  }
  fflush(stdout);
  return found;
}
'''

LIVE=r'''/* R32u: original-CNF-certified short GF2 row is evaluated on actual
 * native Kissat CDCL trail. If exactly one variable is unassigned,
 * its XOR-required value is assigned with a fresh sound CNF reason.
 * The current SAT solver, learned clause DB, and backtracking remain
 * under the same original native Kissat CDCL implementation.
 *
 * WARNING: dynamic XOR clauses added here have independent linear
 * combination certificates, not a DRAT/LRAT replay for an external
 * competition proof. UNSAT conclusions require later DRAT verification.
 */
#include "r32u_native_api.h"
#define R32U_MAX_ROWS 64
#define R32U_MAX_REASON_CLAUSES 256
static r32u_source_equation r32u_rows[R32U_MAX_ROWS];
static unsigned r32u_nrows=0, r32u_added=0, r32u_probed=0;
static unsigned r32u_implications=0, r32u_mismatches=0;
static uint64_t r32u_last_decisions=UINT64_MAX;
static int r32u_mode=-1, r32u_last_assigned=0;
static int r32u_selected(void) {
  if(r32u_mode<0) {
    const char *p=getenv("R32U_ACTIVE");
    r32u_mode=p && !strcmp(p,"1") ? 1:0;
  }
  return r32u_mode;
}
static void r32u_initialize(kissat *solver) {
  (void) solver;
  if(!r32u_selected()){
    // R32u passive mode still constructs the very same original-CNF
    // GF2 RREF, measuring extraction cost, without changing solver.
  }
  r32u_nrows=r32u_prepare_source_rows(r32u_rows,R32U_MAX_ROWS);
  r32u_added=r32u_probed=r32u_implications=r32u_mismatches=0;
  r32u_last_decisions=UINT64_MAX;
  printf("c R32U_MODE active=%d prepared=%u max_reasons=%u\n",
         r32u_selected(),r32u_nrows,R32U_MAX_REASON_CLAUSES);
  fflush(stdout);
}
static int r32u_due(kissat *solver) {
  if(!r32u_nrows || r32u_added>=R32U_MAX_REASON_CLAUSES)return 0;
  // Low overhead for real long-horizon CDCL search: only every 16th
  // decision, with a first unconditional scan at decision zero.
  const uint64_t d=solver->statistics.decisions;
  if(r32u_last_decisions!=UINT64_MAX && d<r32u_last_decisions+16)
     return 0;
  r32u_last_decisions=d;
  return 1;
}
static void r32u_final(kissat *solver) {
  printf("c R32U_STATS active=%d rows=%u scans=%u candidates=%u"
         " attached=%u conflict_rows=%u conflicts=%" PRIu64
         " decisions=%" PRIu64 "\n",
         r32u_selected(),r32u_nrows,r32u_probed,r32u_implications,
         r32u_added,r32u_mismatches,
         solver->statistics.conflicts,solver->statistics.decisions);
  fflush(stdout);
}
static void r32u_scan(kissat *solver) {
  r32u_last_assigned=0;
  if(!r32u_due(solver))return;
  r32u_probed++;
  for(unsigned index=0;index<r32u_nrows;index++){
    const r32u_source_equation *row=&r32u_rows[index];
    unsigned false_lits[5],missing=INVALID_LIT,missing_ext=0;
    unsigned observed=0;
    unsigned parity=row->rhs;
    int safe=1;
    for(unsigned i=0;i<row->width;i++){
      const unsigned ext=row->vars[i];
      // Never import NEW variables into a live solver. Eliminated or
      // remapped originals are rejected rather than unsafely reused.
      if(ext>=SIZE_STACK(solver->import)){safe=0;break;}
      const struct import *imp=&PEEK_STACK(solver->import,ext);
      if(!imp->imported || imp->eliminated){safe=0;break;}
      const unsigned lit=imp->lit;
      if(lit>=LITS){safe=0;break;}
      const value v=solver->values[lit];
      if(!v) {
        if(missing!=INVALID_LIT){safe=0;break;}
        missing=lit;
        missing_ext=ext;
      } else {
        // Every falsified reason literal is an exact opposite of its
        // current assignment, and gives one parity contribution.
        if(v>0){parity^=1;false_lits[observed++]=NOT(lit);}
        else false_lits[observed++]=lit;
      }
    }
    if(!safe || observed+1!=row->width){
      if(safe && missing==INVALID_LIT){
        // Pure telemetry only. A fully conflicting parity is not
        // silently changed into a native CDCL conflict without a reason.
        if(parity)r32u_mismatches++;
      }
      continue;
    }
    r32u_implications++;
    if(!r32u_selected())continue;
    const unsigned target=parity?missing:NOT(missing);
    // Sound clause: all opposite assignments from the currently
    // satisfied row premise OR this forced XOR target literal.
    // Since whole equation is original-CNF-entailed, the clause
    // is *also* original-CNF-entailed regardless of current decisions.
    assert(EMPTY_STACK(solver->clause));
    PUSH_STACK(solver->clause,target);
    for(unsigned j=0;j<observed;j++)
       PUSH_STACK(solver->clause,false_lits[j]);
    if(row->width==2){
      kissat_new_binary_clause(solver,target,false_lits[0]);
      kissat_assign_binary(solver,target,false_lits[0]);
    }else{
      const reference ref=kissat_new_redundant_clause(solver,1);
      clause *reason=kissat_dereference_clause(solver,ref);
      kissat_assign_reference(solver,target,ref,reason);
    }
    CLEAR_STACK(solver->clause);
    r32u_added++;
    r32u_last_assigned=1;
    if(r32u_added<=16 || r32u_added%32==0){
      printf("c R32U_ASSIGN equation=%u target_ext=%u sign=%d level=%u"
             " decisions=%" PRIu64 " conflicts=%" PRIu64 "\n",
             index,missing_ext,parity?1:-1,solver->level,
             solver->statistics.decisions,solver->statistics.conflicts);
      fflush(stdout);
    }
    return;
  }
}
'''
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--kissat-root",type=Path,required=True)
    a=ap.parse_args()
    root=a.kissat_root/"src"
    api=root/"r32u_native_api.h"
    if api.exists():raise RuntimeError("R32u already patched")
    api.write_text(API)
    head=root/"r32b_shadow_core.h"
    h=head.read_text()
    h=once(h,"#define R32B_MAXVAR 2048","#define R32B_MAXVAR 4096","expand_bounded_var")
    h=once(h,"#define R32B_MAXCLAUSE 20000","#define R32B_MAXCLAUSE 60000","expand_bounded_clauses")
    h=once(h,"#define R32B_MAXLITS 210000","#define R32B_MAXLITS 650000","expand_bounded_lits")
    h=once(h,"#define R32B_MAXRECORD 22000","#define R32B_MAXRECORD 60000","expand_patterns")
    h=once(h,'|| !strcmp(mode,"r32k"))) ? 1 : 0;',
              '|| !strcmp(mode,"r32k") || !strcmp(mode,"r32u"))) ? 1 : 0;',
              "enable_source_capture_for_r32u")
    head.write_text(h)
    parse=root/"parse.c"
    s=parse.read_text()
    s=once(s,'#include "r32b_shadow_core.h"',
      '#include "r32b_shadow_core.h"\n'+SOURCE,"source_getter")
    parse.write_text(s)
    search=root/"search.c"
    s=search.read_text()
    s=once(s,"int kissat_search (kissat *solver) {",
           LIVE+"\nint kissat_search (kissat *solver) {","live_helpers")
    s=once(s,
       "  r32b_shadow_native_probe(NULL,0,9999);\n"
       "  if(r32s_on()) { r32s_next_mark=0; r32s_epoch=r32s_now_ms(); }\n"
       "  r32s_emit(solver,\"entry\",0);",
       "  r32b_shadow_native_probe(NULL,0,9999);\n"
       "  r32u_initialize(solver);\n"
       "  if(r32s_on()) { r32s_next_mark=0; r32s_epoch=r32s_now_ms(); }\n"
       "  r32s_emit(solver,\"entry\",0);",
       "live_initialization")
    s=once(s,
       "      clause *conflict = kissat_search_propagate (solver);\n"
       "      if (!conflict) r32b_native_snapshot (solver);\n"
       "      if (conflict) {",
       "      clause *conflict = kissat_search_propagate (solver);\n"
       "      if (!conflict) r32b_native_snapshot (solver);\n"
       "      if (!conflict) {\n"
       "        r32u_scan(solver);\n"
       "        if(r32u_last_assigned)continue; // BCP before a new decision\n"
       "      }\n"
       "      if (conflict) {",
       "propagation_and_reason")
    s=once(s,
       '  r32s_emit(solver,"finished",0);\n'
       '  report_search_result (solver, res);',
       '  r32s_emit(solver,"finished",0);\n'
       '  r32u_final(solver);\n'
       '  report_search_result (solver, res);',
       "final_report")
    search.write_text(s)
    print("R32U_ACTIVE_GF2_TRAIL_REASON_PATCH_OK",flush=True)

if __name__=="__main__":main()
