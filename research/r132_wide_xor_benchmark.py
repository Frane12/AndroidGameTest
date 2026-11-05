#!/usr/bin/env python3
"""R132: PRECOMMITTED width-2..6 exact XOR selector on SHA-excluded real external holdout.
R130 and R118 compared, all original CNFs SHA frozen. Historical R115/R117
are positive controls ONLY and are prohibited from this prospective holdout.
Never promote without independently validated LRAT proof for UNSAT.
"""
import argparse, collections, csv, hashlib, json, os, pathlib, random, re, statistics, subprocess, sys, time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r128_xor_threshold_benchmark as base
import r127_early_xor_benchmark as witness

ROOT=pathlib.Path("r132")
SOURCES=ROOT/"frozen"
MODES=("kissat","cadical","r118","r130","r132")
FILTER=ROOT/"r132_filter"
OLD_FILTER=ROOT/"r130_filter"
R118=ROOT/"r118"
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
CADICAL=pathlib.Path("built/bin/cadical_3_0_1")
CAP=15
SHARDS=8
REPS=2
PROTO="DRNAS-R132-WIDE-K2-K6-FROZEN-PROSPECTIVE-20261105-v1"

def need(v,msg):
    if not v:raise RuntimeError("R132_AUDIT_REFUSED "+str(msg))
def digest(p):
    h=hashlib.sha256()
    with pathlib.Path(p).open("rb") as f:
        for block in iter(lambda:f.read(1048576),b""):h.update(block)
    return h.hexdigest()
def write(p,x):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,sort_keys=True)+"\n")
def cases():
    m=json.loads((SOURCES/"manifest.json").read_text())
    need(m["protocol"]==PROTO,"unexpected R130 manifest protocol")
    cs=m["cases"]
    need(len(cs)>=32,"too few external independently frozen cases")
    need(len({x["sha256"] for x in cs})==len(cs),"duplicate SHA in source list")
    for c in cs:
        p=SOURCES/c["id"]
        need(p.is_file() and digest(p)==c["sha256"],"external source SHA drift: "+c["id"])
    return cs

def freeze():
    """Exclude SHA, URL and benchmark IDs from R120-R130 and R124T.
    Immutable set fixed BEFORE the R130 paired benchmark sees any performance data.
    """
    from r125_native_gate_benchmark import HISTORIC_IDS
    import r126_equivalence_budget as downloader
    prior_names=("r120","r121","r122","r123","r124","r125","r126","r127","r128","r124t","r130","r117500")
    used=set();ids=set(HISTORIC_IDS);urls=set();ledger={}
    for name in prior_names:
        f=ROOT/"prior"/name/"manifest.json"
        need(f.is_file(),"missing required provenance ledger "+str(f))
        m=json.loads(f.read_text())
        entries=m.get("selected") if name in ("r120","r121") else m.get("cases")
        need(isinstance(entries,list) and bool(entries),"invalid prior entries "+name)
        ledger[name]=digest(f)
        for c in entries:
            if c.get("sha256"): used.add(c["sha256"])
            if c.get("id") and len(str(c["id"]))==32:
                ids.add(str(c["id"])) # prospective R117-500 frozen candidate IDs
            for field in ("gbd","url"):
                if c.get(field):
                    val=str(c[field]); ids.add(val.rsplit("/",1)[-1].split("?")[0])
                    if field=="url":urls.add(val)
    # Explicitly exclude all four historically seen R115/R117 breakthroughs.
    known_controls={
      "75429ff7acb5acb597abe01aa745c2a6":"243e5d0079606862166a4619691cbbb8ffc9c8c14eb16250138b16d724c6bc83",
      "42f1311ce504db8cc0cb590a568da20a":"9e4c57b9739f39a924d03267f05542831dc87fec9e9e2238f5e4ba11886378f4",
      "01d6fa8efd18ebfecd06af408958477b":"6be9bfe6b44454a061a2e93350f589643f8a16f5bca6babdaa50a2d3d7069361",
      "0efcbd10294eb001b16b4d126923372f":"84729f80119b50efac42d9477438abbc58c8712654ffe1fcdf9f324e44ae165d"
    }
    used.update(known_controls.values());ids.update(known_controls)
    need(len(used)>150,"insufficient historic SHA exclusion pool")
    specs={
       # Sources and quotas PRECOMMITTED before any R132 timings:
       # GBD real independent families; limit to <= 8 MiB original CNF.
       "miter":("https://benchmark-database.de/getinstances?query=family%3Dmiter&context=cnf",30),
       "cryptography":("https://benchmark-database.de/getinstances?query=family%3Dcryptography&context=cnf",25),
       "xor_shifting":("https://benchmark-database.de/getinstances?query=family%3Dxor-shifting&context=cnf",25),
       "uniform_random":("https://benchmark-database.de/getinstances?query=family%3Duniform-random&context=cnf",25),
       "official2024":("https://benchmark-database.de/getinstances?query=track%3Dmain_2024&context=cnf",20),
       "official2025":("https://raw.githubusercontent.com/satcompetition/2025/main/downloads/SC2025.uri",20)
    }
    SOURCES.mkdir(parents=True,exist_ok=True)
    cases_new=[];sources_meta={};failures=collections.Counter()
    for cohort,(index,target) in specs.items():
        try:
            raw=downloader.download(index,4_000_000)
            all_urls=sorted({u.strip() for u in raw.decode().splitlines()
                             if u.strip().startswith(("https://","http://"))})
            need(bool(all_urls),"source index empty")
        except Exception as e:
            sources_meta[cohort]=dict(index=index,index_error=str(e)[:250],target=target)
            failures[cohort+"_index_unavailable"]+=1
            continue
        sources_meta[cohort]=dict(index=index,index_sha256=hashlib.sha256(raw).hexdigest(),
                                  available_urls=len(all_urls),target=target)
        random.Random(PROTO+"|PRECOMMITTED|"+cohort).shuffle(all_urls)
        accepted=0;attempted=0
        for url in all_urls:
            if accepted>=target or attempted>=160: break
            gbd=url.rsplit("/",1)[-1].split("?")[0]
            if gbd in ids or url in urls:
                failures[cohort+"_historical_id"]+=1
                continue
            attempted+=1
            try:
                raw=downloader.download(url)
                plain=downloader.unpack(raw)
                need(len(plain)<=8_000_000,"decompressed source exceeds 8MiB")
                h=hashlib.sha256(plain).hexdigest()
                if h in used:
                    failures[cohort+"_historical_sha"]+=1
                    continue
                hdr=[l.split() for l in plain.splitlines() if l.startswith(b"p cnf ")]
                need(len(hdr)==1 and len(hdr[0])==4,"invalid DIMACS header")
                n,m=map(int,hdr[0][2:])
                need(n>0 and m>0,"invalid DIMACS dimensions")
                fname=cohort+"-"+str(accepted).zfill(3)+".cnf"
                (SOURCES/fname).write_bytes(plain)
                cases_new.append(dict(id=fname,cohort=cohort,gbd=gbd,url=url,sha256=h,
                        bytes=len(plain),variables=n,clauses=m,original_bytes_sha256=hashlib.sha256(raw).hexdigest()))
                ids.add(gbd);urls.add(url);used.add(h);accepted+=1
                print("R132_FROZEN_CASE",cohort,accepted,h[:12],flush=True)
            except Exception as e:
                failures[cohort+"_download_or_validation"]+=1
        sources_meta[cohort]["accepted"]=accepted
        sources_meta[cohort]["attempted_downloads"]=attempted
    m=dict(protocol=PROTO,phase="PREBENCHMARK_SHA_EXCLUDED_HOLDOUT",cases=cases_new,
        source_indexes=sources_meta,prior_manifest_sha256=ledger,counts=dict(collections.Counter(c["cohort"] for c in cases_new)),
        rejection_counts=dict(failures),repeats=REPS,shards=SHARDS,limit_s=CAP,
        selector="frozen R132 k2..k6: pure full coverage OR connected >=4 equations and >=10% clause coverage; 1MiB input bound; all overhead included",
        original_unchanged=True,original_kissat_unchanged=True,
        caveats="External under-8MB URI pool, not official contest; unresolved UNSAT independently unproved",
        no_holdout_tuning=True)
    write(SOURCES/"manifest.json",m)
    print("R132_FREEZE_FINAL",json.dumps({k:m[k] for k in ("counts","rejection_counts","source_indexes")},sort_keys=True),flush=True)
    need(len(cases_new)>=32,"insufficient SHA-disjoint external set: "+str(m["counts"]))
    need(len(cases_new)<=145,"unexpected overlarge set")

def probe(src,policy):
    st=time.perf_counter()
    selected_filter=FILTER if policy=="wide_exact" else OLD_FILTER
    p=subprocess.run([str(selected_filter.resolve()),str(src),str(R118),str(KISSAT),policy,"--probe-only"],
        text=True,capture_output=True,timeout=6)
    need(p.returncode==0,"probe failed "+str(p.stderr)[:400])
    line=next((v for v in p.stdout.splitlines() if v.startswith("c R132_SELECTOR policy=" if policy=="wide_exact" else "c R130_SELECTOR policy=")),None)
    need(line is not None,"missing selector telemetry")
    fields=dict(re.findall(r"([a-z_]+)=([^\s]+)",line))
    need(fields.get("policy")==policy,"unexpected policy telemetry")
    return dict(policy=policy,route=fields.get("route"),reason=fields.get("reason"),
        bytes=int(fields["bytes"]),clauses=int(fields["clauses"]),
        xor_equations=int(fields["xor_equations"]),covered_clauses=int(fields["covered_clauses"]),
        parsed=int(fields["parsed"]),probe_s=round(time.perf_counter()-st,6))

def run_cadical(src,rep):
    start=time.perf_counter()
    try:
        p=subprocess.run([str(CADICAL.resolve()),str(src)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=CAP)
        elapsed=time.perf_counter()-start
        need(p.returncode in (10,20),"CaDiCaL failure "+str(p.returncode)+" "+p.stderr[-200:].decode(errors="replace"))
        status="SAT" if p.returncode==10 else "UNSAT"
        if elapsed>=CAP: status="TIMEOUT"
        proof="timeout"
        if status=="SAT":
            witness.check_original_sat(p.stdout,src)
            proof="source_SAT_witness_verified"
        elif status=="UNSAT":proof="UNSAT_without_independent_LRAT_proof"
    except subprocess.TimeoutExpired:
        elapsed=CAP;status="TIMEOUT";proof="timeout"
    return dict(mode="cadical",repeat=rep,status=status,
                seconds=round(min(elapsed,CAP),6),par2=30.0 if status=="TIMEOUT" else round(elapsed,6),
                proof=proof,route="CaDiCaL_direct",selected_R118=False,GF2_solved=False)

def execute(shard):
    need(0<=shard<SHARDS,"invalid shard")
    selected=cases()
    for x in (FILTER,OLD_FILTER,R118,KISSAT,CADICAL):
        need(x.is_file(),"missing pinned solver "+str(x))
    (ROOT).mkdir(parents=True,exist_ok=True)
    affinity=sorted(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{affinity[0]})
    rows=[];probes=[]
    base.FILTER=FILTER.resolve();base.R118=R118.resolve();base.KISSAT=KISSAT.resolve();base.POLICIES=("wide_exact","adaptive");base.CAP=CAP
    for i,c in enumerate(selected):
        if i%SHARDS!=shard:continue
        src=SOURCES/c["id"]
        for policy in ("adaptive","wide_exact"):
            probes.append(dict(id=c["id"],sha256=c["sha256"],cohort=c["cohort"],**probe(src,policy)))
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(modes)
            votes=set()
            for mode in modes:
                if mode=="cadical":x=run_cadical(src,rep)
                elif mode=="r130":
                    base.FILTER=OLD_FILTER.resolve()
                    x=base.run_one(src,"adaptive",rep,"holdout")
                    x["mode"]="r130"
                elif mode=="r132":
                    base.FILTER=FILTER.resolve()
                    x=base.run_one(src,"wide_exact",rep,"holdout")
                    x["mode"]="r132"
                else:x=base.run_one(src,mode,rep,"holdout")
                row=dict(protocol=PROTO,shard=shard,id=c["id"],sha256=c["sha256"],
                         cohort=c["cohort"],**x)
                rows.append(row)
                if row["status"]!="TIMEOUT":
                    votes.add(row["status"])
                    need(len(votes)<=1,"SAT/UNSAT disagreement on "+c["id"])
                print("R132_PAIRED_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==len(selected[shard::SHARDS])*REPS*len(MODES),"incomplete rows")
    cpu=next((s for s in pathlib.Path("/proc/cpuinfo").read_text().splitlines() if s.startswith("model name")),"unknown")
    pins={str(x):digest(x) for x in (FILTER,R118,KISSAT,CADICAL)}
    write(ROOT/f"shard-{shard}.json",dict(protocol=PROTO,shard=shard,
          source_manifest_sha256=digest(SOURCES/"manifest.json"),rows=rows,probes=probes,
          binary_sha256=pins,runner_cpu=cpu))
    print("R132_SHARD_COMPLETE",shard,len(rows),len(probes),flush=True)

def audit():
    selected=cases()
    source_sha=digest(SOURCES/"manifest.json")
    shards=[json.loads((ROOT/f"shard-{i}.json").read_text()) for i in range(SHARDS)]
    need(all(x["protocol"]==PROTO and x["source_manifest_sha256"]==source_sha for x in shards),"source drift")
    need(len({json.dumps(x["binary_sha256"],sort_keys=True) for x in shards})==1,"binary drift")
    rows=[y for sh in shards for y in sh["rows"]]
    probes=[y for sh in shards for y in sh["probes"]]
    need(len(rows)==len(selected)*REPS*len(MODES),"missing trials")
    cases_by_sha={c["sha256"]:c for c in selected}
    idx={}
    for x in rows:
        need(x["sha256"] in cases_by_sha and cases_by_sha[x["sha256"]]["id"]==x["id"],"formula identity drift")
        need(x["mode"] in MODES and x["repeat"] in range(REPS),"mode or repetition")
        need(x["status"] in ("SAT","UNSAT","TIMEOUT"),"solver status")
        if x["status"]=="SAT":need(x["proof"]=="source_SAT_witness_verified","missing SAT witness")
        if x["status"]=="UNSAT":need(x["proof"]=="UNSAT_without_independent_LRAT_proof","unfounded UNSAT proof claim")
        need(abs(x["par2"]-(30 if x["status"]=="TIMEOUT" else x["seconds"]))<1e-5,"incorrect PAR2")
        key=(x["sha256"],x["repeat"],x["mode"])
        need(key not in idx,"duplicate trial")
        idx[key]=x
    need(len(idx)==len(rows),"trial duplicates")
    for sha in cases_by_sha:
        for rep in range(REPS):
            tests=[idx[(sha,rep,m)] for m in MODES]
            need(len({x["status"] for x in tests if x["status"]!="TIMEOUT"})<=1,"SAT/UNSAT disagreement")
    summary={}
    for m in MODES:
        x=[r for r in rows if r["mode"]==m]
        solved=[r["seconds"] for r in x if r["status"]!="TIMEOUT"]
        summary[m]=dict(trials=len(x),solved=len(solved),SAT=sum(r["status"]=="SAT" for r in x),
             UNSAT=sum(r["status"]=="UNSAT" for r in x),timeout=sum(r["status"]=="TIMEOUT" for r in x),
             PAR2_total_s=round(sum(r["par2"] for r in x),6),
             PAR2_mean_s=round(statistics.mean(r["par2"] for r in x),6),
             median_solved_wall_s=round(statistics.median(solved),6) if solved else None,
             gate_activations=sum(r["selected_R118"] for r in x),
             GF2_solved=sum(r["GF2_solved"] for r in x))
    base_par2=summary["kissat"]["PAR2_total_s"]
    comparisons={}
    for m in MODES:
        if m=="kissat":continue
        diffs=[sum(idx[(sha,rep,m)]["par2"]-idx[(sha,rep,"kissat")]["par2"] for rep in range(REPS)) for sha in cases_by_sha]
        comparisons[m]=dict(gain_vs_kissat_pct=round(100*(base_par2/summary[m]["PAR2_total_s"]-1),5),
            faster_formula_pairs=sum(d<-1e-5 for d in diffs),
            slower_formula_pairs=sum(d>1e-5 for d in diffs),
            wins_2x=sum(sum(idx[(sha,rep,"kissat")]["par2"] for rep in range(REPS))>=2*sum(idx[(sha,rep,m)]["par2"] for rep in range(REPS)) for sha in cases_by_sha),
            regressions_2x=sum(sum(idx[(sha,rep,m)]["par2"] for rep in range(REPS))>=2*sum(idx[(sha,rep,"kissat")]["par2"] for rep in range(REPS)) for sha in cases_by_sha))
    reasons=collections.Counter((p["policy"],p["reason"]) for p in probes)
    report=dict(protocol=PROTO,phase="NEW_SHA_EXCLUDED_EXTERNAL_BLIND_HOLDOUT",formulas=len(selected),measurements=len(rows),CAP_s=CAP,repeats=REPS,
        original_manifest_sha256=source_sha,source_sha_verified=True,
        summary=summary,comparisons=comparisons,
        probes=dict(by_reason={f"{p}|{reason}":n for (p,reason),n in sorted(reasons.items())},
            triggered={m:sum(p["policy"]==m and p["route"]=="GF2" for p in probes) for m in ("adaptive","wide_exact")},
            median_probe_seconds={m:round(statistics.median(p["probe_s"] for p in probes if p["policy"]==m),6) for m in ("q2_25","adaptive")}),
        all_runs_hardware=[x["runner_cpu"] for x in shards],strict_no_promotion=True,
        no_independent_UNSAT_LRAT=True,
        holdout_note="R132 exact k2..6 precommitted SHA-disjoint external holdout, excludes R120-R130, R124T, R117500 and all 4 historical controls; no independent UNSAT LRAT or official ranking.")
    report["adaptive_verdict"]=("PROMISING_BUT_UNVERIFIED_UNSAT" if
        comparisons["r132"]["gain_vs_kissat_pct"]>0 and
        comparisons["r132"]["regressions_2x"]==0 and
        summary["r132"]["solved"]>=summary["kissat"]["solved"] else "NO_PROMOTION")
    report["new_holdout_by_cohort"]=dict(collections.Counter(c["cohort"] for c in selected))
    report["r132_vs_r130_PAR2_gain_pct"]=round(100*(summary["r130"]["PAR2_total_s"]/summary["r132"]["PAR2_total_s"]-1),6)
    report["missing_independent_unsat_certificate"]=True
    report["no_official_world_rank_claim"]=True
    write(ROOT/"report.json",report)
    with (ROOT/"paired.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    with (ROOT/"probes.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(probes[0]));w.writeheader();w.writerows(probes)
    print("R132_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=("freeze","run","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    {"freeze":freeze,"run":lambda:execute(a.shard),"audit":audit}[a.command]()
