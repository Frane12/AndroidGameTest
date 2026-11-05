#!/usr/bin/env python3
"""DRNAS R150: new SHA-disjoint external experiment, frozen ridge16 routing.

Train only from pre-existing R135S 400 paired measurements (retrospective);
evaluate native R150 versus frozen R148/Kissat/CaDiCaL only on newly frozen
external original CNFs. No clause changes, no V15.3.1 changes, no promotion.
"""
import argparse,bz2,collections,csv,gzip,hashlib,io,json,lzma,math,os,pathlib,random,re,statistics,subprocess,sys,time,urllib.request
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r135_nonxor_portfolio as old

ROOT=pathlib.Path("r150")
INPUT=pathlib.Path("r150-history")
SOURCES=ROOT/"holdout"
TRAIN_ORIGINAL="619665dd5f4ba6680b11200a63ac77ecc706c9897317b5452dbf22a82ef4b787"
PROTO="DRNAS-R150-FROZEN-COST-AWARE-STRUCTURE-PROSPECTIVE-20261105-v1"
FEATURE=ROOT/"r150_features"
R148=ROOT/"r148_selector"
MODEL=ROOT/"model.txt"
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
CADICAL=pathlib.Path("built/bin/cadical_3_0_1")
CAP=15.0; REPS=2; SHARDS=8
MODES=("kissat","cadical","r148","r150_02","r150_07")
QUOTAS={"official2026":20,"official2025":15,"miter":10,"cryptography":10}
INDEXES={
 "official2026":"https://raw.githubusercontent.com/satcompetition/2026/main/downloads/track_main_2026.uri",
 "official2025":"https://raw.githubusercontent.com/satcompetition/2025/main/downloads/SC2025.uri",
 "miter":"https://benchmark-database.de/getinstances?query=family%3Dmiter&context=cnf",
 "cryptography":"https://benchmark-database.de/getinstances?query=family%3Dcryptography&context=cnf"
}
FEATURE_DIM=16

def need(cond,msg):
    if not cond:raise RuntimeError("R150_AUDIT_REFUSED "+str(msg))
def sha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open("rb") as f:
        for block in iter(lambda:f.read(1<<20),b""):h.update(block)
    return h.hexdigest()
def jwrite(path,data):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
def load(path):
    return json.loads(pathlib.Path(path).read_text())
def csvrows(path):
    with path.open(newline="") as f:return list(csv.DictReader(f))
def locate(name):
    a=list(INPUT.rglob(name))
    need(len(a)==1,"expected exactly one "+name+" "+repr(a))
    return a[0]
def sources_old():
    old.ROOT=ROOT/"train-unpacked";old.SOURCE=pathlib.Path("holdout-400")
    x,cases=old.read_sources()
    need(x==TRAIN_ORIGINAL and len(cases)==400 and len({c["sha256"] for c in cases})==400,
         "training source drift")
    return cases
def compute_feature(path):
    p=subprocess.run([str(FEATURE.resolve()),str(pathlib.Path(path).resolve())],
      capture_output=True,text=True,timeout=5)
    need(p.returncode==0,"feature process failure "+p.stderr[-200:])
    line=next((s for s in p.stdout.splitlines() if s.startswith("c R150_FEATURE ")),None)
    need(line is not None,"feature record missing")
    fields=dict(re.findall(r"([a-z_]+)=([^\s]+)",line))
    x=[float(v) for v in fields["x"].split(",")]
    need(len(x)==FEATURE_DIM and all(math.isfinite(v) and 0<=v<=1 for v in x),
         "nonfinite or wrong dimension")
    return x
def linear_solve(mat,v):
    a=[list(row)+[v[i]] for i,row in enumerate(mat)]
    n=len(a)
    for i in range(n):
        k=max(range(i,n),key=lambda q:abs(a[q][i]))
        need(abs(a[k][i])>1e-10,"noninvertible ridge")
        a[i],a[k]=a[k],a[i]
        d=a[i][i]
        for j in range(i,n+1):a[i][j]/=d
        for k in range(n):
            if k==i:continue
            mult=a[k][i]
            for j in range(i,n+1):a[k][j]-=mult*a[i][j]
    return [a[i][-1] for i in range(n)]
def ridge(rows):
    dim=FEATURE_DIM+1
    mat=[[0.0]*dim for _ in range(dim)];rhs=[0.0]*dim
    for r in rows:
        x=[1.0]+r["x"]
        y=r["target"]
        for i in range(dim):
            rhs[i]+=x[i]*y
            for j in range(dim):mat[i][j]+=x[i]*x[j]
    for i in range(1,dim):mat[i][i]+=8.0
    mat[0][0]+=0.00001
    w=linear_solve(mat,rhs)
    need(len(w)==dim and all(math.isfinite(a) for a in w),"model failure")
    return w
def predict(w,x):
    return w[0]+sum(a*b for a,b in zip(w[1:],x))
def route(base,score,threshold):
    return ("cadical" if score>0 else "kissat") if abs(score)>=threshold else base
def train():
    cases=sources_old()
    paired=csvrows(locate("paired.csv"))
    per=csvrows(locate("per_formula.csv"))
    need(len(per)==400 and len(paired)==4000,"historical evidence incomplete")
    base={r["sha256"]:r for r in per}
    need(len(base)==400,"duplicate original per formula rows")
    groups=collections.defaultdict(dict)
    for r in paired:
        need(r["sha256"] in base and r["repeat"] in ("0","1"),"bad paired identity")
        need(r["mode"] in ("kissat","cadical","r118","r135","r135s"),"bad paired mode")
        key=(r["repeat"],r["mode"])
        need(key not in groups[r["sha256"]],"duplicate trial")
        groups[r["sha256"]][key]=r
    examples=[]
    for c in cases:
        k=c["sha256"];r=base[k]
        need(k in groups and len(groups[k])==10 and r["cohort"]==c["cohort"],"paired cohort drift")
        totals={}
        for m in ("kissat","cadical"):
            trials=[groups[k][(str(rep),m)] for rep in (0,1)]
            for t in trials:
                need(t["status"] in ("SAT","UNSAT","TIMEOUT"),"bad status")
                need(abs(float(t["par2"])-(30.0 if t["status"]=="TIMEOUT"
                        else float(t["seconds"])))<0.0001,"wrong historical PAR2")
            totals[m]=sum(float(t["par2"]) for t in trials)
            need(abs(totals[m]-float(r[m+"_par2_s"]))<0.0002,"historical totals mismatch")
        x=compute_feature(c["id"])
        delta=totals["kissat"]-totals["cadical"] # positive: CaDiCaL better
        examples.append(dict(sha=k,cohort=c["cohort"],base=r["r135_route"].lower(),
                             x=x,target=max(-1,min(1,delta/15.0)),cost=totals))
    need(len(examples)==400,"training examples missing")
    # Five-fold historical cross-fit. This is reused data, never new evidence.
    folds={}
    for co in ("official","external_application","external_xor","external_nonxor"):
        a=sorted([r for r in examples if r["cohort"]==co],key=lambda r:r["sha"])
        need(len(a)==100,"historic cohort imbalance")
        for i,r in enumerate(a):folds[r["sha"]]=i%5
    cv={}
    for t in (0.02,0.07):
        gain=0.;chosen=0;reg=0
        for fold in range(5):
            w=ridge([r for r in examples if folds[r["sha"]]!=fold])
            for r in examples:
                if folds[r["sha"]]!=fold:continue
                selected=route(r["base"],predict(w,r["x"]),t)
                if selected!=r["base"]:
                    chosen+=1
                    gain+=r["cost"][r["base"]]-r["cost"][selected]
                    reg+=(r["cost"][selected]>=2*max(.001,r["cost"][r["base"]]))
        cv[str(t)]=dict(route_changes=chosen,gain_PAR2_s=round(gain,6),
                         regressions_2x=reg,kind="RETROSPECTIVE_CROSSFIT_REUSED_400")
    w=ridge(examples)
    MODEL.write_text("R150_RIDGE16_V1\n"+" ".join(format(x,".17g") for x in w)+"\n")
    report=dict(protocol=PROTO,training=400,source_sha256=TRAIN_ORIGINAL,
          historic_trials=4000,model_sha256=sha(MODEL),ridge_lambda=8.,
          dimension=FEATURE_DIM,model_weights=w,
          frozen_thresholds=[.02,.07],retrospective_cv=cv,
          source_tier="ALREADY_USED_400_NOT_INDEPENDENT",
          new_SAT_solver_executions=0,
          claim="No native performance claim; model trained on reused 400")
    jwrite(ROOT/"training.json",report)
    print("R150_TRAIN_FROZEN",json.dumps(report,sort_keys=True),flush=True)

def download(url,maximum=8_000_000):
    req=urllib.request.Request(url,headers={"User-Agent":"DRNAS-R150-Prospective-2026/1.0"})
    with urllib.request.urlopen(req,timeout=20) as f:data=f.read(maximum+1)
    need(len(data)<=maximum,"download cap exceeded")
    return data
def unpack(data):
    if data.startswith(b"\x1f\x8b"):f=gzip.GzipFile(fileobj=io.BytesIO(data))
    elif data.startswith(b"BZh"):f=bz2.BZ2File(io.BytesIO(data))
    elif data.startswith(b"\xfd7zXZ"):f=lzma.LZMAFile(io.BytesIO(data))
    else:return data
    with f:x=f.read(8_000_001)
    need(len(x)<=8_000_000,"decompressed source cap exceeded")
    return x
def freeze():
    # Exclude original 400 training and previous R132 125 sources (SHA+URL+id).
    src=sources_old()
    used={x["sha256"] for x in src}
    prior=pathlib.Path("r150-prior-r132/manifest.json")
    need(prior.exists(),"missing prior R132 provenance ledger")
    meta=load(prior)
    oldcases=meta.get("cases")
    need(isinstance(oldcases,list) and len(oldcases)==125,"R132 manifest count")
    used.update(c["sha256"] for c in oldcases)
    knownurls={x.get("url") for x in oldcases if x.get("url")}
    knownids={x.get("gbd") for x in oldcases if x.get("gbd")}
    SOURCES.mkdir(parents=True,exist_ok=True)
    accepted=[];rejected=collections.Counter();index_meta={}
    for cohort,uri in INDEXES.items():
        target=QUOTAS[cohort]
        try:
            raw=download(uri,4_000_000)
            urls=sorted({x.strip() for x in raw.decode().splitlines()
                         if x.strip().startswith(("http://","https://"))})
            need(bool(urls),"index contains no external URLs")
        except Exception as ex:
            index_meta[cohort]=dict(error=str(ex)[:180],uri=uri,accepted=0)
            rejected[cohort+"_index_error"]+=1
            continue
        rng=random.Random(PROTO+"|SOURCE-FREEZE|"+cohort)
        rng.shuffle(urls)
        index_meta[cohort]=dict(index_sha256=hashlib.sha256(raw).hexdigest(),
                                urls=len(urls),uri=uri,target=target)
        trials=0;n=0
        for url in urls:
            if n>=target or trials>=90:break
            identity=url.rsplit("/",1)[-1].split("?")[0]
            if url in knownurls or identity in knownids:
                rejected[cohort+"_prior_URI"]+=1;continue
            trials+=1
            try:
                packed=download(url)
                plain=unpack(packed)
                need(0<len(plain)<=8_000_000,"input bytes cap")
                h=hashlib.sha256(plain).hexdigest()
                if h in used:
                    rejected[cohort+"_prior_SHA"]+=1;continue
                headers=[line.split() for line in plain.splitlines()
                         if line.startswith(b"p cnf ")]
                need(len(headers)==1 and len(headers[0])==4,"invalid DIMACS header")
                nv,nc=(int(v) for v in headers[0][2:])
                need(nv>0 and nc>0,"empty dimensions")
                file=f"{cohort}-{n:03d}.cnf"
                (SOURCES/file).write_bytes(plain)
                accepted.append(dict(id=file,cohort=cohort,sha256=h,
                    source_url=url,source_identifier=identity,source_catalog=uri,
                    packed_sha256=hashlib.sha256(packed).hexdigest(),
                    variables=nv,clauses=nc,bytes=len(plain),
                    official_uri_catalog=(cohort.startswith("official"))))
                used.add(h);knownurls.add(url);knownids.add(identity);n+=1
                print("R150_FROZEN_NEW_CNF",cohort,n,h[:16],flush=True)
            except Exception as ex:
                rejected[cohort+"_invalid_or_unreachable"]+=1
        index_meta[cohort]["attempts"]=trials
        index_meta[cohort]["accepted"]=n
    counts=dict(collections.Counter(c["cohort"] for c in accepted))
    need(len(accepted)>=24 and len(counts)>=2,
         "insufficient new original external sources "+str(counts))
    need(len({x["sha256"] for x in accepted})==len(accepted),"duplicate new SHA")
    report=dict(protocol=PROTO,phase="FROZEN_BEFORE_ANY_R150_SOLVER_TIMINGS",
       original_SHA_disjoint_from_400=True,
       SHA_disjoint_from_R132=True,
       provenance_exclusion_scope="R135S original 400 and R132 125; NOT exhaustive of all older DRNAS tests",
       original_400_manifest_sha256=TRAIN_ORIGINAL,
       r132_prior_manifest_sha256=sha(prior),
       source_indexes=index_meta,rejections=dict(rejected),
       counts=counts,cases=accepted,cap_s=CAP,repeats=REPS,shards=SHARDS,
       prior_model_not_tuned_on_sources=True)
    jwrite(SOURCES/"manifest.json",report)
    print("R150_FROZEN_FINAL",json.dumps({k:report[k] for k in
          ("counts","rejections","source_indexes")},sort_keys=True),flush=True)

def cases():
    m=load(SOURCES/"manifest.json")
    need(m["protocol"]==PROTO and m["phase"]=="FROZEN_BEFORE_ANY_R150_SOLVER_TIMINGS",
         "invalid prospective manifest")
    cs=m["cases"];need(len(cs)>=24 and len({c["sha256"] for c in cs})==len(cs),"bad input count")
    for c in cs:
        p=SOURCES/c["id"]
        need(p.is_file() and sha(p)==c["sha256"],"new original CNF sha drift")
    return cs
def native(src,mode):
    st=time.perf_counter()
    p=subprocess.run([str(R148.resolve()),str(src.resolve())],text=True,capture_output=True,timeout=5)
    need(p.returncode==0,"R148 native failed "+p.stderr[-150:])
    found=next((s for s in p.stdout.splitlines() if s.startswith("c R148_SELECTOR ")),None)
    need(found is not None,"R148 telemetry absent")
    fields=dict(re.findall(r"([a-z_]+)=([^\s]+)",found))
    base=fields["route"]
    need(base in ("KISSAT","CADICAL"),"unrecognized R148 route")
    selected=base;score=None;changed=False
    if mode.startswith("r150"):
        t=.02 if mode=="r150_02" else .07
        args=[str(FEATURE.resolve()),str(src.resolve()),str(MODEL.resolve()),base,str(t)]
        q=subprocess.run(args,capture_output=True,text=True,timeout=5)
        need(q.returncode==0,"R150 native failed "+q.stderr[-150:])
        line=next((s for s in q.stdout.splitlines() if s.startswith("c R150_FEATURE ")),None)
        need(line is not None,"R150 telemetry missing")
        f=dict(re.findall(r"([a-z_]+)=([^\s]+)",line))
        selected=f["route"];score=float(f["score"]);changed=selected!=base
        need(selected in ("KISSAT","CADICAL"),"R150 unrecognized route")
    return selected,base,score,changed,round(time.perf_counter()-st,6)
def solve(src,mode,rep):
    start=time.perf_counter();sel=None;base=None;score=None;changed=False;cost=0.0
    if mode in ("r148","r150_02","r150_07"):
        sel,base,score,changed,cost=native(src,mode)
        route=sel.lower()
    else:route=mode
    exe=KISSAT if route=="kissat" else CADICAL
    cmd=[str(exe.resolve()),str(src.resolve())]
    elapsed=time.perf_counter()-start
    status="TIMEOUT";proof="timeout"
    if elapsed<CAP:
        try:
            p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=CAP-elapsed)
            elapsed=time.perf_counter()-start
            need(p.returncode in (10,20),"backend exit "+str(p.returncode)+
                 " "+p.stderr[-150:].decode(errors="replace"))
            if elapsed<CAP:
                status="SAT" if p.returncode==10 else "UNSAT"
                if status=="SAT":
                    old.witness.check_original_sat(p.stdout,src)
                    proof="source_SAT_witness_verified"
                else:proof="UNSAT_without_independent_LRAT"
        except subprocess.TimeoutExpired:
            elapsed=CAP
    elapsed=min(elapsed,CAP)
    return dict(mode=mode,repeat=rep,route=route,baseline=base,
        selected=sel,score=score,override=changed,detector_s=cost,
        status=status,seconds=round(elapsed,6),
        par2=30.0 if status=="TIMEOUT" else round(elapsed,6),proof=proof)
def run(shard):
    need(0<=shard<SHARDS,"shard range")
    cs=cases()
    need(MODEL.exists() and FEATURE.exists() and R148.exists() and
         KISSAT.exists() and CADICAL.exists(),"missing frozen model or binary")
    if hasattr(os,"sched_getaffinity"):
        aff=os.sched_getaffinity(0)
        os.sched_setaffinity(0,{min(aff)})
    source_manifest=sha(SOURCES/"manifest.json")
    pins={str(p):sha(p) for p in (FEATURE,R148,KISSAT,CADICAL,MODEL)}
    cpu=next((x for x in pathlib.Path("/proc/cpuinfo").read_text().splitlines()
              if x.startswith("model name")),"unknown")
    rows=[]
    for i,c in enumerate(cs):
        if i%SHARDS!=shard:continue
        src=(SOURCES/c["id"]).resolve()
        need(sha(src)==c["sha256"],"source SHA changed")
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(modes)
            votes=set()
            for mode in modes:
                row=dict(protocol=PROTO,source_manifest_sha256=source_manifest,
                         shard=shard,sha256=c["sha256"],cohort=c["cohort"],id=c["id"],
                         **solve(src,mode,rep))
                rows.append(row)
                if row["status"]!="TIMEOUT":
                    votes.add(row["status"])
                    need(len(votes)==1,"SAT/UNSAT disagreement on original "+c["sha256"])
                print("R150_PAIRED",json.dumps(row,sort_keys=True),flush=True)
                jwrite(ROOT/f"shard-{shard}.json",
                       dict(protocol=PROTO,shard=shard,source_manifest_sha256=source_manifest,
                            cpu=cpu,pinned=pins,rows=rows))
    need(len(rows)==len(cs[shard::SHARDS])*REPS*len(MODES),"shard incomplete")
    print("R150_SHARD_PASS",shard,len(rows),flush=True)
def bootstrap_pairs(per,a,b):
    rng=random.Random(15020261105)
    categories=sorted({x["cohort"] for x in per})
    by={c:[x for x in per if x["cohort"]==c] for c in categories}
    ratios=[]
    for _ in range(2000):
        draw=[rng.choice(by[c]) for c in categories for __ in range(len(by[c]))]
        baseline=sum(x[b] for x in draw);candidate=sum(x[a] for x in draw)
        ratios.append(100*(baseline-candidate)/baseline if baseline else 0)
    ratios.sort()
    return [round(ratios[49],6),round(ratios[1949],6)]
def audit():
    cs=cases();manifest=sha(SOURCES/"manifest.json")
    shards=[load(ROOT/f"shard-{i}.json") for i in range(SHARDS)]
    need(all(x["protocol"]==PROTO and x["source_manifest_sha256"]==manifest for x in shards),
         "shard source/protocol mismatch")
    need(len({json.dumps(x["pinned"],sort_keys=True) for x in shards})==1,
         "pinned binaries or frozen model changed")
    rows=[r for sh in shards for r in sh["rows"]]
    need(len(rows)==len(cs)*REPS*len(MODES),"missing prospective trial rows")
    bysha={c["sha256"]:c for c in cs}
    idx={}
    for r in rows:
        c=bysha.get(r["sha256"])
        need(c and c["cohort"]==r["cohort"] and c["id"]==r["id"],"SHA/ID/cohort drift")
        need(r["mode"] in MODES and r["repeat"] in (0,1),"bad mode or repeat")
        need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"unrecognized status")
        need(abs(r["par2"]-(30 if r["status"]=="TIMEOUT" else r["seconds"]))<1e-4,"bad PAR2")
        if r["status"]=="SAT":need(r["proof"]=="source_SAT_witness_verified","no SAT witness")
        if r["status"]=="UNSAT":need(r["proof"]=="UNSAT_without_independent_LRAT","proof tier mismatch")
        key=(r["sha256"],r["repeat"],r["mode"])
        need(key not in idx,"duplicate trial");idx[key]=r
    for c in cs:
        for rep in range(REPS):
            vals={idx[(c["sha256"],rep,m)]["status"] for m in MODES}-{"TIMEOUT"}
            need(len(vals)<=1,"SAT/UNSAT disagreement")
    summary={}
    for m in MODES:
        x=[r for r in rows if r["mode"]==m]
        summary[m]=dict(trials=len(x),solved=sum(r["status"]!="TIMEOUT" for r in x),
           SAT=sum(r["status"]=="SAT" for r in x),
           UNSAT_without_independent_proof=sum(r["status"]=="UNSAT" for r in x),
           timeouts=sum(r["status"]=="TIMEOUT" for r in x),
           PAR2_s=round(sum(r["par2"] for r in x),6),
           selector_overrides=sum(r["override"] for r in x),
           detector_total_s=round(sum(r["detector_s"] for r in x),6),
           detector_median_s=round(statistics.median(r["detector_s"] for r in x),6))
    per=[]
    for c in cs:
        h=c["sha256"];cost={m:sum(idx[(h,rep,m)]["par2"] for rep in range(REPS)) for m in MODES}
        per.append(dict(sha256=h,cohort=c["cohort"],**cost))
    comparisons={}
    for m in ("r150_02","r150_07"):
        comparisons[m]=dict(
           vs_r148_gain_pct=round(100*(summary["r148"]["PAR2_s"]/summary[m]["PAR2_s"]-1),6),
           vs_Kissat_gain_pct=round(100*(summary["kissat"]["PAR2_s"]/summary[m]["PAR2_s"]-1),6),
           vs_r148_bootstrap95_pct=bootstrap_pairs(per,m,"r148"),
           wins_2x_vs_r148=sum(x["r148"]>=2*x[m] for x in per),
           regressions_2x_vs_r148=sum(x[m]>=2*x["r148"] for x in per),
           faster_formulas=sum(x[m]<x["r148"]-1e-5 for x in per),
           slower_formulas=sum(x[m]>x["r148"]+1e-5 for x in per))
    by_cohort={co:dict(formulas=sum(c["cohort"]==co for c in cs),
           PAR2={m:round(sum(r["par2"] for r in rows if r["mode"]==m and r["cohort"]==co),6)
                for m in MODES}) for co in sorted(set(c["cohort"] for c in cs))}
    report=dict(protocol=PROTO,phase="NEW_SHA_EXCLUDED_EXTERNAL_TEST",formula_count=len(cs),
       measurements=len(rows),shards=SHARDS,source_manifest_sha256=manifest,
       source_sha_verified=True,model_sha256=sha(MODEL),
       original_CNF_unchanged=True,strict_train_source_400_disjoint=True,
       cohort_counts=dict(collections.Counter(c["cohort"] for c in cs)),
       primary_comparator="r148 exact frozen route; 2x regressions and stratified per-formula bootstrap",
       summary=summary,by_cohort=by_cohort,comparisons=comparisons,
       cpu_by_shard=[sh["cpu"] for sh in shards],
       independently_verified_UNSAT=False,
       claimed_world_record=False,
       caveats=["New SHA-disjoint vs old 400 + R132, but not exhaustively all historical DRNAS sources",
               "Official 2026/2025 refers to source catalog, NOT official ranking or an official solver run",
               "Cross-runner CPU heterogeneity can affect subsecond performance",
               "No independent LRAT/FRAT UNSAT validation"],
       verdict="RESEARCH_ONLY_NO_AUTOMATIC_PROMOTION")
    jwrite(ROOT/"report.json",report)
    with (ROOT/"paired.csv").open("w",newline="") as f:
        fieldnames=sorted({k for r in rows for k in r})
        w=csv.DictWriter(f,fieldnames=fieldnames);w.writeheader();w.writerows(rows)
    with (ROOT/"per_formula.csv").open("w",newline="") as f:
        fieldnames=list(per[0].keys())
        w=csv.DictWriter(f,fieldnames=fieldnames);w.writeheader();w.writerows(per)
    print("R150_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("step",choices=("train","freeze","run","audit"))
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    {"train":train,"freeze":freeze,"run":lambda:run(args.shard),"audit":audit}[args.step]()
