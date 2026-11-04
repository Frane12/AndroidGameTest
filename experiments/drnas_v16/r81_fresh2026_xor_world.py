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

PROTO="DRNAS-R81-SOURCE-DISJOINT-REAL2026-XOR-WORLD-20261104-v1"
SALT="DRNAS-R81-BLIND-UNUSED-OFFICIAL2026-STRUCTURAL-XOR-20261104-v1"
TARGET, POS_TARGET, CTRL_TARGET, MIN_READY = 10, 3, 7, 4
REPS, CAP, SHARDS, MAX_FETCH = 2, 25.0, 4, 170
MODES=("kissat_base","kissat_404","cadical_301","drnas_r28","drnas_r65","drnas_r80")

def ck(v, why):
    if not v: raise RuntimeError("R81_FAIL_CLOSED: "+str(why))
def digest(p): return r80.digest(p)
def shaorder(s):return hashlib.sha256((SALT+"/"+str(s)).encode()).hexdigest()
def writejson(p, obj): Path(p).write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")

def freeze(a):
    root=Path(a.out);root.mkdir(parents=True,exist_ok=True)
    old=json.loads((Path(a.prior)/"manifest.json").read_text())
    ck(old["protocol"]==r63.PROTO and len(old["cases"])==32,"R63 historical registry mismatch")
    earlier66=json.loads((Path(a.prior66)/"manifest.json").read_text())
    earlier67=json.loads((Path(a.prior67)/"manifest.json").read_text())
    ck(earlier66["protocol"]==r66.PROTO and len(earlier66["cases"])==12,
       "R66 historical original registry missing")
    ck(earlier67["protocol"]==r67.PROTO and len(earlier67["cases"])==25,
       "R67 historical original registry missing")
    seen=set(old["excludes_previously_seen_gbd"])|{c["gbd"] for c in old["cases"]}
    seen.update(c["gbd"] for c in earlier66["cases"])
    seen.update(c["gbd"] for c in earlier67["cases"])
    ck(len(seen)>=155,"R63/R66/R67 benchmarked-source exclusion incomplete")
    raw_index=r52.fetch_bytes(r52.URI,100000)
    ids=[u.rsplit("/",1)[-1] for u in raw_index.decode().strip().splitlines()]
    ck(len(ids)==400 and len(set(ids))==400,"official 2026 index differs from freeze")
    scores=r52.fetch_bytes(r52.SCORES,32*1024*1024)
    official={x["instanceid"]:x["status"] for x in csv.DictReader(io.StringIO(scores.decode()))
              if x["solverid"]=="biere_cadical3[main]"}
    ck(len(official)==400,"verified 2026 status sheet incomplete")
    candidates=sorted((g for g in ids if g not in seen),key=shaorder)
    positives=[];controls=[];attempts=[]
    r32p.CNF_LIMIT=48*1024*1024
    for g in candidates[:MAX_FETCH]:
        if len(positives)>=POS_TARGET and len(controls)>=CTRL_TARGET: break
        status=official.get(g)
        trace={"gbd":g,"official_score_status":status}
        if status not in ("sat-verified","unsat-verified"):
            trace["state"]="UNVERIFIED_STATUS";attempts.append(trace);continue
        path=root/(g+".cnf")
        try:
            payload,redirect=r32p.request_url("https://benchmark-database.de/file/"+g,
                                                28*1024*1024,seconds=60)
            plain,compression=r32p.decode(payload)
            ck(len(plain)<=48*1024*1024,"original exceeds 48MiB")
            n,m=r32p.parse_dimacs_metadata(plain)
            path.write_bytes(plain)
            features=r63.inspect_exact_xor(path,n,m)
            positive=bool(features["supported"] and features["complete_blocks"]>0)
            bucket=positives if positive else controls
            if len(bucket)>=(POS_TARGET if positive else CTRL_TARGET):
                path.unlink(missing_ok=True)
                trace["state"]="STRUCTURAL_QUOTA_FULL"
            else:
                row=dict(gbd=g,filename=path.name,sha256=digest(path),
                    official_status="SAT" if status=="sat-verified" else "UNSAT",
                    variables=n,clauses=m,bytes=len(plain),
                    source_url="https://benchmark-database.de/file/"+g,
                    compression=compression,compressed_bytes=len(payload),
                    redirect=redirect,**features)
                row["group"]=r64.group(row)
                row["structural_xor_positive"]=positive
                bucket.append(row)
                trace.update(state="SELECTED",group=row["group"],
                             sha256=row["sha256"],xor_blocks=row["complete_blocks"],
                             bytes=row["bytes"])
        except Exception as e:
            path.unlink(missing_ok=True)
            trace.update(state="FETCH_SIZE_OR_SCAN_EXCLUDED",
                         reason=(type(e).__name__+": "+str(e))[:230])
        attempts.append(trace)
        print("R81_SOURCE_SCAN",json.dumps(trace),flush=True)
    # Quotas are TARGETS, never hard failures: include every verifiable new
    # source up to quota; the 400-instance official pool may be exhausted.
    # Stop only if too few genuine inputs or no XOR/control comparison at all.
    chosen=positives[:POS_TARGET]+controls[:TARGET-min(POS_TARGET,len(positives))]
    ck(MIN_READY<=len(chosen)<=TARGET and
       len({x["gbd"] for x in chosen})==len(chosen) and
       any(x["structural_xor_positive"] for x in chosen) and
       any(not x["structural_xor_positive"] for x in chosen),
       "not enough independently verified source-diverse inputs for even a small paired study")
    allnames={x["filename"] for x in chosen}
    for p in root.glob("*.cnf"):
        if p.name not in allnames:p.unlink()
    for row in chosen:
        ck(row["gbd"] not in seen,"prior source was reused")
        ck(digest(root/row["filename"])==row["sha256"],"source hash drift")
        # R65 requires passive structural features; calculate before any solver timing.
        row["r67_features"]=r67.passive_features(root/row["filename"],row)
    manifest=dict(protocol=PROTO,source="SAT Competition 2026 Main original CNFs",
        source_index=r52.URI,official_status_csv=r52.SCORES,
        official_index_sha256=hashlib.sha256(raw_index).hexdigest(),
        official_scores_sha256=hashlib.sha256(scores).hexdigest(),
        previous_registry_manifest_sha256=digest(Path(a.prior)/"manifest.json"),
        r66_registry_sha256=digest(Path(a.prior66)/"manifest.json"),
        r67_registry_sha256=digest(Path(a.prior67)/"manifest.json"),
        excluded_prior_gbd_count=len(seen), excluded_prior_gbds=sorted(seen),
        selection_salt=SALT,selection_method="salted GBD order; pre-solver complete parity pattern only",
        selection_not_using_solver_runtime=True,
        target_xor=POS_TARGET,target_controls=CTRL_TARGET,max_sources=TARGET,
        actual_sources=len(chosen),shortfall=TARGET-len(chosen),
        xor_selected=sum(x["structural_xor_positive"] for x in chosen),
        controls_selected=sum(not x["structural_xor_positive"] for x in chosen),
        candidates_inspected=len(attempts),attempts=attempts,
        cases=chosen,repetitions=REPS,cap_s=CAP,methods=MODES,shards=SHARDS,
        limitations=[
          "Previously unbenchmarked within R63 historical registries plus R66/R67 completed cohorts; cannot prove not viewed by any other experiment.",
          "Stratified original 2026 sample by complete XOR clause patterns; non-representative of the full 400.",
          "Source selection uses no solver runtimes and includes all overhead of DRNAS preprocessing.",
          "Partial parity-shaped groups are never asserted as sound complete XOR equations.",
          "One core affinity, serial randomized methods per formula-repetition; GitHub runner host variation remains.",
          "Timeout 25s and PAR2 50s do not match official competition conditions.",
          "SAT witness checked against original CNF; UNSAT checked against published verified status, not new LRAT.",
          "Kissat 4.0.4 and CaDiCaL 3.0.1 are genuine strong reference solver versions, not claimed 2026 winners.",
          "A quota shortfall is accepted without replacement; exact achieved counts disclosed."
        ])
    writejson(root/"manifest.json",manifest)
    (root/"source.sha256").write_text("".join(
        x["sha256"]+"  "+x["filename"]+"\n" for x in chosen))
    print("R81_FREEZE_PASS",json.dumps({"cases":len(chosen),
         "xor":manifest["xor_selected"],"controls":manifest["controls_selected"],
         "excluded_prior":len(seen),"tried":len(attempts)}),flush=True)

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
                with tempfile.TemporaryDirectory(prefix="r81-") as td:
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
                    if solved: ck(answer==case["official_status"],
                        "solver verdict differs from externally verified 2026 result")
                    row=dict(gbd=case["gbd"],sha256=case["sha256"],
                        group=case["group"],xor_positive=case["structural_xor_positive"],
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
        writejson(out/"r81-shard.json",
            dict(protocol=PROTO,shard=a.shard,source_manifest_sha=digest(root/"manifest.json"),
                binary_sha={k:digest(p) for k,p in {**solvers,"r28":gf2}.items()},
                cpu=Path("/proc/cpuinfo").read_text(errors="replace")[:1200],
                rows=rows))
    expected=len(mf["cases"][a.shard::SHARDS])*REPS*len(MODES)
    ck(len(rows)==expected,"incomplete shard")
    print("R81_SHARD_PASS",a.shard,len(rows),flush=True)

def audit(a):
    root=Path(a.sources);mf=json.loads((root/"manifest.json").read_text())
    ck(mf["protocol"]==PROTO and MIN_READY<=len(mf["cases"])<=TARGET,
       "bad frozen source or insufficient cohort")
    allrows=[];pins=set()
    for shard in range(SHARDS):
        p=Path(a.combined)/("r81-shard-"+str(shard))/"results"/"r81-shard.json"
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
            ck(all(r["answer"] in (case["official_status"],"TIMEOUT") for r in sample),
               "published 2026 verdict mismatch")
    groups=["ALL","XOR_PRESENT","CONTROL"]+sorted({c["group"] for c in mf["cases"]})
    summaries={}
    for group in groups:
        part=[r for r in allrows if group=="ALL" or
              (group=="XOR_PRESENT" and r["xor_positive"]) or
              (group=="CONTROL" and not r["xor_positive"]) or r["group"]==group]
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
    writejson(out/"r81-final.json",result)
    with (out/"paired.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["gbd","group","rep"]+list(MODES))
        w.writeheader()
        for c in mf["cases"]:
            for rep in range(REPS):
                rows=[r for r in allrows if r["gbd"]==c["gbd"] and r["rep"]==rep]
                d=dict(gbd=c["gbd"],group=c["group"],rep=rep)
                d.update({r["mode"]:r["par2_s"] for r in rows});w.writerow(d)
    md=["# DRNAS R81 — Fresh official SAT2026 XOR structural holdout",
        "Unofficial source-disjoint experiment; same original CNFs, 25s cap, 2 repeats.",
        "Selection used SHA-ranked official ids and parity structure, never solve speed.",
        f"Sources {len(mf['cases'])}, XOR-positive {mf['xor_selected']}, controls {mf['controls_selected']}, trials {len(allrows)}.",
        "",f"| Solver | Solved / {len(mf['cases'])*REPS} | PAR-2 sum (s) | Min solved (s) |",
        "|---|---:|---:|---:|"]
    for m,s in summaries["ALL"].items():
        md.append(f"| {m} | {s['solved']}/{s['trials']} | {s['par2_s']:.3f} | {s['min_s']} |")
    md+=["","## Structural subsets"]
    for group in ["XOR_PRESENT","CONTROL"]:
        md.extend(["",f"### {group}","| Method | Solved | PAR-2 sum (s) |","|---|---:|---:|"])
        for m,s in summaries[group].items():
            md.append(f"| {m} | {s['solved']}/{s['trials']} | {s['par2_s']:.3f} |")
    md+=["","## Limitations"]+["- "+x for x in mf["limitations"]]
    (out/"r81-final.md").write_text("\n".join(md)+"\n")
    print("R81_FINAL_AUDIT_PASS",json.dumps(
        {"trials":len(allrows),"sources":len(mf["cases"]),"xor":mf["xor_selected"],
         "summary":summaries["ALL"]}),flush=True)

def main():
    parser=argparse.ArgumentParser()
    s=parser.add_subparsers(dest="cmd",required=True)
    f=s.add_parser("freeze")
    for key in ("prior","prior66","prior67","out"): f.add_argument("--"+key,required=True)
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
