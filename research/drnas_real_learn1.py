#!/usr/bin/env python3
"""REAL-LEARN1: original SAT2024 CNFs; independently verified paired cost learning.

Retrospective, not globally blind. Split by normalized source family before any
solver run. Fit only on TRAIN, use VALIDATION for acceptance only, then freeze
and evaluate on untouched HOLDOUT. No model promotion or change to solver core.
"""
import argparse
import collections
import hashlib
import io
import json
import math
import os
import random
import statistics
import tempfile
import time
from pathlib import Path

import drnas_x52_bench as B

TRAIN_ARMS = ("CORE", "X5_NO_MIN", "X52_LBD")
HOLDOUT_ARMS = ("CORE", "X5_NO_MIN", "X52_LBD", "LEARN1_ROUTED", "Kissat", "CaDiCaL")
FEATURES = ("variables_log", "clauses_log", "density", "binary_fraction",
            "unit_fraction", "horn_fraction", "mean_width")
SPLITS = ("train", "validation", "holdout")
TARGETS = {"train": 0.6, "validation": 0.2, "holdout": 0.2}

def emit(tag, value):
    print(tag + " " + json.dumps(value, sort_keys=True, separators=(",", ":")), flush=True)

def digest(buf):
    return hashlib.sha256(buf).hexdigest()

def load_json(path):
    return json.loads(Path(path).read_text())

def save_json(path, data):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")

def assign_splits(entries):
    by_family = collections.defaultdict(list)
    seen = set()
    for row in entries:
        if row["sha256"] in seen:
            raise AssertionError("duplicate original source sha")
        seen.add(row["sha256"])
        by_family[row["family"]].append(row)
    if len(by_family) < 15:
        raise AssertionError("not enough distinct original source families")
    target = {s: TARGETS[s] * len(entries) for s in SPLITS}
    counts = {s: 0 for s in SPLITS}
    allocated = {s: [] for s in SPLITS}
    ordered = sorted(by_family, key=lambda f: digest(("REAL-LEARN1|" + f).encode()))
    for family in ordered:
        group = by_family[family]
        winner = min(SPLITS, key=lambda s: ((counts[s] + len(group)) / target[s], SPLITS.index(s)))
        allocated[winner].extend(group)
        counts[winner] += len(group)
    if min(counts.values()) < 12:
        raise AssertionError("insufficient split size")
    for s in SPLITS:
        allocated[s].sort(key=lambda x: x["sha256"])
    families = {s: {r["family"] for r in allocated[s]} for s in SPLITS}
    if any(families[a] & families[b] for i, a in enumerate(SPLITS) for b in SPLITS[i+1:]):
        raise AssertionError("family leakage")
    return allocated

def split_sources(args):
    m = load_json(args.sources / "source_manifest.json")
    entries = m["sources"]
    if len(entries) != args.count or len({x["sha256"] for x in entries}) != len(entries):
        raise AssertionError("source count/dedup mismatch")
    for row in entries:
        if Path(row["file"]).name != row["file"]:
            raise AssertionError("source path escapes directory")
        raw = (args.sources / row["file"]).read_bytes()
        if digest(raw) != row["sha256"]:
            raise AssertionError("original CNF content SHA mismatch")
    groups = assign_splits(entries)
    rows = [{**r, "split": split} for split in SPLITS for r in groups[split]]
    result = {
        "protocol": "DRNAS-REAL-LEARN1-v1",
        "dataset": "original SAT Competition 2024 retrospective",
        "archive": m.get("dataset"),
        "selection": m.get("selection"),
        "source_count": len(rows),
        "family_count": len({r["family"] for r in rows}),
        "split_counts": {s: len(groups[s]) for s in SPLITS},
        "split_families": {s: len({r["family"] for r in groups[s]}) for s in SPLITS},
        "sources": rows,
    }
    save_json(args.out, result)
    emit("REAL1_SPLITS", {k: result[k] for k in ("source_count","family_count","split_counts","split_families")})

def structural_features(text, nvars, nclauses):
    # Bounded deterministic prefix. Cheap inference, not access to solver result.
    widths = []
    binary = unit = horn = 0
    open_clause = []
    for line in io.StringIO(text):
        ln = line.lstrip()
        if not ln or ln[0] in "cp%":
            continue
        for token in ln.split():
            lit = int(token)
            if lit:
                open_clause.append(lit)
            else:
                k = len(open_clause)
                widths.append(k)
                binary += int(k == 2)
                unit += int(k == 1)
                horn += int(sum(v > 0 for v in open_clause) <= 1)
                open_clause.clear()
                if len(widths) >= 256:
                    break
        if len(widths) >= 256:
            break
    if not widths:
        raise ValueError("no complete clauses in structural sample")
    nn = len(widths)
    return {
        "variables_log": math.log1p(nvars),
        "clauses_log": math.log1p(nclauses),
        "density": nclauses / max(1, nvars),
        "binary_fraction": binary / nn,
        "unit_fraction": unit / nn,
        "horn_fraction": horn / nn,
        "mean_width": sum(widths) / nn,
    }

def choose(policy, feat):
    rule = policy.get("active_rule")
    if rule is None:
        return "CORE"
    if rule["kind"] == "fixed":
        return rule["arm"]
    value = feat[rule["feature"]]
    applicable = value < rule["threshold"] if rule["direction"] == "lt" else value >= rule["threshold"]
    return rule["arm"] if applicable else "CORE"

def checked_manifest(args):
    m = load_json(args.split_manifest)
    if m.get("protocol") != "DRNAS-REAL-LEARN1-v1":
        raise AssertionError("wrong split protocol")
    by = collections.defaultdict(list)
    for r in m["sources"]:
        by[r["split"]].append(r)
    split_sets = [{r["sha256"] for r in by[s]} for s in SPLITS]
    if any(split_sets[i] & split_sets[j] for i in range(3) for j in range(i+1, 3)):
        raise AssertionError("split sha overlap")
    split_fam = [{r["family"] for r in by[s]} for s in SPLITS]
    if any(split_fam[i] & split_fam[j] for i in range(3) for j in range(i+1, 3)):
        raise AssertionError("family overlap")
    if sum(len(by[s]) for s in SPLITS) != m["source_count"]:
        raise AssertionError("split count mismatch")
    return m, by

def benchmark(args):
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    m, by = checked_manifest(args)
    if args.mode == "train":
        all_entries = by["train"] + by["validation"]
        arms = TRAIN_ARMS
    else:
        if not args.model:
            raise RuntimeError("frozen model is required for holdout")
        policy = load_json(args.model)
        if policy.get("protocol") != "DRNAS-REAL-LEARN1-v1":
            raise AssertionError("bad model protocol")
        arms = HOLDOUT_ARMS
        all_entries = by["holdout"]
    entries = [r for i, r in enumerate(sorted(all_entries, key=lambda r:r["sha256"])) if i % args.shards == args.shard]
    args.out.mkdir(parents=True, exist_ok=False)
    manifest = {"protocol": m["protocol"], "stage": args.mode, "cap": args.cap,
                "repeats": args.repeats, "arms": list(arms), "shard": args.shard,
                "shards": args.shards, "source_sha": [r["sha256"] for r in entries],
                "source_splits": {r["sha256"]: r["split"] for r in entries},
                "model_sha": digest(args.model.read_bytes()) if args.model else None,
                "logical_cpu_count": len(os.sched_getaffinity(0))}
    save_json(args.out / "manifest.json", manifest)
    args.checker = args.checker.resolve()
    args.kissat = str(args.kissat.resolve())
    args.cadical = str(args.cadical.resolve())
    args.frat = args.frat.resolve()
    args.cms = str(args.cms.resolve())
    wrong = 0
    with tempfile.TemporaryDirectory() as tdname, (args.out / "trials.jsonl").open("w") as stream:
        td = Path(tdname)
        cnf = td / "original.cnf"
        for number, source in enumerate(entries):
            raw = (args.sources / source["file"]).read_bytes()
            if digest(raw) != source["sha256"]:
                raise AssertionError("CNF source bytes changed")
            cnf.write_bytes(raw)
            text = raw.decode("ascii")
            original = {"sha256": source["sha256"], "family": source["family"],
                        "content": text, "nvars": source["nvars"], "nclauses": source["nclauses"],
                        "cert": "OFFICIAL_UNSAT_UNVERIFIED"}
            # Training/validation features are computed off-line; holdout inference
            # charges feature extraction and model-routing CPU time to routed arm.
            precomputed = structural_features(text, source["nvars"], source["nclauses"])
            for rep in range(args.repeats):
                order = list(arms)
                random.Random(int(source["sha256"][:12], 16) ^ rep).shuffle(order)
                for arm in order:
                    effective = arm
                    overhead = 0.
                    feat = precomputed
                    if arm == "LEARN1_ROUTED":
                        clock = time.monotonic()
                        feat = structural_features(text, source["nvars"], source["nclauses"])
                        effective = choose(policy, feat)
                        overhead = time.monotonic() - clock
                    row = B.run(effective, original, cnf, td, args)
                    row["arm"] = arm
                    row["effective_arm"] = effective
                    row["routing_overhead_s"] = overhead
                    row["e2e_s"] += overhead
                    row["accepted"] = bool(row["verified"] and row["e2e_s"] <= args.cap)
                    row["PAR2"] = row["e2e_s"] if row["accepted"] else 2 * args.cap
                    row.update({"sha256": source["sha256"], "family": source["family"],
                                "split": source["split"], "rep": rep, "features": feat})
                    if row["status"] in ("SAT","UNSAT") and not row["verified"] and row["e2e_s"] < args.cap:
                        # A missing/late proof can be censored; do not claim contradiction.
                        row["uncertified_solution"] = True
                    stream.write(json.dumps(row, sort_keys=True) + "\n")
                    stream.flush()
                if number % 5 == 0:
                    emit("REAL1_PROGRESS", {"stage": args.mode, "shard": args.shard,
                                             "source_done": number+1, "shard_sources": len(entries),
                                             "split": source["split"]})
    emit("REAL1_SHARD_DONE", {"stage": args.mode, "shard": args.shard,
                               "sources": len(entries), "trials": len(entries) * len(arms) * args.repeats})

def load_trials(root):
    rows = []
    manifests = []
    for p in sorted(Path(root).rglob("manifest.json")):
        m = load_json(p)
        data = p.parent / "trials.jsonl"
        rr = [json.loads(line) for line in data.read_text().splitlines() if line.strip()]
        expected = {(s, a, k) for s in m["source_sha"] for a in m["arms"] for k in range(m["repeats"])}
        actual = {(r["sha256"],r["arm"],r["rep"]) for r in rr}
        if len(rr) != len(actual) or expected != actual:
            raise AssertionError("missing/duplicated paired experiment rows")
        if m["logical_cpu_count"] != 1:
            raise AssertionError("solver not pinned to one logical CPU")
        for r in rr:
            if r["PAR2"] != (r["e2e_s"] if r["accepted"] else 2*m["cap"]):
                raise AssertionError("PAR2 bookkeeping invalid")
            if r["accepted"] and not r["verified"]:
                raise AssertionError("unverified result received credit")
        manifests.append(m)
        rows.extend(rr)
    if not manifests:
        raise RuntimeError("no shard results found")
    if len({m["shard"] for m in manifests}) != manifests[0]["shards"]:
        raise RuntimeError("missing shard")
    if len({m["cap"] for m in manifests}) != 1 or len({m["repeats"] for m in manifests}) != 1:
        raise RuntimeError("incomparable caps/repeats")
    return rows, manifests

def source_metrics(rows, split):
    agg=collections.defaultdict(lambda:collections.defaultdict(list))
    family = {}
    feature = {}
    solves = collections.defaultdict(lambda:collections.defaultdict(int))
    for row in rows:
        if row["split"] != split: continue
        sha = row["sha256"]
        agg[sha][row["arm"]].append(row["PAR2"])
        solves[sha][row["arm"]] += int(row["accepted"])
        family[sha] = row["family"]
        feature[sha] = row["features"]
    result = {}
    for sha, values in agg.items():
        if set(values) != set(TRAIN_ARMS):
            raise AssertionError("paired training arms missing")
        if len({len(v) for v in values.values()}) != 1:
            raise AssertionError("different repeat counts")
        result[sha] = {"cost": {k: statistics.mean(v) for k,v in values.items()},
                       "solved": dict(solves[sha]), "family": family[sha], "features": feature[sha]}
    return result

def rule_score(samples, rule):
    base = sum(r["cost"]["CORE"] for r in samples.values())
    cost = sum(r["cost"][choose({"active_rule":rule},r["features"])] for r in samples.values())
    solved = sum(r["solved"].get("CORE",0) for r in samples.values())
    candidate_solved = sum(r["solved"].get(choose({"active_rule":rule},r["features"]),0) for r in samples.values())
    acted = sum(choose({"active_rule":rule},r["features"])!="CORE" for r in samples.values())
    acted_families = len({r["family"] for r in samples.values() if choose({"active_rule":rule},r["features"])!="CORE"})
    return {"relative_gain": (base-cost)/base if base else 0.0,
            "core_PAR2":base,"candidate_PAR2":cost,"core_solved":solved,
            "candidate_solved":candidate_solved,"acted_sources":acted,"acted_families":acted_families}

def candidate_rules(training):
    rules = []
    for arm in TRAIN_ARMS[1:]:
        rules.append({"kind":"fixed","arm":arm})
        for feat in FEATURES:
            xs = sorted(r["features"][feat] for r in training.values())
            for q in (0.2,0.4,0.6,0.8):
                threshold = xs[min(len(xs)-1,round(q*(len(xs)-1)))]
                for direction in ("lt","ge"):
                    rules.append({"kind":"threshold","arm":arm,"feature":feat,
                                  "threshold":threshold,"direction":direction})
    return rules

def fit(args):
    m, by = checked_manifest(args)
    rows, manifests = load_trials(args.train_data)
    if any(x["stage"]!="train" or tuple(x["arms"]) != TRAIN_ARMS for x in manifests):
        raise AssertionError("training stage audit failed")
    want = {r["sha256"] for r in by["train"]+by["validation"]}
    if {x["sha256"] for x in rows} != want:
        raise AssertionError("training dataset incomplete or includes holdout")
    train = source_metrics(rows,"train")
    val = source_metrics(rows,"validation")
    assert set(train) == {r["sha256"] for r in by["train"]}
    assert set(val) == {r["sha256"] for r in by["validation"]}
    informative = sum(any(r["solved"][a] for a in TRAIN_ARMS) for r in train.values())
    val_info = sum(any(r["solved"][a] for a in TRAIN_ARMS) for r in val.values())
    scored = []
    for rule in candidate_rules(train):
        stats = rule_score(train,rule)
        if stats["acted_sources"] < 8 or stats["acted_families"] < 4:
            continue
        if stats["relative_gain"] <= 0:
            continue
        scored.append((stats["relative_gain"],rule,stats))
    scored.sort(key=lambda x:(-x[0],json.dumps(x[1],sort_keys=True)))
    proposed = scored[0][1] if scored else None
    selected = None
    validation = {}
    selection_reasons = []
    if informative < 12:
        selection_reasons.append("too_few_verified_informative_training_sources")
    if val_info < 5:
        selection_reasons.append("too_few_verified_informative_validation_sources")
    if not scored:
        selection_reasons.append("no_training_rule_beats_CORE")
    # Select on TRAIN only. VALIDATION is strictly one pass/fail audit, not tuning.
    if proposed is not None:
        validation = rule_score(val, proposed)
        if validation["relative_gain"] < 0.03:
            selection_reasons.append("validation_PAR2_gain_under_3pct")
        if validation["candidate_solved"] < validation["core_solved"]:
            selection_reasons.append("validation_solved_regression")
        if validation["acted_sources"] < 4:
            selection_reasons.append("too_few_validation_actions")
    if not selection_reasons:
        selected = proposed
    policy={"protocol":"DRNAS-REAL-LEARN1-v1","dataset":"SAT2024 retrospective",
            "source_count":m["source_count"],"model_type":"cheap_one_split_rule_or_abstain",
            "active_rule":selected,"proposed_rule":proposed,
            "train_sources":len(train),"validation_sources":len(val),
            "informative_train_sources":informative,"informative_validation_sources":val_info,
            "training_best":scored[0][2] if scored else {},
            "validation_proposed":validation,"reasons":selection_reasons,
            "model_activated": selected is not None,
            "holdout_seen_at_training":False,"promoted":False,
            "no_production_changes":True}
    save_json(args.out,policy)
    emit("REAL1_MODEL_FROZEN", {"model_activated":policy["model_activated"],
         "informative_train":informative,"informative_val":val_info,
         "proposed_rule":proposed,"validation":validation,
         "reasons":selection_reasons,"model_sha":digest(args.out.read_bytes())})

def cluster_ci(grouped, arm, control, reps=3000):
    keys = sorted(grouped)
    costs_a = [statistics.mean(x["PAR2"] for x in grouped[s][arm]) for s in keys]
    costs_b = [statistics.mean(x["PAR2"] for x in grouped[s][control]) for s in keys]
    rng=random.Random(1222026)
    samples=[]
    for _ in range(reps):
        picks=[rng.randrange(len(keys)) for _ in keys]
        before=sum(costs_b[i] for i in picks)
        after=sum(costs_a[i] for i in picks)
        samples.append((before-after)/before if before else 0.)
    samples.sort()
    original=(sum(costs_b)-sum(costs_a))/sum(costs_b) if sum(costs_b) else 0.
    return {"reduction":original,"lower95":samples[int(.025*(reps-1))],
            "upper95":samples[int(.975*(reps-1))],"independent_source_units":len(keys)}

def report(args):
    policy=load_json(args.model)
    m, by=checked_manifest(args)
    rows, shards=load_trials(args.holdout_data)
    if any(x["stage"]!="holdout" or tuple(x["arms"])!=HOLDOUT_ARMS for x in shards):
        raise AssertionError("holdout stage audit failed")
    if any(x["model_sha"]!=digest(args.model.read_bytes()) for x in shards):
        raise AssertionError("model changed during holdout")
    expect={r["sha256"] for r in by["holdout"]}
    if {r["sha256"] for r in rows} != expect:
        raise AssertionError("incomplete or contaminated holdout")
    grouped=collections.defaultdict(lambda:collections.defaultdict(list))
    for r in rows:
        grouped[r["sha256"]][r["arm"]].append(r)
    counts={}
    for arm in HOLDOUT_ARMS:
        subset=[r for r in rows if r["arm"]==arm]
        counts[arm]={"trials":len(subset),
                     "verified_solved":sum(r["accepted"] for r in subset),
                     "SAT_verified":sum(r["accepted"] and r["status"]=="SAT" for r in subset),
                     "UNSAT_proof_verified":sum(r["accepted"] and r["status"]=="UNSAT" for r in subset),
                     "PAR2_s":sum(r["PAR2"] for r in subset),
                     "uncertified_solutions":sum(r.get("uncertified_solution",False) for r in subset)}
    comparisons={a:cluster_ci(grouped,"LEARN1_ROUTED",a) for a in HOLDOUT_ARMS if a!="LEARN1_ROUTED"}
    verdict=(policy["model_activated"] and
             comparisons["CORE"]["reduction"]>=0.10 and
             comparisons["CORE"]["lower95"]>0.0 and
             counts["LEARN1_ROUTED"]["verified_solved"]>=counts["CORE"]["verified_solved"])
    actual=collections.Counter(r["effective_arm"] for r in rows if r["arm"]=="LEARN1_ROUTED")
    res={"status":"COMPLETE","protocol":"DRNAS-REAL-LEARN1-v1",
         "dataset":"SAT Competition 2024 original retrospective",
         "sources":m["source_count"],"family_count":m["family_count"],
         "splits":m["split_counts"],"split_families":m["split_families"],
         "holdout_sources":len(grouped),"holdout_repeats":shards[0]["repeats"],
         "cap_s":shards[0]["cap"],"model_sha":digest(args.model.read_bytes()),
         "model_activated":policy["model_activated"],"model_reasons":policy["reasons"],
         "model_rule":policy["active_rule"],"informative_train":policy["informative_train_sources"],
         "informative_validation":policy["informative_validation_sources"],
         "routing_actions":dict(actual),"arms":counts,"paired":comparisons,
         "eligible_for_later_independent_replication":bool(verdict),
         "promoted":False,
         "limits":["Retrospective SAT2024, not an unseen future competition set",
                   "Source families, not repetitions, are resampling units",
                   "UNSAT receives solved credit only after independent proof verification",
                   "All timeouts and missing proofs are censored, not labels",
                   "Policy never replaces native core or production binaries"]}
    save_json(args.out,res)
    emit("REAL1_FINAL",{k:res[k] for k in ("status","holdout_sources","model_activated",
        "informative_train","informative_validation","routing_actions","arms","paired",
        "eligible_for_later_independent_replication")})

def main():
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=("split","bench","fit","report"))
    p.add_argument("--sources",type=Path)
    p.add_argument("--split-manifest",type=Path)
    p.add_argument("--train-data",type=Path)
    p.add_argument("--holdout-data",type=Path)
    p.add_argument("--model",type=Path)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--count",type=int,default=120)
    p.add_argument("--mode",choices=("train","holdout"),default="train")
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--shards",type=int,default=4)
    p.add_argument("--repeats",type=int,default=2)
    p.add_argument("--cap",type=float,default=3.0)
    p.add_argument("--checker",type=Path,default=Path("build/drat-trim"))
    p.add_argument("--frat",type=Path,default=Path("build/frat-rs"))
    p.add_argument("--kissat",type=Path,default=Path("build/kissat"))
    p.add_argument("--cadical",type=Path,default=Path("build/cadical"))
    p.add_argument("--cms",type=Path,default=Path("build/cms"))
    args=p.parse_args()
    if args.command=="split": split_sources(args)
    elif args.command=="bench": benchmark(args)
    elif args.command=="fit": fit(args)
    elif args.command=="report": report(args)

if __name__=="__main__":
    main()
