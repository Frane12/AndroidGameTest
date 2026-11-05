#!/usr/bin/env python3
"""DRNAS R152: multi-window features + cost-sensitive symmetric SAT selection.

Train on frozen, previously exposed 400 only. Prospective 6-way comparison on
new original SHA-disjoint CNFs, excluding R132/R135/R135S/R148/R150/R151.
Kissat/CaDiCaL/R148/R151_05 preserved as separate, pinned references.
"""
import argparse,collections,csv,hashlib,json,math,os,pathlib,random,re,statistics,subprocess,time
import r150_quality_benchmark as legacy
import r151_risk_benchmark as prev

ROOT=pathlib.Path("r152")
SOURCE=ROOT/"holdout"
HISTORY=pathlib.Path("r152-history")
BIN=ROOT/"stratified_features"
LEGACY_FEATURES=ROOT/"legacy_features"
SELECTOR=ROOT/"stratified_features"
R151_BIN=ROOT/"r151_selector"
R151_MODEL=ROOT/"prior-r151-model.txt"
R148_BIN=ROOT/"r148_selector"
MODEL=ROOT/"model24.txt"
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
CADICAL=pathlib.Path("built/bin/cadical_3_0_1")
PROTO="DRNAS-R152-STRATIFIED-REGRET-PROSPECTIVE-SHA-DISJOINT-20261105-v1"
SHARDS=8; REPS=2; CAP=15.0; DIM=24; K=24
MODES=("kissat","cadical","r148","r151_05","r152_05","r152_15")
ZS={"r152_05":0.5,"r152_15":1.5}
QUOTAS={"official2026":12,"official2025":12,"miter":10,"cryptography":10,
        "xor_shifting":10,"uniform_random":10}
INDEXES_EXTRA={
 "xor_shifting":"https://benchmark-database.de/getinstances?query=family%3Dxor-shifting&context=cnf",
 "uniform_random":"https://benchmark-database.de/getinstances?query=family%3Duniform-random&context=cnf"}
PREVIOUS={
 "r135_56":("r152-prior-r135/manifest.json",56),
 "r135s_21":("r152-prior-r135s/frozen/manifest.json",21),
 "r148_50":("r152-prior-r148/frozen/manifest.json",50),
 "r150_55":("r152-prior-r150/holdout/manifest.json",55),
 "r151_40":("r152-prior-r151/holdout/manifest.json",40),
}
def need(cond, msg):
    if not cond:raise RuntimeError("R152_REFUSED "+str(msg))
def sha(path):return legacy.sha(path)
def read(path):return json.loads(pathlib.Path(path).read_text())
def write(path,obj):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+".partial")
    tmp.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
    os.replace(tmp,p)
def configure():
    prev.ROOT=ROOT;prev.SOURCE=SOURCE;prev.HISTORY=HISTORY
    prev.FEAT=LEGACY_FEATURES;prev.R148=R148_BIN
    prev.MODEL=R151_MODEL;prev.PROTO=PROTO
    prev.QUOTAS=QUOTAS.copy()
    prev.EXTRA_PRIORS=PREVIOUS.copy()
    prev.base_config()
    legacy.INDEXES.update(INDEXES_EXTRA)
def feature24(path):
    p=subprocess.run([str(BIN.resolve()),str(pathlib.Path(path).resolve())],
        capture_output=True,text=True,timeout=6)
    need(p.returncode==0,"native feature extraction failure "+p.stderr[-150:])
    line=next((x for x in p.stdout.splitlines() if x.startswith("c R152_FEATURE ")),None)
    need(line is not None,"native features missing")
    m=re.search(r"\bx=([0-9.,]+)",line)
    need(m is not None,"native vector missing")
    x=[float(v) for v in m.group(1).split(",")]
    need(len(x)==DIM and all(math.isfinite(v) and 0<=v<=1 for v in x),
         "native feature dimension/validity drift")
    return x
def scales(e):
    return [max(.08,min(2.,statistics.pstdev(row["x"][i] for row in e))) for i in range(DIM)]
def predict(e,sigma,x,z):
    near=sorted(e,key=lambda r:sum(((r["x"][i]-x[i])/sigma[i])**2
                                 for i in range(DIM)))[:K]
    mu=statistics.mean(r["delta"] for r in near)
    var=statistics.variance(r["delta"] for r in near)
    se=math.sqrt(var/K)
    return ("cadical" if mu+z*se < -.5 else "kissat"),mu,se
def train():
    configure()
    # Read-only replay of pre-existing 400 paired PAR-2 records. Native R151
    # model is a pinned baseline, not retrained or touched here.
    examples=prev.training_data()
    need(len(examples)==400,"historical training drift")
    for i,row in enumerate(examples):
        row["x"]=feature24(row["id"])
        if (i+1)%100==0:print("R152_TRAIN_FEATURES",i+1,flush=True)
    cohorts=collections.defaultdict(list)
    for r in examples:cohorts[r["cohort"]].append(r)
    need(len(cohorts)==4 and all(len(a)==100 for a in cohorts.values()),
         "expected four historical cohorts")
    cv={}
    for mode,z in ZS.items():
        kcost=0.;candidate=0.;changes=0;reg=0
        for held,heldrows in cohorts.items():
            sample=[r for r in examples if r["cohort"]!=held]
            sigma=scales(sample)
            for row in heldrows:
                pick,mu,se=predict(sample,sigma,row["x"],z)
                kcost+=row["cost"]["kissat"]
                candidate+=row["cost"][pick]
                changes+=(pick=="cadical")
                reg+=(row["cost"][pick]>=2*max(.001,row["cost"]["kissat"]))
        cv[mode]=dict(grouped_leave_cohort_out=True,
                      gain_PAR2_s=round(kcost-candidate,6),
                      candidate_PAR2_s=round(candidate,6),
                      Kissat_PAR2_s=round(kcost,6),
                      cadical_routes=changes,regressions_2x=reg)
    # Full-par2 regret target (no clipping). Model frozen BEFORE acquiring
    # any new prospective formula, with no per-formula ID/hardcoding.
    sigma=scales(examples)
    lines=[f"R152_KNN24_V1 {len(examples)} {K} {DIM}",
           " ".join(format(v,".17g") for v in sigma)]
    lines.extend(" ".join(format(v,".9g") for v in row["x"]+[row["delta"]])
                 for row in examples)
    MODEL.parent.mkdir(parents=True,exist_ok=True)
    MODEL.write_text("\n".join(lines)+"\n")
    report=dict(protocol=PROTO,historical_training=400,historical_trials=4000,
       test_sources_used_to_train=0,dimension=DIM,model_sha256=sha(MODEL),
       no_target_clipping=True,precommitted_ZS=ZS,
       grouped_leave_cohort_out_cv=cv,
       feature_scope="three windows up to 64KiB/1024 clauses each; 24 bounded features",
       caution="Group-CV history was already used and is not new blind evidence")
    write(ROOT/"train-report.json",report)
    print("R152_TRAIN_FROZEN",json.dumps(report,sort_keys=True),flush=True)
def freeze():
    configure()
    excluded,urls,ids,hashes=prev.old_exclusions()
    orig_download=legacy.download
    index_urls=set(legacy.INDEXES.values())
    rejected=collections.Counter()
    def strict(url,maximum=8000000):
        if url not in index_urls:
            identity=url.rsplit("/",1)[-1].split("?")[0]
            if url in urls or identity in ids:
                rejected["prior_URL_or_ID"]+=1
                raise RuntimeError("R152_PRIOR_URL_ID")
        raw=orig_download(url,maximum)
        if url not in index_urls and hashlib.sha256(legacy.unpack(raw)).hexdigest() in excluded:
            rejected["prior_SHA"]+=1
            raise RuntimeError("R152_PRIOR_SHA")
        return raw
    legacy.download=strict
    try:legacy.freeze()
    finally:legacy.download=orig_download
    meta=read(SOURCE/"manifest.json");cases=meta["cases"]
    need(48<=len(cases)<=sum(QUOTAS.values()) and
         len({x["cohort"] for x in cases})>=5,"insufficient diverse new CNFs")
    need(all(c["sha256"] not in excluded and c["source_url"] not in urls
             and c["source_identifier"] not in ids for c in cases),
         "historical formula overlap")
    for c in cases:
        nv,nc=prev.verify_dimacs(SOURCE/c["id"])
        need(nv==c["variables"] and nc==c["clauses"],"DIMACS header mismatch")
    meta["r152_protocol"]=PROTO
    meta["r152_sources_precommitted"]=QUOTAS
    meta["r152_prior_manifests_sha256"]=hashes
    meta["r152_extra_prior_exclusion_rejections"]=dict(rejected)
    meta["r152_full_DIMACS_verified"]=True
    meta["r152_historical_model_frozen_before_solver_timing"]=sha(MODEL)
    meta["r152_policies_precommitted"]=list(MODES)
    write(SOURCE/"manifest.json",meta)
    print("R152_FREEZE_FINAL",json.dumps(dict(count=len(cases),
       cohorts=meta["counts"],model_sha=sha(MODEL),manifest_sha=sha(SOURCE/"manifest.json"),
       exclusions=hashes,rejections=dict(rejected)),sort_keys=True),flush=True)
def cases():
    configure()
    cc=legacy.cases()
    m=read(SOURCE/"manifest.json")
    need(m.get("r152_protocol")==PROTO and m.get("r152_full_DIMACS_verified")
         and m.get("r152_historical_model_frozen_before_solver_timing")==sha(MODEL),
         "prospective source/model mismatch")
    need(48<=len(cc)<=64 and len(set(c["sha256"] for c in cc))==len(cc),
         "source count or identity mismatch")
    return cc
def choose(src,mode):
    start=time.perf_counter()
    if mode=="r148":
        cmd=[str(R148_BIN.resolve()),str(src.resolve())]
        tag="c R148_SELECTOR "
    elif mode=="r151_05":
        cmd=[str(R151_BIN.resolve()),str(src.resolve()),str(R151_MODEL.resolve()),"0.5"]
        tag="c R151_SELECTOR "
    else:
        cmd=[str(SELECTOR.resolve()),str(src.resolve()),str(MODEL.resolve()),
             str(ZS[mode])]
        tag="c R152_FEATURE "
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
         text=True,timeout=6)
    need(p.returncode==0,"native routing failure "+mode+" "+p.stderr[-200:])
    line=next((x for x in p.stdout.splitlines() if x.startswith(tag)),None)
    need(line is not None,"native telemetry missing "+mode)
    fields=dict(re.findall(r"([a-z_]+)=([^\s]+)",line))
    route=fields.get("route","").lower()
    need(route in ("kissat","cadical"),"unsafe backend route "+route)
    extra={}
    if mode.startswith("r152"):
        extra=dict(predicted_delta=float(fields["risk_delta"]),
                   predicted_se=float(fields["risk_se"]),
                   sampled_windows=int(fields["sampled_windows"]),
                   abstained=fields["abstained"]=="1")
        need(all(math.isfinite(extra[k]) for k in ("predicted_delta","predicted_se")),"invalid score")
    return route,round(time.perf_counter()-start,6),extra
def trial(src,mode,rep):
    t=time.perf_counter()
    route=mode;cost=0.;extra={}
    if mode not in ("kissat","cadical"):
        route,cost,extra=choose(src,mode)
    status="TIMEOUT";proof="timeout"
    elapsed=time.perf_counter()-t
    if elapsed<CAP:
        cmd=[str((KISSAT if route=="kissat" else CADICAL).resolve()),str(src.resolve())]
        try:
            p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
              timeout=CAP-elapsed)
            elapsed=time.perf_counter()-t
            need(p.returncode in (10,20),"unexpected SAT engine return code "+
                 str(p.returncode)+" stderr "+p.stderr[-120:].decode(errors="replace"))
            if elapsed<CAP:
                status="SAT" if p.returncode==10 else "UNSAT"
                if status=="SAT":
                    legacy.old.witness.check_original_sat(p.stdout,src)
                    proof="original_CNF_SAT_witness_verified"
                else:
                    proof="UNSAT_not_independently_certified"
        except subprocess.TimeoutExpired:elapsed=CAP
    elapsed=min(CAP,elapsed)
    return dict(mode=mode,rep=rep,route=route,selector_s=cost,
                status=status,seconds=round(elapsed,6),
                par2=30.0 if status=="TIMEOUT" else round(elapsed,6),
                proof=proof,**extra)
def run(shard):
    need(0<=shard<SHARDS,"invalid shard")
    cs=cases()
    required=(KISSAT,CADICAL,R148_BIN,R151_BIN,R151_MODEL,SELECTOR,MODEL)
    need(all(p.exists() for p in required),"missing one frozen binary or model")
    if hasattr(os,"sched_getaffinity"):
        affinity=os.sched_getaffinity(0)
        os.sched_setaffinity(0,{min(affinity)})
    cpu=next((line for line in pathlib.Path("/proc/cpuinfo").read_text().splitlines()
             if line.startswith("model name")),"unknown")
    manifest_sha=sha(SOURCE/"manifest.json")
    pins={str(p):sha(p) for p in required}
    rows=[]
    for i,c in enumerate(cs):
        if i%SHARDS!=shard:continue
        src=(SOURCE/c["id"]).resolve()
        need(sha(src)==c["sha256"],"original SHA mismatch")
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(PROTO+"|"+c["sha256"]+"|"+str(rep)).shuffle(modes)
            observed=set()
            for mode in modes:
                r=dict(protocol=PROTO,source_manifest_sha256=manifest_sha,
                       cohort=c["cohort"],id=c["id"],sha256=c["sha256"],
                       shard=shard,**trial(src,mode,rep))
                rows.append(r)
                if r["status"]!="TIMEOUT":
                    observed.add(r["status"])
                    need(len(observed)<=1,"SAT/UNSAT result contradiction")
                print("R152_PAIRED",json.dumps(r,sort_keys=True),flush=True)
                write(ROOT/f"shard-{shard}.json",dict(shard=shard,protocol=PROTO,
                    source_manifest_sha256=manifest_sha,cpu=cpu,pinned=pins,rows=rows))
    need(len(rows)==len(cs[shard::SHARDS])*REPS*len(MODES),
         "incomplete shard trial records")
    print("R152_SHARD_PASS",shard,len(rows),flush=True)
def audit():
    cs=cases()
    manifest_sha=sha(SOURCE/"manifest.json")
    shards=[read(ROOT/f"shard-{i}.json") for i in range(SHARDS)]
    need(all(s["source_manifest_sha256"]==manifest_sha and s["protocol"]==PROTO
             for s in shards),"source protocol/manifest drift")
    need(len(set(json.dumps(s["pinned"],sort_keys=True) for s in shards))==1,
         "pinned binary/model mismatch across runners")
    rows=[r for shard in shards for r in shard["rows"]]
    need(len(rows)==len(cs)*REPS*len(MODES),"incomplete 6-arm trials")
    bysha={c["sha256"]:c for c in cs}
    lookup={}
    for r in rows:
        c=bysha.get(r["sha256"])
        need(c and r["id"]==c["id"] and r["cohort"]==c["cohort"],"source drift")
        need(r["mode"] in MODES and r["rep"] in (0,1),"unrecognized mode/rep")
        need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"status invalid")
        need(0<=r["seconds"]<=CAP and 0<=r["selector_s"]<=CAP,"invalid timing")
        need(abs(r["par2"]-(30 if r["status"]=="TIMEOUT" else r["seconds"]))<1e-4,
             "PAR2 cap accounting invalid")
        if r["status"]=="SAT":need(r["proof"]=="original_CNF_SAT_witness_verified","missing proof")
        if r["status"]=="UNSAT":need(r["proof"]=="UNSAT_not_independently_certified","proof tier misreported")
        key=(r["sha256"],r["rep"],r["mode"])
        need(key not in lookup,"duplicate trial")
        lookup[key]=r
    for c in cs:
        for rep in range(REPS):
            results={lookup[c["sha256"],rep,mode]["status"] for mode in MODES}-{"TIMEOUT"}
            need(len(results)<=1,"contradictory SAT/UNSAT proof")
    summary={}
    for mode in MODES:
        rr=[r for r in rows if r["mode"]==mode]
        solved=[r["seconds"] for r in rr if r["status"]!="TIMEOUT"]
        times=[r["selector_s"] for r in rr]
        summary[mode]=dict(n=len(rr),solved=len(solved),timeouts=len(rr)-len(solved),
          SAT=sum(r["status"]=="SAT" for r in rr),
          UNSAT_unverified=sum(r["status"]=="UNSAT" for r in rr),
          PAR2_s=round(sum(r["par2"] for r in rr),6),
          median_solved_s=round(statistics.median(solved),6) if solved else None,
          detector_total_s=round(sum(times),6),
          detector_median_s=round(statistics.median(times),6))
    per=[]
    for c in cs:
        cost={mode:sum(lookup[c["sha256"],rep,mode]["par2"] for rep in range(REPS))
              for mode in MODES}
        routes={mode:lookup[c["sha256"],0,mode]["route"]
                for mode in MODES if mode not in ("kissat","cadical")}
        per.append(dict(id=c["id"],sha256=c["sha256"],cohort=c["cohort"],**cost,
            **{mode+"_route":route for mode,route in routes.items()}))
    comparisons={}
    for mode in MODES:
        if mode=="kissat":continue
        cmp={}
        for base in ("kissat","r148","r151_05"):
            cmp["gain_vs_"+base+"_pct"]=round(100*(summary[base]["PAR2_s"]-
              summary[mode]["PAR2_s"])/summary[base]["PAR2_s"],6)
            if mode!=base:
                cmp["bootstrap95_vs_"+base]=legacy.bootstrap_pairs(per,mode,base)
                cmp["regressions_2x_vs_"+base]=sum(p[mode]>=2*max(.001,p[base]) for p in per)
        cmp["formula_wins_vs_kissat"]=sum(p[mode]<p["kissat"]-1e-5 for p in per)
        cmp["formula_losses_vs_kissat"]=sum(p[mode]>p["kissat"]+1e-5 for p in per)
        if mode.startswith("r152"):
            cmp["r148_to_kissat"]=sum(p["r148_route"]=="cadical" and p[mode+"_route"]=="kissat" for p in per)
            cmp["r148_to_cadical"]=sum(p["r148_route"]=="kissat" and p[mode+"_route"]=="cadical" for p in per)
        comparisons[mode]=cmp
    cohorts={co:dict(formulas=sum(c["cohort"]==co for c in cs),
        PAR2={mode:round(sum(r["par2"] for r in rows if r["cohort"]==co and r["mode"]==mode),6)
              for mode in MODES},
        solved={mode:sum(r["status"]!="TIMEOUT" for r in rows if r["cohort"]==co and r["mode"]==mode)
              for mode in MODES}) for co in sorted(set(c["cohort"] for c in cs))}
    report=dict(protocol=PROTO,verdict="RESEARCH_ONLY_NO_AUTO_PROMOTION",
        formulas=len(cs),trials=len(rows),cap_s=CAP,reps=REPS,shards=SHARDS,
        source_SHA_verified=True,source_manifest_sha256=manifest_sha,
        historical_400_only_for_training=True,model_sha256=sha(MODEL),
        new_formula_performance_used_for_training=False,
        comparator_R151_model_sha256=sha(R151_MODEL),
        pinned=shards[0]["pinned"],CPU_by_shard=[s["cpu"] for s in shards],
        summary=summary,comparisons=comparisons,by_cohort=cohorts,
        independent_UNSAT_proofs=False,
        caveats=["SHA/URL/ID disjoint from explicit R132/R135/R135S/R148/R150/R151 ledgers, not exhaustive entire repository",
                 "R151 and R152 model both trained on historical 400, not the new test sources",
                 "GitHub CPU models vary between shards; modes paired within shard",
                 "15-second cap produces censored hard-formula decisions",
                 "SAT witnesses checked but no independent UNSAT LRAT/FRAT certificates",
                 "No promotion absent repeated independent blind robustness evidence"])
    write(ROOT/"audit.json",report)
    with (ROOT/"paired.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=sorted({key for row in rows for key in row}))
        w.writeheader();w.writerows(rows)
    with (ROOT/"per_formula.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(per[0]))
        w.writeheader();w.writerows(per)
    print("R152_FINAL",json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("step",choices=("train","freeze","run","audit"))
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    {"train":train,"freeze":freeze,"run":lambda:run(args.shard),"audit":audit}[args.step]()
