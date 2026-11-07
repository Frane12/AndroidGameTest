#!/usr/bin/env python3
"""R22: instrument mature low-LBD *antecedent reasons in conflict analysis*.

Extend independently audited R21 ABI-safe birth-signature sidecar, rather than
changing clause layout. Distinguish antecedent clauses in 1-UIP from conflict
clauses and immediate direct implications. No resets or deletions. Frozen rule.
"""
from pathlib import Path
import argparse,hashlib,json
import patch_r21_age_lbd_reason as prev

PROTOCOL=Path("experiments/drnas_v16/r22_frozen_protocol.json")
def change(s,old,new,label):
 n=s.count(old)
 if n!=1:raise RuntimeError("R22_SOURCE_ANCHOR_MISMATCH "+label+" matches="+str(n))
 return s.replace(old,new,1)
def config():
 c=json.loads(PROTOCOL.read_text())
 g=c["preregistered_frozen_rule"]
 assert c["protocol"]=="DRNAS-R22-mature-lowLBD-conflict-chain-frozen-20261103-v1"
 assert c["instrumentation"]["upstream_kissat"]==prev.EXPECTED_KISSAT
 assert g["threshold_recent_scarcity"]==.105
 assert g["threshold_moderate_recent"]==.14
 assert g["threshold_increase_ratio"]==1.8
 assert g["action_conflict"]==2048 and g["n_min"]==220
 assert c["dataset"]["native_solves"]==3840
 prev.config() # Never bypass the vetted ABI-safe R21 source
 return c

def deduce(src):
 s=prev.patch_deduce(src)
 s=change(s,"static uint64_t drnas_r21_counts[11] = {0};",
          "static uint64_t drnas_r21_counts[14] = {0};","counter_capacity")
 s=change(s,"for (unsigned i=0;i<11;i++) destination[i]=drnas_r21_counts[i];",
          "for (unsigned i=0;i<14;i++) destination[i]=drnas_r21_counts[i];","counter_copy")
 s=change(s,"  INC (clauses_used);\n  c->used = MAX_USED;",
 '''  // R22 tracks *conflict-analysis antecedent reasons* only.
  // This is NOT direct propagation or the initial conflict clause.
  if (antecedent_reason) {
    const uint64_t r22_age=drnas_r21_age(solver,c);
    if (r22_age>=256) drnas_r21_counts[13]++;
    if (c->glue<=4) {
      drnas_r21_counts[12]++;
      if (r22_age>=256) drnas_r21_counts[11]++;
    }
  }
  INC (clauses_used);
  c->used = MAX_USED;''',"antecedent_lbd_age")
 return s

def search(src):
 s=prev.patch_search(src)
 s=change(s,
 '  const bool r16_active=r16_live50 || r16_live50_strict ||\n                        r16_snapshot50 || r20_active || r21_active;',
 '''  const bool r22_chain50=!strcmp(drnas_mode,"r22_chain50");
  const bool r22_inverse50=!strcmp(drnas_mode,"r22_inverse50");
  const bool r22_active=r22_chain50 || r22_inverse50;
  const bool r16_active=r16_live50 || r16_live50_strict ||
                        r16_snapshot50 || r20_active || r21_active || r22_active;''',"new_selector_modes")
 s=change(s,"  uint64_t r21_bins[4][11]={{0}};",
          "  uint64_t r21_bins[4][14]={{0}};","counter_matrix")
 s=change(s,
  '''                if (r21_active) {
                  drnas_r21_copy_counters (r21_bins[i]);''',
  '''                if (r21_active || r22_active)
                  drnas_r21_copy_counters (r21_bins[i]);
                if (r21_active) {''',"checkpoint_shared_copy")
 s=change(s,
  '''                if (r20_active) {
                  r20_clause_use[i]=solver->statistics.clauses_used;''',
  '''                if (r22_active &&
                    (r16_mark==256 || r16_mark==512 || r16_mark==1024)) {
                  fprintf(stdout,
                    "c R22_TRACE conflict=%" PRIu64
                    " antecedent=%" PRIu64
                    " low_antecedent=%" PRIu64
                    " mature_low_antecedent=%" PRIu64
                    " mature_antecedent=%" PRIu64
                    " analysis_total=%" PRIu64
                    " conflict_clauses=%" PRIu64
                    " birth_unknown=%" PRIu64 "\\n",
                    drnas_seen,r21_bins[i][6],r21_bins[i][12],
                    r21_bins[i][11],r21_bins[i][13],r21_bins[i][5],
                    r21_bins[i][7],r21_bins[i][10]);
                  fflush(stdout);
                }
                if (r20_active) {
                  r20_clause_use[i]=solver->statistics.clauses_used;''',"new_trace_tags")
 s=change(s,"                  if (selected) drnas_target=2048;",
 '''                  if (r22_active) {
                    const uint64_t d0=r21_bins[2][6]-r21_bins[1][6];
                    const uint64_t d1=r21_bins[3][6]-r21_bins[2][6];
                    const uint64_t u0=r21_bins[2][11]-r21_bins[1][11];
                    const uint64_t u1=r21_bins[3][11]-r21_bins[2][11];
                    const double prev_share=(double)u0/(1.0+(double)d0);
                    const double recent_share=(double)u1/(1.0+(double)d1);
                    // Fixed scarcity + unexpectedly weak maturation gate.
                    const bool weak=recent_share<0.105 ||
                      (recent_share<0.14 && recent_share<1.8*prev_share);
                    selected=r13_n>=220 && (r22_chain50 ? weak : !weak);
                    fprintf(stdout,
                      "c R22_DECISION conflict=%" PRIu64
                      " n=%u complete=%d antecedent_prev=%" PRIu64
                      " antecedent_recent=%" PRIu64
                      " mature_low_prev=%" PRIu64
                      " mature_low_recent=%" PRIu64
                      " share_prev=%.12f share_recent=%.12f"
                      " weak=%d selected=%d target=%" PRIu64
                      " model=%s\\n",
                      drnas_seen,r13_n,(int)ready,d0,d1,u0,u1,
                      prev_share,recent_share,(int)weak,(int)selected,
                      selected?(uint64_t)2048:(uint64_t)0,
                      r22_chain50?"chain":"inverse");
                    fflush(stdout);
                  }
                  if (selected) drnas_target=2048;''',"fixed_reaction_rule")
 for tag in ("c R22_TRACE","c R22_DECISION","c R21_TRACE","c R16_DECISION","DRNAS_V177_SWITCH"):
  if s.count(tag)!=1:raise RuntimeError("R22_MISSING_TAG "+tag)
 return s

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("--kissat-root",type=Path,required=True)
 args=ap.parse_args()
 config()
 root=args.kissat_root/"src"
 edits={
  "clause.c":prev.patch_clause_c,
  "deduce.c":deduce,
  "assign.c":prev.patch_assign,
  "search.c":search}
 transformed={}
 for p,fn in edits.items():
  target=root/p
  transformed[target]=fn(target.read_text())
 for p,c in transformed.items():p.write_text(c)
 print("R22_TRUE_CHAIN_LBD_AGE_PINNED_PATCH",
       "protocol_sha256="+hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
       "source_sha256="+hashlib.sha256("".join(transformed[k] for k in sorted(transformed)).encode()).hexdigest(),
       "kissat_pin="+prev.EXPECTED_KISSAT,flush=True)
if __name__=="__main__":main()
