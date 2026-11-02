#!/usr/bin/env python3
"""DRNAS R21: birth-age, LBD and actual implication-role learned-clause telemetry.

All controls use the same instrumented native binary, except separate original
Kissat and V15.3.1 external references. Changes only on R21 experiment branch.
The 64-bit birth counter is stored in each nonbinary clause's native structure;
it survives Kissat arena relocation (no pointer/hash age approximation).
"""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from patch_r20_local_utility import patch as patch_r20
from patch_r20_local_utility import EXPECTED_KISSAT

CFG=Path("experiments/drnas_v16/r21_frozen_protocol.json")
NCOUNTERS=10
def replace_one(s,old,new,what):
 count=s.count(old)
 if count!=1:raise RuntimeError(f"R21_SOURCE_ANCHOR_MISMATCH {what} count={count}")
 return s.replace(old,new,1)
def config():
 c=json.loads(CFG.read_text())
 gate=c["frozen_gate"]
 if (c["protocol"]!="DRNAS-R21-true-clause-birth-lbd-implication-role-frozen-20261102-v1"
    or c["history"]["pinned_kissat_commit"]!=EXPECTED_KISSAT
    or gate["low_lbd_max"]!=4 or gate["mature_age_conflicts"]!=256
    or gate["min_prior_lowLBD_mature_reason_share"]!=.08
    or gate["max_recent_to_prior_share_ratio"]!=.85
    or gate["action_at_conflicts"]!=2048 or gate["restartint"]!=50
    or c["dataset"]["expected_native_executions"]!=3840):
  raise RuntimeError("R21_FROZEN_PROTOCOL_OR_PIN_CHANGED")
 return c
def patch_clause_h(src):
 src=replace_one(src,'#include <stdbool.h>','#include <stdbool.h>\n#include <stdint.h>',"clause_h_include")
 return replace_one(src,"  unsigned searched;","  uint64_t r21_birth_conflicts;\n  unsigned searched;","clause_birth_field")
def patch_clause_c(src):
 return replace_one(src,
  '  init_clause (c, redundant, glue, size);\n  memcpy (c->lits, lits, size * sizeof (unsigned));',
  '''  init_clause (c, redundant, glue, size);
  c->r21_birth_conflicts = solver->statistics.conflicts;
  memcpy (c->lits, lits, size * sizeof (unsigned));''',"birth_write")
def patch_deduce(src):
 anchor="static inline void mark_clause_as_used (kissat *solver, clause *c) {"
 metrics='''// DRNAS R21 research-only counters, one Kissat process = one SAT attempt.
// Indexes: 0=all implication reasons,1=LBD<=4 implication reasons,
// 2=mature(age>=256 conflicts) LBD<=4 reasons,3=mature all reasons,
// 4=LBD>4 implication reasons,5=all redundant uses in conflict analysis,
// 6=antecedent reason uses,7=conflict clause uses,
// 8=LBD<=4 conflict-analysis uses,9=mature LBD<=4 conflict-analysis uses.
static uint64_t drnas_r21_counts[10] = {0};

void drnas_r21_copy_counters (uint64_t *destination) {
  for (unsigned i=0;i<10;i++) destination[i]=drnas_r21_counts[i];
}

static inline uint64_t drnas_r21_age (kissat *solver, clause *c) {
  const uint64_t now=solver->statistics.conflicts;
  return now>=c->r21_birth_conflicts ? now-c->r21_birth_conflicts : 0;
}

// Called on assigning a literal via an explicit large learned clause.
// This includes immediate first-UIP asserting clauses and later propagation.
void drnas_r21_track_direct_implication (kissat *solver, clause *c) {
  if (!c->redundant) return;
  const bool low=c->glue<=4;
  const bool mature=drnas_r21_age(solver,c)>=256;
  drnas_r21_counts[0]++;
  if (low) drnas_r21_counts[1]++;
  if (low && mature) drnas_r21_counts[2]++;
  if (mature) drnas_r21_counts[3]++;
  if (!low) drnas_r21_counts[4]++;
}

'''
 src=replace_one(src,anchor,metrics+'static inline void mark_clause_as_used (kissat *solver, clause *c, bool antecedent_reason) {',"deduce_hook")
 src=replace_one(src,
  '  INC (clauses_used);\n  c->used = MAX_USED;',
  '''  // Record LBD and true clause age BEFORE promotion changes glue.
  drnas_r21_counts[5]++;
  if (antecedent_reason) drnas_r21_counts[6]++;
  else drnas_r21_counts[7]++;
  if (c->glue<=4) {
    drnas_r21_counts[8]++;
    if (drnas_r21_age(solver,c)>=256) drnas_r21_counts[9]++;
  }
  INC (clauses_used);
  c->used = MAX_USED;''',"deduce_counters")
 src=replace_one(src,'mark_clause_as_used (solver, conflict);','mark_clause_as_used (solver, conflict, false);',"conflict_clause_role")
 src=replace_one(src,'mark_clause_as_used (solver, reason);','mark_clause_as_used (solver, reason, true);',"antecedent_reason_role")
 return src
def patch_assign(src):
 src=replace_one(src,
  'void kissat_assign_reference (kissat *solver, unsigned lit, reference ref,',
  '''extern void drnas_r21_track_direct_implication (kissat *, clause *);

void kissat_assign_reference (kissat *solver, unsigned lit, reference ref,''',"assign_decl")
 return replace_one(src,
  '  LOGREF (ref, "assign %s reason", LOGLIT (lit));',
  '''  drnas_r21_track_direct_implication (solver, reason);
  LOGREF (ref, "assign %s reason", LOGLIT (lit));''',"assign_hook")
def patch_search(src):
 s=patch_r20(src)
 s=replace_one(s,
  '  const bool r16_active=r16_live50 || r16_live50_strict || r16_snapshot50 || r20_active;',
  '''  const bool r21_local50=!strcmp(drnas_mode,"r21_mature_low50");
  const bool r21_inverse50=!strcmp(drnas_mode,"r21_inverse50");
  const bool r21_active=r21_local50 || r21_inverse50;
  const bool r16_active=r16_live50 || r16_live50_strict ||
                        r16_snapshot50 || r20_active || r21_active;''',"new_gate_modes")
 s=replace_one(s,
  '  uint64_t r20_clause_use[4]={0};',
  '''  uint64_t r20_clause_use[4]={0};
  uint64_t r21_bins[4][10]={{0}};
  extern void drnas_r21_copy_counters (uint64_t *);''',"native_bins")
 s=replace_one(s,
  '                if (r20_active) {\n                  r20_clause_use[i]=solver->statistics.clauses_used;',
  '''                if (r21_active) {
                  drnas_r21_copy_counters (r21_bins[i]);
                  if (r16_mark==256 || r16_mark==512 || r16_mark==1024) {
                    fprintf(stdout,
                      "c R21_TRACE conflict=%" PRIu64
                      " direct=%" PRIu64 " low=%" PRIu64
                      " oldlow=%" PRIu64 " old=%" PRIu64
                      " high=%" PRIu64 " analysis=%" PRIu64
                      " antecedent=%" PRIu64 " conflictreason=%" PRIu64
                      " analysislow=%" PRIu64 " analysisoldlow=%" PRIu64 "\\n",
                      drnas_seen,r21_bins[i][0],r21_bins[i][1],
                      r21_bins[i][2],r21_bins[i][3],r21_bins[i][4],
                      r21_bins[i][5],r21_bins[i][6],r21_bins[i][7],
                      r21_bins[i][8],r21_bins[i][9]);
                    fflush(stdout);
                  }
                }
                if (r20_active) {
                  r20_clause_use[i]=solver->statistics.clauses_used;''',"checkpoint_capture")
 s=replace_one(s,
  '                  if (selected) drnas_target=2048;',
  '''                  if (r21_active) {
                    const uint64_t d0=r21_bins[2][0]-r21_bins[1][0];
                    const uint64_t d1=r21_bins[3][0]-r21_bins[2][0];
                    const uint64_t oldlow0=r21_bins[2][2]-r21_bins[1][2];
                    const uint64_t oldlow1=r21_bins[3][2]-r21_bins[2][2];
                    const double share0=(double)oldlow0/(1.0+(double)d0);
                    const double share1=(double)oldlow1/(1.0+(double)d1);
                    const bool bottleneck=share0>=0.08 &&
                                           share1<0.85*share0;
                    selected=r13_n>=220 &&
                             (r21_local50 ? bottleneck : !bottleneck);
                    fprintf(stdout,
                      "c R21_DECISION conflict=%" PRIu64
                      " n=%u complete=%d direct_prev=%" PRIu64
                      " direct_recent=%" PRIu64
                      " mature_low_prev=%" PRIu64
                      " mature_low_recent=%" PRIu64
                      " share_prev=%.12f share_recent=%.12f"
                      " signal=%d selected=%d target=%" PRIu64
                      " role_analysis=%" PRIu64
                      " role_antecedent=%" PRIu64
                      " model=%s\\n",
                      drnas_seen,r13_n,(int)ready,d0,d1,oldlow0,oldlow1,
                      share0,share1,(int)bottleneck,(int)selected,
                      selected?(uint64_t)2048:(uint64_t)0,
                      r21_bins[3][5],r21_bins[3][6],
                      r21_local50?"maturelow":"inverse");
                    fflush(stdout);
                  }
                  if (selected) drnas_target=2048;''',"frozen_gate")
 for marker in ("c R21_TRACE","c R21_DECISION","c R20_TRACE",
                "c R20_DECISION","c R16_DECISION","DRNAS_V177_SWITCH"):
  if s.count(marker)!=1:
   raise RuntimeError("R21_SRC_EXPECTED_EXACT_MARKER "+marker+" count="+str(s.count(marker)))
 return s
def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--kissat-root",type=Path,required=True)
 a=ap.parse_args()
 config()
 root=a.kissat_root/"src"
 edits={
 "clause.h":patch_clause_h,
 "clause.c":patch_clause_c,
 "deduce.c":patch_deduce,
 "assign.c":patch_assign,
 "search.c":patch_search}
 targets={}
 # Transform all in memory; if any anchor fails, DO NOT modify upstream tree.
 for name,fun in edits.items():
  target=root/name
  content=fun(target.read_text())
  targets[target]=content
 for dest,txt in targets.items():dest.write_text(txt)
 print("R21_TRUE_CLAUSE_BIRTH_LBD_ROLE_PINNED_PATCHED",
  "protocol_sha256="+hashlib.sha256(CFG.read_bytes()).hexdigest(),
  "kissat_pin="+EXPECTED_KISSAT,
  "source_sha256="+hashlib.sha256(
    "".join(targets[x] for x in sorted(targets)).encode()).hexdigest(),flush=True)
if __name__=="__main__":main()
