#!/usr/bin/env python3
"""Certified DELTA4X + MATH-GUARD4 four-arm A/B on original SAT2024 CNFs.

No train, no outcome-informed policy. Historical labels used ONLY for audit.
All modes use the SAME derived binary, one process on one logical CPU;
SAT models checked against original source, UNSAT proofs by frozen drat-trim.
"""
import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import resource
import signal
import statistics
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research"))
from drnas_delta4x import bench as B
from drnas_delta4x.verify import validate_events,events,canon,fixtures,oracle
from drnas_x55_cpu_real36 import parse_cnf,check_sat

EXEC=ROOT/"build/drnas-delta4x-mathguard"
CHECKER=ROOT/"build/drat-trim"
DEST=ROOT/"delta4x_mathguard_ab"
CAP=6.0
REPS=2
IDS=(8,14,19,28,33,38,40,41)
ARMS=("BASE","SHADOW","GUARD_ON","SELECTIVE")
MODES={"BASE":0,"SHADOW":1,"GUARD_ON":2,"SELECTIVE":3}
PIN_STATUS={14:"SAT_VERIFIED",33:"UNSAT_CERTIFIED",
            40:"SAT_VERIFIED",41:"SAT_VERIFIED"}
PIN_SHA={14:"79f06cc7ea5b02048b574ae0c834b5abec765bd8042618261554a30822e90a3d",
         33:"3406f2546021e23fec5838524107e45fd5df0de84ec27dde866b7874f8308703",
         40:"15872c7e09964533ca139d769b14563c8a8d2d863fc9995b829ff89bd44742cb",
         41:"d3338c04e29f5c8b7e75686fa30fd9927babb7b34b9f7c87785397662f59d8e2"}

def sha(data):return hashlib.sha256(data).hexdigest()
def output(tag,obj):print(tag+" "+json.dumps(obj,sort_keys=True),flush=True)

def input_sources():
    src,manifest=B.sources()
    assert manifest==B.PIN_MANIFEST
    byid={s["id"]:s for s in src}
    assert set(IDS).issubset(byid)
    for i in IDS:
        src=byid[i]
        if i in PIN_SHA:assert src["sha256"]==PIN_SHA[i]
        assert sha((ROOT/src["path"]).read_bytes())==src["sha256"]
    return {i:byid[i] for i in IDS},manifest

def proof_check(cnf,proof):
    assert proof.is_file() and proof.stat().st_size
    q=subprocess.run([str(CHECKER),str(cnf),str(proof)],
                     capture_output=True,text=True,timeout=30)
    if "s VERIFIED" not in q.stdout:raise RuntimeError(("INVALID_DRAT",q.stdout[-400:],q.stderr[-200:]))

def check_lemmas(stderr,clauses,mode):
    source={canon(c) for c in clauses if len(c) in (2,3)}
    found=events(stderr,"MG4_LEMMA")
    meta=events(stderr,"MATH_GUARD4_STATS")
    if len(meta)!=1:raise RuntimeError("MATHGUARD_STATS_MISSING")
    st=meta[0]
    assert st["mode"]==mode
    if mode in (0,1):assert st["installed"]==0 and not found
    assert len(found)==min(8,st["installed"])
    for item in found:
        a,b,piv,c=item["parent_a"],item["parent_b"],item["pivot"],item["clause"]
        assert canon(a) in source and canon(b) in source,("UNKNOWN_ORIGINAL_PARENT",item)
        assert piv in a and -piv in b,("INVALID_PIVOT",item)
        resolvent=canon([l for l in a if l!=piv]+[l for l in b if l!=-piv])
        assert resolvent==canon(c) and len(resolvent)==2,("BAD_RESOLUTION",item)
        assert not any(-l in resolvent for l in resolvent)
    return st,len(found)

def run_one(src,mode,rep,cap,folder):
    arm=ARMS[mode]
    cnf=(ROOT/src["path"]).resolve()
    raw=cnf.read_bytes()
    assert sha(raw)==src["sha256"]
    n,clauses=parse_cnf(raw)
    folder.mkdir(parents=True,exist_ok=True)
    proof=folder/(f"{src['id']}-{rep}-{arm}.drat")
    usage=folder/"usage.txt"
    cmd=[str(EXEC),str(cnf),"--mode","core","--time",str(cap-.12),
         "--x5-no-minimize","--coop4","gate","--coop5","off",
         "--delta2","d4x","--stats","--proof",str(proof),
         "--math-guard4",str(mode),"--math-guard4-budget-ms","2.0"]
    def limits():
        resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,4*1024**3))
        resource.setrlimit(resource.RLIMIT_FSIZE,(128*1024**2,128*1024**2))
    start=time.perf_counter()
    p=subprocess.Popen(["/usr/bin/time","-f","%U %S %M","-o",str(usage),*cmd],
                       stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                       text=True,start_new_session=True,preexec_fn=limits)
    killed=False
    try:
        stdout,stderr=p.communicate(timeout=cap+.15)
    except subprocess.TimeoutExpired:
        killed=True
        os.killpg(p.pid,signal.SIGKILL)
        stdout,stderr=p.communicate()
    wall=time.perf_counter()-start
    status="TIMEOUT" if killed else "UNKNOWN"
    check_time=0.0
    if not killed and p.returncode==10:
        assert check_sat(stdout,clauses,n),("WRONG_SAT_MODEL",src["id"],arm)
        status="SAT_VERIFIED"
    elif not killed and p.returncode==20:
        start_check=time.perf_counter()
        try:
            proof_check(cnf,proof)
            status="UNSAT_CERTIFIED"
        except subprocess.TimeoutExpired:
            status="UNSAT_CHECK_TIMEOUT"
        check_time=time.perf_counter()-start_check
    elif not killed and p.returncode not in (0,153):
        raise RuntimeError(("NATIVE_CRASH",src["id"],arm,p.returncode,stderr[-900:]))
    g={}
    dx={}
    cdcl={}
    if not killed:
        g,verified_logged=check_lemmas(stderr,clauses,mode)
        dx,_,_=validate_events(stderr,clauses)
        stats=events(stderr,"X41_STATS")
        assert len(stats)==1
        cdcl=stats[0]
    verified=(status in ("SAT_VERIFIED","UNSAT_CERTIFIED") and wall<=cap)
    if verified and src["id"] in PIN_STATUS:
        assert status==PIN_STATUS[src["id"]],("WRONG_CERTIFIED_LABEL",src["id"],status)
    cpu=rss=None
    if usage.is_file():
        usage_row=usage.read_text().split()
        if len(usage_row)==3:
            cpu=float(usage_row[0])+float(usage_row[1])
            rss=int(usage_row[2])
    if proof.exists():proof.unlink()
    row=dict(id=src["id"],family=src["family"],sha256=src["sha256"],
        mode=mode,arm=arm,rep=rep,
        status=status,verified=verified,wall_e2e_s=wall,cpu_s=cpu,
        maxrss_kib=rss,proof_check_s=check_time,
        PAR2_verified_s=wall if verified else 2*cap,
        conflicts=cdcl.get("conflicts"),decisions=cdcl.get("decisions"),
        mg_candidates=g.get("candidates",0),mg_installed=g.get("installed",0),
        mg_ms=g.get("wall_ms",0),mg_gate_skips=g.get("gate_skips",0),
        mg_caused_enqueues=g.get("reason_enqueues",0),
        mg_scanned=g.get("scanned",0),mg_pairs=g.get("pairs",0),
        math_original_binary=g.get("orig_binary",0),
        math_original_ternary=g.get("orig_ternary",0),
        delta4x_installed=dx.get("installed",0),
        delta4x_causal_enqueues=dx.get("actual_enqueues",0),
        historical_certified_status=PIN_STATUS.get(src["id"]))
    output("MG4_REAL_TRIAL",row)
    return row

def preflight():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    assert EXEC.is_file() and CHECKER.is_file()
    sources,manifest=input_sources()
    synthetic=[
        ("bridge_sat",4,[[1,2,3],[-1,2,3],[2,4],[-4,3]]),
        ("bridge_unsat",4,[[1,2,3],[-1,2,3],[-2],[-3],[4]]),
        ("bridge_sat2",5,[[1,2,3],[-1,2,3],[-2,4],[-3,5],[4,5]]),
        ("xor_sat",3,[[1,2,3],[1,-2,-3],[-1,2,-3],[-1,-2,3]]),
    ]
    for i in range(20):
        rng=random.Random(44006+i)
        n=5+i%4
        clauses=[]
        for j in range(8+i%12):
            width=rng.choice((2,3,3,4))
            vs=rng.sample(range(1,n+1),min(width,n))
            clauses.append([v if rng.randrange(2) else -v for v in vs])
        synthetic.append((f"random_{i}",n,clauses))
    nchecked=0;nonzero=0
    with tempfile.TemporaryDirectory() as root:
        for name,n,clauses in synthetic:
            cnf=Path(root)/(name+".cnf")
            cnf.write_text(f"p cnf {n} {len(clauses)}\n"+
                           "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
            expect=10 if oracle(clauses) else 20
            for mode in range(4):
                proof=Path(root)/(name+f"_{mode}.drat")
                cmd=[str(EXEC),str(cnf),"--mode","core","--time","1.4",
                     "--stats","--proof",str(proof),"--x5-no-minimize",
                     "--coop4","gate","--coop5","off","--delta2","d4x",
                     "--math-guard4",str(mode)]
                p=subprocess.run(cmd,capture_output=True,text=True,timeout=4)
                assert p.returncode==expect,("MATHGUARD_ORACLE_FAILURE",name,mode,p.returncode,expect,p.stderr[-700:])
                if expect==10:
                    assert check_sat(p.stdout,clauses,n),("BAD_SAT",name,mode)
                else:
                    proof_check(cnf,proof)
                mg, count=check_lemmas(p.stderr,clauses,mode)
                if mode==2:nonzero+=mg["installed"]
                assert events(p.stderr,"DELTA4X_STATS")
                nchecked+=1
    assert nonzero>0,("NO_BINARY_RESOLVENTS",nonzero)
    manifest_out=dict(originals=sorted(IDS),hashes={str(i):sources[i]["sha256"] for i in IDS},
        source_manifest_sha256=manifest,frozen_reference_binary_sha256=sha((ROOT/"build/drnas-delta4x").read_bytes()),
        derived_binary_sha256=sha(EXEC.read_bytes()),arms=ARMS,reps=REPS,cap=CAP,
        retrospective=True,blind_holdout=False,one_cpu=True,one_process=True,
        no_main_changes=True,no_promotion=True,
        original_sat2024=True,certified_sources=PIN_STATUS)
    DEST.mkdir(exist_ok=True)
    (DEST/"protocol.json").write_text(json.dumps(manifest_out,indent=2,sort_keys=True)+"\n")
    output("MG4_PREFLIGHT_PASS",dict(cases=len(synthetic),trials=nchecked,
        installed=nonzero,all_small_oracles_and_original_RUP_verified=True,
        original_sources=len(sources),manifest=manifest,one_cpu=True))

def bench():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    sources,_=input_sources()
    assert (DEST/"protocol.json").exists()
    rows=[]
    for src in sources.values():
        for rep in range(REPS):
            modes=list(range(4))
            random.Random(int(src["sha256"][:16],16)+rep*97).shuffle(modes)
            for mode in modes:
                with tempfile.TemporaryDirectory() as temp:
                    rows.append(run_one(src,mode,rep,CAP,Path(temp)))
    assert len(rows)==len(IDS)*REPS*4
    (DEST/"trials.json").write_text(json.dumps(rows,indent=2,sort_keys=True)+"\n")
    result={}
    for arm in ARMS:
        group=[r for r in rows if r["arm"]==arm]
        result[arm]=dict(attempts=len(group),verified=sum(r["verified"] for r in group),
            PAR2_s=sum(r["PAR2_verified_s"] for r in group),
            cpu_s=sum(r["cpu_s"] or 0 for r in group),
            guard_candidates=sum(r["mg_candidates"] for r in group),
            guard_lemmas=sum(r["mg_installed"] for r in group),
            guard_caused_enqueues=sum(r["mg_caused_enqueues"] for r in group),
            guard_ms=sum(r["mg_ms"] for r in group),
            delta4x_lemmas=sum(r["delta4x_installed"] for r in group))
    by_case={}
    verified_pairs=[]
    for i in IDS:
        items=[r for r in rows if r["id"]==i]
        by_case[i]={a:dict(statuses=[r["status"] for r in items if r["arm"]==a],
              verified=sum(r["verified"] for r in items if r["arm"]==a),
              par2=sum(r["PAR2_verified_s"] for r in items if r["arm"]==a),
              mg_lemmas=sum(r["mg_installed"] for r in items if r["arm"]==a),
              delta4x=sum(r["delta4x_installed"] for r in items if r["arm"]==a))
              for a in ARMS}
        for rep in range(REPS):
            base=next(r for r in items if r["rep"]==rep and r["arm"]=="BASE")
            for a in ("GUARD_ON","SELECTIVE"):
                branch=next(r for r in items if r["rep"]==rep and r["arm"]==a)
                if base["verified"] and branch["verified"]:
                    assert base["status"]==branch["status"]
                    verified_pairs.append((i,rep,a,base["wall_e2e_s"]/branch["wall_e2e_s"]))
    summary=dict(original_sources=len(IDS),runs=len(rows),
        one_cpu=True,one_process_at_a_time=True,retrospective=True,
        blind_holdout=False,promotion=False,cap_s=CAP,
        results=result,by_case=by_case,
        median_verified_speedup={
            a:statistics.median(r[3] for r in verified_pairs if r[2]==a)
            if any(r[2]==a for r in verified_pairs) else None
            for a in ("GUARD_ON","SELECTIVE")})
    (DEST/"report.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    output("MG4_REAL_FINAL",summary)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("stage",choices=("preflight","bench"))
    args=parser.parse_args()
    if args.stage=="preflight":preflight()
    else:bench()
