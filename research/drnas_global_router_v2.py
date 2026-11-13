#!/usr/bin/env python3
"""DRNAS router-v2: train-only risk-controlled routing and sealed SAT2025 evaluation.

Does NOT learn from 2025 holdout nor earlier exposed MATERIAL2 holdout. Native
solver and proof binaries are frozen. All policy gates are diagnostic only.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import os
import random
import statistics
import tempfile
import time
from pathlib import Path

import drnas_real_material2 as M
import drnas_real_train2 as T
import drnas_global_material2025 as D

PROTOCOL = "DRNAS-ROUTER-V2-v1"
BASE = "X5"
CONTROL = "NO_MIN"
ARMS = ("NO_MIN", "X5", "OLD_GLOBAL", "GLOBAL_V2", "SHAM_X5")
COMPETITORS = ("Kissat", "CaDiCaL", "CMS")
CAP_COUNTS = ((3.0,64),(10.0,32),(30.0,16))
REPEATS = 2
SHA_BINARIES = ("frozen-proof", "drnas-x5", "drat-trim", "kissat", "cadical", "cms")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(path, item):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(item, sort_keys=True, indent=2)+"\n")


def decide(rule, feat):
    """Route to NO_MIN only on evidence-based region; otherwise fixed X5."""
    if rule is None:
        return BASE
    if rule.get("kind") != "region" or rule.get("fallback") != BASE or rule.get("target") != "X5_NO_MIN":
        raise ValueError("Malformed v2 rule")
    predicates = rule.get("predicates", [])
    if not 1 <= len(predicates) <= 2:
        raise ValueError("Invalid rule complexity")
    for p in predicates:
        if p["feature"] not in M.FEATURES or not isinstance(p["threshold"], (int,float)):
            raise ValueError("Invalid feature")
        match = feat[p["feature"]] < p["threshold"]
        if match != p["below"]:
            return BASE
    return "X5_NO_MIN"


def region(specs):
    return {"kind":"region", "fallback":BASE, "target":"X5_NO_MIN",
            "predicates":[{"feature":x[0], "threshold":x[1], "below":x[2]} for x in specs]}


def training_samples(folder):
    """Only immutable REAL1-MATERIAL2 TRAIN trials, no validation or holdout."""
    grouped = collections.defaultdict(lambda:collections.defaultdict(list))
    manifests = []
    for p in sorted(Path(folder).rglob("manifest.json")):
        meta = json.loads(p.read_text())
        if meta.get("stage") != "train" or meta.get("protocol") != M.PROTOCOL:
            raise AssertionError("Refusing non-training source")
        if meta["cpus"] != 1 or set(meta["arms"]) != set(T.ARMS):
            raise AssertionError("Expected 3 matched single-core native arms")
        rows = [json.loads(x) for x in (p.parent/"trials.jsonl").read_text().splitlines() if x]
        for r in rows:
            if r["split"]!="train" or r["arm"] not in T.ARMS:
                raise AssertionError("Train/holdout leakage")
            if r["PAR2"] != (r["e2e_s"] if r["accepted"] else 2*r["cap_s"]):
                raise AssertionError("PAR2 not verified")
            if r["accepted"] and not r["verified"]:
                raise AssertionError("Unverified train result")
            grouped[r["sha256"]][r["arm"]].append(r)
        manifests.append((meta,rows))
    if len(manifests)!=4 or len({m["shard"] for m,_ in manifests})!=4:
        raise AssertionError("Expected 4 immutable train shards")
    if len({m["material_sha"] for m,_ in manifests})!=1:
        raise AssertionError("Source material mismatch")
    if len({json.dumps(m["binary_sha"],sort_keys=True) for m,_ in manifests})!=1:
        raise AssertionError("Train engine drift")
    if set(grouped) != {s for m,_ in manifests for s in m["sources"]}:
        raise AssertionError("Lost training source")
    samples = []
    for source, arms in grouped.items():
        if set(arms)!=set(T.ARMS):
            raise AssertionError("Unpaired train source")
        native = {a:sorted(v,key=lambda r:r["rep"]) for a,v in arms.items()}
        n = len(native["X5"])
        if n!=len(native["X5_NO_MIN"]) or len({(r["cap_s"],r["rep"]) for r in native["X5"]})!=n:
            raise AssertionError("Unpaired train repeat")
        before,after = native["X5"],native["X5_NO_MIN"]
        if [(r["cap_s"],r["rep"]) for r in before] != [(r["cap_s"],r["rep"]) for r in after]:
            raise AssertionError("Unmatched caps")
        deltas = [(a["PAR2"]-b["PAR2"])/(2*a["cap_s"]) for a,b in zip(before,after)]
        # Remove microsecond/millisecond timing noise, without erasing substantive wins.
        deltas = [v if abs(v)*2*before[i]["cap_s"] >= .005 else 0.0
                  for i,v in enumerate(deltas)]
        gain = statistics.median(deltas)
        if n < 2:
            gain = 0.0
        samples.append({"sha":source,"family":before[0]["family"],
            "features":before[0]["features"],"gain":max(-1.,min(1.,gain)),
            "paired_repeats":n, "source_cap":before[0]["cap_s"]})
    if len(samples)<200 or len({s["family"] for s in samples})<100:
        raise AssertionError("Insufficient independent train sources")
    return sorted(samples,key=lambda x:x["sha"]), {
        "sources":len(samples), "families":len({s["family"] for s in samples}),
        "informative":sum(abs(s["gain"])>1e-4 for s in samples),
        "material_sha":manifests[0][0]["material_sha"],
        "binary_sha":manifests[0][0]["binary_sha"],
        "training_shards":4
    }


def candidate_predicates(samples):
    result, seen = [], set()
    for name in M.FEATURES:
        values = sorted(float(s["features"][name]) for s in samples)
        for q in (.20,.40,.60,.80):
            i = min(len(values)-2,max(0,int(q*(len(values)-1))))
            low,high = values[i],values[i+1]
            if low == high:
                continue
            threshold = (low+high)/2
            for below in (True,False):
                p = (name,round(threshold,10),below)
                if p not in seen:
                    result.append(p)
                    seen.add(p)
    return result


def selected(samples, rule):
    return [s for s in samples if decide(rule,s["features"])=="X5_NO_MIN"]


def score(samples, rule):
    selected_units = selected(samples,rule)
    selected_families = {s["family"] for s in selected_units}
    wins = {s["family"] for s in selected_units if s["gain"]>.005}
    if len(selected_units)<12 or len(selected_families)<10 or len(wins)<3:
        return -1.
    families = collections.defaultdict(list)
    for s in samples:
        families[s["family"]].append(s["gain"] if decide(rule,s["features"])=="X5_NO_MIN" else 0.)
    benefit = statistics.mean(statistics.mean(v) for v in families.values())
    # Explicit regularization for a second split and small/slippery regions.
    return benefit - .00025*(len(rule["predicates"])-1)


def fit_rule(samples):
    preds = candidate_predicates(samples)
    rules = [region([p]) for p in preds]
    # Bounded depth 2: different structural features only, no family labels.
    rules += [region([a,b]) for i,a in enumerate(preds) for b in preds[i+1:]
              if a[0]!=b[0]]
    best_rule, best_score = None, .0006
    for rule in rules:
        s = score(samples,rule)
        if s>best_score:
            best_rule,best_score=rule,s
    return best_rule,best_score


def fit(args):
    samples,meta = training_samples(args.train)
    def fold(s):
        return int(sha(("router-v2-cv|"+s["family"]).encode())[:8],16)%5
    cv = []
    for k in range(5):
        a = [s for s in samples if fold(s)!=k]
        b = [s for s in samples if fold(s)==k]
        rule,_ = fit_rule(a)
        gains = collections.defaultdict(list)
        for s in b:
            gains[s["family"]].append(s["gain"] if decide(rule,s["features"])=="X5_NO_MIN" else 0.)
        benefit = statistics.mean(statistics.mean(v) for v in gains.values()) if gains else 0.0
        cv.append({"fold":k, "families":len(gains), "gain_vs_fixed_X5":benefit,
                   "active_sources":len(selected(b,rule))})
    proposed,train_score = fit_rule(samples)
    cv_mean = statistics.mean(x["gain_vs_fixed_X5"] for x in cv)
    model={
        "protocol":PROTOCOL, "baseline":BASE,
        "proposed_rule":proposed, "promoted":False,
        "training_run":43405148962, "train_only":True,
        "validation_and_holdout_excluded":True,
        "training":meta, "train_score":train_score,
        "family_cv":cv, "family_cv_mean":cv_mean,
        "cv_positive":bool(cv_mean>.002 and
                           sum(x["gain_vs_fixed_X5"]>0 for x in cv)>=4),
        "proposed_switches_on_train":len(selected(samples,proposed)),
        "diagnostic_only":True,
        "notes":"No policy accepted without new unseen-set verification"
    }
    write(args.out,model)
    M.emit("ROUTER_V2_FIT",model)


def validate_model(data):
    if (data.get("protocol")!=PROTOCOL or data.get("promoted") is not False or
        data.get("train_only") is not True or data.get("baseline")!="X5"):
        raise AssertionError("Non-frozen/non-diagnostic model")
    decide(data["proposed_rule"],{k:1.0 for k in M.FEATURES})


def validate_material(folder):
    manifest=json.loads((folder/"manifest.json").read_text())
    if (manifest["protocol"]!=D.PROTOCOL or
        manifest.get("only_new_2025_submissions") is not True):
        raise AssertionError("Invalid 2025 material protocol")
    originals=manifest["sources"]
    if len(originals)<24 or len({s["family"] for s in originals})<10:
        raise AssertionError("Underpowered blind material")
    if len({s["semantic_sha256"] for s in originals})!=len(originals):
        raise AssertionError("Semantic duplicate")
    if any(s["track"]!="main_2025,submissions_2025" or s["source_year"]!=2025 for s in originals):
        raise AssertionError("Not new 2025 originals")
    return sorted(originals,key=lambda s:s["sha256"])


def execute_route(arm,cnf,clauses,n,cap,td,model_path,old_model_path):
    """Charge feature extraction and policy I/O to elapsed end-to-end time."""
    if arm in ("NO_MIN","X5",*COMPETITORS):
        call="X5_NO_MIN" if arm=="NO_MIN" else arm
        r=T.execute(call,cnf,clauses,n,cap,td)
        r["effective_arm"]=call
        r["arm"]=arm
        return r
    started=time.monotonic()
    path=old_model_path if arm=="OLD_GLOBAL" else model_path
    model=json.loads(path.read_text())
    with cnf.open("rb") as handle:
        features=M.features(handle.read(131072))
    if arm=="OLD_GLOBAL":
        if model.get("protocol")!=M.PROTOCOL or model.get("promoted") is not False:
            raise AssertionError("Old diagnostic candidate changed")
        choice=T.choose(model["proposed_rule"],features)
    else:
        validate_model(model)
        choice=decide(model["proposed_rule"],features)
        if arm=="SHAM_X5":
            choice=BASE
    overhead=time.monotonic()-started
    if choice not in ("X5_NO_MIN","X5"):
        raise AssertionError("Unsupported native choice")
    if overhead>=cap:
        return {"arm":arm,"effective_arm":choice,"status":"TIMEOUT",
                "verified":False,"accepted":False,"cap_s":cap,"e2e_s":overhead,
                "PAR2":2*cap,"routing_s":overhead,"solve_s":overhead,
                "check_s":0.0,"maxrss_kib":None,"conflicts":None,"propagations":None}
    r=T.execute(choice,cnf,clauses,n,cap-overhead,td)
    total=time.monotonic()-started
    r.update({"arm":arm,"effective_arm":choice,"e2e_s":total,
        "solve_s":r["solve_s"]+overhead,"routing_s":overhead,
        "cap_s":cap,"accepted":bool(r["accepted"] and total<=cap)})
    r["PAR2"]=total if r["accepted"] else 2*cap
    return r


def bench(args):
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    originals=validate_material(args.material)
    model=json.loads(args.model.read_text())
    validate_model(model)
    old=json.loads(args.old_model.read_text())
    if not old.get("proposed_rule") or old.get("promoted") is not False:
        raise AssertionError("Previous global diagnostic model not frozen")
    args.out.mkdir(parents=True,exist_ok=False)
    all_caps = {}
    for cap,count in CAP_COUNTS:
        cohort=originals[:min(count,len(originals))]
        all_caps[str(int(cap))]=[s["sha256"] for s in cohort]
    manifest={
        "protocol":PROTOCOL, "material_protocol":D.PROTOCOL,
        "model_sha":M.sha(args.model.read_bytes()),"old_model_sha":M.sha(args.old_model.read_bytes()),
        "material_sha":M.sha((args.material/"manifest.json").read_bytes()),
        "binary_sha":{k:M.sha((Path("build")/k).read_bytes()) for k in SHA_BINARIES},
        "shard":args.shard,"shards":args.shards,"one_logical_cpu_per_solver":True,
        "cpus":[cpu],"caps":all_caps,"repeats":REPEATS,
        "source_year":2025,"test_data_never_used_for_training":True}
    write(args.out/"manifest.json",manifest)
    statuses={}
    with tempfile.TemporaryDirectory(prefix="drnas-v2-") as tmp,(args.out/"trials.jsonl").open("w") as log:
        td=Path(tmp)
        for cap,count in CAP_COUNTS:
            all_selected=originals[:min(count,len(originals))]
            chosen=all_selected[args.shard::args.shards]
            arms=ARMS+COMPETITORS if cap==3.0 else ARMS
            for i,s in enumerate(chosen):
                cnf=args.material/s["file"]
                raw=cnf.read_bytes()
                if sha(raw)!=s["sha256"]:
                    raise AssertionError("Original 2025 CNF SHA drift")
                n,m,clauses,identity=M.parse(raw)
                if (n,m,identity)!=(s["nvars"],s["nclauses"],s["semantic_sha256"]):
                    raise AssertionError("Semantic holdout corruption")
                for rep in range(REPEATS):
                    order=list(arms)
                    random.Random(0x20261113^int(s["sha256"][:12],16)^int(cap*1000)^rep).shuffle(order)
                    for arm in order:
                        row=execute_route(arm,cnf,clauses,n,cap,td,args.model,args.old_model)
                        row.update({"sha256":s["sha256"],"family":s["family"],"source_year":2025,
                                    "gbd_hash":s["gbd_hash"],"shard":args.shard,"rep":rep,"cap_s":cap})
                        if row["accepted"]:
                            if not row["verified"] or row["e2e_s"]>cap:
                                raise AssertionError("Invalid accepted result")
                            previous=statuses.setdefault(s["sha256"],row["status"])
                            if previous!=row["status"]:
                                raise AssertionError("Contradictory independently verified answers")
                        if row["PAR2"]!=(row["e2e_s"] if row["accepted"] else 2*cap):
                            raise AssertionError("Wrong PAR2")
                        log.write(json.dumps(row,sort_keys=True)+"\n")
                        log.flush()
                if (i+1)%4==0 or i+1==len(chosen):
                    M.emit("ROUTER_V2_PROGRESS",{"shard":args.shard,"cap_s":cap,
                        "completed":i+1,"total":len(chosen)})
    M.emit("ROUTER_V2_SHARD_DONE",{"shard":args.shard,
        "sources":len(originals),"caps":{k:len(v) for k,v in all_caps.items()}})


def bootstrap(rows,arm,base="X5",seed=131126,reps=3500):
    families=collections.defaultdict(lambda:collections.defaultdict(float))
    for r in rows:
        families[r["family"]][r["arm"]]+=r["PAR2"]
    names=sorted(families)
    def improvement(groups):
        before=sum(families[n][base] for n in groups)
        after=sum(families[n][arm] for n in groups)
        return (before-after)/before if before>0 else 0.0
    rng=random.Random(seed)
    simulations=[improvement([rng.choice(names) for _ in names]) for _ in range(reps)]
    simulations.sort()
    return {"reduction":improvement(names),"lower95":simulations[int(.025*(reps-1))],
            "upper95":simulations[int(.975*(reps-1))],"family_units":len(names)}


def report(args):
    manifests=[];rows=[]
    for p in sorted(args.results.rglob("manifest.json")):
        m=json.loads(p.read_text())
        if m["protocol"]!=PROTOCOL:
            raise AssertionError("Invalid benchmark result")
        raw=[json.loads(x) for x in (p.parent/"trials.jsonl").read_text().splitlines() if x]
        manifests.append(m)
        rows+=raw
    if len(manifests)!=4 or set(m["shard"] for m in manifests)!=set(range(4)):
        raise AssertionError("Incomplete/mismatched shard count")
    for key in ("material_sha","model_sha","old_model_sha","binary_sha","caps"):
        if len({json.dumps(m[key],sort_keys=True) for m in manifests})!=1:
            raise AssertionError("Inconsistent benchmark %s"%key)
    cases=manifests[0]["caps"]
    expected=set()
    for k,sha_list in cases.items():
        cap=float(k)
        arms=ARMS+COMPETITORS if cap==3 else ARMS
        for source in sha_list:
            for rep in range(REPEATS):
                expected.update((source,cap,rep,arm) for arm in arms)
    actual=[(r["sha256"],r["cap_s"],r["rep"],r["arm"]) for r in rows]
    if len(rows)!=len(expected) or len(set(actual))!=len(actual) or set(actual)!=expected:
        raise AssertionError("Missing/duplicate trials")
    if any((r["accepted"] and not r["verified"]) or
           r["source_year"]!=2025 or
           r["PAR2"]!=(r["e2e_s"] if r["accepted"] else 2*r["cap_s"]) for r in rows):
        raise AssertionError("Incorrect credit / blind data corruption")
    report={"protocol":PROTOCOL,"status":"COMPLETE","promoted":False,
        "training_run":43405148962,"dataset":"only new submissions SAT Competition 2025",
        "originals":len(cases["3"]),"repeats":REPEATS,
        "one_cpu":True,"caps":{},"holdout_used_for_training":False}
    for cap,_ in CAP_COUNTS:
        subset=[r for r in rows if r["cap_s"]==cap]
        arms=ARMS+COMPETITORS if cap==3 else ARMS
        totals={}
        for arm in arms:
            item=[r for r in subset if r["arm"]==arm]
            totals[arm]={"trials":len(item),"verified":sum(r["accepted"] for r in item),
                "SAT":sum(r["accepted"] and r["status"]=="SAT" for r in item),
                "UNSAT":sum(r["accepted"] and r["status"]=="UNSAT" for r in item),
                "unique_solved":len({r["sha256"] for r in item if r["accepted"]}),
                "PAR2_s":sum(r["PAR2"] for r in item),
                "routing_s":sum(r.get("routing_s",0.) for r in item),
                "selected_no_min":sum(r["effective_arm"]=="X5_NO_MIN" for r in item)}
        contrasts={arm:bootstrap(subset,arm) for arm in arms if arm!="X5"}
        wins=contrasts["GLOBAL_V2"]
        baseline=bootstrap(subset,"GLOBAL_V2",base="NO_MIN")
        pass_gate=(wins["reduction"]>=.05 and wins["lower95"]>0 and
                   baseline["reduction"]>=.05 and baseline["lower95"]>0 and
                   totals["GLOBAL_V2"]["verified"]>=max(totals["NO_MIN"]["verified"],
                                                      totals["X5"]["verified"]) and
                   totals["GLOBAL_V2"]["selected_no_min"]>=8)
        report["caps"][str(int(cap))]={"originals":len(cases[str(int(cap))]),
            "arms":totals,"vs_fixed_X5":contrasts,"v2_vs_no_min":baseline,
            "exploratory_gate":pass_gate}
        M.emit("ROUTER_V2_CAP_FINAL",{"cap_s":cap,"results":report["caps"][str(int(cap))]})
    report["exploratory_all_caps_pass"]=all(x["exploratory_gate"] for x in report["caps"].values())
    report["limits"]=[
        "Frozen native binaries, no clause sharing",
        "TRAIN fitted only from earlier MATERIAL2 train shards, never prior holdout",
        "2025 new submissions selected by family/hash independent of outcome",
        "2025 3/10/30s overlapping subsets predetermined by SHA; no outcome-based filtering",
        "Family-cluster bootstrap 95 percent, diagnostic only, never promote automatically",
        "Post-solve conflict/propagation telemetry logged for future analysis only"
    ]
    write(args.out,report)
    M.emit("ROUTER_V2_FINAL",{"status":"COMPLETE",
        "pass":report["exploratory_all_caps_pass"],
        "caps":{k:{"PAR2_V2":v["arms"]["GLOBAL_V2"]["PAR2_s"],
                    "PAR2_X5":v["arms"]["X5"]["PAR2_s"],
                    "PAR2_NO_MIN":v["arms"]["NO_MIN"]["PAR2_s"],
                    "verified_v2":v["arms"]["GLOBAL_V2"]["verified"],
                    "vs_X5":v["vs_fixed_X5"]["GLOBAL_V2"]} for k,v in report["caps"].items()}})


def main():
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=("fit","bench","report"))
    p.add_argument("--train",type=Path)
    p.add_argument("--material",type=Path)
    p.add_argument("--model",type=Path)
    p.add_argument("--old-model",type=Path)
    p.add_argument("--results",type=Path)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--shards",type=int,default=4)
    a=p.parse_args()
    if a.command=="fit":
        if not a.train: p.error("--train required")
        fit(a)
    elif a.command=="bench":
        if not a.material or not a.model or not a.old_model: p.error("missing input")
        if a.shards!=4 or not 0<=a.shard<4: p.error("exactly 4 shards")
        bench(a)
    else:
        if not a.results: p.error("--results required")
        report(a)


if __name__=="__main__":
    main()
