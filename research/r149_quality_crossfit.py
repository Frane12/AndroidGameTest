#!/usr/bin/env python3
"""R149: leakage-aware retrospective structural routing quality cross-fit.
NO solver executions; NO live routing; previous 400 CNFs already used.
"""
import collections
import csv
import hashlib
import json
import pathlib
import random
import statistics
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import r135_nonxor_portfolio as old

ROOT = pathlib.Path("r149")
INPUT = pathlib.Path("r149-input")
SOURCE_SHA = "619665dd5f4ba6680b11200a63ac77ecc706c9897317b5452dbf22a82ef4b787"
PROTO = "DRNAS-R149-QUALITY-STRUCTURE-RETROSPECTIVE-5FOLD-20261105-v1"
CATEGORIES = ("official", "external_application", "external_xor", "external_nonxor")
FEATURES = ("prefix_binary", "prefix_horn", "full_binary", "full_horn")
THRESHOLDS = (0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80)
MODES = ("kissat", "cadical")
FOLDS = 5

def need(ok, message):
    if not ok:
        raise RuntimeError("R149_FAIL_CLOSED " + str(message))

def find(name):
    matches = list(INPUT.rglob(name))
    need(len(matches) == 1, "expected one " + name + ": " + str(matches))
    return matches[0]

def readcsv(path):
    with path.open(newline="") as f:
        return list(csv.DictReader(f))

def fmt(x):
    return round(float(x), 6)

def asfloat(v):
    if v is None or v == "" or str(v).lower() in ("none", "null"):
        return None
    return float(v)

def output(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")

def source():
    old.ROOT = ROOT
    sha, cases = old.read_sources()
    need(sha == SOURCE_SHA, "manifest changed")
    need(len(cases) == 400 and len(set(c["sha256"] for c in cases)) == 400,
         "original source identity or distinctness wrong")
    return {c["sha256"]: c for c in cases}

def collect(cases):
    prior = readcsv(find("per_formula.csv"))
    paired = readcsv(find("paired.csv"))
    need(len(prior) == 400 and len(paired) == 4000, "incomplete historical input")
    need(len(set(r["sha256"] for r in prior)) == 400, "duplicate formula summary")
    need(set(r["sha256"] for r in prior) == set(cases), "input SHA not original 400")
    grouped = collections.defaultdict(dict)
    for r in paired:
        sha = r["sha256"]
        need(sha in cases and r["cohort"] == cases[sha]["cohort"], "paired cohort drift")
        need(r["mode"] in ("kissat", "cadical", "r118", "r135", "r135s"),
             "unknown historical mode")
        need(r["repeat"] in ("0", "1"), "bad repeat")
        need(r["status"] in ("SAT", "UNSAT", "TIMEOUT"), "invalid status")
        need(abs(float(r["par2"]) - (30.0 if r["status"] == "TIMEOUT"
                  else float(r["seconds"]))) < 0.0001, "incorrect PAR-2")
        key = (r["repeat"], r["mode"])
        need(key not in grouped[sha], "duplicate historical trial")
        grouped[sha][key] = r
    rows = []
    for r in prior:
        sha = r["sha256"]
        need(r["cohort"] == cases[sha]["cohort"], "summary cohort drift")
        measurements = grouped[sha]
        need(len(measurements) == 10, "missing paired trial " + sha)
        need(len({measurements[(str(rep), m)]["status"]
                  for rep in (0, 1) for m in ("kissat", "cadical", "r135")
                  if measurements[(str(rep), m)]["status"] != "TIMEOUT"}) <= 1,
             "SAT/UNSAT contradiction")
        totals = {m: sum(float(measurements[(str(rep), m)]["par2"])
                         for rep in (0, 1)) for m in MODES}
        for m in MODES:
            need(abs(totals[m] - float(r[m + "_par2_s"])) < 0.0002,
                 "summary/trial mismatch " + sha + " " + m)
        base = r["r135_route"].lower()
        need(base in MODES, "unrecognized frozen R135 route")
        need(measurements[("0", "r135")]["selector_target"] == base,
             "R135 route disagreement")
        f = {
            "prefix_binary": asfloat(r["r135s_binary_fraction"]),
            "prefix_horn": asfloat(r["r135s_horn_fraction"]),
            "full_binary": asfloat(r["r135_binary_fraction"]),
            "full_horn": asfloat(r["r135_horn_fraction"]),
        }
        for v in f.values():
            need(v is None or 0.0 <= v <= 1.0, "invalid ratio")
        limited = r["r135s_prefix_limited"].strip().lower() in ("true", "1")
        rows.append(dict(sha=sha, cohort=r["cohort"], base=base,
                         f=f, limited=limited, cost=totals))
    return sorted(rows, key=lambda x: x["sha"])

def fold_assignment(rows):
    folds = {}
    for cohort in CATEGORIES:
        a = sorted((r for r in rows if r["cohort"] == cohort), key=lambda r:r["sha"])
        need(len(a) == 100, "expected 100 original formulas per cohort")
        for i, r in enumerate(a):
            folds[r["sha"]] = i % FOLDS
    need(len(folds) == 400, "fold assignment incomplete")
    return folds

def alternate(mode):
    return "cadical" if mode == "kissat" else "kissat"

def rule_applies(rule, row):
    if rule is None or row["base"] != rule["from_route"]:
        return False
    if rule["limited"] != "any" and row["limited"] != (rule["limited"] == "yes"):
        return False
    value = row["f"][rule["feature"]]
    if value is None:
        return False
    return value < rule["threshold"] if rule["operator"] == "<" else value >= rule["threshold"]

def formula_delta(row, rule):
    if not rule_applies(rule, row):
        return 0.0
    return row["cost"][row["base"]] - row["cost"][alternate(row["base"])]

def candidate_rules():
    for origin in MODES:
        for feature in FEATURES:
            for limited in ("any", "yes", "no"):
                for operator in ("<", ">="):
                    for threshold in THRESHOLDS:
                        yield dict(from_route=origin, feature=feature, limited=limited,
                                   operator=operator, threshold=threshold)

def fit(rows):
    # Exactly ONE transparent routing override; minimum support and net regret.
    # All thresholds and complexity penalties are fixed BEFORE examining this run.
    chosen = None
    best = 0.0
    notes = dict(candidate_count=0, accepted=0)
    for rule in candidate_rules():
        notes["candidate_count"] += 1
        switched = [r for r in rows if rule_applies(rule, r)]
        if len(switched) < 12:
            continue
        diffs = [formula_delta(r, rule) for r in switched]
        gains = sum(diffs)
        wins = sum(d > 0.05 for d in diffs)
        losses = sum(d < -0.05 for d in diffs)
        severe = sum(r["cost"][alternate(r["base"])] >=
                     2 * max(r["cost"][r["base"]], 0.001)
                     for r in switched)
        # A single lucky case is insufficient. Penalize changed routes and
        # especially 2x regressions; never optimize a validation fold.
        if wins < 3 or gains <= 10.0 or severe > max(2, len(switched)//10):
            continue
        score = gains - len(switched) * 0.5 - severe * 5.0 - losses * 0.5
        notes["accepted"] += 1
        if score > best:
            best = score
            chosen = dict(rule, support=len(switched), training_gain_s=fmt(gains),
                          training_wins=wins, training_losses=losses,
                          training_regressions_2x=severe,
                          regularized_score=fmt(score))
    return chosen, notes

def result_row(row, fold, chosen):
    switch = rule_applies(chosen, row)
    selected = alternate(row["base"]) if switch else row["base"]
    base_s = row["cost"][row["base"]]
    new_s = row["cost"][selected]
    other_s = row["cost"][alternate(row["base"])]
    return dict(sha256=row["sha"], cohort=row["cohort"], fold=fold,
                original_route=row["base"], selected_route=selected,
                overridden=switch, frozen_route_par2_s=fmt(base_s),
                replay_route_par2_s=fmt(new_s), oracle_best_par2_s=fmt(min(row["cost"].values())),
                replay_gain_s=fmt(base_s-new_s),
                alternative_gain_s=fmt(base_s-other_s),
                severe_regression_vs_baseline=(new_s >= 2*max(base_s,0.001) and switch))

def bootstrap(rows):
    # Formula-cluster bootstrap stratified by 4 established cohorts.
    # These are historical samples; CI is NOT a new prospective trial.
    rng = random.Random(14920261105)
    by = {name:[r for r in rows if r["cohort"] == name] for name in CATEGORIES}
    boot = []
    for _ in range(3000):
        draw = [rng.choice(by[name]) for name in CATEGORIES
                for _ in range(len(by[name]))]
        original = sum(r["frozen_route_par2_s"] for r in draw)
        proposed = sum(r["replay_route_par2_s"] for r in draw)
        boot.append(100*(original-proposed)/original if original else 0.0)
    boot.sort()
    return [fmt(boot[74]), fmt(boot[2924])]

def summary(rows):
    base = sum(r["frozen_route_par2_s"] for r in rows)
    replay = sum(r["replay_route_par2_s"] for r in rows)
    oracle = sum(r["oracle_best_par2_s"] for r in rows)
    return dict(formulas=len(rows), frozen_route_PAR2_s=fmt(base),
                replay_route_PAR2_s=fmt(replay), oracle_lower_bound_PAR2_s=fmt(oracle),
                replay_gain_PAR2_s=fmt(base-replay),
                replay_gain_pct=fmt(100*(base-replay)/base) if base else None,
                overridden=sum(r["overridden"] for r in rows),
                changed_route_wins=sum(r["replay_gain_s"] > 0.05 for r in rows),
                changed_route_losses=sum(r["replay_gain_s"] < -0.05 for r in rows),
                regressions_2x=sum(r["severe_regression_vs_baseline"] for r in rows))

def run():
    ROOT.mkdir(exist_ok=True)
    cases = source()
    rows = collect(cases)
    folds = fold_assignment(rows)
    oof = []
    rules = []
    for fold in range(FOLDS):
        development = [r for r in rows if folds[r["sha"]] != fold]
        validation = [r for r in rows if folds[r["sha"]] == fold]
        need(len(development) == 320 and len(validation) == 80,
             "unexpected fold split")
        chosen, notes = fit(development)
        rules.append(dict(fold=fold, development=320, validation=80,
                          rule=chosen, search=notes))
        oof.extend(result_row(r, fold, chosen) for r in validation)
    need(len(oof) == 400 and len(set(r["sha256"] for r in oof)) == 400,
         "OOF incomplete or duplicate")
    byfold = {str(i): summary([r for r in oof if r["fold"] == i]) for i in range(FOLDS)}
    bycohort = {c: summary([r for r in oof if r["cohort"] == c]) for c in CATEGORIES}
    total = summary(oof)
    ci = bootstrap(oof)
    # Honest conclusion: even a positive retrospective CI cannot promote.
    report = dict(protocol=PROTO, experiment="RETROSPECTIVE_OFF_POLICY_CROSS_FIT_ONLY",
                  original_formula_count=400, historical_solver_attempts=4000,
                  NEW_solver_attempts=0, folds=FOLDS,
                  source_manifest_sha256=SOURCE_SHA,
                  original_SHA_verified=True, status="COMPLETE_SHADOW_ONLY",
                  no_runtime_gate=True, train_test_reused_source=True,
                  historical_data_leakage_caveat=True,
                  independent_UNSAT_proofs=False,
                  model="single regularized bounded feature override per training fold",
                  replay_cost_note="Direct historical Kissat/CaDiCaL timings; R149 native detector cost NOT measured",
                  original_R135_cost_note="Frozen route replay excludes old R135 detection overhead; comparator is same-cost R148 exact route",
                  main=total, stratified_formula_bootstrap_95pct_CI_gain_pct=ci,
                  per_cohort=bycohort, per_fold=byfold, learned_rules=rules,
                  verdict="NO_PROMOTION_PROSPECTIVE_NATIVE_SAME_RUNNER_BENCHMARK_REQUIRED")
    output(ROOT/"report.json", report)
    output(ROOT/"rules.json", rules)
    with (ROOT/"out_of_fold_decisions.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(oof[0].keys()))
        w.writeheader()
        w.writerows(sorted(oof, key=lambda r:r["sha256"]))
    print("R149_QUALITY_SHADOW_FINAL", json.dumps(report,sort_keys=True),flush=True)

if __name__ == "__main__":
    run()
