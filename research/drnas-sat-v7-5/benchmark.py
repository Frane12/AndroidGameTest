#!/usr/bin/env python3
"""V7.5 reproducible SATLIB benchmark. Identical untouched CaDiCaL 3.0.1
across six modes; trial and resume use SAME solver without dropping learned
clauses. All timeouts included in PAR-2; no selection by runtime.
"""
import argparse
import collections
import csv
import hashlib
import json
import random
import statistics
import subprocess
import time
from pathlib import Path

METHODS=("plain","majority","split_plain256","guided256","guided1024","random256")
FIELDS=("case","family","answer_expected","method","repeat","answer","elapsed_s","native_s",
        "hints","limit_conflicts","stage1_status","resumed","hint_us","stage1_us",
        "stage2_us","variables","clauses","error","cutoff_s")
def execute(binary,method,path,seed,timeout_s):
    start=time.perf_counter()
    try:
        run=subprocess.run([str(binary),method,str(path),str(seed)],
                           capture_output=True,text=True,timeout=timeout_s,check=False)
    except subprocess.TimeoutExpired:
        return dict(answer="TIMEOUT",elapsed_s=timeout_s,native_s=None,error="")
    elapsed=time.perf_counter()-start
    if run.returncode:
        raise RuntimeError(f"{method}: solver crash/invalid output: {run.stderr[-1000:]} {run.stdout[-200:]}")
    output=[line for line in run.stdout.splitlines() if line.startswith("DRNAS_RESULT\t")]
    if len(output)!=1:
        raise RuntimeError(f"{method}: no unique result marker")
    cols=output[0].split("\t")
    if len(cols)!=13 or cols[1]!=method or cols[2] not in ("SAT","UNSAT"):
        raise RuntimeError(f"{method}: malformed result: {output[0][:300]}")
    return dict(answer=cols[2],elapsed_s=elapsed,native_s=float(cols[3])/1e6,
         hints=int(cols[4]),limit_conflicts=int(cols[5]),stage1_status=int(cols[6]),
         resumed=int(cols[7]),hint_us=float(cols[8]),stage1_us=float(cols[9]),
         stage2_us=float(cols[10]),variables=int(cols[11]),clauses=int(cols[12]),error="")

def report(rows,repetitions,cutoff_s):
    by=collections.defaultdict(lambda:collections.defaultdict(list))
    families={}
    for row in rows:
        by[row["case"]][row["method"]].append(row)
        families[row["case"]]=row["family"]
    ids=sorted(by)
    if not ids:raise ValueError("No valid benchmark cases")
    def case_cost(samples):
        values=[(2*cutoff_s if x["answer"]=="TIMEOUT" else x["elapsed_s"]) for x in samples]
        return statistics.median(values)
    for case in ids:
        if set(by[case])!=set(METHODS):
            raise ValueError("Method missing on "+case)
        if any(len(by[case][method])!=repetitions for method in METHODS):
            raise ValueError("Missing paired repeats on "+case)
        if any(x["answer"] not in ("SAT","UNSAT","TIMEOUT") for method in METHODS for x in by[case][method]):
            raise ValueError("Unknown outcome on "+case)
    def summarize_cases(cases,method):
        if not cases:return None
        score=sum(case_cost(by[c][method]) for c in cases)
        base=sum(case_cost(by[c]["plain"]) for c in cases)
        return {
           "cases":len(cases),
           "par2_sum_case_medians_s":round(score,6),
           "speedup_plain_over_mode":round(base/max(score,1e-12),6),
           "solved_runs":sum(x["answer"]!="TIMEOUT" for c in cases for x in by[c][method]),
           "total_runs":len(cases)*repetitions,
           "faster_cases":sum(case_cost(by[c][method])<case_cost(by[c]["plain"]) for c in cases),
           "slower_cases":sum(case_cost(by[c][method])>case_cost(by[c]["plain"]) for c in cases),
           "hinted_cases":sum(any(x["hints"] for x in by[c][method]) for c in cases),
           "stage1_unknown_cases":sum(any(x["stage1_status"]==0 for x in by[c][method]) for c in cases),
        }
    overall={m:summarize_cases(ids,m) for m in METHODS}
    fam=collections.defaultdict(list)
    for c in ids:fam[families[c]].append(c)
    byfam={key:{m:summarize_cases(cases,m) for m in METHODS}
           for key,cases in sorted(fam.items())}
    # Exploratory bootstrap over independent instance medians, not repeated
    # runs from the same CNF; no baseline stochastic cherry-picking.
    boot={}
    rng=random.Random(7505001)
    for mode in METHODS[1:]:
        estimates=[]
        for i in range(1000):
            draw=[rng.choice(ids) for _ in ids]
            a=sum(case_cost(by[c]["plain"]) for c in draw)
            b=sum(case_cost(by[c][mode]) for c in draw)
            estimates.append(a/max(b,1e-12))
        estimates.sort()
        boot[mode]=[round(estimates[24],5),round(estimates[974],5)]
    return {
      "cases":len(ids),"repeats":repetitions,"cutoff_s":cutoff_s,
      "original_solver":"CaDiCaL 3.0.1 rel-3.0.1 unchanged",
      "modes":overall,"families":byfam,"bootstrap_95pct_ratio":boot,
      "notes":[
       "Actual public SATLIB archive members with SHA256-verified files, selected without solver timings.",
       "Original untouched single CaDiCaL solver; only default phase hints, conflicts limit, and unphase API used.",
       "When the first solve returns 0 due to conflict budget, unphase is applied then same solver resumed.",
       "PAR-2 for timeout=2*cutoff; sum of per-CNF median across repetitions.",
       "Identical process cutoff for each method, method order randomized per case/repeat.",
       "SAT models checked against all clauses by CaDiCaL API; UNSAT results checked against original expected class.",
       "No solver proof certificate checked for UNSAT.",
       "Small samples and per-instance runtime variability limit claims of general speedup."]
    }
def main(args):
    verify=json.loads(Path(args.verification).read_text())
    root=Path(args.outdir);root.mkdir(parents=True,exist_ok=True)
    rows=[]
    with (root/"raw.csv").open("w",newline="",encoding="utf8") as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS)
        writer.writeheader()
        for i,case in enumerate(verify[args.group]):
            p=Path(case["path"])
            data=p.read_bytes()
            if hashlib.sha256(data).hexdigest()!=case["expected_sha256"]:
                raise RuntimeError("SHA256 error: "+case["name"])
            if case["status"] not in ("SAT","UNSAT"):
                raise RuntimeError("Unknown source SAT label")
            for rep in range(args.repeats):
                order=list(METHODS)
                random.Random(75052026+i*139+rep*701).shuffle(order)
                for method in order:
                    res=execute(args.binary,method,p,7505123+i*389+rep*131,args.timeout)
                    row={key:res.get(key) for key in FIELDS}
                    row.update(case=case["name"],family=case["family"],answer_expected=case["status"],
                               method=method,repeat=rep,cutoff_s=args.timeout)
                    rows.append(row)
                    writer.writerow(row)
                    f.flush()
                    if res["answer"] not in ("TIMEOUT",case["status"]):
                        raise RuntimeError(f"Wrong answer: {case['name']} method={method} got {res['answer']} expected {case['status']}")
            summary=collections.Counter(r["answer"] for r in rows if r["case"]==case["name"])
            print(f"{args.group} {i+1}/{len(verify[args.group])}: {case['name']} {dict(summary)}",flush=True)
    results=report(rows,args.repeats,args.timeout)
    (root/"summary.json").write_text(json.dumps(results,indent=2)+"\n",encoding="utf8")
    print("TOTAL",json.dumps({k:results[k] for k in ("cases","repeats","modes","bootstrap_95pct_ratio")},indent=2),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--binary",required=True)
    p.add_argument("--verification",required=True)
    p.add_argument("--group",choices=["pilot","holdout"],required=True)
    p.add_argument("--outdir",required=True)
    p.add_argument("--timeout",type=float,default=20)
    p.add_argument("--repeats",type=int,default=2)
    main(p.parse_args())
