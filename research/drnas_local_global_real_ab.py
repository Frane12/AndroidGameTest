#!/usr/bin/env python3
"""Paired LOCAL CDCL versus frozen cross-formula GLOBAL policy, never deployment.

The global candidate was learned from separate MATERIAL2 training families but
rejected at family-CV. Here it is enabled for an explicitly DIAGNOSTIC-only
comparison with LOCAL and a cost-matched SHAM on untouched MATERIAL2 holdout.
No clause reuse; "global memory" means a source-level learned X5/X5_NO_MIN
routing policy. All runs are fresh processes, one logical CPU per solver.
"""
import argparse
import collections
import hashlib
import json
import math
import os
import random
import statistics
import tempfile
from pathlib import Path
import drnas_real_material2 as M
import drnas_real_train2 as T

ARMS=("LOCAL","LOCAL_X5","GLOBAL_SHAM","GLOBAL_PROPOSED")
CAP=3.0
REPEATS=2

def dump(path,item):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(item,sort_keys=True,indent=2)+"\n")

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def verify_candidate(candidate):
    if candidate.get("protocol")!=M.PROTOCOL:
        raise AssertionError("Wrong global model protocol")
    if candidate.get("promoted") is not False:
        raise AssertionError("Diagnostic candidate unexpectedly promoted")
    proposed=candidate.get("proposed_rule")
    if proposed is None or proposed.get("arm") not in ("X5", "CORE"):
        raise AssertionError("No compatible or actionable proposed global policy")
    if candidate.get("baseline")!="X5_NO_MIN":
        raise AssertionError("Global model not native-X5 compatible")
    if proposed.get("kind") not in ("threshold","fixed"):
        raise AssertionError("Unsupported global rule")
    if proposed.get("kind")=="threshold" and (
        proposed.get("feature") not in M.FEATURES or
        not isinstance(proposed.get("threshold"),(float,int)) or
        not isinstance(proposed.get("below"),bool)):
        raise AssertionError("Unrecognized or malformed global rule")
    return proposed

def records(material):
    data=json.loads((material/"manifest.json").read_text())
    if data["protocol"]!=M.PROTOCOL:
        raise AssertionError("Source protocol changed")
    entries=data["sources"]
    seen=set();families={}
    for s in entries:
        if s["semantic_sha256"] in seen:
            raise AssertionError("Semantic duplicate in source manifest")
        seen.add(s["semantic_sha256"])
        if s["split"]!=M.split_for(s["family"]):
            raise AssertionError("Family assignment changed")
        if s["family"] in families and families[s["family"]]!=s["split"]:
            raise AssertionError("Family leaked across splits")
        families[s["family"]]=s["split"]
    holdout=[s for s in entries if s["split"]=="holdout"]
    if len(holdout)<25 or len({s["family"] for s in holdout})<10:
        raise AssertionError("Insufficient original-CNF independent holdout")
    return sorted(holdout,key=lambda x:x["sha256"])

def test_shard(args):
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    args.out.mkdir(parents=True,exist_ok=False)
    candidate=json.loads(args.candidate.read_text())
    proposed=verify_candidate(candidate)
    policy={"protocol":candidate["protocol"],"baseline":candidate["baseline"],
            "rule":proposed,"diagnostic_only":True,"model_not_accepted":True,
            "training_source":str(args.source_run),"original_candidate_sha256":sha(args.candidate)}
    dump(args.out/"diagnostic_policy.json",policy)
    holdout=records(args.material)
    selected=holdout[args.shard::args.shards]
    model=args.out/"diagnostic_policy.json"
    manifest={"protocol":"DRNAS-LOCAL-GLOBAL-REAL-v1",
              "source_protocol":M.PROTOCOL,
              "source_run":args.source_run,"source_count_total":len(holdout),
              "shards":args.shards,"shard":args.shard,
              "sources":[r["sha256"] for r in selected],
              "families":sorted({r["family"] for r in selected}),
              "cap":CAP,"repeats":REPEATS,"arms":ARMS,
              "source_manifest_sha256":sha(args.material/"manifest.json"),
              "training_candidate_sha256":sha(args.candidate),
              "diagnostic_policy_sha256":sha(model),
              "binary_sha256":{name:sha(Path("build")/name)
                 for name in ("frozen-proof","drnas-x5","drat-trim")},
              "logical_cpus_per_solver":1,"promoted":False,
              "data_usage":"held-out MATERIAL2 original CNFs; no retraining"}
    dump(args.out/"manifest.json",manifest)
    counters=collections.Counter()
    with tempfile.TemporaryDirectory(prefix="real-local-global-") as temp, (args.out/"trials.jsonl").open("w") as fd:
        td=Path(temp)
        for idx,source in enumerate(selected):
            original=args.material/source["file"]
            raw=original.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=source["sha256"]:
                raise AssertionError("Original CNF SHA not frozen")
            n,m,clauses,semantic=M.parse(raw)
            if semantic!=source["semantic_sha256"] or n!=source["nvars"] or m!=source["nclauses"]:
                raise AssertionError("Original CNF semantic integrity changed")
            for rep in range(REPEATS):
                order=list(ARMS)
                random.Random(20261113^int(source["sha256"][:12],16)^rep).shuffle(order)
                statuses=set()
                for arm in order:
                    call={"LOCAL":"X5_NO_MIN","LOCAL_X5":"X5",
                          "GLOBAL_SHAM":"SHAM","GLOBAL_PROPOSED":"LEARNED"}[arm]
                    row=T.execute(call,original,clauses,n,CAP,td,model if call in ("LEARNED","SHAM") else None)
                    row["arm"]=arm
                    row.update({"sha256":source["sha256"],"semantic_sha256":source["semantic_sha256"],
                                "family":source["family"],"split":source["split"],
                                "source_year":source.get("source_year","historical"),
                                "rep":rep,"shard":args.shard})
                    if row["accepted"]:
                        statuses.add(row["status"])
                        counters[arm+"_solved"]+=1
                    if row["arm"]=="GLOBAL_PROPOSED" and row["effective_arm"]!="X5_NO_MIN":
                        counters["active_global_decisions"]+=1
                    if row["accepted"] and row["e2e_s"]>CAP:
                        raise AssertionError("Invalid accepted wall-clock cap")
                    if row["PAR2"]!=(row["e2e_s"] if row["accepted"] else 2*CAP):
                        raise AssertionError("Missing proof credited")
                    fd.write(json.dumps(row,sort_keys=True)+"\n")
                    fd.flush()
                if len(statuses)>1:
                    raise AssertionError("Contradictory independently verified answers")
            if idx%5==0:
                print("LOCAL_GLOBAL_PROGRESS",json.dumps({"shard":args.shard,
                    "completed":idx+1,"total":len(selected),"counters":counters},sort_keys=True),flush=True)
    print("LOCAL_GLOBAL_SHARD_DONE",json.dumps({"shard":args.shard,
        "originals":len(selected),"trial_rows":len(selected)*len(ARMS)*REPEATS,
        "counts":counters},sort_keys=True),flush=True)

def interval(values,arm,baseline="LOCAL",seed=161126,reps=6000):
    # Bootstrap original source families, not repeat rows or treatment arms.
    families=collections.defaultdict(lambda:collections.defaultdict(float))
    for r in values:
        families[r["family"]][r["arm"]]+=r["PAR2"]
    keys=sorted(families)
    before=sum(families[f][baseline] for f in keys)
    after=sum(families[f][arm] for f in keys)
    rng=random.Random(seed)
    bootstrap=[]
    for _ in range(reps):
        chosen=[keys[rng.randrange(len(keys))] for _ in keys]
        a=sum(families[f][baseline] for f in chosen)
        b=sum(families[f][arm] for f in chosen)
        bootstrap.append((a-b)/a if a else 0.0)
    bootstrap.sort()
    return {"reduction":(before-after)/before if before else 0.0,
            "lower95":bootstrap[int(.025*(reps-1))],
            "upper95":bootstrap[int(.975*(reps-1))],
            "family_units":len(keys)}

def report(args):
    all_rows=[];metadata=[]
    for p in sorted(args.root.rglob("manifest.json")):
        meta=json.loads(p.read_text())
        rr=[json.loads(x) for x in (p.parent/"trials.jsonl").read_text().splitlines() if x.strip()]
        expected={(source,arm,rep) for source in meta["sources"] for arm in ARMS for rep in range(REPEATS)}
        actual={(r["sha256"],r["arm"],r["rep"]) for r in rr}
        if len(rr)!=len(expected) or len(actual)!=len(rr) or actual!=expected:
            raise AssertionError("Missing paired trial or duplication")
        if meta["logical_cpus_per_solver"]!=1 or meta["cap"]!=CAP:
            raise AssertionError("Mismatched CPU/cap")
        if tuple(meta["arms"])!=ARMS or meta["repeats"]!=REPEATS:
            raise AssertionError("Arms or repetitions differ")
        if any(r["split"]!="holdout" or
               (r["accepted"] and not r["verified"]) or
               r["PAR2"]!=(r["e2e_s"] if r["accepted"] else 2*CAP) for r in rr):
            raise AssertionError("Holdout leakage / proof invalid")
        metadata.append(meta);all_rows.extend(rr)
    if len(metadata)!=args.shards or set(m["shard"] for m in metadata)!=set(range(args.shards)):
        raise AssertionError("Incomplete shards")
    for field in ("source_manifest_sha256","training_candidate_sha256","diagnostic_policy_sha256","binary_sha256"):
        if len({json.dumps(m[field],sort_keys=True) for m in metadata})!=1:
            raise AssertionError("Inconsistent model or binary versions")
    n_sources=len({r["sha256"] for r in all_rows})
    if sum(len(m["sources"]) for m in metadata)!=n_sources or n_sources!=metadata[0]["source_count_total"]:
        raise AssertionError("Holdout source count mismatch")
    if len({r["family"] for r in all_rows})<10:
        raise AssertionError("Insufficient families")
    totals={}
    for arm in ARMS:
        subset=[r for r in all_rows if r["arm"]==arm]
        totals[arm]={
            "trials":len(subset),
            "verified":sum(r["accepted"] for r in subset),
            "SAT":sum(r["accepted"] and r["status"]=="SAT" for r in subset),
            "UNSAT":sum(r["accepted"] and r["status"]=="UNSAT" for r in subset),
            "solved_sources":len({r["sha256"] for r in subset if r["accepted"]}),
            "PAR2_s":sum(r["PAR2"] for r in subset),
            "solve_s_sum":sum(r["solve_s"] for r in subset),
            "routing_s_sum":sum(r.get("routing_s",0.0) for r in subset),
        }
    proposed_actions=collections.Counter(r["effective_arm"] for r in all_rows if r["arm"]=="GLOBAL_PROPOSED")
    comparison={arm:interval(all_rows,arm) for arm in ARMS if arm!="LOCAL"}
    informative=sum(any(r["accepted"] for r in all_rows if r["sha256"]==sha) for sha in
                    {r["sha256"] for r in all_rows})
    improvement=comparison["GLOBAL_PROPOSED"]
    gate=(improvement["reduction"]>=.05 and improvement["lower95"]>0 and
          totals["GLOBAL_PROPOSED"]["verified"]>=totals["LOCAL"]["verified"] and
          proposed_actions.get("X5",0)>=10)
    result={"status":"COMPLETE","protocol":"DRNAS-LOCAL-GLOBAL-REAL-v1",
            "data":"480-original MATERIAL2 retrospective, ONLY 103 sealed holdout CNFs",
            "source_run":metadata[0]["source_run"],
            "original_sources":n_sources,"family_units":len({r["family"] for r in all_rows}),
            "informative_sources":informative,
            "cap_s":CAP,"repeats":REPEATS,"arms":totals,"global_switches":dict(proposed_actions),
            "paired_vs_local":comparison,
            "diagnostic_passes_exploratory_5pct":bool(gate),
            "promoted":False,"learning_enabled":False,
            "limits":["Global policy trained on prior sources but not accepted by family CV",
                      "Unapproved policy enabled for DIAGNOSTIC only",
                      "No learned clause transfer across CNFs",
                      "One core, same binary, same CNFs, verified original SAT and UNSAT",
                      "Family-cluster bootstrap; no production policy change",
                      "This holdout is now evaluated, never use it to tune this policy"] }
    dump(args.out,result)
    print("LOCAL_GLOBAL_FINAL",json.dumps({
        "status":result["status"],"original_sources":n_sources,
        "informative_sources":informative,"global_switches":result["global_switches"],
        "arms":totals,"paired_vs_local":comparison,
        "exploratory_gate":gate,"promoted":False},sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=("bench","report"))
    p.add_argument("--material",type=Path)
    p.add_argument("--candidate",type=Path)
    p.add_argument("--source-run",default="43405148962")
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--root",type=Path)
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--shards",type=int,default=4)
    a=p.parse_args()
    if a.command=="bench":
        if a.shards<1 or not 0<=a.shard<a.shards:
            p.error("invalid shard")
        if not a.material or not a.candidate:p.error("missing frozen material/model")
        test_shard(a)
    else:
        if not a.root:p.error("missing benchmark shards")
        report(a)

if __name__=="__main__":
    main()
