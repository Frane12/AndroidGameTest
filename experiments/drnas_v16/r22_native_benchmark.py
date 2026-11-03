#!/usr/bin/env python3
"""R22 prospective native SAT: mature low-LBD *conflict-analysis reasons*.
Thin strict extension of verified R21 harness, with fresh formula identities.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math,os,platform,random
from pathlib import Path
import r21_native_benchmark as prior

ROOT=Path("experiments/drnas_v16")
PROTOCOL=ROOT/"r22_frozen_protocol.json"
PRIOR_CSV=ROOT/"r21-results/current/formula_features.csv"
OUT=Path("drnas-r22-results")
SHARDS=prior.SHARDS
MODES=("monitor","r11_2048_50","r16_live50","r21_inverse50",
       "r22_chain50","r22_inverse50","original_kissat","stable_v1531")
LOCAL=("r22_chain50","r22_inverse50")
FIELDS=prior.FIELDS+("r22_native_decision","r22_python_selected","r22_python_weak",
 "r22_antecedent_prev","r22_antecedent_recent","r22_mature_low_prev",
 "r22_mature_low_recent","r22_share_prev","r22_share_recent",
 "r22_trace_checkpoint_count","r22_protocol_sha256","r22_error")
PREV_PARSE=prior.parse
PREV_HISTORY=prior.history
PRIOR_CFG=prior.cfg
PRIOR_PROTOCOL=prior.PROTOCOL
PREV_ACTUAL=prior.actual_run
PRIOR_LOCAL=prior.LOCAL
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def cfg():
 c=json.loads(PROTOCOL.read_text())
 g=c["preregistered_frozen_rule"]
 if c["protocol"]!="DRNAS-R22-mature-lowLBD-conflict-chain-frozen-20261103-v1" or (
    c["dataset"]["modes"]!=list(MODES) or c["dataset"]["native_solves"]!=3840
    or c["dataset"]["seed_base"]!=2222220000
    or g["threshold_recent_scarcity"]!=.105 or
    g["threshold_moderate_recent"]!=.14 or
    g["threshold_increase_ratio"]!=1.8 or
    c["instrumentation"]["upstream_kissat"]!=prior.r20.r16.PIN or
    c["history"]["stable_v1531_blob"]!=prior.r20.r16.STABLE_PIN):
  raise RuntimeError("R22_FROZEN_PROTOCOL_OR_PIN_CHANGED")
 return c
def history():
 old_config,old_protocol=prior.cfg,prior.PROTOCOL
 prior.cfg,prior.PROTOCOL=PRIOR_CFG,PRIOR_PROTOCOL
 try:used=PREV_HISTORY()
 finally:prior.cfg,prior.PROTOCOL=old_config,old_protocol
 if len(used)!=2894:raise RuntimeError("R22_2894_HISTORIC_CNFS_MISSING")
 if prior.r20.r19.git_blob(PRIOR_CSV)!=cfg()["history"]["r21_formula_features_blob"]:
  raise RuntimeError("R22_R21_FORMULA_CATALOG_GIT_BLOB_DRIFT")
 with PRIOR_CSV.open(newline="") as f:
  newly={x["formula_sha256"] for x in csv.DictReader(f)}
 if len(newly)!=160 or newly&used:raise RuntimeError("R22_PRIOR_SHA_COLLISION")
 used|=newly
 if len(used)!=3054:raise RuntimeError("R22_HISTORIC_COUNT_INCORRECT")
 return used
def make_cases(category,folder,used):
 c=cfg()
 n=prior.r20.r16.previous.r14.size_from_category(category)
 family=prior.r20.r16.previous.r14.family_from_category(category)
 fold="development" if "_development" in category else "test"
 part=int(category[-1]);cases=[]
 for j in range(10):
  seed=(c["dataset"]["seed_base"]+n*10000+(1000 if fold=="test" else 0)
        +part*10+j+(20000 if family=="community3" else 0))
  rng=random.Random(seed);clauses=[]
  for _ in range(round(4.23*n)):
   if family=="community3" and rng.random()<.65:
    start=rng.randrange(4)*(n//4)+1
    vs=rng.sample(range(start,start+n//4),3)
   else:vs=rng.sample(range(1,n+1),3)
   clauses.append([v if rng.getrandbits(1) else -v for v in vs])
  f=prior.r20.r16.previous.r14.r11.features(clauses,n)
  case=prior.r20.r16.previous.r14.r11.base.emit_cnf(
   folder,f"r22_{family}_{n}_{fold}_{part}_{j:02d}.cnf",
   n,clauses,"UNKNOWN","generated_prospective",
   "R22 mature-LBD conflict-analysis antecedent synthetic blind formula",
   "R22-frozen-conflict-chain-age-LBD",
   {"seed":seed,"fold":fold,"family":family,"features":f,
    "community_probability":.65 if family=="community3" else 0.})
  if case["formula_sha256"] in used:raise RuntimeError("R22_HISTORICAL_SHA_COLLISION")
  case["category"]=category;cases.append(case)
 if len({x["formula_sha256"] for x in cases})!=10:
  raise RuntimeError("R22_DUPLICATED_GENERATED_FORMULAS")
 return cases
def parse(output):
 points,labels=PREV_PARSE(output)
 checkpoint=[];decisions=[]
 for line in output.splitlines():
  if line.startswith("c R22_TRACE ") or line.startswith("c R22_DECISION "):
   entry={}
   for token in line.split()[2:]:
    if "=" in token:
     key,value=token.split("=",1);entry[key]=value
   if line.startswith("c R22_TRACE "):checkpoint.append(entry)
   else:decisions.append(entry)
 if len(checkpoint)>3 or len(decisions)>1:raise RuntimeError("R22_DUPLICATE_TRACE")
 early=labels.setdefault("DRNAS_V177_EARLY",{})
 early["r22_checkpoints"]=checkpoint
 early["r22_decision"]=decisions[0] if decisions else {}
 return points,labels
prior.r20.r16.previous.r14.r11.base.extract_tags=parse

# Reuse proven real runner / same-core / SAT witness and partial artifacts.
# Replace only the R22-specific generator, parser, rule and provenance.
prior.PROTOCOL=PROTOCOL
prior.OUT=OUT
prior.MODES=MODES
prior.LOCAL=LOCAL
prior.FIELDS=FIELDS
prior.cfg=cfg
prior.history=history
prior.make_cases=make_cases

# R22 run_one and smoke are appended below.

def actual_run(case,repeat,mode,runner):
 if mode not in LOCAL:
  # The previous R21 inverse strategy must retain its own native audit.
  old_local,old_protocol=prior.LOCAL,prior.PROTOCOL
  prior.LOCAL,prior.PROTOCOL=PRIOR_LOCAL,PRIOR_PROTOCOL
  try:row,trace=PREV_ACTUAL(case,repeat,mode,runner)
  finally:prior.LOCAL,prior.PROTOCOL=old_local,old_protocol
  event={};values={}
 else:
  features=case["metadata"]["features"]
  env={"DRNAS_R16_GINI":features["degree_gini"],
       "DRNAS_R16_POLARITY":features["polarity_imbalance"]}
  old={k:os.environ.get(k) for k in env}
  try:
   for k,v in env.items():os.environ[k]=format(v,".17g")
   row,trace=prior.r20.r16.previous.r14.run_one(case,repeat,mode,runner)
  finally:
   for k,v in old.items():
    if v is None:os.environ.pop(k,None)
    else:os.environ[k]=v
  row["fold"]=prior.r20.r16.previous.r14.fold_from_category(case["category"])
  row["r16_protocol_sha256"]=sha(prior.r20.r16.CONFIG)
  row["r16_model_sha256"]=sha(prior.r20.r16.MODEL)
  early=trace.get("early",{})
  inherited=early.get("r16_event",{})
  event=early.get("r22_decision",{})
  checkpoints=early.get("r22_checkpoints",[])
  row.update(r16_native_conflict=inherited.get("conflict",""),
       r16_native_ready=inherited.get("complete",""),
       r16_native_score=inherited.get("score",""),
       r16_python_score="",r16_selected=inherited.get("selected",""),
       r16_expected_target=inherited.get("target",""),
       r16_threshold=inherited.get("threshold",""),
       r16_model=inherited.get("model",""),r16_decision_error="")
  values={}
  if event:
   ticks=[int(q["conflict"]) for q in checkpoints]
   if not(len(ticks)==3 and 256<=ticks[0]<512 and
          512<=ticks[1]<1024 and 1024<=ticks[2]<2048):
    row["error"]="R22 INVALID ORDERED ACTUAL NATIVE CHECKPOINTS"
   else:
    a,b,c=checkpoints
    delta=lambda key,p,q:int(q[key])-int(p[key])
    d0=delta("antecedent",a,b)
    d1=delta("antecedent",b,c)
    u0=delta("mature_low_antecedent",a,b)
    u1=delta("mature_low_antecedent",b,c)
    if min(d0,d1,u0,u1)<0:row["error"]="R22 NON-MONOTONIC CLAUSE REASON COUNTER"
    p0=u0/(1.+d0);p1=u1/(1.+d1)
    weak=(p1<.105 or (p1<.14 and p1<1.8*p0))
    selected=(case["n"]>=220 and
       (weak if mode=="r22_chain50" else not weak))
    expected="2048" if selected else "0"
    calculated=dict(antecedent_prev=d0,antecedent_recent=d1,
      mature_low_prev=u0,mature_low_recent=u1,
      share_prev=p0,share_recent=p1)
    mismatch=[]
    for k,v in calculated.items():
     val=float(event.get(k,"nan"))
     if not math.isfinite(val) or abs(val-v)>2e-5:mismatch.append(k)
    if (mismatch or event.get("selected")!=str(int(selected)) or
        event.get("weak")!=str(int(weak)) or
        event.get("target")!=expected or
        event.get("complete")!="1" or
        event.get("model")!=("chain" if mode=="r22_chain50" else "inverse") or
        int(event.get("n","-1"))!=case["n"] or
        inherited.get("selected")!=str(int(selected)) or
        inherited.get("target")!=expected):
     row["error"]="R22 C/PYTHON CONFLICT-CHAIN PARITY MISMATCH "+str(mismatch)
    if row["switch_at"] and (not selected or
       int(row["switch_at"])<2048 or int(row["restart_after"])!=50 or
       row["learned_before"]!=row["learned_after"]):
     row["error"]="R22 UNAUTHORIZED SWITCH OR CLAUSE RESET"
    values=dict(r22_python_selected=int(selected),r22_python_weak=int(weak),
     r22_antecedent_prev=d0,r22_antecedent_recent=d1,
     r22_mature_low_prev=u0,r22_mature_low_recent=u1,
     r22_share_prev=p0,r22_share_recent=p1)
  elif row["switch_at"]:row["error"]="R22 SWITCH WITHOUT NATIVE DECISION"
  if event and not inherited:row["error"]="R22 MISSING SHARED 1024 PREFIX"
  trace["r22_native_event"]=event
  trace["r22_native_checkpoints"]=checkpoints
 row.update(r22_native_decision=json.dumps(event,sort_keys=True) if event else "",
  r22_trace_checkpoint_count=len(trace.get("early",{}).get("r22_checkpoints",[])) if mode in LOCAL else "",
  r22_protocol_sha256=sha(PROTOCOL),r22_error=row.get("error",""),**values)
 return row,trace

prior.actual_run=actual_run
def smoke():
 from tempfile import TemporaryDirectory
 with TemporaryDirectory() as d:
  for case in make_cases("n240_development0",Path(d),history()):
   for arm in LOCAL:
    row,trace=actual_run(case,0,arm,"R22 smoke")
    if row["error"] or row["status"] not in ("SAT","UNSAT"):
     raise RuntimeError("R22 HARD NATIVE CHECK FAILED "+str(row))
    if row["r22_native_decision"]:
     print("R22_LBD_CONFLICT_CHAIN_NATIVE_PYTHON_PARITY",arm,
           case["formula"],row["r22_share_prev"],row["r22_share_recent"],flush=True)
     return
 raise RuntimeError("R22 NATIVE 1024 DECISION NOT OBSERVED")

if __name__=="__main__":
 parser=argparse.ArgumentParser()
 parser.add_argument("--category",choices=SHARDS)
 parser.add_argument("--smoke",action="store_true")
 args=parser.parse_args()
 if args.smoke:smoke()
 elif args.category:prior.run_shard(args.category)
 else:parser.error("Provide --smoke or --category")
