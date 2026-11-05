#!/usr/bin/env python3
"""DRNAS R151 risk-aware symmetric SAT solver selector.
Historical training only from the pre-existing 400 SHA-known cases.
Prospective held-out external formulas excluded by SHA, URL and identity from
R132, R135, R135S, R148 and R150. All variants predeclared before freezing.
No mutable frozen baseline, no UNSAT proof claim or automatic promotion.
"""
import argparse,collections,csv,hashlib,json,math,os,pathlib,random,re,statistics,subprocess,sys,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r150_quality_benchmark as b

ROOT=pathlib.Path("r151")
SOURCE=ROOT/"holdout"
HISTORY=pathlib.Path("r151-history")
MODEL=ROOT/"model.txt"
FEAT=ROOT/"features"
SELECTOR=ROOT/"selector"
R148=ROOT/"r148_selector"
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
CADICAL=pathlib.Path("built/bin/cadical_3_0_1")
PROTO="DRNAS-R151-RISK-ABSTENTION-NEW-SHA-DISJOINT-20261105-v1"
MODES=("kissat","cadical","r148","r151_05","r151_15")
CAP=15.0; REPS=2; SHARDS=8
QUOTAS={"official2026":10,"official2025":10,"miter":10,"cryptography":10}
EXTRA_PRIORS={
    "r135_56":("r151-prior-r135/manifest.json",56),
    "r135s_21":("r151-prior-r135s/frozen/manifest.json",21),
    "r148_50":("r151-prior-r148/frozen/manifest.json",50),
    "r150_55":("r151-prior-r150/holdout/manifest.json",55),
}
KNN=24
CONFIDENCES={"r151_05":0.5,"r151_15":1.5}

def need(ok,msg):
    if not ok:raise RuntimeError("R151_REFUSED "+str(msg))
def sha(path):return b.sha(path)
def write(path,data):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    temp=p.with_suffix(p.suffix+".partial")
    temp.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
    os.replace(temp,p)
def load(path):return json.loads(pathlib.Path(path).read_text())
def base_config():
    b.ROOT=ROOT;b.INPUT=HISTORY;b.SOURCES=SOURCE
    b.FEATURE=FEAT;b.R148=R148;b.MODEL=MODEL
    b.PROTO=PROTO;b.QUOTAS=QUOTAS.copy()
    b.CAP=CAP;b.REPS=REPS;b.SHARDS=SHARDS
def training_data():
    base_config()
    cases=b.sources_old()
    need(len(cases)==400,"missing historical 400 real sources")
    paired=b.csvrows(b.locate("paired.csv"))
    need(len(paired)==4000,"historical 4000 paired rows missing")
    grouped=collections.defaultdict(dict)
    for r in paired:
        key=(r["mode"],r["repeat"])
        need(key not in grouped[r["sha256"]],"duplicate historical paired row")
        grouped[r["sha256"]][key]=r
    examples=[]
    for c in cases:
        rr=grouped[c["sha256"]]
        need(len(rr)==10,"bad historical formula rows")
        cost={}
        for mode in ("kissat","cadical","r135"):
            records=[rr[(mode,str(rep))] for rep in range(REPS)]
            for row in records:
                need(row["status"] in ("SAT","UNSAT","TIMEOUT"),"bad historic result")
                expected=2*CAP if row["status"]=="TIMEOUT" else float(row["seconds"])
                need(abs(float(row["par2"])-expected)<0.0001,"bad historical PAR2")
            cost[mode]=sum(float(r["par2"]) for r in records)
        x=b.compute_feature(c["id"])
        need(len(x)==16,"bad feature vector")
        examples.append(dict(id=c["id"],sha256=c["sha256"],cohort=c["cohort"],x=x,
                             delta=cost["cadical"]-cost["kissat"],cost=cost))
    need(len(examples)==400,"missing training examples")
    return examples
def scales_for(examples):
    return [max(.08,min(2.,statistics.pstdev(r["x"][i] for r in examples))) for i in range(16)]
def predict(examples,scale,x,z):
    near=sorted(examples,key=lambda r:sum(((x[i]-r["x"][i])/scale[i])**2 for i in range(16)))[:KNN]
    mean=sum(r["delta"] for r in near)/len(near)
    var=sum((r["delta"]-mean)**2 for r in near)/(len(near)-1)
    se=math.sqrt(max(0.,var/len(near)))
    return "cadical" if mean+z*se<-.5 else "kissat",mean,se
def train():
    e=training_data()
    scale=scales_for(e)
    grouped=collections.defaultdict(list)
    for r in e:grouped[r["cohort"]].append(r)
    need(all(len(v)==100 for v in grouped.values()) and len(grouped)==4,
         "historical 4-cohort grouped CV invalid")
    crossfit={}
    for mode,z in CONFIDENCES.items():
        par2=0;refpar2=0;changes=0;recover=0;severe=0
        for cohort,held in grouped.items():
            tr=[r for r in e if r["cohort"]!=cohort]
            sig=scales_for(tr)
            for row in held:
                selected,mean,se=predict(tr,sig,row["x"],z)
                par2+=row["cost"][selected]
                refpar2+=row["cost"]["kissat"]
                changes+=selected=="cadical"
                recover+=row["cost"]["kissat"]-row["cost"][selected]>1.0
                severe+=row["cost"][selected]>=2*max(.001,row["cost"]["kissat"])
        crossfit[mode]=dict(heldout_by_historical_cohort=True,reference_Kissat_PAR2_s=round(refpar2,5),
            prediction_PAR2_s=round(par2,5),gain_PAR2_s=round(refpar2-par2,5),
            cadical_routes=changes,material_wins=recover,regressions_2x=severe)
    # Model is a frozen deterministic 400-example local risk model. The cost
    # delta is full paired PAR-2 (no clipping of timeout penalties).
    text="R151_KNN16_V1 "+str(len(e))+" "+str(KNN)+"\n"
    text+=" ".join(format(v,".17g") for v in scale)+"\n"
    for r in e:
        text+=" ".join(format(v,".9g") for v in r["x"]+ [r["delta"]])+"\n"
    MODEL.parent.mkdir(parents=True,exist_ok=True)
    MODEL.write_text(text)
    report=dict(protocol=PROTO,training_sha_known=400,historic_trials=4000,
         model_sha256=sha(MODEL),local_neighbors=KNN,scale=scale,
         policies=CONFIDENCES,grouped_leave_cohort_out_cv=crossfit,
         prior_400_only=True,prospective_new_formula_results_used_for_training=False,
         caveat="Exploratory risk model; the historical dataset may be nonrepresentative and no CV result implies new holdout success")
    write(ROOT/"training.json",report)
    print("R151_TRAIN_FROZEN",json.dumps(report,sort_keys=True),flush=True)
def old_exclusions():
    used=set();urls=set();ids=set();hashes={}
    for name,(path,n) in EXTRA_PRIORS.items():
        p=pathlib.Path(path)
        need(p.is_file(),"missing previous manifest "+name+" "+str(p))
        hashes[name]=sha(p);cs=load(p).get("cases")
        need(isinstance(cs,list) and len(cs)==n,"prior manifest count mismatch "+name)
        for c in cs:
            if c.get("sha256"):used.add(c["sha256"])
            for field in ("url","source_url","download_url","original_url","gbd",
                          "source_identifier","file_id","compressed_file"):
                val=c.get(field)
                if val:
                    val=str(val)
                    if val.startswith(("https://","http://")):urls.add(val)
                    ids.add(val.rsplit("/",1)[-1].split("?")[0])
    need(len(used)>=150,"extra excluded SHA coverage too small")
    return used,urls,ids,hashes
def verify_dimacs(path):
    header=False;nv=nc=total=0;opened=False
    with pathlib.Path(path).open("rb") as f:
        for line in f:
            s=line.strip()
            if not s or s==b"c" or s.startswith((b"c ",b"c\t")):continue
            if s==b"%":break
            if s.startswith(b"p "):
                need(not header,"duplicate DIMACS header")
                t=s.split();need(len(t)==4 and t[:2]==[b"p",b"cnf"],"bad header")
                nv=int(t[2]);nc=int(t[3]);need(nv>0 and nc>0,"nonpositive DIMACS dimensions")
                header=True;continue
            need(header,"literals before header")
            for tok in s.split():
                n=int(tok)
                need(abs(n)<=nv,"literal outside declared vars")
                if n==0:total+=1;opened=False
                else:opened=True
                need(total<=nc,"too many clauses")
    need(header and total==nc and not opened,"incomplete original DIMACS")
    return nv,nc
def freeze():
    base_config()
    excluded,urls,ids,prior_hashes=old_exclusions()
    old_download=b.download
    indexes=set(b.INDEXES.values())
    rejects=collections.Counter()
    def strict_download(url,maximum=8000000):
        if url not in indexes:
            ident=url.rsplit("/",1)[-1].split("?")[0]
            if url in urls or ident in ids:
                rejects["historical_URL_or_ID"]+=1
                raise RuntimeError("R151_EXCLUDED_PRIOR_URL_ID")
        data=old_download(url,maximum)
        if url not in indexes:
            plain=b.unpack(data)
            if hashlib.sha256(plain).hexdigest() in excluded:
                rejects["historical_SHA"]+=1
                raise RuntimeError("R151_EXCLUDED_PRIOR_SHA")
        return data
    b.download=strict_download
    try:
        b.freeze()
    finally:
        b.download=old_download
    manifest=load(SOURCE/"manifest.json")
    selected=manifest["cases"]
    need(32<=len(selected)<=40 and len({c["cohort"] for c in selected})>=3,
         "prospective source coverage insufficient")
    for c in selected:
        need(c["sha256"] not in excluded,"leaked previously evaluated SHA")
        need(c["source_url"] not in urls and c["source_identifier"] not in ids,
             "leaked old source URL/ID")
        nv,nc=verify_dimacs(SOURCE/c["id"])
        need(nv==c["variables"] and nc==c["clauses"],"header mismatch")
    manifest["r151_protocol"]=PROTO
    manifest["r151_extra_prior_manifest_sha256"]=prior_hashes
    manifest["r151_sha_url_id_exclusions"]=sorted(EXTRA_PRIORS)
    manifest["r151_exclusion_rejections"]=dict(rejects)
    manifest["r151_full_DIMACS_clause_validation"]=True
    manifest["r151_no_solver_timed_before_freeze"]=True
    manifest["r151_selection_uninformed_by_runtime"]=True
    write(SOURCE/"manifest.json",manifest)
    print("R151_FREEZE_FINAL",json.dumps(dict(count=len(selected),cohorts=manifest["counts"],
       exclusions=prior_hashes,rejections=dict(rejects),manifest_sha256=sha(SOURCE/"manifest.json")),
       flush=True,sort_keys=True)
def cases():
    base_config()
    cs=b.cases()
    meta=load(SOURCE/"manifest.json")
    need(meta.get("r151_protocol")==PROTO and meta.get("r151_full_DIMACS_clause_validation"),
         "R151 provenance missing")
    need(32<=len(cs)<=40 and len(set(c["sha256"] for c in cs))==len(cs),
         "invalid prospective holdout size")
    return cs
def selector(source,mode):
    t0=time.perf_counter()
    if mode=="r148":
        cmd=[str(R148.resolve()),str(source.resolve())]
        tag="c R148_SELECTOR "
    else:
        cmd=[str(SELECTOR.resolve()),str(source.resolve()),str(MODEL.resolve()),
             str(CONFIDENCES[mode])]
        tag="c R151_SELECTOR "
    out=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                       text=True,timeout=5)
    need(out.returncode==0,"native selector failed "+mode+" "+out.stderr[-250:])
    line=next((s for s in out.stdout.splitlines() if s.startswith(tag)),None)
    need(line is not None,"missing native selector telemetry "+mode)
    fields=dict(re.findall(r"([a-z_]+)=([^\s]+)",line))
    route=fields.get("route","").lower()
    need(route in ("kissat","cadical"),"bad native route "+route)
    extras={}
    if mode.startswith("r151"):
        extras=dict(predicted_delta=float(fields["risk_mean_delta"]),
                    predicted_se=float(fields["risk_se"]),
                    abstained=(fields["abstained"]=="1"))
        need(all(math.isfinite(v) for v in (extras["predicted_delta"],extras["predicted_se"])),
             "nonfinite risk")
    return route,round(time.perf_counter()-t0,6),extras
def trial(src,mode,rep):
    start=time.perf_counter()
    route=mode;cost=0.0;extras={}
    if mode in ("r148","r151_05","r151_15"):
        route,cost,extras=selector(src,mode)
    exe=KISSAT if route=="kissat" else CADICAL
    status="TIMEOUT";proof="timeout"
    elapsed=time.perf_counter()-start
    if elapsed<CAP:
        try:
            p=subprocess.run([str(exe.resolve()),str(src.resolve())],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=CAP-elapsed)
            elapsed=time.perf_counter()-start
            need(p.returncode in (10,20),"backend exit code "+str(p.returncode)+
                 " "+p.stderr[-180:].decode(errors="replace"))
            if elapsed<CAP:
                status="SAT" if p.returncode==10 else "UNSAT"
                if status=="SAT":
                    b.old.witness.check_original_sat(p.stdout,src)
                    proof="source_SAT_witness_verified"
                else:
                    proof="UNSAT_without_independent_LRAT"
        except subprocess.TimeoutExpired:
            elapsed=CAP
    elapsed=min(CAP,elapsed)
    return dict(mode=mode,repeat=rep,route=route,detector_s=cost,
       status=status,seconds=round(elapsed,6),
       par2=30.0 if status=="TIMEOUT" else round(elapsed,6),
       proof=proof,**extras)
def run(shard):
    need(0<=shard<SHARDS,"shard range")
    cs=cases()
    need(all(x.exists() for x in (MODEL,SELECTOR,R148,KISSAT,CADICAL)),
         "missing pinned binary/model")
    if hasattr(os,"sched_getaffinity"):
        cpus=os.sched_getaffinity(0);os.sched_setaffinity(0,{min(cpus)})
    cpu=next((line for line in pathlib.Path("/proc/cpuinfo").read_text().splitlines()
              if line.startswith("model name")),"unknown")
    man_sha=sha(SOURCE/"manifest.json")
    pinned={str(x):sha(x) for x in (MODEL,SELECTOR,R148,KISSAT,CADICAL)}
    rows=[]
    for i,c in enumerate(cs):
        if i%SHARDS!=shard:continue
        src=(SOURCE/c["id"]).resolve()
        need(sha(src)==c["sha256"],"original source sha drift")
        for rep in range(REPS):
            order=list(MODES)
            random.Random(PROTO+"|"+c["sha256"]+"|"+str(rep)).shuffle(order)
            votes=set()
            for mode in order:
                row=dict(protocol=PROTO,source_manifest_sha256=man_sha,shard=shard,
                    id=c["id"],cohort=c["cohort"],sha256=c["sha256"],**trial(src,mode,rep))
                rows.append(row)
                if row["status"]!="TIMEOUT":
                    votes.add(row["status"])
                    need(len(votes)<=1,"SAT UNSAT disagreement "+c["sha256"])
                print("R151_PAIRED",json.dumps(row,sort_keys=True),flush=True)
                write(ROOT/f"shard-{shard}.json",dict(protocol=PROTO,
                    source_manifest_sha256=man_sha,shard=shard,cpu=cpu,pinned=pinned,rows=rows))
    need(len(rows)==len(cs[shard::SHARDS])*REPS*len(MODES),"incomplete benchmark shard")
    print("R151_SHARD_PASS",shard,len(rows),flush=True)
def audit():
    cs=cases()
    man_sha=sha(SOURCE/"manifest.json")
    sh=[load(ROOT/f"shard-{i}.json") for i in range(SHARDS)]
    need(all(x["source_manifest_sha256"]==man_sha and x["protocol"]==PROTO for x in sh),
         "benchmark provenance mismatch")
    need(len(set(json.dumps(x["pinned"],sort_keys=True) for x in sh))==1,
         "pinned reference binaries/model changed")
    rows=[r for s in sh for r in s["rows"]]
    need(len(rows)==len(cs)*REPS*len(MODES),"wrong paired trial count")
    identities={c["sha256"]:c for c in cs}
    keyed={}
    for r in rows:
        c=identities.get(r["sha256"])
        need(c and r["cohort"]==c["cohort"] and r["id"]==c["id"],"source identity drift")
        need(r["mode"] in MODES and r["repeat"] in (0,1),"invalid mode or rep")
        need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"invalid trial status")
        need(0<=r["seconds"]<=CAP and 0<=r["detector_s"]<=CAP,"invalid timed seconds")
        need(abs(r["par2"]-(2*CAP if r["status"]=="TIMEOUT" else r["seconds"]))<1e-4,
             "invalid PAR-2 accounting")
        if r["status"]=="SAT":need(r["proof"]=="source_SAT_witness_verified","no SAT check")
        if r["status"]=="UNSAT":need(r["proof"]=="UNSAT_without_independent_LRAT","false UNSAT certification")
        key=(r["sha256"],r["repeat"],r["mode"])
        need(key not in keyed,"duplicate paired trial")
        keyed[key]=r
    for c in cs:
        for rep in range(REPS):
            votes={keyed[(c["sha256"],rep,m)]["status"] for m in MODES}-{"TIMEOUT"}
            need(len(votes)<=1,"solver disagreement on original CNF")
    summary={}
    for mode in MODES:
        a=[r for r in rows if r["mode"]==mode]
        completed=[r["seconds"] for r in a if r["status"]!="TIMEOUT"]
        detector=[r["detector_s"] for r in a]
        summary[mode]=dict(trials=len(a),solved=len(completed),
             SAT=sum(r["status"]=="SAT" for r in a),
             UNSAT_without_independent_proof=sum(r["status"]=="UNSAT" for r in a),
             timeouts=sum(r["status"]=="TIMEOUT" for r in a),
             PAR2_s=round(sum(r["par2"] for r in a),6),
             median_solved_s=round(statistics.median(completed),6) if completed else None,
             detector_total_s=round(sum(detector),6),
             detector_median_s=round(statistics.median(detector),6))
    per=[]
    for c in cs:
        h=c["sha256"]
        costs={m:sum(keyed[(h,rep,m)]["par2"] for rep in range(REPS)) for m in MODES}
        routes={m:keyed[(h,0,m)]["route"] for m in MODES}
        per.append(dict(id=c["id"],sha256=h,cohort=c["cohort"],**costs,
                        r148_route=routes["r148"],r151_05_route=routes["r151_05"],
                        r151_15_route=routes["r151_15"]))
    comparisons={}
    for mode in ("r151_05","r151_15","r148","cadical"):
        def gain(base):
            return round(100*(summary[base]["PAR2_s"]-summary[mode]["PAR2_s"])/
                         summary[base]["PAR2_s"],6)
        comparisons[mode]=dict(
            gain_vs_Kissat_pct=gain("kissat"),gain_vs_R148_pct=gain("r148"),
            faster_formulas_vs_Kissat=sum(x[mode]<x["kissat"]-1e-5 for x in per),
            slower_formulas_vs_Kissat=sum(x[mode]>x["kissat"]+1e-5 for x in per),
            regressions_2x_vs_Kissat=sum(x[mode]>=2*max(.001,x["kissat"]) for x in per),
            regressions_2x_vs_R148=sum(x[mode]>=2*max(.001,x["r148"]) for x in per),
            bootstrap95_vs_Kissat_pct=b.bootstrap_pairs(per,mode,"kissat"),
            bootstrap95_vs_R148_pct=b.bootstrap_pairs(per,mode,"r148"),
            switch_CaDiCaL_to_Kissat=sum(x["r148_route"]=="cadical" and
                                       x.get(mode+"_route")=="kissat" for x in per) if mode.startswith("r151") else 0,
            switch_Kissat_to_CaDiCaL=sum(x["r148_route"]=="kissat" and
                                       x.get(mode+"_route")=="cadical" for x in per) if mode.startswith("r151") else 0)
    by_cohort={co:dict(formulas=sum(c["cohort"]==co for c in cs),
       PAR2={m:round(sum(r["par2"] for r in rows if r["mode"]==m and r["cohort"]==co),6)
             for m in MODES},
       solved={m:sum(r["status"]!="TIMEOUT" for r in rows if r["mode"]==m and r["cohort"]==co)
               for m in MODES}) for co in sorted(set(c["cohort"] for c in cs))}
    report=dict(protocol=PROTO,verdict="RESEARCH_ONLY_NO_AUTOMATIC_PROMOTION",
        formula_count=len(cs),measurements=len(rows),shards=SHARDS,repeats=REPS,cap_s=CAP,
        source_manifest_sha256=man_sha,source_sha_verified=True,
        strict_SHA_URL_ID_exclusions=load(SOURCE/"manifest.json")["r151_sha_url_id_exclusions"],
        training_source_reuse=False,source_phase="FROZEN_BEFORE_FIRST_SOLVER_TIMING",
        model_sha256=sha(MODEL),pinned=sh[0]["pinned"],
        CPU_models=[s["cpu"] for s in sh],summary=summary,comparisons=comparisons,
        by_cohort=by_cohort,independent_UNSAT_proof=False,
        caveats=["R151 historical train from 400 previously used CNFs",
            "Prospective SHA/URL/ID excludes specified prior ledgers, not every historical DRNAS source",
            "GitHub shard CPU heterogeneity; paired modes share each shard, but subsecond noise remains",
            "15s cap cannot distinguish most hard formulas that time out",
            "Original SAT witness verification yes; UNSAT independently unproven",
            "No promotion without fresh holdout replication and proof/stability checks"])
    write(ROOT/"report.json",report)
    with (ROOT/"paired.csv").open("w",newline="") as f:
        keys=sorted({k for row in rows for k in row})
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
    with (ROOT/"per_formula.csv").open("w",newline="") as f:
        keys=list(per[0])
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(per)
    print("R151_FINAL",json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("step",choices=("train","freeze","run","audit"))
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    {"train":train,"freeze":freeze,"run":lambda:run(args.shard),"audit":audit}[args.step]()
