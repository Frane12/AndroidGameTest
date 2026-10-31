#!/usr/bin/env python3
"""DRNAS v9.5: preregistered CNF-structure selector and prospective SAT test.
All training uses exactly the prior 18+12 published project trials.
New official CNFs and model decisions are frozen before new solver timings.
No SAT/UNSAT label, filename, hash, reference solver time, or run outcomes enter routing.
"""
import argparse,csv,hashlib,json,math,os,random,statistics,subprocess,time
from collections import Counter,defaultdict
from pathlib import Path
from official_shortlong_select import download_and_features,REV,SCORES_GIT_BLOB
import official_shortlong_select as official_source
# v9.5 experiment only: permit moderate files beyond the earlier 48MiB screening.
official_source.CNF_CAP=96*1024*1024
official_source.RAW_CAP=96*1024*1024
official_source.VARIABLE_CAP=1000000
official_source.CLAUSE_CAP=4000000
BASE=("ca_plain","orig_v76","orig_v76_plain","v92_sparse")
MODES=BASE+("v94_cautious","v95_structural")
FEATURES=("log_vars","log_clauses","clause_var","avg_width",
          "binary_frac","ternary_frac","four_frac","polarity_imbalance",
          "majority_coverage","binary_x_majority","binary_x_imbalance",
          "non_short_frac","density_x_imbalance")
SALT="DRNAS-v95-official-2026-24-new-20261031-v1"
QUOTAS={a+"_"+b:4 for a in ("sat","unsat") for b in ("fast","mid","slow")}
CAP=15.0
REPS=3

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def dump(path,obj):
    Path(path).write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def features(src):
    f={key:float(src[key]) for key in FEATURES[:9]}
    f["binary_x_majority"]=f["binary_frac"]*f["majority_coverage"]
    f["binary_x_imbalance"]=f["binary_frac"]*f["polarity_imbalance"]
    f["non_short_frac"]=max(0.,1.-f["binary_frac"]-f["ternary_frac"]-f["four_frac"])
    f["density_x_imbalance"]=math.log1p(f["clause_var"])*f["polarity_imbalance"]
    return f
def read_training(old_path,new_path):
    old=json.loads(Path(old_path).read_text())
    new=json.loads(Path(new_path).read_text())
    assert len(old["per_case"])==18 and len(new["per_case"])==12
    rows=[]
    for x in old["per_case"]:
        cost={m:float(x["PAR2_by_cap"][m]["15.0"]) for m in BASE}
        rows.append({"id":x["id"],"features":features(x["features"]),
                     "cost":cost,"origin":"original18"})
    for x in new["per_case"]:
        rows.append({"id":x["case"],"features":features(x["features"]),
                     "cost":{m:float(x["cost"][m]) for m in BASE},
                     "origin":"new12"})
    assert len({x["id"] for x in rows})==30
    assert all(0 <= v <= 30 for row in rows for v in row["cost"].values())
    return rows
def mean_cost(rows,m):
    return statistics.mean(x["cost"][m] for x in rows)
def best_constant(rows):
    return min(BASE,key=lambda m:(mean_cost(rows,m),BASE.index(m)))
def fit_stump(rows):
    """Single feature/threshold with >=5 different CNFs per leaf."""
    constant=best_constant(rows)
    best={"kind":"constant","mode":constant}
    bestsum=sum(x["cost"][constant] for x in rows)
    for f in FEATURES:
        values=sorted(set(x["features"][f] for x in rows))
        for a,b in zip(values,values[1:]):
            threshold=(a+b)/2
            left=[x for x in rows if x["features"][f]<=threshold]
            right=[x for x in rows if x["features"][f]>threshold]
            if min(len(left),len(right))<5:continue
            ml=best_constant(left);mr=best_constant(right)
            score=sum(x["cost"][ml] for x in left)+sum(x["cost"][mr] for x in right)
            if score+1e-9<bestsum:
                bestsum=score
                best={"kind":"stump","feature":f,"threshold":threshold,
                      "left":ml,"right":mr,"training_gain_s":round(
                          sum(x["cost"][constant] for x in rows)-score,6)}
    return best
def predict(row,train,model):
    kind=model["kind"]
    if kind=="constant":return model["mode"]
    if kind=="stump":
        return model["left"] if row["features"][model["feature"]]<=model["threshold"] else model["right"]
    if kind.startswith("knn"):
        n=int(kind[3:]); f=row["features"]
        # Train-derived robust feature scales; symmetric normalized L1 distance.
        scale={k:max(.05,statistics.median(abs(x["features"][k]-
               statistics.median(z["features"][k] for z in train)) for x in train))
               for k in FEATURES}
        def dist(x):
            return sum(min(5.,abs(f[k]-x["features"][k])/scale[k]) for k in FEATURES)
        neighbors=sorted(train,key=lambda x:(dist(x),x["id"]))[:n]
        def score(m):
            return statistics.mean(x["cost"][m] for x in neighbors)
        default=best_constant(train)
        chosen=min(BASE,key=lambda m:(score(m),BASE.index(m)))
        # Nontrivial margin avoids routing on sub-millisecond noise.
        return chosen if score(default)-score(chosen) >= .5 else default
    raise ValueError("bad selector type")
def fit(rows,kind):
    if kind=="constant":return {"kind":"constant","mode":best_constant(rows)}
    if kind=="stump":return fit_stump(rows)
    if kind in ("knn3","knn5"):return {"kind":kind}
    raise ValueError(kind)
def train_cmd(args):
    rows=read_training(args.old,args.new)
    methods=("constant","stump","knn3","knn5")
    cv={}
    for kind in methods:
        costs=[];counts=0;choices=Counter()
        for i,row in enumerate(rows):
            subset=rows[:i]+rows[i+1:]
            mod=fit(subset,kind)
            choice=predict(row,subset,mod)
            choices[choice]+=1
            costs.append(row["cost"][choice])
            counts+=int(row["cost"][choice]<30.)
        cv[kind]={"mean_PAR2":statistics.mean(costs),
                  "solved_cases":counts,"choices":dict(choices)}
    default=cv["constant"]
    winner=min(methods,key=lambda k:(cv[k]["mean_PAR2"],methods.index(k)))
    # Conservative precommitted validation gate: at least 0.20s/instance
    # improvement in LOO CV AND no reduction in solved-case count.
    if winner!="constant" and (default["mean_PAR2"]-cv[winner]["mean_PAR2"]<.2
            or cv[winner]["solved_cases"]<default["solved_cases"]):
        winner="constant"
    full=fit(rows,winner)
    model={"protocol":SALT,"training_cases":30,
           "historical_source_sha256":{"original18":sha(args.old),"new12":sha(args.new)},
           "features":list(FEATURES),"candidate_CV":cv,
           "selected_family":winner,"fitted_selector":full,
           "fallback":best_constant(rows),"training":rows,
           "limitations":["Only 30 size-screened examples, no leakage from 24 prospective cases",
             "LOOCV across previously studied examples is not an independent claim",
             "Routing only among four existing CaDiCaL-based modes",
             "Python routing uses precomputed CNF features in manifest; feature extraction not part of timed run",
             "No claim of solver novelty, representative speedup or world record"]}
    dump(args.out,model)
    print("V95_TRAIN_FROZEN",winner,full,"LOOCV",cv,"sha256",sha(args.out),flush=True)
def freeze_cmd(args):
    old=json.loads(Path(args.old_manifest).read_text())
    prev=json.loads(Path(args.new_manifest).read_text())
    excluded={x["id"] for x in old["cases"]}|{x["id"] for x in prev["cases"]}
    assert len(excluded)==30
    model=json.loads(Path(args.model).read_text())
    assert model["protocol"]==SALT and model["training_cases"]==30
    with Path(args.scores).open(newline="",encoding="utf8") as f:
        records=list(csv.DictReader(f))
    baseline=[r for r in records if r["solverid"]=="biere_cadical3[main]"]
    assert len(baseline)==400
    pools=defaultdict(list)
    for x in baseline:
        ident=x["instanceid"]
        if ident in excluded or x["status"] not in ("sat-verified","unsat-verified"):continue
        sec=float(x["runtime"])
        if not (.5<=sec<=180.):continue
        grade="fast" if sec<5 else ("mid" if sec<30 else "slow")
        label="sat" if x["status"]=="sat-verified" else "unsat"
        pools[label+"_"+grade].append({"id":ident,"official_label":label.upper(),
                       "stratum":label+"_"+grade,"official_baseline_s":sec})
    def key(s):return hashlib.sha256((SALT+"/"+s).encode()).hexdigest()
    chosen=[];attempts=[];attempted=set()
    # First, try balanced strata. An exhausted stratum must not abort
    # an otherwise valid prospective cohort; fill remainder in fixed order.
    candidates=[]
    for stratum,quota in QUOTAS.items():
        ordered=sorted(pools[stratum],key=lambda x:key(stratum+"/"+x["id"]))
        candidates.extend(ordered)
        count=0
        for rec in ordered:
            if count>=quota:break
            attempted.add(rec["id"])
            try:info=download_and_features(rec["id"])
            except Exception as ex:
                attempts.append({"id":rec["id"],"accepted":False,"why":str(ex)})
                print("V95_REJECT",stratum,rec["id"],str(ex),flush=True)
                continue
            chosen.append({**rec,**info,"split":"v95_unseen"})
            attempts.append({"id":rec["id"],"accepted":True})
            count+=1
            print("V95_ACCEPT",stratum,rec["id"],info["cnf_bytes"],flush=True)
        if count<quota:
            print("V95_STRATUM_SHORTFALL",stratum,count,quota,flush=True)
    if len(chosen)<24:
        # Original SAT/UNSAT strata are public and frozen; no DRNAS outcome
        # has been measured for any candidate.
        for rec in sorted(candidates,key=lambda x:key("spill/"+x["id"])):
            if len(chosen)>=24:break
            if rec["id"] in attempted:continue
            attempted.add(rec["id"])
            try:info=download_and_features(rec["id"])
            except Exception as ex:
                attempts.append({"id":rec["id"],"accepted":False,"why":str(ex)})
                print("V95_SPILL_REJECT",rec["stratum"],rec["id"],str(ex),flush=True)
                continue
            chosen.append({**rec,**info,"split":"v95_unseen"})
            attempts.append({"id":rec["id"],"accepted":True})
            print("V95_SPILL_ACCEPT",rec["stratum"],rec["id"],info["cnf_bytes"],flush=True)
    if len(chosen)<24:
        raise RuntimeError("Insufficient 24 disjoint downloadable CNFs: "+str(len(chosen)))
    assert len(chosen)==24 and not ({x["id"] for x in chosen}&excluded)
    # Stable shuffle; four CNFs per shard.
    chosen.sort(key=lambda x:key("schedule/"+x["id"]))
    dump(args.out,{"protocol":SALT,"official_commit":REV,
        "scores_git_blob":SCORES_GIT_BLOB,"exclude_30":sorted(excluded),
        "model_sha256":sha(args.model),"quota":QUOTAS,
        "cases":chosen,"candidates":attempts,
        "warnings":["Official problems already public, so not a fully blind contest",
          "Size and public baseline time stratification affects representativeness",
          "24 new unique CNFs independent of model's 30 training cases"]})
    print("V95_FROZEN",len(chosen),"sha256",sha(args.out),flush=True)
def run_cmd(args):
    manifest=json.loads(Path(args.manifest).read_text())
    model=json.loads(Path(args.model).read_text())
    assert manifest["protocol"]==model["protocol"]==SALT
    assert manifest["model_sha256"]==sha(args.model)
    assert len(manifest["cases"])==24 and 0<=args.shard<6
    subset=manifest["cases"][args.shard*4:(args.shard+1)*4]
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    core=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{core})
    dump(out/"meta.json",{"shard":args.shard,"model_sha256":sha(args.model),
        "manifest_sha256":sha(args.manifest),"cpu_core":core,
        "cases":[x["id"] for x in subset],"repeats":REPS,"cap_s":CAP})
    fields=("id","sha256","shard","rep","mode","selected","status","wall_s","error")
    rows=[];issues=[]
    with (out/"raw.csv").open("w",newline="") as fh:
        writer=csv.DictWriter(fh,fieldnames=fields);writer.writeheader()
        for item in subset:
            ident=item["id"];cnf=out/(ident+".cnf")
            info=download_and_features(ident,cnf)
            assert info["sha256"]==item["sha256"] and info["features"]==item["features"]
            print("V95_INPUT_SHA_OK",ident,flush=True)
            static={"features":features(item["features"])}
            decision=predict(static,model["training"],model["fitted_selector"])
            assert decision in BASE
            for rep in range(REPS):
                order=list(MODES)
                random.Random(9151+int(ident[:8],16)+rep*997).shuffle(order)
                seed=(830031+rep*527+int(item["sha256"][:8],16))%(2**32)
                for mode in order:
                    selected=decision if mode=="v95_structural" else mode
                    started=time.monotonic();error=""
                    try:
                        proc=subprocess.run([str(Path(args.exe).resolve()),selected,
                            str(cnf),str(seed)],capture_output=True,text=True,
                            timeout=CAP,check=False)
                        seconds=time.monotonic()-started
                        if proc.returncode!=0:raise RuntimeError(
                            "exit="+str(proc.returncode)+": "+proc.stderr[-300:])
                        lines=[s for s in proc.stdout.splitlines() if s.startswith("DRNAS_CAUSAL\t")]
                        if len(lines)!=1:raise RuntimeError("solver output missing")
                        attrs=dict(part.split("=",1) for part in lines[0].split("\t")[1:])
                        if attrs.get("mode")!=selected:raise RuntimeError("mode mismatch")
                        status=attrs.get("answer")
                        if status!=item["official_label"]:raise RuntimeError(
                            "solver answer does not match official label: "+str(status))
                    except subprocess.TimeoutExpired:
                        status="TIMEOUT";seconds=CAP
                    except Exception as ex:
                        status="ERROR";seconds=time.monotonic()-started;error=str(ex)
                        issues.append(f"{ident} {mode} rep={rep}: {error}")
                    rec={"id":ident,"sha256":item["sha256"],"shard":args.shard,
                        "rep":rep,"mode":mode,"selected":selected,
                        "status":status,"wall_s":round(seconds,6),"error":error}
                    writer.writerow(rec);fh.flush();rows.append(rec)
                    print("V95_TRIAL",ident[:8],rep,mode,"->",selected,
                          status,rec["wall_s"],flush=True)
            cnf.unlink(missing_ok=True)
    dump(out/"summary.json",{"shard":args.shard,"count":len(rows),"issues":issues})
    if issues or len(rows)!=4*len(MODES)*REPS:raise RuntimeError(str(issues[:3]))
    print("V95_SHARD_PASS",args.shard,len(rows),flush=True)
def audit_cmd(args):
    manifest=json.loads(Path(args.manifest).read_text())
    model=json.loads(Path(args.model).read_text())
    assert manifest["protocol"]==SALT and manifest["model_sha256"]==sha(args.model)
    ids={x["id"]:x for x in manifest["cases"]}
    assert len(ids)==24
    rows=[]
    for i in range(6):
        with (Path(args.combined)/f"v95-shard-{i}"/"results"/"raw.csv").open(newline="") as f:
            rows+=list(csv.DictReader(f))
    assert len(rows)==24*len(MODES)*REPS
    seen=set();per=defaultdict(lambda:defaultdict(list))
    for r in rows:
        pair=(r["id"],r["mode"],int(r["rep"]))
        assert pair not in seen;seen.add(pair)
        assert r["id"] in ids and r["mode"] in MODES and int(r["rep"]) in range(REPS)
        assert r["sha256"]==ids[r["id"]]["sha256"] and not r["error"]
        assert r["status"] in ("SAT","UNSAT","TIMEOUT")
        if r["status"]!="TIMEOUT":assert r["status"]==ids[r["id"]]["official_label"]
        assert r["selected"] in BASE if r["mode"]=="v95_structural" else r["selected"]==r["mode"]
        per[r["id"]][r["mode"]].append(30. if r["status"]=="TIMEOUT" else float(r["wall_s"]))
    assert all(len(per[id][m])==REPS for id in ids for m in MODES)
    result={m:{"solved":sum(x<30 for id in ids for x in per[id][m]),
               "mean_PAR2":statistics.mean(x for id in ids for x in per[id][m])}
            for m in MODES}
    individual=[]
    for id in ids:
        c={m:statistics.mean(per[id][m]) for m in MODES}
        decision=predict({"features":features(ids[id]["features"])},
                         model["training"],model["fitted_selector"])
        individual.append({"id":id,"stratum":ids[id]["stratum"],
                           "official_label":ids[id]["official_label"],
                           "selected":decision,"PAR2":c})
    # Unattainable diagnostic oracle, not a usable solver.
    oracle=statistics.mean(min(x["PAR2"][m] for m in BASE) for x in individual)
    best=min(BASE,key=lambda m:result[m]["mean_PAR2"])
    baseline=best
    improvements=[x["PAR2"][baseline]-x["PAR2"]["v95_structural"] for x in individual]
    rng=random.Random(950031)
    boots=[]
    for _ in range(5000):
        pick=[rng.choice(improvements) for j in improvements]
        boots.append(statistics.mean(pick))
    boots.sort()
    report={"protocol":SALT,"cases":24,"repetitions":REPS,"trials":len(rows),
            "model_selection":model["selected_family"],
            "model_cv":model["candidate_CV"],"fitted":model["fitted_selector"],
            "results":result,"best_static_baseline":best,
            "mean_v95_improvement_over_best_static":statistics.mean(improvements),
            "paired_bootstrap_95pct_delta_seconds":[boots[125],boots[4874]],
            "oracle_existing_four_per_case_PAR2":oracle,
            "cases_detail":individual,
            "limitations":["Official baseline runtimes influenced pre-sampling, no blind claim",
              "Small 24-case test; timings on different GitHub-hosted CPUs across shards",
              "3 repetitions are not independent CNF problems",
              "PAR2 timeouts charged 30s, true runtime beyond 15s unknown",
              "Python routing uses frozen precomputed CNF features, excludes extraction cost",
              "V9.5 only switches existing algorithms; no universal theorem or record"]}
    dump(args.report,report)
    lines=["# DRNAS v9.5 — preregistered structure selector, 24 fresh official 2026 CNFs",
           "",f"Independent from prior 30 training instances; {len(rows)} attempts (3 repetitions).",
           f"Model chosen by old-data LOOCV: **{model['selected_family']}** {model['fitted_selector']}.",
           "All runs use 15s timeout, PAR2 penalty 30s. Lower mean PAR2 is better.","",
           "| Mode | Solved / 72 | Mean PAR2 (s) |","|---|---:|---:|"]
    for m in MODES:
        lines.append(f"| {m} | {result[m]['solved']}/72 | {result[m]['mean_PAR2']:.5f} |")
    lines+=["",f"Unattainable per-instance oracle across four existing arms: {oracle:.5f}s.",
       f"Paired mean (best static {best} minus v95): {statistics.mean(improvements):.5f}s.",
       f"Instance-bootstrap 95% interval: [{boots[125]:.5f}, {boots[4874]:.5f}]s.",
       "WARNING: Feature extraction time was not included in timed selection.",
       "No claim of world record, independent competition ranking, or P=NP.",
       "","## Per-instance PAR2"]
    lines+=["| CNF | Type | Routed mode | CaDiCaL | V7.6 | V7.6 Plain | V9.2 Sparse | V9.4 | V9.5 |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for x in individual:
        a=x["PAR2"]
        lines.append(f"| {x['id'][:10]} | {x['official_label']} | {x['selected']} | "+
             " | ".join(f"{a[m]:.3f}" for m in MODES)+" |")
    Path(args.markdown).write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)
def main():
    parser=argparse.ArgumentParser()
    commands=parser.add_subparsers(dest="action",required=True)
    t=commands.add_parser("train")
    t.add_argument("--old",required=True);t.add_argument("--new",required=True)
    t.add_argument("--out",required=True)
    f=commands.add_parser("freeze")
    f.add_argument("--old-manifest",required=True)
    f.add_argument("--new-manifest",required=True)
    f.add_argument("--model",required=True);f.add_argument("--scores",required=True)
    f.add_argument("--out",required=True)
    r=commands.add_parser("run")
    r.add_argument("--model",required=True);r.add_argument("--manifest",required=True)
    r.add_argument("--shard",type=int,required=True)
    r.add_argument("--exe",required=True);r.add_argument("--out",required=True)
    a=commands.add_parser("audit")
    a.add_argument("--model",required=True);a.add_argument("--manifest",required=True)
    a.add_argument("--combined",required=True);a.add_argument("--report",required=True)
    a.add_argument("--markdown",required=True)
    args=parser.parse_args()
    {"train":train_cmd,"freeze":freeze_cmd,"run":run_cmd,"audit":audit_cmd}[args.action](args)
if __name__=="__main__":main()
