#!/usr/bin/env python3
"""R17 native Kissat harm-risk veto on top of the UNCHANGED R16 ridge score.

At conflict 1024, calculate frozen R16 benefit score. Only if it clears .25
and a second model trained from R16 *development* estimates risk <= .30/.45,
permit the single restartint=50 change at conflict 2048. No clause reset.
"""
from __future__ import annotations
import argparse,hashlib,json,math
from pathlib import Path
from patch_r16_live_ridge import patch as patch_r16

MODEL=Path("experiments/drnas_v16/r17-frozen-model/risk_model.json")
UPSTREAM_PIN="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
EXPECTED_FEATURES=["r16_score","n_scaled","degree_cv","degree_gini","polarity_imbalance"]
MODES={"r17_risk30":.30,"r17_risk45":.45}

def replace_once(s,old,new):
 n=s.count(old)
 if n!=1:
  raise RuntimeError(f"R17_FROZEN_C_ANCHOR_MISMATCH count={n}: {old[:120]}")
 return s.replace(old,new,1)

def values(a):
 return "{"+",".join(format(float(x),".17g") for x in a)+"}"

def load():
 m=json.loads(MODEL.read_text())
 if (m["model"]!="DRNAS R17 harm probability veto v1" or
     m["feature_order"]!=EXPECTED_FEATURES or
     m["frozen_approved_risk_limits"]!=MODES or
     m["training_fold"]!="R16 random3_development ONLY" or
     m["train_count"]!=39 or
     m["risk_label_threshold_ratio"]!=1.20 or
     m["frozen_minimum_r16_gain_score"]!=.25 or
     m["frozen_eligible_n_min"]!=220 or
     len(m["mu"])!=5 or len(m["sd"])!=5 or len(m["coefficients"])!=5 or
     not all(math.isfinite(z) for z in
       [m["intercept"],*m["mu"],*m["sd"],*m["coefficients"]])):
  raise RuntimeError("R17 MODEL OR PROVENANCE INVALID")
 return m

def patch(source):
 m=load()
 s=patch_r16(source)
 # The base model is unchanged. Only two extra named modes are added.
 old='  const bool r16_active=r16_live50 || r16_live50_strict || r16_snapshot50;'
 new='''  const bool r17_risk30=!strcmp(drnas_mode,"r17_risk30");
  const bool r17_risk45=!strcmp(drnas_mode,"r17_risk45");
  const bool r17_active=r17_risk30 || r17_risk45;
  const bool r16_active=r16_live50 || r16_live50_strict || r16_snapshot50 || r17_active;'''
 s=replace_once(s,old,new)
 # Native score is a learned *expected benefit*, not a calibrated risk.
 # Use a separate logistic model for P(>20% harm) that is frozen BEFORE R17 tests.
 old='''                  selected=r13_n>=220 && isfinite(score) && score>threshold;
                  if (selected) drnas_target=2048;'''
 new=f'''                  selected=r13_n>=220 && isfinite(score) && score>threshold;
                  if (r17_active) {{
                    static const double r17_mu[5]={values(m["mu"])};
                    static const double r17_sd[5]={values(m["sd"])};
                    static const double r17_coef[5]={values(m["coefficients"])};
                    const double r17_inputs[5]={{score,x[0],x[1],x[2],x[3]}};
                    const double r17_maxrisk=r17_risk30?0.30:0.45;
                    double log_odds={format(float(m["intercept"]),".17g")};
                    for (int k=0;k<5;k++) {{
                      double z=(r17_inputs[k]-r17_mu[k])/r17_sd[k];
                      if (z>3.0)z=3.0;
                      if (z< -3.0)z= -3.0;
                      log_odds+=r17_coef[k]*z;
                    }}
                    if (log_odds>40.0)log_odds=40.0;
                    if (log_odds< -40.0)log_odds= -40.0;
                    const double harm_risk=1.0/(1.0+exp(-log_odds));
                    selected=selected && isfinite(harm_risk) && harm_risk<=r17_maxrisk;
                    fprintf(stdout,
                      "c R17_RISK conflict=%" PRIu64
                      " benefit=%.12f risk=%.12f risk_limit=%.12f"
                      " selected=%d target=%d\\\\n",
                      drnas_seen,score,harm_risk,r17_maxrisk,
                      (int)selected,selected?2048:0);
                    fflush(stdout);
                  }}
                  if (selected) drnas_target=2048;'''
 s=replace_once(s,old,new)
 for marker in ["c R17_RISK","c R16_DECISION","DRNAS_V177_SWITCH"]:
  if s.count(marker)!=1:
   raise RuntimeError("R17 REQUIRED C TELEMETRY MARKER MISSING "+marker)
 return s

if __name__=="__main__":
 parser=argparse.ArgumentParser()
 parser.add_argument("--kissat-root",required=True,type=Path)
 args=parser.parse_args()
 target=args.kissat_root/"src"/"search.c"
 new=patch(target.read_text())
 target.write_text(new)
 print("R17_NATIVE_FROZEN_RISK_PATCHED",UPSTREAM_PIN,
   "model_sha256="+hashlib.sha256(MODEL.read_bytes()).hexdigest(),
   "patched_sha256="+hashlib.sha256(new.encode()).hexdigest(),flush=True)
