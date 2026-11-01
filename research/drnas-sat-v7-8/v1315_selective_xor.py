#!/usr/bin/env python3
"""V13.15 guarded exact-XOR SAT hybrid: prospective *policy*, retrospective *data*.

Cheap fixed gate (input size <=96 KiB, >=16 exact complete 3-XOR blocks)
decides whether to run the prior full certified V13.12 prepass. Both the gate
and full prepass wall time count toward the same 8 s cutoff as the solvers.
No instance IDs, labels, or previously measured runtimes are consulted.

Paired comparison on the *same* 30 original 2024 CNFs seen in V13.13/14:
V13.15 selective, always-on V13.12 hybrid, Kissat404, DRNAS Legacy.
This is exploratory; a NEW SHA-disjoint holdout is necessary after this study.
"""
import argparse
import collections
import hashlib
import json
import os
import random
import resource
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import official_shortlong_select as source
import v1314_timed_ab as prev
import v1312_sparse_gf2 as sparse

PROTOCOL="DRNAS-V1315-SELECTIVE-XOR-30CNF-TIMED-20261101-v1"
FREEZE=prev.SOURCE_PROTOCOL
CAP=8.0
REPS=2
SHARDS=10
MODES=("Kissat404","DRNAS_Legacy","V1312_XOR_Kissat","V1315_SELECTIVE_XOR")
GATE_MAX_BYTES=96*1024
GATE_MIN_XOR=16
MEMORY_GIB=3
source.RAW_CAP=96*1024**2
source.CNF_CAP=64*1024**2
source.VARIABLE_CAP=500000
source.CLAUSE_CAP=1000000

def require(ok,message):
    if not ok: raise RuntimeError(message)

def load(path):
    return json.loads(Path(path).read_text())

def save(path,obj):
    p=Path(path)
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for part in iter(lambda:f.read(1024*1024),b""):
            h.update(part)
    return h.hexdigest()

def limit():
    n=MEMORY_GIB*1024**3
    resource.setrlimit(resource.RLIMIT_AS,(n,n))

def gate(path):
    """Only structural input, no official labels or solver performance; fail closed."""
    p=Path(path)
    size=p.stat().st_size
    if size>GATE_MAX_BYTES:
        return {"eligible":False,"reason":"over_fixed_size_cap",
                "bytes":size,"xor_blocks":None}
    n,m,eq,diag=sparse.prior.extract(path)
    complete=diag["extraction_complete"]
    if not complete:
        return {"eligible":False,"reason":"truncated_extract",
                "bytes":size,"xor_blocks":len(eq)}
    return {"eligible":len(eq)>=GATE_MIN_XOR,
            "reason":"structural_candidate" if len(eq)>=GATE_MIN_XOR else
                     "insufficient_complete_3xor",
            "bytes":size,"xor_blocks":len(eq)}

def child_probe(path):
    start=time.monotonic()
    g=gate(path)
    out={"gate":g,"certified_contradiction":False,"certified_units":0,
         "probe_wall_s":0.0}
    if g["eligible"]:
        full=prev.probe(path)
        out["certified_contradiction"]=bool(full["verified_contradiction"])
        out["certified_units"]=full["certified_forced_literals"]
    out["probe_wall_s"]=round(time.monotonic()-start,6)
    return out

def selective_trial(path,seed,drnas,kissat,expected):
    start=time.monotonic()
    try:
        p=subprocess.run(
            [sys.executable,str(Path(__file__).resolve()),"probe",
             "--file",str(Path(path).resolve())],
            capture_output=True,text=True,errors="replace",timeout=CAP,
            preexec_fn=limit,check=False)
        passed=time.monotonic()-start
        require(p.returncode==0,"selective prepass error: "+p.stderr[-270:])
        diag=json.loads(p.stdout)
        if diag["certified_contradiction"]:
            status="UNSAT"
            reason="replay_verified_exact_xor_unsat"
        elif passed>=CAP:
            status="TIMEOUT";reason="gate_consumed_cap"
        else:
            status,_,_=prev.exec_solver("Kissat404",path,seed,drnas,kissat,CAP-passed)
            reason="fallback_"+diag["gate"]["reason"]
        elapsed=time.monotonic()-start
        if elapsed>CAP+0.02:status="TIMEOUT"
        require(status in ("SAT","UNSAT","TIMEOUT"),"invalid status")
        if status!="TIMEOUT":require(status==expected,"verdict differs from published label")
        return {"status":status,"wall_s":round(min(elapsed,CAP),6),
                "probe_wall_s":round(passed,6),"reason":reason,
                "gate":diag["gate"],"certified_contradictions":
                int(diag["certified_contradiction"]),"error":""}
    except subprocess.TimeoutExpired:
        return {"status":"TIMEOUT","wall_s":CAP,"probe_wall_s":CAP,
                "reason":"probe_timeout","gate":None,
                "certified_contradictions":0,"error":""}
    except Exception as exc:
        return {"status":"ERROR",
                "wall_s":round(min(time.monotonic()-start,CAP),6),
                "probe_wall_s":0,"reason":"error","gate":None,
                "certified_contradictions":0,"error":f"{type(exc).__name__}: {exc}"[:280]}

def trial(mode,path,seed,drnas,kissat,expected):
    if mode=="V1315_SELECTIVE_XOR":
        return selective_trial(path,seed,drnas,kissat,expected)
    x=prev.timed_trial(mode,path,seed,drnas,kissat,expected)
    return {"status":x["status"],"wall_s":x["wall_s"],
            "probe_wall_s":x["probe_wall_s"],"reason":x["reason"],
            "gate":None,"certified_contradictions":x["certified_contradictions"],
            "error":x["error"]}

def selftest():
    import v1311_local_xor as xor
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/"test.cnf"
        edges=[(1,2,3),(1,4,5),(2,4,6),(3,5,6)]
        # Four blocks with contradictory parity; chosen threshold of 16
        # requires many synthetically disjoint 3-XOR blocks.
        equations=[]
        for offset in (0,10,20,30,40):
            equations.extend([(tuple(v+offset for v in e),int(i==3))
                              for i,e in enumerate(edges)])
        p.write_bytes(xor.synthetic(equations))
        z=child_probe(p)
        require(z["gate"]["eligible"] and z["certified_contradiction"],
                "missed exact unsat in gated branch")
        require(not xor.brute_models(xor.synthetic([(e,int(i==3))
                for i,e in enumerate(edges)])), "unsafe contradiction proof")
        p.write_bytes(xor.synthetic([((1,2,3),0)],extras=[(4,)]))
        z=child_probe(p)
        require(not z["gate"]["eligible"] and not z["certified_contradiction"],
                "incorrect trivial fallback")
        p.write_bytes(b"p cnf 1 1\n1 0\n"+b"c filler\n"*(GATE_MAX_BYTES//8+1))
        z=child_probe(p)
        require(z["gate"]["reason"]=="over_fixed_size_cap","large file failed gating")
    print("V1315_SELFTEST_PASS: threshold gate, replay-verified UNSAT, safe bypass",flush=True)

def run(a):
    m=load(a.manifest)
    prev.validate_manifest(m)
    require(0<=a.shard<SHARDS,"invalid shard")
    cases=m["cases"][a.shard::SHARDS]
    require(len(cases)==3,"missing cases")
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    cpu=next((ln.split(":",1)[1].strip() for ln in
              Path("/proc/cpuinfo").read_text().splitlines()
              if ln.startswith("model name")),"unknown")
    info={"protocol":PROTOCOL,"shard":a.shard,"sha256s":[x["sha256"] for x in cases],
          "cpu_model":cpu,"cpu_affinity":len(os.sched_getaffinity(0)),
          "binary_sha256s":{k:sha(v) for k,v in
                            (("kissat",a.kissat),("drnas",a.drnas))},
          "script_sha256":sha(__file__),"prior_v1314_sha256":sha(prev.__file__),
          "sparse_sha256":sha(sparse.__file__),"cap":CAP,"reps":REPS,
          "gate_max_bytes":GATE_MAX_BYTES,"gate_min_xor":GATE_MIN_XOR}
    save(out/"meta.json",info)
    rows=[]
    for case in cases:
        f=out/(case["id"]+".cnf")
        got=source.download_and_features(case["id"],f)
        require(got["sha256"]==case["sha256"] and
                got["features"]==case["features"],"SHA/features mismatch")
        for rep in range(REPS):
            seed=(20241315+104729*rep+int(case["sha256"][:8],16))%(2**32)
            order=list(MODES)
            random.Random(seed^131515).shuffle(order)
            for mode in order:
                result=trial(mode,f,seed,a.drnas,a.kissat,case["official_label"])
                rows.append({"id":case["id"],"sha256":case["sha256"],
                             "label":case["official_label"],"rep":rep,
                             "mode":mode,"seed":seed,**result})
                save(out/"rows.json",rows)
                print("V1315_TRIAL",a.shard,case["id"][:12],rep,
                      mode,result["status"],result["wall_s"],
                      "gate",result["gate"]["reason"] if result["gate"] else "-",
                      "reason",result["reason"],flush=True)
                require(result["status"]!="ERROR","abort bad verdict/command: "+result["error"])
        f.unlink(missing_ok=True)
    require(len(rows)==3*REPS*len(MODES),"incomplete case run")
    print("V1315_SHARD_PASS",a.shard,len(rows),flush=True)

def audit(a):
    m=load(a.manifest)
    prev.validate_manifest(m)
    cases={x["id"]:x for x in m["cases"]}
    all_rows=[]
    signatures=set()
    cpu=set()
    for shard in range(SHARDS):
        f=Path(a.combined)/f"v1315-shard-{shard}"
        meta=load(f/"meta.json")
        r=load(f/"rows.json")
        require(meta["protocol"]==PROTOCOL and meta["shard"]==shard and
                meta["sha256s"]==[x["sha256"] for x in m["cases"][shard::SHARDS]]
                and meta["cap"]==CAP and meta["reps"]==REPS
                and meta["gate_max_bytes"]==GATE_MAX_BYTES
                and meta["gate_min_xor"]==GATE_MIN_XOR
                and meta["cpu_affinity"]==1, "misconfigured shard")
        signatures.add(json.dumps([meta[x] for x in (
            "binary_sha256s","script_sha256","prior_v1314_sha256","sparse_sha256")],
            sort_keys=True))
        cpu.add(meta["cpu_model"])
        require(len(r)==3*REPS*len(MODES),"missing trials in shard")
        all_rows+=r
    require(len(signatures)==1,"runner code/binary drift")
    keys=set()
    for r in all_rows:
        c=cases[r["id"]];key=(r["id"],r["rep"],r["mode"])
        require(key not in keys,"duplicate result")
        keys.add(key)
        require(r["sha256"]==c["sha256"] and r["label"]==c["official_label"]
                and r["mode"] in MODES and r["rep"] in (0,1)
                and r["status"] in ("SAT","UNSAT","TIMEOUT")
                and 0<=r["wall_s"]<=CAP+0.02 and not r["error"],
                "unverified record")
        require(r["status"]=="TIMEOUT" or r["status"]==c["official_label"],
                "wrong solver result")
    require(len(keys)==30*REPS*len(MODES),"not all attempts audited")
    summary={}
    for cohort in ("all","SAT","UNSAT"):
        rr=[x for x in all_rows if cohort=="all" or x["label"]==cohort]
        summary[cohort]={}
        for mode in MODES:
            xs=[r for r in rr if r["mode"]==mode]
            solved=[r["wall_s"] for r in xs if r["status"]!="TIMEOUT"]
            par=[r["wall_s"] if r["status"]!="TIMEOUT" else 2*CAP for r in xs]
            summary[cohort][mode]={"solved":len(solved),"attempts":len(xs),
                    "PAR2_s":round(statistics.mean(par),6),
                    "mean_solved_s":round(statistics.mean(solved),6) if solved else None,
                    "timeouts":len(xs)-len(solved)}
    sel=[x for x in all_rows if x["mode"]=="V1315_SELECTIVE_XOR"]
    route=collections.Counter(x["gate"]["reason"] if x["gate"] else "unknown" for x in sel)
    proof=[x for x in sel if x["reason"]=="replay_verified_exact_xor_unsat"]
    report={"protocol":PROTOCOL,"sample":30,"attempts":len(all_rows),
            "policies":list(MODES),"summary":summary,
            "selective_routes":dict(route),"certified_early_unsat_trials":len(proof),
            "certified_early_unsat_distinct_cases":len({x["id"] for x in proof}),
            "cpu_models":sorted(cpu),"trials":all_rows,
            "limitations":[
                "30 formulas were already used in V13.13 and V13.14: EXPLORATORY evaluation, not blind holdout for this chosen gate.",
                "Gate threshold 96 KiB and 16 parity blocks chosen after earlier dataset inspection; selection bias possible.",
                "8s cap, 3GiB RAM, single CPU affinity; not official SAT Competition 2024 settings.",
                "Each policy timed from process invocation; selective includes Python startup and gate, always-on includes full prepass.",
                "SAT/UNSAT results match published labels; we do not independently validate all baseline solver certificates.",
                "A false positive proof is prohibited by replay verification; no SAT result inferred from parity consistency.",
                "Best generalization requires an independently frozen new 2024/2025/2026 cohort."
            ]}
    save(a.json,report)
    lines=["# DRNAS V13.15 — selective XOR vs Kissat / always-on XOR / DRNAS",
           "","30 earlier frozen genuine 2024 CNFs, 2 repeats, 8s cutoff, 3GiB, one pinned core.",
           "**Exploratory retrospective test, not fresh blind holdout.**","",
           "| Class | Policy | Solved | PAR2 s | Mean solved s |",
           "|---|---|---:|---:|---:|"]
    for cohort in ("all","SAT","UNSAT"):
        for mode in MODES:
            q=summary[cohort][mode]
            lines.append(f"| {cohort} | {mode} | {q['solved']}/{q['attempts']} | "
                         f"{q['PAR2_s']:.4f} | "
                         f"{q['mean_solved_s']:.4f}" if q["mean_solved_s"] is not None else
                         f"| {cohort} | {mode} | {q['solved']}/{q['attempts']} | {q['PAR2_s']:.4f} | n/a |")
            if q["mean_solved_s"] is not None:
                lines[-1] += " |"
    lines += ["","## Selective gate outcomes"]
    lines += [f"- {k}: {v} / 60 attempts" for k,v in sorted(route.items())]
    lines += ["",f"Replay-verified early UNSAT: {len(proof)} attempts in {len({x['id'] for x in proof})} distinct formulas.",
              "","## Limits"]
    lines += ["- "+s for s in report["limitations"]]
    Path(a.md).write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)
    print("V1315_AUDIT_PASS",json.dumps(summary["all"],sort_keys=True),
          "routes",dict(route),"proof_trials",len(proof),flush=True)

def main():
    p=argparse.ArgumentParser()
    cmd=p.add_subparsers(dest="action",required=True)
    cmd.add_parser("selftest")
    q=cmd.add_parser("probe");q.add_argument("--file",required=True)
    q=cmd.add_parser("run")
    for field in ("manifest","kissat","drnas","out"):
        q.add_argument("--"+field,required=True)
    q.add_argument("--shard",type=int,required=True)
    q=cmd.add_parser("audit")
    for field in ("manifest","combined","json","md"):
        q.add_argument("--"+field,required=True)
    args=p.parse_args()
    if args.action=="selftest":selftest()
    elif args.action=="probe":print(json.dumps(child_probe(args.file),sort_keys=True))
    elif args.action=="run":run(args)
    else:audit(args)

if __name__=="__main__":main()
