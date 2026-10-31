#!/usr/bin/env python3
"""DRNAS V10.3: PRE-REGISTERED structural routing, external 2026 evaluation.

TRAINING: 18 already studied CNFs from completed 216-run mini benchmark.
EVALUATION: size-bounded, SHA-verified official 2026 CNFs disjoint from those
18 and pinned V10 cases. No evaluation performance is fed into the router.
The router is a counterfactual paired replay, NOT an integrated solver binary.
"""
import argparse, csv, hashlib, json, math, os, random, statistics, time
from collections import defaultdict
from pathlib import Path
import official_shortlong_select as source
import official_2026_mini_sim as mini

PROTOCOL="DRNAS-v103-locked-router-20261031-v1"
SALT="DRNAS-v103-external-2026-predeclared-sample-1031"
CAP=15.0
REPS=2
SHARDS=6
TARGET=120
MIN_ACCEPT=100
MEMORY_GIB=3
MODES=("DRNAS_Legacy","DRNAS_NoLate","Kissat404","CaDiCaL301")
ROUTABLE=("DRNAS_Legacy","DRNAS_NoLate","Kissat404")
FEATURES=("log_vars","log_clauses","clause_var","avg_width","binary_frac",
          "ternary_frac","four_frac","polarity_imbalance","majority_coverage")
mini.CAP=CAP
mini.MEMORY_GIB=MEMORY_GIB
source.RAW_CAP=96*1024*1024
source.CNF_CAP=96*1024*1024
source.VARIABLE_CAP=1000000
source.CLAUSE_CAP=4000000

def check(cond,msg):
    if not cond: raise RuntimeError(msg)

def save(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")

def sha_bytes(data):
    return hashlib.sha256(data).hexdigest()

def load(path):
    return json.loads(Path(path).read_text())

def objective(obs):
    return 2*CAP if obs["status"]=="TIMEOUT" else float(obs["seconds"])

def train_model(report):
    check(report["total_attempts"]==216,"Training mini report incomplete")
    raw=report["all_rows"]
    cases=report["source"]["cases"]
    check(len(cases)==18 and len(raw)==216,"Training dimensions incorrect")
    items=[]
    for c in cases:
        row={"sha256":c["sha256"],"features":{k:float(c["features"][k]) for k in FEATURES}}
        costs={}
        for mode in ROUTABLE:
            found=[r for r in raw if r["cnf_id"]==c["id"] and r["mode"]==mode]
            check(len(found)==2 and {r["repetition"] for r in found}=={0,1},"Training repetitions wrong")
            check(all(r["status"] in ("SAT","UNSAT","TIMEOUT") and not r["error"] for r in found),
                  "Invalid training outcome")
            # Old 30-second cap is intentionally preserved for training costs.
            costs[mode]=sum(60 if r["status"]=="TIMEOUT" else r["seconds"] for r in found)/2
        row["costs"]=costs
        items.append(row)
    check(len({x["sha256"] for x in items})==18,"Duplicate training inputs")
    scale={k:max(max(x["features"][k] for x in items)-min(x["features"][k] for x in items),0.001)
           for k in FEATURES}
    return {"train":items,"scale":scale,"k":5,"minimum_predicted_gain_s":3.0,
            "minimum_support":3,"fallback":"DRNAS_Legacy",
            "training_cap_s":30,"evaluation_cap_s":CAP}

def route(model,features):
    def d(row):
        return math.sqrt(sum(((float(features[k])-row["features"][k])/model["scale"][k])**2 for k in FEATURES))
    near=sorted(model["train"],key=lambda row:(d(row),row["sha256"]))[:model["k"]]
    weights=[1/(0.05+d(x)) for x in near]
    estimates={m:sum(w*x["costs"][m] for w,x in zip(weights,near))/sum(weights) for m in ROUTABLE}
    prefer=min(ROUTABLE,key=lambda m:(estimates[m],m))
    wins=sum(1 for x in near if x["costs"][prefer] + 1e-9 < x["costs"]["DRNAS_Legacy"])
    if prefer=="DRNAS_Legacy" or wins<model["minimum_support"] or (
          estimates["DRNAS_Legacy"]-estimates[prefer] < model["minimum_predicted_gain_s"]):
        prefer="DRNAS_Legacy"
    return prefer

def selftest():
    features={k:0.4 for k in FEATURES}
    train=[]
    for i in range(6):
        train.append({"sha256":f"{i:064x}","features":{k:0.4+i*.01 for k in FEATURES},
                      "costs":{"DRNAS_Legacy":40,"DRNAS_NoLate":35,"Kissat404":5}})
    model={"train":train,"scale":{k:1 for k in FEATURES},
           "k":5,"minimum_predicted_gain_s":3.0,"minimum_support":3,
           "fallback":"DRNAS_Legacy"}
    check(route(model,features)=="Kissat404","Router should choose Kissat")
    model["minimum_support"]=6
    check(route(model,features)=="DRNAS_Legacy","Router must fallback")
    print("V103_SELFTEST_PASS")

def freeze(args):
    import official_shortlong_select as sel
    report=load(args.train)
    prior=load(args.prior)
    check(len(prior["cases"])==18,"Old 18 manifest not found")
    model=train_model(report)
    old_ids={c["id"] for c in prior["cases"]}
    old_shas={c["sha256"] for c in prior["cases"]}
    check(old_shas=={x["sha256"] for x in model["train"]},"Training source mismatch")
    if args.v100:
        old_ids.update(c["id"] for c in load(args.v100)["cases"])
    old_ids.update(source.EXCLUDED)
    check(sha_bytes(Path(args.scores).read_bytes())!="" ,"Missing score table")
    with open(args.scores,newline="",encoding="utf-8") as f:
        rows=list(csv.DictReader(f))
    eligible=[r for r in rows if r["solverid"]=="biere_cadical3[main]"
              and r["status"] in ("sat-verified","unsat-verified")
              and r["instanceid"] not in old_ids]
    # No DRNAS performance used to choose new cases. Official baseline time
    # is used ONLY to spread difficulty buckets, never given to the model.
    buckets=defaultdict(list)
    for r in eligible:
        sec=float(r["runtime"])
        difficulty="fast" if sec<10 else "mid" if sec<180 else "hard"
        label="SAT" if r["status"]=="sat-verified" else "UNSAT"
        buckets[label+"_"+difficulty].append(r)
    for label in buckets:
        buckets[label].sort(key=lambda r:sha_bytes((SALT+"/"+r["instanceid"]).encode()))
    keys=sorted(buckets)
    attempts=[];cases=[];seen=set()
    while len(cases)<TARGET and any(buckets.values()):
        for key in keys:
            if not buckets[key] or len(cases)>=TARGET:continue
            r=buckets[key].pop(0);rid=r["instanceid"]
            if rid in seen: continue
            seen.add(rid)
            try:
                details=source.download_and_features(rid)
                check(details["sha256"] not in old_shas,"Previously seen training SHA")
                decision=route(model,details["features"])
                case={**details,"official_label":"SAT" if r["status"]=="sat-verified" else "UNSAT",
                      "cohort":key,"locked_choice":decision}
                cases.append(case)
                print("V103_FREEZE",len(cases),rid,key,decision,flush=True)
            except Exception as e:
                attempts.append({"id":rid,"cohort":key,"reason":str(e)[:140]})
                print("V103_SKIP",rid,str(e)[:120],flush=True)
    check(len(cases)>=MIN_ACCEPT,f"Insufficient verified eligible new inputs: {len(cases)}/{MIN_ACCEPT}")
    check(len({c["sha256"] for c in cases})==len(cases),"New SHA duplicate")
    check(not ({c["id"] for c in cases}&old_ids),"Old formula leaked")
    m={"protocol":PROTOCOL,"target_cases":TARGET,"accepted_cases":len(cases),
       "training_run_id":41248293940,"train_model":model,"modes":list(MODES),
       "repetitions":REPS,"cap_seconds":CAP,"memory_limit_gib":MEMORY_GIB,
       "shards":SHARDS,"cases":cases,"excluded_prior_ids":sorted(old_ids),
       "attempts_rejected":attempts,
       "scope":["Unofficial; 2026 SAT competition CNFs, not official result",
                "Input IDs disjoint from pinned mini and V10 manifests, not guaranteed unseen in every historical DRNAS experiment",
                "Locked structural router; prior 18 cases trained with 30-second cost, evaluation has 15-second cap",
                "Router is a counterfactual matched-policy analysis, not a running integrated executable",
                "No certificate for SAT models/UNSAT proofs, official labels only",
                "Any 2026 official baseline times used for sampling buckets only",
                "No model selection or threshold tuning after these data are measured"]}
    save(args.out,m)
    print("V103_FREEZE_PASS",len(cases),"targets",TARGET,flush=True)

def run(args):
    manifest=load(args.manifest)
    check(manifest["protocol"]==PROTOCOL,"Protocol mismatch")
    check(0<=args.shard<SHARDS,"Invalid shard")
    subset=[c for idx,c in enumerate(manifest["cases"]) if idx%SHARDS==args.shard]
    check(len(subset)>0,"No cases in shard")
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    available=os.sched_getaffinity(0)
    os.sched_setaffinity(0,{min(available)})
    cpuinfo=Path("/proc/cpuinfo").read_text()
    model=next((x.split(":",1)[1].strip() for x in cpuinfo.splitlines()
               if x.startswith("model name")),"unknown")
    save(out/"meta.json",{"protocol":PROTOCOL,"shard":args.shard,
         "ids":[c["id"] for c in subset],"cpu":model,"cap_seconds":CAP})
    rows=[]
    for case in subset:
        path=out/(case["id"]+".cnf")
        actual=source.download_and_features(case["id"],path)
        check(actual["sha256"]==case["sha256"] and actual["features"]==case["features"],
              "Frozen inputs changed or structural feature mismatch")
        check(route(manifest["train_model"],actual["features"])==case["locked_choice"],
              "Frozen decision changed")
        for rep in range(REPS):
            seed=(1032026+1009*rep+int(case["sha256"][:8],16))%(2**32)
            modes=list(MODES)
            random.Random(seed^103).shuffle(modes)
            for mode in modes:
                obs=mini.trial(mode,path,seed,args.drnas,args.kissat,case["official_label"])
                row={"id":case["id"],"sha256":case["sha256"],
                     "mode":mode,"cohort":case["cohort"],"repetition":rep,
                     "locked_choice":case["locked_choice"],**obs}
                rows.append(row)
                save(out/"rows.json",rows)
                print("V103_TRIAL",case["id"][:12],rep,mode,obs["status"],
                      f'{obs["seconds"]:.3f}',flush=True)
                check(obs["status"]!="ERROR","Trial error: "+obs["error"])
        path.unlink(missing_ok=True)
    check(len(rows)==len(subset)*len(MODES)*REPS,"Incomplete shard")
    print("V103_SHARD_PASS",args.shard,len(rows),flush=True)

def audit(args):
    m=load(args.manifest)
    check(m["protocol"]==PROTOCOL,"Wrong protocol")
    cases={x["id"]:x for x in m["cases"]}
    check(len(cases)==m["accepted_cases"]>=MIN_ACCEPT,"Invalid case count")
    all_rows=[];cores=set()
    for shard in range(SHARDS):
        folder=Path(args.combined)/f"v103-shard-{shard}"/"results"
        meta=load(folder/"meta.json")
        expected=[c["id"] for idx,c in enumerate(m["cases"]) if idx%SHARDS==shard]
        check(meta["ids"]==expected and meta["shard"]==shard,"Shard mismatch")
        cores.add(meta["cpu"])
        rows=load(folder/"rows.json")
        check(len(rows)==len(expected)*len(MODES)*REPS,"Missing attempt rows")
        all_rows.extend(rows)
    check(len(all_rows)==len(cases)*len(MODES)*REPS,"Incorrect row total")
    keyed={}
    for row in all_rows:
        c=cases[row["id"]]
        check(row["sha256"]==c["sha256"] and row["cohort"]==c["cohort"],
              "Incorrect row provenance")
        check(row["locked_choice"]==c["locked_choice"],"Decision mismatch")
        check(row["mode"] in MODES and row["repetition"] in range(REPS),"Invalid method/rep")
        check(row["status"] in ("SAT","UNSAT","TIMEOUT") and not row["error"],"Solver error")
        check(row["status"]=="TIMEOUT" or row["status"]==c["official_label"],"Wrong label")
        check(0<=row["seconds"]<=CAP+0.2,"Implausible timing")
        k=(row["id"],row["repetition"],row["mode"])
        check(k not in keyed,"Duplicate attempt")
        keyed[k]=row
    def aggregate(rows):
        return {"solved":sum(r["status"]!="TIMEOUT" for r in rows),
                "total":len(rows),
                "PAR2_s":round(statistics.mean(objective(r) for r in rows),5)}
    overall={}
    for mode in MODES:
        overall[mode]=aggregate([r for r in all_rows if r["mode"]==mode])
    routed=[]
    for case in m["cases"]:
        for rep in range(REPS):
            routed.append(keyed[(case["id"],rep,case["locked_choice"])])
    overall["V103_LockedRouter"]=aggregate(routed)
    by_cohort={}
    for cohort in sorted({c["cohort"] for c in m["cases"]}):
        ids={c["id"] for c in m["cases"] if c["cohort"]==cohort}
        block={}
        for mode in MODES:
            block[mode]=aggregate([r for r in all_rows if r["id"] in ids and r["mode"]==mode])
        block["V103_LockedRouter"]=aggregate([r for r in routed if r["id"] in ids])
        by_cohort[cohort]=block
    report={"protocol":PROTOCOL,"cases":len(cases),"attempts":len(all_rows),
            "cpu_models":sorted(cores),"overall":overall,"by_cohort":by_cohort,
            "router_choices":{m:sum(c["locked_choice"]==m for c in m_cases)
                              for m in ROUTABLE for m_cases in [list(cases.values())]},
            "training_cases":len(m["train_model"]["train"]),
            "official_rank":None}
    save(args.out,report)
    lines=["# DRNAS V10.3 — prospective matched router audit","",
      "**NOT an official 2026 SAT competition rank or world record.**",
      f'{len(cases)} newly selected CNFs, {len(all_rows)} matched solver attempts.',
      "15-second timeout, 3 GiB, pinned 1 core; official track uses different conditions.",
      "Router decisions frozen before evaluation, trained on 18 old cases.",
      "Routing is simulated from paired solver trials, not an integrated executable.",
      "This excludes the pinned training formulas but cannot prove globally unseen cases.",
      "Official SAT/UNSAT labels checked; proof certificates not independently verified.","",
      "| Method | Solved | PAR2 s (lower better) |","|---|---:|---:|"]
    for mode,s in sorted(overall.items(),key=lambda x:x[1]["PAR2_s"]):
        lines.append(f'| {mode} | {s["solved"]}/{s["total"]} | {s["PAR2_s"]:.5f} |')
    lines.extend(["","## By source difficulty cohort"])
    for cohort,vals in by_cohort.items():
        lines.extend(["",f'### {cohort}',"| Method | Solved | PAR2 s |","|---|---:|---:|"])
        for mode,s in sorted(vals.items(),key=lambda x:x[1]["PAR2_s"]):
            lines.append(f'| {mode} | {s["solved"]}/{s["total"]} | {s["PAR2_s"]:.5f} |')
    Path(args.md).write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)
    print("V103_AUDIT_PASS",len(cases),len(all_rows),flush=True)

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("selftest")
    f=sub.add_parser("freeze")
    for key in ("train","prior","scores","out"):f.add_argument("--"+key,required=True)
    f.add_argument("--v100")
    r=sub.add_parser("run")
    for key in ("manifest","drnas","kissat","out"):r.add_argument("--"+key,required=True)
    r.add_argument("--shard",type=int,required=True)
    a=sub.add_parser("audit")
    for key in ("manifest","combined","out","md"):a.add_argument("--"+key,required=True)
    args=p.parse_args()
    {"selftest":lambda:selftest(),"freeze":lambda:freeze(args),
     "run":lambda:run(args),"audit":lambda:audit(args)}[args.cmd]()

if __name__=="__main__":main()
