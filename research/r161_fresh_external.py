#!/usr/bin/env python3
"""R161 prospective external original-CNF SHA holdout.

The input files are frozen BEFORE any R161 solver measurement. Exclusions:
the successful cumulative SQLite 2979-formula snapshot; R135S 400 original
CNFs; R132 125; R148 50; R150 55; R151 40; R154 mixed 12 and
R158 industrial 20. Both content hashes and source URL/GBD IDs checked.
This is source-disjoint from these pinned audited sets, not a claim that
every formula on Earth or all private experiments have been checked.

All four actual strategies use SAME original CNFs, 3 repeats, 8s cap,
CPU affinity, pinned ref binaries. R160 category portfolio is a frozen
negative-control policy learned on R159; NO adaptation on R160/R161 timings.
R158 graph descriptors are SHADOW ONLY and excluded from timing.
No modifications of V15.3.1 or any native solver source.
"""
import argparse,bz2,collections,csv,gzip,hashlib,io,json,lzma,math,os,platform
import random,statistics,sys,time,urllib.request
from pathlib import Path

sys.path.insert(0,"research")
sys.path.insert(0,"experiments/drnas_v16")
import r160_portfolio_transfer as prior
import r158_features as geom

ROOT=Path("r161")
FROZEN=ROOT/"frozen"
PRIOR=Path("r161-prior")
CAP=8.0
REPEATS=3
SHARDS=4
QUOTA={"official2026":6,"official2025":6,"miter":6,"cryptography":6}
MODES=("original_kissat","stable_v1531","cadical","r161_portfolio")
PROTO="DRNAS-R161-PROSP-NEW-SOURCE-SHA-AUDITED-20261106-v1"
INDEXES={
 "official2026":"https://raw.githubusercontent.com/satcompetition/2026/main/downloads/track_main_2026.uri",
 "official2025":"https://raw.githubusercontent.com/satcompetition/2025/main/downloads/SC2025.uri",
 "miter":"https://benchmark-database.de/getinstances?query=family%3Dmiter&context=cnf",
 "cryptography":"https://benchmark-database.de/getinstances?query=family%3Dcryptography&context=cnf"
}
MAX_BYTES=8_000_000
MAX_ATTEMPTS_PER_COHORT=110
SOURCE_FILES={
 "analytics":("analytics/formulas.csv",2979),
 "r135s":("r135s/per_formula.csv",400),
 "r132":("r132/frozen/manifest.json",125),
 "r148":("r148/frozen/manifest.json",50),
 "r150":("r150/holdout/manifest.json",55),
 "r151":("r151/holdout/manifest.json",40),
 "r154mix":("r154mix/frozen/manifest.json",12),
 "r158industrial":("r158industrial/frozen/manifest.json",20),
}
PORTFOLIO=PRIOR/"r160"/"r160/frozen/manifest.json"

def need(ok,msg):
    if not ok:raise RuntimeError("R161_FAIL_CLOSED "+str(msg))
def sha(data):
    h=hashlib.sha256()
    if isinstance(data,Path):
        with data.open("rb") as f:
            for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    else:h.update(data)
    return h.hexdigest()
def readcsv(path):
    with Path(path).open(newline="") as f:return list(csv.DictReader(f))
def save(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def writecsv(path,rs):
    need(rs,"empty CSV")
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    columns=list(dict.fromkeys(k for r in rs for k in r))
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=columns,extrasaction="raise")
        w.writeheader();w.writerows(rs)
def inventory():
    hashes=set();urls=set();ids=set();audit={}
    for name,(path,expected) in SOURCE_FILES.items():
        p=PRIOR/path
        need(p.is_file(),"missing historical source "+str(p))
        if p.suffix==".csv":
            rows=readcsv(p)
            need(len(rows)==expected,"historic row count "+name+" "+str(len(rows)))
        else:
            data=json.loads(p.read_text())
            rows=data["cases"]
            need(len(rows)==expected,"historic manifest case count "+name)
        for c in rows:
            for field in ("formula_sha256","sha256","source_sha256",
                          "original_sha256","original_bytes_sha256","raw_source_sha256"):
                h=str(c.get(field) or "").lower()
                if len(h)==64 and all(d in "0123456789abcdef" for d in h):
                    hashes.add(h)
            for field in ("url","source_url","original_url","download_url"):
                u=str(c.get(field) or "").strip()
                if u.startswith(("http://","https://")):
                    urls.add(u);ids.add(u.rsplit("/",1)[-1].split("?")[0])
            for field in ("source_identifier","gbd","id"):
                ident=str(c.get(field) or "").strip()
                if len(ident)==32 and all(x in "0123456789abcdefABCDEF" for x in ident):
                    ids.add(ident.lower())
        audit[name]=dict(artifact_path=path,records=len(rows),sha256=sha(p))
    need(len(hashes)>3000,"historical SHA coverage incomplete")
    portfolio=json.loads(PORTFOLIO.read_text())
    need(portfolio["protocol"]=="R160-AUDITED-R159-COHORT-PORTFOLIO-COMPLEMENT-20261106-v1"
         and portfolio["status"]=="FROZEN_BEFORE_R160_RUNTIME"
         and portfolio["trained_on_only_R159_16"] is True
         and len(portfolio["portfolio"])==4,"portfolio provenance mismatch")
    routing={k:v["selected"] for k,v in portfolio["portfolio"].items()}
    need(set(routing)==set(QUOTA) and
         set(routing.values())<=set(MODES[:-1]),"invalid frozen portfolio")
    audit["portfolio_r160_precommitted_sha256"]=sha(PORTFOLIO)
    return hashes,urls,ids,audit,routing

def get(url,limit):
    request=urllib.request.Request(url,headers={"User-Agent":"DRNAS-R161-Prospective-External-Source-Audit/1.0"})
    with urllib.request.urlopen(request,timeout=12) as reply:
        data=reply.read(limit+1)
    need(len(data)<=limit,"download exceeds source budget")
    return data
def unpack(data):
    if data.startswith(b"\x1f\x8b"):
        f=gzip.GzipFile(fileobj=io.BytesIO(data))
    elif data.startswith(b"BZh"):
        f=bz2.BZ2File(io.BytesIO(data))
    elif data.startswith(b"\xfd7zXZ"):
        f=lzma.LZMAFile(io.BytesIO(data))
    else:return data
    with f:raw=f.read(MAX_BYTES+1)
    need(len(raw)<=MAX_BYTES,"decompressed input exceeds budget")
    return raw
def dimensions(data):
    """Full token-level DIMACS validation: clauses may span lines."""
    stream=io.BytesIO(data)
    n=declared=None;seen=0;pending=0
    for line in stream:
        s=line.strip()
        if not s or s.startswith((b"c ",b"c\t",b"c\n")) or s==b"c":
            continue
        if s==b"%" or s.startswith(b"% "):break
        if s.startswith(b"p "):
            chunks=s.split()
            need(n is None and len(chunks)==4 and chunks[1]==b"cnf",
                 "DIMACS header")
            n,declared=int(chunks[2]),int(chunks[3])
            need(1<=n<=50000 and 1<=declared<=600000,"DIMACS dimension budget")
            continue
        need(n is not None,"clauses before header")
        for token in s.split():
            lit=int(token)
            need(abs(lit)<=n,"literal exceeds header")
            if lit:
                pending+=1
                need(pending<=100000,"clause too wide")
            else:
                seen+=1;pending=0
                need(seen<=declared,"too many clauses")
    need(n is not None and seen==declared and pending==0,
         "missing/truncated DIMACS clauses")
    return n,declared

def freeze():
    known,urls,ids,historical,choice=inventory()
    candidates=[];indices={};rejections=collections.Counter()
    FROZEN.mkdir(parents=True,exist_ok=True)
    for cohort,uri in INDEXES.items():
        index=get(uri,4_000_000)
        listed=sorted({line.strip() for line in index.decode().splitlines()
                       if line.strip().startswith(("http://","https://"))})
        need(len(listed)>=QUOTA[cohort],"no source catalog "+cohort)
        random.Random(PROTO+"|source-selection|"+cohort).shuffle(listed)
        indices[cohort]=dict(index_url=uri,index_sha256=sha(index),
                             candidate_urls=len(listed))
        attempted=0;selected=0
        for url in listed:
            if selected>=QUOTA[cohort] or attempted>=MAX_ATTEMPTS_PER_COHORT:break
            ident=url.rsplit("/",1)[-1].split("?")[0].lower()
            if url in urls or ident in ids:
                rejections[cohort+":prior-URL-ID"]+=1
                continue
            attempted+=1
            try:
                packed=get(url,MAX_BYTES)
                plain=unpack(packed)
                need(100<=len(plain)<=MAX_BYTES,"CNF size bound")
                digest=sha(plain)
                need(digest not in known,"historically used SHA")
                n,nc=dimensions(plain)
                name="%s-%03d.cnf"%(cohort,selected)
                (FROZEN/name).write_bytes(plain)
                candidates.append(dict(id=name,cohort=cohort,
                    sha256=digest,packed_sha256=sha(packed),
                    source_url=url,source_id=ident,source_catalog=uri,
                    variables=n,clauses=nc,bytes=len(plain)))
                known.add(digest);urls.add(url);ids.add(ident)
                selected+=1
                print("R161_NEW_ORIGINAL",cohort,selected,name,digest,flush=True)
            except Exception as exc:
                rejections[cohort+":invalid-large-unreachable"]+=1
        indices[cohort].update(attempted_downloads=attempted,accepted=selected)
        need(selected==QUOTA[cohort],"insufficient strictly new CNFs "+cohort+
             " "+str(indices[cohort])+" rejects="+str(rejections))
    need(len(candidates)==24 and len({x["sha256"] for x in candidates})==24,
         "duplicate or incomplete prospective new source")
    manifest=dict(protocol=PROTO,status="FROZEN_BEFORE_ANY_R161_TIMING",
        source_class="NEW_SHA_OUTSIDE_EXPLICIT_AUDITED_HISTORICAL_REGISTRY",
        external_original_CNFs_not_modified=True,
        certified_globally_virgin=False,
        official_catalog_not_official_competition_result=True,
        all_SAT_witness_requires_check=True,
        original_history=historical,history_source_run=42044317651,
        original_history_snapshot_artifact=13423658142,
        r161_source_registry_hash_count=len(known),
        historical_exclusion_checks="source SHA + raw SHA + URL + GBD ID",
        index_snapshots=indices,rejected=dict(rejections),
        frozen_portfolio=choice,
        R160_category_policy_is_negative_control_not_promoted=True,
        R158_features_shadow_only=True,V15_3_1_immutable=True,
        quota=QUOTA,cap_seconds=CAP,repetitions=REPEATS,
        modes=MODES,cases=candidates)
    save(FROZEN/"manifest.json",manifest)
    print("R161_FREEZE_PASS "+json.dumps({
        "original_formulas":len(candidates),"cohorts":QUOTA,
        "known_hash_count":len(known),
        "manifest_sha256":sha(FROZEN/"manifest.json")},sort_keys=True),flush=True)

def selected(shard):
    _,_,_,audit,choice=inventory()
    m=json.loads((FROZEN/"manifest.json").read_text())
    need(m["protocol"]==PROTO and
         m["status"]=="FROZEN_BEFORE_ANY_R161_TIMING",
         "unfrozen or wrong protocol")
    need(m["original_history"]==audit and m["frozen_portfolio"]==choice,
         "history/portfolio source changed")
    need(len(m["cases"])==24 and m["repetitions"]==REPEATS,
         "incomplete frozen sample")
    cases=[]
    for c in m["cases"][shard::SHARDS]:
        path=FROZEN/c["id"]
        need(path.is_file() and sha(path)==c["sha256"],"frozen CNF checksum changed")
        # Full original DIMACS validation, no transformation or re-encoding.
        n,clauses=prior.r159.ext.parse_original(path)
        need(n==c["variables"] and len(clauses)==c["clauses"],
             "original DIMACS dimensional drift")
        cases.append(dict(path=path.resolve(),formula=c["id"],n=n,
            clauses=clauses,formula_sha256=c["sha256"],expected="UNKNOWN",
            category=c["cohort"],metadata=dict(seed=int(c["sha256"][:12],16),
             fold="R161_prospective_outside_checked_registry",cohort=c["cohort"],
             features=prior.r159.ext.features(clauses,n))))
    need(len(cases)==6,"incomplete shard")
    return cases,m

def run(shard):
    need(0<=shard<SHARDS,"invalid shard")
    cases,source=selected(shard)
    prior.setup_binaries()
    core=prior.r159.ext.set_cpu_affinity()
    runner=os.environ.get("RUNNER_NAME","unknown")+" cpu="+str(core)+" "+platform.processor()
    bins=dict(kissat=sha(prior.r159.ext.base.ORIGINAL),
        cadical=sha(Path("built/bin/cadical_3_0_1")),
        stable_v1531=sha(prior.r159.ext.base.STABLE))
    records=[];traces=[]
    for case in cases:
        for rep in range(REPEATS):
            ordering=list(MODES)
            random.Random(int(case["formula_sha256"][:12],16)+rep+161).shuffle(ordering)
            for mode in ordering:
                # Call R160's audited same-CPU native executor. The new portfolio
                # name routes to the exact precommitted R160 training rule.
                oldmode="r160_portfolio" if mode=="r161_portfolio" else mode
                fake={cohort:{"selected":policy}
                      for cohort,policy in source["frozen_portfolio"].items()}
                row,trace=prior.attempt(case,rep,oldmode,runner,fake)
                row["mode"]=mode;row["r161_protocol"]=PROTO
                row["source_sha256"]=case["formula_sha256"]
                trace["mode"]=mode
                records.append(row);traces.append(trace)
                print("R161_MEASURE",case["formula"],rep,mode,
                      row["r160_selected_solver"],row["status"],row["par2_s"],flush=True)
                need(not row.get("error"),"solver error")
        statuses={x["status"] for x in records if x["formula"]==case["formula"]
                  and x["status"] in ("SAT","UNSAT")}
        need(len(statuses)<=1,"SAT/UNSAT contradictory solvers")
    need(len(records)==6*REPEATS*len(MODES),"not 72 trials")
    folder=ROOT/("shard-%d"%shard)
    writecsv(folder/"measurements.csv",records)
    folder.mkdir(parents=True,exist_ok=True)
    (folder/"traces.jsonl").write_text("".join(json.dumps(x,sort_keys=True)+"\n" for x in traces))
    save(folder/"manifest.json",dict(protocol=PROTO,
       source_commit=os.environ.get("GITHUB_SHA","local"),
       frozen_manifest_sha256=sha(FROZEN/"manifest.json"),
       frozen_CNF_SHA=[x["formula_sha256"] for x in cases],
       runner=runner,CPU_affinity=sorted(os.sched_getaffinity(0)),
       binary_sha256=bins,shard=shard,
       rows=len(records),policies=MODES,cap_seconds=CAP))
    print("R161_SHARD_PASS",shard,len(records),flush=True)

def confidence(per,arm):
    rng=random.Random(161000+sum(map(ord,arm)))
    strata=collections.defaultdict(list)
    for x in per:strata[x["cohort"]].append(x)
    out=[]
    for _ in range(3000):
        sample=[rng.choice(v) for v in strata.values() for i in v]
        b=sum(z["original_kissat"] for z in sample)
        t=sum(z[arm] for z in sample)
        out.append(100*(b-t)/b if b else 0.0)
    out.sort()
    return [round(out[int(i*2999)],5) for i in (.025,.975)]

def audit():
    src=json.loads((FROZEN/"manifest.json").read_text())
    known,urls,ids,old,choices=inventory()
    need(src["protocol"]==PROTO and src["original_history"]==old
         and src["frozen_portfolio"]==choices,
         "frozen model/provenance mismatch")
    expected={c["id"]:c for c in src["cases"]}
    need(len(expected)==24 and len({c["sha256"] for c in expected.values()})==24,
         "source incomplete/duplicate")
    measurements=[];pins=[];keyset=set()
    for shard in range(SHARDS):
        f=Path("r161-shards")/("r161-shard-%d"%shard)/"r161"/("shard-%d"%shard)
        meta=json.loads((f/"manifest.json").read_text())
        entries=readcsv(f/"measurements.csv")
        traces=[json.loads(x) for x in (f/"traces.jsonl").read_text().splitlines() if x.strip()]
        need(meta["protocol"]==PROTO and meta["shard"]==shard and
             meta["frozen_manifest_sha256"]==sha(FROZEN/"manifest.json") and
             len(entries)==len(traces)==72,"shard provenance or row count")
        for i,r in enumerate(entries):
            need(r["mode"] in MODES and r["formula"] in expected and
                 r["formula_sha256"]==expected[r["formula"]]["sha256"] and
                 r["runner"]==meta["runner"] and not r.get("error"),
                 "measurement source, runner or recorded error")
            need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"invalid result")
            need(abs(float(r["par2_s"])-(16.0 if r["status"]=="TIMEOUT"
                       else float(r["wall_s"])))<1e-4,"PAR2 mismatch")
            if r["status"]=="SAT":
                need(r["sat_model_checked"]=="True","unverified SAT witness")
            selection=src["frozen_portfolio"][r["category"]] if r["mode"]=="r161_portfolio" else r["mode"]
            need(r["r160_selected_solver"]==selection,"unfrozen actual route")
            trace=traces[i]
            need(trace["formula"]==r["formula"] and
                 str(trace["repeat"])==r["repeat"] and trace["mode"]==r["mode"],
                 "trace not paired to trial")
            k=(r["formula_sha256"],r["repeat"],r["mode"])
            need(k not in keyset,"duplicate raw attempted SAT solve")
            keyset.add(k)
        measurements+=entries
        pins.append(dict(shard=shard,source_commit=meta["source_commit"],
            runner=meta["runner"],cpu_affinity=meta["CPU_affinity"],
            binaries=meta["binary_sha256"],
            manifest_sha256=sha(f/"manifest.json"),
            measurements_sha256=sha(f/"measurements.csv"),
            traces_sha256=sha(f/"traces.jsonl")))
    need(len(measurements)==len(keyset)==288,"incomplete 288 SAT attempts")
    need(len({json.dumps(x["binaries"],sort_keys=True) for x in pins})==1,
         "inconsistent executable SHA between shards")
    grouped=collections.defaultdict(dict)
    for r in measurements:
        key=(r["formula_sha256"],r["repeat"])
        need(r["mode"] not in grouped[key],"duplicate mode")
        grouped[key][r["mode"]]=r
    need(len(grouped)==72,"not 72 paired groups")
    for group in grouped.values():
        need(set(group)==set(MODES),"incomplete paired strategies")
        need(len({x["runner"] for x in group.values()})==1,"unpaired CPU runner")
        need(len({x["status"] for x in group.values() if x["status"] in ("SAT","UNSAT")})<=1,
             "SAT/UNSAT contradiction")
    per=[]
    for c in src["cases"]:
        row=dict(id=c["id"],sha256=c["sha256"],cohort=c["cohort"],
                 variables=c["variables"],clauses=c["clauses"])
        sub=[r for r in measurements if r["formula_sha256"]==c["sha256"]]
        need(len(sub)==12,"incomplete formula")
        for m in MODES:row[m]=sum(float(r["par2_s"]) for r in sub if r["mode"]==m)
        per.append(row)
    target=ROOT/"report";target.mkdir(parents=True,exist_ok=True)
    writecsv(target/"paired.csv",per)
    base=sum(x["original_kissat"] for x in per)
    summaries={}
    for m in MODES:
        total=sum(x[m] for x in per)
        summaries[m]=dict(PAR2_s=round(total,6),
          gain_vs_Kissat_percent=round(100*(base-total)/base,6),
          solved=sum(x["status"] in ("SAT","UNSAT") for x in measurements if x["mode"]==m),
          formula_bootstrap95=confidence(per,m) if m!="original_kissat" else [0,0],
          severe_regression_2x=sum(x[m]>2*x["original_kissat"] for x in per))
    shadow=[];overhead=[]
    for c in src["cases"]:
        start=time.perf_counter()
        try:
            x=geom.static_features(geom.parse_dimacs(FROZEN/c["id"]))
            state="OK"
        except (ValueError,MemoryError) as ex:
            x={};state=str(ex)[:180]
        elapsed=1000*(time.perf_counter()-start);overhead.append(elapsed)
        shadow.append(dict(formula=c["id"],sha256=c["sha256"],
             cohort=c["cohort"],feature_status=state,feature_ms=round(elapsed,3),
             **{k:v for k,v in x.items() if k!="box_counts"}))
    writecsv(target/"r158_graph_shadow.csv",shadow)
    maxv=max([x[m] for x in per for m in ("original_kissat","r161_portfolio")]+[1])
    circles="".join('<circle cx="%.2f" cy="%.2f" r="4" fill="#228ea6"/>'%
      (50+680*x["original_kissat"]/maxv,730-680*x["r161_portfolio"]/maxv) for x in per)
    (target/"paired_scatter.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 800"><rect width="800" height="800" fill="white"/><path d="M50 730L730 50" stroke="#777" stroke-dasharray="5 5"/>'+circles+'<text x="50" y="30" font-size="17">R161 prospective SHA-distinct sources, PAR2 vs Kissat</text></svg>')
    report=dict(protocol=PROTO,source_class=src["source_class"],
       new_original_formula_SHA=24,compared_attempts=len(measurements),
       source_disjoint_against_proven_audited_registry=True,
       globally_never_tested_not_provable=True,
       not_official_competition_ranking=True,
       historical_registry_artifact_sources=src["original_history"],
       frozen_source_manifest_sha256=sha(FROZEN/"manifest.json"),
       source_shards=pins,consistent_reference_binaries=True,
       same_formula_CPU_paired=True,all_SAT_witness_verified=True,
       independent_UNSAT_certificate=False,
       V15_3_1_changed=False,R158_features_shadow_only=True,
       R160_portfolio_unpromoted_negative_control=True,
       graph_features_valid=sum(x.get("graph_box_valid",0)>0 for x in shadow),
       median_graph_extraction_overhead_ms=round(statistics.median(overhead),4),
       frozen_route=src["frozen_portfolio"],
       summary=summaries,
       warnings=["No independent UNSAT LRAT/FRAT certificate",
         "Verified novel SHA vs explicit historical registries only",
         "Catalog official membership is not official contest ranking",
         "R158 offline graph signals are not a live solver policy",
         "R160 category rule failed its preceding validation and is a negative control"])
    save(target/"report.json",report)
    print("R161_FINAL "+json.dumps({"formulas":24,"attempts":288,
        "summary":summaries,"graph_valid":report["graph_features_valid"]},sort_keys=True),flush=True)

if __name__=="__main__":
    cli=argparse.ArgumentParser()
    cli.add_argument("step",choices=("freeze","run","audit"))
    cli.add_argument("--shard",type=int,default=0)
    args=cli.parse_args()
    {"freeze":freeze,"run":lambda:run(args.shard),"audit":audit}[args.step]()
