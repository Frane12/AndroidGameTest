#!/usr/bin/env python3
"""V15.0 broad structural regression.
Deterministic *development* data for checking SAT/UNSAT, models and timing.
8 independent construction families, 12 SAT/UNSAT instances each.
This is not a blind test or an official SAT competition evaluation.
"""
import json,random,statistics,subprocess,time
from pathlib import Path
from collections import defaultdict
from v150_proof_checker import verify_certificate
OUT=Path("v150-broad-regression");OUT.mkdir(exist_ok=True)
SOLVERS={"v148":Path("/tmp/v148_xor4"),"v1410":Path("/tmp/v1410_xor4"),
         "v150":Path("/tmp/v150_broad"),"kissat":Path("/tmp/kissat_solver")}
FAMILIES=["xor5","xor6","xor7","xor8","2sat","unit_chain","pigeonhole","graph_color"]
REPS=3
TIMEOUT=3
def exact_xor(vs,rhs,rng):
    result=[]
    for mask in range(1<<len(vs)):
        if mask.bit_count()%2==rhs:continue
        cl=[-v if mask>>i&1 else v for i,v in enumerate(vs)]
        rng.shuffle(cl);result.append(cl)
    rng.shuffle(result)
    return result

def formula(family,index):
    rng=random.Random(150001+FAMILIES.index(family)*10000+index)
    unsat=index%2==1
    clauses=[]
    if family.startswith("xor"):
        width=int(family[-1]);n=max(16,width*2)
        vars_=rng.sample(range(1,n+1),width)
        planted=[rng.randrange(2) for _ in range(n+1)]
        rhs=sum(planted[v] for v in vars_)%2
        clauses+=exact_xor(vars_,rhs,rng)
        if unsat:clauses+=exact_xor(vars_,rhs^1,rng)
        # Add a second, independent XOR with overlapping variables.
        vars2=rng.sample(range(1,n+1),width)
        if not unsat:
            clauses+=exact_xor(vars2,sum(planted[v] for v in vars2)%2,rng)
    elif family=="2sat":
        n=26
        for i in range(1,n):
            clauses.append([-i,i+1])
            clauses.append([i,-(i+1)])
        if unsat:
            # No units; the binary implication graph forces x1 and not x1.
            clauses.extend([[1,2],[-1,2],[1,-2],[-1,-2]])
        else:
            clauses.extend([[1,2],[-1,2]])
    elif family=="unit_chain":
        n=40
        clauses.append([1])
        for v in range(1,n):clauses.append([-v,v+1])
        clauses.append([-n] if unsat else [n])
        # A satisfied unrelated residual clause.
        clauses.append([n,1,2])
    elif family=="pigeonhole":
        holes=4;birds=5 if unsat else 4
        n=birds*holes
        def v(b,h):return b*holes+h+1
        for b in range(birds):
            clauses.append([v(b,h) for h in range(holes)])
        for h in range(holes):
            for a in range(birds):
                for b in range(a+1,birds):
                    clauses.append([-v(a,h),-v(b,h)])
    elif family=="graph_color":
        colors=2 if unsat else 3
        vertices=7 if unsat else 6
        n=vertices*colors
        def v(node,color):return node*colors+color+1
        for node in range(vertices):
            clauses.append([v(node,c) for c in range(colors)])
            for c in range(colors):
                for d in range(c+1,colors):
                    clauses.append([-v(node,c),-v(node,d)])
        edges=[(i,i+1) for i in range(vertices-1)]
        if unsat:edges.append((vertices-1,0))
        for a,b in edges:
            for c in range(colors):
                clauses.append([-v(a,c),-v(b,c)])
    else:raise ValueError(family)
    # Renumber variables and shuffle all clause/literal orders.
    perm=list(range(1,n+1));rng.shuffle(perm)
    def rename(x):return (1 if x>0 else -1)*perm[abs(x)-1]
    clauses=[[rename(lit) for lit in cl] for cl in clauses]
    for cl in clauses:rng.shuffle(cl)
    rng.shuffle(clauses)
    expected="UNSAT" if unsat else "SAT"
    p=OUT/f"{family}_{index:02d}_{expected.lower()}.cnf"
    p.write_text(f"p cnf {n} {len(clauses)}\n"+
                 "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
    return {"name":p.name,"path":p,"n":n,"clauses":clauses,
            "expected":expected,"family":family}

def sat_witness_ok(out,payload,case):
    model=[]
    if payload and isinstance(payload.get("model"),list):
        model=payload["model"]
    else:
        for line in out.splitlines():
            if line.startswith("v "):
                model.extend(int(x) for x in line.split()[1:] if x!="0")
    assign={}
    for v in model:
        if not isinstance(v,int) or v==0 or abs(v)>case["n"]:return False
        if abs(v) in assign and assign[abs(v)]!=(v>0):return False
        assign[abs(v)]=(v>0)
    return bool(assign) and all(any(assign.get(abs(v))==(v>0) for v in cl)
                                for cl in case["clauses"])

def solve(name,exe,case):
    cmd=[str(exe.resolve()),str(case["path"]),str(SOLVERS["kissat"].resolve()),"1"]
    if name=="kissat":cmd=cmd[:2]
    t=time.perf_counter()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=TIMEOUT)
        secs=time.perf_counter()-t
        payload=None
        for line in p.stdout.splitlines():
            if line.startswith("DRNAS_HYBRID_RESULT\t"):
                try:payload=json.loads(line.split("\t",1)[1])
                except json.JSONDecodeError:pass
        if payload is not None:status=payload.get("status","UNKNOWN")
        elif "s UNSATISFIABLE" in p.stdout:status="UNSAT"
        elif "s SATISFIABLE" in p.stdout:status="SAT"
        else:status="UNKNOWN"
        valid=(sat_witness_ok(p.stdout,payload,case) if status=="SAT" else None)
        proof_ok=(verify_certificate(payload,case["clauses"])
                  if name=="v150" and status=="UNSAT" else None)
        return {"seconds":secs,"status":status,
                "correct":status==case["expected"] and valid is not False and proof_ok is not False,
                "witness_ok":valid,"proof_ok":proof_ok,"path":payload.get("path") if payload else "kissat",
                "exit_code":p.returncode}
    except subprocess.TimeoutExpired:
        return {"seconds":TIMEOUT,"status":"TIMEOUT","correct":False,
                "witness_ok":None,"path":"timeout","exit_code":-1}

def main():
    for n,p in SOLVERS.items():
        if not p.is_file():raise RuntimeError("Missing "+n)
    cases=[formula(family,i) for family in FAMILIES for i in range(12)]
    results=[];rng=random.Random(151500)
    for case in cases:
        collected=defaultdict(list)
        for _ in range(REPS):
            names=list(SOLVERS);rng.shuffle(names)
            for name in names:
                collected[name].append(solve(name,SOLVERS[name],case))
        for name,reps in collected.items():
            results.append({"case":case["name"],"family":case["family"],
                "expected":case["expected"],"solver":name,"runs":reps,
                "correct":all(r["correct"] for r in reps),
                "median_seconds":statistics.median(r["seconds"] for r in reps)})
    summary={}
    for family in ["ALL"]+FAMILIES:
        summary[family]={}
        for name in SOLVERS:
            rr=[r for r in results if r["solver"]==name and
                (family=="ALL" or family==r["family"])]
            summary[family][name]={"correct":sum(r["correct"] for r in rr),
                "total":len(rr),"sum_medians":sum(r["median_seconds"] for r in rr),
                "median":statistics.median(r["median_seconds"] for r in rr)}
    (OUT/"results.json").write_text(json.dumps({"summary":summary,"results":results},indent=2))
    lines=["# DRNAS V15.0 broad structural regression (96 development cases)",
        "All runs on same runner; 3 reps, shuffled solver order; NOT a blind suite.",
        "","| Family | Solver | Correct | Median (s) | Sum medians (s) |",
        "|---|---|---:|---:|---:|"]
    for family,sg in summary.items():
        for name,s in sg.items():
            lines.append(f"| {family} | {name} | {s['correct']}/{s['total']} | {s['median']:.6f} | {s['sum_medians']:.6f} |")
    (OUT/"results.md").write_text("\n".join(lines)+"\n")
    print("\n".join(lines))
    if any(r["status"] in ("SAT","UNSAT") and not r["correct"]
           for row in results for r in row["runs"]):
        raise RuntimeError("Incorrect SAT/UNSAT or invalid witness")
    if any(not row["correct"] for row in results):
        raise RuntimeError("Timeouts or incomplete results; inspect results.json")
if __name__=="__main__":main()
