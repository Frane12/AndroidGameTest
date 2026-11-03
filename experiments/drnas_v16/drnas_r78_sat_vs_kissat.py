#!/usr/bin/env python3
"""DRNAS R78: SAME frozen TSP-derived SAT CNF, one-core solver study.

Competing methods all run real pinned Kissat binary; one with no source
intervention, and two with DRNAS R55/R61 certificates and input rewrites.
R55/R61 do NOT claim to replace Kissat's core algorithm; their incremental
cost, added clause count, SAT witness checks, and real elapsed wall time are
charged. NEW R78 deterministic seed, no tuned formula selection, 8 opt/opt-1
CNFs for n=8,10,12,14, 2 reps, 15s cap. This is not the official SAT comp.
"""
from __future__ import annotations
import argparse,hashlib,itertools,json,os,random
from pathlib import Path
import drnas_r72_tsp_sat as tsp
import r61_killer_transfer as core

PROTO="DRNAS-R78-EXACT-SAT-IDENTICAL-CNF-20261104-v1"
SEED=7811042026
COUNTS=(8,10,12,14)
MODES=("clean","r55_fixed18","r61_pair18")
CAP=15.0;REPS=2;SHARDS=4

def ck(ok,msg):
    if not ok:raise RuntimeError("R78_FAIL_CLOSED "+str(msg))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def freeze(folder):
    root=Path(folder);root.mkdir(parents=True,exist_ok=True)
    old=tsp.SEED
    tsp.SEED=SEED
    try:
        cases=[]
        for n in COUNTS:
            xy,d=tsp.graph(n)
            optimum,tour=tsp.held_karp(d)
            for outcome,bound in (("SAT",optimum),("UNSAT",optimum-1)):
                cnf=tsp.encode(d,bound)
                fname=f"r78_n{n}_{outcome.lower()}.cnf"
                p=root/fname
                cnf.save(p)
                c=dict(name=fname,n=n,expect=outcome,bound=bound,
                       optimum=optimum,coords=xy,distances=d,
                       canonical_tour=tour,variables=cnf.vars,
                       clauses=len(cnf.rows),sha256=sha(p))
                cases.append(c)
                print("R78_FROZEN",fname,"vars",c["variables"],
                     "clauses",c["clauses"],"expect",outcome,flush=True)
    finally:tsp.SEED=old
    ck(len(cases)==8 and len({c["sha256"] for c in cases})==8,
       "duplicate or missing cases")
    manifest=dict(protocol=PROTO,seed=SEED,cases=cases,
      modes=list(MODES),cap_s=CAP,repeats=REPS,shards=SHARDS,
      limitations=[
        "Same original CNF for all modes, but candidate DRNAS modes may add independently certified derived clauses",
        "DRNAS policies wrap the SAME pinned Kissat; this is not a new independent SAT core",
        "Preprocessing/certificate and SAT witness verification counted in wall time",
        "SAT witnesses verified on original CNFs; UNSAT exact statuses cross-checked with Held-Karp",
        "Four sizes, 8 deterministic synthetic TSP CNFs, two repeats; NOT official SAT 2026 and NOT broad generalization",
        "R78 seed differs from R72; no per-formula performance tuning, but R55/R61 policies pre-existing",
        "Single CPU affinity for all modes; timeout=15s, PAR2=30s"
      ])
    (root/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    (root/"sources.sha256").write_text("".join(c["sha256"]+"  "+c["name"]+"\n" for c in cases))
    print("R78_FREEZE_PASS",sha(root/"manifest.json"),flush=True)

def selftest():
    # Check independent Held-Karp vs small brute-force optimal costs and CNF ranges.
    old=tsp.SEED;tsp.SEED=SEED
    try:
        for n in (5,6,7):
            _,d=tsp.graph(n)
            best,_=tsp.held_karp(d)
            brute=min(sum(d[a][b] for a,b in zip((0,)+perm,perm+(0,)))
                      for perm in itertools.permutations(range(1,n)))
            ck(best==brute,"bad HeldKarp exact n="+str(n))
    finally:tsp.SEED=old
    print("R78_HELD_KARP_BRUTEFORCE_SELFTEST_PASS",flush=True)

def measure(a):
    root=Path(a.sources);m=json.loads((root/"manifest.json").read_text())
    ck(m["protocol"]==PROTO and len(m["cases"])==8
       and m["modes"]==list(MODES) and m["cap_s"]==CAP,
       "invalid freeze config")
    ck(0<=a.shard<SHARDS,"shard")
    kb=Path(a.kissat).resolve()
    ck(kb.is_file(),"missing pinned Kissat")
    core.CAP=CAP
    base=os.sched_getaffinity(0);cpu=min(base)
    os.sched_setaffinity(0,{cpu})
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    (out/"meta.json").write_text(json.dumps(
       dict(protocol=PROTO,shard=a.shard,
            manifest_sha=sha(root/"manifest.json"),
            kissat_binary_sha=sha(kb),cpu=cpu),indent=2)+"\n")
    rows=[]
    try:
        for case in m["cases"][a.shard::SHARDS]:
            p=root/case["name"]
            ck(sha(p)==case["sha256"],"source drift")
            ck(tsp.held_karp(case["distances"])[0]==case["optimum"],
               "bad exact TSP metadata")
            for rep in range(REPS):
                modes=list(MODES)
                random.Random(int(hashlib.sha256(
                    (case["sha256"]+str(rep)+PROTO).encode()).hexdigest(),16)).shuffle(modes)
                for mode in modes:
                    result=core.ordinary_trial(p,kb,kb,mode,cpu)
                    ck(result["status"] in (case["expect"],"TIMEOUT"),
                       "SAT/UNSAT conflict with HeldKarp")
                    # R61 wrapper PAR2 is hardcoded to 40s protocol, so recompute.
                    result["par2_s"]=round(CAP*2 if result["status"]=="TIMEOUT"
                                          else result["wall_s"],6)
                    row=dict(case=case["name"],source_sha=case["sha256"],
                             repeat=rep,mode=mode,**result)
                    rows.append(row)
                    (out/"rows.json").write_text(json.dumps(rows,indent=2)+"\n")
                    print("R78_TRIAL",case["name"],rep,mode,
                      result["status"],"wall",result["wall_s"],
                      "added_verified",result["added"],flush=True)
    finally:os.sched_setaffinity(0,base)
    ck(len(rows)==len(m["cases"][a.shard::SHARDS])*REPS*len(MODES),
       "incomplete measurements")

def audit(a):
    root=Path(a.sources);m=json.loads((root/"manifest.json").read_text())
    ck(m["protocol"]==PROTO and len(m["cases"])==8,"manifest")
    seen=set();rows=[];binaries=set()
    for shard in range(SHARDS):
        fold=Path(a.combined)/f"r78-shard-{shard}"/"results"
        meta=json.loads((fold/"meta.json").read_text())
        ck(meta["shard"]==shard and meta["protocol"]==PROTO and
           meta["manifest_sha"]==sha(root/"manifest.json"),"mixed source")
        binaries.add(meta["kissat_binary_sha"])
        part=json.loads((fold/"rows.json").read_text())
        ck(len(part)==len(m["cases"][shard::SHARDS])*REPS*len(MODES),
           "shard not complete")
        for row in part:
            key=(row["case"],row["repeat"],row["mode"])
            ck(key not in seen,"duplicate");seen.add(key)
            case=next(x for x in m["cases"] if x["name"]==row["case"])
            ck(row["source_sha"]==case["sha256"] and
               row["mode"] in MODES and
               row["status"] in (case["expect"],"TIMEOUT"),
               "inconsistent result")
        rows.extend(part)
    ck(len(binaries)==1 and len(rows)==8*REPS*len(MODES),
       "mixed binaries or incomplete runs")
    summary={}
    for mode in MODES:
        zz=[x for x in rows if x["mode"]==mode]
        summary[mode]=dict(attempts=len(zz),
          solved=sum(x["status"]!="TIMEOUT" for x in zz),
          total_PAR2_s=round(sum(x["par2_s"] for x in zz),6),
          total_wall_s=round(sum(x["wall_s"] for x in zz),6),
          added_clause_trials=sum(x["added"]>0 for x in zz),
          added_clauses=sum(x["added"] for x in zz))
    final=dict(protocol=PROTO,binary_sha=next(iter(binaries)),
               summary=summary,rows=rows,limitations=m["limitations"])
    Path(a.json).write_text(json.dumps(final,indent=2)+"\n")
    lines=["# R78 same-CNF one-core: unmodified Kissat vs R55/R61 certified clause interventions",
           "New independent deterministic seed, exact optimum TSP SAT/UNSAT threshold cases.",
           "All methods share Kissat binary and original CNFs; full preprocessing counted.",
           "| Method | Correct solves | Sum PAR2 (s) | Sum wall (s) | Trials adding clauses |",
           "|---|---:|---:|---:|---:|"]
    for mode in MODES:
        z=summary[mode]
        lines.append(f"| {mode} | {z['solved']}/{z['attempts']} | "+
                     f"{z['total_PAR2_s']:.4f} | {z['total_wall_s']:.4f} | {z['added_clause_trials']} |")
    lines+=["","| Cities | Expected | Repeat | Clean Kissat (s) | R55 (s) | R61 (s) |",
             "|---:|---|---:|---|---|---|"]
    for c in m["cases"]:
        for rep in range(REPS):
            def val(mode):
                v=next(z for z in rows if z["case"]==c["name"] and z["repeat"]==rep and z["mode"]==mode)
                return "TIMEOUT" if v["status"]=="TIMEOUT" else f"{v['wall_s']:.5f}"
            lines.append(f"| {c['n']} | {c['expect']} | {rep} | "+
                 " | ".join(val(mode) for mode in MODES)+" |")
    lines+=["","## Limitations"]+["- "+x for x in m["limitations"]]
    Path(a.md).write_text("\n".join(lines)+"\n")
    print("R78_FINAL_AUDIT_PASS",json.dumps(summary,sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="action",required=True)
    sub.add_parser("selftest")
    x=sub.add_parser("freeze");x.add_argument("--out",required=True)
    x=sub.add_parser("measure")
    for name in ("sources","kissat","out"):x.add_argument("--"+name,required=True)
    x.add_argument("--shard",required=True,type=int)
    x=sub.add_parser("audit")
    for name in ("sources","combined","json","md"):x.add_argument("--"+name,required=True)
    a=p.parse_args()
    {"selftest":lambda:selftest(),"freeze":lambda:freeze(a.out),
     "measure":lambda:measure(a),"audit":lambda:audit(a)}[a.action]()
if __name__=="__main__":main()
