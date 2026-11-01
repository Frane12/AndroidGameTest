#!/usr/bin/env python3
"""Frozen independent SATLIB holdout E from a DIFFERENT source repository.
48 real SATLIB cases, 6 families (3 SAT and 3 UNSAT), 8 per family.
Selected before any V15.2 results. Not an official competition ranking.
Only non-semantic SATLIB trailing % / 0 markers are stripped.
"""
import hashlib,json,random,statistics,subprocess,time
from pathlib import Path
from collections import defaultdict,Counter
from v151_proof_checker import verify_certificate as check_v151
from v152_proof_checker import verify_certificate as check_v152
SOURCE="mitchellh/go-sat"
REV="fc0e735aff48989326f256121b5ed6fc585858c3"
ROOT=Path("/tmp/satlib-repo/testdata/satlib")
OUT=Path("v152-satlib-external-holdout-e")
OUT.mkdir(exist_ok=True)
CASES=[]
for number in range(5,13):
    CASES.append((f"sat-uniform-20-91/uf20-{number:02d}.cnf","SAT","uniform20"))
    CASES.append((f"sat-flat125-301/flat125-{number}.cnf","SAT","graph_coloring"))
    CASES.append((f"unsat-uniform-50-218/uuf50-{number:02d}.cnf","UNSAT","uniform50"))
for size in list(range(24,31))+[100]:
    CASES.append((f"unsat-dimacs-dubois/dubois{size}.cnf","UNSAT","dubois"))
for size in (100,200):
    for number in range(1,5):
        CASES.append((f"file-dimacs-aim/aim-{size}-2_0-yes1-{number}.cnf","SAT","aim_sat"))
        CASES.append((f"file-dimacs-aim/aim-{size}-2_0-no-{number}.cnf","UNSAT","aim_unsat"))
SOLVERS={"v148":Path("/tmp/v148_xor4"),
         "v151":Path("/tmp/v151_expanded"),
         "v152":Path("/tmp/v152_hall_xor"),
         "kissat":Path("/tmp/kissat_solver")}
REPS=3
TIMEOUT=2

def normalize_satlib(path):
    raw=path.read_bytes()
    n=m=0
    header=0
    clauses=[];pending=[]
    trailer=False
    for line0 in raw.decode("utf-8").splitlines():
        line=line0.strip()
        if not line or line.startswith("c"):continue
        if line.startswith("%"):
            trailer=True;continue
        if trailer:
            # Several historical SATLIB files put an extra zero after the
            # terminating %. It is NOT a CNF clause. Reject any other tail.
            if line!="0":raise ValueError(f"Unexpected SATLIB tail in {path.name}: {line[:30]}")
            continue
        if line.startswith("p "):
            header+=1
            words=line.split()
            if header!=1 or len(words)!=4 or words[1]!="cnf":
                raise ValueError("Multiple/invalid DIMACS headers "+path.name)
            n,m=int(words[2]),int(words[3])
            if n<1 or m<0:raise ValueError("Invalid header counts")
            continue
        if header!=1:raise ValueError("Clause before header "+path.name)
        for token in line.split():
            value=int(token)
            if abs(value)>n:raise ValueError("Literal outside DIMACS variables")
            if value==0:
                clauses.append(pending)
                pending=[]
                if len(clauses)>m:raise ValueError("Excess clause count")
            else:pending.append(value)
    if header!=1 or pending or len(clauses)!=m:
        raise ValueError(f"Incorrect CNF clauses {len(clauses)}/{m}: {path.name}")
    clean=f"p cnf {n} {m}\n"+"".join(" ".join(map(str,cl))+" 0\n" for cl in clauses)
    return raw,clean.encode(),n,clauses,trailer

def parse_response(stdout):
    payload=None
    for line in stdout.splitlines():
        if line.startswith("DRNAS_HYBRID_RESULT\t"):
            try:payload=json.loads(line.split("\t",1)[1])
            except json.JSONDecodeError:pass
    if payload:return payload.get("status","UNKNOWN"),payload
    if "s UNSATISFIABLE" in stdout:return "UNSAT",None
    if "s SATISFIABLE" in stdout:return "SAT",None
    return "UNKNOWN",None

def witness_valid(stdout,payload,case):
    model=[]
    if payload and isinstance(payload.get("model"),list):model=payload["model"]
    else:
        for line in stdout.splitlines():
            if line.startswith("v "):
                model.extend(int(x) for x in line.split()[1:] if x!="0")
    assignment={}
    for lit in model:
        if not isinstance(lit,int) or not 1<=abs(lit)<=case["n"]:return False
        if abs(lit) in assignment and assignment[abs(lit)]!=(lit>0):return False
        assignment[abs(lit)]=(lit>0)
    return bool(assignment) and all(any(assignment.get(abs(lit))==(lit>0)
        for lit in cl) for cl in case["clauses"])

def run(name,exe,case):
    cmd=[str(exe.resolve()),str(case["file"]),str(SOLVERS["kissat"].resolve()),"1"]
    if name=="kissat":cmd=cmd[:2]
    start=time.perf_counter()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=TIMEOUT)
        t=time.perf_counter()-start
        status,payload=parse_response(p.stdout)
        model_ok=witness_valid(p.stdout,payload,case) if status=="SAT" else None
        proof_ok=None
        if status=="UNSAT":
            if name=="v152":proof_ok=check_v152(payload,case["clauses"])
            if name=="v151":proof_ok=check_v151(payload,case["clauses"])
        if name=="v152" and "DRNAS_V152_ROUTE\tkissat_augmented" in p.stdout:
            route="kissat_augmented"
        else:route=payload.get("path") if payload else "kissat"
        correct=(status==case["expected"] and model_ok is not False and
                 proof_ok is not False)
        return {"status":status,"seconds":t,"correct":correct,"model_valid":model_ok,
                "proof_valid":proof_ok,"route":route,
                "exit":p.returncode}
    except subprocess.TimeoutExpired:
        return {"status":"TIMEOUT","seconds":TIMEOUT,"correct":False,
                "model_valid":None,"proof_valid":None,"route":"timeout","exit":-1}
def main():
    for name,p in SOLVERS.items():
        if not p.is_file():raise RuntimeError(f"Missing native solver {name}")
    cases=[];manifest=[]
    for i,(rel,expected,family) in enumerate(CASES):
        src=ROOT/rel
        raw,clean,n,clauses,trailer=normalize_satlib(src)
        dst=OUT/f"case_{i:02d}.cnf"
        dst.write_bytes(clean)
        cases.append({"file":dst,"family":family,"expected":expected,"n":n,"clauses":clauses})
        manifest.append({"id":dst.name,"source":rel,"expected":expected,
            "sha256_source":hashlib.sha256(raw).hexdigest(),
            "sha256_normalized":hashlib.sha256(clean).hexdigest(),
            "trailing_satlib_marker_removed":trailer,"n":n,"clauses":len(clauses)})
    rng=random.Random(152120261101)
    results=[]
    for case in cases:
        rr=defaultdict(list)
        for _ in range(REPS):
            names=list(SOLVERS);rng.shuffle(names)
            for name in names:rr[name].append(run(name,SOLVERS[name],case))
        for name,reps in rr.items():
            results.append({"case":case["file"].name,"family":case["family"],
                "expected":case["expected"],"solver":name,
                "correct":all(x["correct"] for x in reps),
                "median_seconds":statistics.median(x["seconds"] for x in reps),
                "runs":reps})
    summary={}
    for name in SOLVERS:
        rr=[x for x in results if x["solver"]==name]
        routes=Counter(r["route"] for x in rr for r in x["runs"])
        summary[name]={"solved":sum(x["correct"] for x in rr),"cases":len(rr),
          "sum_medians":sum(x["median_seconds"] for x in rr),
          "median_seconds":statistics.median(x["median_seconds"] for x in rr),
          "par2":sum(x["median_seconds"] if x["correct"] else 2*TIMEOUT for x in rr),
          "routes":dict(routes)}
    (OUT/"results.json").write_text(json.dumps({"source":SOURCE,"revision":REV,
        "benchmark":"SATLIB public external holdout E; not an official competition",
        "timeout_seconds":TIMEOUT,"repetitions":REPS,
        "manifest":manifest,"summary":summary,"results":results},indent=2))
    rows=["# V15.2 expanded on independent SATLIB public holdout E",
          "48 fixed SATLIB instances, 6 distinct families, same runner, 3 repeats.",
          "Original source SHA-256, normalized hashes and suffix markers documented in JSON.",
          "2 s per attempt, PAR-2; native UNSAT independently checked, SAT models clause-validated.",
          "NOT official SAT Competition ranking.","",
          "| Solver | Solved | Median (s) | Sum medians (s) | PAR-2 |",
          "|---|---:|---:|---:|---:|"]
    for name,s in summary.items():
        rows.append(f"| {name} | {s['solved']}/{s['cases']} | {s['median_seconds']:.6f} | {s['sum_medians']:.6f} | {s['par2']:.6f} |")
    (OUT/"results.md").write_text("\n".join(rows)+"\n")
    print("\n".join(rows))
    for name,s in summary.items():print("ROUTES",name,json.dumps(s["routes"],sort_keys=True))
    if any(x["status"] in ("SAT","UNSAT") and not x["correct"]
           for row in results for x in row["runs"]):
        raise RuntimeError("Incorrect SAT/UNSAT or invalid proof/model; inspect results.json")
if __name__=="__main__":main()
