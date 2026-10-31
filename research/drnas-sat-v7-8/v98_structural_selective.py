#!/usr/bin/env python3
"""DRNAS V9.8: post-hoc structural hypothesis tested on frozen, never-run CNFs.

The target is diagnostic only. The selection rule was motivated by V9.6 target
0922... and MUST NOT be reported as independently validated before holdout.
"""
import argparse
import csv
import hashlib
import json
import os
import random
import statistics
import subprocess
from collections import defaultdict
from pathlib import Path
import official_shortlong_select as src

src.RAW_CAP = 96*1024*1024
src.CNF_CAP = 96*1024*1024
src.VARIABLE_CAP = 1_000_000
src.CLAUSE_CAP = 4_000_000
SALT = "DRNAS-v98-selective-0922-prospective-20261031-v1"
TARGET = "0922feab75c35d04d9b8df69013a6df0"
MODES = ("ca_plain", "orig_v76", "v96_phase_durable",
         "v96_plain_durable", "v96_phase_force", "v96_plain_force",
         "v96_phase_stop", "v96_plain_stop")
NEW_MODES = ("ca_plain", "orig_v76", "v96_phase_durable",
             "v96_plain_durable", "v98_selective")
FIELDS = ("id", "group", "sha256", "rep", "limit", "mode", "actual_mode",
          "status", "wall_s", "error", "early_trace")

def save(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")

def candidate_order(s):
    return hashlib.sha256((SALT + "/" + s).encode()).hexdigest()

def target_profile(features):
    """PRE-FROZEN after observing V9.6 target, before fresh V9.8 runs."""
    return (features["avg_width"] >= 5.0
            and features["polarity_imbalance"] <= 0.15
            and features["majority_coverage"] <= 0.35
            and features["binary_frac"] <= 0.05)

def select_mode(features):
    return "v96_plain_durable" if target_profile(features) else "orig_v76"

def freeze(args):
    older = json.loads(Path(args.v96).read_text())
    newer = json.loads(Path(args.v97).read_text())
    diag, = [x for x in older["all_cases"] if x["id"] == TARGET]
    assert diag["official_label"] == "SAT" and target_profile(diag["features"])
    excluded = set(older["prior_54_excluded"])
    excluded.update(x["id"] for x in older["all_cases"])
    excluded.update(x["id"] for x in newer["cases"])
    # No use of experimental solver results to choose prospective instances.
    with Path(args.scores).open(newline="", encoding="utf8") as f:
        scores = list(csv.DictReader(f))
    records = [r for r in scores if r["solverid"] == "biere_cadical3[main]"]
    assert len(records) == 400
    candidates = []
    for r in records:
        if r["instanceid"] in excluded or r["status"] not in (
                "sat-verified", "unsat-verified"):
            continue
        t = float(r["runtime"])
        if not (0.5 <= t <= 180.0):
            continue
        candidates.append({"id": r["instanceid"], "official_label":
                            "SAT" if r["status"] == "sat-verified" else "UNSAT",
                            "official_baseline_s": t})
    candidates.sort(key=lambda x: candidate_order(x["id"]))
    matched = []
    controls = []
    attempts = []
    for c in candidates:
        if len(matched) == 3 and len(controls) == 3:
            break
        try:
            info = src.download_and_features(c["id"])
            is_match = target_profile(info["features"])
            bucket = matched if is_match else controls
            attempts.append({"id": c["id"], "match": is_match, "ok": True})
            if len(bucket) < 3:
                bucket.append({**c, **info, "group":
                               "fresh_match" if is_match else "fresh_control"})
                print("V98_FROZEN_CASE", c["id"], is_match, flush=True)
        except Exception as e:
            attempts.append({"id": c["id"], "ok": False, "error": str(e)})
            print("V98_SKIP", c["id"], str(e)[:100], flush=True)
    if len(matched) != 3 or len(controls) != 3:
        raise RuntimeError("Incomplete predeclared structural quotas: " +
                           str((len(matched), len(controls))))
    all_new = sorted(matched + controls, key=lambda x: candidate_order("run/"+x["id"]))
    save(args.out, {"protocol": SALT, "rule": "width>=5; abs polarity<=.15;"
                    " majority<=.35; binary<=.05", "target": diag,
                    "new": all_new, "attempts": attempts,
                    "excluded_count": len(excluded),
                    "official_commit": src.REV,
                    "official_scores_blob": src.SCORES_GIT_BLOB,
                    "limitations": ["Target is post-hoc diagnostic, not holdout",
                    "Preselected structural strata and public baseline-time "
                    "bounds do not represent full SAT Competition 2026"]})
    print("V98_FROZEN", len(all_new), len(attempts), flush=True)

def run(args):
    data = json.loads(Path(args.manifest).read_text())
    assert data["protocol"] == SALT and args.shard in (0, 1, 2)
    cases = ([data["target"]] if args.shard == 0 else
             data["new"][(args.shard-1)*3:args.shard*3])
    root = Path(args.out)
    root.mkdir(parents=True, exist_ok=True)
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    rows = []
    for c in cases:
        path = root / (c["id"] + ".cnf")
        chk = src.download_and_features(c["id"], path)
        assert chk["sha256"] == c["sha256"]
        assert chk["features"] == c["features"]
        modes = MODES if args.shard == 0 else NEW_MODES
        cap = 30.0 if args.shard == 0 else 15.0
        for rep in range(2):
            seed = (98111 + rep * 451 + int(c["sha256"][:8],16)) % (2**32)
            order = list(modes)
            random.Random(seed ^ 98643).shuffle(order)
            for mode in order:
                actual = select_mode(c["features"]) if mode == "v98_selective" else mode
                t0 = __import__("time").monotonic()
                error = ""
                early = ""
                try:
                    p = subprocess.run([str(Path(args.exe).resolve()), actual,
                                        str(path), str(seed)],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, timeout=cap, check=False)
                    sec = __import__("time").monotonic() - t0
                    if p.returncode:
                        raise RuntimeError("exit "+str(p.returncode)+" "+p.stderr[-250:])
                    detail = [line for line in p.stdout.splitlines()
                              if line.startswith("DRNAS_CAUSAL\\t")]
                    if len(detail) != 1:
                        raise RuntimeError("Missing complete solver result")
                    vals = dict(kv.split("=",1) for kv in detail[0].split("\\t")[1:])
                    status = vals["answer"]
                    if status != c["official_label"]:
                        raise RuntimeError("Solver result contradicts official label")
                    early = "\\n".join(line for line in p.stdout.splitlines()
                                      if line.startswith("DRNAS_EARLY\\t"))
                except subprocess.TimeoutExpired as e:
                    status = "TIMEOUT"
                    sec = cap
                    output = e.stdout or b""
                    if isinstance(output, bytes):
                        output = output.decode("utf8", "replace")
                    early = "\\n".join(line for line in output.splitlines()
                                      if line.startswith("DRNAS_EARLY\\t"))
                except Exception as e:
                    status = "ERROR"
                    sec = __import__("time").monotonic() - t0
                    error = str(e)
                row = {"id": c["id"], "group": c.get("group","known_target"),
                       "sha256": c["sha256"], "rep": rep, "limit": cap,
                       "mode": mode, "actual_mode": actual, "status": status,
                       "wall_s": round(sec,6), "error": error,
                       "early_trace": early}
                rows.append(row)
                print("V98_TRIAL", c["id"][:10], rep, mode, actual, status,
                      round(sec,3), flush=True)
                if status == "ERROR":
                    raise RuntimeError(error)
        path.unlink(missing_ok=True)
    with (root/"raw.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    save(root/"meta.json", {"shard": args.shard, "cases": [c["id"] for c in cases],
                           "trials": len(rows)})
    assert len(rows) == (16 if args.shard == 0 else 30)
    print("V98_SHARD_PASS", args.shard, len(rows), flush=True)

def audit(args):
    data = json.loads(Path(args.manifest).read_text())
    assert data["protocol"] == SALT
    cases = [data["target"]] + data["new"]
    by_case = defaultdict(dict)
    allrows = []
    for shard in range(3):
        fn = Path(args.combined)/f"v98-shard-{shard}"/"results"/"raw.csv"
        with fn.open(newline="") as f:
            allrows.extend(csv.DictReader(f))
    assert len(allrows) == 76, len(allrows)
    seen = set()
    for r in allrows:
        key = (r["id"],r["mode"],int(r["rep"]))
        assert key not in seen
        seen.add(key)
        case, = [c for c in cases if c["id"] == r["id"]]
        assert r["sha256"] == case["sha256"]
        assert r["status"] in ("SAT","UNSAT","TIMEOUT") and not r["error"]
        assert r["actual_mode"] == (select_mode(case["features"])
                                    if r["mode"] == "v98_selective" else r["mode"])
        if r["status"] != "TIMEOUT":
            assert r["status"] == case["official_label"]
        by_case[r["id"]].setdefault(r["mode"],[]).append(
            2 * float(r["limit"]) if r["status"] == "TIMEOUT" else float(r["wall_s"]))
    details = []
    for c in cases:
        modes = MODES if c["id"] == TARGET else NEW_MODES
        assert set(by_case[c["id"]]) == set(modes)
        assert all(len(by_case[c["id"]][m]) == 2 for m in modes)
        details.append({"id":c["id"],"group":c.get("group","known_target"),
                        "selected":select_mode(c["features"]),
                        "profile":target_profile(c["features"]),
                        "mean_PAR2":{m:statistics.mean(by_case[c["id"]][m])
                                     for m in modes}})
    cohorts = {}
    for group in ("fresh_match","fresh_control"):
        relevant = [c for c in details if c["group"] == group]
        cohorts[group] = {"n":len(relevant),"mean_PAR2":{
            m:statistics.mean(c["mean_PAR2"][m] for c in relevant)
            for m in NEW_MODES}}
    matched = [c for c in details if c["group"]=="fresh_match"]
    # Observationally selected target never included in holdout aggregates.
    differences = [c["mean_PAR2"]["v96_phase_durable"] -
                   c["mean_PAR2"]["v98_selective"] for c in matched]
    report = {"protocol":SALT,"trials":len(allrows),"cases":details,
              "cohorts":cohorts,"match_phase_minus_selector_PAR2_s":
              statistics.mean(differences),
              "match_wins":sum(v>0 for v in differences),
              "match_losses":sum(v<0 for v in differences),
              "match_ties":sum(v==0 for v in differences),
              "limitations":["Known target is not independent validation",
              "Only 3 fresh analogues and 3 controls; effects unstable",
              "PAR2 censors >limit; no world record or complexity proof",
              "UNSAT external certificates not independently verified"]}
    save(args.out,report)
    lines = ["# DRNAS V9.8 structural phase-selective test", "",
             "76 completed paired attempts, 1 known target plus 6 unseen official CNFs.",
             "Predeclared post-hoc selector: weak polarity + wide, nonbinary clauses"
             " -> no initial phase hints; otherwise frozen V7.6.", ""]
    for name in ("fresh_match","fresh_control"):
        s = cohorts[name]
        lines += [f"## {name}: {s['n']} independent CNFs", "",
                  "| Method | Mean PAR2 seconds (lower better) |",
                  "|---|---:|"]
        for mode,mean in s["mean_PAR2"].items():
            lines.append(f"| {mode} | {mean:.4f} |")
        lines.append("")
    lines += ["Fresh matches: phase-durable minus V9.8 selector PAR2 = "
              f"{report['match_phase_minus_selector_PAR2_s']:.4f} seconds",
              f"wins/losses/ties = {report['match_wins']}/{report['match_losses']}/{report['match_ties']}",
              "", "## Individual CNFs", ""]
    for c in details:
        lines.append(f"- {c['id'][:12]} ({c['group']}) selected "
                     f"{c['selected']} | "+", ".join(
                         f"{m}={v:.3f}" for m,v in c["mean_PAR2"].items()))
    lines += ["","No official competition placing or generality claim."]
    Path(args.md).write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    s = p.add_subparsers(dest="cmd", required=True)
    for cmd, fields in (("freeze", ("v96","v97","scores","out")),
                        ("run", ("manifest","exe","out")),
                        ("audit",("manifest","combined","out","md"))):
        parser=s.add_parser(cmd)
        for field in fields:
            parser.add_argument("--"+field,required=True)
        if cmd=="run":
            parser.add_argument("--shard",required=True,type=int)
    a=p.parse_args()
    {"freeze":freeze,"run":run,"audit":audit}[a.cmd](a)
