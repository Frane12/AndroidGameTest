#!/usr/bin/env python3
"""V15.2 broad structural dev regression, NOT a blind/official competition.
168 deterministically generated cases (14 families x 12), 5 repeats, 4 solvers.
Every SAT witness checked against ORIGINAL CNF, every DRNAS V15.2 UNSAT
certificate independently replayed from ORIGINAL clauses.
"""
import json,random,statistics,subprocess,time,sys
from pathlib import Path
from collections import Counter,defaultdict
from v152_proof_checker import verify_certificate

OUT=Path("v152-structural-dev")
OUT.mkdir(exist_ok=True)
SOLVERS={"v148":Path("/tmp/v148_xor4"),
         "v151":Path("/tmp/v151_expanded"),
         "v152":Path("/tmp/v152_hall_xor"),
         "kissat":Path("/tmp/kissat_solver")}
FAMILIES=[
    "hall_dense","hall_sparse","hall_residual","mixed_xor4","mixed_xor6",
    "equiv_xor3","equiv_binary","xor10","xor8","2sat","unit_chain",
    "php_general","graph_color","planted3"
]
REPEATS=5
TIMEOUT=3
def xorclauses(vs,rhs,rng):
    result=[]
    for mask in range(1<<len(vs)):
        if mask.bit_count()%2 == rhs:continue
        cl=[(-v if mask>>i&1 else v) for i,v in enumerate(vs)]
        rng.shuffle(cl);result.append(cl)
    return result
def build_hall(rng,unsat,variant):
    # First 5 birds have 4 possible resources on UNSAT instances
    # (Hall deficit 5>4), 5 resources on SAT instances. Other 3
    # birds have disjoint resources {5,6,7}, giving full matching.
    birds=8;holes=8
    if variant=="sparse":
        domains=[list(range(3 if unsat else 4)) for _ in range(4)]
        domains += [list(range(4,7)) for _ in range(3)]
        birds=7;holes=7
    else:
        domains=[list(range(4 if unsat else 5)) for _ in range(5)]
        domains += [list(range(5,8)) for _ in range(3)]
    varmap={}
    for b,domain in enumerate(domains):
        for h in domain:varmap[(b,h)]=len(varmap)+1
    n=len(varmap);clauses=[]
    for b,domain in enumerate(domains):
        clauses.append([varmap[(b,h)] for h in domain])
    for h in range(holes):
        attending=[b for b in range(birds) if h in domains[b]]
        for i,b1 in enumerate(attending):
            for b2 in attending[i+1:]:
                clauses.append([-varmap[(b1,h)],-varmap[(b2,h)]])
    if variant=="residual":
        # Add mixed-sign 3-SAT clauses compatible with a fixed injection.
        chosen={}
        if not unsat:
            for b in range(birds):
                h=b if b<5 else b
                assert h in domains[b]
                chosen[b]=h
        assignment={v:(not unsat and chosen.get(b)==h)
                    for (b,h),v in varmap.items()}
        for _ in range(25):
            vs=rng.sample(list(range(1,n+1)),3)
            signs=[rng.choice([-1,1]) for _ in range(3)]
            if all(x>0 for x in signs):signs[0]=-1
            literals=[v*signs[j] for j,v in enumerate(vs)]
            if not unsat and not any(assignment[abs(l)]==(l>0) for l in literals):
                literals[0]=abs(literals[0]) if assignment[abs(literals[0])] else -abs(literals[0])
            clauses.append(literals)
    return n,clauses
def build_mixed_xor(rng,unsat,width):
    n=width+10
    shared=list(range(1,width))
    a=width;b=width+1
    row1=shared+[a]
    row2=shared+[b]
    rhs=rng.randrange(2)
    parity_diff=0  # implied a == b
    clauses=xorclauses(row1,rhs,rng)+xorclauses(row2,rhs^parity_diff,rng)
    # Forces mixed XOR + residual CNF interaction.
    clauses.extend([[a],[-b]] if unsat else [[a],[b]])
    # Extra residual clauses guaranteed true when a==b==1.
    if not unsat:
        for _ in range(12):
            cl=rng.sample(range(width+2,n+1),3)
            cl.append(a)
            rng.shuffle(cl)
            clauses.append(cl)
    return n,clauses
def build_equiv_xor(rng,unsat):
    n=15
    clauses=[]
    for v in range(1,7):
        clauses.extend([[-v,v+1],[v,-(v+1)]])
    clauses+=xorclauses([1,7,8],0,rng)
    clauses+=xorclauses([6,7,8],1 if unsat else 0,rng)
    return n,clauses
def build_equiv_binary(rng,unsat):
    n=22;clauses=[]
    for v in range(1,16):
        clauses.extend([[-v,v+1],[v,-(v+1)]])
    # Force a shared variable through a 3-CNF gadget.
    clauses.extend([[1,17,18],[-16,19,20]])
    if unsat:
        # Two disjoint XOR3 equations with opposite parity and
        # end-variable equivalence; normal 2-SAT alone cannot prove it.
        clauses+=xorclauses([1,21,22],0,rng)
        clauses+=xorclauses([16,21,22],1,rng)
    else:
        clauses+=xorclauses([1,21,22],0,rng)
        clauses+=xorclauses([16,21,22],0,rng)
    return n,clauses
def build_reference(rng,unsat,family):
    clauses=[]
    if family in ("xor8","xor10"):
        w=int(family[3:]);n=w+6
        vars_=list(range(1,w+1))
        rhs=rng.randrange(2)
        clauses=xorclauses(vars_,rhs,rng)
        if unsat:clauses+=xorclauses(vars_,rhs^1,rng)
    elif family=="2sat":
        n=30
        for v in range(1,n):
            clauses.extend([[-v,v+1],[v,-(v+1)]])
        if unsat:clauses.extend([[1,2],[-1,2],[1,-2],[-1,-2]])
        else:clauses.extend([[1,2],[-1,2]])
    elif family=="unit_chain":
        n=40
        clauses=[[1]]+[[-v,v+1] for v in range(1,n)]
        clauses.append([-n] if unsat else [n])
    elif family=="php_general":
        H=5;B=7 if unsat else 5;n=H*B
        def v(b,h):return b*H+h+1
        for b in range(B):clauses.append([v(b,h) for h in range(H)])
        for h in range(H):
            for a in range(B):
                for b in range(a+1,B):clauses.append([-v(a,h),-v(b,h)])
    elif family=="graph_color":
        colors=2 if unsat else 3;V=7 if unsat else 6
        n=colors*V
        def v(u,col):return u*colors+col+1
        for u in range(V):
            clauses.append([v(u,c) for c in range(colors)])
            for c in range(colors):
                for d in range(c+1,colors):
                    clauses.append([-v(u,c),-v(u,d)])
        edges=[(i,i+1) for i in range(V-1)]
        if unsat:edges.append((V-1,0))
        for a,b in edges:
            for c in range(colors):clauses.append([-v(a,c),-v(b,c)])
    elif family=="planted3":
        n=40
        model=[0]+[rng.randrange(2) for _ in range(n)]
        for _ in range(120):
            vs=rng.sample(range(1,n+1),3)
            while True:
                lits=[v*rng.choice((-1,1)) for v in vs]
                if any((lit>0)==bool(model[abs(lit)]) for lit in lits):break
            clauses.append(lits)
        if unsat:
            clauses.extend([[1,2],[-1,2],[1,-2],[-1,-2]])
    else:raise RuntimeError("unknown "+family)
    return n,clauses
def formula(family,index):
    rng=random.Random(15220261101+FAMILIES.index(family)*1000+index)
    unsat=bool(index%2)
    if family.startswith("hall_"):
        n,clauses=build_hall(rng,unsat,family.removeprefix("hall_"))
    elif family.startswith("mixed_xor"):
        n,clauses=build_mixed_xor(rng,unsat,int(family.removeprefix("mixed_xor")))
    elif family=="equiv_xor3":n,clauses=build_equiv_xor(rng,unsat)
    elif family=="equiv_binary":n,clauses=build_equiv_binary(rng,unsat)
    else:n,clauses=build_reference(rng,unsat,family)
    # No filenames or positional patterns fed to any DRNAS classification.
    perm=list(range(1,n+1));rng.shuffle(perm)
    clauses=[[ (1 if x>0 else -1)*perm[abs(x)-1] for x in cl] for cl in clauses]
    for cl in clauses:rng.shuffle(cl)
    rng.shuffle(clauses)
    expected="UNSAT" if unsat else "SAT"
    p=OUT/f"case_{FAMILIES.index(family):02d}_{index:02d}.cnf"
    p.write_text(f"p cnf {n} {len(clauses)}\n"+
                 "".join(" ".join(map(str,cl))+" 0\n" for cl in clauses))
    return {"path":p,"family":family,"expected":expected,
            "n":n,"clauses":clauses}
def verify_sat(stdout,payload,case):
    model=[]
    if payload and isinstance(payload.get("model"),list):model=payload["model"]
    else:
        for line in stdout.splitlines():
            if line.startswith("v "):
                model += [int(x) for x in line.split()[1:] if x!="0"]
    assignment={}
    for lit in model:
        if not isinstance(lit,int) or lit==0 or abs(lit)>case["n"]:return False
        if abs(lit) in assignment and assignment[abs(lit)]!=(lit>0):return False
        assignment[abs(lit)]=lit>0
    return bool(assignment) and all(any(assignment.get(abs(lit))==(lit>0)
               for lit in cl) for cl in case["clauses"])
def run(name,exe,case):
    cmd=[str(exe.resolve()),str(case["path"]),str(SOLVERS["kissat"].resolve()),"1"]
    if name=="kissat":cmd=cmd[:2]
    t=time.perf_counter()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=TIMEOUT)
        seconds=time.perf_counter()-t
        payload=None
        for line in p.stdout.splitlines():
            if line.startswith("DRNAS_HYBRID_RESULT\t"):
                try:payload=json.loads(line.split("\t",1)[1])
                except json.JSONDecodeError:pass
        if payload:status=payload.get("status","UNKNOWN")
        elif "s UNSATISFIABLE" in p.stdout:status="UNSAT"
        elif "s SATISFIABLE" in p.stdout:status="SAT"
        else:status="UNKNOWN"
        route=payload.get("path") if payload else "kissat"
        if "DRNAS_V152_ROUTE\tkissat_augmented" in p.stdout:
            route="kissat_augmented"
        sat_ok=verify_sat(p.stdout,payload,case) if status=="SAT" else None
        proof_ok=(verify_certificate(payload,case["clauses"]) if
                  name=="v152" and status=="UNSAT" else None)
        correct=status==case["expected"] and sat_ok is not False and proof_ok is not False
        return {"seconds":seconds,"status":status,"correct":correct,
           "route":route,"sat_witness_ok":sat_ok,"native_proof_ok":proof_ok,
           "exit":p.returncode}
    except subprocess.TimeoutExpired:
        return {"seconds":TIMEOUT,"status":"TIMEOUT","correct":False,
                "route":"timeout","sat_witness_ok":None,"native_proof_ok":None,"exit":-1}
def main():
    for name,p in SOLVERS.items():
        if not p.exists():raise RuntimeError(f"Missing solver {name} {p}")
    cases=[formula(family,i) for family in FAMILIES for i in range(12)]
    rng=random.Random(15241121)
    results=[]
    for case in cases:
        measurements=defaultdict(list)
        for _ in range(REPEATS):
            order=list(SOLVERS);rng.shuffle(order)
            for name in order:
                measurements[name].append(run(name,SOLVERS[name],case))
        for name,reps in measurements.items():
            results.append({"case":case["path"].name,"family":case["family"],
                "expected":case["expected"],"solver":name,
                "reps":reps,"correct":all(x["correct"] for x in reps),
                "median_seconds":statistics.median(x["seconds"] for x in reps)})
    summary={}
    for family in ["ALL"]+FAMILIES:
        summary[family]={}
        for name in SOLVERS:
            rows=[x for x in results if x["solver"]==name and
                  (family=="ALL" or x["family"]==family)]
            summary[family][name]={
                "solved":sum(x["correct"] for x in rows),
                "cases":len(rows),
                "median_seconds":statistics.median(x["median_seconds"] for x in rows),
                "sum_case_medians":sum(x["median_seconds"] for x in rows),
                "routes":dict(Counter(y["route"] for row in rows for y in row["reps"]))
            }
    (OUT/"results.json").write_text(json.dumps({"summary":summary,"results":results,
            "reps":REPEATS,"seconds_cap":TIMEOUT},indent=2))
    lines=["# DRNAS V15.2 168 generated development instances (14 families)",
        "Five repetitions, randomized solver order, same runner. NOT blind.",
        "SAT model checked on original CNF, native V15.2 UNSAT proof replayed in Python.","",
        "| Family | Solver | Correct | Median s | Sum case medians s |",
        "|---|---|---:|---:|---:|"]
    for family,sg in summary.items():
        for name,stat in sg.items():
            lines.append(f"| {family} | {name} | {stat['solved']}/{stat['cases']} | {stat['median_seconds']:.6f} | {stat['sum_case_medians']:.6f} |")
    (OUT/"results.md").write_text("\n".join(lines)+"\n")
    print("\n".join(lines))
    for name,stat in summary["ALL"].items():
        print("ROUTES",name,json.dumps(stat["routes"],sort_keys=True))
    wrong=[(row["case"],row["solver"],x["route"],x["status"]) for row in results
           for x in row["reps"] if x["status"] in ("SAT","UNSAT") and not x["correct"]]
    if wrong:raise RuntimeError("Incorrect answer or invalid model/certificate: "+repr(wrong[:5]))
    if any(not x["correct"] for x in results):
        raise RuntimeError("Unsolved instances or timeouts; inspect results.json")
if __name__=="__main__":main()
