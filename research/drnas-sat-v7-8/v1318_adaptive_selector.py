#!/usr/bin/env python3
"""V13.18: train one-split SAT policy on prior V13.17 CNFs, test new 30 CNFs.

Train data are 30 SHA-frozen V13.17 formulas with paired 20s measurements.
No holdout label, solver runtime or ID is passed to the learned selector.
A single conservative tree split chooses Kissat, DRNAS Legacy, or the
unchanged V13.15 selective XOR. Selection latency counts against 20s cap.
"""
import argparse,collections,hashlib,json,os,random,statistics,time
from pathlib import Path
import official_shortlong_select as source
import v1315_selective_xor as fixed
import v1314_timed_ab as old

PROTOCOL="DRNAS-V1318-LEARNED-SELECTOR-30-BLIND-20261101-v1"
COHORT_PROTOCOL="DRNAS-V1318-UNSEEN30-LEARNED-SELECTOR-20261101-v1"
TRAIN_PROTOCOL="DRNAS-V1317-FRESH30-CAP20-V1315-FIXED-20261101-v1"
TRAIN_COHORT="DRNAS-V1317-NEW30-SC2024-FIXED20-V1315-20261101-v1"
ACTIONS=("Kissat404","DRNAS_Legacy","V1315_SELECTIVE_XOR")
MODES=ACTIONS+("V1318_ADAPTIVE",)
CAP=20.0
REPS=2
SHARDS=10
MIN_LEAF=8
MIN_GAIN=0.50
OTHER_MODE_PENALTY=0.20
SPLIT_PENALTY=0.10
FEATURES=("cnf_bytes","variables","clauses","clauses_per_variable")
V1315_BLOB="2b1b14d9d58459e350a0906d356c5003a6105d64"
source.RAW_CAP=96*1024**2
source.CNF_CAP=64*1024**2
source.VARIABLE_CAP=500000
source.CLAUSE_CAP=1000000

def check(x,msg):
    if not x:raise RuntimeError(msg)
def load(p):return json.loads(Path(p).read_text())
def save(p,x):
    path=Path(p);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(x,indent=2,sort_keys=True)+"\n")
def sha(p):
    h=hashlib.sha256()
    with Path(p).open("rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()
def configure():
    fixed.CAP=CAP;old.CAP=CAP
    check(fixed.GATE_MAX_BYTES==96*1024 and fixed.GATE_MIN_XOR==16,
          "V13.15 fixed gate drift")
    check(fixed.MODES==("Kissat404","DRNAS_Legacy","V1312_XOR_Kissat","V1315_SELECTIVE_XOR"),"V13.15 modes changed")

def features_from_metadata(c):
    n=int(c["variables"]);m=int(c["clauses"])
    return {"cnf_bytes":int(c["cnf_bytes"]),"variables":n,"clauses":m,
            "clauses_per_variable":round(m/max(1,n),9)}

def features_from_path(p):
    p=Path(p);size=p.stat().st_size
    with p.open("rb") as f:
        for i,line in enumerate(f):
            check(i<5000,"DIMACS header missing")
            tokens=line.strip().split()
            if tokens and tokens[0]==b"p":
                check(len(tokens)>=4 and tokens[1]==b"cnf","bad DIMACS header")
                n=int(tokens[2]);m=int(tokens[3])
                check(0<n<=500000 and 0<=m<=1000000,"DIMACS limits")
                return {"cnf_bytes":size,"variables":n,"clauses":m,
                        "clauses_per_variable":round(m/max(1,n),9)}
    raise RuntimeError("DIMACS p cnf missing")

def choose(model,feats):
    r=model["rule"]
    if r["feature"] is None:return r["left_mode"]
    return r["left_mode"] if feats[r["feature"]]<=r["threshold"] else r["right_mode"]

def learn(features,costs):
    ids=sorted(features)
    check(len(ids)==30 and all(set(costs[i])==set(ACTIONS) for i in ids),
          "training size or methods differ")
    baseline=statistics.mean(costs[i]["Kissat404"] for i in ids)
    best={"rule":{"feature":None,"threshold":None,
                  "left_mode":"Kissat404","right_mode":"Kissat404"},
          "raw_par2":baseline,"objective":baseline,"leaf_counts":[30,0]}
    candidates=0
    for feature in FEATURES:
        ids_sorted=sorted(ids,key=lambda i:(features[i][feature],i))
        for pivot in range(MIN_LEAF,31-MIN_LEAF):
            a=features[ids_sorted[pivot-1]][feature]
            b=features[ids_sorted[pivot]][feature]
            if a>=b:continue
            left=ids_sorted[:pivot];right=ids_sorted[pivot:]
            for mleft in ACTIONS:
                for mright in ACTIONS:
                    if mleft==mright:continue
                    raw=(sum(costs[i][mleft] for i in left)+
                         sum(costs[i][mright] for i in right))/30
                    penalty=OTHER_MODE_PENALTY*(
                         (len(left) if mleft!="Kissat404" else 0)+
                         (len(right) if mright!="Kissat404" else 0))/30
                    objective=raw+penalty+SPLIT_PENALTY
                    candidates+=1
                    if objective+1e-10<best["objective"] and baseline-raw>=MIN_GAIN:
                        best={"rule":{"feature":feature,"threshold":(a+b)/2,
                                      "left_mode":mleft,"right_mode":mright},
                              "raw_par2":raw,"objective":objective,
                              "leaf_counts":[len(left),len(right)]}
    return best,baseline,candidates

def train(a):
    configure()
    m=load(a.manifest);audit=load(a.audit)
    check(m["holdout_protocol"]==TRAIN_COHORT and len(m["cases"])==30,
          "bad training manifest")
    check(audit["protocol"]==TRAIN_PROTOCOL and audit["attempts"]==240 and
          audit["timeout_s"]==20.0,"wrong V13.17 audit")
    cases={c["id"]:c for c in m["cases"]}
    feats={i:features_from_metadata(c) for i,c in cases.items()}
    readings=collections.defaultdict(list)
    for r in audit["trials"]:
        if r["mode"] not in ACTIONS:continue
        check(r["id"] in cases and
              r["sha256"]==cases[r["id"]]["sha256"],"train SHA mismatch")
        check(r["status"] in ("SAT","UNSAT","TIMEOUT"),"bad outcome")
        readings[(r["id"],r["mode"])].append(
            40.0 if r["status"]=="TIMEOUT" else float(r["wall_s"]))
    costs={}
    for i in cases:
        costs[i]={}
        for mode in ACTIONS:
            obs=readings[(i,mode)]
            check(len(obs)==2,"missing paired training measurements")
            costs[i][mode]=statistics.mean(obs)
    rule,baseline,candidates=learn(feats,costs)
    model={"protocol":PROTOCOL,"rule":rule["rule"],
       "training_cnfs":30,"training_reps":2,
       "trained_at_cap_s":CAP,"par2_timeout_cost_s":40,
       "training_kissat_PAR2_s":round(baseline,6),
       "training_rule_PAR2_s":round(rule["raw_par2"],6),
       "training_gain_s":round(baseline-rule["raw_par2"],6),
       "leaf_counts":rule["leaf_counts"],
       "candidates_checked":candidates,
       "min_leaf":MIN_LEAF,"min_training_gain_s":MIN_GAIN,
       "v1317_manifest_sha256":sha(a.manifest),
       "v1317_audit_sha256":sha(a.audit),
       "v1315_blob_sha":V1315_BLOB,
       "features":list(FEATURES),"no_label_routing":True,
       "caveat":"Rule fit on only 30 earlier formula results, not tuned on V13.18 holdout."}
    save(a.out,model)
    print("V1318_TRAIN_PASS",json.dumps(model,sort_keys=True),flush=True)

def verify_model(model):
    check(model["protocol"]==PROTOCOL and model["training_cnfs"]==30 and
          model["trained_at_cap_s"]==20.0 and
          model["v1315_blob_sha"]==V1315_BLOB and
          model["no_label_routing"] and model["features"]==list(FEATURES),
          "unfrozen or invalid model")
    r=model["rule"]
    check(r["left_mode"] in ACTIONS and r["right_mode"] in ACTIONS and
          (r["feature"] is None or r["feature"] in FEATURES),
          "invalid rule")

def selftest():
    configure()
    features={str(i):{"cnf_bytes":100*i,"variables":i+1,"clauses":i+2,
            "clauses_per_variable":(i+2)/(i+1)} for i in range(30)}
    costs={str(i):{"Kissat404":20,
            "DRNAS_Legacy":1 if i<15 else 35,
            "V1315_SELECTIVE_XOR":35 if i<15 else 1} for i in range(30)}
    rule,baseline,n=learn(features,costs)
    check(n>0 and rule["rule"]["feature"] is not None,
          "training failed to learn obvious split")
    check(choose({"rule":rule["rule"]},features["0"])=="DRNAS_Legacy" and
          choose({"rule":rule["rule"]},features["29"])=="V1315_SELECTIVE_XOR",
          "learning mislabeled synthetic data")
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/"test.cnf"
        p.write_bytes(b"c comment\np cnf 2 1\n1 -2 0\n")
        f=features_from_path(p)
        check(f["variables"]==2 and f["clauses"]==1,"DIMACS header fail")
    print("V1318_SELFTEST_PASS learned split and feature extraction",flush=True)

def trial(mode,p,seed,drnas,kissat,official,model):
    if mode!="V1318_ADAPTIVE":
        q=fixed.trial(mode,p,seed,drnas,kissat,official)
        q["selected_mode"]=mode;q["feature_time_s"]=0.0
        return q
    started=time.monotonic()
    try:
        feats=features_from_path(p)
        chosen=choose(model,feats)
        elapsed=time.monotonic()-started
        remaining=CAP-elapsed
        if remaining<=0.001:
            q={"status":"TIMEOUT","wall_s":CAP,"probe_wall_s":0,
               "reason":"selection_timeout","gate":None,
               "certified_contradictions":0,"error":""}
        else:
            fixed.CAP=remaining;old.CAP=remaining
            try:q=fixed.trial(chosen,p,seed,drnas,kissat,official)
            finally:fixed.CAP=CAP;old.CAP=CAP
            total=time.monotonic()-started
            q["wall_s"]=round(min(total,CAP),6)
            if total>CAP+.02:q["status"]="TIMEOUT"
        q["selected_mode"]=chosen
        q["feature_time_s"]=round(elapsed,6)
        return q
    except Exception as exc:
        fixed.CAP=CAP;old.CAP=CAP
        return {"status":"ERROR","wall_s":round(min(time.monotonic()-started,CAP),6),
                "probe_wall_s":0.0,"reason":"selector_error","gate":None,
                "certified_contradictions":0,"error":str(exc)[:220],
                "selected_mode":None,"feature_time_s":0.0}

def run(a):
    configure()
    m=load(a.manifest);model=load(a.model)
    fixed.prev.validate_manifest(m);verify_model(model)
    check(m["holdout_protocol"]==COHORT_PROTOCOL and 0<=a.shard<SHARDS,
          "wrong blind input")
    subset=m["cases"][a.shard::SHARDS]
    check(len(subset)==3,"incomplete test shard")
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    cpu=next((l.split(":",1)[1].strip() for l in
              Path("/proc/cpuinfo").read_text().splitlines()
              if l.startswith("model name")),"unknown")
    save(out/"meta.json",{"protocol":PROTOCOL,"shard":a.shard,
         "cases_sha256":[c["sha256"] for c in subset],
         "model_sha256":sha(a.model),"model_rule":model["rule"],
         "cpu":cpu,"cpu_affinity":len(os.sched_getaffinity(0)),
         "binaries_sha256":{"kissat":sha(a.kissat),"drnas":sha(a.drnas)},
         "script_sha256":sha(__file__),"fixed_v1315_sha256":sha(fixed.__file__),
         "cap":CAP,"repetitions":REPS})
    rows=[]
    for case in subset:
        p=out/(case["id"]+".cnf")
        got=source.download_and_features(case["id"],p)
        check(got["sha256"]==case["sha256"] and
              got["features"]==case["features"],"CNF SHA/features mismatch")
        check(features_from_path(p)==features_from_metadata(case),
              "training vs runtime feature drift")
        for rep in range(REPS):
            seed=(20241318+104729*rep+int(case["sha256"][:8],16))%(2**32)
            order=list(MODES);random.Random(seed^181818).shuffle(order)
            for mode in order:
                q=trial(mode,p,seed,a.drnas,a.kissat,case["official_label"],model)
                rows.append({"id":case["id"],"sha256":case["sha256"],
                    "label":case["official_label"],"repetition":rep,
                    "mode":mode,"seed":seed,**q})
                save(out/"rows.json",rows)
                print("V1318_TRIAL",a.shard,case["id"][:12],rep,
                      mode,q["status"],q["wall_s"],"choice",q["selected_mode"],flush=True)
                check(q["status"]!="ERROR","fail closed: "+q["error"])
        p.unlink(missing_ok=True)
    check(len(rows)==3*REPS*len(MODES),"incomplete shard")
    print("V1318_SHARD_PASS",a.shard,len(rows),flush=True)

def audit(a):
    m=load(a.manifest);model=load(a.model);train_m=load(a.train_manifest)
    fixed.prev.validate_manifest(m);verify_model(model)
    check(m["holdout_protocol"]==COHORT_PROTOCOL and
          train_m["holdout_protocol"]==TRAIN_COHORT and
          model["v1317_manifest_sha256"]==sha(a.train_manifest),
          "training/final manifests mismatched")
    check(not {c["sha256"] for c in m["cases"]}&
          {c["sha256"] for c in train_m["cases"]} and
          not {c["id"] for c in m["cases"]}&
          {c["id"] for c in train_m["cases"]},"training leakage")
    allrows=[];signatures=set();cpus=set()
    for shard in range(SHARDS):
        folder=Path(a.combined)/f"v1318-shard-{shard}"
        meta=load(folder/"meta.json");r=load(folder/"rows.json")
        check(meta["protocol"]==PROTOCOL and meta["shard"]==shard and
              meta["cases_sha256"]==
                  [c["sha256"] for c in m["cases"][shard::SHARDS]] and
              meta["model_sha256"]==sha(a.model) and
              meta["model_rule"]==model["rule"] and
              meta["cpu_affinity"]==1 and meta["cap"]==CAP and
              meta["repetitions"]==REPS,"bad shard metadata")
        signatures.add(json.dumps([meta["script_sha256"],
               meta["fixed_v1315_sha256"],meta["binaries_sha256"]],sort_keys=True))
        cpus.add(meta["cpu"])
        check(len(r)==3*REPS*len(MODES),"partial results")
        allrows.extend(r)
    check(len(signatures)==1 and len(allrows)==30*REPS*len(MODES),
          "different code/binaries or missing trials")
    cases={c["id"]:c for c in m["cases"]};seen=set();routes=collections.Counter()
    for r in allrows:
        key=r["id"],r["mode"],r["repetition"]
        check(key not in seen,"duplicate run");seen.add(key)
        c=cases[r["id"]]
        check(r["sha256"]==c["sha256"] and r["label"]==c["official_label"]
              and r["mode"] in MODES and r["repetition"] in (0,1)
              and r["status"] in ("SAT","UNSAT","TIMEOUT")
              and not r["error"] and 0<=r["wall_s"]<=CAP+.02
              and (r["status"]=="TIMEOUT" or r["status"]==c["official_label"]),
              "wrong trial data")
        if r["mode"]=="V1318_ADAPTIVE":
            check(r["selected_mode"]==choose(model,features_from_metadata(c)),
                  "model decisions not reproducible")
            routes[r["selected_mode"]]+=1
    stats={}
    for label in ("all","SAT","UNSAT"):
        sub=[r for r in allrows if label=="all" or r["label"]==label]
        stats[label]={}
        for mode in MODES:
            trials=[r for r in sub if r["mode"]==mode]
            solved=[r["wall_s"] for r in trials if r["status"]!="TIMEOUT"]
            times=[r["wall_s"] if r["status"]!="TIMEOUT" else 40.0
                   for r in trials]
            stats[label][mode]={"solved":len(solved),"attempts":len(trials),
                 "PAR2_s":round(statistics.mean(times),6),
                 "mean_solved_s":round(statistics.mean(solved),6) if solved else None,
                 "timeouts":len(trials)-len(solved)}
    report={"protocol":PROTOCOL,"model":model,"holdout_manifest_sha256":sha(a.manifest),
            "training_manifest_sha256":sha(a.train_manifest),
            "number_of_new_cnfs":30,"attempts":len(allrows),
            "timeout_cap_s":CAP,"PAR2_timeout_penalty_s":40,
            "methods":list(MODES),"stats":stats,"adaptive_routes":dict(routes),
            "cpu_models":sorted(cpus),"trials":allrows,
            "limitations":[
              "30 old 2024 CNFs used exclusively for training; 30 SHA-disjoint 2024 CNFs in test.",
              "Training one-split rule has only 30 examples; any apparent gains may reflect sampling noise.",
              "20s cutoff, 3GiB RAM, one pinned CPU core on Github Actions, not official competition conditions.",
              "Adaptive decision time and all selected solver/prepass wall time fully counted.",
              "All solver outputs checked against published labels, but full baseline solver proof certificates not independently checked.",
              "2024 competition sample selection and file-size caps are not representative of global SAT instances."
            ]}
    save(a.json,report)
    lines=["# DRNAS V13.18: learned method routing, strict 30-CNF holdout","",
           "Training: previous SHA-frozen V13.17 30 CNFs; testing: 30 distinct fresh 2024 CNFs.",
           "30 holdout CNFs x 4 policies x 2 repetitions = 240 trials.",
           "20 s wall cap; 40 s PAR2 penalty; CPU affinity 1 core; 3 GiB RAM.",
           "", "Locked rule: "+json.dumps(model["rule"],sort_keys=True),"",
           "| Cohort | Policy | Solved | PAR2 s | Mean solved s |",
           "|---|---|---:|---:|---:|"]
    for label in ("all","SAT","UNSAT"):
        for mode in MODES:
            x=stats[label][mode]
            mean="n/a" if x["mean_solved_s"] is None else f'{x["mean_solved_s"]:.4f}'
            lines.append(f'| {label} | {mode} | {x["solved"]}/{x["attempts"]} | '
                         f'{x["PAR2_s"]:.4f} | {mean} |')
    lines.extend(["","## Adaptive choices"])
    lines.extend([f"- {k}: {routes[k]}/60 trials" for k in ACTIONS])
    lines.extend(["","## Limitations"]+["- "+q for q in report["limitations"]])
    Path(a.md).write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)
    print("V1318_AUDIT_PASS",json.dumps(stats["all"],sort_keys=True),
          "routes",json.dumps(dict(routes),sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="action",required=True)
    sub.add_parser("selftest")
    x=sub.add_parser("train")
    for key in ("manifest","audit","out"):x.add_argument("--"+key,required=True)
    x=sub.add_parser("run")
    for key in ("manifest","model","kissat","drnas","out"):x.add_argument("--"+key,required=True)
    x.add_argument("--shard",required=True,type=int)
    x=sub.add_parser("audit")
    for key in ("manifest","model","combined","json","md"):x.add_argument("--"+key,required=True)
    x.add_argument("--train-manifest",dest="train_manifest",required=True)
    a=p.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="train":train(a)
    elif a.action=="run":run(a)
    else:audit(a)

if __name__=="__main__":main()
