#!/usr/bin/env python3
"""V13.14 actual wall-clock SAT benchmark, same 30 SHA-frozen public 2024 CNFs.

Three policies: Kissat404, DRNAS_Legacy, and V1312 certified XOR prepass -> Kissat404.
Full Python startup and prepass/fallback cost counted in hybrid.
Strict same cap and same one-core CPU affinity for each mode; order shuffled by seed.
This is not an official SAT Competition ranking or independent UNSAT proof checker.
"""
import argparse
import hashlib
import json
import os
import random
import resource
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
import official_shortlong_select as source
import official_2026_mini_sim as mini
import v1312_sparse_gf2 as sparse

PROTOCOL="DRNAS-V1314-30-2024-TIMED-PAIRED-CAP8-20261101-v1"
SOURCE_PROTOCOL="DRNAS-V1313-SC2024-THIRTY-SHA-DISJOINT-20261101-v1"
CAP=8.0
REPS=2
SHARDS=10
MEMORY_GIB=3
MODES=("Kissat404","DRNAS_Legacy","V1312_XOR_Kissat")
source.RAW_CAP=96*1024**2
source.CNF_CAP=64*1024**2
source.VARIABLE_CAP=500000
source.CLAUSE_CAP=1000000

def require(b,message):
    if not b: raise RuntimeError(message)

def load(path):
    return json.loads(Path(path).read_text())

def save(path,obj):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""):h.update(b)
    return h.hexdigest()

def memlimit():
    n=MEMORY_GIB*1024**3
    resource.setrlimit(resource.RLIMIT_AS,(n,n))

def probe(path):
    """Run exact unchanged V13.12 diagnostics, replay all stored UNSAT proofs."""
    d=sparse.analyze(path)
    result={"certified_contradictions":d["sparse"]["certified_contradictions"],
            "certified_forced_literals":d["sparse"]["certified_units"],
            "sparse_wall_s":d["total_wall_s"],"equations":d["xor_equations"],
            "verified_contradiction":False}
    if result["certified_contradictions"]:
        proofs=[p for p in d["certificates"] if p["kind"]=="unsat_subset_proof"]
        require(bool(proofs),"contradiction without certificate")
        _,_,eq,_=sparse.prior.extract(path)
        require(any(sparse.prior.proof_valid(eq,cert["equation_indices"],(),1)
                    for cert in proofs),"invalid replayed contradiction")
        result["verified_contradiction"]=True
    return result

def exec_solver(mode, file, seed, drnas, kissat, seconds):
    if mode=="Kissat404":
        cmd=[str(Path(kissat).resolve()),str(Path(file).resolve())]
    elif mode=="DRNAS_Legacy":
        cmd=[str(Path(drnas).resolve()),"v100_late_legacy_force",
             str(Path(file).resolve()),str(seed)]
    else:raise ValueError("unknown mode "+mode)
    try:
        proc=subprocess.run(cmd, capture_output=True,text=True,errors="replace",
              timeout=max(0.001,seconds),preexec_fn=memlimit,check=False)
    except subprocess.TimeoutExpired:
        return "TIMEOUT","",None
    if mode=="Kissat404":
        require(proc.returncode in (10,20),
                f"Kissat exit {proc.returncode} stderr {proc.stderr[-160:]}")
        status=mini.parse_kissat(proc.stdout)
        require((proc.returncode==10)==(status=="SAT"),"wrong Kissat exit/status")
    else:
        require(proc.returncode==0,
                f"DRNAS exit {proc.returncode} stderr {proc.stderr[-160:]}")
        status=mini.parse_drnas(proc.stdout,"v100_late_legacy_force")
    return status,"",proc.returncode

def timed_trial(mode,file,seed,drnas,kissat,expected):
    start=time.monotonic()
    reason="direct_binary"
    probe_s=0.0
    detected=0
    result="ERROR"
    msg=""
    exitcode=None
    try:
        if mode=="V1312_XOR_Kissat":
            reason="safe_fallback"
            # Separate subprocess gives the prepass a strict wall cap and clean
            # Python startup cost. Failure is not silently considered a proof.
            remaining=CAP-(time.monotonic()-start)
            try:
                child=subprocess.run(
                    [sys.executable,str(Path(__file__).resolve()),
                     "probe","--file",str(Path(file).resolve())],
                    capture_output=True,text=True,errors="replace",
                    timeout=max(.001,remaining),preexec_fn=memlimit)
            except subprocess.TimeoutExpired:
                child=None
                result="TIMEOUT"
                reason="prepass_timeout"
            probe_s=time.monotonic()-start
            if child is not None:
                require(child.returncode==0,"prepass error: "+child.stderr[-250:])
                p=json.loads(child.stdout)
                detected=p["certified_contradictions"]
                if p["verified_contradiction"]:
                    result="UNSAT"
                    reason="independently_replayed_xor_unsat"
                else:
                    remaining=CAP-(time.monotonic()-start)
                    if remaining<=.001:
                        result="TIMEOUT"
                    else:
                        result,_,exitcode=exec_solver("Kissat404",file,seed,drnas,kissat,remaining)
        else:
            result,_,exitcode=exec_solver(mode,file,seed,drnas,kissat,CAP)
        elapsed=time.monotonic()-start
        if elapsed>CAP+.02:
            result="TIMEOUT"
        if result in ("SAT","UNSAT"):
            require(result==expected, "wrong solver answer versus published 2024 label")
        require(result in ("SAT","UNSAT","TIMEOUT"),"bad status")
    except Exception as e:
        result="ERROR"
        msg=f"{type(e).__name__}: {str(e)[:220]}"
        elapsed=time.monotonic()-start
    return {"status":result, "wall_s":round(min(elapsed,CAP),6),
            "probe_wall_s":round(probe_s,6),
            "certified_contradictions":detected,
            "reason":reason,"exit_code":exitcode,"error":msg}

def validate_manifest(m):
    require(m["protocol"]==SOURCE_PROTOCOL and len(m["cases"])==30,
            "wrong prior frozen sample")
    require(len({c["sha256"] for c in m["cases"]})==30,"duplicate SHA")
    require(m["excluded_prior_shas"] is True,"no previous SHA exclusion")

def selftest():
    import tempfile
    import v1311_local_xor as xor
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)/"test.cnf"
        edges=[(1,2,3),(1,4,5),(2,4,6),(3,5,6)]
        unsat=xor.synthetic([(s,int(i==3)) for i,s in enumerate(edges)],
                            extras=[(1,-2)])
        p.write_bytes(unsat)
        r=probe(p)
        require(r["verified_contradiction"],"missed certified XOR UNSAT")
        require(xor.brute_models(unsat)==[],"incorrect certified UNSAT")
        p.write_bytes(xor.synthetic([((1,2,3),0)],extras=[(4,)]))
        r=probe(p)
        require(not r["verified_contradiction"],"false UNSAT verdict on SAT")
    print("V1314_SELFTEST_PASS exact proof branch and safe fallback",flush=True)

def run(a):
    m=load(a.manifest);validate_manifest(m)
    require(0<=a.shard<SHARDS,"invalid shard")
    subset=m["cases"][a.shard::SHARDS]
    require(len(subset)==3,"not 3 cases per shard")
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    cpus=sorted(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpus[0]})
    cpu=next((s.split(":",1)[1].strip() for s in
              Path("/proc/cpuinfo").read_text().splitlines()
              if s.startswith("model name")),"unknown")
    save(out/"meta.json",{"shard":a.shard,"case_sha256":[x["sha256"] for x in subset],
         "cpu_model":cpu,"cpu_affinity":len(os.sched_getaffinity(0)),
         "binary_sha256":{"kissat":sha(a.kissat),"drnas":sha(a.drnas)},
         "hybrid_script_sha256":sha(__file__),
         "sparse_code_sha256":sha(sparse.__file__),
         "cap_s":CAP,"reps":REPS,"modes":list(MODES),"protocol":PROTOCOL})
    rows=[]
    for case in subset:
        f=out/(case["id"]+".cnf")
        got=source.download_and_features(case["id"],f)
        require(got["sha256"]==case["sha256"] and
                got["features"]==case["features"],"case SHA/features mismatch")
        for rep in range(REPS):
            seed=(20241314+104729*rep+int(case["sha256"][:8],16))%(2**32)
            order=list(MODES)
            random.Random(seed^1391414).shuffle(order)
            for mode in order:
                q=timed_trial(mode,f,seed,a.drnas,a.kissat,case["official_label"])
                record={"id":case["id"],"sha256":case["sha256"],
                        "official_label":case["official_label"],"family":case["family"],
                        "repetition":rep,"seed":seed,"mode":mode,**q}
                rows.append(record)
                save(out/"rows.json",rows)
                print("V1314_TRIAL",a.shard,case["id"][:12],rep,mode,q["status"],
                      q["wall_s"],"probe",q["probe_wall_s"],
                      "reason",q["reason"],flush=True)
                require(q["status"]!="ERROR",
                        "Fail closed on incorrect solver/probe: "+q["error"])
        f.unlink(missing_ok=True)
    require(len(rows)==3*REPS*len(MODES),"missing benchmark rows")
    print("V1314_SHARD_PASS",a.shard,len(rows),flush=True)

def audit(a):
    m=load(a.manifest);validate_manifest(m)
    all_rows=[];hashes=set();cpu=set()
    for shard in range(SHARDS):
        folder=Path(a.combined)/f"v1314-shard-{shard}"
        meta=load(folder/"meta.json")
        part=load(folder/"rows.json")
        subset=m["cases"][shard::SHARDS]
        require(meta["protocol"]==PROTOCOL and meta["shard"]==shard
                and meta["cap_s"]==CAP and meta["reps"]==REPS
                and meta["modes"]==list(MODES)
                and meta["case_sha256"]==[c["sha256"] for c in subset],
                "bad shard provenance")
        require(meta["cpu_affinity"]==1,"CPU not pinned")
        hashes.add(json.dumps([meta["binary_sha256"],meta["hybrid_script_sha256"],
                               meta["sparse_code_sha256"]],sort_keys=True))
        cpu.add(meta["cpu_model"])
        require(len(part)==3*REPS*len(MODES),"incomplete trials")
        all_rows.extend(part)
    require(len(hashes)==1,"different binary/code hashes among shards")
    expected={c["id"]:c for c in m["cases"]}
    observed=set()
    bymode=defaultdict(list)
    bytype=defaultdict(list)
    wins=[]
    for x in all_rows:
        case=expected[x["id"]]
        key=(x["id"],x["repetition"],x["mode"])
        require(key not in observed,"duplicate trial")
        observed.add(key)
        require(x["sha256"]==case["sha256"]
                and x["official_label"]==case["official_label"]
                and x["status"] in ("SAT","UNSAT","TIMEOUT")
                and not x["error"] and 0<=x["wall_s"]<=CAP+.02,
                "wrong identity/verdict/wall time")
        require(x["status"]=="TIMEOUT" or x["status"]==case["official_label"],
                "invalid verdict")
        bymode[x["mode"]].append(x)
        bytype[(x["official_label"],x["mode"])].append(x)
        if x["reason"]=="independently_replayed_xor_unsat":
            wins.append(x)
            require(x["status"]=="UNSAT" and x["certified_contradictions"]>0,
                    "invalid certified early-UNSAT")
    require(len(observed)==30*REPS*len(MODES),"missing attempts")
    stats={}
    for group,rr in [("all",all_rows)]+[(name,[x for x in all_rows
                                           if x["official_label"]==name])
                                        for name in ("SAT","UNSAT")]:
        stats[group]={}
        for mode in MODES:
            sub=[x for x in rr if x["mode"]==mode]
            cost=[2*CAP if x["status"]=="TIMEOUT" else x["wall_s"] for x in sub]
            solved=[x["wall_s"] for x in sub if x["status"] in ("SAT","UNSAT")]
            stats[group][mode]={
              "solved":len(solved),"attempts":len(sub),
              "PAR2_s":round(statistics.mean(cost),6),
              "mean_solved_s":round(statistics.mean(solved),6) if solved else None,
              "median_solved_s":round(statistics.median(solved),6) if solved else None,
              "timeouts":len(sub)-len(solved)}
    diffs=[]
    for c in m["cases"]:
        for rep in range(REPS):
            k=next(x for x in bymode["Kissat404"] if x["id"]==c["id"] and x["repetition"]==rep)
            h=next(x for x in bymode["V1312_XOR_Kissat"] if x["id"]==c["id"] and x["repetition"]==rep)
            diffs.append({"id":c["id"],"rep":rep,"kissat_status":k["status"],
                          "kissat_s":k["wall_s"],"hybrid_status":h["status"],
                          "hybrid_s":h["wall_s"],"hybrid_reason":h["reason"],
                          "delta_s":round(h["wall_s"]-k["wall_s"],6)})
    report={"protocol":PROTOCOL,"sample":30,"attempts":len(all_rows),
            "cap_s":CAP,"reps":REPS,"cpu_models":sorted(cpu),
            "per_mode":stats,"verified_early_unsat_attempts":len(wins),
            "verified_early_unsat_cases":len({x["id"] for x in wins}),
            "xor_early_wins":wins,"paired_kissat_hybrid":diffs,
            "all_trials":all_rows,
            "limitations":[
                "30 SHA-frozen 2024 formulas already inspected in structural V13.13; held-out from earlier listed cohorts, not a fresh prospective external benchmark of this hybrid policy.",
                "8-second per-method cap and 3 GiB RAM on GitHub Actions; not official SAT Competition conditions or world ranking.",
                "2 repetitions per formula, single-core affinity; cross-runner CPU models reported.",
                "Wall-clock includes Python startup, XOR prepass and fallback for hybrid.",
                "Non-UNSAT hybrid path falls back unchanged to Kissat, without injecting implied literals.",
                "Solved answers checked against published official status; solver-generated proof/model files not independently certified.",
                "PAR-2 timeout cost is 16 seconds; numerical timeouts never interpreted as SAT/UNSAT.",
                "This is an A/B/C ablation of exact XOR early-UNSAT, not a claim of general SAT speedup."
            ]}
    save(a.json,report)
    lines=["# DRNAS V13.14 — actual 30-CNF SAT timed comparison","",
           "**30 SHA-verified SC2024 CNFs, three policies, two repetitions, 8 s cutoff, 3 GiB, one pinned CPU core.**",
           "Full Python XOR prepass startup and fallback cost included; not an official ranking.",
           "",
           "| Sample | Solver | Solved / attempts | PAR-2 seconds | Mean solved seconds |",
           "|---|---|---:|---:|---:|"]
    for group in ("all","SAT","UNSAT"):
        for mode in MODES:
            q=stats[group][mode]
            lines.append(f"| {group} | {mode} | {q['solved']}/{q['attempts']} | {q['PAR2_s']:.4f} | "
                         +(f"{q['mean_solved_s']:.4f}" if q["mean_solved_s"] is not None else "n/a")+" |")
    lines+=["",f"Verified XOR early UNSAT: {len(wins)} attempts on {len({x['id'] for x in wins})} formulas.","",
            "## Verified early-UNSAT samples","",
            "| CNF hash prefix | Repetition | Hybrid time s | Kissat time s |",
            "|---|---:|---:|---:|"]
    for x in wins:
        compare=next(y for y in diffs if y["id"]==x["id"] and y["rep"]==x["repetition"])
        lines.append(f"| {x['id'][:12]} | {x['repetition']} | {x['wall_s']:.4f} | {compare['kissat_s']:.4f} |")
    lines+=["","## Limits"]+["- "+msg for msg in report["limitations"]]
    Path(a.md).write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)
    print("V1314_AUDIT_PASS",json.dumps(stats["all"],sort_keys=True),
          "early_certified",len(wins),flush=True)

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="action",required=True)
    sub.add_parser("selftest")
    x=sub.add_parser("probe");x.add_argument("--file",required=True)
    x=sub.add_parser("run")
    for name in ("manifest","drnas","kissat","out"):x.add_argument("--"+name,required=True)
    x.add_argument("--shard",type=int,required=True)
    x=sub.add_parser("audit")
    for name in ("manifest","combined","json","md"):x.add_argument("--"+name,required=True)
    args=p.parse_args()
    if args.action=="selftest":selftest()
    elif args.action=="probe":print(json.dumps(probe(args.file),sort_keys=True))
    elif args.action=="run":run(args)
    else:audit(args)
if __name__=="__main__":main()
