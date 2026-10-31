#!/usr/bin/env python3
"""DRNAS V8.9 structural-discovery PILOT; exploratory, not a claim of new SAT class.

Frozen CaDiCaL 3.0.1 and V7.6 controls are used through v89_yield_probe.
New case seeds are disjoint from v8.8/v8.8b/v8.9 yield runs.
No structural feature is used to select a solver in this pilot.
"""
import csv
import hashlib
import json
import math
import os
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import blind_v89 as core

EXPERIMENT = "drnas-v89-structural-pilot40-20261031-frozen-v1"
SHARD = int(os.environ.get("SHARD", "0"))
OUT = Path("structural-v89-pilot") / ("shard-%d" % SHARD)
CAP = 3.0
REPEATS = 3
MODES = ("ca_plain", "orig_v76", "orig_v76_plain",
         "v89_rate_no_hints", "v89_rate_late_hints")
SPECS = []
for family, sizes in (
    ("random3", (175, 195, 215, 235)),
    ("random4", (100, 115, 130, 145)),
    ("color3", (250, 290, 330, 370)),
    ("xor3", (170, 230, 290, 350)),
    ("pigeonhole", (7, 8, 9, 10)),
):
    for size in sizes:
        for instance in (0, 1):
            SPECS.append((family, size, instance))

FEATURE_NAMES = ("density", "mean_width", "binary_fraction",
                 "degree_cv", "max_degree_over_mean",
                 "polarity_imbalance", "largest_component_fraction",
                 "isolated_variable_fraction")
FIELDS = ("family", "size", "instance", "case", "sha256", "mode", "repeat",
          "status", "wall_s", "seed", "error", "gate_reason",
          "learned_delta", "active_256", "threshold", "hints",
          "cpu_256_ns", "cpu_128_ns", "cpu_total_ns")

def structural_features(path):
    """Label/renaming invariant static CNF features; linear in literal count."""
    with open(path) as f:
        header = f.readline().split()
        if len(header) != 4 or header[:2] != ["p", "cnf"]:
            raise ValueError("bad DIMACS header")
        n = int(header[2])
        expected = int(header[3])
        pos, neg = [0] * n, [0] * n
        parent = list(range(n))
        sizes = []
        def root(k):
            while parent[k] != k:
                parent[k] = parent[parent[k]]
                k = parent[k]
            return k
        def union(x, y):
            rx, ry = root(x), root(y)
            if rx != ry:
                parent[ry] = rx
        for line in f:
            if line.startswith("c") or not line.strip():
                continue
            clause = list(map(int, line.split()))
            if not clause or clause[-1] != 0:
                raise ValueError("nonterminated clause")
            clause = clause[:-1]
            sizes.append(len(clause))
            if clause:
                anchor = abs(clause[0]) - 1
                for lit in clause:
                    k = abs(lit) - 1
                    if not 0 <= k < n:
                        raise ValueError("out-of-range literal")
                    if lit > 0: pos[k] += 1
                    else: neg[k] += 1
                    union(anchor, k)
    if len(sizes) != expected or not n:
        raise ValueError("DIMACS clause mismatch or empty problem")
    deg = [a+b for a,b in zip(pos,neg)]
    mean = sum(deg)/n
    std = math.sqrt(sum((x-mean)**2 for x in deg)/n)
    components = defaultdict(int)
    for i in range(n):
        components[root(i)] += 1
    features = dict(
        density=round(expected/n, 8),
        mean_width=round(sum(sizes)/expected, 8),
        binary_fraction=round(sum(x == 2 for x in sizes)/expected, 8),
        degree_cv=round(std/mean if mean else 0, 8),
        max_degree_over_mean=round(max(deg)/mean if mean else 0, 8),
        polarity_imbalance=round(sum(abs(a-b) for a,b in zip(pos,neg)) / sum(deg), 8),
        largest_component_fraction=round(max(components.values())/n, 8),
        isolated_variable_fraction=round(sum(x == 0 for x in deg)/n, 8),
    )
    if not all(math.isfinite(v) for v in features.values()):
        raise ValueError("non-finite feature")
    return features

def main():
    if not 0 <= SHARD < 5:
        raise ValueError("SHARD must be in 0..4")
    OUT.mkdir(parents=True, exist_ok=True)
    # A new frozen experiment ID ensures no earlier holdout instance is reused.
    core.EXPERIMENT = EXPERIMENT
    core.OUT = OUT
    core.CAP = CAP
    specs = [s for i,s in enumerate(SPECS) if i % 5 == SHARD]
    assert len(SPECS) == 40 and len(specs) == 8
    cases = []
    for item in specs:
        case = core.make_case(*item)
        case["features"] = structural_features(case["cnf"])
        cases.append(case)
    (OUT/"manifest.json").write_text(json.dumps({
        "experiment":EXPERIMENT,"cap_s":CAP,"repeats":REPEATS,
        "modes":MODES,"cases":cases}, indent=2))
    results = []
    with (OUT/"raw.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, FIELDS)
        w.writeheader()
        affinity = os.sched_getaffinity(0)
        os.sched_setaffinity(0, {min(affinity)})
        for case in cases:
            for rep in range(REPEATS):
                order = list(MODES)
                random.Random(case["generator_seed"]+rep*941).shuffle(order)
                for mode in order:
                    result = core.execute(case, mode, rep)
                    row = dict(family=case["family"],size=case["size"],
                               instance=case["instance"],
                               case=Path(case["cnf"]).stem,
                               sha256=case["sha256"],mode=mode,repeat=rep,
                               status=result["status"],wall_s=result["wall_s"],
                               seed=result["seed"],error=result.get("error",""),
                               gate_reason=result.get("gate_reason",""),
                               learned_delta=result.get("learned_delta",""),
                               active_256=result.get("active_256",""),
                               threshold=result.get("threshold",""),
                               hints=result.get("hints",""),
                               cpu_256_ns=result.get("cpu_256_ns",""),
                               cpu_128_ns=result.get("cpu_128_ns",""),
                               cpu_total_ns=result.get("cpu_total_ns",""))
                    results.append(row)
                    w.writerow(row)
                    f.flush()
                    print("STRUCTURALV89",row["case"],rep,mode,
                          row["status"],round(row["wall_s"],5),flush=True)
    assert len(results) == 8*REPEATS*len(MODES)
    for case in cases:
        block = [x for x in results if x["sha256"] == case["sha256"]]
        statuses = {x["status"] for x in block if x["status"] in ("SAT","UNSAT")}
        if len(statuses)>1 or any(x["status"]=="ERROR" for x in block):
            raise RuntimeError("incorrect/discrepant solver on "+case["cnf"])
        if case["known_truth"].startswith("UNSAT") and "SAT" in statuses:
            raise RuntimeError("contradicts pigeonhole truth "+case["cnf"])
    print("SHARD_SUCCESS",SHARD,len(results),flush=True)

if __name__ == "__main__":
    main()
