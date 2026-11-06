#!/usr/bin/env python3
"""DRNAS R158x: short, source-frozen 6 original CNF holdout (2026-11-06).

No solver may run before this source-only freeze. Uses metadata, complete CNF
parity group structure and SHA/ID exclusions; no solver times or outcomes.
"Unseen" means SHA/ID disjoint from explicitly materialized prior archives,
not provably every historical DRNAS workflow in existence.
"""
from __future__ import annotations
import argparse,importlib.util,json,pathlib,hashlib

ROOT=pathlib.Path("r158short")
PROTO="DRNAS-R158X-SHORT-NEW-SHA-20261106-v1"
QUOTAS={"mixed_residual":2,"complete_xor":1,"xor_plus_units":1,"nonxor_control":2}
SHARDS=3;REPS=2
CAP=6.0

def mod(path,name):
 spec=importlib.util.spec_from_file_location(name,path)
 x=importlib.util.module_from_spec(spec);spec.loader.exec_module(x)
 return x

def freeze():
 x=mod("research/r158x_short_source_engine.py","r158short_prospective_source")
 x.ROOT=ROOT
 x.PROTO=PROTO
 x.FAMILIES=("lights-out","linear-equations","xor-chain","cryptography",
             "miter","random-circuits","bitvector","or_randxor","random-graph-xorsat",
             "xor-shifting","minimum-disagreement-parity")
 x.TRACKS=("main_2025","main_2026","submissions_2025","submissions_2026")
 x.QUOTA=QUOTAS
 x.MAX_SOURCE_FETCH=900
 x.MIN_FREEZE_CASES=6
 x.MAX_VARIABLES=25000
 x.MAX_CLAUSES=500000
 x.RAW_CAP=48*1024*1024
 x.CNF_CAP=24*1024*1024
 x.freeze()
 verify()

def verify():
 m=json.loads((ROOT/"frozen/manifest.json").read_text())
 assert m["protocol"]==PROTO
 assert len(m["cases"])==6, "Need precisely six prospectively selected cases"
 assert m["cohort_counts"]==QUOTAS, "Inadequate predeclared structural balance"
 assert len({c["sha256"] for c in m["cases"]})==6
 assert len({c["id"] for c in m["cases"]})==6
 x=m["historical_exclusions"]
 assert x["prior_source_sha"]>=1326 and any("r154mix" in f for f in x["files"])
 assert any("r28full" in f for f in x["files"]), "Missing R28 Full source exclusion"
 for c in m["cases"]:
  p=ROOT/"frozen"/(c["id"]+".cnf")
  assert hashlib.sha256(p.read_bytes()).hexdigest()==c["sha256"]
  assert c["cohort"] in QUOTAS
 print("R158X_SHORT_NEW_SHA_FREEZE_PASS",json.dumps({
  "cases":len(m["cases"]),"cohorts":m["cohort_counts"],
  "historical_sha":x["prior_source_sha"],"historical_ids":x["prior_ids"],
  "source_manifest_sha256":hashlib.sha256((ROOT/"frozen/manifest.json").read_bytes()).hexdigest()
 },sort_keys=True),flush=True)
 return m

if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("action",choices=("freeze","verify"))
 a=p.parse_args()
 if a.action=="freeze":freeze()
 else:verify()
