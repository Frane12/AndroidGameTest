#!/usr/bin/env python3
"""DRNAS R88 Parity Jump (development; exact original-CNF certificates).

Hypothesis: R87's rare native XOR first-UIP uses arise because optional periodic
trail scans miss short-lived propagation opportunities. Materialize *only*
independently source-proven GF(2) parity consequences as standard CNF before
search. Kissat's native BCP then sees them at every propagation point.

Pre-registered arms: original clean Kissat; original R87 native adaptive;
16 certified short rows upfront; 64 upfront; 16 upfront + R87 adaptive.
Preprocessing time IS included; source original SAT witnesses are checked.
R85 already-seen SHA-frozen 2025 originals: DEVELOPMENT ONLY, NOT HOLDOUT.
No score-based selection, oracle labels, invented UNSAT certification, or
change to any frozen baseline. Fail closed on certification errors.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys
import tempfile
import time

import r85_fresh_abcd as r85
import r32t_certified_short_xor as cert

PROTO="DRNAS-R88-CERTIFIED-PARITY-JUMP-DEVELOPMENT-20261104-v1"
MODES=("clean","r87_adaptive","cuts16","cuts64","hybrid16")
REPS=2
SHARDS=12
CAP=35.0
LIMITS={"cuts16":(16,256),"cuts64":(64,1024),"hybrid16":(16,256)}
BEGIN=re.compile(r"^c R87_MODE dynamic=(\d+) initial_interval=(\d+) window_scans=(\d+)$",re.M)

# A standalone process permits a HARD timeout on preprocessing; not a free
# hidden offline phase. The independent audit runs after the timed trial.
BUILD_CODE=(
  "import sys;from pathlib import Path;"
  "sys.path.insert(0,sys.argv[1]);"
  "import r32t_certified_short_xor as c;"
  "c.CAP_VARIABLES=4096;c.CAP_CLAUSES=60000;"
  "c.MAX_NEW_EQUATIONS=int(sys.argv[2]);"
  "c.MAX_NEW_CLAUSES=int(sys.argv[3]);"
  "c.build(sys.argv[4],sys.argv[5],Path(sys.argv[6]))"
)

def ck(v,msg):
    if not v:raise RuntimeError("R88_FAIL_CLOSED "+str(msg))

def digest(p):return cert.digest(Path(p))
def save(p,x):Path(p).write_text(json.dumps(x,sort_keys=True,indent=2)+"\n")

def manifest(source_root):
    mf=json.loads((source_root/"manifest.json").read_text())
    ck(mf["protocol"]==r85.PROTO and len(mf["cases"])==SHARDS,
       "source cohort must be exact R85 frozen 12 originals")
    ck(len({x["sha256"] for x in mf["cases"]})==SHARDS,
       "original source SHA duplicates")
    ck(sum(bool(c["structural_xor_positive"]) for c in mf["cases"])==4,
       "R85 structural split drift")
    return mf

def run_one(source,mode,compiled,work):
    start=time.monotonic()
    aug=work/"augmented.cnf"
    proof=work/"cert.json"
    preprocess=0.0
    stats={"chosen_short_equations":0,"added_clauses":0,
           "new_short_candidates":0,"axioms":0,"derivation_guard":None}
    solve_input=source
    if mode in LIMITS:
        cap_eq,cap_clauses=LIMITS[mode]
        cmd=[sys.executable,"-c",BUILD_CODE,str(Path(__file__).resolve().parent),
             str(cap_eq),str(cap_clauses),str(source),str(aug),str(proof)]
        try:
            built=subprocess.run(cmd,capture_output=True,text=True,errors="replace",
                                 timeout=CAP)
        except subprocess.TimeoutExpired:
            return {"answer":"TIMEOUT","wall_s":CAP,"par2_s":2*CAP,
                    "preprocess_s":CAP,"solver_s":0,"cut":stats,
                    "sat_witness_checked":False,"source_proof_checked":False,
                    "preprocess_timeout":True,"native_mode_verified":False}
        ck(built.returncode==0,
           "parity derivation or encoding failed (FAIL CLOSED) "
           +built.stderr[-900:]+built.stdout[-300:])
        preprocess=time.monotonic()-start
        stats=json.loads(proof.read_text())
        ck(stats["sha256_original"]==digest(source),
           "preprocess input original changed")
        ck(stats["sha256_augmented"]==digest(aug),
           "preprocess output SHA differs from recorded")
        ck(stats["chosen_short_equations"]<=cap_eq and
           stats["added_clauses"]<=cap_clauses,
           "source-certified parity cut budget exceeded")
        solve_input=aug
    remain=CAP-(time.monotonic()-start)
    if remain<=0:
        # All preprocessing costs charged against original 35s wall budget.
        if mode in LIMITS:
            cert.CAP_VARIABLES=4096
            cert.CAP_CLAUSES=60000
            cert.audit(source,aug,proof)
        return {"answer":"TIMEOUT","wall_s":CAP,"par2_s":2*CAP,
                "preprocess_s":round(preprocess,6),"solver_s":0,
                "cut":stats,"sat_witness_checked":False,
                "source_proof_checked":mode in LIMITS,
                "preprocess_timeout":False,"native_mode_verified":False}
    use_native=mode in ("r87_adaptive","hybrid16")
    exe=compiled/("native-r87" if use_native else "clean")
    env=os.environ.copy()
    if use_native:
        env.update(R32B_MODE="r32u",R32U_ACTIVE="1",
                   R84_SCAN_EVERY="16",R85_DIVERSE="0",
                   R85_CAP="64",R32S_PASSIVE_TRACE="0",
                   R87_ADAPT="1")
    stdout="";verdict="TIMEOUT";did_finish=False
    started_solver=time.monotonic()
    try:
        p=subprocess.run([str(exe),str(solve_input)],env=env,
                         capture_output=True,text=True,errors="replace",
                         timeout=remain)
        ck(p.returncode in (10,20),
           "native Kissat failed exit "+str(p.returncode)+" "+p.stderr[-400:])
        stdout=p.stdout
        verdict="SAT" if p.returncode==10 else "UNSAT"
        did_finish=True
    except subprocess.TimeoutExpired as e:
        stdout=e.stdout or b""
        if isinstance(stdout,bytes):stdout=stdout.decode(errors="replace")
    solver_s=time.monotonic()-started_solver
    native_ok=False
    if use_native:
        matches=BEGIN.findall(stdout)
        ck(len(matches)==1 and tuple(map(int,matches[0]))==(1,16,128),
           "R87 adaptive native was not enabled")
        native_ok=True
    sat_witness=False
    if did_finish and verdict=="SAT":
        # Augmented models MUST satisfy the original, untouched CNF.
        r85.r32p.verify_sat_witness(source,stdout)
        sat_witness=True
    elapsed=time.monotonic()-start
    answer=verdict if did_finish and elapsed<=CAP else "TIMEOUT"
    if mode in LIMITS:
        # Independent re-derivation from untouched source; not an uncharged
        # preprocessing cache used to accelerate the solver.
        cert.CAP_VARIABLES=4096
        cert.CAP_CLAUSES=60000
        cert.audit(source,aug,proof)
    return dict(answer=answer,wall_s=round(min(CAP,elapsed),6),
                par2_s=round(elapsed if answer!="TIMEOUT" else CAP*2,6),
                preprocess_s=round(preprocess,6),solver_s=round(solver_s,6),
                cut={k:stats[k] for k in (
                    "chosen_short_equations","added_clauses",
                    "new_short_candidates","axioms","derivation_guard")},
                sat_witness_checked=sat_witness,
                source_proof_checked=mode in LIMITS,
                preprocess_timeout=False,native_mode_verified=native_ok)

def measure(a):
    root=Path(a.sources).resolve()
    mf=manifest(root)
    ck(0<=a.shard<SHARDS,"bad shard")
    case=mf["cases"][a.shard]
    source=root/case["filename"]
    ck(digest(source)==case["sha256"],"original CNF SHA mismatch")
    compiled=Path(a.compiled).resolve()
    x=subprocess.run(["sha256sum","-c","r87-binaries.sha256"],
                     cwd=compiled,capture_output=True,text=True)
    ck(x.returncode==0,"baseline binary SHA drift: "+x.stderr[-200:])
    ck(all((compiled/b).is_file() for b in ("clean","native-r87")),
       "missing exact clean/native R87 binaries")
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    target=Path(a.out).resolve()
    target.mkdir(parents=True,exist_ok=True)
    rows=[]
    for rep in range(REPS):
        order=list(MODES)
        seed=int(hashlib.sha256((PROTO+case["sha256"]+str(rep)).encode()).hexdigest(),16)
        random.Random(seed).shuffle(order)
        for mode in order:
            with tempfile.TemporaryDirectory(prefix="r88_") as tmp:
                got=run_one(source,mode,compiled,Path(tmp))
            row=dict(gbd=case["gbd"],sha256=case["sha256"],
                     group=case["group"],rep=rep,mode=mode,**got,
                     commit=os.getenv("GITHUB_SHA",""),
                     run_id=os.getenv("GITHUB_RUN_ID",""),
                     runner=os.getenv("RUNNER_NAME",""))
            rows.append(row)
            save(target/"r88-shard.json",dict(protocol=PROTO,
                 shard=a.shard,original_manifest_sha=digest(root/"manifest.json"),
                 binaries={"clean":digest(compiled/"clean"),
                           "native-r87":digest(compiled/"native-r87")},
                 rows=rows))
            print("R88_TRIAL",json.dumps({
                k:row[k] for k in ("gbd","group","mode","rep","answer",
                  "wall_s","par2_s","preprocess_s","solver_s","cut")}),flush=True)
    ck(len(rows)==REPS*len(MODES),"incomplete shard")
    print("R88_SHARD_PASS",a.shard,len(rows),flush=True)

def audit(a):
    root=Path(a.sources)
    mf=manifest(root)
    full=[];pins=set()
    for i,c in enumerate(mf["cases"]):
        ck(digest(root/c["filename"])==c["sha256"],
           "original official CNF sha drift")
        path=Path(a.combined)/f"r88-shard-{i}"/"results"/"r88-shard.json"
        ck(path.exists(),"missing shard artifact "+str(i))
        j=json.loads(path.read_text())
        ck(j["protocol"]==PROTO and j["shard"]==i and
           j["original_manifest_sha"]==digest(root/"manifest.json"),
           "mixed or stale original source bundle")
        pins.add(json.dumps(j["binaries"],sort_keys=True))
        ck(len(j["rows"])==REPS*len(MODES),"missing row in shard "+str(i))
        for rep in range(REPS):
            paired=[r for r in j["rows"] if r["rep"]==rep]
            ck(len(paired)==len(MODES) and
               {r["mode"] for r in paired}==set(MODES),
               "not source/rep paired")
            ck(all(r["sha256"]==c["sha256"] and
                   r["gbd"]==c["gbd"] and r["run_id"] and
                   r["commit"] and r["runner"] for r in paired),
               "provenance missing")
            answers={r["answer"] for r in paired if r["answer"]!="TIMEOUT"}
            ck(len(answers)<=1,"original CNF SAT/UNSAT verdict contradiction")
            ck(all((r["answer"]!="SAT" or r["sat_witness_checked"]) and
               (r["mode"] not in LIMITS or
                r["preprocess_timeout"] or r["source_proof_checked"])
               for r in paired),"original SAT witness/source proof not checked")
        full+=j["rows"]
    ck(len(pins)==1 and len(full)==SHARDS*REPS*len(MODES),
       "inconsistent pins or incomplete 120 attempts")
    totals={}
    for group in ("ALL","XOR","CONTROL"):
        allowed={c["sha256"] for c in mf["cases"] if
                 group=="ALL" or
                 (group=="XOR" and c["structural_xor_positive"]) or
                 (group=="CONTROL" and not c["structural_xor_positive"])}
        totals[group]={}
        for mode in MODES:
            vals=[r for r in full if r["sha256"] in allowed and r["mode"]==mode]
            totals[group][mode]=dict(
              trials=len(vals),solved=sum(r["answer"]!="TIMEOUT" for r in vals),
              par2_s=round(sum(r["par2_s"] for r in vals),6),
              preprocess_s=round(sum(r["preprocess_s"] for r in vals),6),
              added_clauses=sum(r["cut"]["added_clauses"] for r in vals))
    paired=[]
    for c in mf["cases"]:
        rr=[r for r in full if r["sha256"]==c["sha256"]]
        paired.append({m:sum(z["par2_s"] for z in rr if z["mode"]==m)/REPS
                       for m in MODES})
    bootstrap={}
    rng=random.Random(881104)
    for mode in MODES[1:]:
        diff=[r["clean"]-r[mode] for r in paired]
        sims=sorted(sum(diff[rng.randrange(SHARDS)] for _ in range(SHARDS))/SHARDS
                    for __ in range(2000))
        bootstrap[mode]=dict(mean_saved_s_per_source=round(sum(diff)/SHARDS,6),
                        ci95=[round(sims[49],6),round(sims[1949],6)])
    output=Path(a.out);output.mkdir(parents=True,exist_ok=True)
    report=dict(protocol=PROTO,status="PASS_DEVELOPMENT_NOT_HOLDOUT",
                original_count=SHARDS,paired_trials=len(full),groups=totals,
                bootstrap=bootstrap,rows=full,binary_shas=json.loads(next(iter(pins))),
                original_manifest_sha=digest(root/"manifest.json"),
                limitations=[
                  "R88 reuses R85/R87 already observed real SAT 2025 originals: DEVELOPMENT NOT BLIND.",
                  "R32T-derived clauses certified from complete original CNF XOR axioms only.",
                  "Preprocessing fully counts in each 35-second trial; no cached costs excluded.",
                  "Native R87 remains fixed; its source use is only as measured baseline/hybrid.",
                  "Sample is XOR-enriched 4/12 (not representative of official competition).",
                  "SAT models validated on original CNF; UNSAT independent DRAT/LRAT not replayed.",
                  "Any apparent gain requires unseen SHA-disjoint paired holdout replication."
                ])
    save(output/"r88-final.json",report)
    lines=["# DRNAS R88 Certified Parity Jump",
           "","**120 source-paired development attempts, 12 known 2025 formulas, 35s cap, PAR-2**",
           "All preprocessing costs are included. Certificate independently rederived. Not an unseen holdout.",
           "","| Group | Mode | Solved | PAR-2 s | Preprocess s | Added parity clauses |",
           "|---|---|---:|---:|---:|---:|"]
    for group,modes in totals.items():
        for mode,x in modes.items():
            lines.append(f"| {group} | {mode} | {x['solved']}/{x['trials']} |"
                         f" {x['par2_s']:.3f} | {x['preprocess_s']:.3f} |"
                         f" {x['added_clauses']} |")
    lines+=["","## Paired-source bootstrap saved seconds (positive is better)"]
    lines.extend(f"- {m}: {x}" for m,x in bootstrap.items())
    lines+=["","## Limitations"]
    lines.extend("- "+z for z in report["limitations"])
    (output/"r88-final.md").write_text("\n".join(lines)+"\n")
    print("R88_FINAL_CERTIFIED_PARITY_JUMP_AUDIT_PASS",len(full),
          json.dumps(totals["ALL"]),flush=True)

def selftest():
    ck(REPS*SHARDS*len(MODES)==120,"protocol counts")
    ck(LIMITS["cuts16"]==(16,256) and LIMITS["cuts64"]==(64,1024),
       "frozen parity cut arms changed")
    ck("c.build" in BUILD_CODE and "CAP_VARIABLES=4096" in BUILD_CODE,
       "preprocessor not pinned")
    # Exact 3-variable parity has four clauses and decodes to same rhs.
    example=list(cert.encode_parity((1,2,3),0))
    ck(len(example)==4 and all(len(c)==3 for c in example),
       "XOR clause expansion broken")
    # The conjunction of all generated parity clauses accepts precisely
    # the 2^(k-1) target parity assignments.
    for mask in range(8):
        assign={v:bool(mask&(1<<(v-1))) for v in (1,2,3)}
        sat=all(any((assign[abs(l)] if l>0 else not assign[abs(l)])
                    for l in clause) for clause in example)
        ck(sat==(mask.bit_count()%2==0),"parity encoding truth-table mismatch")
    print("R88_CERTIFIED_PARITY_JUMP_SELFTEST_PASS",flush=True)

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="action",required=True)
    sub.add_parser("selftest")
    m=sub.add_parser("measure")
    for k in ("sources","compiled","out"):m.add_argument("--"+k,required=True)
    m.add_argument("--shard",required=True,type=int)
    a=sub.add_parser("audit")
    for k in ("sources","combined","out"):a.add_argument("--"+k,required=True)
    args=p.parse_args()
    if args.action=="selftest":selftest()
    elif args.action=="measure":measure(args)
    else:audit(args)

if __name__=="__main__":main()
