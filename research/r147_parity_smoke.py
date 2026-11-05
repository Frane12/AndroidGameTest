#!/usr/bin/env python3
"""R147 independently paired smoke test on six REUSED SHA-pinned SATLIB PARITY CNFs."""
import collections
import csv
import hashlib
import json
from pathlib import Path
import random
import subprocess
import time
import sys
import r127_early_xor_benchmark as witness

MODES=("kissat","cadical","r118","r147")
REPS=2
CAP=10.0
BIN=Path("r147")
SOLVERS={"kissat":Path("built/bin/kissat_4_0_4"),
         "cadical":Path("built/bin/cadical_3_0_1")}
EXPECTED=("par16-1-c.cnf","par16-1.cnf","par32-3.cnf",
          "par32-4-c.cnf","par8-5-c.cnf","par8-5.cnf")

def check(b,msg):
    if not b:raise RuntimeError("R147_PARITY_AUDIT "+msg)

def run_one(src,mode):
    if mode=="r147":
        cmd=[str((BIN/"r147").resolve()),str(src.resolve()),
             str((BIN/"r132").resolve()),str((BIN/"r118").resolve()),
             str(SOLVERS["kissat"].resolve()),str(SOLVERS["cadical"].resolve())]
    elif mode=="r118":
        cmd=[str((BIN/"r118").resolve()),str(src.resolve()),
             str(SOLVERS["kissat"].resolve())]
    else:
        cmd=[str(SOLVERS[mode].resolve()),str(src.resolve())]
    st=time.perf_counter()
    try:
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=CAP)
        t=time.perf_counter()-st
        check(p.returncode in (10,20),mode+" error "+str(p.returncode)+p.stderr[-200:].decode(errors="replace"))
        status="SAT" if p.returncode==10 else "UNSAT"
        if t>=CAP: status="TIMEOUT"
        if status=="SAT":witness.check_original_sat(p.stdout,src)
        route=""
        if mode=="r147":
            for line in p.stdout.splitlines():
                if line.startswith(b"c R147_ROUTE "):
                    route=line.decode(errors="replace")
            check(bool(route),"missing r147 route")
    except subprocess.TimeoutExpired:
        status="TIMEOUT";t=CAP;route="timeout"
    return {"status":status,"seconds":round(min(t,CAP),6),
            "par2":round(min(t,CAP),6) if status!="TIMEOUT" else 20.0,
            "route":route}

def main():
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--satlib",type=Path,required=True)
    ap.add_argument("--out",type=Path,default=Path("r147/parity"))
    a=ap.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    sources=[]
    for name in EXPECTED:
        found=list(a.satlib.rglob(name))
        check(len(found)==1,name+" not unique or missing")
        sources.append(found[0])
    rows=[]
    for src in sources:
        sha=hashlib.sha256(src.read_bytes()).hexdigest()
        for rep in range(REPS):
            shuffled=list(MODES)
            random.Random("R147-PARITY-FROZEN"+sha+str(rep)).shuffle(shuffled)
            decisions={}
            for mode in shuffled:
                value=run_one(src,mode)
                decisions[mode]=value["status"]
                row={"file":src.name,"sha256":sha,"rep":rep,"mode":mode,**value}
                rows.append(row)
                print("R147_PARITY_PAIRED",json.dumps(row,sort_keys=True),flush=True)
            check(len(set(decisions.values())-{"TIMEOUT"})<=1,"solver outcome disagreement "+src.name)
    check(len(rows)==len(EXPECTED)*REPS*len(MODES),"missing rows")
    with (a.out/"paired.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]))
        w.writeheader();w.writerows(rows)
    report={"protocol":"R147-REUSED-SATLIB-PARITY-6x2x4-v1",
            "blinded":False,"cap_s":CAP,"formulas":len(EXPECTED),
            "measurements":len(rows),"independent_unsat_proof":False,
            "summary":{m:{"solved":sum(r["mode"]==m and r["status"]!="TIMEOUT" for r in rows),
                          "par2_s":round(sum(r["par2"] for r in rows if r["mode"]==m),6)}
                       for m in MODES},
            "r147_route_counts":dict(collections.Counter(
                r["route"].split("route=",1)[1].split()[0] if "route=" in r["route"] else "timeout"
                for r in rows if r["mode"]=="r147")),
            "verdict":"DIAGNOSTIC_ONLY"}
    (a.out/"audit.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("R147_PARITY_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":main()
