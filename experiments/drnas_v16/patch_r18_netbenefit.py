#!/usr/bin/env python3
"""R18: freeze mean paired log-time gain and uncertainty into native Kissat.

Only append R18 behavior to the already audited frozen R17/R16 patch chain.
Models/thresholds are from R17 random3 development only; no R18 data fits.
At 1024 conflicts, optional single restartint=50 at conflict 2048.
"""
from __future__ import annotations
import argparse,hashlib,json,math
from pathlib import Path
from patch_r17_risk import patch as patch_r17

MODEL=Path("experiments/drnas_v16/r18-frozen-model/netbenefit_model.json")
EXPECTED_SHA="3ac5e05ef62a5d5632f3493dcc19638bc75fdaecb186ad8aaf9324eca7b29602"
EXPECTED_BOOT=31
UPSTREAM_KISSAT="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
MODES=("r18_lcb","r18_mean")

def once(s,a,b):
 if s.count(a)!=1:
  raise RuntimeError("R18_C_SOURCE_ANCHOR_MISMATCH count="+str(s.count(a))+" at "+a[:100])
 return s.replace(a,b,1)
def arr(v):
 return "{"+",".join(format(float(x),".17g") for x in v)+"}"
def models():
 b=MODEL.read_bytes()
 if hashlib.sha256(b).hexdigest()!=EXPECTED_SHA:
  raise RuntimeError("R18 FROZEN MODEL SHA256 MISMATCH")
 m=json.loads(b)
 if (m["name"]!="DRNAS R18 direct paired log time advantage with bootstrap uncertainty v1"
     or m["trained_fold"]!="R17 random3_development ONLY"
     or m["trained_count"]!=40 or
     m["features"]!=["prior_r16_score","n_scaled","degree_cv",
                       "degree_gini","polarity_imbalance"] or
     len(m["bootstrap_coefficients"])!=EXPECTED_BOOT or
     not all(len(x)==6 for x in m["bootstrap_coefficients"]) or
     m["preregistered_rules"]["r18_lcb"]!={"predicted_mean_min":.05,"uncertainty_multiplier":.75,"lower_bound_min":0.0} or
     m["preregistered_rules"]["r18_mean"]!={"predicted_mean_min":.08,"uncertainty_multiplier":0.0,"lower_bound_min":-999.0} or
     not math.isfinite(m["loo_residual_rmse"]) or m["loo_residual_rmse"]<=0):
  raise RuntimeError("R18 TRAINING BOUNDARY OR MODEL CONFIG MISMATCH")
 return m

def patch(src):
 m=models()
 s=patch_r17(src)
 # Keep R16 native decision event and all comparator policy code untouched.
 s=once(s,
  '  const bool r16_active=r16_live50 || r16_live50_strict || r16_snapshot50 || r17_active;',
  '''  const bool r18_lcb=!strcmp(drnas_mode,"r18_lcb");
  const bool r18_mean=!strcmp(drnas_mode,"r18_mean");
  const bool r18_active=r18_lcb || r18_mean;
  const bool r16_active=r16_live50 || r16_live50_strict || r16_snapshot50 || r17_active || r18_active;''')
 coeff=",\n".join("                      "+arr(coef) for coef in m["bootstrap_coefficients"])
 additional=f'''
                  if (r18_active) {{
                    static const double r18_mu[5]={arr(m["feature_mean"])};
                    static const double r18_sd[5]={arr(m["feature_sd"])};
                    static const double r18_b[31][6]={{
{coeff}
                    }};
                    const double inputs[5]={{score,x[0],x[1],x[2],x[3]}};
                    double z[5]={{0.0}};
                    for (int k=0;k<5;k++) {{
                      z[k]=(inputs[k]-r18_mu[k])/r18_sd[k];
                      if (z[k]>3.0)z[k]=3.0;
                      if (z[k]< -3.0)z[k]= -3.0;
                    }}
                    double sum=0.0,sumsq=0.0;
                    for (int j=0;j<31;j++) {{
                      double predicted=r18_b[j][0];
                      for (int k=0;k<5;k++)predicted+=r18_b[j][k+1]*z[k];
                      sum+=predicted;
                      sumsq+=predicted*predicted;
                    }}
                    const double gain_mean=sum/31.0;
                    const double ensemble_var=fmax(0.0,sumsq/31.0-gain_mean*gain_mean);
                    const double gain_sigma=sqrt(ensemble_var+{format(m["loo_residual_rmse"]**2,".17g")});
                    const double multiplier=r18_lcb?0.75:0.0;
                    const double lower=gain_mean-multiplier*gain_sigma;
                    const double mean_floor=r18_lcb?0.05:0.08;
                    const double lower_floor=r18_lcb?0.0:-999.0;
                    selected=r13_n>=220 &&
                      isfinite(gain_mean) && isfinite(gain_sigma) &&
                      gain_mean>mean_floor && lower>lower_floor;
                    fprintf(stdout,
                      "c R18_DECISION conflict=%" PRIu64
                      " base=%.12f mean=%.12f sigma=%.12f lower=%.12f"
                      " selected=%d target=%" PRIu64
                      " model=%s\\n",
                      drnas_seen,score,gain_mean,gain_sigma,lower,
                      (int)selected,selected?(uint64_t)2048:(uint64_t)0,
                      r18_lcb?"lcb":"mean");
                    fflush(stdout);
                  }}
'''
 # R17 existing block follows the R16 base decision, R18 overwrites selection
 s=once(s,
  '                  if (r17_active) {\n',
  additional+'                  if (r17_active) {\n')
 for marker in ("c R18_DECISION","c R17_RISK","c R16_DECISION","DRNAS_V177_SWITCH"):
  if s.count(marker)!=1:
   raise RuntimeError("R18 NATIVE MODEL EVIDENCE MARKER MISSING "+marker)
 return s

if __name__=="__main__":
 parser=argparse.ArgumentParser()
 parser.add_argument("--kissat-root",type=Path,required=True)
 args=parser.parse_args()
 target=args.kissat_root/"src"/"search.c"
 result=patch(target.read_text())
 target.write_text(result)
 print("R18_NATIVE_FROZEN_DIRECT_GAIN_PATCHED",
       "model_sha256="+hashlib.sha256(MODEL.read_bytes()).hexdigest(),
       "kissat_pin="+UPSTREAM_KISSAT,
       "patched_sha256="+hashlib.sha256(result.encode()).hexdigest(),flush=True)
