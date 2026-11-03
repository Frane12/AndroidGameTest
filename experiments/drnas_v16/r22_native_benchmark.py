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
 used=prior.history()
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
