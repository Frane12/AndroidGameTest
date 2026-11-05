#!/usr/bin/env python3
"""R159: genuine external CNF transfer for frozen R158 A/B/C/D.

Honest scope: 16 original R151 external CNFs, SHA-disjoint from the 160
R158 training/evaluation formulas, but REUSED from the earlier R151 benchmark.
No false claim that these are globally untested or a fresh SAT competition.

R158 policy predictions are SHADOW ONLY. No R158 live policy exists; we
benchmark native R17 guarded versus same-binary monitor, original Kissat,
CaDiCaL, and immutable V15.3.1 on the same runner and same original CNF.
"""
import argparse,collections,csv,hashlib,json,math,os,platform,random,resource
import signal,statistics,subprocess,sys,time
from pathlib import Path

sys.path.insert(0,"experiments/drnas_v16")
sys.path.insert(0,"research")
import r17_external_transfer as ext
import r158_features as feat
import r158_experiment as r158

ROOT=Path("r159")
SOURCE=Path("r159-r151-source/holdout")
MODEL_DIR=Path("r159-r158-model/r158-evidence")
FREEZE=ROOT/"frozen"
MODES=("monitor","r17_guarded50","original_kissat","stable_v1531","cadical")
QUOTAS=("official2026","official2025","miter","cryptography")
PROTO="R159-R158-REAL-EXTERNAL-SHA-TRANSFER-20261106-v1"
REPS=3
CAP=8.0
SHARDS=4
SOURCE_RUN=42094754907
SOURCE_ARTIFACT=13447565674
R158_RUN=42130768112
R158_ARTIFACT=13463705395

def need(yes,what):
    if not yes:raise RuntimeError("R159_FAIL_CLOSED "+str(what))
def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1<<20),b""):h.update(block)
    return h.hexdigest()
def dump(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def rows(path):
    with Path(path).open(newline="") as f:return list(csv.DictReader(f))
def writecsv(path,data):
    need(bool(data),"no CSV rows")
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(data[0]))
        w.writeheader();w.writerows(data)
def check_frozen():
    data=json.loads((SOURCE/"manifest.json").read_text())
    prior=json.loads((MODEL_DIR/"r158_models.json").read_text())
    r158rows=rows(MODEL_DIR/"r158_features.csv")
    need(len(data["cases"])==40 and len(set(x["sha256"] for x in data["cases"]))==40,
         "missing original R151 independent SHA source 40")
    need(data["r151_protocol"]=="DRNAS-R151-RISK-ABSTENTION-NEW-SHA-DISJOINT-20261105-v1" and
         data["r151_full_DIMACS_clause_validation"] is True, "source model/protocol drift")
    need(prior["protocol"]=="R158-FED-20261106-v1" and prior["source_run"]==42094261835,
         "R158 model source drift")
    need(prior["safe_action"]=="MONITOR_ABSTAIN" and prior["train_formulas"]==80
         and prior["heldout_formulas"]==80 and prior["test_labels_used_for_fit"] is False,
         "R158 frozen model not safe")
    need(len(r158rows)==160 and len({x["sha256"] for x in r158rows})==160,
         "incomplete R158 historical SHA registry")
    past={x["sha256"] for x in r158rows}
    return data,prior,past

def freeze():
    data,prior,past=check_frozen()
    chosen=[]
    for cohort in QUOTAS:
        possible=sorted((x for x in data["cases"] if x["cohort"]==cohort
            and x["variables"]<=5000 and x["bytes"]<=5_000_000
            and x["clauses"]<=250000),key=lambda x:(x["variables"],x["sha256"]))
        take=possible[:4]
        need(len(take)==4,"not four feasible SHA-original sources for "+cohort)
        for case in take:
            path=SOURCE/case["id"]
            need(path.is_file() and sha(path)==case["sha256"],"original CNF SHA "+case["id"])
            need(case["sha256"] not in past,"source overlaps R158 training/test")
            n,clauses=ext.parse_original(path)
            need(n==case["variables"] and len(clauses)==case["clauses"],
                 "full original DIMACS validation mismatch "+case["id"])
            chosen.append({k:case[k] for k in (
                "id","cohort","sha256","variables","clauses","bytes",
                "source_url","source_identifier","source_catalog","packed_sha256")})
    need(len(chosen)==16 and len({c["sha256"] for c in chosen})==16,"invalid selection 16")
    manifest=dict(protocol=PROTO,phase="FIXED_BEFORE_R159_SOLVES",
       source_R151_run=SOURCE_RUN,source_R151_artifact=SOURCE_ARTIFACT,
       source_manifest_sha256=sha(SOURCE/"manifest.json"),
       r158_model_run=R158_RUN,r158_model_artifact=R158_ARTIFACT,
       r158_models_sha256=sha(MODEL_DIR/"r158_models.json"),
       r158_formula_registry_sha256=sha(MODEL_DIR/"r158_features.csv"),
       SHA_disjoint_from_R158_160=True,
       previously_measured_in_R151=True,not_globally_blind=True,
       original_CNFs_preserved=True,
       formula_selection="cohort-fixed first four smallest eligible variable-count original CNFs, before R159 timings",
       quotas={c:4 for c in QUOTAS},repeats=REPS,cap_seconds=CAP,
       modes=MODES,cases=chosen)
    dump(FREEZE/"manifest.json",manifest)
    print("R159_FROZEN_SOURCE_PASS "+json.dumps({"formulas":16,
       "cohorts":manifest["quotas"],"sha":sha(FREEZE/"manifest.json"),
       "reused_R151":True,"new_to_R158":True},sort_keys=True),flush=True)

def cases_for(shard):
    manifest=json.loads((FREEZE/"manifest.json").read_text())
    data,model,past=check_frozen()
    need(manifest["protocol"]==PROTO and manifest["phase"]=="FIXED_BEFORE_R159_SOLVES",
         "frozen manifest mismatch")
    need(manifest["source_manifest_sha256"]==sha(SOURCE/"manifest.json")
         and manifest["r158_models_sha256"]==sha(MODEL_DIR/"r158_models.json")
         and manifest["r158_formula_registry_sha256"]==sha(MODEL_DIR/"r158_features.csv"),
         "frozen source changed")
    need(len(manifest["cases"])==16,"missing 16 fixed original CNFs")
    out=[]
    for c in manifest["cases"][shard::SHARDS]:
        path=SOURCE/c["id"]
        need(sha(path)==c["sha256"] and c["sha256"] not in past,"real CNF SHA drift")
        n,clauses=ext.parse_original(path)
        need(n==c["variables"] and len(clauses)==c["clauses"],"original CNF clause drift")
        # Stable synthetic seed derived from the immutable original formula SHA;
        # no generator or synthetic CNF is used.
        out.append(dict(path=path.resolve(),formula=c["id"],n=n,clauses=clauses,
          formula_sha256=c["sha256"],expected="UNKNOWN",category=c["cohort"],
          metadata=dict(fold="external_transfer_reused_R151",
             seed=int(c["sha256"][:12],16),
             features=ext.features(clauses,n),cohort=c["cohort"])))
    need(len(out)==4,"missing 4 original CNFs in shard")
    return out

def cadical_trial(case,rep,runner):
    path=Path("built/bin/cadical_3_0_1").resolve()
    need(path.is_file(),"missing pinned CaDiCaL")
    begin=time.perf_counter()
    cpu_before=resource.getrusage(resource.RUSAGE_CHILDREN)
    p=subprocess.Popen([str(path),str(case["path"])],text=True,errors="replace",
       stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    try:
        stdout,stderr=p.communicate(timeout=CAP)
        status={10:"SAT",20:"UNSAT"}.get(p.returncode,"ERROR")
    except subprocess.TimeoutExpired:
        os.killpg(p.pid,signal.SIGKILL)
        stdout,stderr=p.communicate();status="TIMEOUT"
    wall=time.perf_counter()-begin
    cpu_after=resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu=(cpu_after.ru_utime+cpu_after.ru_stime)-(cpu_before.ru_utime+cpu_before.ru_stime)
    checked=ext.base.check_witness(case,stdout,None) if status=="SAT" else None
    error="" if status in ("SAT","UNSAT","TIMEOUT") else "unexpected CaDiCaL return "+str(p.returncode)+" "+stderr[-250:]
    if status=="SAT" and checked is not True:error="CaDiCaL invalid/missing SAT model"
    row=dict(formula=case["formula"],formula_sha256=case["formula_sha256"],
      category=case["category"],fold="external_transfer_reused_R151",
      seed=case["metadata"]["seed"],repeat=rep,mode="cadical",status=status,
      wall_s=round(wall,6),cpu_s=round(cpu,6),
      par2_s=round(wall,6) if status!="TIMEOUT" else 2*CAP,
      runner=runner,error=error,sat_model_checked=checked,
      unsat_certificate_checked=False,exit_code=p.returncode,
      switch_at="",r17_selected="",r17_error="")
    return row,{"category":case["category"],"formula":case["formula"],
      "repeat":rep,"mode":"cadical","points":[]}

def run(shard):
    need(0<=shard<SHARDS,"invalid shard")
    ext.r11.CAP=CAP
    core=ext.set_cpu_affinity()
    runner=os.environ.get("RUNNER_NAME","unknown")+"/pinned_core_"+str(core)+"/"+platform.processor()
    cases=cases_for(shard)
    d=ROOT/("shard-%d"%shard)
    d.mkdir(parents=True,exist_ok=True)
    binaries=dict(original_kissat=sha(ext.base.ORIGINAL),
          r17_patched=sha(ext.base.PATCHED),stable_v1531=sha(ext.base.STABLE),
          cadical=sha(Path("built/bin/cadical_3_0_1")),
          r158_model=sha(MODEL_DIR/"r158_models.json"))
    data=[];traces=[]
    for case in cases:
        for rep in range(REPS):
            order=list(MODES)
            random.Random(int(case["formula_sha256"][:12],16)+rep+159).shuffle(order)
            for mode in order:
                if mode=="cadical":r,t=cadical_trial(case,rep,runner)
                else:r,t=ext.run_one(case,rep,mode,runner)
                r["original_source_sha256"]=case["formula_sha256"]
                r["r159_protocol"]=PROTO
                data.append(r);traces.append(t)
                print("R159_MEASURE",case["formula"],rep,mode,r["status"],r["par2_s"],
                      "switch",r.get("switch_at",""),flush=True)
                need(not r.get("error") and not r.get("r17_error"),
                     "native error "+str(r.get("error"))+" "+str(r.get("r17_error")))
        statuses={r["status"] for r in data if r["formula"]==case["formula"]
                   and r["status"] in ("SAT","UNSAT")}
        need(len(statuses)<=1,"SAT/UNSAT contradiction "+case["formula"])
    need(len(data)==4*REPS*len(MODES) and len(traces)==len(data),"partial paired shard")
    writecsv(d/"measurements.csv",data)
    (d/"traces.jsonl").write_text("".join(json.dumps(x,sort_keys=True)+"\n" for x in traces))
    dump(d/"manifest.json",dict(protocol=PROTO,shard=shard,runner=runner,
      source_commit=os.environ.get("GITHUB_SHA","local"),
      frozen_source_sha256=sha(FREEZE/"manifest.json"),
      binary_sha256=binaries,
      cpu_affinity=sorted(os.sched_getaffinity(0)),modes=MODES,
      rows=len(data),source_shas=[x["formula_sha256"] for x in cases],
      cap_seconds=CAP))
    print("R159_SHARD_PASS",shard,len(data),flush=True)

def bootstrap(per,arm):
    rng=random.Random(159221+sum(ord(c) for c in arm))
    cohorts=collections.defaultdict(list)
    for x in per:cohorts[x["cohort"]].append(x)
    gains=[]
    for _ in range(2000):
        sampled=[rng.choice(group) for group in cohorts.values() for _ in group]
        b=sum(x["monitor"] for x in sampled);a=sum(x[arm] for x in sampled)
        gains.append(100*(b-a)/b if b else 0)
    gains.sort()
    return [round(gains[int(.025*1999)],5),round(gains[int(.975*1999)],5)]

def audit():
    source=json.loads((FREEZE/"manifest.json").read_text())
    data,model,past=check_frozen()
    need(source["phase"]=="FIXED_BEFORE_R159_SOLVES","unfrozen source")
    original={c["id"]:c for c in source["cases"]}
    observed=[];traces={};source_shards=[]
    for shard in range(SHARDS):
        folder=Path("r159-download")/("r159-shard-%d"%shard)
        meta=json.loads((folder/"manifest.json").read_text())
        measurements=rows(folder/"measurements.csv")
        logs=[json.loads(line) for line in (folder/"traces.jsonl").read_text().splitlines()]
        need(meta["protocol"]==PROTO and meta["shard"]==shard and
             meta["frozen_source_sha256"]==sha(FREEZE/"manifest.json"),
             "shard source mismatch")
        need(len(measurements)==60 and len(logs)==60,"partial 60 attempt shard")
        need(meta["modes"]==list(MODES) and len(meta["source_shas"])==4,"policy split wrong")
        for r in measurements:
            need(r["runner"]==meta["runner"] and not r.get("error") and
                 r["original_source_sha256"]==r["formula_sha256"],
                 "identity, runner or recorded solver error")
            need(r["formula"] in original and r["formula_sha256"]==original[r["formula"]]["sha256"],
                 "unrecognized original SHA")
            need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"invalid solver status")
            need(abs(float(r["par2_s"])-(2*CAP if r["status"]=="TIMEOUT" else float(r["wall_s"])))<.0001,
                 "invalid PAR-2")
            if r["status"]=="SAT":
                need(str(r["sat_model_checked"])=="True","SAT model was not checked")
            if r["mode"]=="r17_guarded50":
                need(not r.get("switch_at"),"guarded50 made unapproved outside-domain switch")
        for t in logs:
            key=(t["formula"],str(t["repeat"]),t["mode"])
            need(key not in traces,"duplicate native trace")
            traces[key]=t
        observed.extend(measurements)
        source_shards.append(dict(shard=shard,runner=meta["runner"],commit=meta["source_commit"],
             executable_SHA256=meta["binary_sha256"],
             manifest_sha256=sha(folder/"manifest.json"),
             measurements_sha256=sha(folder/"measurements.csv"),
             traces_sha256=sha(folder/"traces.jsonl")))
    need(len(observed)==240 and len(traces)==240,"incomplete 240 measured attempts")
    grouped=collections.defaultdict(dict)
    for r in observed:
        key=(r["formula"],str(r["repeat"]))
        need(r["mode"] not in grouped[key],"duplicate per formula-mode")
        grouped[key][r["mode"]]=r
    need(len(grouped)==48,"missing paired formula-repeats")
    for key,vals in grouped.items():
        need(set(vals)==set(MODES),"partial paired policy")
        need(len({r["runner"] for r in vals.values()})==1,"unpaired runner")
        need(len({r["status"] for r in vals.values() if r["status"] in ("SAT","UNSAT")})<=1,
             "SAT/UNSAT inconsistency")
        monitor=traces[(*key,"monitor")]["points"]
        guard=traces[(*key,"r17_guarded50")]["points"]
        one={int(x["conflict"]):x for x in monitor if int(x["conflict"])<=1024}
        two={int(x["conflict"]):x for x in guard if int(x["conflict"])<=1024}
        need(one.keys()==two.keys(),"native prefix checkpoint coverage drift")
        for checkpoint in one:
            need(all(one[checkpoint].get(k)==two[checkpoint].get(k) for k in
                ("restarts","decisions","propagations","learned","glue","stable")),
                "pre-intervention native prefix mismatch")
    per=[];feature_rows=[];warnings=[];cost=[]
    for c in source["cases"]:
        formula=c["id"]
        rr=[r for r in observed if r["formula"]==formula]
        need(len(rr)==REPS*len(MODES),"missing per-formula attempts")
        sums={mode:sum(float(r["par2_s"]) for r in rr if r["mode"]==mode) for mode in MODES}
        per.append(dict(formula=formula,sha256=c["sha256"],cohort=c["cohort"],
                        n=c["variables"],**sums))
        metrics=None;why=""
        started=time.perf_counter()
        try:
            metrics=feat.static_features(feat.parse_dimacs(SOURCE/c["id"]))
        except (ValueError,MemoryError) as e:
            why=str(e)[:200]
        monitors=[traces[(formula,str(i),"monitor")] for i in range(REPS)]
        dynamic=feat.dynamic_features(monitors)
        cost.append((time.perf_counter()-started)*1000)
        if metrics is None:
            featrow={"formula":formula,"sha256":c["sha256"],"cohort":c["cohort"],
                "source":"real_external_R151_reused_not_blind",
                "graph_available":False,"graph_error":why,"safe_action":"MONITOR_ABSTAIN"}
            warnings.append(formula+": "+why)
        else:
            numbers={**metrics,**dynamic}
            featrow={"formula":formula,"sha256":c["sha256"],"cohort":c["cohort"],
                "source":"real_external_R151_reused_not_blind",
                "graph_available":True,"graph_error":"",
                "safe_action":"MONITOR_ABSTAIN",
                **{k:v for k,v in numbers.items() if k!="box_counts"}}
            for arm in ("A","B","C","D"):
                prediction=r158.predict(model["models"][arm]["ridge"],numbers)
                need(math.isfinite(prediction),"nonfinite prediction")
                featrow["shadow_pred_gain_"+arm]=round(100*prediction,6)
        feature_rows.append(featrow)
    # CSV columns union since unsupported graphs intentionally omit predictions.
    cols=list(dict.fromkeys(k for x in feature_rows for k in x))
    path=ROOT/"report";path.mkdir(parents=True,exist_ok=True)
    with (path/"external_features.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=cols);w.writeheader();w.writerows(feature_rows)
    writecsv(path/"paired_external.csv",per)
    base=sum(x["monitor"] for x in per);summary={}
    for arm in MODES:
        total=sum(x[arm] for x in per)
        summary[arm]=dict(par2_s=round(total,6),
            relative_to_monitor_pct=round(100*(base-total)/base,6) if base else 0,
            solved=sum(x["status"] in ("SAT","UNSAT") for x in observed if x["mode"]==arm),
            formula_bootstrap95=bootstrap(per,arm) if arm!="monitor" else [0,0],
            regressions_2x=sum(x[arm]>2*x["monitor"] for x in per))
    report=dict(protocol=PROTO,phase="REAL_SOURCE_PREVIOUSLY_MEASURED_IN_R151_NOT_GLOBALLY_BLIND",
        source_run=SOURCE_RUN,source_artifact=SOURCE_ARTIFACT,
        new_to_frozen_R158_training_and_test=True,original_formulas=16,
        distinct_original_formula_sha=16,source_families=list(QUOTAS),repeats=REPS,
        measured_SAT_attempts=len(observed),old_R151_timings_not_reused=True,
        frozen_R158_model_sha256=sha(MODEL_DIR/"r158_models.json"),
        frozen_source_manifest_sha256=sha(FREEZE/"manifest.json"),
        graph_feature_available=sum(bool(x["graph_available"]) for x in feature_rows),
        graph_feature_unavailable=warnings,
        early_prefix_valid=sum(x.get("prefix_valid",0)==1 for x in feature_rows),
        median_feature_overhead_ms=round(statistics.median(cost),4),
        source_shards=source_shards,
        summary=summary,live_R158_policy_executed=False,live_guarded50_switch_count=0,
        new_live_R158_speedup_claim=False,
        frozen_V1531_changed=False,independent_UNSAT_certificate=False,
        warnings=["R151 original external cases reused, not globally unseen/virgin",
             "Original official-catalog membership is not competition ranking",
             "Frozen R17 guarded policy only acts at n=220 or 240; R159 n differs",
             "Fractal box-cover proxy is not verified mathematical fractality",
             "R158 models predict R17 guarded-vs-monitor, NOT Kissat-vs-CaDiCaL",
             "Feature extraction overhead measured separately from SAT PAR-2"])
    dump(path/"report.json",report)
    # Paired scatterplot, no dependence on matplotlib.
    mx=max([x["monitor"] for x in per]+[x["r17_guarded50"] for x in per])
    def v(x):return 45+670*x/max(1e-9,mx)
    points="".join('<circle cx="%.2f" cy="%.2f" r="4" fill="#208e9e"/>'%
                   (v(x["monitor"]),760-v(x["r17_guarded50"])) for x in per)
    svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800"><rect width="800" height="800" fill="white"/><path d="M45 715 L715 45" stroke="#777" stroke-dasharray="5 5"/>'+points+'<text x="45" y="24" font-size="18">R159 paired real CNF, reused R151</text><text x="45" y="780">X=monitor PAR2 / Y=guarded PAR2</text></svg>'
    (path/"paired_scatter.svg").write_text(svg)
    print("R159_FINAL "+json.dumps({k:report[k] for k in
        ("original_formulas","measured_SAT_attempts","graph_feature_available",
         "live_R158_policy_executed","summary")},sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("step",choices=("freeze","run","audit"))
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    {"freeze":freeze,"run":lambda:run(args.shard),"audit":audit}[args.step]()
