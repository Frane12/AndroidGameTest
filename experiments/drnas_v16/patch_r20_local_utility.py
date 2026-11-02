#!/usr/bin/env python3
"""DRNAS R20 native local learned-clause usefulness gate.

Patch ONLY pinned Kissat search.c through existing audited R16 layers.
Use existing Kissat clauses_used counter (incremented by deduce.c whenever a
redundant clause is used as a reason) as an observational local reuse proxy.

No restarting the Kissat process, no learned-clause reset or deletion, and
no changes to upstream deduce.c. Fixed gate is frozen BEFORE test generation.
"""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from patch_r16_live_ridge import patch as patch_r16

CFG=Path("experiments/drnas_v16/r20_frozen_protocol.json")
EXPECTED_KISSAT="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
def once(s,old,new):
 n=s.count(old)
 if n!=1:raise RuntimeError("R20_SOURCE_ANCHOR_CHANGED "+str(n)+" at "+old[:100])
 return s.replace(old,new,1)
def load():
 c=json.loads(CFG.read_text())
 if (c["protocol"]!="DRNAS-R20-local-clause-reuse-prospective-20261102-v1"
     or c["source_kissat"]!=EXPECTED_KISSAT
     or c["candidate_rule"]["max_recent_over_previous_reuse"]!=.85
     or c["candidate_rule"]["min_previous_reuse"]!=.05
     or c["candidate_rule"]["max_recent_over_previous_prop"]!=.95
     or c["candidate_rule"]["min_recent_over_previous_glue"]!=1.05
     or c["dataset"]["attempts"]!=3360):
  raise RuntimeError("R20 PRE-REGISTERED GATE OR KISSAT PIN MODIFIED")
 return c
def patch(src):
 cfg=load()
 s=patch_r16(src)
 s=once(s,
  '  const bool r16_active=r16_live50 || r16_live50_strict || r16_snapshot50;',
  '''  const bool r20_local50=!strcmp(drnas_mode,"r20_local50");
  const bool r20_inverse50=!strcmp(drnas_mode,"r20_inverse50");
  const bool r20_active=r20_local50 || r20_inverse50;
  const bool r16_active=r16_live50 || r16_live50_strict || r16_snapshot50 || r20_active;''')
 s=once(s,
  '  uint64_t r16_cp_decisions[4]={0};',
  '''  uint64_t r16_cp_decisions[4]={0};
  uint64_t r20_clause_use[4]={0},r20_clause_improved[4]={0};''')
 s=once(s,
  '                r16_cp_stable[i]=(int)solver->stable;',
  '''                r16_cp_stable[i]=(int)solver->stable;
                if (r20_active) {
                  r20_clause_use[i]=solver->statistics.clauses_used;
                  r20_clause_improved[i]=solver->statistics.clauses_improved;
                  if (r16_mark==256 || r16_mark==512 || r16_mark==1024) {
                    fprintf(stdout,
                      "c R20_TRACE conflict=%" PRIu64
                      " used=%" PRIu64 " improved=%" PRIu64
                      " learned=%" PRIu64 " props=%" PRIu64
                      " glue=%.12f\\n",
                      drnas_seen,r20_clause_use[i],r20_clause_improved[i],
                      r16_cp_learned[i],r16_cp_props[i],r16_cp_glue[i]);
                    fflush(stdout);
                  }
                }''')
 s=once(s,
  '                  selected=r13_n>=220 && isfinite(score) && score>threshold;',
  '''                  selected=r13_n>=220 && isfinite(score) && score>threshold;
                  if (r20_active) {
                    const uint64_t u_prev=r20_clause_use[2]-r20_clause_use[1];
                    const uint64_t u_recent=r20_clause_use[3]-r20_clause_use[2];
                    const uint64_t l_prev=r16_cp_learned[2]-r16_cp_learned[1];
                    const uint64_t l_recent=r16_cp_learned[3]-r16_cp_learned[2];
                    const double reuse_prev=(double)u_prev/(1.0+(double)l_prev);
                    const double reuse_recent=(double)u_recent/(1.0+(double)l_recent);
                    const double prop_prev=
                      (double)(r16_cp_props[2]-r16_cp_props[1])/
                      (double)(r16_cp_conflicts[2]-r16_cp_conflicts[1]);
                    const double prop_recent=
                      (double)(r16_cp_props[3]-r16_cp_props[2])/
                      (double)(r16_cp_conflicts[3]-r16_cp_conflicts[2]);
                    const double glue_prev=r16_cp_glue[2];
                    const double glue_recent=r16_cp_glue[3];
                    const bool reuse_decline=reuse_prev>=0.05 &&
                      reuse_recent<0.85*reuse_prev;
                    const bool propagation_decline=prop_recent<0.95*prop_prev;
                    const bool glue_worse=glue_recent>1.05*glue_prev;
                    const bool stagnating=reuse_decline &&
                      (propagation_decline || glue_worse);
                    selected=r13_n>=220 && (r20_local50 ?
                      stagnating : !stagnating);
                    fprintf(stdout,
                      "c R20_DECISION conflict=%" PRIu64
                      " n=%u complete=%d used_prev=%" PRIu64
                      " used_recent=%" PRIu64
                      " learned_prev=%" PRIu64
                      " learned_recent=%" PRIu64
                      " reuse_prev=%.12f reuse_recent=%.12f"
                      " prop_prev=%.12f prop_recent=%.12f"
                      " glue_prev=%.12f glue_recent=%.12f"
                      " stagnating=%d selected=%d target=%" PRIu64
                      " model=%s\\n",
                      drnas_seen,r13_n,(int)ready,u_prev,u_recent,
                      l_prev,l_recent,reuse_prev,reuse_recent,
                      prop_prev,prop_recent,glue_prev,glue_recent,
                      (int)stagnating,(int)selected,
                      selected?(uint64_t)2048:(uint64_t)0,
                      r20_local50?"local":"inverse");
                    fflush(stdout);
                  }''')
 for marker in ("c R20_TRACE","c R20_DECISION","c R16_DECISION",
                "DRNAS_V177_SWITCH","c R6_TRACE"):
  if s.count(marker)!=1:raise RuntimeError("R20 EXPECTED SINGLE SOURCE MARKER "+marker)
 return s
if __name__=="__main__":
 ap=argparse.ArgumentParser()
 ap.add_argument("--kissat-root",type=Path,required=True)
 args=ap.parse_args()
 dest=args.kissat_root/"src/search.c"
 edited=patch(dest.read_text())
 dest.write_text(edited)
 print("R20_LOCAL_CLAUSE_REUSE_PATCHED",
       "protocol_sha256="+hashlib.sha256(CFG.read_bytes()).hexdigest(),
       "kissat_pin="+EXPECTED_KISSAT,
       "search_sha256="+hashlib.sha256(edited.encode()).hexdigest(),flush=True)
