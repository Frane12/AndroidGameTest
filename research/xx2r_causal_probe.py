#!/usr/bin/env python3
"""XX2R causal diagnosis: targeted, NON-BLIND replay of previously observed gaps.

The 30s E2E runs use frozen original CNFs and SAME pinned binaries from XX2R,
with original SAT witnesses checked by the frozen XX2R harness.
The bounded CMS checkpoints are diagnostics, never PAR2 or proof claims.
No solver change, no frozen baseline mutation, no auto-promotion.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import os
import pathlib
import random
import re
import subprocess
import tempfile
import time

import mre_xx2r_recovered as xx

OUT = pathlib.Path("xx2r_causal_probe")
PROTO = "DRNAS-XX2R-CAUSAL-6SHA-48E2E-30S-24BOUNDED-20261109-v1"
TARGETS = (
    "44092fcc83a5cba81419e82cfd18602c",  # tiny UNSAT: both refs solve
    "70af2c3bfd44bcf9baa2a9605f4a17fe",  # duplicate-rich UNSAT
    "e9b4369f9a98e397ac69eb7740ffef49",  # 15k-variable SAT
    "3fb297f59ad2dc32fd3f79d61951d8cb",  # CMS seed-dependent SAT
    "909f704d5f4127c1197a086705468624",  # dense duplicates / mixed
    "037c423f56548082b1935e88c48ffdda",  # positive CMS control
)
MODES = ("original", "front100", "kissat", "cadical")
BOUNDS = (100, 1000, 5000)
CAP = 30.0
REPS = 2
SHARDS = 3
HARD = set(TARGETS[:4])

def need(ok, msg):
    if not ok:
        raise RuntimeError("XX2R_CAUSAL_FAIL_CLOSED " + str(msg))

def save(path, data):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")

def case_data():
    manifest = xx.verify()
    byid = {c["gbd"]: c for c in manifest["cases"]}
    need(len(TARGETS) == 6 and len(set(TARGETS)) == 6, "bad target cohort")
    need(all(g in byid for g in TARGETS), "case missing from frozen XX2R manifest")
    return [byid[g] for g in TARGETS]

def bounded(c, mode, conf):
    """Read-only CMS conflict checkpoint; cannot establish full solve performance."""
    need(mode in ("original", "front100") and conf in BOUNDS, "bad checkpoint")
    src = xx.ROOT / c["filename"]
    with tempfile.TemporaryDirectory(dir=xx.ROOT) as td:
        use = src
        if mode == "front100":
            n, clauses = xx.xx.x11.x9.x2.parse(src)
            reordered = xx.xx.x11.transform(clauses, "front100")
            need(collections.Counter(clauses) == collections.Counter(reordered),
                 "front100 altered the exact original clause multiset")
            use = pathlib.Path(td) / "front.cnf"
            xx.xx.x11.x9.x2.write(use, n, reordered)
        env = os.environ.copy()
        env["DRNAS_MAX_CONFLICTS"] = str(conf)
        start = time.perf_counter()
        try:
            p = subprocess.run(
                [str(pathlib.Path("mre_x4/bin/native").resolve()),
                 str(use.resolve()), "x_native", str(xx.seed(c, 0))],
                env=env, capture_output=True, text=True, errors="replace", timeout=9.0
            )
        except subprocess.TimeoutExpired:
            return dict(gbd=c["gbd"], mode=mode, budget_conflicts=conf,
                        status="CHECKPOINT_TIMEOUT", diagnostic_not_PAR2=True,
                        wall_s=round(time.perf_counter()-start, 6))
        need(p.returncode == 0, "CMS bounded probe crashed: " + p.stderr[-400:])
        m = re.search(
            r"R195_RESULT status=(\w+) conflicts=(\d+) decisions=(\d+) propagations=(\d+)",
            p.stdout,
        )
        need(bool(m), "missing native bounded counters")
        return dict(gbd=c["gbd"], mode=mode, budget_conflicts=conf,
                    status=m.group(1), conflicts=int(m.group(2)),
                    decisions=int(m.group(3)), propagations=int(m.group(4)),
                    diagnostic_not_PAR2=True, independent_UNSAT_LRAT=False,
                    wall_s=round(time.perf_counter()-start, 6))

def shard(idx):
    need(0 <= idx < SHARDS, "invalid shard")
    cases = [c for i, c in enumerate(case_data()) if i % SHARDS == idx]
    need(len(cases) == 2, "missing cases in shard")
    OUT.mkdir(exist_ok=True)
    trials = []
    probes = []
    for c in cases:
        for rep in range(REPS):
            modes = list(MODES)
            random.Random(xx.seed(c, rep)).shuffle(modes)
            for mode in modes:
                # Keep the frozen 8s XX2R manifest contract unchanged.
                # Extend the limit only during the experimental solve, and restore it.
                original_cap = xx.CAP
                try:
                    xx.CAP = CAP
                    row = xx.trial(c, rep, mode)
                finally:
                    xx.CAP = original_cap
                row["diagnostic_cohort"] = "post_outcome_explanatory_not_blind"
                row["causal_protocol"] = PROTO
                trials.append(row)
                save(OUT / ("shard-%d.json" % idx), dict(trials=trials, bounded=probes))
                print("XX2R_CAUSAL_TRIAL", json.dumps(row, sort_keys=True), flush=True)
        if c["gbd"] in HARD:
            for mode in ("original", "front100"):
                for conf in BOUNDS:
                    row = bounded(c, mode, conf)
                    probes.append(row)
                    save(OUT / ("shard-%d.json" % idx), dict(trials=trials, bounded=probes))
                    print("XX2R_CAUSAL_BOUNDED", json.dumps(row, sort_keys=True), flush=True)
    need(len(trials) == 16, "missing E2E trials")
    print("XX2R_CAUSAL_SHARD_PASS", idx, len(trials), len(probes), flush=True)

def audit():
    cases = case_data()
    trials = []
    probes = []
    for idx in range(SHARDS):
        data = json.loads((OUT / ("shard-%d.json" % idx)).read_text())
        trials += data["trials"]
        probes += data["bounded"]
    need(len(trials) == 48 and len(probes) == 24,
         "expected 48 E2E trials and 24 bounded diagnostics")
    keys = [(r["gbd"], r["rep"], r["mode"]) for r in trials]
    need(len(set(keys)) == 48, "duplicate paired trial")
    need(set(r["gbd"] for r in trials) == set(TARGETS), "cohort drift")
    for r in trials:
        need(r["causal_protocol"] == PROTO and r["mode"] in MODES and
             r["rep"] in range(REPS) and r["status"] in ("SAT", "UNSAT", "TIMEOUT"),
             "trial contract drift")
        need(r["status"] != "SAT" or r["SAT_original_verified"],
             "SAT witness missing on original CNF")
        need(r["status"] != "TIMEOUT" or r["PAR2_s"] == 2*CAP,
             "invalid timeout score")
    need(all(x["diagnostic_not_PAR2"] for x in probes),
         "bounded result accidentally scored as PAR2")
    out = {}
    for mode in MODES:
        rs = [r for r in trials if r["mode"] == mode]
        out[mode] = dict(raw_PAR2_s=round(sum(r["PAR2_s"] for r in rs), 6),
                         conservative_PAR2_s=round(sum(
                             r["PAR2_s"] if r["status"] == "SAT" else 2*CAP for r in rs), 6),
                         SAT_verified=sum(r["status"] == "SAT" for r in rs),
                         UNSAT_unproven=sum(r["status"] == "UNSAT" for r in rs),
                         timeouts=sum(r["status"] == "TIMEOUT" for r in rs),
                         n=len(rs))
    per_case = []
    for c in cases:
        rs = [r for r in trials if r["gbd"] == c["gbd"]]
        per_case.append(dict(gbd=c["gbd"], year=c["year"],
            rows={mode:[dict(rep=r["rep"],status=r["status"],
                            elapsed_s=r["elapsed_s"],PAR2_s=r["PAR2_s"],
                            preprocessing_s=r["preprocessing_s"])
                        for r in rs if r["mode"]==mode]
                  for mode in MODES},
            checkpoints=[p for p in probes if p["gbd"]==c["gbd"]]))
    result = dict(protocol=PROTO, source_run_id=42568720337,
        source_sha_pinned=True, same_frozen_solvers=True, result_set_post_outcome=True,
        experimental_diagnostic_not_blind=True, no_auto_promotion=True,
        cap_s=CAP, E2E_trials=len(trials), bounded_diagnostics=len(probes),
        UNSAT_independent_LRAT=False, score=out, per_case=per_case)
    save(OUT / "report.json", result)
    print("XX2R_CAUSAL_FINAL", json.dumps({k:v for k,v in result.items()
          if k!="per_case"},sort_keys=True),flush=True)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("action",choices=("verify", "shard", "audit"))
    p.add_argument("--shard",type=int,default=0)
    args = p.parse_args()
    if args.action == "verify":
        case_data()
        print("XX2R_CAUSAL_VERIFY_PASS",flush=True)
    elif args.action == "shard":
        shard(args.shard)
    else:
        audit()

if __name__ == "__main__":
    main()
