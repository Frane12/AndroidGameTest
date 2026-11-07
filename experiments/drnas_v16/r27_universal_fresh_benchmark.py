#!/usr/bin/env python3
"""R27 preregistered multi-family fresh SHA holdout for restart-risk hypothesis.

Six distinct synthetic families, 12 formulas each; no R24/R26 input reuse.
The native R27 gate, its thresholds and seed salt are committed before timings.
Five policies run within the SAME compiled native binary, 2 paired repeats.
"""
import argparse
import csv
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import re
import statistics
import subprocess
import sys
import time

SALT = "DRNAS-R27-FRESH-GENERATOR-SALT-20261103-4096-GATE-LOCKED-BEFORE-TEST-v1"
UPSTREAM = "8af8e56f174b778aef3aa45af9f739b2a5f492c2"
CAP = 2.0
REPEATS = 2
SHARDS = 4
N_PER_FAMILY = 12
FAMILIES = (
    ("random3_220_423", 220, 4.23),
    ("random3_280_423", 280, 4.23),
    ("random3_220_385", 220, 3.85),
    ("random3_220_465", 220, 4.65),
    ("community3_220", 220, 4.23),
    ("tseitin_xor_64", 64, 0.0),
)
MODES = {
    "monitor": "r5_monitor",
    "switch2048_25": "r11_2048_25",
    "switch2048_50": "r11_2048_50",
    "switch4096_50": "r11_4096_50",
    "R27_guarded": "r27_cautious_late50",
}
PROTO = "DRNAS-R27-FRESH-SIX-FAMILY-FROZEN-20261103-v1"

def sha(data):
    return hashlib.sha256(data).hexdigest()

def rnd(family,i):
    return random.Random(int(sha(f"{SALT}/{family}/{i}".encode()), 16))

def random3_case(family, n, density, i):
    rng = rnd(family,i)
    community = family.startswith("community")
    clauses = []
    for _ in range(round(n*density)):
        if community and rng.random() < 0.65:
            q = n // 4
            start = rng.randrange(4)*q + 1
            vs = rng.sample(range(start, start+q),3)
        else:
            vs = rng.sample(range(1,n+1),3)
        clauses.append([v if rng.getrandbits(1) else -v for v in vs])
    return n, clauses, None

def xor_case(family,n,i):
    rng=rnd(family,i)
    if n%2: raise RuntimeError("N must be even")
    ring={tuple(sorted((v,(v+1)%n))) for v in range(n)}
    for k in range(100):
        perm=list(range(n));rng.shuffle(perm)
        match={tuple(sorted((perm[j],perm[j+n//2]))) for j in range(n//2)}
        if len(match)==n//2 and not (match & ring):
            break
    else:
        raise RuntimeError("Could not generate disjoint cubic matching")
    edges=sorted(ring|match)
    if len(edges)!=3*n//2: raise RuntimeError("Wrong cubic edge count")
    incident=[[] for _ in range(n)]
    for idx,(u,v) in enumerate(edges,1):
        incident[u].append(idx);incident[v].append(idx)
    if any(len(c)!=3 for c in incident):raise RuntimeError("Not degree 3")
    witness={idx:rng.getrandbits(1) for idx in range(1,len(edges)+1)}
    rhs=[sum(witness[x] for x in c)%2 for c in incident]
    unsat=i%2==0
    if unsat:
        rhs[0]^=1
        if sum(rhs)%2!=1:raise RuntimeError("Bad parity witness")
    clauses=[]
    for vs, parity in zip(incident,rhs):
        for mask in range(8):
            bits=[mask>>b&1 for b in range(3)]
            if sum(bits)%2 != parity:
                clauses.append([-v if bit else v for v,bit in zip(vs,bits)])
    if not unsat:
        if any(not any((x>0)==bool(witness[abs(x)]) for x in c) for c in clauses):
            raise RuntimeError("Planted witness failed")
    return len(edges), clauses, "UNSAT" if unsat else "SAT"

def freeze(root):
    root.mkdir(parents=True,exist_ok=True)
    cases=[]
    for family,n,density in FAMILIES:
        for i in range(N_PER_FAMILY):
            if family.startswith("tseitin"):
                v,c,expected=xor_case(family,n,i)
            else:
                v,c,expected=random3_case(family,n,density,i)
            data=(f"p cnf {v} {len(c)}\n" +
                  "".join(" ".join(map(str,row))+" 0\n" for row in c)).encode()
            name=f"{family}_{i:02}.cnf"
            (root/name).write_bytes(data)
            cases.append(dict(name=name,family=family,sha256=sha(data),
                              n=v,m=len(c),expected=expected,
                              seed_label=f"{SALT}/{family}/{i}"))
    if len(cases)!=72 or len({x["sha256"] for x in cases})!=72:
        raise RuntimeError("Wrong count or duplicate cases")
    manifest=dict(protocol=PROTO,salt=SALT,upstream=UPSTREAM,
                  cap=CAP,repeats=REPEATS,shards=SHARDS,modes=MODES,
                  families=[x[0] for x in FAMILIES],
                  notes=["Synthetic family diversity cannot establish universal SAT performance",
                         "Rule thresholds derived from earlier R26 insights, frozen before these data",
                         "All measurements include time from process start",
                         "Paired per same case and machine; individual runners may vary",
                         "Original UNSAT proof certificates not independently verified",
                         "SAT models checked against original CNF",
                         "PAR-2 timeout penalty is 4 seconds"],
                  cases=cases)
    (root/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    print("R27_MANIFEST_FROZEN",len(cases),sha((root/"manifest.json").read_bytes()),flush=True)
    for family,*_ in FAMILIES:
        print("R27_FAMILY",family,N_PER_FAMILY,flush=True)

def parse_clauses(path):
    clauses=[]
    for line in path.read_text().splitlines():
        if not line or line.startswith(("p ","c ","%")):continue
        vals=[int(v) for v in line.split()]
        if not vals or vals[-1]!=0:
            raise RuntimeError("Bad DIMACS line")
        clauses.append(vals[:-1])
    return clauses

def attempt(binary,path,case,mode,rep,clauses):
    env=os.environ.copy()
    env.update(DRNAS_V177_MODE=MODES[mode],DRNAS_R13_N=str(case["n"]),
               DRNAS_R12_DEGREE_CV="0.28",DRNAS_R16_GINI="0.16",
               DRNAS_R16_POLARITY="0.22")
    started=time.monotonic()
    try:
        proc=subprocess.run([str(binary),str(path)],capture_output=True,text=True,
                            errors="replace",env=env,timeout=CAP)
        sec=time.monotonic()-started
        output=proc.stdout
        if proc.returncode not in (10,20):
            raise RuntimeError(f"Bad exit {proc.returncode} {case['name']} {mode}: {proc.stderr[-400:]}")
        status="SAT" if proc.returncode==10 else "UNSAT"
        if case["expected"] and status!=case["expected"]:
            raise RuntimeError(f"Incorrect known parity status: {case['name']} {status}")
        if status=="SAT":
            lits=[int(k) for line in output.splitlines() if line.startswith("v ")
                  for k in line.split()[1:] if k!="0"]
            assignment={abs(x):x>0 for x in lits}
            if not lits or not all(any(assignment.get(abs(v))==(v>0) and abs(v) in assignment
                                       for v in cl) for cl in clauses):
                raise RuntimeError(f"Invalid SAT witness: {case['name']} {mode}")
    except subprocess.TimeoutExpired as e:
        sec=time.monotonic()-started
        status="TIMEOUT"
        output=e.stdout or b""
        if isinstance(output,bytes):output=output.decode(errors="replace")
    gates=[line for line in output.splitlines() if line.startswith("c R27_GATE")]
    switches=[line for line in output.splitlines() if line.startswith("c DRNAS_V177_SWITCH")]
    return dict(formula=case["name"],family=case["family"],mode=mode,
                repeat=rep,status=status,seconds=round(sec,6),
                par2=round(sec,6) if status!="TIMEOUT" else 2*CAP,
                gate=gates[-1] if gates else None,switched=bool(switches))

def measure(a):
    root=Path(a.inputs); manifest=json.loads((root/"manifest.json").read_text())
    if (manifest["protocol"]!=PROTO or manifest["modes"]!=MODES
        or manifest["cap"]!=CAP or manifest["repeats"]!=REPEATS
        or manifest["salt"]!=SALT):
        raise RuntimeError("Manifest mismatch")
    if not 0<=a.shard<SHARDS:raise RuntimeError("Shard out of range")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    selected=manifest["cases"][a.shard::SHARDS]
    out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    b=Path(a.binary).resolve()
    if not b.is_file():raise RuntimeError("Missing binary")
    meta=dict(shard=a.shard,manifest_sha256=sha((root/"manifest.json").read_bytes()),
              binary_sha256=sha(b.read_bytes()),cases=len(selected),
              cpu=next((x for x in Path("/proc/cpuinfo").read_text().splitlines()
                        if x.startswith("model name")),"unknown"))
    (out/"metadata.json").write_text(json.dumps(meta,indent=2)+"\n")
    rows=[]
    for case in selected:
        path=(root/case["name"]).resolve()
        if sha(path.read_bytes())!=case["sha256"]:raise RuntimeError("SHA mismatch "+case["name"])
        clauses=parse_clauses(path)
        for rep in range(REPEATS):
            modes=list(MODES)
            rng=rnd(case["name"]+"_order",rep)
            rng.shuffle(modes)
            for mode in modes:
                x=attempt(b,path,case,mode,rep,clauses)
                rows.append(x)
                print("R27_TRIAL",a.shard,case["name"],rep,mode,x["status"],
                      x["seconds"],"switched",int(x["switched"]),flush=True)
                (out/"rows.json").write_text(json.dumps(rows,indent=1)+"\n")
        answers={x["status"] for x in rows if x["formula"]==case["name"]} - {"TIMEOUT"}
        if len(answers)>1: raise RuntimeError("SAT UNSAT disagreement "+case["name"])
    print("R27_SHARD_DONE",a.shard,len(rows),flush=True)

def aggregate(a):
    inputroot=Path(a.inputs); manifest=json.loads((inputroot/"manifest.json").read_text())
    combined=Path(a.combined)
    allrows=[]
    orig_sha=sha((inputroot/"manifest.json").read_bytes())
    bin_sha=None
    for shard in range(SHARDS):
        part=combined/f"r27-shard-{shard}"/"results"
        metadata=json.loads((part/"metadata.json").read_text())
        if metadata["manifest_sha256"]!=orig_sha or metadata["shard"]!=shard:
            raise RuntimeError("Shard identity mismatch")
        if bin_sha is None:bin_sha=metadata["binary_sha256"]
        if metadata["binary_sha256"]!=bin_sha:raise RuntimeError("Binary inconsistency")
        rows=json.loads((part/"rows.json").read_text())
        if len(rows)!=len(manifest["cases"][shard::SHARDS])*REPEATS*len(MODES):
            raise RuntimeError("Incomplete shard "+str(shard))
        allrows+=rows
    if len(allrows)!=72*REPEATS*len(MODES):raise RuntimeError("Incomplete 720 attempts")
    lookup={x["name"]:x for x in manifest["cases"]}
    grouped={}
    for family in ["ALL"]+manifest["families"]:
        cases=[c for c in manifest["cases"] if family=="ALL" or c["family"]==family]
        summary={}
        for mode in MODES:
            meanpen=[];solved=0;timeouts=0;switches=0;gates=0;reg2=0
            for case in cases:
                trials=[x for x in allrows if x["formula"]==case["name"] and x["mode"]==mode]
                if len(trials)!=REPEATS:raise RuntimeError("Missing mode "+case["name"])
                meanpen+= [x["par2"] for x in trials]
                solved+=int(all(x["status"]!="TIMEOUT" for x in trials))
                timeouts+=sum(x["status"]=="TIMEOUT" for x in trials)
                switches+=sum(x["switched"] for x in trials)
                gates+=sum(x["gate"] is not None for x in trials)
                base=[x["par2"] for x in allrows if x["formula"]==case["name"] and x["mode"]=="monitor"]
                if len(base)!=REPEATS:raise RuntimeError("Missing baseline")
                if statistics.median(x["par2"] for x in trials)>2*statistics.median(base):
                    reg2+=1
            summary[mode]=dict(solved_cases=solved,n_cases=len(cases),
                               timeouts=timeouts,mean_PAR2=round(statistics.mean(meanpen),6),
                               sum_PAR2=round(sum(meanpen),6),switched_attempts=switches,
                               reached_gate_attempts=gates,regressions_gt2x=reg2)
        base=summary["monitor"]["sum_PAR2"]
        for mode in MODES:
            summary[mode]["gain_pct"]=round(100*(base-summary[mode]["sum_PAR2"])/base,3)
        grouped[family]=summary
        print("R27_SUMMARY",family,json.dumps(summary,sort_keys=True),flush=True)
    output=dict(protocol=PROTO,manifest_sha256=orig_sha,binary_sha256=bin_sha,
                groups=grouped,rows=allrows,
                restrictions=["Six synthetic families only: not a universal solver proof",
                              "Rule was motivated by known R26 cases, frozen before R27 holdout",
                              "No official SAT Competition leaderboard equivalence",
                              "UNSAT original proof verification not performed"])
    Path(a.output).write_text(json.dumps(output,indent=2)+"\n")
    md=["# DRNAS SAT R27 — fresh SHA-separated six-family holdout",
        f"72 CNFs × {REPEATS} paired repetitions × {len(MODES)} policies = 720 attempts.",
        "Cap 2 s; PAR-2 penalty for timeout = 4 s; lower is better.",
        "The R27 decision uses only live 4096-conflict telemetry, with an abstention fallback.",
        "Synthetic diversity is NOT a proof of universal benefit or official championship performance.",
        "",
        "| Family | Baseline PAR-2 sum (s) | R27 PAR-2 sum (s) | R27 gain | Selected attempts | >2× regressions |",
        "|---|---:|---:|---:|---:|---:|"]
    for family,g in grouped.items():
        b=g["monitor"];v=g["R27_guarded"]
        md.append(f"| {family} | {b['sum_PAR2']:.3f} | {v['sum_PAR2']:.3f} | {v['gain_pct']:+.2f}% | {v['switched_attempts']} | {v['regressions_gt2x']} |")
    md+=["","## All-arm overall", "| Mode | PAR-2 sum (s) | solved (cases) | switched attempts | >2× regressions |",
          "|---|---:|---:|---:|---:|"]
    for mode,g in grouped["ALL"].items():
        md.append(f"| {mode} | {g['sum_PAR2']:.3f} | {g['solved_cases']}/72 | {g['switched_attempts']} | {g['regressions_gt2x']} |")
    Path(a.md).write_text("\n".join(md)+"\n")
    with Path(a.csv).open("w",newline="") as f:
        w=csv.writer(f);w.writerow(["formula","family","mode","repeat","status","seconds","par2","switched","gate"])
        for x in allrows:
            w.writerow([x[k] for k in ("formula","family","mode","repeat","status","seconds","par2","switched","gate")])
    print("R27_AUDIT_PASS",len(allrows),"attempts",len(manifest["cases"]),"formulas",flush=True)

def main():
    p=argparse.ArgumentParser()
    subs=p.add_subparsers(dest="command",required=True)
    x=subs.add_parser("prepare");x.add_argument("--outdir",required=True)
    x=subs.add_parser("measure")
    for s in ("inputs","binary","outdir"):x.add_argument("--"+s,required=True)
    x.add_argument("--shard",type=int,required=True)
    x=subs.add_parser("aggregate")
    for s in ("inputs","combined","output","md","csv"):x.add_argument("--"+s,required=True)
    args=p.parse_args()
    if args.command=="prepare":freeze(Path(args.outdir))
    elif args.command=="measure":measure(args)
    elif args.command=="aggregate":aggregate(args)

if __name__=="__main__":
    main()
