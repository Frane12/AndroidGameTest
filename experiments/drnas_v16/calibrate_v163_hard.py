#!/usr/bin/env python3
"""Calibrate hard random 3-SAT against pinned Kissat on THIS CI runner.
Select measured instances close to 15 seconds, never pretend unmeasured
instances hit the target. Preserve metadata for reproducibility.
"""
import argparse
import csv
import pathlib
import random
import shutil
import subprocess
import time

def make_cnf(path, variables, seed):
    rng=random.Random(seed)
    num_clauses=round(4.26*variables)
    with open(path,"w",encoding="ascii") as f:
        f.write(f"c random3 calibration seed={seed} n={variables} m={num_clauses}\n")
        f.write(f"p cnf {variables} {num_clauses}\n")
        for _ in range(num_clauses):
            vars_=rng.sample(range(1, variables+1),3)
            clause=[v if rng.getrandbits(1) else -v for v in vars_]
            f.write(" ".join(map(str,clause))+" 0\n")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--solver",required=True)
    ap.add_argument("--out-dir",default="drnas_v163_hard")
    ap.add_argument("--target",type=float,default=15.0)
    ap.add_argument("--min-seconds",type=float,default=10.0)
    ap.add_argument("--max-seconds",type=float,default=20.0)
    ap.add_argument("--timeout",type=float,default=24.0)
    ap.add_argument("--attempts",type=int,default=18)
    ap.add_argument("--select",type=int,default=3)
    args=ap.parse_args()
    root=pathlib.Path(args.out_dir)
    candidates=root/"candidates"
    selected=root/"selected"
    candidates.mkdir(parents=True,exist_ok=True)
    selected.mkdir(parents=True,exist_ok=True)
    rows=[]
    # Near phase-transition random3. Fixed sizes and seeds, not learned from outcomes.
    sizes=[220,280,340,400,460,520,580,640,720]
    for i in range(args.attempts):
        n=sizes[i % len(sizes)]
        seed=163000+i
        path=candidates/f"random3_n{n}_seed{seed}.cnf"
        make_cnf(path,n,seed)
        start=time.perf_counter()
        try:
            result=subprocess.run([args.solver,str(path)],stdout=subprocess.DEVNULL,
                                  stderr=subprocess.PIPE,text=True,timeout=args.timeout)
            status={10:"SAT",20:"UNSAT"}.get(result.returncode,"ERROR")
        except subprocess.TimeoutExpired:
            status="TIMEOUT"
        elapsed=time.perf_counter()-start
        eligible=status in ("SAT","UNSAT") and args.min_seconds<=elapsed<=args.max_seconds
        rows.append(dict(file=path.name,variables=n,seed=seed,seconds=round(elapsed,6),
                         result=status,eligible=eligible))
        print(f"CALIBRATION {i+1}/{args.attempts} {path.name}: {status} {elapsed:.3f}s eligible={eligible}",flush=True)
        # We want several eligible problems, not merely one.
        if sum(r["eligible"] for r in rows)>=args.select:
            break
    eligible=[r for r in rows if r["eligible"]]
    eligible.sort(key=lambda r:abs(r["seconds"]-args.target))
    chosen=eligible[:args.select]
    for row in chosen:
        shutil.copyfile(candidates/row["file"],selected/row["file"])
    root.joinpath("calibration.csv").write_text("",encoding="utf-8")
    with open(root/"calibration.csv","w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    print(f"SELECTED {len(chosen)} target≈{args.target}s window=[{args.min_seconds},{args.max_seconds}]s",flush=True)
    for row in chosen:
        print("SELECT",row["file"],row["seconds"],row["result"],flush=True)
    if not chosen:
        print("NO IN-WINDOW INSTANCES. Calibration recorded; benchmark skipped, not mislabeled.",flush=True)

if __name__=="__main__":
    main()
