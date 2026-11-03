#!/usr/bin/env python3
"""R25 frozen structure gate: no filename, category, answer or timing input.

This is a *portfolio experiment*, not a novel general-purpose SAT proof.
XOR-looking formulas are sent to native V15.3.1 with independently checked
exact structural routes; density-gated formulas to original V7.8/CaDiCaL;
everything else goes to unchanged Kissat. All time includes this gate.
"""
import argparse
import os
import re
import subprocess
import sys

MAX_PREFIX = 1048576
MAX_XOR_SIZE = 12000000

def choose(path):
    size = os.stat(path).st_size
    with open(path, "rb") as f:
        raw = f.read(MAX_PREFIX)
    header = re.search(rb"(?m)^p\s+cnf\s+(\d+)\s+(\d+)\s*$", raw)
    if not header:
        return "kissat_direct", {"reason": "header"}
    n, m = map(int, header.groups())
    if n <= 0 or m <= 0:
        return "kissat_direct", {"reason": "dimensions"}
    supports = set()
    repeated = 0
    observed = 0
    for line in raw.splitlines():
        s = line.strip()
        if not s or s[:1] in (b"c", b"p", b"%"):
            continue
        if not s.endswith(b" 0"):
            continue  # Never infer complete clause from a truncated prefix
        try:
            vals = [int(x) for x in s.split()]
        except ValueError:
            continue
        if len(vals) >= 3 and vals[-1] == 0 and 2 <= len(vals)-1 <= 10:
            sup = tuple(sorted(abs(x) for x in vals[:-1]))
            if len(set(sup)) != len(sup):
                continue
            observed += 1
            if sup in supports:
                repeated += 1
            supports.add(sup)
    # No model output without exact native checking on the ENTIRE input.
    if size <= MAX_XOR_SIZE and repeated >= 4 and repeated * 100 >= observed:
        return "v1531_xor", {"n": n, "m": m, "repeated": repeated, "observed": observed}
    # Historical V7.8 density gate, explicitly NOT polynomial recognition.
    if n >= 180 and m >= 800 and 39*n <= 10*m <= 44*n:
        return "v78_quality_guided", {"n": n, "m": m, "repeated": repeated, "observed": observed}
    return "kissat_direct", {"n": n, "m": m, "repeated": repeated, "observed": observed}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("cnf")
    p.add_argument("--kissat", required=True)
    p.add_argument("--v1531", required=True)
    p.add_argument("--v78", required=True)
    p.add_argument("--seed", type=int, default=25031103)
    a = p.parse_args()
    path = os.path.abspath(a.cnf)
    route, info = choose(path)
    print("DRNAS_R25_ROUTE\t" + route + "\t" + str(info), flush=True)
    if route == "v1531_xor":
        command = [os.path.abspath(a.v1531), path, os.path.abspath(a.kissat), str(a.seed)]
    elif route == "v78_quality_guided":
        command = [os.path.abspath(a.v78), "quality_guided", path, str(a.seed)]
    else:
        command = [os.path.abspath(a.kissat), path]
    # exec replaces the selector so the job-level wall time includes routing.
    os.execv(command[0], command)

if __name__ == "__main__":
    main()
