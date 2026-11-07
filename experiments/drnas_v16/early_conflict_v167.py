#!/usr/bin/env python3
"""DRNAS SAT v16.7: early-conflict probes, replay-only fitting, frozen blind holdout.

Probes are independent cold Kissat runs with built-in --conflicts and -s.
They do NOT continue the solver state. Every probe second is charged to
adaptive wall time and its 25s per-instance budget. The learned policy
is immutable after replay calibration and before new holdout CNFs exist.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
import math
from pathlib import Path
import random
import re
import statistics
import subprocess
import time

SOURCE_SHA="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
CHECKPOINTS=(1000,5000,10000)
OPTIONS={
    "baseline":(),
    "target-only":("--target=2",),
    "restart-only":("--restartint=50",),
    "sat-both":("--sat",),
}
TRAIN=(("replay",640,165000),("replay",640,165001),
       ("replay",640,163007),("replay",640,163016),
       ("replay",480,165005))
HOLDOUT=(("holdout",480,167000),("holdout",640,167001),
         ("holdout",480,167002),("holdout",640,167003),
         ("holdout",480,167004),("holdout",640,167005))
STATS=("conflicts","decisions","restarts","propagations",
       "clauses_learned","clauses_used","clauses_redundant",
       "switched","search_ticks")
FIELDS=("nvars_norm","deg_cv","repeated_pair_ratio",
        "base_dec_per_conflict","base_prop_per_conflict",
        "restart_prop_per_conflict","sat_prop_per_conflict",
        "restart_used_per_learned","sat_used_per_learned",
        "sat_early_prop_growth","restart_early_prop_growth")

def generate(path,n,seed):
    # Fixed algorithm from the earlier v16.5/16.6 suite; no post-result filter.
    rng=random.Random(seed)
    m=round(4.26*n)
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="ascii") as out:
        out.write(f"c DRNAS-v167 n={n} seed={seed}\n")
        out.write(f"p cnf {n} {m}\n")
        for _ in range(m):
            vs=rng.sample(range(1,n+1),3)
            signs=(1 if rng.getrandbits(1) else -1 for _ in range(3))
            out.write(" ".join(str(v*s) for v,s in zip(vs,signs))+" 0\n")
    return hashlib.sha256(path.read_bytes()).hexdigest()

def structure(path,n):
    occurrences=[0]*n
    pairs=Counter()
    clauses=0
    for row in path.read_text(encoding="ascii").splitlines():
        if row.startswith(("c","p")) or not row:
            continue
        values=[int(v) for v in row.split()]
        if len(values)!=4 or values[-1]!=0:
            raise ValueError(f"Non 3CNF at {path}")
        vs=[abs(v)-1 for v in values[:-1]]
        clauses+=1
        for v in vs:
            occurrences[v]+=1
        for i,j in ((0,1),(0,2),(1,2)):
            pairs[tuple(sorted((vs[i],vs[j])))]+=1
    mean=sum(occurrences)/n
    variance=sum((x-mean)**2 for x in occurrences)/n
    repeated=sum(x-1 for x in pairs.values() if x>1)
    return {
        "nvars_norm":n/640,
        "deg_cv":math.sqrt(variance)/mean if mean else 0.0,
        "repeated_pair_ratio":repeated/max(1,3*clauses),
    }

def execute(solver,path,profile,timeout,conflict_cap=None,record_path=None):
    cmd=[str(solver),"-s"]
    if conflict_cap is not None:
        cmd.append(f"--conflicts={conflict_cap}")
    cmd.extend(OPTIONS[profile])
    cmd.append(str(path))
    begin=time.perf_counter()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout,check=False)
        result={0:"UNKNOWN",10:"SAT",20:"UNSAT"}.get(p.returncode,"ERROR")
        stdout=p.stdout
        stderr=p.stderr
        rc=p.returncode
    except subprocess.TimeoutExpired as exc:
        result="TIMEOUT"
        rc=-1
        stdout=(exc.stdout or b"")
        stderr=(exc.stderr or b"")
        if isinstance(stdout,bytes): stdout=stdout.decode("utf-8","replace")
        if isinstance(stderr,bytes): stderr=stderr.decode("utf-8","replace")
    elapsed=time.perf_counter()-begin
    stats={k:"" for k in STATS}
    for k,v in re.findall(r"(?m)^c\s+([a-z_]+):\s*([0-9][0-9,]*)",stdout):
        if k in stats:
            stats[k]=int(v.replace(",",""))
    if record_path:
        record_path.parent.mkdir(parents=True,exist_ok=True)
        record_path.write_text("command: "+" ".join(cmd)+
            f"\nresult: {result}, returncode: {rc}, elapsed: {elapsed:.6f}\n"+
            stdout+"\nSTDERR:\n"+stderr,encoding="utf-8")
    return dict(result=result,elapsed=elapsed,returncode=rc,**stats)

def ratio(value,other):
    if value=="" or other=="":
        raise ValueError("Missing Kissat statistics; use fail-closed policy")
    return float(value)/max(1,float(other))

def extract(probes,stats):
    # Probe keys: (profile, conflict_budget); snapshots are independent runs.
    def obj(mode,cp):
        return probes[(mode,cp)]
    def quot(mode,cp,n,d):
        x=obj(mode,cp)
        return ratio(x[n],x[d])
    f=dict(stats)
    f["base_dec_per_conflict"]=quot("baseline",10000,"decisions","conflicts")
    f["base_prop_per_conflict"]=quot("baseline",10000,"propagations","conflicts")
    f["restart_prop_per_conflict"]=quot("restart-only",10000,"propagations","conflicts")
    f["sat_prop_per_conflict"]=quot("sat-both",10000,"propagations","conflicts")
    f["restart_used_per_learned"]=quot("restart-only",10000,"clauses_used","clauses_learned")
    f["sat_used_per_learned"]=quot("sat-both",10000,"clauses_used","clauses_learned")
    f["sat_early_prop_growth"]=quot("sat-both",10000,"propagations","conflicts") / max(
            1e-6,quot("sat-both",1000,"propagations","conflicts"))
    f["restart_early_prop_growth"]=quot("restart-only",10000,"propagations","conflicts") / max(
            1e-6,quot("restart-only",1000,"propagations","conflicts"))
    return [float(f[k]) for k in FIELDS]

def probes_for(solver,path,seed,dir_,maxprobe):
    outcomes={}
    records=[]
    started=time.perf_counter()
    for cp in CHECKPOINTS:
        for mode in OPTIONS:
            log=dir_/ "raw" / f"{seed}_{mode}_{cp}.txt"
            r=execute(solver,path,mode,maxprobe,conflict_cap=cp,record_path=log)
            outcomes[(mode,cp)]=r
            entry=dict(seed=seed,profile=mode,checkpoint=cp,**r)
            records.append(entry)
            print("PROBE",seed,cp,mode,r["result"],
                  f'{r["elapsed"]:.4f}s', "conflicts",r["conflicts"],
                  "restarts",r["restarts"],flush=True)
            if r["result"]=="ERROR":
                raise RuntimeError(f"Probe failed; see {log}")
    overhead=time.perf_counter()-started
    return outcomes,records,overhead

def csv_write(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    if not rows:
        raise ValueError("Empty CSV")
    with path.open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)

def measure_all(solver,path,seed,dir_,timeout,repeats):
    rows=[]
    for rep in range(repeats):
        modes=list(OPTIONS)
        modes=modes[rep%len(modes):]+modes[:rep%len(modes)]
        for mode in modes:
            log=dir_/"full_logs"/f"{seed}_{rep}_{mode}.txt"
            r=execute(solver,path,mode,timeout,record_path=log)
            rows.append(dict(seed=seed,repeat=rep,profile=mode,**r))
            print("FULL",seed,rep,mode,r["result"],
                  f'{r["elapsed"]:.4f}s',flush=True)
            if r["result"]=="ERROR":
                raise RuntimeError(f"Solver error: {log}")
    answers={r["result"] for r in rows if r["result"] in ("SAT","UNSAT")}
    if len(answers)>1:
        raise RuntimeError(f"SAT/UNSAT conflict for {seed}: {answers}")
    return rows

def training_label(rows,timeout):
    # Explicit policy: demand at least a 15% improvement; otherwise abstain.
    aggregates={}
    for mode in OPTIONS:
        rs=[r for r in rows if r["profile"]==mode]
        aggregates[mode]=sum(r["elapsed"] if r["result"] in ("SAT","UNSAT")
                             else 2*timeout for r in rs)/len(rs)
    best=min(aggregates,key=aggregates.get)
    baseline=aggregates["baseline"]
    if best!="baseline" and aggregates[best] <= 0.85*baseline:
        return best,aggregates
    return "baseline",aggregates

def distance(a,b,scales):
    return math.sqrt(sum(((x-y)/max(s,0.01))**2 for x,y,s in zip(a,b,scales)))

def train_policy(rows):
    # Fixed nearest-prototype rule, scales learnt exclusively from replay examples.
    vectors=[r["vector"] for r in rows]
    scales=[]
    for col in zip(*vectors):
        ordered=sorted(col)
        med=statistics.median(col)
        deviations=[abs(v-med) for v in col]
        mad=statistics.median(deviations)
        scales.append(max(.02,1.4826*mad,.05*abs(med)))
    loo=[]
    for i,v in enumerate(vectors):
        near=sorted((distance(v,x,scales),j) for j,x in enumerate(vectors) if i!=j)
        loo.append(dict(seed=rows[i]["seed"],neighbor=rows[near[0][1]]["seed"],
                        distance=near[0][0],correct=rows[near[0][1]]["label"]==rows[i]["label"]))
    # Abstain for distant signatures. This threshold is frozen BEFORE holdout.
    threshold=min(3.0,max(.75,statistics.median([x["distance"] for x in loo])))
    policy=dict(version="v16.7",Kissat=SOURCE_SHA,
        checkpoint_conflicts=list(CHECKPOINTS),
        feature_names=list(FIELDS),scales=scales,
        threshold=threshold,min_neighbor_margin=1.10,
        examples=rows,
        leave_one_out=loo,explanation="nearest known replay signature; abstain to default on low confidence")
    return policy

def apply_policy(policy,vector):
    examples=policy["examples"]
    nearest=sorted((distance(vector,x["vector"],policy["scales"]),x)
                   for x in examples)
    d1,x1=nearest[0]
    # Cannot confidently distinguish close models with different labels.
    conflicts=[(dist,x) for dist,x in nearest[1:] if x["label"]!=x1["label"]]
    d2=conflicts[0][0] if conflicts else float("inf")
    confidence=(d1 <= policy["threshold"] and d2 >= d1*policy["min_neighbor_margin"])
    choice=x1["label"] if confidence else "baseline"
    return choice,d1,d2,confidence,x1["seed"]

def calibration(args):
    rows=[]
    probes_csv=[]
    solves_csv=[]
    for group,n,seed in TRAIN:
        path=args.root/"cnf"/group/f"{seed}.cnf"
        sha=generate(path,n,seed)
        print("TRAIN",seed,sha,flush=True)
        p,results,_=probes_for(args.solver,path,seed,args.root/"calibration",args.probe_timeout)
        probes_csv.extend(results)
        f=extract(p,structure(path,n))
        runs=measure_all(args.solver,path,seed,args.root/"calibration",
                         args.timeout,args.repeats)
        solves_csv.extend(runs)
        label,aggregates=training_label(runs,args.timeout)
        rows.append(dict(seed=seed,nvars=n,label=label,vector=f,
                         aggregate_PAR2=aggregates,sha256=sha))
        print("TRAIN_LABEL",seed,label,aggregates,flush=True)
    policy=train_policy(rows)
    target=args.root/"frozen-policy.json"
    target.write_text(json.dumps(policy,indent=2,sort_keys=True)+"\n",encoding="utf8")
    digest=hashlib.sha256(target.read_bytes()).hexdigest()
    (args.root/"frozen-policy.sha256").write_text(digest+"\n",encoding="ascii")
    csv_write(args.root/"calibration"/"early-probes.csv",probes_csv)
    csv_write(args.root/"calibration"/"full-results.csv",solves_csv)
    print("FROZEN_POLICY_SHA256",digest,flush=True)
    print("FROZEN_TRAIN_LABELS",[(r["seed"],r["label"]) for r in rows],flush=True)
    print("LEAVE_ONE_OUT",policy["leave_one_out"],flush=True)
    print("FROZEN_THRESHOLD",policy["threshold"],flush=True)

def evaluation(args):
    frozen=args.root/"frozen-policy.json"
    policy=json.loads(frozen.read_text(encoding="utf8"))
    expected=(args.root/"frozen-policy.sha256").read_text(encoding="ascii").strip()
    actual=hashlib.sha256(frozen.read_bytes()).hexdigest()
    if expected!=actual or policy["Kissat"]!=SOURCE_SHA:
        raise RuntimeError("Frozen policy hash or pinned Kissat commit mismatch")
    assert tuple(policy["checkpoint_conflicts"])==CHECKPOINTS
    assert tuple(policy["feature_names"])==FIELDS
    records=[]; probe_rows=[]; identities=[]; choices=[]
    for group,n,seed in HOLDOUT:
        path=args.root/"cnf"/group/f"{seed}.cnf"
        sha=generate(path,n,seed)
        identities.append(dict(seed=seed,sha256=sha,nvars=n))
        print("BLIND_SEED",seed,"sha256",sha,flush=True)
        for rep in range(args.repeats):
            # Rotate run order. Adaptive cost includes cold probes and final solve.
            modes=list(OPTIONS)+["adaptive"]
            modes=modes[rep%len(modes):]+modes[:rep%len(modes)]
            for mode in modes:
                if mode!="adaptive":
                    r=execute(args.solver,path,mode,args.timeout,
                        record_path=args.root/"evaluation"/"full_logs"/f"{seed}_{rep}_{mode}.txt")
                    row=dict(seed=seed,rep=rep,mode=mode,used_profile=mode,
                        probe_seconds=0.0,solve_seconds=r["elapsed"],
                        total_seconds=r["elapsed"],result=r["result"],
                        returncode=r["returncode"],nearest_seed="",
                        nearest_distance="",second_distance="",confident="")
                else:
                    adaptive_start=time.perf_counter()
                    probe_folder=args.root/"evaluation"/f"probe_{seed}_{rep}"
                    probes,details,_=probes_for(
                        args.solver,path,seed,probe_folder,args.probe_timeout)
                    for x in details:
                        probe_rows.append(dict(rep=rep,**x))
                    try:
                        vector=extract(probes,structure(path,n))
                        selected,d1,d2,confident,neighbor=apply_policy(policy,vector)
                    except ValueError as e:
                        print("FAIL_CLOSED",seed,str(e),flush=True)
                        selected="baseline";d1=d2=float("nan");confident=False;neighbor=-1
                    # Charge parsing, structural extraction and selection too.
                    probe_sec=time.perf_counter()-adaptive_start
                    # Wall-clock fairness: 25s INCLUDES all probe and feature costs.
                    remaining=max(0.0,args.timeout-probe_sec)
                    if remaining < .02:
                        r=dict(result="TIMEOUT",elapsed=0.0,returncode=-1)
                    else:
                        r=execute(args.solver,path,selected,remaining,
                            record_path=args.root/"evaluation"/"full_logs"/f"{seed}_{rep}_adaptive_{selected}.txt")
                    row=dict(seed=seed,rep=rep,mode=mode,used_profile=selected,
                        probe_seconds=probe_sec,solve_seconds=r["elapsed"],
                        total_seconds=probe_sec+r["elapsed"],
                        result=r["result"],returncode=r["returncode"],
                        nearest_seed=neighbor,nearest_distance=d1,
                        second_distance=d2,confident=confident)
                    choices.append(dict(seed=seed,rep=rep,profile=selected,
                        probe_seconds=probe_sec,nearest_seed=neighbor,
                        nearest_distance=d1,confidence=confident))
                    print("POLICY",seed,rep,"profile",selected,"nearest",neighbor,
                          "distance",d1,"probe",probe_sec,"confidence",confident,flush=True)
                records.append(row)
                print("RESULT",seed,rep,mode,row["result"],
                      f'{row["total_seconds"]:.4f}s',flush=True)
                if row["result"] in ("ERROR","UNKNOWN"):
                    raise RuntimeError(f"Unexpected solver result: {row}")
    csv_write(args.root/"evaluation"/"results.csv",records)
    csv_write(args.root/"evaluation"/"probes.csv",probe_rows)
    csv_write(args.root/"evaluation"/"identities.csv",identities)
    csv_write(args.root/"evaluation"/"choices.csv",choices)
    pairs=defaultdict(dict)
    for r in records:
        pairs[(r["seed"],r["rep"])][r["mode"]]=r
    for key,modes in pairs.items():
        if set(modes)!=set(OPTIONS)|{"adaptive"}:
            raise RuntimeError(f"Incomplete paired modes {key}")
        verdicts={r["result"] for r in modes.values()
                  if r["result"] in ("SAT","UNSAT")}
        if len(verdicts)>1:
            raise RuntimeError(f"SAT/UNSAT disagreement {key}: {verdicts}")
    summary=[
        "DRNAS SAT v16.7: FROZEN no-leakage blind holdout",
        "Kissat pinned commit: "+SOURCE_SHA,
        "Policy SHA256: "+actual,
        "Cold conflict-limited probes; costs fully charged to adaptive's 25s budget.",
        "UNKNOWN or no trustworthy early metrics -> fail-closed default.",
        f"Unique unseen seeds: {len(HOLDOUT)}; paired repetitions: {args.repeats}",
    ]
    for mode in list(OPTIONS)+["adaptive"]:
        rs=[r for r in records if r["mode"]==mode]
        solved=sum(r["result"] in ("SAT","UNSAT") for r in rs)
        par2=statistics.mean(r["total_seconds"] if r["result"] in ("SAT","UNSAT")
                              else 2*args.timeout for r in rs)
        median=statistics.median(r["total_seconds"] for r in rs)
        summary.append(f"{mode}: solved={solved}/{len(rs)} med={median:.4f}s PAR2={par2:.4f}s")
    for seed in sorted({r["seed"] for r in records}):
        summary.append("SEED "+str(seed))
        for mode in list(OPTIONS)+["adaptive"]:
            rs=[r for r in records if r["seed"]==seed and r["mode"]==mode]
            summary.append(f"  {mode}: med={statistics.median(x['total_seconds'] for x in rs):.4f}s "
                           f"status={'/'.join(x['result'] for x in rs)}")
    summary.append("No model tuning on these seeds; no general speedup claim.")
    text="\n".join(summary)+"\n"
    (args.root/"evaluation"/"summary.txt").write_text(text,encoding="utf8")
    print(text,flush=True)
    print("HOLDOUT_VALIDATED",len(records),len(HOLDOUT),"new seeds",flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("phase",choices=("calibrate","holdout"))
    p.add_argument("--solver",required=True)
    p.add_argument("--root",type=Path,default=Path("drnas_v167"))
    p.add_argument("--timeout",type=float,default=25.0)
    p.add_argument("--probe-timeout",type=float,default=4.0)
    p.add_argument("--repeats",type=int,default=2)
    args=p.parse_args()
    if args.repeats<1 or args.timeout<=0 or args.probe_timeout<=0:
        p.error("All limits must be positive")
    if args.phase=="calibrate":
        calibration(args)
    else:
        evaluation(args)

if __name__=="__main__":
    main()
