#!/usr/bin/env python3
"""V15.3 frozen synthetic cross-structure challenge (96 fresh cases).
Eight XOR widths 3..10, 12 randomized SAT/UNSAT each, repeated 3 times.
This is a constructed test of the new mathematical mechanism, NOT independent
SAT Competition evidence.
"""
import json,random,statistics,subprocess,time
from pathlib import Path
from collections import Counter,defaultdict
from v153_proof_checker import verify_certificate
OUT=Path("v1532-mixed-96")
OUT.mkdir(exist_ok=True)
SOLVERS={"v1531":Path("/tmp/v1531_nohang"),"v1532":Path("/tmp/v1532_prefix"),"kissat":Path("/tmp/kissat_solver")}
WIDTHS=list(range(3,11))
REPEATS=3
TIMEOUT=4
def xorclauses(vs,rhs,rng):
    result=[]
    for mask in range(1<<len(vs)):
        if mask.bit_count()%2==rhs:continue
        cl=[-v if mask>>j&1 else v for j,v in enumerate(vs)]
        rng.shuffle(cl)
        result.append(cl)
    return result
def make(width,index):
    rng=random.Random(1531110100+width*10000+index)
    unsat=bool(index%2)
    n=max(2*width+8,32)
    vs=rng.sample(range(1,n+1),width+1)
    shared=vs[:-2]
    d,e=vs[-2:]
    p=rng.randrange(2)
    q=rng.randrange(2)
    x=rng.randrange(2)
    # x XOR e = p XOR q when x is the d value.
    y=x^p^q
    if unsat:y^=1
    eq1=shared+[d]
    eq2=shared+[e]
    clauses=xorclauses(eq1,p,rng)+xorclauses(eq2,q,rng)
    clauses+=[[d if x else -d],[e if y else -e]]
    # Include duplicate clauses and other signed 3-CNF distractors.
    clauses.append(clauses[rng.randrange(len(clauses))][:])
    model={d:x,e:y}
    for _ in range(24):
        other=rng.sample([v for v in range(1,n+1) if v not in (d,e)],2)
        # SAT distractors are guaranteed true by the chosen unit on d/e.
        anchor=rng.choice((d,e))
        lit=anchor if model[anchor] else -anchor
        cl=[lit,rng.choice((-1,1))*other[0],rng.choice((-1,1))*other[1]]
        rng.shuffle(cl)
        clauses.append(cl)
    remap=list(range(1,n+1));rng.shuffle(remap)
    clauses=[[(1 if v>0 else -1)*remap[abs(v)-1] for v in cl]
             for cl in clauses]
    for cl in clauses:rng.shuffle(cl)
    rng.shuffle(clauses)
    expect="UNSAT" if unsat else "SAT"
    path=OUT/f"cross_w{width}_case{index:02d}.cnf"
    path.write_text(f"p cnf {n} {len(clauses)}\n"+
                    "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
    return {"file":path,"clauses":clauses,"n":n,"expected":expect,
            "width":width}
def sat_witness(stdout,payload,case):
    model=payload.get("model",[]) if payload else []
    if not model:
        for line in stdout.splitlines():
            if line.startswith("v "):
                model.extend(int(x) for x in line.split()[1:] if x!="0")
    values={}
    for lit in model:
        if not isinstance(lit,int) or lit==0 or abs(lit)>case["n"]:return False
        if abs(lit) in values and values[abs(lit)]!=(lit>0):return False
        values[abs(lit)]=(lit>0)
    return bool(values) and all(any(values.get(abs(x))==(x>0)
                for x in cl) for cl in case["clauses"])
def solve(name,exe,case):
    cmd=[str(exe.resolve()),str(case["file"]),str(SOLVERS["kissat"].resolve()),"1"]
    if name=="kissat":cmd=cmd[:2]
    start=time.perf_counter()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=TIMEOUT)
        seconds=time.perf_counter()-start
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
        if "DRNAS_V153_ROUTE\tkissat_augmented" in p.stdout:route="kissat_augmented"
        model_ok=sat_witness(p.stdout,payload,case) if status=="SAT" else None
        proof_ok=(verify_certificate(payload,case["clauses"]) if
                  status=="UNSAT" and name in ("v1531","v1532") else None)
        return {"seconds":seconds,"status":status,
                "correct":status==case["expected"] and
                  model_ok is not False and proof_ok is not False,
                "route":route,"model_ok":model_ok,"proof_ok":proof_ok,
                "exit_code":p.returncode}
    except subprocess.TimeoutExpired:
        return {"seconds":TIMEOUT,"status":"TIMEOUT","correct":False,
                "route":"timeout","model_ok":None,"proof_ok":None,"exit_code":-1}
def main():
    for name,path in SOLVERS.items():
        if not path.exists():raise RuntimeError(f"Missing solver {name}")
    cases=[make(w,i) for w in WIDTHS for i in range(12)]
    rng=random.Random(15301101)
    results=[]
    for case in cases:
        rounds=defaultdict(list)
        for _ in range(REPEATS):
            names=list(SOLVERS);rng.shuffle(names)
            for name in names:
                rounds[name].append(solve(name,SOLVERS[name],case))
        for name,runs in rounds.items():
            results.append({"case":case["file"].name,"width":case["width"],
                "expected":case["expected"],"solver":name,"runs":runs,
                "median":statistics.median(x["seconds"] for x in runs),
                "correct":all(x["correct"] for x in runs)})
    summary={}
    for width in ["ALL"]+WIDTHS:
        summary[str(width)]={}
        for name in SOLVERS:
            sub=[x for x in results if x["solver"]==name and
                 (width=="ALL" or x["width"]==width)]
            summary[str(width)][name]={"solved":sum(x["correct"] for x in sub),
                "total":len(sub),"sum_case_medians":sum(x["median"] for x in sub),
                "median":statistics.median(x["median"] for x in sub),
                "routes":dict(Counter(y["route"] for x in sub for y in x["runs"]))}
    (OUT/"results.json").write_text(json.dumps({"summary":summary,
        "results":results,"repetitions":REPEATS,"timeout":TIMEOUT},indent=2))
    lines=["# V15.3.2 prefix vs V15.3.1 mixed XOR+unit structural challenge (96 constructed cases)",
           "3 repeats, widths 3..10, shuffled solver order. NOT official/blind.",
           "Native V15.3 UNSAT proof independently checked on original CNF.",
           "","| XOR width | Solver | Solved | Median (s) | Sum case medians (s) |",
           "|---|---|---:|---:|---:|"]
    for width,group in summary.items():
        for name,z in group.items():
            lines.append(f"| {width} | {name} | {z['solved']}/{z['total']} | {z['median']:.6f} | {z['sum_case_medians']:.6f} |")
    (OUT/"results.md").write_text("\n".join(lines)+"\n")
    print("\n".join(lines))
    for name,z in summary["ALL"].items():
        print("ROUTES",name,json.dumps(z["routes"],sort_keys=True))
    for row in results:
        if not row["correct"]:
            raise RuntimeError("A solver missed/incorrectly solved "+row["case"]+" "+row["solver"])
if __name__=="__main__":main()
