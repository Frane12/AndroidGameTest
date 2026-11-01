#!/usr/bin/env python3
"""Frozen external public holdout; NOT an official SAT Competition benchmark.
12 NEW files (lexicographically third/fourth in each SAT/UNSAT x Easy/Moderate/Hard tier).
Repo pinned before this benchmark is run, no generator overlap with DRNAS development.
"""
import hashlib,json,random,statistics,subprocess,time
from pathlib import Path
from collections import defaultdict

SOURCE="Byt-wyze-technology/sat-instances-library"
REV="0a150d63fb86d0eb344d65c6b2cf94be24bbfd11"
INPUT=Path("/tmp/sat-external/instances")
OUT=Path("v1410-public-holdout-results")
OUT.mkdir(exist_ok=True)
CASES=[
 "sat-Easy-A-1477conflicts-longclauses.cnf",
 "sat-Easy-A-173conflicts-longclauses.cnf",
 "sat-Moderate-A-18415conflicts-longclauses.cnf",
 "sat-Moderate-A-19447conflicts-transition.cnf",
 "sat-Hard-B-88132conflicts-transition.cnf",
 "sat-Hard-B-88239conflicts-transition.cnf",
 "unsat-Easy-A-1301conflicts-toy.cnf",
 "unsat-Easy-A-1311conflicts-toy.cnf",
 "unsat-Moderate-A-15158conflicts-standard.cnf",
 "unsat-Moderate-A-16134conflicts-transition.cnf",
 "unsat-Hard-C-126197conflicts-transition.cnf",
 "unsat-Hard-C-137892conflicts-symbolic.cnf",
]
SOLVERS={"v142":Path("/tmp/v142_xor4"),"v147":Path("/tmp/v147_xor4"),
         "v148":Path("/tmp/v148_xor4"),"v149":Path("/tmp/v149_xor4"),"v1410":Path("/tmp/v1410_xor4"),
         "kissat":Path("/tmp/kissat_solver")}
TIMEOUT=3
REPETITIONS=3

def parse_cnf(path):
    clauses=[];pending=[];n=0;m=0
    for line in path.read_text(errors="replace").splitlines():
        line=line.strip()
        if not line or line.startswith(("c","%")):continue
        if line.startswith("p"):
            words=line.split()
            if len(words)>=4 and words[1]=="cnf":
                n,m=int(words[2]),int(words[3])
            continue
        for raw in line.split():
            if raw=="%":break
            x=int(raw)
            if x==0:
                clauses.append(pending)
                pending=[]
            else: pending.append(x)
    if n<1 or len(clauses)!=m or pending:raise RuntimeError(f"Invalid DIMACS: {path.name}")
    return n,clauses

def extract_status(stdout):
    payload=None
    for line in stdout.splitlines():
        if line.startswith("DRNAS_HYBRID_RESULT\t"):
            try:payload=json.loads(line.split("\t",1)[1])
            except json.JSONDecodeError:pass
    if payload:return payload.get("status","UNKNOWN"),payload
    if "s UNSATISFIABLE" in stdout:return "UNSAT",None
    if "s SATISFIABLE" in stdout:return "SAT",None
    return "UNKNOWN",None

def check_sat_model(stdout,payload,n,clauses):
    literals=[]
    if payload and isinstance(payload.get("model"),list):
        literals=payload["model"]
    else:
        for line in stdout.splitlines():
            if line.startswith("v "):
                literals += [int(x) for x in line.split()[1:] if x!="0"]
    model={}
    for lit in literals:
        if not isinstance(lit,int) or lit==0 or abs(lit)>n:return False
        v=abs(lit)
        if v in model and model[v]!=(lit>0):return False
        model[v]=(lit>0)
    return bool(model) and all(any(model.get(abs(lit))==(lit>0) for lit in cl) for cl in clauses)

def run_solver(name,exe,case,kissat):
    cmd=[str(exe.resolve()),str(case["anonymous"]),str(kissat.resolve()),"1"]
    if name=="kissat":cmd=cmd[:2]
    start=time.perf_counter()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=TIMEOUT)
        seconds=time.perf_counter()-start
        status,payload=extract_status(p.stdout)
        proof_path=payload.get("path","unknown") if payload else "kissat"
        model_ok=(check_sat_model(p.stdout,payload,case["vars"],case["clauses"])
                  if status=="SAT" else None)
        wrong=(status in ("SAT","UNSAT") and
                (status!=case["expected"] or model_ok is False))
        return {"seconds":seconds,"status":status,"exit_code":p.returncode,
                "path":proof_path,"sat_witness_checked":model_ok,
                "wrong":wrong}
    except subprocess.TimeoutExpired:
        return {"seconds":TIMEOUT,"status":"TIMEOUT","exit_code":-1,
                "path":"timeout","sat_witness_checked":None,"wrong":False}

def main():
    for name,path in SOLVERS.items():
        if not path.exists():raise RuntimeError(f"Missing binary: {name}")
    cases=[]
    for idx,name in enumerate(CASES):
        p=INPUT/name
        data=p.read_bytes()
        n,clauses=parse_cnf(p)
        anon=OUT/f"instance_{idx:02d}.cnf"
        anon.write_bytes(data)
        cases.append({"anonymous":anon,"source_name":name,"vars":n,
             "clauses":clauses,"sha256":hashlib.sha256(data).hexdigest(),
             "expected":"UNSAT" if name.startswith("unsat-") else "SAT",
             "tier":name.split("-")[1]})
    rng=random.Random(14920261101)
    results=[]
    for case in cases:
        r=defaultdict(list)
        for _ in range(REPETITIONS):
            names=list(SOLVERS)
            rng.shuffle(names)
            for name in names:
                r[name].append(run_solver(name,SOLVERS[name],case,SOLVERS["kissat"]))
        for name,reps in r.items():
            results.append({"case":case["anonymous"].name,"expected":case["expected"],
                "tier":case["tier"],"solver":name,"reps":reps,
                "median_seconds":statistics.median(v["seconds"] for v in reps),
                "all_correct":all(v["status"]==case["expected"] and
                                  v["sat_witness_checked"] is not False for v in reps)})
    summary={}
    for name in SOLVERS:
        sub=[x for x in results if x["solver"]==name]
        summary[name]={"solved":sum(x["all_correct"] for x in sub),
            "cases":len(sub),
            "median_seconds":statistics.median(x["median_seconds"] for x in sub),
            "sum_case_medians_seconds":sum(x["median_seconds"] for x in sub),
            "par2_seconds":sum(x["median_seconds"] if x["all_correct"] else 2*TIMEOUT
                                 for x in sub)}
    meta=[{"anonymous":c["anonymous"].name,"source":c["source_name"],
           "expected":c["expected"],"sha256":c["sha256"],
           "variables":c["vars"],"clauses":len(c["clauses"])} for c in cases]
    (OUT/"results.json").write_text(json.dumps({"source":SOURCE,"source_commit":REV,
         "timeout_seconds":TIMEOUT,"repetitions":REPETITIONS,
         "cases":meta,"summary":summary,"results":results},indent=2))
    lines=["# V14.10 Stratified external public holdout",
       "Independent *second* 12-instance public library split, NOT SAT Competition official.",
       "Three repetitions, random solver order, 3-s per-run timeout.",
       "SAT models checked against CNF; UNSAT compared against file label and Kissat, NOT DRAT proof verified.",
       "","| Solver | Solved | Median (s) | Sum medians (s) | PAR-2 (s) |",
       "|---|---:|---:|---:|---:|"]
    for name,s in summary.items():
        lines.append(f"| {name} | {s['solved']}/{s['cases']} | {s['median_seconds']:.6f} | {s['sum_case_medians_seconds']:.6f} | {s['par2_seconds']:.6f} |")
    (OUT/"results.md").write_text("\n".join(lines)+"\n")
    print("\n".join(lines))
    if any(v["wrong"] for x in results for v in x["reps"]):
        raise RuntimeError("Wrong SAT/UNSAT or invalid SAT witness: see results.json")

if __name__=="__main__":main()
