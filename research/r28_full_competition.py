#!/usr/bin/env python3
"""R28 full same-runner competition-style SAT benchmark.
Freeze original 2025/2026 official main and cross-family CNF sources BEFORE
timing. Compare unchanged R28, pinned Kissat/CaDiCaL and a reproducibly
compiled official 2026 kissat-sc2024 source archive. Published times are only
cross-machine context, NEVER used to rank same-runner competitors.
"""
import argparse,bz2,collections,csv,gzip,hashlib,io,json,lzma,math,os,pathlib,random,re,statistics,subprocess,sys,time,urllib.request
sys.path.insert(0,str(pathlib.Path("research").resolve()))
import r115_world_top_rematch as witness

ROOT=pathlib.Path("r28full")
INPUT=ROOT/"frozen"
PROTO="DRNAS-R28-FULL-COMPETITION-2025-2026-20261105-v1"
CAP=20.;REPS=2;SHARDS=8
MODES=("r28","kissat","cadical","official_sc2024")
QUOTAS={"official2026":32,"official2025":32,"xor_shifting":16,"cryptography":16,"miter":16}
INDEXES={
 "official2026":"https://raw.githubusercontent.com/satcompetition/2026/main/downloads/track_main_2026.uri",
 "official2025":"https://raw.githubusercontent.com/satcompetition/2025/main/downloads/SC2025.uri",
 "xor_shifting":"https://benchmark-database.de/getinstances?query=family%3Dxor-shifting&context=cnf",
 "cryptography":"https://benchmark-database.de/getinstances?query=family%3Dcryptography&context=cnf",
 "miter":"https://benchmark-database.de/getinstances?query=family%3Dmiter&context=cnf",
}
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
CADICAL=pathlib.Path("built/bin/cadical_3_0_1")
OFFICIAL=ROOT/"sc2024-kissat"
R28=ROOT/"r28"
SAMPLE_LIMIT=12_000_000
def need(flag,msg):
    if not flag:raise RuntimeError("R28_FULL_FAIL_CLOSED "+str(msg))
def sha(data):return hashlib.sha256(data).hexdigest()
def fsha(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()
def write(path,value):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(p.suffix+".partial")
    tmp.write_text(json.dumps(value,indent=2,sort_keys=True)+"\n")
    os.replace(tmp,p)
def load(path):return json.loads(pathlib.Path(path).read_text())
def urlget(url,limit=12_000_000,timeout=24):
    req=urllib.request.Request(url,headers={"User-Agent":"DRNAS-R28-Competition-Freeze/1.0"})
    with urllib.request.urlopen(req,timeout=timeout) as fh:raw=fh.read(limit+1)
    need(len(raw)<=limit,"source exceeds allowed compressed size")
    return raw
def expand(raw):
    if raw.startswith(b"\x1f\x8b"):f=gzip.GzipFile(fileobj=io.BytesIO(raw))
    elif raw.startswith(b"BZh"):f=bz2.BZ2File(io.BytesIO(raw))
    elif raw.startswith(b"\xfd7zXZ"):f=lzma.LZMAFile(io.BytesIO(raw))
    else:return raw
    with f:data=f.read(SAMPLE_LIMIT+1)
    need(len(data)<=SAMPLE_LIMIT,"unpacked CNF too large")
    return data
def dimacs(plain):
    need(0<len(plain)<=SAMPLE_LIMIT,"source size out of bounds")
    header=False;nv=nc=seen=0;opened=False
    for line in plain.splitlines():
        t=line.strip()
        if not t or t==b"c" or t.startswith((b"c ",b"c\t")):continue
        if t==b"%":break
        if t.startswith(b"p "):
            need(not header,"second DIMACS header")
            a=t.split()
            need(len(a)==4 and a[:2]==[b"p",b"cnf"],"bad DIMACS header")
            nv,nc=map(int,a[2:]);need(nv>0 and nc>0,"empty DIMACS dimensions")
            header=True;continue
        need(header,"literals before DIMACS header")
        for token in t.split():
            v=int(token)
            need(abs(v)<=nv,"out of-range literal")
            if v:opened=True
            else:seen+=1;opened=False
            need(seen<=nc,"excess clauses")
    need(header and not opened and seen==nc,"incomplete DIMACS")
    return nv,nc
def prior_exclusions():
    ids=set();sha256=set();urls=set();files=[]
    folders=["prior/400","prior/r132","prior/r135","prior/r135s",
             "prior/r148","prior/r150","prior/r151","prior/r152","prior/r115"]
    for folder in folders:
        folder=pathlib.Path(folder)
        possible=list(folder.rglob("*.json"))
        need(possible,"missing prior SHA ledger under "+str(folder))
        files.extend(possible)
    for path in files:
        try:obj=load(path)
        except (ValueError,OSError,UnicodeError):continue
        def visit(value,key=""):
            if isinstance(value,dict):
                for k,v in value.items():visit(v,str(k).lower())
            elif isinstance(value,list):
                for item in value:visit(item,key)
            elif isinstance(value,str):
                s=value.strip()
                if re.fullmatch("[0-9a-fA-F]{64}",s) and ("sha" in key or key in ("hash","source_hash")):
                    sha256.add(s.lower())
                if re.fullmatch("[0-9a-fA-F]{32}",s) and key in ("id","gbd","gbd_id","instanceid","source_id","source_identifier"):
                    ids.add(s.lower())
                if s.startswith(("https://","http://")) and any(z in key for z in ("url","uri","download","source")):
                    urls.add(s)
                    ident=re.search(r"(?i)[a-f0-9]{32}",s)
                    if ident:ids.add(ident.group(0).lower())
        visit(obj)
    need(len(sha256)>=500,"SHA exclusion ledger unexpectedly narrow "+str(len(sha256)))
    return sha256,ids,urls,{str(p):fsha(p) for p in files}
def freeze():
    oldsha,oldids,oldurls,prior=prior_exclusions()
    target_total=sum(QUOTAS.values());accepted=[];rejects=collections.Counter()
    sourcemeta={};INPUT.mkdir(parents=True,exist_ok=True)
    present_sha=set();present_ids=set()
    for cohort,uri in INDEXES.items():
        try:
            indexraw=urlget(uri,4_000_000,35)
            sources=sorted({line.strip() for line in indexraw.decode("utf-8").splitlines()
                if line.strip().startswith(("https://","http://"))},
                key=lambda x:sha((PROTO+"|"+cohort+"|"+x).encode()))
            need(bool(sources),"no URLs in source index")
        except Exception as exc:
            sourcemeta[cohort]=dict(error=str(exc)[:250],url=uri,accepted=0)
            rejects[cohort+"_index_error"]+=1;continue
        sourcemeta[cohort]=dict(index_url=uri,index_sha256=sha(indexraw),
                                 index_entries=len(sources),target=QUOTAS[cohort])
        # Frozen deterministic, performance-blind source ordering. No solver is
        # executed or outcome inspected during acquisition.
        attempts=0;n=0
        for url in sources:
            if n>=QUOTAS[cohort] or attempts>=260:break
            ident=re.search(r"(?i)[0-9a-f]{32}",url)
            gbd=ident.group(0).lower() if ident else None
            if url in oldurls or (gbd and gbd in oldids):
                rejects[cohort+"_prior_url_or_id"]+=1;continue
            attempts+=1
            try:
                packed=urlget(url,SAMPLE_LIMIT,26)
                plain=expand(packed)
                nv,nc=dimacs(plain)
                digest=sha(plain)
                if digest in oldsha or digest in present_sha or (gbd and gbd in present_ids):
                    rejects[cohort+"_prior_or_duplicate_sha"]+=1;continue
                filename=f"{cohort}-{n:03d}.cnf"
                (INPUT/filename).write_bytes(plain)
                accepted.append(dict(id=filename,cohort=cohort,source_url=url,
                    gbd_id=gbd,sha256=digest,compressed_sha256=sha(packed),
                    bytes=len(plain),variables=nv,clauses=nc,
                    R28_native_parse_possible=nv<=3000 and nc<=150000))
                present_sha.add(digest)
                if gbd:present_ids.add(gbd)
                n+=1
                print("R28_FULL_FROZEN",cohort,n,digest[:16],flush=True)
            except Exception as exc:
                rejects[cohort+"_unavailable_invalid_or_oversize"]+=1
        sourcemeta[cohort].update(attempts=attempts,accepted=n)
    counts=dict(collections.Counter(c["cohort"] for c in accepted))
    need(len(accepted)>=65 and len(counts)>=4 and
         counts.get("official2026",0)+counts.get("official2025",0)>=28,
         "insufficient independent mixed SAT competition sources "+repr(counts))
    need(len({c["sha256"] for c in accepted})==len(accepted),"duplicate frozen CNF")
    manifest=dict(protocol=PROTO,phase="SOURCES_FROZEN_BEFORE_FIRST_SOLVER_TIMING",
        selected_count=len(accepted),precommitted_quotas=QUOTAS,cohort_counts=counts,
        source_indexes=sourcemeta,source_rejections=dict(rejects),
        strict_prior_manifest_sha256=prior,excluded_prior_content_sha256=len(oldsha),
        excluded_prior_32hex_ids=len(oldids),excluded_prior_urls=len(oldurls),
        source_size_bound_bytes=SAMPLE_LIMIT,repeats=REPS,shards=SHARDS,
        cap_seconds=CAP,modes=MODES,original_CNF_unchanged=True,
        no_solver_performance_used_for_selection=True,
        independent_exclusion_not_exhaustive_of_every_older_DRNAS_dataset=True,
        published_official_times_only_separate_cross_hardware_context=True,
        cases=accepted)
    write(INPUT/"manifest.json",manifest)
    print("R28_FULL_SOURCE_FREEZE",json.dumps({k:manifest[k] for k in
          ("selected_count","cohort_counts","source_rejections","source_indexes")},
          sort_keys=True),flush=True)
def cases():
    m=load(INPUT/"manifest.json")
    need(m["protocol"]==PROTO and m["phase"]=="SOURCES_FROZEN_BEFORE_FIRST_SOLVER_TIMING",
         "original source freeze missing")
    cs=m["cases"]
    need(65<=len(cs)<=sum(QUOTAS.values()) and len({c["sha256"] for c in cs})==len(cs),
         "source count or uniqueness invalid")
    return cs,m
def trial(c,mode,rep):
    src=(INPUT/c["id"]).resolve()
    need(fsha(src)==c["sha256"],"original source SHA mismatch")
    exe=R28 if mode=="r28" else KISSAT if mode=="kissat" else CADICAL if mode=="cadical" else OFFICIAL
    cmd=[str(exe.resolve()),str(src),str(KISSAT.resolve())] if mode=="r28" else [str(exe.resolve()),str(src)]
    start=time.perf_counter();status="TIMEOUT";seconds=CAP;output=b"";proof="timeout";route="timeout";out_sha=None
    try:
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=CAP)
        seconds=time.perf_counter()-start
        need(p.returncode in (10,20),"unexpected exit mode="+mode+" rc="+str(p.returncode)+
             " stderr="+p.stderr[-300:].decode(errors="replace"))
        status="SAT" if p.returncode==10 else "UNSAT"
        output=p.stdout
        out_sha=sha(output)
        route=("gf2_sat" if b"c R28_ROUTE certified_pure_xor_sat" in output else
               "gf2_unsat" if b"c R28_ROUTE certified_xor_contradiction" in output else
               "fallback" if mode=="r28" else "native")
        if status=="SAT":
            witness.sat_model_check(src,output)
            proof="original_CNF_SAT_witness_validated"
        elif mode=="r28" and route=="gf2_unsat":
            witness.xor_unsat_check(src,output)
            proof="independently_replayed_original_XOR_UNSAT"
        else:
            proof="UNSAT_without_independent_LRAT"
    except subprocess.TimeoutExpired:
        seconds=CAP
    if seconds>=CAP:
        status="TIMEOUT";proof="timeout";seconds=CAP;route="timeout"
    return dict(mode=mode,rep=rep,status=status,seconds=round(seconds,6),
       par2=round(2*CAP if status=="TIMEOUT" else seconds,6),route=route,proof=proof,
       solver_stdout_sha256=out_sha)
def run(shard):
    need(0<=shard<SHARDS,"shard index")
    cs,m=cases()
    for f in (KISSAT,CADICAL,OFFICIAL,R28):
        need(f.is_file(),"missing solver binary "+str(f))
    if hasattr(os,"sched_getaffinity"):
        available=os.sched_getaffinity(0)
        os.sched_setaffinity(0,{min(available)})
    cpu=next((x for x in pathlib.Path("/proc/cpuinfo").read_text().splitlines()
        if x.startswith("model name")),"unknown")
    pins={str(p):fsha(p) for p in (KISSAT,CADICAL,OFFICIAL,R28)}
    sourcepin=fsha(INPUT/"manifest.json")
    rows=[]
    for idx,c in enumerate(cs):
        if idx%SHARDS!=shard:continue
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(PROTO+"|"+c["sha256"]+"|"+str(rep)).shuffle(modes)
            answers=set()
            for mode in modes:
                d=dict(protocol=PROTO,source_manifest_sha256=sourcepin,
                    shard=shard,id=c["id"],cohort=c["cohort"],
                    sha256=c["sha256"],**trial(c,mode,rep))
                rows.append(d)
                if d["status"]!="TIMEOUT":
                    answers.add(d["status"])
                    need(len(answers)<=1,"contradiction between solvers "+c["sha256"])
                print("R28_FULL_PAIRED",json.dumps(d,sort_keys=True),flush=True)
                write(ROOT/f"shard-{shard}.json",dict(protocol=PROTO,shard=shard,
                    source_manifest_sha256=sourcepin,cpu=cpu,pinned=pins,rows=rows))
    need(len(rows)==len(cs[shard::SHARDS])*REPS*len(MODES),"incomplete paired shard")
    print("R28_FULL_SHARD_PASS",shard,len(rows),flush=True)
def bootstrap(per,mode,baseline):
    rng=random.Random(2820261105)
    groups=collections.defaultdict(list)
    for row in per:groups[row["cohort"]].append(row)
    gains=[]
    for _ in range(2000):
        selection=[rng.choice(group) for co,group in sorted(groups.items()) for i in range(len(group))]
        d=sum(x[baseline] for x in selection)
        gains.append(100*(d-sum(x[mode] for x in selection))/d if d else 0.)
    gains.sort();return [round(gains[49],5),round(gains[1949],5)]
def audit():
    cs,m=cases()
    sourcepin=fsha(INPUT/"manifest.json")
    shards=[load(ROOT/f"shard-{i}.json") for i in range(SHARDS)]
    need(all(s["protocol"]==PROTO and s["source_manifest_sha256"]==sourcepin for s in shards),
         "shard source/protocol drift")
    need(len(set(json.dumps(s["pinned"],sort_keys=True) for s in shards))==1,
         "competitor or R28 binary SHA drift")
    rows=[d for s in shards for d in s["rows"]]
    need(len(rows)==len(cs)*REPS*len(MODES),"incomplete total benchmark")
    bysha={c["sha256"]:c for c in cs};lookup={}
    for r in rows:
        c=bysha.get(r["sha256"])
        need(c and r["id"]==c["id"] and r["cohort"]==c["cohort"],"source identity mismatch")
        need(r["mode"] in MODES and r["rep"] in (0,1),"bad mode or rep")
        need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"invalid result")
        need(0<=r["seconds"]<=CAP+1e-4,"invalid time")
        need(abs(r["par2"]-(2*CAP if r["status"]=="TIMEOUT" else r["seconds"]))<1e-4,
             "wrong PAR2")
        if r["status"]=="SAT":need(r["proof"]=="original_CNF_SAT_witness_validated","missing SAT proof")
        if r["proof"]=="independently_replayed_original_XOR_UNSAT":
            need(r["mode"]=="r28" and r["status"]=="UNSAT" and r["route"]=="gf2_unsat",
                 "false XOR UNSAT proof")
        key=(r["sha256"],r["rep"],r["mode"])
        need(key not in lookup,"duplicate trial");lookup[key]=r
    for c in cs:
        for rep in range(REPS):
            results={lookup[c["sha256"],rep,mode]["status"] for mode in MODES}-{"TIMEOUT"}
            need(len(results)<=1,"conflicting SAT/UNSAT results "+c["sha256"])
    summary={}
    for mode in MODES:
        subset=[r for r in rows if r["mode"]==mode]
        solved=[r["seconds"] for r in subset if r["status"]!="TIMEOUT"]
        summary[mode]=dict(trials=len(subset),solved=len(solved),
             SAT=sum(r["status"]=="SAT" for r in subset),
             UNSAT_independent_XOR=sum(r["proof"]=="independently_replayed_original_XOR_UNSAT" for r in subset),
             UNSAT_without_independent_LRAT=sum(r["proof"]=="UNSAT_without_independent_LRAT" for r in subset),
             timeouts=len(subset)-len(solved),
             PAR2_total_s=round(sum(r["par2"] for r in subset),6),
             median_solved_s=round(statistics.median(solved),6) if solved else None,
             r28_gf2_SAT=sum(r["route"]=="gf2_sat" for r in subset),
             r28_gf2_UNSAT=sum(r["route"]=="gf2_unsat" for r in subset),
             r28_fallback=sum(r["route"]=="fallback" for r in subset))
    per=[]
    for c in cs:
        h=c["sha256"]
        per.append(dict(id=c["id"],cohort=c["cohort"],sha256=h,
           **{mode:sum(lookup[h,rep,mode]["par2"] for rep in range(REPS)) for mode in MODES},
           **{mode+"_solved":sum(lookup[h,rep,mode]["status"]!="TIMEOUT" for rep in range(REPS)) for mode in MODES}))
    comparisons={}
    for mode in MODES:
        if mode=="r28":continue
        comparisons[mode]=dict(
          R28_gain_percent=round(100*(summary[mode]["PAR2_total_s"]-summary["r28"]["PAR2_total_s"])/
                               summary[mode]["PAR2_total_s"],6),
          R28_vs_mode_bootstrap95_pct=bootstrap(per,"r28",mode),
          R28_formula_wins=sum(x["r28"]<x[mode]-1e-5 for x in per),
          R28_formula_losses=sum(x["r28"]>x[mode]+1e-5 for x in per),
          R28_regressions_2x=sum(x["r28"]>=2*max(.001,x[mode]) for x in per))
    cohorts={co:dict(formulas=sum(c["cohort"]==co for c in cs),
        PAR2={mode:round(sum(r["par2"] for r in rows if r["cohort"]==co and r["mode"]==mode),6)
              for mode in MODES},
        solved={mode:sum(r["status"]!="TIMEOUT" for r in rows if r["cohort"]==co and r["mode"]==mode)
                for mode in MODES}) for co in sorted(set(c["cohort"] for c in cs))}
    report=dict(protocol=PROTO,verdict="EXPERIMENT_NO_WORLD_RECORD_CLAIM",
        formulas=len(cs),measurements=len(rows),cap_s=CAP,repeats=REPS,
        frozen_manifest_sha256=sourcepin,source_hashes_verified=True,
        original_CNF_unchanged=True,reference_competitor="official SAT Competition 2026 author biere.tar.xz kissat-sc2024",
        pinned=shards[0]["pinned"],CPU_by_shard=[s["cpu"] for s in shards],
        summary=summary,comparisons=comparisons,by_cohort=cohorts,
        independent_UNSAT_LRAT=False,
        caveats=["This is a local timed simulation, not the official SAT Competition ranking",
          "SAT Competition 2026 published per-instance scores are cross-hardware context only, not same-runner evidence",
          "Resource bounds: original uncompressed DIMACS <=12MB, no speed-based exclusions",
          "Some 2025/2026 sources may have been used in unlisted historic DRNAS tests",
          "R28 native GF2 parser has 3000-var/150000-clause limits; larger sources trigger native Kissat fallback",
          "No automatic promotion; need blind repeat and independent UNSAT certificates"])
    write(ROOT/"audit.json",report)
    with (ROOT/"paired.csv").open("w",newline="") as f:
        fields=sorted({k for x in rows for k in x})
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    with (ROOT/"per_formula.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(per[0]))
        w.writeheader();w.writerows(per)
    print("R28_FULL_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("step",choices=("freeze","run","audit"))
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    {"freeze":freeze,"run":lambda:run(args.shard),"audit":audit}[args.step]()
