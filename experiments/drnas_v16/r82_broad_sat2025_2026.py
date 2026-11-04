#!/usr/bin/env python3
"""R82 broad SAT Competition 2025 previously unused primary holdout and 2026 retrospective audit.

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
import shutil

PROTO="DRNAS-R82-BROAD-REAL2025-2026-20261104-v1"
SALT="DRNAS-R82-PRECOMMITTED-BROAD-NO-RUNTIME-PRESCREEN-20261104-v1"
TARGET, MIN_READY, N25_TARGET, N26_TARGET = 64, 28, 40, 24
REPS, CAP, SHARDS, MAX_FETCH = 2, 45.0, 8, 220
MODES=("kissat_base","kissat_404","cadical_301","drnas_r28","drnas_r65","drnas_r80")

def ck(v, why):
    if not v: raise RuntimeError("R81_FAIL_CLOSED: "+str(why))
def digest(p): return r80.digest(p)
def shaorder(s):return hashlib.sha256((SALT+"/"+str(s)).encode()).hexdigest()
def writejson(p, obj): Path(p).write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")



def freeze(a):
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    roots={"r63":Path(a.prior63),"r66":Path(a.prior66),"r67":Path(a.prior67)}
    prior={}
    for key in roots:
        x=json.loads((roots[key]/"manifest.json").read_text())
        expected={"r63":(r63.PROTO,32),"r66":(r66.PROTO,12),"r67":(r67.PROTO,25)}[key]
        ck(x["protocol"]==expected[0] and len(x["cases"])==expected[1],
           key+" source archive mismatch")
        prior[key]=x
    mf73=json.loads((Path(a.prior73)/"manifest.json").read_text())
    ck(mf73["protocol"]==r73.PROTO and len(mf73["cases"])==8,
       "R73 2025 source registry mismatch")
    idx26=r52.fetch_bytes(r52.URI,100000)
    ids26=[s.strip().rsplit("/",1)[-1] for s in idx26.decode().splitlines() if s.strip()]
    idx25=r52.fetch_bytes(r73.SC2025,100000)
    ids25=[s.strip().rsplit("/",1)[-1] for s in idx25.decode().splitlines() if s.strip()]
    ck(len(ids26)==400 and len(set(ids26))==400,"2026 official index")
    ck(len(ids25)>=300 and len(set(ids25))==len(ids25),"2025 official index")
    seen_old=(set(prior["r63"]["excludes_previously_seen_gbd"])|
              {x["gbd"] for m in prior.values() for x in m["cases"]})
    # Conservatively exclude the FIRST 100 possible R72 official-2025
    # attempts, by the precise historic ranking protocol.
    salt72="DRNAS-R72-NEW-SHA-AND-ATTEMPT-DISJOINT-20261103-v1"
    c72=sorted((g for g in ids25 if g not in seen_old and g not in set(ids26)),
        key=lambda g:hashlib.sha256((salt72+":"+g).encode()).hexdigest())
    excluded=(set(ids26)|set(c72[:100])|
             {x["gbd"] for x in mf73["cases"]}|
             {x["gbd"] for x in mf73["selection_attempts"]})
    c25=sorted([g for g in ids25 if g not in excluded],key=shaorder)
    ck(len(c25)>10,"not enough truly new 2025 source IDs")
    r32p.CNF_LIMIT=48*1024*1024
    knownsha=({x["sha256"] for m in prior.values() for x in m["cases"]}|
             {x["sha256"] for x in mf73["cases"]})
    fresh=[];attempts=[]
    for g in c25[:MAX_FETCH]:
        if len(fresh)>=N25_TARGET:break
        p=out/(g+".cnf")
        note=dict(gbd=g,year=2025)
        try:
            raw,redirect=r32p.request_url(
                "https://benchmark-database.de/file/"+g,28*1024*1024,seconds=35)
            cnf,compression=r32p.decode(raw)
            ck(len(cnf)<=48*1024*1024,"2025 source >48MiB")
            n,m=r32p.parse_dimacs_metadata(cnf)
            p.write_bytes(cnf)
            hashvalue=digest(p)
            ck(hashvalue not in knownsha,"previously used source SHA")
            feats=r63.inspect_exact_xor(p,n,m)
            x=dict(gbd=g,filename=p.name,sha256=hashvalue,official_status="UNKNOWN",
                variables=n,clauses=m,bytes=len(cnf),**feats)
            x.update(source_year=2025,cohort="2025_FRESH",
                     group=r64.group(x),compression=compression,redirect=redirect,
                     structural_xor_positive=bool(feats["supported"] and
                                                  feats["complete_blocks"]>0))
            x["r67_features"]=r67.passive_features(p,x)
            fresh.append(x);knownsha.add(hashvalue)
            note.update(state="NEW_FROZEN_NO_SOLVER_SCREEN",sha256=hashvalue,
                        group=x["group"],bytes=len(cnf))
        except Exception as e:
            p.unlink(missing_ok=True)
            if "previously used source" in str(e):raise
            note.update(state="EXCLUDED_SIZE_OR_DOWNLOAD",
                        reason=(type(e).__name__+": "+str(e))[:200])
        attempts.append(note)
        print("R82_2025_SCAN",json.dumps(note),flush=True)
    # Retrospective archive: real, already tested 2026 formulas. It is never
    # mixed with the prospective 2025 primary claim.
    prior26=[]
    for key in ("r63","r66","r67"):
        for x in prior[key]["cases"]:
            p=roots[key]/x["filename"]
            ck(p.is_file() and digest(p)==x["sha256"],key+" source SHA drift")
            prior26.append((dict(x),p,key))
    ck(len(prior26)==69 and len({x[0]["gbd"] for x in prior26})==69,
       "historic 2026 source union must be 69 unique")
    yes=sorted((x for x in prior26 if x[0]["supported"] and
                x[0]["complete_blocks"]>0),key=lambda x:shaorder(x[0]["gbd"]))
    no=sorted((x for x in prior26 if not (x[0]["supported"] and
               x[0]["complete_blocks"]>0)),key=lambda x:shaorder(x[0]["gbd"]))
    chosen=yes[:12]+no[:N26_TARGET-min(12,len(yes))]
    ck(len(chosen)==N26_TARGET,"2026 XOR-stratified replay source quota")
    replay=[]
    for x,p,key in chosen:
        dst=out/x["filename"]
        ck(not dst.exists(),"2025/2026 identity collision")
        shutil.copyfile(p,dst)
        ck(digest(dst)==x["sha256"],"copied CNF mismatch")
        x.update(source_year=2026,cohort="2026_REPLAY",
                 structural_xor_positive=bool(x["supported"] and
                      x["complete_blocks"]>0),group=r64.group(x),historic_origin=key)
        x["r67_features"]=r67.passive_features(dst,x)
        ck(x["official_status"] in ("SAT","UNSAT"),"missing verified 2026 result")
        replay.append(x)
    cases=fresh+replay
    ck(len(fresh)>=8 and len(cases)>=MIN_READY and
       len({c["sha256"] for c in cases})==len(cases),
       "too few fresh source inputs or SHA duplicates")
    manifest=dict(protocol=PROTO,source="SAT Competition official Main 2025 plus 2026",
        cases=cases,source_index_2025=r73.SC2025,source_index_2026=r52.URI,
        index25_sha256=hashlib.sha256(idx25).hexdigest(),
        index26_sha256=hashlib.sha256(idx26).hexdigest(),
        previous_manifest_sha={k:digest(v/"manifest.json") for k,v in roots.items()},
        prior73_sha=digest(Path(a.prior73)/"manifest.json"),
        selection_salt=SALT,previous_r72_window_excluded=100,
        previous_r73_attempts_excluded=len(mf73["selection_attempts"]),
        selected_without_solver_runtime=True,selection_attempts=attempts,
        target_new2025=N25_TARGET,actual_new2025=len(fresh),
        target_replay2026=N26_TARGET,actual_replay2026=len(replay),
        xor2025=sum(x["structural_xor_positive"] for x in fresh),
        xor2026=sum(x["structural_xor_positive"] for x in replay),
        selection_2026="12 exact XOR + 12 other SHA ordered, retrospective",
        modes=list(MODES),cap_s=CAP,repeat=REPS,shards=SHARDS,
        limitations=[
          "Primary 2025 sources disjoint from documented R72/R73 source scans, not provably all unpublished tests.",
          "Secondary 2026 sources previously tested and XOR-stratified, never presented as blind.",
          "No solver-runtime screening of source inclusion; size-censored <=48MiB.",
          "Unscannable does NOT mean XOR-free.",
          "2025 SAT witnesses checked on original CNF, but UNSAT verdicts not independently certified.",
          "2026 SAT/UNSAT verdicts checked against imported verified official status; no LRAT proofs.",
          "45s limit, GitHub runners and solver lineup are not official world competition conditions.",
          "Kissat 4.0.4 and CaDiCaL 3.0.1 are strong reproducible references, not all top 2026 solvers.",
          "R80 scan/activation overhead is included, no hidden oracle or formula speed based selection.",
          "Independent primary 2025 conclusions require sample size and paired bootstrap checks."
        ])
    writejson(out/"manifest.json",manifest)
    (out/"source.sha256").write_text("".join(
        x["sha256"]+"  "+x["filename"]+"\n" for x in cases))
    print("R82_FREEZE_PASS",json.dumps(dict(new2025=len(fresh),
        retrospective2026=len(replay),xor2025=manifest["xor2025"],
        xor2026=manifest["xor2026"],cases=len(cases),attempts=len(attempts))),flush=True)

def measure(a):
    root=Path(a.sources)
    mf=json.loads((root/"manifest.json").read_text())
    ck(mf["protocol"]==PROTO and MIN_READY<=len(mf["cases"])<=TARGET,
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
                    if solved and case["official_status"]!="UNKNOWN": ck(answer==case["official_status"],
                        "solver verdict differs from externally verified 2026 result")
                    row=dict(gbd=case["gbd"],sha256=case["sha256"],cohort=case["cohort"],
                        group=case["group"],xor_positive=case["structural_xor_positive"],
                        rep=rep,mode=mode,answer=answer if solved else "TIMEOUT",
                        route=route,solver_route=solver_route,new_clauses=added,
                        preprocess_s=round(overhead,6),wall_s=round(min(elapsed,CAP),6),
                        par2_s=round(elapsed if solved else 2*CAP,6),
                        runner=os.environ.get("RUNNER_NAME",""),
                        sha_commit=os.environ.get("GITHUB_SHA",""),
                        run_id=os.environ.get("GITHUB_RUN_ID",""))
                    rows.append(row)
                    print("R82_TRIAL",json.dumps(
                        {k:row[k] for k in ("gbd","group","rep","mode","answer","route","wall_s","par2_s")}),
                        flush=True)
        writejson(out/"r82-shard.json",
            dict(protocol=PROTO,shard=a.shard,source_manifest_sha=digest(root/"manifest.json"),
                binary_sha={k:digest(p) for k,p in {**solvers,"r28":gf2}.items()},
                cpu=Path("/proc/cpuinfo").read_text(errors="replace")[:1200],
                rows=rows))
    expected=len(mf["cases"][a.shard::SHARDS])*REPS*len(MODES)
    ck(len(rows)==expected,"incomplete shard")
    print("R82_SHARD_PASS",a.shard,len(rows),flush=True)

def audit(a):
    root=Path(a.sources);mf=json.loads((root/"manifest.json").read_text())
    ck(mf["protocol"]==PROTO and MIN_READY<=len(mf["cases"])<=TARGET,
       "bad frozen source or insufficient cohort")
    allrows=[];pins=set()
    for shard in range(SHARDS):
        p=Path(a.combined)/("r82-shard-"+str(shard))/"results"/"r82-shard.json"
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
            ck(all(r["answer"] in ((case["official_status"],"TIMEOUT") if case["official_status"]!="UNKNOWN" else ("SAT","UNSAT","TIMEOUT")) for r in sample),
               "published 2026 verdict mismatch")
    groups=["ALL","2025_FRESH","2026_REPLAY","XOR_PRESENT","NO_PROVEN_XOR"]+sorted({c["group"] for c in mf["cases"]})
    summaries={}
    for group in groups:
        part=[r for r in allrows if group=="ALL" or r["cohort"]==group or
              (group=="XOR_PRESENT" and r["xor_positive"]) or
              (group=="NO_PROVEN_XOR" and not r["xor_positive"]) or r["group"]==group]
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
                new2025=mf["actual_new2025"],replay2026=mf["actual_replay2026"],
                summary=summaries,rows=allrows,
                limitations=mf["limitations"])
    # Primary decision was frozen BEFORE any timing. Formula-level bootstrap
    # explicitly tests the winner against the strongest fixed reference on
    # the prospective 2025 cohort, resampling WHOLE formulas (not repeats).
    fcases=[c for c in mf["cases"] if c["cohort"]=="2025_FRESH"]
    reference_modes=("kissat_base","kissat_404","cadical_301")
    per={}
    for case in fcases:
        current=[r for r in allrows if r["sha256"]==case["sha256"]]
        per[case["gbd"]]={mode:sum(r["par2_s"] for r in current if r["mode"]==mode)
                          for mode in MODES}
    case_values=list(per.values())
    n=len(case_values)
    total={mode:sum(v[mode] for v in case_values) for mode in MODES}
    strongest=min(reference_modes,key=lambda mode:total[mode])
    delta=total[strongest]-total["drnas_r80"]
    wins=sum(v["drnas_r80"]+.01<min(v[m] for m in reference_modes)
             for v in case_values)
    losses=sum(v["drnas_r80"]>min(v[m] for m in reference_modes)+.01
               for v in case_values)
    informative=sum(any(v[m]<REPS*CAP*2 for m in MODES) for v in case_values)
    rng=random.Random(820261104)
    boot=[]
    for _ in range(2000):
        sampled=[case_values[rng.randrange(n)] for k in range(n)]
        best=min(sum(v[m] for v in sampled) for m in reference_modes)
        boot.append(best-sum(v["drnas_r80"] for v in sampled))
    boot.sort()
    lower,upper=boot[int(.025*len(boot))],boot[int(.975*len(boot))-1]
    adequately_broad=(n>=30 and informative>=8)
    strong=(adequately_broad and delta>0 and wins>=5 and lower>0)
    result["predeclared_primary_2025_evidence"]=dict(
        independent_new_sources=n,informative_sources=informative,
        R80_wins_by_distinct_source=wins,R80_losses_by_distinct_source=losses,
        fixed_best_reference=strongest,
        reference_par2_s=round(total[strongest],3),
        r80_par2_s=round(total["drnas_r80"],3),
        par2_advantage_pct=round(100*delta/total[strongest],4)
                           if total[strongest] else None,
        paired_cluster_bootstrap_delta_CI95_s=[round(lower,3),round(upper,3)],
        breadth_criterion_met=adequately_broad,
        robust_general_advantage_criterion_met=strong,
        verdict="BROAD_EVIDENCE_FOR_R80" if strong else
                "NO_BROAD_ADVANTAGE_ESTABLISHED")
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
    md=["# DRNAS R82 — Broad original SAT2025 fresh / SAT2026 retrospective",
        "Unofficial primary prospective 2025 plus secondary retrospective 2026; 45s cap, 2 repeats.",
        "Selection used SHA-ranked official ids and parity structure, never solve speed.",
        f"Sources {len(mf['cases'])}: new 2025 = {mf['actual_new2025']}; replay 2026 = {mf['actual_replay2026']}; trials {len(allrows)}.",
        "",f"| Solver | Solved / {len(mf['cases'])*REPS} | PAR-2 sum (s) | Min solved (s) |",
        "|---|---:|---:|---:|"]
    for m,s in summaries["ALL"].items():
        md.append(f"| {m} | {s['solved']}/{s['trials']} | {s['par2_s']:.3f} | {s['min_s']} |")
    md+=["","## Structural subsets"]
    for group in ["2025_FRESH","2026_REPLAY","XOR_PRESENT","NO_PROVEN_XOR"]:
        md.extend(["",f"### {group}","| Method | Solved | PAR-2 sum (s) |","|---|---:|---:|"])
        for m,s in summaries[group].items():
            md.append(f"| {m} | {s['solved']}/{s['trials']} | {s['par2_s']:.3f} |")
    md+=["","## Preregistered prospective 2025 assessment",
         str(result["predeclared_primary_2025_evidence"]),
         "Criterion: >=30 new formulas, >=8 informative, >=5 distinct source wins, lower bootstrap 95% CI >0",
         "2025 UNSAT answers are provisional without published proof status.",
         "","## Limitations"]+["- "+x for x in mf["limitations"]]
    (out/"r82-final.md").write_text("\n".join(md)+"\n")
    print("R82_FINAL_AUDIT_PASS",json.dumps(
        {"trials":len(allrows),"sources":len(mf["cases"]),"new2025":mf["actual_new2025"],
         "summary":summaries["ALL"]}),flush=True)

def main():
    parser=argparse.ArgumentParser()
    s=parser.add_subparsers(dest="cmd",required=True)
    f=s.add_parser("freeze")
    for key in ("prior63","prior66","prior67","prior73","out"): f.add_argument("--"+key,required=True)
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
