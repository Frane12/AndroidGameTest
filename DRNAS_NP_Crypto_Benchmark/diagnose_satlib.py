#!/usr/bin/env python3
"""Exact structural diagnoses, independent of wall-clock benchmark grouping.

Explains which representation DRNAS selected, isolates algebra's benefit
through ablations, captures raw CryptoMiniSat verbose logs without guessing.
"""
import csv,hashlib,json,statistics,subprocess,time
from collections import Counter,defaultdict
from pathlib import Path
from drnas_np_lab import read_dimacs,normalize,detect_xor3,gaussian,cancel_complementary_pairs,solve

ROOT=Path(__file__).resolve().parent
OUT=ROOT/"diagnostic_results"
OUT.mkdir(exist_ok=True)

def readcsv(file):
    with Path(file).open(newline="") as f:return list(csv.DictReader(f))
def savecsv(file,rows):
    if not rows:return
    with Path(file).open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def families(rows):
    result={}
    for fam in sorted(set(r["family"] for r in rows)):
        vals=[r for r in rows if r["family"]==fam]
        result[fam]={"cases":len(vals),"xor_detected":sum(int(v["xor_count"])>0 for v in vals),
            "median_xor_count":statistics.median(int(v["xor_count"]) for v in vals),
            "methods":dict(Counter(v["selected_method"] for v in vals))}
    return result

def main():
    external=readcsv(ROOT/"external_cases/manifest.csv")
    original=readcsv(ROOT/"cases/manifest.csv")
    profiles=[]
    for rec in external+original:
        group=("external" if rec["case_id"].startswith("satlib_") else "synthetic")
        path=ROOT/("external_cases" if group=="external" else "cases")/(rec["case_id"]+".cnf")
        n,cnf=read_dimacs(path)
        original_clauses=normalize(n,cnf)
        restored,pair_count=(cancel_complementary_pairs(n,cnf) if any(len(c)>3 for c in cnf) else (cnf,0))
        eq,resid=detect_xor3(restored)
        pivots,free=gaussian(eq,n)
        rank=(n-free) if pivots is not None else None
        r=solve(n,cnf,mode="auto",budget=0.12)
        profiles.append(dict(dataset=group,case_id=rec["case_id"],family=rec["family"],
              n=n,m=len(cnf),clause_size_max=max(map(len,cnf)),xor_count=len(eq),
              algebra_rank=rank,algebra_contradiction=(pivots is None),
              residual_clauses=len(resid),interface_variables=len({abs(x) for c in resid for x in c}),
              rewriting_pairs=pair_count,selected_method=r.method,
              solve_status=r.status,solve_internal_ms=round(r.seconds*1000,3),
              solve_nodes=r.nodes,sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    savecsv(OUT/"structure.csv",profiles)
    evidence=[]
    for rec in original:
        if rec["family"] not in ("parity_unsat","masked_unsat","parity_sat","masked_sat"):
            continue
        path=ROOT/"cases"/(rec["case_id"]+".cnf")
        n,cnf=read_dimacs(path)
        for variant in ("full","no_resolution","no_algebra"):
            start=time.perf_counter()
            if variant=="full":r=solve(n,cnf,mode="auto",budget=0.32)
            elif variant=="no_resolution":r=solve(n,cnf,mode="auto",budget=0.32,preprocess_resolve=False)
            else:r=solve(n,cnf,mode="dpll",budget=0.32)
            evidence.append(dict(case_id=rec["case_id"],family=rec["family"],n=n,
              variant=variant,status=r.status,method=r.method,
              solver_internal_ms=round(r.seconds*1000,3),
              xor_found=r.xor_found,algebra_rank=r.rank,interface=r.interface,
              rewrite_pairs=r.resolved_pairs,nodes=r.nodes))
    savecsv(OUT/"ablations.csv",evidence)
    # Verbose solver traces saved unaltered for two hardest UNSAT and easy SAT cases.
    for family in ("parity_unsat","masked_unsat","parity_sat"):
        group=[r for r in original if r["family"]==family]
        sample=max(group,key=lambda r:int(r["n"]))
        p=ROOT/"cases"/(sample["case_id"]+".cnf")
        cmd=["cryptominisat5","--verb","1",str(p)]
        try:
            r=subprocess.run(cmd,text=True,capture_output=True,timeout=5)
            (OUT/f"cms_{family}.log").write_text(
                "command: "+" ".join(cmd)+"\nexit="+str(r.returncode)+"\n"+r.stdout+"\nSTDERR:\n"+r.stderr)
        except Exception as e:
            (OUT/f"cms_{family}.log").write_text("TRACE FAILED "+str(e))
    stat={"external":families([r for r in profiles if r["dataset"]=="external"]),
          "synthetic":families([r for r in profiles if r["dataset"]=="synthetic"]),
          "notes":["Original vs independent instances separated","Algebra counts refer to exact recovered XOR quartets after optional sound pair cancellation","Ablation disables GF2 or CNF rewriting, same CNF and timer","CMS verbose raw logs are evidence, not proof of algorithm's internal reason."]}
    (OUT/"diagnosis.json").write_text(json.dumps(stat,indent=2,ensure_ascii=False))
    print("=== Structural profile of independent SATLIB instances ===")
    for fam,d in stat["external"].items():
        print(f'{fam:12} cases={d["cases"]} xor_detected={d["xor_detected"]} methods={d["methods"]}',flush=True)
    print("=== Synthetic ablation summary ===")
    for family in ("parity_unsat","masked_unsat","parity_sat","masked_sat"):
        for var in ("full","no_resolution","no_algebra"):
            rows=[x for x in evidence if x["family"]==family and x["variant"]==var]
            print(f'{family:15} {var:13}: statuses={dict(Counter(x["status"] for x in rows))} '
                  f'median_internal_ms={statistics.median(x["solver_internal_ms"] for x in rows):.3f}',
                  flush=True)
if __name__=="__main__":main()
