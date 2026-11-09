#!/usr/bin/env python3
"""DRNAS X13C/D independent E2E experiments; no promotion, historical replays.

C: eight separately frozen X6fresh sources, eight arms, 10s caps.
D: 32 X11 sources, nine factorial arms (order x certified deletion), 12s caps.
Original CNF SHA and solver binary hashes are checked before every run.
SAT models are checked against original CNF; UNSAT uses two-solver agreement,
not an independent LRAT proof. Neither cohort is a prospective blind holdout.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import pathlib
import random
import time

import mre_x13b_sample_gate as b
import mre_x6_fresh_short as x6
import mre_x11_placebo_causal as x11

REPO = pathlib.Path(".")
CONFIG = {
    "c": dict(tag="X13C", root="mre_x13c", sources="mre_x6fresh",
              cap=10.0, ncases=8, shards=8, reps=2,
              arms=("original", "sample_noop", "sample_front", "sample_reduce",
                    "front100", "gate_reduce", "kissat", "cadical"),
              provenance="X6fresh8 independently frozen historical 2021-23 originals; not prospective blind"),
    "d": dict(tag="X13D", root="mre_x13d", sources="mre_x11",
              cap=12.0, ncases=32, shards=8, reps=2,
              arms=("original", "rewrite_identity", "front100", "dedup",
                    "reduce", "front_reduce", "gate_reduce", "kissat", "cadical"),
              provenance="X11 replay32 historical originals; not prospective blind"),
}

def digest(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def set_mode(mode):
    cfg = dict(CONFIG[mode])
    cfg["mode"] = mode
    cfg["root"] = pathlib.Path(cfg["root"])
    cfg["sources"] = pathlib.Path(cfg["sources"])
    cfg["proto"] = "DRNAS-%s-ORIGINAL-SHA-PAIRED-E2E-PAR2-20261109-v1" % cfg["tag"]
    cfg["expected"] = cfg["ncases"] * cfg["reps"] * len(cfg["arms"])
    b.ROOT = cfg["root"]
    b.CAP = cfg["cap"]
    b.REPS = cfg["reps"]
    b.SHARDS = cfg["shards"]
    b.ARMS = cfg["arms"]
    b.PROTO = cfg["proto"]
    x11.ROOT = cfg["sources"]
    return cfg

def source_cases(cfg):
    if cfg["mode"] == "c":
        manifest = x6.verify()
        source_manifest = pathlib.Path("mre_x6fresh/manifest.json")
    else:
        manifest = x11.verify()
        source_manifest = pathlib.Path("mre_x11/manifest.json")
    cases = [dict(c, cohort=c.get("cohort", "x6fresh8_frozen")) for c in manifest["cases"]]
    b.need(len(cases) == cfg["ncases"] and
           len({c["sha256"] for c in cases}) == cfg["ncases"], "source count or SHA duplication")
    for c in cases:
        src = cfg["sources"] / c["filename"]
        b.need(src.is_file() and digest(src) == c["sha256"], "source hash drift: " + str(src))
        b.need("gbd" in c and len(c["sha256"]) == 64, "missing original identifier")
    return cases, digest(source_manifest)

def backends():
    return {key: digest(path) for key, path in {
        "native": "mre_x4/bin/native",
        "kissat": "built/bin/kissat_4_0_4",
        "cadical": "/usr/bin/cadical",
        "cms_lib": "mre5/lib/libcryptominisat5.so.5.11",
    }.items()}

def freeze(cfg):
    cases, upstream_hash = source_cases(cfg)
    cfg["root"].mkdir(exist_ok=True)
    m = dict(protocol=cfg["proto"], experiment=cfg["tag"], cases=cases,
             original_sources=len(cases), original_sha_locked=True,
             source_manifest_sha256=upstream_hash, source_provenance=cfg["provenance"],
             historical_replay_not_blind=True, arms=cfg["arms"], cap_s=cfg["cap"],
             repetitions=cfg["reps"], shards=cfg["shards"],
             expected_trials=cfg["expected"], binary_sha256=backends(),
             SAT_original_witness_required=True,
             UNSAT_independent_LRAT=False, UNSAT_requires_CMS_reference_agreement=True,
             no_auto_promotion=True,
             score="audited PAR2 includes CNF rewriting, solver startup, and end-to-end walltime")
    b.save(cfg["root"] / "manifest.json", m)
    print(cfg["tag"] + "_FROZEN", len(cases), cfg["expected"], flush=True)

def verify(cfg):
    cases, upstream_hash = source_cases(cfg)
    m = json.loads((cfg["root"] / "manifest.json").read_text())
    b.need(m["protocol"] == cfg["proto"] and
           m["source_manifest_sha256"] == upstream_hash and
           m["expected_trials"] == cfg["expected"] and
           m["cap_s"] == cfg["cap"] and
           tuple(m["arms"]) == cfg["arms"], "protocol drift")
    b.need(m["binary_sha256"] == backends(), "solver binary changed across jobs")
    b.need([c["sha256"] for c in m["cases"]] ==
           [c["sha256"] for c in cases], "source roster changed")
    return m

def selftest(cfg):
    b.selftest()
    b.need(cfg["expected"] in (128, 576), "unexpected total")
    b.need("original" in cfg["arms"] and "kissat" in cfg["arms"] and
           "cadical" in cfg["arms"], "reference omission")
    print(cfg["tag"] + "_SELFTEST_PASS", flush=True)

def shard(cfg, index):
    m = verify(cfg)
    b.need(0 <= index < cfg["shards"], "bad shard index")
    selected = [c for i, c in enumerate(m["cases"])
                if i % cfg["shards"] == index]
    b.need(len(selected) == cfg["ncases"] // cfg["shards"], "unbalanced shard")
    rows = []
    for c in selected:
        for rep in range(cfg["reps"]):
            order = list(cfg["arms"])
            random.Random(x11.seed(c, rep)).shuffle(order)
            for arm in order:
                row = b.trial(c, rep, arm)
                b.need(row["original_sha256"] == c["sha256"] and
                       row["protocol"] == cfg["proto"], "trial provenance mismatch")
                rows.append(row)
                b.save(cfg["root"] / ("shard-%d.json" % index), rows)
                print(cfg["tag"] + "_TRIAL", json.dumps(row, sort_keys=True), flush=True)
    n = len(selected) * cfg["reps"] * len(cfg["arms"])
    b.need(len(rows) == n, "short shard")
    print(cfg["tag"] + "_SHARD_PASS", index, n, flush=True)

def audit(cfg):
    m = verify(cfg)
    rows = []
    for idx in range(cfg["shards"]):
        rows.extend(json.loads((cfg["root"] / ("shard-%d.json" % idx)).read_text()))
    roster = {c["sha256"]: c for c in m["cases"]}
    expected = {(src, rep, arm) for src in roster
                for rep in range(cfg["reps"]) for arm in cfg["arms"]}
    actual = {(r["original_sha256"], r["rep"], r["arm"]) for r in rows}
    b.need(len(rows) == len(actual) == cfg["expected"] and actual == expected,
           "unmatched, duplicated, or missing source-seed-arm rows")
    score = {}
    per_source = []
    for srcsha, c in roster.items():
        source_rows = [r for r in rows if r["original_sha256"] == srcsha]
        solved_statuses = {r["status"] for r in source_rows if r["status"] != "TIMEOUT"}
        b.need(len(solved_statuses) <= 1, "SAT / UNSAT solver disagreement")
        cms_unsat = any(r["status"] == "UNSAT" and
                        r["arm"] not in ("kissat", "cadical") for r in source_rows)
        ref_unsat = any(r["status"] == "UNSAT" and
                        r["arm"] in ("kissat", "cadical") for r in source_rows)
        for r in source_rows:
            b.need(r["protocol"] == cfg["proto"] and
                   r["seed"] == x11.seed(c, r["rep"]) and
                   r["cap_s"] == cfg["cap"] and r["gbd"] == c["gbd"],
                   "trial seed / protocol / source drift")
            bin_name = ("kissat" if r["arm"] == "kissat" else
                        "cadical" if r["arm"] == "cadical" else "native")
            b.need(r["binary_sha256"] == m["binary_sha256"][bin_name],
                   "trial backend SHA mismatch")
            b.need(r["status"] != "SAT" or r["SAT_original_witness_verified"],
                   "SAT answer without original model replay")
            b.need(r["status"] != "TIMEOUT" or r["PAR2_s"] == 2 * cfg["cap"],
                   "bad timeout penalty")
            b.need(r["status"] == "TIMEOUT" or
                   r["elapsed_s"] <= cfg["cap"] and
                   r["PAR2_s"] == r["elapsed_s"], "not true E2E PAR2")
            r["accepted"] = (r["status"] == "SAT" or
                             r["status"] == "UNSAT" and cms_unsat and ref_unsat)
            r["audited_PAR2_s"] = (r["PAR2_s"] if r["accepted"] else 2 * cfg["cap"])
        _, clauses = b.x11.x9.x2.parse(cfg["sources"] / c["filename"])
        duplicates = len(clauses) - len(b.dedup(clauses))
        totals = {arm: round(sum(r["audited_PAR2_s"] for r in source_rows
                                 if r["arm"] == arm), 6)
                  for arm in cfg["arms"]}
        per_source.append(dict(sha256=srcsha, gbd=c["gbd"], cohort=c["cohort"],
            duplicate_count=duplicates,
            duplicate_ratio=round(duplicates / max(1, len(clauses)), 6),
            clauses=len(clauses), PAR2_s=totals,
            comparisons={arm: round(totals["original"] - value, 6)
                         for arm, value in totals.items()}))
    for arm in cfg["arms"]:
        rr = [r for r in rows if r["arm"] == arm]
        score[arm] = dict(n=len(rr),
            solved=sum(r["accepted"] for r in rr),
            raw_timeouts=sum(r["status"] == "TIMEOUT" for r in rr),
            PAR2_s=round(sum(r["audited_PAR2_s"] for r in rr), 6),
            prep_s=round(sum(r["preprocess_s"] for r in rr), 6),
            clauses_deleted=sum(r["reduction"].get("deleted", 0) for r in rr))
    for arm, data in score.items():
        for baseline in ("original", "kissat", "cadical"):
            base_s = score[baseline]["PAR2_s"]
            data["pct_less_PAR2_vs_" + baseline] = round(
                100 * (1 - data["PAR2_s"] / base_s), 4)
            data["speedup_vs_" + baseline] = round(base_s / data["PAR2_s"], 5)
    report = dict(protocol=cfg["proto"], experiment=cfg["tag"],
        sources=len(roster), trials=len(rows), cap_s=cfg["cap"],
        source_provenance=cfg["provenance"],
        no_auto_promotion=True, historical_replay_not_blind=True,
        UNSAT_independent_LRAT=False, score=score,
        per_source=per_source, rows=rows)
    b.save(cfg["root"] / "report.json", report)
    headline = {key: value for key, value in report.items()
                if key not in ("rows", "per_source")}
    print(cfg["tag"] + "_FINAL", json.dumps(headline, sort_keys=True), flush=True)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=("c", "d"), required=True)
    p.add_argument("action", choices=("selftest", "freeze", "verify", "shard", "audit"))
    p.add_argument("--shard", type=int, default=0)
    args = p.parse_args()
    cfg = set_mode(args.mode)
    if args.action == "selftest":
        selftest(cfg)
    elif args.action == "freeze":
        freeze(cfg)
    elif args.action == "verify":
        verify(cfg)
        print(cfg["tag"] + "_VERIFY_PASS", flush=True)
    elif args.action == "shard":
        shard(cfg, args.shard)
    else:
        audit(cfg)

if __name__ == "__main__":
    main()
