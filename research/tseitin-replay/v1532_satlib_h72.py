#!/usr/bin/env python3
"""Frozen independent SATLIB holdout H from a DIFFERENT source repository.
72 real SATLIB cases: 48 uf/uuf/flat and 24 AIM SAT/UNSAT.
Selected before any V15.3 results. Not an official competition ranking.
Only non-semantic SATLIB trailing % / 0 markers are stripped.
"""
import hashlib,json,random,statistics,subprocess,time
from pathlib import Path
from collections import defaultdict,Counter
from v151_proof_checker import verify_certificate as check_v151
from v153_proof_checker import verify_certificate as check_v153
SOURCE="mitchellh/go-sat"
REV="fc0e735aff48989326f256121b5ed6fc585858c3"
ROOT=Path("/tmp/satlib-repo/testdata/satlib")
OUT=Path("v1532-satlib-h-72")
OUT.mkdir(exist_ok=True)
CASES=[]
# Frozen BEFORE any V15.3.2 runtime: different IDs than SATLIB F (13-20) and G (21-32).
for number in range(33,49):
    CASES.append((f"sat-uniform-20-91/uf20-0{number}.cnf","SAT","uniform20"))
    CASES.append((f"sat-flat125-301/flat125-{number}.cnf","SAT","graph_coloring"))
    CASES.append((f"unsat-uniform-50-218/uuf50-0{number}.cnf","UNSAT","uniform50"))
# New AIM 100 1_6 and 2_0 plus AIM 200 2_0, not G's 200 1_6/3_4/6_0.
for size,density in ((100,"1_6"),(100,"2_0"),(200,"2_0")):
    for number in range(1,5):
        CASES.append((f"file-dimacs-aim/aim-{size}-{density}-yes1-{number}.cnf",
                      "SAT","aim_sat"))
        CASES.append((f"file-dimacs-aim/aim-{size}-{density}-no-{number}.cnf",
                      "UNSAT","aim_unsat"))
SOLVERS={"v1531":Path("/tmp/v1531_nohang"),"v1532":Path("/tmp/v1532_prefix"),"kissat":Path("/tmp/kissat_solver")}
REPS=5
TIMEOUT=6

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
            if name in ("v1531","v1532"):proof_ok=check_v153(payload,case["clauses"])
            
        if name=="v1531" and "DRNAS_V153_ROUTE\tkissat_augmented" in p.stdout:
            route="kissat_augmented"
        elif name=="v1532" and "DRNAS_V1532_ROUTE\\tprefix_kissat_direct" in p.stdout:
            route="prefix_kissat_direct"
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
    cases=[];manifest=[];rejected=[]
    for i,(rel,expected,family) in enumerate(CASES):
        src=ROOT/rel
        try:
            raw,clean,n,clauses,trailer=normalize_satlib(src)
        except (ValueError,OSError) as err:
            rejected.append({"source":rel,"expected":expected,"reason":str(err)})
            continue
        dst=OUT/f"case_{i:02d}.cnf"
        dst.write_bytes(clean)
        cases.append({"file":dst,"family":family,"expected":expected,"n":n,"clauses":clauses})
        manifest.append({"id":dst.name,"source":rel,"expected":expected,
            "sha256_source":hashlib.sha256(raw).hexdigest(),
            "sha256_normalized":hashlib.sha256(clean).hexdigest(),
            "trailing_satlib_marker_removed":trailer,"n":n,"clauses":len(clauses)})
    if len(cases)!=72:raise RuntimeError(f'Expected 72 valid cases, got {len(cases)}')
    rng=random.Random(153120261105)
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
        "benchmark":"SATLIB external holdout H (new IDs vs F/G); not official",
        "timeout_seconds":TIMEOUT,"repetitions":REPS,
        "manifest":manifest,"rejected_invalid_input":rejected,
        "summary":summary,"results":results},indent=2))
    rows=["# V15.3.2 prefix gate vs V15.3.1 on SATLIB H (72 fresh IDs)",
          f"72 new frozen candidates, {len(cases)} valid, {len(rejected)} excluded as malformed; 5 repeats.",
          "Original source SHA-256, normalized hashes and suffix markers documented in JSON.",
          "6 s per attempt, PAR-2; native UNSAT independently checked, SAT models clause-validated.",
          "NOT official SAT Competition ranking.","",
          "| Solver | Solved | Median (s) | Sum medians (s) | PAR-2 |",
          "|---|---:|---:|---:|---:|"]
    for name,s in summary.items():
        rows.append(f"| {name} | {s['solved']}/{s['cases']} | {s['median_seconds']:.6f} | {s['sum_medians']:.6f} | {s['par2']:.6f} |")
    (OUT/"results.md").write_text("\n".join(rows)+"\n")
    print("\n".join(rows))
    for r in rejected:print("REJECTED_INVALID_INPUT",r["source"],r["reason"])
    for name,s in summary.items():print("ROUTES",name,json.dumps(s["routes"],sort_keys=True))
    if any(x["status"] in ("SAT","UNSAT") and not x["correct"]
           for row in results for x in row["runs"]):
        raise RuntimeError("Incorrect SAT/UNSAT or invalid proof/model; inspect results.json")
if __name__=="__main__":main()
