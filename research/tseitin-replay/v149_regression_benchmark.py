#!/usr/bin/env python3
"""V14.9 Selective regression: reused 72 development cases, 6 families, three repetitions.
Reused V14.8 development suite, NOT blind/official validation.
"""
import json, random, statistics, subprocess, time
from collections import defaultdict
from pathlib import Path

OUT=Path("v149-regression-results")
OUT.mkdir(exist_ok=True)
SOLVERS={"v142":Path("/tmp/v142_xor4"),"v147":Path("/tmp/v147_xor4"),
         "v148":Path("/tmp/v148_xor4"),"v149":Path("/tmp/v149_xor4"),"kissat":Path("/tmp/kissat_solver")}
FAMILIES=("exhaustive","cycle","partial","xor2","planted3","cycle_large")
REPEATS=3

def xor_clauses(vs,rhs,rng,partial=False):
    masks=[m for m in range(1<<len(vs)) if m.bit_count()%2 != rhs]
    if partial: masks=masks[:max(1,len(masks)//2)]
    clauses=[]
    for mask in masks:
        lits=[-v if mask>>i&1 else v for i,v in enumerate(vs)]
        rng.shuffle(lits)
        clauses.append(lits)
    if clauses and rng.random()<0.6: clauses.append(clauses[0][:])
    return clauses

def make(family,i):
    rng=random.Random(1488000 + FAMILIES.index(family)*1000 + i)
    unsat=bool(i%2)
    n=96 if family=="cycle_large" else 40 if family=="planted3" else 32 if family=="xor2" else 24
    model=[0]+[rng.randrange(2) for _ in range(n)]
    clauses=[]
    if family=="exhaustive":
        blocks=[(1,2,3,4),(4,5,6,7),(7,8,9,10),(10,11,12,13),
                (13,14,15,16),(16,17,18,19),(19,20,21,22),(22,23,24,1)]
        for vs in blocks:
            rhs=sum(model[v] for v in vs)%2
            clauses+=xor_clauses(vs,rhs,rng)
        if unsat:
            rhs=sum(model[v] for v in blocks[0])%2
            clauses+=xor_clauses(blocks[0],rhs^1,rng)
    elif family in ("cycle","partial","cycle_large"):
        # A xor B = C for each triple: contradictory third RHS gives
        # global UNSAT without a locally exhausted truth table.
        groups=16 if family=="cycle_large" else 4
        for g in range(groups):
            a,b,c,d,e,f=range(6*g+1,6*g+7)
            rows=((a,b,c,d),(c,d,e,f),(a,b,e,f))
            for j,vs in enumerate(rows):
                rhs=sum(model[v] for v in vs)%2
                if unsat and g==0 and j==2: rhs^=1
                partial=(family=="partial" and g!=0 and j!=0)
                clauses+=xor_clauses(vs,rhs,rng,partial=partial)
    elif family=="xor2":
        for j in range(1,n+1):
            k=j+1 if j<n else 1
            rhs=model[j]^model[k]
            if unsat and j==n:rhs^=1
            clauses+=xor_clauses((j,k),rhs,rng)
    elif family=="planted3":
        for _ in range(160):
            vs=rng.sample(range(1,n+1),3)
            while True:
                ls=[v if rng.randrange(2) else -v for v in vs]
                if any((v>0)==bool(model[abs(v)]) for v in ls):break
            clauses.append(ls)
        if unsat:clauses.extend(([1],[-1]))
    # Variable relabeling and clause reordering prevent fixed positional cues.
    remap=list(range(n+1))
    shuffled=list(range(1,n+1));rng.shuffle(shuffled)
    remap[1:]=shuffled
    clauses=[[remap[abs(v)]*(1 if v>0 else -1) for v in cl] for cl in clauses]
    rng.shuffle(clauses)
    expected="UNSAT" if unsat else "SAT"
    path=OUT/f"{family}_{i:02d}_{expected.lower()}.cnf"
    path.write_text(f"p cnf {n} {len(clauses)}\n"+
                    "".join(" ".join(map(str,cl))+" 0\n" for cl in clauses))
    return {"path":path,"family":family,"expected":expected,"clauses":clauses}

def verify_exhaustive(payload,clauses):
    support=tuple(sorted(payload.get("support",[])))
    if not support or len(support)>4:return False
    seen=set()
    for cl in clauses:
        if len(cl)!=len(support) or tuple(sorted(map(abs,cl)))!=support:continue
        mask=sum(1<<j for j,v in enumerate(support) if -v in cl)
        seen.add(mask)
    return len(seen)==(1<<len(support))

def run(exe,case,kissat):
    cmd=[str(exe.resolve()),str(case["path"]),str(kissat.resolve()),"1"]
    if exe.resolve()==kissat.resolve():cmd=cmd[:2]
    start=time.perf_counter()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=4)
        elapsed=time.perf_counter()-start
        output=p.stdout
        payload=None
        for line in output.splitlines():
            if line.startswith("DRNAS_HYBRID_RESULT\t"):
                try:payload=json.loads(line.split("\t",1)[1])
                except json.JSONDecodeError:pass
        if payload is not None:status=payload.get("status","UNKNOWN")
        elif "s UNSATISFIABLE" in output:status="UNSAT"
        elif "s SATISFIABLE" in output:status="SAT"
        else:status="UNKNOWN"
        certified=True
        if payload and payload.get("path")=="v148_exhaustive_support":
            certified=verify_exhaustive(payload,case["clauses"])
        if payload and status=="SAT":
            model=payload.get("model",[])
            assignment={abs(v):v>0 for v in model}
            certified=len(assignment)>=max(abs(v) for cl in case["clauses"] for v in cl)
            if certified:
                certified=all(any(assignment.get(abs(v))==(v>0) for v in cl) for cl in case["clauses"])
        return {"seconds":elapsed,"status":status,"exit":p.returncode,
                "path":payload.get("path") if payload else "kissat",
                "correct":status==case["expected"] and certified}
    except subprocess.TimeoutExpired:
        return {"seconds":4.0,"status":"TIMEOUT","exit":-1,
                "path":"timeout","correct":False}

def main():
    for name,p in SOLVERS.items():
        if not p.is_file():raise RuntimeError(f"Missing {name}: {p}")
    cases=[make(family,i) for family in FAMILIES for i in range(12)]
    rng=random.Random(1488900)
    results=[]
    for case in cases:
        measurements=defaultdict(list)
        for _ in range(REPEATS):
            names=list(SOLVERS);rng.shuffle(names)
            for name in names:
                measurements[name].append(run(SOLVERS[name],case,SOLVERS["kissat"]))
        for name in SOLVERS:
            reps=measurements[name]
            results.append({"case":case["path"].name,"family":case["family"],
                 "expected":case["expected"],"solver":name,"reps":reps,
                 "median_seconds":statistics.median(x["seconds"] for x in reps),
                 "correct":all(x["correct"] for x in reps)})
    stats={}
    for family in ("ALL",)+FAMILIES:
        stats[family]={}
        for name in SOLVERS:
            subset=[x for x in results if x["solver"]==name and
                    (family=="ALL" or x["family"]==family)]
            stats[family][name]={"correct":sum(x["correct"] for x in subset),
                "total":len(subset),
                "median_seconds":statistics.median(x["median_seconds"] for x in subset),
                "sum_medians_seconds":sum(x["median_seconds"] for x in subset)}
    (OUT/"results.json").write_text(json.dumps({"stats":stats,"results":results},indent=2))
    lines=["# DRNAS V14.9 Selective regression: 72 reused development regression cases",
        "Same runner, 3 repeats, includes process startup; NOT blind independent validation.","",
        "| Family | Solver | Correct | Median (s) | Sum case medians (s) |",
        "|---|---|---:|---:|---:|"]
    for family,ss in stats.items():
        for name,s in ss.items():
            lines.append(f"| {family} | {name} | {s['correct']}/{s['total']} | {s['median_seconds']:.6f} | {s['sum_medians_seconds']:.6f} |")
    (OUT/"results.md").write_text("\n".join(lines)+"\n")
    print("\n".join(lines))
    if any(not r["correct"] for r in results):
        raise RuntimeError("An incorrect/timeout result occurred; inspect results.json")

if __name__=="__main__":main()
