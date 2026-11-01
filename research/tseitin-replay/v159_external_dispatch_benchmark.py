#!/usr/bin/env python3
"""DRNAS V15.9: reproducible external benchmark, no training/tuning.
Two suites:
 - dimacs: the original 1993 Rutgers DIMACS pigeonhole instances hole6..10,
   downloaded as UNIX compress .Z, each with native SAT/UNSAT provenance.
 - controls: third-party GENERATED SAT-style CNF from a pinned Git commit.
   These are not actual SATLIB archival problems and are NOT represented as such.
All SAT models verified against full source CNF, all native DRNAS V15.3
UNSAT certificates independently checked. UNSAT from Kissat remains a solver
claim, cross-checked against published source designation (not DRAT/LRAT).
Hard deadline, process wall times, 5 repeats; PAR-2 and timeout counts.
"""
import argparse,collections,hashlib,json,random,statistics,subprocess,time
from pathlib import Path
from v153_proof_checker import verify_certificate

REPS=5
TIMEOUT=12.0
SOLVERS={"kissat":Path("/tmp/kissat_solver"),
         "kissat_api":Path("/tmp/kissat_api_control"),
         "v1531":Path("/tmp/v1531_nohang"),
         "v154":Path("/tmp/v154_inprocess"),
         "v159":Path("/tmp/v159_relational_dispatch")}
DIMACS=["hole6","hole7","hole8","hole9","hole10"]
CONTROL_ROOT=Path("/tmp/independent-controls/LogicalOptimizer.Benchmarks/SatCorpus")
CONTROL=["uf075-01","uf080-01","uf090-01","uf095-01","uf100-01",
         "uf105-01","uf110-01","uf115-01","uf120-01","uf125-01",
         "uuf016-01","uuf016-02","uuf017-03","uuf017-04",
         "uuf018-05","uuf018-06"]
CONTROL_COMMIT="366bd1964be332de6d281d4e4099ae67c156d552"
ARCHIVE_ROOT="https://archive.dimacs.rutgers.edu/pub/challenge/sat/benchmarks/cnf/"
OUT_ROOT=Path("v159-external-synthesis-benchmark")

def parse_dimacs(path):
    text=path.read_text(errors="strict")
    n=nc=None;pending=[];clauses=[];head=0;terminated=False
    for line in text.splitlines():
        line=line.strip()
        if not line or line.startswith("c"):continue
        if line.startswith("%"):
            terminated=True
            continue
        if terminated:
            if line=="0":continue
            raise ValueError(f"Unexpected DIMACS trailer {path.name}")
        if line.startswith("p "):
            head+=1
            words=line.split()
            if head!=1 or len(words)!=4 or words[1]!="cnf":
                raise ValueError(f"Bad/multiple DIMACS header {path.name}")
            n,nc=int(words[2]),int(words[3])
            if n<=0 or nc<0 or n>200000 or nc>2000000:
                raise ValueError(f"Unsafe DIMACS dimensions {path.name}")
            continue
        if head!=1:raise ValueError("Missing header "+path.name)
        for token in line.split():
            lit=int(token)
            if abs(lit)>n:raise ValueError("Out-of-range literal")
            if lit:
                pending.append(lit)
                if len(pending)>100000:raise ValueError("Oversized clause")
            else:
                clauses.append(pending);pending=[]
                if len(clauses)>nc:raise ValueError("Too many clauses")
    if head!=1 or pending or len(clauses)!=nc:
        raise ValueError(f"Invalid header/actual clause count for {path.name} ({len(clauses)} vs {nc})")
    return n,clauses

def check_sat_model(stdout,payload,n,clauses):
    values=[]
    if payload and isinstance(payload.get("model"),list):
        values=payload["model"]
    else:
        for line in stdout.splitlines():
            if line.startswith("v "):
                values += [int(z) for z in line.split()[1:] if z!="0"]
    assign={}
    for lit in values:
        if not isinstance(lit,int) or not 1<=abs(lit)<=n:return False
        if abs(lit) in assign and assign[abs(lit)]!=(lit>0):return False
        assign[abs(lit)]=(lit>0)
    if not assign:return False
    return all(any(assign.get(abs(v))==(v>0) for v in cl)
               for cl in clauses)

def run_solver(name,case):
    exe=SOLVERS[name]
    cmd=[str(exe.resolve()),str(case["path"].resolve()),
         str(SOLVERS["kissat"].resolve()),"1"]
    if name in ("kissat","kissat_api"):cmd=cmd[:2]
    start=time.perf_counter()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return {"status":"TIMEOUT","seconds":TIMEOUT,"correct":False,
                "route":"timeout","witness_ok":None,"proof_ok":None,"exit":-1}
    seconds=time.perf_counter()-start
    payload=None
    for line in p.stdout.splitlines():
        if line.startswith("DRNAS_HYBRID_RESULT\t"):
            try:payload=json.loads(line.split("\t",1)[1])
            except json.JSONDecodeError:pass
    if payload:
        status=payload.get("status","UNKNOWN")
        route=payload.get("path","drnas_unknown")
    elif "s UNSATISFIABLE" in p.stdout:
        status="UNSAT";route="kissat_fallback" if name not in ("kissat","kissat_api") else name
    elif "s SATISFIABLE" in p.stdout:
        status="SAT";route="kissat_fallback" if name!="kissat" else "kissat"
    else:
        status="UNKNOWN";route="unknown"
    # Do not claim a SAT/UNSAT proof from a mere startup/return code.
    witness_ok=(check_sat_model(p.stdout,payload,case["n"],case["clauses"])
                if status=="SAT" else None)
    proof_ok=(verify_certificate(payload,case["clauses"])
              if status=="UNSAT" and name not in ("kissat","kissat_api") and payload else None)
    correct=(status==case["expected"] and witness_ok is not False and
             proof_ok is not False)
    return {"seconds":round(seconds,8),"status":status,"correct":correct,
            "route":route,"witness_ok":witness_ok,"proof_ok":proof_ok,
            "exit":p.returncode}

def download_dimacs(destination):
    destination.mkdir(parents=True,exist_ok=True)
    manifest=[]
    for filename in DIMACS:
        gz=destination/(filename+".cnf.Z")
        raw=destination/(filename+".cnf")
        url=ARCHIVE_ROOT+filename+".cnf.Z"
        # Fixed names from published archive. Never select based on performance.
        cmd=["curl","-fLsS","--connect-timeout","8","--max-time","35",
             "--retry","2",url,"-o",str(gz)]
        subprocess.run(cmd,check=True,timeout=45)
        with raw.open("wb") as output:
            subprocess.run(["gzip","-dc",str(gz)],check=True,stdout=output,timeout=15)
        manifest.append({"name":filename,"expected":"UNSAT","origin":url,
           "compressed_sha256":hashlib.sha256(gz.read_bytes()).hexdigest(),
           "input_sha256":hashlib.sha256(raw.read_bytes()).hexdigest(),
           "path":raw})
    return manifest

def prepare_control():
    if not CONTROL_ROOT.is_dir():raise RuntimeError("Pinned external controls checkout missing")
    manifest=[]
    for name in CONTROL:
        src=CONTROL_ROOT/(name+".cnf")
        manifest.append({"name":name,"expected":("UNSAT" if name.startswith("uuf") else "SAT"),
             "origin":f"AlexanderV/LogicalOptimizer@{CONTROL_COMMIT}/LogicalOptimizer.Benchmarks/SatCorpus/{name}.cnf",
             "input_sha256":hashlib.sha256(src.read_bytes()).hexdigest(),"path":src})
    return manifest

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--suite",choices=["dimacs","controls"],required=True)
    ap.add_argument("--timeout",type=float,default=12.0)
    args=ap.parse_args()
    global TIMEOUT
    TIMEOUT=args.timeout
    if not 0<TIMEOUT<=30:raise ValueError("Unsafe timeout")
    for name,path in SOLVERS.items():
        if not path.is_file():raise RuntimeError(f"Missing binary {name}: {path}")
    suite=args.suite
    out=OUT_ROOT/suite
    out.mkdir(parents=True,exist_ok=True)
    if suite=="dimacs":manifest=download_dimacs(out/"source")
    else:manifest=prepare_control()
    cases=[]
    for item in manifest:
        n,clauses=parse_dimacs(item["path"])
        item["n"]=n;item["clause_count"]=len(clauses)
        cases.append({**item,"clauses":clauses})
    export_manifest=[{k:v for k,v in case.items() if k not in ("clauses","path")}
                      for case in cases]
    (out/"sources.json").write_text(json.dumps(export_manifest,indent=2))
    # Fixed random order; no tuning or choice made from timings.
    rng=random.Random(153120261101 if suite=="dimacs" else 153120261102)
    results=[]
    for case in cases:
        recorded=collections.defaultdict(list)
        for rep in range(REPS):
            order=list(SOLVERS)
            rng.shuffle(order)
            for name in order:
                entry=run_solver(name,case)
                entry["repeat"]=rep
                recorded[name].append(entry)
        for name,runs in recorded.items():
            median=statistics.median(x["seconds"] for x in runs)
            solved=sum(x["correct"] for x in runs)
            results.append({"case":case["name"],"solver":name,"n":case["n"],
              "clauses":case["clause_count"],"expected":case["expected"],
              "runs":runs,"correct_repetitions":solved,
              "correct_all":solved==REPS,
              "median_seconds":median,
              "par2":median if solved==REPS else 2*TIMEOUT})
        print("CASE_COMPLETED",suite,case["name"],
              {name:round(statistics.median(x["seconds"] for x in runs),5)
               for name,runs in recorded.items()},flush=True)
    summary={}
    for name in SOLVERS:
        rows=[r for r in results if r["solver"]==name]
        routes=collections.Counter(x["route"] for row in rows for x in row["runs"])
        summary[name]={"solved":sum(r["correct_all"] for r in rows),
           "cases":len(rows),
           "sum_medians_seconds":round(sum(r["median_seconds"] for r in rows),8),
           "PAR2_seconds":round(sum(r["par2"] for r in rows),8),
           "timeouts":sum(x["status"]=="TIMEOUT" for row in rows for x in row["runs"]),
           "routes":dict(routes)}
    payload={"suite":suite,"source_type":("1993 DIMACS archival original" if
      suite=="dimacs" else "Third-party generated SAT-style, not original SATLIB"),
      "repeat_count":REPS,"per_attempt_timeout_seconds":TIMEOUT,
      "original_cnf_models_checked":True,"native_unsat_certificate_checker":"v153_proof_checker.py",
      "unsat_fallback_DRAT_checked":False,"manifest":export_manifest,
      "summary":summary,"results":results}
    (out/"results.json").write_text(json.dumps(payload,indent=2))
    lines=[f"# V15.9 No-Hang external long benchmark: {suite}",
       "Five repetitions, original SAT models checked, native UNSAT independently replayed.",
       "Reused published DIMACS holdout; NOT independent new source and NOT SC2026 ranking." if suite=="dimacs"
       else "Third-party SEEDED SAT-style corpus; not original SATLIB or an official competition.",
       f"{TIMEOUT:g} second timeout per attempt, PAR-2 for unsolved cases; same GitHub runner for each solver.","",
       "| Solver | Solved | Timeouts | Sum medians (s) | PAR-2 (s) |",
       "|---|---:|---:|---:|---:|"]
    for name,z in summary.items():
        lines.append(f"| {name} | {z['solved']}/{z['cases']} | {z['timeouts']} | {z['sum_medians_seconds']:.6f} | {z['PAR2_seconds']:.6f} |")
    lines+=["","## Per-instance timings (median of 5 repeats)",
             "| CNF | Expected | Kissat (s) | Kissat API (s) | V15.3.1 (s) | V15.4 (s) | V15.9 (s) |",
             "|---|---|---:|---:|---:|---:|---:|"]
    for case in cases:
        rr={row["solver"]:row for row in results if row["case"]==case["name"]}
        lines.append("| "+case["name"]+" | "+case["expected"]+" | "+
             " | ".join(f"{rr[k]['median_seconds']:.6f}" for k in SOLVERS)+" |")
    (out/"results.md").write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)
    print("SUMMARY",suite,json.dumps(summary,sort_keys=True),flush=True)
    wrong=[(r["case"],r["solver"],x["status"],x["route"])
           for r in results for x in r["runs"] if
           x["status"] in ("SAT","UNSAT") and not x["correct"]]
    if wrong:raise RuntimeError("WRONG_ANSWER_OR_BAD_PROOF "+repr(wrong[:20]))
    # Timeouts are accounted in PAR-2 but never classed as incorrect SAT/UNSAT.

if __name__=="__main__":
    main()
