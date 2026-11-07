#!/usr/bin/env python3
"""R17 frozen harm-probability model, trained ONLY on R16 random3_development.

The R16 holdout and community folds are forbidden for model fitting and threshold
selection. We model P(forced restartint=50 at conflict 2048 is >20% slower than
same-runner monitor) using a small regularized logistic regression at conflict 1024.
This is a risk estimate, not a theorem or independent SAT validation.
"""
from __future__ import annotations
import csv,hashlib,json,math,statistics,subprocess
from pathlib import Path

ROOT=Path("experiments/drnas_v16")
TRAIN=ROOT/"r16-results/current/formula_features.csv"
BASE=ROOT/"r15-results/current/frozen_trained_models.json"
PROTO=ROOT/"r16_frozen_live_protocol.json"
OUT=Path("r17-frozen-model")
FIELDS=("r16_score","n_scaled","degree_cv","degree_gini","polarity_imbalance")
BLOBS={
 "training_formula_features":"0a51dead07645bf6e84bb16a44dfba84f9e4526c",
 "prior_r15_model":"d005747f177008172b49cef5f0b8a6f29c3ffc46",
 "prior_r16_protocol":"d0ba1f19c73e082026e0f385dc8ce39bff99a7c5"
}
THRESHOLDS={"r17_risk30":.30,"r17_risk45":.45}
LAM=.15
STEPS=2500
LEARNING=.35

def fail(msg):raise RuntimeError("R17_RISK_TRAIN_AUDIT_FAILURE "+msg)
def blob(p):return subprocess.check_output(["git","hash-object",str(p)],text=True).strip()
def logistic(z):
 z=min(40.,max(-40.,z))
 return 1./(1.+math.exp(-z))
def train(x,y,mu,sd):
 n=len(y);a=[0.]*(len(mu)+1)
 p=max(.001,min(.999,sum(y)/n))
 a[0]=math.log(p/(1-p))
 for _ in range(STEPS):
  gradients=[0.]*(len(a))
  for row,label in zip(x,y):
   xstd=[max(-3.,min(3.,(v-m)/s)) for v,m,s in zip(row,mu,sd)]
   e=logistic(a[0]+sum(w*v for w,v in zip(a[1:],xstd)))-label
   gradients[0]+=e
   for j,v in enumerate(xstd):gradients[j+1]+=e*v
  a[0]-=LEARNING*gradients[0]/n
  for j in range(1,len(a)):
   a[j]-=LEARNING*(gradients[j]/n+LAM*a[j])
 return a

def main():
 for p,expected in ((TRAIN,BLOBS["training_formula_features"]),
                    (BASE,BLOBS["prior_r15_model"]),
                    (PROTO,BLOBS["prior_r16_protocol"])):
  if blob(p)!=expected:fail("source changed: "+str(p))
 with TRAIN.open(newline="") as f:rows=list(csv.DictReader(f))
 if len(rows)!=160 or len({r["formula_sha256"] for r in rows})!=160:
  fail("R16 source formula count/hash")
 dev=[r for r in rows if r["fold"]=="random3_development"]
 if len(dev)!=60:fail("R16 random3 development not 60")
 # Do not even read the R16 test labels. Explicit allowed-row filtering.
 eligible=[r for r in dev if int(r["n"])>=220
           and r["r16_live50_score_median"]]
 if len(eligible)!=39:fail("expected exactly 39 development + scored CNFs")
 if any(r["fold"]!="random3_development" for r in eligible):
  fail("test label leakage")
 observations=[]
 x=[];y=[]
 for r in eligible:
  m=float(r["monitor"]);f=float(r["r11_2048_50"])
  if m<=0 or f<=0:fail("nonpositive training PAR2")
  score=float(r["r16_live50_score_median"])
  feats=[score,float(r["n"])/240.,float(r["degree_cv"]),
         float(r["degree_gini"]),float(r["polarity_imbalance"])]
  if not all(math.isfinite(v) for v in feats):fail("invalid feature")
  harm=int(f>m*1.20)
  x.append(feats);y.append(harm)
  observations.append(dict(formula_sha256=r["formula_sha256"],n=int(r["n"]),
      forced50_par2=f,monitor_par2=m,score=score,
      forced50_log_gain=math.log(m/f),harm_gt20_percent=harm))
 mu=[statistics.mean(r[j] for r in x) for j in range(len(FIELDS))]
 sd=[max(1e-8,statistics.pstdev([r[j] for r in x]))
     for j in range(len(FIELDS))]
 coef=train(x,y,mu,sd)
 # Cross-fitted diagnostics on training group only. NOT an external test.
 loo=[]
 for i in range(len(eligible)):
  restx=x[:i]+x[i+1:];resty=y[:i]+y[i+1:]
  mean=[statistics.mean(t[j] for t in restx) for j in range(len(FIELDS))]
  std=[max(1e-8,statistics.pstdev([t[j] for t in restx])) for j in range(len(FIELDS))]
  w=train(restx,resty,mean,std)
  z=[max(-3.,min(3.,(v-m)/s)) for v,m,s in zip(x[i],mean,std)]
  loo.append(logistic(w[0]+sum(a*b for a,b in zip(w[1:],z))))
 brier=sum((v-target)**2 for v,target in zip(loo,y))/len(y)
 model={
  "model":"DRNAS R17 harm probability veto v1",
  "output":"P(force50/monitor PAR2 > 1.20) at fixed conflict 2048",
  "input_checkpoint":1024,
  "intervention_checkpoint":2048,
  "feature_order":list(FIELDS),
  "intercept":coef[0],
  "coefficients":coef[1:],
  "mu":mu,"sd":sd,
  "feature_z_clip":3.0,
  "ridge_penalty":LAM,
  "training_iterations":STEPS,
  "train_count":len(eligible),
  "training_fold":"R16 random3_development ONLY",
  "training_labels_kind":"retrospective same-formula forced50 vs monitor, 3 repeats",
  "training_sha256":sorted(r["formula_sha256"] for r in eligible),
  "risk_label_positive":sum(y),
  "risk_label_negative":len(y)-sum(y),
  "risk_label_threshold_ratio":1.20,
  "out_of_fold_dev_brier":brier,
  "frozen_approved_risk_limits":THRESHOLDS,
  "frozen_minimum_r16_gain_score":.25,
  "frozen_eligible_n_min":220,
  "model_github_source_git_blobs":BLOBS,
  "prohibition":"Do NOT use ANY R16 random3_test or community labels or new R17 test results for fitting."
 }
 OUT.mkdir(parents=True,exist_ok=True)
 (OUT/"risk_model.json").write_text(json.dumps(model,indent=2,sort_keys=True)+"\n")
 (OUT/"train_audit.json").write_text(json.dumps({
  "source_rows":len(rows),"development_formula_count":len(dev),
  "trained_formulas":len(eligible),"risk_positive":sum(y),
  "other_eligible_random3_development_missing_1024":40-len(eligible),
  "risk_train_loo_brier":brier,"trained_input_sha256":hashlib.sha256(
   json.dumps(observations,sort_keys=True).encode()).hexdigest(),
  "model_sha256":hashlib.sha256((OUT/"risk_model.json").read_bytes()).hexdigest(),
  "training_only":True,"risk_limits":THRESHOLDS},indent=2,sort_keys=True)+"\n")
 if len(coef)!=len(FIELDS)+1:fail("bad dimension")
 print("R17_RISK_FROZEN_DEVELOPMENT_MODEL",json.dumps({
   "formulas":len(eligible),"positive":sum(y),"loo_brier":brier,
   "coefficients":coef,"sha256":hashlib.sha256((OUT/"risk_model.json").read_bytes()).hexdigest()},sort_keys=True),flush=True)

if __name__=="__main__":
 main()
