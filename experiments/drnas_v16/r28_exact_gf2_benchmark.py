#!/usr/bin/env python3
"""DRNAS R28: SHA-frozen 240-case six-family GF(2) study + known R27 replay.

R28 has only two answer-producing routes: exact complete XOR CNF blocks plus
Gaussian elimination, or exec of the original SHA-pinned upstream Kissat.
Every SAT witness is rechecked on original DIMACS; every direct XOR UNSAT is
checked independently by verifying the parity clauses and 0=1 row XOR.
This is NOT a proof of general P=NP or a new theoretical SAT breakthrough.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import random
import re
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict

PROTO = "DRNAS-R28-EXACT-GF2-FRESH-20261103-v1"
SALT = "DRNAS-R28-INDEPENDENT-GF2-SALT-NOV03-LOCKED-BEFORE-MEASUREMENT"
UPSTREAM = "8af8e56f174b778aef3aa45af9f739b2a5f492c2"
FAMILIES = ("pure_xor3","pure_xor6","mixed_xor3","near_xor_decoy",
            "random3_critical","community3")
N_PER = 40
SHARDS = 4
REPS = 2
CAP = 2.0
MODES = ("Kissat_pin","R28_exact_gf2")
# All 240 input formulas are new relative to the R24-R27 experiments.

def digest(data):
    if isinstance(data,Path):data=data.read_bytes()
    return hashlib.sha256(data).hexdigest()

def check(v,why):
    if not v:raise RuntimeError("R28_AUDIT_ERROR "+why)

def rng_for(family,idx):
    return random.Random(int(digest((SALT+"/"+family+"/"+str(idx)).encode()),16))

def dimacs(n,clauses):
    return (f"p cnf {n} {len(clauses)}\n" +
            "".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode()

def graph_xor(k,n,rng):
    # Edges are variables, vertices are XOR constraints. Every edge has
    # exactly two endpoints and odd total RHS is a GF2 UNSAT certificate.
    if k==3:
        ring={tuple(sorted((v,(v+1)%n))) for v in range(n)}
        for _ in range(1000):
            order=list(range(n));rng.shuffle(order)
            match={tuple(sorted((order[j],order[j+n//2])))
                   for j in range(n//2)}
            if len(match)==n//2 and not (ring & match):break
        else:raise RuntimeError("Matching generation exhausted")
        edges=sorted(ring|match)
    elif k==6:
        edges=sorted({tuple(sorted((v,(v+d)%n)))
                      for v in range(n) for d in (1,2,3)})
    else:raise RuntimeError("Unexpected XOR width")
    inc=[[] for _ in range(n)]
    for idx,(a,b) in enumerate(edges,1):
        inc[a].append(idx);inc[b].append(idx)
    check(all(len(v)==k for v in inc),"Not a regular graph")
    check(len(edges)*2==n*k,"Wrong incidence count")
    return inc,len(edges)

def xor_case(family,idx):
    rng=rng_for(family,idx)
    k=6 if family=="pure_xor6" else 3
    n=24+(idx%3)*4 if k==6 else 64+(idx%4)*8
    inc,variables=graph_xor(k,n,rng)
    truth={x:rng.getrandbits(1) for x in range(1,variables+1)}
    rhs=[sum(truth[x] for x in row)%2 for row in inc]
    unsat=idx%2==0
    if unsat:
        rhs[0]^=1
        check(sum(rhs)%2==1,"Parity contradiction absent")
    clauses=[]
    for row,p in zip(inc,rhs):
        for mask in range(1<<k):
            if (mask.bit_count()&1)!=p:
                clause=[-v if (mask>>j)&1 else v for j,v in enumerate(row)]
                rng.shuffle(clause)
                clauses.append(clause)
    if family=="mixed_xor3":
        for _ in range(8+(idx%13)):
            vs=rng.sample(range(1,variables+1),3)
            lits=[-v if rng.getrandbits(1) else v for v in vs]
            if not unsat and not any(((x>0)==bool(truth[abs(x)])) for x in lits):
                lits[0]*=-1
            clauses.append(lits)
    rng.shuffle(clauses)
    if not unsat:
        check(all(any((v>0)==bool(truth[abs(v)]) for v in c)
                  for c in clauses),"Planted SAT model fails")
    return variables,clauses,"UNSAT" if unsat else "SAT"

def ordinary_case(family,idx):
    rng=rng_for(family,idx)
    n=220+(idx%3)*30 if family=="random3_critical" else 220
    if family=="near_xor_decoy": n=220
    count=round(n*4.23)
    clauses=[]
    for _ in range(count):
        if family=="community3" and rng.random()<0.78:
            size=n//4
            start=rng.randrange(4)*size+1
            vs=rng.sample(range(start,start+size),3)
        else:
            vs=rng.sample(range(1,n+1),3)
        clauses.append([-v if rng.getrandbits(1) else v for v in vs])
    if family=="near_xor_decoy":
        for z in range(6):
            vs=rng.sample(range(1,n+1),3)
            parity=rng.getrandbits(1)
            bad=[m for m in range(8) if (m.bit_count()&1)!=parity]
            rng.shuffle(bad)
            for mask in bad[:3]:
                clauses.append([-v if (mask>>j)&1 else v for j,v in enumerate(vs)])
    rng.shuffle(clauses)
    return n,clauses,None

def freeze(root):
    root.mkdir(parents=True,exist_ok=True)
    cases=[]
    for family in FAMILIES:
        for idx in range(N_PER):
            if family.startswith("pure_") or family=="mixed_xor3":
                n,clauses,expect=xor_case(family,idx)
            else:
                n,clauses,expect=ordinary_case(family,idx)
            name=f"{family}_{idx:02d}.cnf"
            raw=dimacs(n,clauses)
            (root/name).write_bytes(raw)
            cases.append({"name":name,"family":family,"idx":idx,
                          "sha256":digest(raw),"n":n,"m":len(clauses),
                          "expected":expect})
    check(len(cases)==240,"Expected 240 inputs")
    check(len({c["sha256"] for c in cases})==240,"Duplicate generated CNFs")
    manifest=dict(protocol=PROTO,salt=SALT,pinned_upstream=UPSTREAM,
                  cases=cases,families=FAMILIES,modes=MODES,shards=SHARDS,
                  repeats=REPS,cap_s=CAP,known_replay_excluded=True,
                  caution=["All fresh cases generated before timing by fixed SHA-salted generators",
                           "No actual industrial instances in the 240-case synthetic suite",
                           "Known R27 Tseitin case is replayed separately and excluded from fresh totals",
                           "Only exact complete parity blocks permit a GF2 result",
                           "Mixed consistent XOR systems must fall back to native Kissat",
                           "Independent arithmetic certificates validate GF2 UNSAT only",
                           "No independent CDCL UNSAT certificates from fallback Kissat",
                           "Synthetic distribution cannot establish universal SAT advantage"])
    (root/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    (root/"cnf.sha256").write_text("".join(f"{c['sha256']}  {c['name']}\n" for c in cases))
    print("R28_FROZEN",len(cases),digest(root/"manifest.json"),flush=True)

def load_clauses(path):
    n=0;declared=None;clause=[];clauses=[]
    with open(path) as f:
        for line in f:
            s=line.strip()
            if not s or s.startswith(("c","%")):continue
            if s.startswith("p "):
                _,kind,ns,ms=s.split()
                check(kind=="cnf","Header")
                n=int(ns);declared=int(ms);continue
            for word in s.split():
                v=int(word)
                if v==0:
                    clauses.append(tuple(clause));clause=[]
                else:clause.append(v)
    check(declared==len(clauses) and not clause and n>0,"DIMACS parse mismatch")
    return n,clauses

def check_sat_model(output,n,clauses):
    model={}
    for line in output.splitlines():
        if not line.startswith("v "):continue
        for word in line.split()[1:]:
            v=int(word)
            if v: model[abs(v)]=v>0
    if len(model)<n:return False
    return all(any(model.get(abs(v))==(v>0) for v in clause) for clause in clauses)

def check_gf2_unsat_proof(output,clauses):
    # Independent of native C++ parity matcher and its row elimination.
    statements={}
    certificate=None
    for line in output.splitlines():
        if line.startswith("c R28_EQ "):
            match=re.fullmatch(r"c R28_EQ id=(\d+) rhs=([01]) vars=([0-9,]+)",line)
            if not match:return False
            index=int(match.group(1));rhs=int(match.group(2))
            vs=tuple(int(s) for s in match.group(3).split(","))
            if not 2<=len(vs)<=6 or sorted(set(vs))!=list(vs):return False
            statements[index]=(vs,rhs)
        if line.startswith("c R28_UNSAT_CERT ids="):
            if certificate is not None:return False
            certificate=[int(x) for x in line.split("ids=",1)[1].split(",")]
    if not statements or not certificate or len(set(certificate))!=len(certificate):
        return False
    normalized={tuple(sorted(c,key=abs)) for c in clauses}
    for vs,rhs in statements.values():
        k=len(vs)
        for mask in range(1<<k):
            if (mask.bit_count()&1)!=rhs:
                cl=tuple(-v if (mask>>i)&1 else v for i,v in enumerate(vs))
                if cl not in normalized:return False
    variables=set();parity=0
    for idx in certificate:
        if idx not in statements:return False
        vs,rhs=statements[idx]
        parity^=rhs
        for v in vs:
            if v in variables:variables.remove(v)
            else:variables.add(v)
    return not variables and parity==1

def solve(binary,path,baseline,mode,cap,expected,clauses,n):
    cmd=[str(baseline),str(path)] if mode=="Kissat_pin" else [str(binary),str(path),str(baseline)]
    t0=time.monotonic()
    try:
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                         text=True,errors="replace",timeout=cap)
        elapsed=time.monotonic()-t0
        output=p.stdout
        if p.returncode not in (10,20):
            raise RuntimeError(f"Non-SAT exit {mode} code={p.returncode} {p.stderr[-250:]}")
        status="SAT" if p.returncode==10 else "UNSAT"
        check(not expected or expected==status,"Known parity label mismatch")
        route="upstream"
        if mode=="R28_exact_gf2":
            mark=next((l for l in output.splitlines() if l.startswith("c R28_ROUTE ")),"")
            check(bool(mark),"Missing R28 routing log")
            route=mark.split()[2]
        if status=="SAT":
            check(check_sat_model(output,n,clauses),"Invalid SAT assignment")
            proof="SAT_witness"
        elif route=="certified_xor_contradiction":
            check(check_gf2_unsat_proof(output,clauses),"Invalid parity UNSAT certificate")
            proof="GF2_independently_verified"
        else:
            proof="UNSAT_by_native_solver_only"
    except subprocess.TimeoutExpired:
        elapsed=time.monotonic()-t0
        status="TIMEOUT"
        route="timeout"
        proof="not_applicable"
    return {"status":status,"seconds":round(elapsed,6),
            "PAR2":round(elapsed,6) if status!="TIMEOUT" else 2*cap,
            "route":route,"proof":proof}

def cpu_affinity():
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})

def measure(a):
    spec=json.loads((Path(a.inputs)/"manifest.json").read_text())
    check(spec["protocol"]==PROTO and spec["modes"]==list(MODES)
          and spec["cap_s"]==CAP and spec["repeats"]==REPS,"Protocol mismatch")
    check(0<=a.shard<SHARDS,"Shard")
    cpu_affinity()
    root=Path(a.inputs);out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    binary=Path(a.binary).resolve();base=Path(a.kissat).resolve()
    check(binary.is_file() and base.is_file(),"Missing solver")
    case_list=spec["cases"][a.shard::SHARDS]
    md={"shard":a.shard,"manifest_sha256":digest(root/"manifest.json"),
        "r28_sha256":digest(binary),"kissat_sha256":digest(base),
        "cases":len(case_list),"cpu":next((l for l in Path("/proc/cpuinfo").read_text().splitlines()
              if l.startswith("model name")),"unknown")}
    (out/"metadata.json").write_text(json.dumps(md,indent=2)+"\n")
    rows=[]
    for case in case_list:
        path=(root/case["name"]).resolve()
        check(digest(path)==case["sha256"],"Formula SHA changed")
        n,clauses=load_clauses(path)
        for rep in range(REPS):
            order=list(MODES)
            random.Random(int(digest(f"r28/order/{case['sha256']}/{rep}".encode()),16)).shuffle(order)
            for mode in order:
                result=solve(binary,path,base,mode,CAP,case["expected"],clauses,n)
                row={"formula":case["name"],"family":case["family"],
                     "repeat":rep,"mode":mode,**result}
                rows.append(row)
                (out/"rows.json").write_text(json.dumps(rows,indent=1)+"\n")
                print("R28_TRIAL",a.shard,case["name"],rep,mode,result["status"],
                      result["seconds"],result["route"],result["proof"],flush=True)
        answers={r["status"] for r in rows if r["formula"]==case["name"]} - {"TIMEOUT"}
        check(len(answers)<=1,"SAT/UNSAT disagreement")
    print("R28_SHARD_COMPLETE",a.shard,len(rows),flush=True)

def known(a):
    # Source-reconstructed R27 input, examined in earlier research; not blind.
    import r27_universal_fresh_benchmark as old
    out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    inputs=out/"r27_replayed"
    old.freeze(inputs)
    target=inputs/"tseitin_xor_64_10.cnf"
    n,clauses=load_clauses(target)
    cpu_affinity()
    binary=Path(a.binary).resolve();base=Path(a.kissat).resolve()
    result={}
    for mode in MODES:
        vals=[]
        for rep in range(3):
            x=solve(binary,target,base,mode,4.0,"UNSAT",clauses,n)
            vals.append(x)
            print("R28_KNOWN_REPLAY",mode,rep,x["status"],x["seconds"],x["route"],x["proof"],flush=True)
        result[mode]=vals
    (out/"known_replay.json").write_text(json.dumps(result,indent=2)+"\n")
    print("R28_KNOWN_PASS",digest(target),flush=True)

def aggregate(a):
    root=Path(a.inputs); spec=json.loads((root/"manifest.json").read_text())
    expected_sha=digest(root/"manifest.json")
    whole=[];binaries=set();upstreams=set()
    for shard in range(SHARDS):
        folder=Path(a.combined)/f"r28-shard-{shard}"/"results"
        md=json.loads((folder/"metadata.json").read_text())
        check(md["shard"]==shard and md["manifest_sha256"]==expected_sha,"SHA provenance")
        binaries.add(md["r28_sha256"]);upstreams.add(md["kissat_sha256"])
        rr=json.loads((folder/"rows.json").read_text())
        check(len(rr)==len(spec["cases"][shard::SHARDS])*REPS*len(MODES),"Missing attempts")
        whole.extend(rr)
    check(len(binaries)==1 and len(upstreams)==1,"Binary drift")
    check(len(whole)==240*REPS*len(MODES),"Expected 960 results")
    byname={v["name"]:v for v in spec["cases"]}
    summary={}
    for family in ("ALL",)+FAMILIES:
        subset=[c for c in spec["cases"] if family=="ALL" or c["family"]==family]
        group={}
        for mode in MODES:
            trials=[x for x in whole if x["mode"]==mode and
                    (family=="ALL" or x["family"]==family)]
            check(len(trials)==len(subset)*REPS,"Missing group trials")
            solved=sum(all(r["status"]!="TIMEOUT" for r in whole if
                           r["formula"]==c["name"] and r["mode"]==mode) for c in subset)
            group[mode]={"solved":solved,"total":len(subset),
                         "sum_PAR2":round(sum(x["PAR2"] for x in trials),6),
                         "timeouts":sum(x["status"]=="TIMEOUT" for x in trials),
                         "routes":dict(Counter(x["route"] for x in trials)),
                         "independent_gf2_proofs":sum(x["proof"]=="GF2_independently_verified" for x in trials)}
        b=group["Kissat_pin"]["sum_PAR2"]
        v=group["R28_exact_gf2"]["sum_PAR2"]
        group["R28_gain_pct"]=round(100*(b-v)/b,3)
        summary[family]=group
        print("R28_SUMMARY",family,json.dumps(group,sort_keys=True),flush=True)
    data={"protocol":PROTO,"manifest_sha256":expected_sha,
          "r28_binary_sha":list(binaries)[0],"kissat_binary_sha":list(upstreams)[0],
          "summary":summary,"rows":whole,
          "limitations":["Synthetic multi-family suite, not universal SAT theorem",
                         "Six synthetic families, no official industrial SAT inputs",
                         "Baseline Kissat commit pinned, not latest competition winner",
                         "Fallback UNSAT not independently certified in this run",
                         "Known replay held separate from 240 fresh inputs"]}
    Path(a.output).write_text(json.dumps(data,indent=2)+"\n")
    lines=["# DRNAS R28 — exact native GF(2) vs pinned clean Kissat",
           "240 new SHA-frozen formulas, 2 paired repeats × 2 modes = 960 executions.",
           "2s limit, PAR-2 timeout=4s. Lower is better. Known R27 replay is excluded.",
           "**Not a general NP/SAT proof or SAT Competition ranking.**","",
           "| Family | Kissat PAR2 sum(s) | R28 PAR2 sum(s) | R28 gain | R28 solved | GF2 UNSAT proofs |",
           "|---|---:|---:|---:|---:|---:|"]
    for family,g in summary.items():
        k,v=g["Kissat_pin"],g["R28_exact_gf2"]
        lines.append(f"| {family} | {k['sum_PAR2']:.4f} | {v['sum_PAR2']:.4f} | "
                     f"{g['R28_gain_pct']:+.2f}% | {v['solved']}/{v['total']} | "
                     f"{v['independent_gf2_proofs']} |")
    Path(a.report).write_text("\n".join(lines)+"\n")
    with Path(a.csv).open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(whole[0]))
        w.writeheader();w.writerows(whole)
    print("R28_AUDIT_PASS",len(whole),len(spec["cases"]),flush=True)

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="command",required=True)
    v=sub.add_parser("prepare");v.add_argument("--outdir",required=True)
    v=sub.add_parser("known")
    for n in ("binary","kissat","outdir"):v.add_argument("--"+n,required=True)
    v=sub.add_parser("measure")
    for n in ("inputs","binary","kissat","outdir"):v.add_argument("--"+n,required=True)
    v.add_argument("--shard",type=int,required=True)
    v=sub.add_parser("aggregate")
    for n in ("inputs","combined","output","report","csv"):v.add_argument("--"+n,required=True)
    a=p.parse_args()
    if a.command=="prepare":freeze(Path(a.outdir))
    elif a.command=="known":known(a)
    elif a.command=="measure":measure(a)
    else:aggregate(a)

if __name__=="__main__":main()
