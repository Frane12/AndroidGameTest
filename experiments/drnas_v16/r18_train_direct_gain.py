#!/usr/bin/env python3
"""R18: frozen direct *paired log time advantage* regression with uncertainty.

Labels: log(PAR2_monitor/PAR2_forced2048_50) on R17 random3_development
ONLY (n>=220). No R17 random3_test or community folds are read for
model fitting. 31 fixed-seed bootstrap ridge regressors plus leave-one-
FORMULA-out predictive residual scale give a conservative lower score.

Sigma and lower bounds are HEURISTICS, not calibrated probabilities or
formal confidence intervals. No R18 test labels are used to train/tune.
"""
from __future__ import annotations
import csv,hashlib,json,math,random,statistics,subprocess
from collections import defaultdict
from pathlib import Path

ROOT=Path("experiments/drnas_v16")
FEATURES=ROOT/"r17-results/current/formula_features.csv"
DECISIONS=ROOT/"r17-results/current/native_risk_decisions.csv"
CONFIG=ROOT/"r17_frozen_protocol.json"
R15=ROOT/"r15-results/current/frozen_trained_models.json"
OUT=Path("r18-frozen-model")
PINS={
  "r17_formula_features_blob":"cc8e5c9f80bcb6babb697048be99e775354aefa5",
  "r17_native_decisions_blob":"36904cdc744362f3e00bb71723277749f97f34d3",
  "r17_protocol_blob":"c07c933e81faaf5846f27f910699730f0a78b149",
  "r15_base_model_blob":"d005747f177008172b49cef5f0b8a6f29c3ffc46",
}
NBOOT=31
RIDGE_LAMBDA=2.0
SEED=18181817
FIELDS=("prior_r16_score","n_scaled","degree_cv","degree_gini","polarity_imbalance")
TARGET_CLIP=1.5
RULES={
 "r18_lcb":dict(predicted_mean_min=.05,uncertainty_multiplier=.75,lower_bound_min=0.0),
 "r18_mean":dict(predicted_mean_min=.08,uncertainty_multiplier=0.0,lower_bound_min=-999.0)
}

def fail(message):raise RuntimeError("R18_FROZEN_TRAIN_AUDIT_FAIL "+message)
def gitblob(path):return subprocess.check_output(["git","hash-object",str(path)],text=True).strip()
def loadcsv(path):
 with path.open(newline="") as f:return list(csv.DictReader(f))
def solve_linear(a,b):
 # 6x6 ridge normal equations with deterministic pivoted Gaussian elimination
 n=len(b)
 aug=[list(row)+[b[i]] for i,row in enumerate(a)]
 for k in range(n):
  best=max(range(k,n),key=lambda i:abs(aug[i][k]))
  if abs(aug[best][k])<1e-10:fail("ill-conditioned ridge matrix")
  aug[k],aug[best]=aug[best],aug[k]
  scale=aug[k][k]
  for j in range(k,n+1):aug[k][j]/=scale
  for i in range(n):
   if i==k:continue
   factor=aug[i][k]
   if factor:
    for j in range(k,n+1):aug[i][j]-=factor*aug[k][j]
 return [aug[i][-1] for i in range(n)]
def fit(xs,ys,mu,sd,weights=None):
 d=len(mu);xtx=[[0.]*(d+1) for _ in range(d+1)];xty=[0.]*(d+1)
 if weights is None:weights=[1]*len(xs)
 total=sum(weights)
 for raw,y,w in zip(xs,ys,weights):
  if not w:continue
  vals=[1.]+[max(-3.,min(3.,(v-m)/s)) for v,m,s in zip(raw,mu,sd)]
  for i in range(d+1):
   xty[i]+=w*vals[i]*y/total
   for j in range(d+1):xtx[i][j]+=w*vals[i]*vals[j]/total
 for i in range(1,d+1):xtx[i][i]+=RIDGE_LAMBDA
 xtx[0][0]+=1e-7
 return solve_linear(xtx,xty)
def predict(model,raw,mu,sd):
 z=[max(-3.,min(3.,(v-m)/s)) for v,m,s in zip(raw,mu,sd)]
 return model[0]+sum(a*b for a,b in zip(model[1:],z))
def main():
 for p,k in ((FEATURES,"r17_formula_features_blob"),(DECISIONS,"r17_native_decisions_blob"),
             (CONFIG,"r17_protocol_blob"),(R15,"r15_base_model_blob")):
  if gitblob(p)!=PINS[k]:fail("source mutated: "+str(p))
 features=loadcsv(FEATURES)
 decisions=loadcsv(DECISIONS)
 if len(features)!=160 or len({x["formula_sha256"] for x in features})!=160:
  fail("R17 verified source formula count/hash")
 if len(decisions)!=960:fail("R17 native decision count expected 960")
 dev=[f for f in features if f["fold"]=="random3_development"]
 if len(dev)!=60:fail("unexpected train fold")
 candidates=[f for f in dev if int(f["n"])>=220]
 if len(candidates)!=40:fail("need 40 eligible R17 development CNFs")
 byform=defaultdict(list)
 for d in decisions:
  if d["arm"]=="r17_risk30" and d["fold"]=="random3_development":
   byform[d["formula"]].append(d)
 xs=[];ys=[];identities=[];observations=[]
 for f in sorted(candidates,key=lambda f:f["formula_sha256"]):
  decisions_for=byform[f["formula"]]
  if len(decisions_for)!=3:fail("missing 3 independent prefix repetitions")
  scores=[float(d["r16_benefit_score"]) for d in decisions_for if d["r16_benefit_score"]]
  if len(scores)!=3:fail("missing prior frozen score at 1024")
  score=statistics.median(scores)
  m=float(f["monitor"]);forced=float(f["r11_2048_50"])
  if m<=0 or forced<=0:fail("nonpositive PAR-2")
  y=max(-TARGET_CLIP,min(TARGET_CLIP,math.log(m/forced)))
  x=[score,int(f["n"])/240.,float(f["degree_cv"]),
     float(f["degree_gini"]),float(f["polarity_imbalance"])]
  if not all(math.isfinite(v) for v in x+[y]):fail("nonfinite dev value")
  xs.append(x);ys.append(y);identities.append(f["formula_sha256"])
  observations.append(dict(formula_sha256=f["formula_sha256"],n=int(f["n"]),
    frozen_prior_score=score,log_gain_target=y,monitor_PAR2=m,forced50_PAR2=forced))
 if len(set(identities))!=40:fail("training duplicate formula")
 d=len(FIELDS)
 mu=[statistics.mean(a[j] for a in xs) for j in range(d)]
 sd=[max(1e-8,statistics.pstdev([a[j] for a in xs])) for j in range(d)]
 full=fit(xs,ys,mu,sd)
 rng=random.Random(SEED)
 ensemble=[]
 for _ in range(NBOOT):
  weights=[0]*len(xs)
  for _ in range(len(xs)):weights[rng.randrange(len(xs))]+=1
  ensemble.append(fit(xs,ys,mu,sd,weights))
 # Leave-one-formula-out errors to estimate predictive residual noise
 errors=[]
 for i in range(len(xs)):
  subset=[row for j,row in enumerate(xs) if j!=i]
  labels=[v for j,v in enumerate(ys) if j!=i]
  leave_mu=[statistics.mean(v[j] for v in subset) for j in range(d)]
  leave_sd=[max(1e-8,statistics.pstdev([v[j] for v in subset])) for j in range(d)]
  fitted=fit(subset,labels,leave_mu,leave_sd)
  pred=predict(fitted,xs[i],leave_mu,leave_sd)
  errors.append(ys[i]-pred)
 # A robust spread floor: predictive residual out-of-fold RMS
 residual_rmse=math.sqrt(sum(e*e for e in errors)/len(errors))
 # Always use predefined zero lower boundary and fixed .75 multiplier
 obj={
  "name":"DRNAS R18 direct paired log time advantage with bootstrap uncertainty v1",
  "trained_fold":"R17 random3_development ONLY",
  "trained_count":40,"trained_sha256":identities,
  "features":list(FIELDS),
  "target":"clip(log(PAR2_monitor/PAR2_forced2048_50),-1.5,1.5) across 3 repeats",
  "target_clipped_at":TARGET_CLIP,
  "feature_mean":mu,"feature_sd":sd,
  "feature_z_clip":3.0,
  "full_coefficients":full,
  "bootstrap_coefficients":ensemble,
  "bootstrap_count":NBOOT,
  "bootstrap_seed":SEED,
  "regularization_lambda":RIDGE_LAMBDA,
  "loo_residual_rmse":residual_rmse,
  "lower_bound_formula":"mean(bootstrap predictions) - multiplier * sqrt(population variance of bootstrap predictions + LOOCV residual_rmse^2)",
  "uncertainty_disclaimer":"Heuristic uncertainty bound, not a calibrated frequentist confidence interval.",
  "preregistered_rules":RULES,
  "frozen_n_eligibility":220,
  "read_only_input_blobs":PINS,
  "hard_no_leakage":"Any R17 random3_test, community3_* or any R18 formula MUST NOT be used in fitting or cutoff choice.",
  "no_official_sat_claim":True
 }
 OUT.mkdir(parents=True,exist_ok=True)
 (OUT/"netbenefit_model.json").write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
 digest=hashlib.sha256((OUT/"netbenefit_model.json").read_bytes()).hexdigest()
 summary={
  "train_random3_development":40,"r17_all_development":60,
  "development_clipped_positive_log_gain_count":sum(y>0 for y in ys),
  "development_harm_gt20_pct_count":sum(x["forced50_PAR2"]>x["monitor_PAR2"]*1.2 for x in observations),
  "train_target_log_gain_mean":statistics.mean(ys),
  "train_target_log_gain_min":min(ys),"train_target_log_gain_max":max(ys),
  "loo_residual_rmse":residual_rmse,
  "bootstrap_count":NBOOT,"fixed_seed":SEED,
  "model_sha256":digest,
  "development_input_only":True,
  "proof_of_excluded_folds":"Training uses only explicit dev filter; test rows not used as targets or features.",
  "training_observations_sha256":hashlib.sha256(json.dumps(observations,sort_keys=True).encode()).hexdigest(),
  "predeclared_rules":RULES
 }
 (OUT/"model_audit.json").write_text(json.dumps(summary,sort_keys=True,indent=2)+"\n")
 print("R18_FROZEN_DIRECT_GAIN_MODEL_READY",json.dumps(summary,sort_keys=True),flush=True)

if __name__=="__main__":main()
