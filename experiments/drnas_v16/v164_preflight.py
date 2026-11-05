#!/usr/bin/env python3
"""Fail-fast profile preflight for DRNAS v16.4.1 with explicit diagnostics."""
import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

def check(solver, path, expected):
    for profile in ("default", "--sat", "--unsat"):
        args=[solver] + ([] if profile=="default" else [profile]) + [str(path)]
        try:
            p=subprocess.run(args,capture_output=True,text=True,timeout=10,check=False)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"PROFILE_PREFLIGHT_TIMEOUT profile={profile} input={path}")
        got={10:"SAT",20:"UNSAT"}.get(p.returncode, "ERROR")
        print(f"PROFILE_PREFLIGHT profile={profile} expected={expected} actual={got} returncode={p.returncode}",flush=True)
        if got!=expected:
            print("STDOUT tail:",p.stdout[-1000:],flush=True)
            print("STDERR tail:",p.stderr[-2000:],flush=True)
            raise RuntimeError(f"PROFILE_PREFLIGHT_FAILED profile={profile} expected={expected} actual={got}")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--solver",required=True)
    args=ap.parse_args()
    with tempfile.TemporaryDirectory() as t:
        root=Path(t)
        sat=root/"sat.cnf"
        unsat=root/"unsat.cnf"
        sat.write_text("p cnf 2 2\n1 2 0\n-1 2 0\n",encoding="ascii")
        unsat.write_text("p cnf 1 2\n1 0\n-1 0\n",encoding="ascii")
        check(args.solver,sat,"SAT")
        check(args.solver,unsat,"UNSAT")
    print("PROFILE_PREFLIGHT_PASSED",flush=True)

if __name__=="__main__":
    try:
        main()
    except Exception as e:
        print(f"PROFILE_PREFLIGHT_EXCEPTION: {type(e).__name__}: {e}",file=sys.stderr,flush=True)
        raise
