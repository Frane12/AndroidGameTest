#!/usr/bin/env python3
"""R81 fresh SAT Competition 2026 XOR-stratified, source-disjoint paired benchmark.

Official original CNFs ONLY. Exclude R63's entire historical 2026 registry
(R32p/R32r, R52/R55b/R57/R60/R61/R63, therefore R80).
Select by salted GBD order and pre-solve proof-pattern features, NEVER runtime.
Two repetitions, 25s end-to-end cap, six unchanged solver policies, PAR-2.
This is an unofficial engineering sample, not SAT Competition ranking.
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, io, json, os, random, tempfile, time
from pathlib import Path
import r32p_real_satcomp26_benchmark as r32p
import r52_prospective_2026_toprefs as r52
import r63_real2026_xor_prevalence_fallback as r63
import r64_mixed_xor_implied as r64
import r71_bcp_15sec_eight_formulas as r71
import r80_xor_structure_only as r80
import r67_xor_structural_diagnostics as r67
import r66_r65_blind_short_holdout as r66
import r73_fresh_quick_unseen_2025 as r73
import r81_fresh2026_xor_world as r81

PROTO="DRNAS-R82-WIDE-OFFICIAL-2025-2026-NOSCREEN-20261104-v1"
SALT="DRNAS-R82-PRECOMMIT-WIDE-RANDOM-ORIGINALS-2025-2026-20261104-v1"
MIN_READY=4
TARGET_2025,TARGET_2026=32,16
MAX_TRIES_2025,MAX_TRIES_2026=145,220
REPS, CAP, SHARDS = 2, 30.0, 12
MODES=("kissat_base","kissat_404","cadical_301","drnas_r28","drnas_r65","drnas_r80")

def ck(v, why):
    if not v: raise RuntimeError("R82_FAIL_CLOSED: "+str(why))
def digest(p): return r80.digest(p)
def shaorder(s):return hashlib.sha256((SALT+"/"+str(s)).encode()).hexdigest()
def writejson(p, obj): Path(p).write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")

def freeze(a):
    """Precommit two independent, unscreened random cohorts.

    The 2025 cohort excludes R72 possible attempts and R73 attempts.
    The 2026 cohort samples its entire official main pool, but tags whether
    the source was benchmarked in prior DRNAS runs. No XOR or speed filtering.
    """
    root=Path(a.out);root.mkdir(parents=True,exist_ok=True)
    r63m=json.loads((Path(a.prior)/"manifest.json").read_text())
    r66m=json.loads((Path(a.prior66)/"manifest.json").read_text())
    r67m=json.loads((Path(a.prior67)/"manifest.json").read_text())
    r73m=json.loads((Path(a.prior73)/"manifest.json").read_text())
    r81m=json.loads((Path(a.prior81)/"manifest.json").read_text())
    ck(r63m["protocol"]==r63.PROTO and len(r63m["cases"])==32,"R63 provenance")
    ck(r66m["protocol"]==r66.PROTO and len(r66m["cases"])==12,"R66 provenance")
    ck(r67m["protocol"]==r67.PROTO and len(r67m["cases"])==25,"R67 provenance")
    ck(r73m["protocol"]==r73.PROTO and len(r73m["cases"])==8,"R73 2025 provenance")
    ck(r81m["protocol"]==r81.PROTO and len(r81m["cases"])==6,"R81 2026 provenance")
    registered=set(r63m["excludes_previously_seen_gbd"])
    for m in (r63m,r66m,r67m,r81m):
        registered.update(x["gbd"] for x in m["cases"])
        registered.update(x["gbd"] for x in m.get("selection_attempts",m.get("attempts",[])))
    index26=r52.fetch_bytes(r52.URI,100000)
    ids26=[s.rsplit("/",1)[-1] for s in index26.decode().strip().splitlines()]
    ck(len(ids26)==400 and len(set(ids26))==400,"2026 official source index")
    score_bytes=r52.fetch_bytes(r52.SCORES,32*1024*1024)
    labels={x["instanceid"]:x["status"] for x in csv.DictReader(io.StringIO(score_bytes.decode()))
            if x["solverid"]=="biere_cadical3[main]"}
    ck(len(labels)==400,"2026 official verdict table")
    index25=r52.fetch_bytes(r73.SC2025,100000)
    ids25=[s.rsplit("/",1)[-1] for s in index25.decode().strip().splitlines()]
    ck(len(ids25)>=300 and len(set(ids25))==len(ids25),"2025 official index")
    prev_r72_salt="DRNAS-R72-NEW-SHA-AND-ATTEMPT-DISJOINT-20261103-v1"
    old_r72_candidates=sorted((g for g in ids25 if g not in registered and g not in set(ids26)),
        key=lambda g:hashlib.sha256((prev_r72_salt+":"+g).encode()).hexdigest())
    no2025=set(old_r72_candidates[:100])
    no2025.update(x["gbd"] for x in r73m["cases"])
    no2025.update(x["gbd"] for x in r73m["selection_attempts"])
    no2025.update(registered)
    prior_sha={x["sha256"] for m in (r63m,r66m,r67m,r73m,r81m) for x in m["cases"]}
    selected=[];attempts=[];new_sha=set()
    r32p.CNF_LIMIT=48*1024*1024
    specs=[(2025,ids25,TARGET_2025,MAX_TRIES_2025,no2025),
           (2026,ids26,TARGET_2026,MAX_TRIES_2026,set())]
    for year,ids,target,limit,excluded in specs:
        eligible=sorted((g for g in ids if g not in excluded and g not in
                         {x["gbd"] for x in selected}),key=lambda x:shaorder(str(year)+"/"+x))
        count=0
        for g in eligible[:limit]:
            if count>=target:break
            status=labels.get(g) if year==2026 else "not_loaded"
            note=dict(gbd=g,year=year,official_status=status)
            path=root/(str(year)+"-"+g+".cnf")
            if year==2026 and status not in ("sat-verified","unsat-verified"):
                note["state"]="UNVERIFIED_STATUS_2026"
                attempts.append(note);continue
            try:
                packed,redirect=r32p.request_url(
                    "https://benchmark-database.de/file/"+g,24*1024*1024,seconds=30)
                plain,compression=r32p.decode(packed)
                ck(len(plain)<=48*1024*1024,"DIMACS > 48 MiB")
                n,clauses=r32p.parse_dimacs_metadata(plain)
                path.write_bytes(plain)
                file_sha=digest(path)
                ck(file_sha not in new_sha and
                   (year!=2025 or file_sha not in prior_sha),"source SHA collision")
                structure=r63.inspect_exact_xor(path,n,clauses)
                row=dict(gbd=g,year=year,filename=path.name,sha256=file_sha,
                         official_status=("SAT" if status=="sat-verified" else
                                          "UNSAT" if status=="unsat-verified" else "UNKNOWN"),
                         source_url="https://benchmark-database.de/file/"+g,
                         source_verified_status=(year==2026),size_bytes=len(plain),
                         variables=n,clauses=clauses,bytes=len(plain),
                         compression=compression,compressed_bytes=len(packed),
                         redirect=redirect,
                         prior_drnas_benchmarked=(g in registered),
                         **structure)
                row["group"]=r64.group(row)
                row["structural_xor_positive"]=bool(
                     row["supported"] and row["complete_blocks"]>0)
                row["r67_features"]=r67.passive_features(path,row)
                new_sha.add(file_sha);selected.append(row);count+=1
                note.update(state="READY",sha256=file_sha,group=row["group"],
                            n_bytes=len(plain),previously_tested=row["prior_drnas_benchmarked"])
            except Exception as exc:
                path.unlink(missing_ok=True)
                note.update(state="FETCH_SIZE_OR_SCAN_EXCLUDED",
                    reason=(type(exc).__name__+": "+str(exc))[:240])
            attempts.append(note)
            print("R82_SOURCE",json.dumps(note,sort_keys=True),flush=True)
        print("R82_YEAR_READY",year,count,"of target",target,flush=True)
    ck(len(selected)>=4 and len({x["sha256"] for x in selected})==len(selected),
       "Not enough distinct eligible real original CNFs to benchmark")
    cases2025=sum(c["year"]==2025 for c in selected)
    cases2026=sum(c["year"]==2026 for c in selected)
    manifest=dict(protocol=PROTO,source_indices={"2025":r73.SC2025,"2026":r52.URI},
        index_2025_sha256=hashlib.sha256(index25).hexdigest(),
        index_2026_sha256=hashlib.sha256(index26).hexdigest(),
        2026_reference_scores_sha256=hashlib.sha256(score_bytes).hexdigest(),
        prior_manifests_sha256={
            "r63":digest(Path(a.prior)/"manifest.json"),
            "r66":digest(Path(a.prior66)/"manifest.json"),
            "r67":digest(Path(a.prior67)/"manifest.json"),
            "r73":digest(Path(a.prior73)/"manifest.json"),
            "r81":digest(Path(a.prior81)/"manifest.json")},
        selection_salt=SALT,selection_no_speed_or_xor_screening=True,
        limits={"raw_bytes":24*1024*1024,"plain_bytes":48*1024*1024,
                "2025_candidates":MAX_TRIES_2025,"2026_candidates":MAX_TRIES_2026},
        prior_2025_excluded_gbd=len(no2025),
        prior_2026_benchmarked_identifiers=len(registered),
        year_counts={"2025":cases2025,"2026":cases2026},
        source_selection_attempts=attempts,
        cases=selected,repetitions=REPS,cap_s=CAP,methods=MODES,shards=SHARDS,
        no_cherry_pick=True,
        # Primary decision fixed before trials, no changing based on results.
        precommitted_claim_rule={
            "primary_solver":"drnas_r65",
            "reference_solvers":["kissat_404","cadical_301"],
            "min_distinct_cases":24,"min_new_2025":12,
            "required_relative_par2_gain_vs_each":0.05,
            "bootstrap_paired_formula_95pct_lower_seconds_above":0,
            "requires_no_fewer_solved_than_both":True},
        limitations=[
          "2025 fresh cohort excludes documented R72 possible and R73 attempted sources, not all unrecorded experiments.",
          "2026 is SHA-ranked from ALL verified Main2026 and can include formerly tested DRNAS originals, reported explicitly.",
          "2025 official SAT/UNSAT labels not independently imported: SAT original witnesses validated, UNSAT lacks independent proof.",
          "2026 SAT answers validated with original model; UNSAT compared with published verified result, no new LRAT.",
          "Selection only by SHA hash, original year and size cap; never by XOR structure, solver answer or speed.",
          "XOR performance is a POST-HOC subgroup and is not representative of all 2025/2026 SAT formulas.",
          "Max 48MiB DIMACS excludes many large competition instances and biases the sample.",
          "Thirty seconds per attempt and runner CPU are NOT official SAT Competition scoring conditions.",
          "Two repetitions are paired on the same worker CPU; between-worker hardware variability remains.",
          "Genuine Kissat 4.0.4/CaDiCaL 3.0.1, not necessarily actual 2026 ranking winners.",
          "If sample size or confidence requirements fail, the test is descriptive only, even if PAR-2 appears better."])
    writejson(root/"manifest.json",manifest)
    (root/"source.sha256").write_text("".join(
        x["sha256"]+"  "+x["filename"]+"\n" for x in selected))
    print("R82_FREEZE_PASS",json.dumps(dict(sources=len(selected),
         source_2025=cases2025,source_2026=cases2026,
         attempted=len(attempts),replays_2026=sum(x["year"]==2026 and
         x["prior_drnas_benchmarked"] for x in selected))),flush=True)

def measure(a):
    root=Path(a.sources)
    mf=json.loads((root/"manifest.json").read_text())
    ck(mf["protocol"]==PROTO and MIN_READY<=len(mf["cases"])<=TARGET_2025+TARGET_2026,
       "invalid frozen manifest or insufficient source cohort")
    ck(0<=a.shard<SHARDS,"wrong shard index")
    bins=Path(a.bins).resolve()
    old=Path(a.native).resolve()
    ck((bins/"binaries.sha256").is_file() and (old/"binary.sha256").is_file(),
       "missing exact solver provenance files")
    import subprocess
    for folder,checksum in [(bins,"binaries.sha256"),(old,"binary.sha256")]:
        ck(subprocess.run(["sha256sum","-c",checksum],cwd=folder,
                          stdout=subprocess.DEVNULL).returncode==0,
           "binary checksum mismatch "+str(folder))
    solvers={"kissat_base":old/"kissat",
             "kissat_404":bins/"kissat_4_0_4",
             "cadical_301":bins/"cadical_3_0_1"}
    gf2=old/"r28_gf2"
    ck(all(x.is_file() and os.access(x,os.X_OK)
           for x in [gf2,*solvers.values()]),"non-executable solver")
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    r80.r65.MAX_PREP_S=2.0
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for case in mf["cases"][a.shard::SHARDS]:
        original=root/case["filename"]
        ck(digest(original)==case["sha256"],"CNF SHA changed")
        for rep in range(REPS):
            order=list(MODES)
            random.Random(int(shaorder(case["sha256"]+"/"+str(rep)),16)).shuffle(order)
            for mode in order:
                t0=time.monotonic()
                selected="kissat_base";route="kissat";added=0
                with tempfile.TemporaryDirectory(prefix="r82-") as td:
                    target=original
                    argv=[solvers["kissat_base"],original]
                    if mode in ("kissat_404","cadical_301"):
                        selected=mode
                        argv=[solvers[mode],original]
                        route=mode
                    elif mode=="drnas_r28":
                        route="r28"
                        argv=[gf2,original,solvers["kissat_base"]]
                    elif mode=="drnas_r65":
                        route="r28" if case["pure_exact_xor"] else "r65"
                    elif mode=="drnas_r80":
                        features=r63.inspect_exact_xor(original,case["variables"],case["clauses"])
                        ck(features["supported"]==case["supported"] and
                           features["complete_blocks"]==case["complete_blocks"] and
                           features["pure_exact_xor"]==case["pure_exact_xor"],
                           "runtime structure differs from frozen classification")
                        route=r80.decide(features)
                    if mode in ("drnas_r65","drnas_r80"):
                        if route=="r28":argv=[gf2,original,solvers["kissat_base"]]
                        elif route=="r65":
                            _,_,clauses,_,stats=r71.prepare(root,case)
                            added=len(clauses)
                            if clauses:
                                target=Path(td)/"augmented.cnf"
                                r64.augment(original,target,case["variables"],case["clauses"],clauses)
                            argv=[solvers["kissat_base"],target]
                    overhead=time.monotonic()-t0
                    answer,wall,timeout,solver_route=r80.run_solver(argv,original,CAP-overhead)
                    elapsed=time.monotonic()-t0
                    solved=(answer!="UNKNOWN" and not timeout and elapsed<=CAP)
                    if solved and case["source_verified_status"]: ck(answer==case["official_status"],
                        "solver verdict differs from externally verified 2026 result")
                    row=dict(gbd=case["gbd"],sha256=case["sha256"],
                        group=case["group"],year=case["year"],fresh_2025=(case["year"]==2025),
                        prior_drnas_benchmarked=case["prior_drnas_benchmarked"],
                        xor_positive=case["structural_xor_positive"],
                        rep=rep,mode=mode,answer=answer if solved else "TIMEOUT",
                        route=route,solver_route=solver_route,new_clauses=added,
                        preprocess_s=round(overhead,6),wall_s=round(min(elapsed,CAP),6),
                        par2_s=round(elapsed if solved else 2*CAP,6),
                        runner=os.environ.get("RUNNER_NAME",""),
                        sha_commit=os.environ.get("GITHUB_SHA",""),
                        run_id=os.environ.get("GITHUB_RUN_ID",""))
                    rows.append(row)
                    print("R81_TRIAL",json.dumps(
                        {k:row[k] for k in ("gbd","group","rep","mode","answer","route","wall_s","par2_s")}),
                        flush=True)
        writejson(out/"r82-shard.json",
            dict(protocol=PROTO,shard=a.shard,source_manifest_sha=digest(root/"manifest.json"),
                binary_sha={k:digest(p) for k,p in {**solvers,"r28":gf2}.items()},
                cpu=Path("/proc/cpuinfo").read_text(errors="replace")[:1200],
                rows=rows))
    expected=len(mf["cases"][a.shard::SHARDS])*REPS*len(MODES)
    ck(len(rows)==expected,"incomplete shard")
    print("R81_SHARD_PASS",a.shard,len(rows),flush=True)

def audit(a):
    root=Path(a.sources);mf=json.loads((root/"manifest.json").read_text())
    ck(mf["protocol"]==PROTO and MIN_READY<=len(mf["cases"])<=TARGET_2025+TARGET_2026,
       "bad frozen source or insufficient cohort")
    allrows=[];pins=set()
    for shard in range(SHARDS):
        p=Path(a.combined)/("r82-shard-"+str(shard))/"results"/"r81-shard.json"
        ck(p.is_file(),"missing shard "+str(shard))
        j=json.loads(p.read_text())
        ck(j["protocol"]==PROTO and j["shard"]==shard and
           j["source_manifest_sha"]==digest(root/"manifest.json"),"shard manifest mismatch")
        pins.add(json.dumps(j["binary_sha"],sort_keys=True))
        allrows.extend(j["rows"])
    ck(len(pins)==1 and len(allrows)==len(mf["cases"])*REPS*len(MODES),
       "binary drift or missing paired trial")
    for case in mf["cases"]:
        rr=[r for r in allrows if r["sha256"]==case["sha256"]]
        ck(len(rr)==REPS*len(MODES),"per-source incomplete rows")
        for rep in range(REPS):
            sample=[r for r in rr if r["rep"]==rep]
            ck(len(sample)==len(MODES) and {r["mode"] for r in sample}==set(MODES),
               "missing matched policy")
            ck(len({r["answer"] for r in sample if r["answer"]!="TIMEOUT"})<=1,
               "conflicting SAT/UNSAT answers")
            ck(all(r["answer"] in (case["official_status"],"TIMEOUT")
                   for r in sample) if case["source_verified_status"] else True,
               "published 2026 verdict mismatch")
    groups=["ALL","XOR_PRESENT","CONTROL","YEAR_2025","YEAR_2026","NEW_2026"]+sorted({c["group"] for c in mf["cases"]})
    summaries={}
    for group in groups:
        part=[r for r in allrows if group=="ALL" or
              (group=="XOR_PRESENT" and r["xor_positive"]) or
              (group=="CONTROL" and not r["xor_positive"]) or
              (group=="YEAR_2025" and r["year"]==2025) or
              (group=="YEAR_2026" and r["year"]==2026) or
              (group=="NEW_2026" and r["year"]==2026 and not r["prior_drnas_benchmarked"]) or
              r["group"]==group]
        summaries[group]={m:dict(trials=len([r for r in part if r["mode"]==m]),
                      solved=sum(r["answer"]!="TIMEOUT" for r in part if r["mode"]==m),
                      par2_s=round(sum(r["par2_s"] for r in part if r["mode"]==m),6),
                      min_s=min((r["wall_s"] for r in part if r["mode"]==m
                                 and r["answer"]!="TIMEOUT"),default=None))
                     for m in MODES}
    result=dict(status="PASS_UNOFFICIAL",protocol=PROTO,sources=len(mf["cases"]),
                repeats=REPS,cap_s=CAP,trials=len(allrows),
                solver_sha256=json.loads(next(iter(pins))),
                groups=dict(collections.Counter(c["group"] for c in mf["cases"])),
                xor_selected=mf["xor_selected"],
                controls_selected=mf["controls_selected"],
                summary=summaries,rows=allrows,
                limitations=mf["limitations"])
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    writejson(out/"r82-final.json",result)
    with (out/"paired.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["gbd","group","rep"]+list(MODES))
        w.writeheader()
        for c in mf["cases"]:
            for rep in range(REPS):
                rows=[r for r in allrows if r["gbd"]==c["gbd"] and r["rep"]==rep]
                d=dict(gbd=c["gbd"],group=c["group"],rep=rep)
                d.update({r["mode"]:r["par2_s"] for r in rows});w.writerow(d)
    md=["# DRNAS R82 — Wide precommitted 2025/2026 original SAT benchmark",
        "Unofficial experiment; 2025 new vs prior recorded attempt logs, 2026 allows flagged historical overlaps; 30s cap, 2 repeats.",
        "Selection used salted SHA-ranked official ids, source-size censoring only; never speed or XOR structure.",
        f"Sources {len(mf['cases'])}, XOR-positive {mf['xor_selected']}, controls {mf['controls_selected']}, trials {len(allrows)}.",
        "",f"| Solver | Solved / {len(mf['cases'])*REPS} | PAR-2 sum (s) | Min solved (s) |",
        "|---|---:|---:|---:|"]
    for m,s in summaries["ALL"].items():
        md.append(f"| {m} | {s['solved']}/{s['trials']} | {s['par2_s']:.3f} | {s['min_s']} |")
    md+=["","## Structural subsets"]
    for group in ["YEAR_2025","YEAR_2026","NEW_2026","XOR_PRESENT","CONTROL"]:
        md.extend(["",f"### {group}","| Method | Solved | PAR-2 sum (s) |","|---|---:|---:|"])
        for m,s in summaries[group].items():
            md.append(f"| {m} | {s['solved']}/{s['trials']} | {s['par2_s']:.3f} |")
    md+=["","## Limitations"]+["- "+x for x in mf["limitations"]]
    (out/"r82-final.md").write_text("\n".join(md)+"\n")
    print("R81_FINAL_AUDIT_PASS",json.dumps(
        {"trials":len(allrows),"sources":len(mf["cases"]),"xor":mf["xor_selected"],
         "summary":summaries["ALL"]}),flush=True)

def main():
    parser=argparse.ArgumentParser()
    s=parser.add_subparsers(dest="cmd",required=True)
    f=s.add_parser("freeze")
    for key in ("prior","prior66","prior67","prior73","prior81","out"): f.add_argument("--"+key,required=True)
    m=s.add_parser("measure")
    for key in ("sources","bins","native","out"):m.add_argument("--"+key,required=True)
    m.add_argument("--shard",required=True,type=int)
    au=s.add_parser("audit")
    for key in ("sources","combined","out"):au.add_argument("--"+key,required=True)
    a=parser.parse_args()
    if a.cmd=="freeze":freeze(a)
    elif a.cmd=="measure":measure(a)
    else:audit(a)
if __name__=="__main__":main()
