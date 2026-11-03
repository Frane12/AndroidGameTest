#!/usr/bin/env python3
"""R72: never-previously-attempted real SAT sources, selected for medium solve time.

The entire R63/R66/R67 historical ID/attempt ledger and accepted-source
SHA-256 registry is imported and hashed. R68-R71 use subsets of R67.
2026 Main is searched first; 2025 official benchmark list is supplemental.
Only source IDs absent from this historical union and SHA-disjoint are eligible.
One separate baseline Kissat screening run determines the 5-30s cohort;
this is baseline-conditioned prospective selection, NOT a blind leaderboard.
A failure to discover eight 5-30s instances FAILS CLOSED (no replays).
"""
from __future__ import annotations
import argparse, collections, csv, hashlib, io, json, os, random, tempfile
import time
from pathlib import Path

import r28_exact_gf2_benchmark as r28
import r32p_real_satcomp26_benchmark as r32p
import r52_prospective_2026_toprefs as r52
import r63_real2026_xor_prevalence_fallback as r63
import r64_mixed_xor_implied as r64
import r65_xor_cnf_feedback as r65
import r67_xor_structural_diagnostics as r67
import r68_xor_2sec_forensics as r68
import r71_bcp_15sec_eight_formulas as r71

PROTO="DRNAS-R72-NEVER-SEEN-5TO30S-20261103-v1"
SALT="DRNAS-R72-NEW-SHA-AND-ATTEMPT-DISJOINT-20261103-v1"
N=8
REPS=2
SHARDS=8
MODES=("original","full_r65","bcp_filtered")
SCREEN_MIN=5.0
SCREEN_CAP=30.0
BENCH_CAP=45.0
MAX_2025_ATTEMPTS=100
RAW_MAX=28*1024*1024
CNF_MAX=48*1024*1024
SC2025="https://raw.githubusercontent.com/satcompetition/2025/main/downloads/SC2025.uri"

def check(ok,msg):
    if not ok:raise RuntimeError("R72_FAIL_CLOSED "+str(msg))

def digest(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for c in iter(lambda:f.read(1<<20),b""):h.update(c)
    return h.hexdigest()

def order(g):
    return hashlib.sha256((SALT+":"+g).encode()).hexdigest()

def history(args):
    r63_final=json.loads(Path(args.r63).read_text())
    old=r63_final["manifest"]
    r66m=json.loads(Path(args.r66).read_text())
    r67m=json.loads(Path(args.r67).read_text())
    r67_final=json.loads(Path(args.r67final).read_text())
    check(r63_final["protocol"]==r63.PROTO and old["protocol"]==r63.PROTO
        and len(old["cases"])==32,"R63 historical registry invalid")
    check(r66m["protocol"]=="DRNAS-R66-R65-NEW-SOURCE-BLIND-SHORT-20261103-v1",
          "R66 registry invalid")
    check(r67m["protocol"]==r67.PROTO and r67_final["protocol"]==r67.PROTO
          and r67_final["status"]=="PASS", "R67 registry/final audit invalid")
    check(len(r67m["cases"])==25 and
          {c["gbd"] for c in r67m["cases"]} ==
          {c["gbd"] for c in r67_final["per_formula"]},
          "R67 source/audit discrepancy")
    seen=set(old["excludes_previously_seen_gbd"])
    shas=set()
    count_by_manifest={}
    for name,m in (("r63",old),("r66",r66m),("r67",r67m)):
        attempted={x["gbd"] for x in m["selection_attempts"]}
        cases={c["gbd"] for c in m["cases"]}
        count_by_manifest[name]=dict(attempts=len(attempted),accepted=len(cases))
        check(len(attempted)==len(m["selection_attempts"]),name+" repeated attempt")
        seen |= attempted|cases
        for c in m["cases"]:
            shas.add(c["sha256"])
    # R63 oldest-history registry + its source attempts + R66 attempts
    # must agree with the exact prior exclusion count recorded by R67.
    old_count=(set(old["excludes_previously_seen_gbd"])|
               {x["gbd"] for x in old["selection_attempts"]}|
               {x["gbd"] for x in old["cases"]}|
               {x["gbd"] for x in r66m["selection_attempts"]}|
               {x["gbd"] for x in r66m["cases"]})
    check(len(old_count)==r67m["prior_excluded_gbd_count"],
          "R67 prior exclusion count drift")
    check(len(seen)>=len(old_count)+25,"R67 attempts absent from registry")
    binary_sha=r67_final["binary_sha"][0]
    check(len(binary_sha)==64,"missing pinned Kissat SHA")
    return seen,shas,binary_sha,dict(
        old_historical_ids=len(old["excludes_previously_seen_gbd"]),
        total_excluded_ids=len(seen),accepted_known_sha=len(shas),
        included_manifests=count_by_manifest,
        binary_sha=binary_sha,
        r63_sha=digest(args.r63),r66_sha=digest(args.r66),
        r67_sha=digest(args.r67),r67_final_sha=digest(args.r67final),
        notes="R68-R71 exclusively replayed accepted R67 original IDs")

def catalogs():
    index=r52.fetch_bytes(r52.URI,100000)
    ids26=[u.rsplit("/",1)[-1] for u in index.decode().strip().splitlines()]
    check(len(ids26)==400 and len(set(ids26))==400,"2026 Main index changed")
    csv_bytes=r52.fetch_bytes(r52.SCORES,32*1024*1024)
    score_rows=[x for x in csv.DictReader(io.StringIO(csv_bytes.decode()))
                if x["solverid"]=="biere_cadical3[main]" and
                x["instanceid"] in set(ids26)]
    check(len(score_rows)==400,"2026 reference score count changed")
    scores={x["instanceid"]:x for x in score_rows}
    index25=r52.fetch_bytes(SC2025,100000)
    ids25=[u.rsplit("/",1)[-1] for u in index25.decode().strip().splitlines()]
    check(len(ids25)>=300 and len(set(ids25))==len(ids25),
          "2025 official GBD URI list invalid")
    return ids26,scores,ids25,dict(
        index26_sha=hashlib.sha256(index).hexdigest(),
        scores26_sha=hashlib.sha256(csv_bytes).hexdigest(),
        index25_sha=hashlib.sha256(index25).hexdigest())

def freeze(args):
    root=Path(args.out);root.mkdir(parents=True,exist_ok=True)
    seen,known_sha,binary_sha,registry=history(args)
    binary=Path(args.kissat).resolve()
    check(binary.is_file() and digest(binary)==binary_sha,"Kissat binary SHA drift")
    ids26,scores,ids25,catsha=catalogs()
    unattempted26=[g for g in ids26 if g not in seen]
    # 2026 known CaDiCaL times prioritize plausibly soluble cases, without
    # testing DRNAS or using its performance. Still verify actual Kissat time.
    candidates26=sorted(
        (g for g in unattempted26 if scores[g]["status"] in
          ("sat-verified","unsat-verified")),
        key=lambda g:(not (3 <= float(scores[g]["runtime"]) <= 80),order(g)))
    candidates25=sorted((g for g in ids25 if g not in seen and
                         g not in set(ids26)),key=order)
    check(not(set(candidates25)&seen) and not(set(candidates26)&seen),
          "previously attempted GBD leaked into R72")
    print("R72_HISTORY_PASS",json.dumps({
        **registry,"unused_main2026":len(unattempted26),
        "unused_2025_additional":len(candidates25),
        "2025_fallback_if_needed":True}),flush=True)
    r32p.CNF_LIMIT=CNF_MAX
    r68.PULSE_SECONDS=SCREEN_CAP
    # Preserve a single CPU pin for the entire discovery job.
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    attempts=[]
    selected=[]
    seen_candidates=set()
    def try_one(g,year):
        check(g not in seen and g not in seen_candidates,
              "duplicate historical or new attempt")
        seen_candidates.add(g)
        note={"gbd":g,"year":year}
        source=root/(g+".cnf")
        try:
            if year==2026:
                note["official_status"]=scores[g]["status"]
                note["official_cadical_s"]=float(scores[g]["runtime"])
            raw,redirect=r32p.request_url(
                "https://benchmark-database.de/file/"+g,RAW_MAX,seconds=38)
            contents,comp=r32p.decode(raw)
            check(len(contents)<=CNF_MAX,"source exceeds 48MiB size bound")
            n,m=r32p.parse_dimacs_metadata(contents)
            source.write_bytes(contents)
            sh=digest(source)
            check(sh not in known_sha,"source SHA previously used")
            check(all(c["sha256"]!=sh for c in selected),
                  "source duplicates another selected formula")
            baseline=r68.short_pulse(binary,source,source,
                "SAT" if year==2025 else
                ("SAT" if scores[g]["status"]=="sat-verified" else "UNSAT"))
            note.update(
                sha256=sh,baseline_answer=baseline["answer"],
                baseline_wall_s=baseline["wall_s"],
                baseline_interrupted=baseline["interrupted"],
                bytes=len(contents),variables=n,clauses=m)
            if baseline["answer"]=="UNKNOWN":
                note["state"]="SCREEN_UNSOLVED_30S"
            elif (year==2025 and baseline["answer"]!="SAT"):
                # 2025 UNSAT lacks independently imported reference labels.
                note["state"]="SCREEN_2025_UNSAT_UNVALIDATED"
            elif baseline["wall_s"]<SCREEN_MIN or baseline["wall_s"]>SCREEN_CAP:
                note["state"]="SCREEN_NOT_5_TO_30S"
            else:
                status="SAT" if year==2025 else (
                    "SAT" if scores[g]["status"]=="sat-verified" else "UNSAT")
                scan=r63.inspect_exact_xor(source,n,m)
                case=dict(gbd=g,source_year=year,filename=source.name,
                    sha256=sh,variables=n,clauses=m,bytes=len(contents),
                    official_status=status,original_status_provenance=(
                       "2026 CaDiCaL official verified" if year==2026 else
                       "2025 SAT original witness verified by pinned Kissat"),
                    screen_kissat_wall_s=baseline["wall_s"],
                    screen_kissat_answer=baseline["answer"],
                    redirect=redirect,compression=comp,**scan)
                case["group"]=r64.group(case)
                case["r67_features"]=r67.passive_features(source,case)
                selected.append(case)
                note["state"]="SELECTED_READY"
                note["group"]=case["group"]
        except Exception as exc:
            # Do not convert a soundness/provenance failure to a skippable case.
            if isinstance(exc,RuntimeError) and (
                "source SHA previously used" in str(exc) or
                (year==2026 and "original official verdict contradiction" in str(exc))):
                raise
            note.update(state="FETCH_SIZE_PARSE_OR_VERIFY_ERROR",
                        error=(type(exc).__name__+": "+str(exc))[:250])
        if note.get("state")!="SELECTED_READY":
            source.unlink(missing_ok=True)
        attempts.append(note)
        print("R72_SOURCE_SCREEN",json.dumps(note,sort_keys=True),flush=True)
    for g in candidates26:
        if len(selected)==N:break
        try_one(g,2026)
    for g in candidates25[:MAX_2025_ATTEMPTS]:
        if len(selected)==N:break
        try_one(g,2025)
    manifest=dict(protocol=PROTO,target=N,ready=len(selected),
        source_selection_salt=SALT,registry=registry,
        source_catalog_sha=catsha,source_index26=r52.URI,
        source_index25=SC2025,
        source_exclusion_ids_sha256=hashlib.sha256(
            "\n".join(sorted(seen)).encode()).hexdigest(),
        prior_gbd_exclusion_count=len(seen),
        prior_sha_count=len(known_sha),screen_min_s=SCREEN_MIN,
        screen_max_s=SCREEN_CAP,bench_cap_s=BENCH_CAP,
        modes=list(MODES),repeats=REPS,shards=SHARDS,
        selection_conditioned_on_pinned_Kissat_baseline=True,
        not_blind_generalizable=True,results_not_official_competition=True,
        no_prior_accepted_or_attempted_gbd_reused=True,
        cases=selected,selection_attempts=attempts,
        limitations=[
            "Prior known registry is R63 history plus R63/R66/R67 attempted/accepted IDs; R68-R71 reused R67",
            "The 2025 supplement uses only SAT cases with Kissat witness verified on original CNF",
            "Kissat screening 5-30s itself uses each formula once and biases selection toward the baseline",
            "The final benchmark reuses those newly screened sources, but never sources used in earlier builds",
            "Historical ledger is limited to documented cohorts; external unrecorded project runs cannot be audited",
            "Time caps and hardware differ from official SAT Competition"
        ])
    (root/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    (root/"source.sha256").write_text("".join(
        c["sha256"]+"  "+c["filename"]+"\n" for c in selected))
    print("R72_FREEZE_SUMMARY",json.dumps({
        "target":N,"ready":len(selected),"attempted":len(attempts),
        "from2026":sum(c["source_year"]==2026 for c in selected),
        "from2025":sum(c["source_year"]==2025 for c in selected),
        "score_band":"5-30s pinned Kissat baseline",
        "prior_ids_excluded":len(seen)}),flush=True)
    check(len(selected)==N,"R72_COHORT_SHORTFALL: only "+
          str(len(selected))+" never-before-tried 5-30s solved sources")

def measure(args):
    root=Path(args.sources)
    manifest=json.loads((root/"manifest.json").read_text())
    check(manifest["protocol"]==PROTO and manifest["ready"]==N,
          "incomplete frozen R72 cohort")
    check(0<=args.shard<SHARDS,"invalid shard")
    check(len({c["sha256"] for c in manifest["cases"]})==N,
          "duplicate frozen SHA")
    binary=Path(args.kissat).resolve()
    check(binary.is_file() and digest(binary)==manifest["registry"]["binary_sha"],
          "pinned Kissat SHA mismatch")
    # The same R67 pinned binary is independently verified by binary.sha256
    # in GitHub Actions and the final audit checks every shard has same hash.
    case=manifest["cases"][args.shard]
    source=root/case["filename"]
    check(digest(source)==case["sha256"],"source SHA changed")
    r65.MAX_PREP_S=2.0
    src,cnf,all_clauses,filtered,stats=r71.prepare(root,case)
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    results=[]
    with tempfile.TemporaryDirectory(prefix="r72-new-") as temp:
        full=Path(temp)/"full.cnf"
        filt=Path(temp)/"filtered.cnf"
        if all_clauses:
            r64.augment(source,full,case["variables"],case["clauses"],all_clauses)
        else:
            full=source
        if filtered:
            r64.augment(source,filt,case["variables"],case["clauses"],filtered)
        else:
            filt=source
        modes={"original":source,"full_r65":full,"bcp_filtered":filt}
        r68.PULSE_SECONDS=BENCH_CAP
        for rep in range(REPS):
            order_modes=list(MODES)
            random.Random(int(hashlib.sha256((PROTO+case["sha256"]+
                       str(rep)).encode()).hexdigest(),16)).shuffle(order_modes)
            for mode in order_modes:
                pulse=r68.short_pulse(binary,modes[mode],source,
                                     case["official_status"])
                overhead=(0.0 if mode=="original" else stats["prep_s"] if
                          mode=="full_r65" else stats["end_to_end_overhead_s"])
                effective_wall=pulse["wall_s"]+overhead
                solved=pulse["answer"]!="UNKNOWN" and effective_wall<=BENCH_CAP
                row=dict(gbd=case["gbd"],year=case["source_year"],rep=rep,
                    mode=mode,answer=pulse["answer"],solved_within_total_cap=solved,
                    solver_wall_s=pulse["wall_s"],prep_and_filter_s=round(overhead,6),
                    end_to_end_wall_s=round(effective_wall,6),
                    par2_s=round(effective_wall if solved else 2*BENCH_CAP,6),
                    counters=pulse["early_counters"])
                results.append(row)
                print("R72_TRIAL",json.dumps({k:row[k] for k in
                    ("gbd","year","rep","mode","answer","solved_within_total_cap",
                     "solver_wall_s","prep_and_filter_s","par2_s")}),flush=True)
    check(len(results)==REPS*len(MODES),"missing matched measurements")
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    data=dict(protocol=PROTO,shard=args.shard,case=case,
              binary_sha=digest(binary),diagnostics=stats,
              rows=results)
    (out/"r72-shard.json").write_text(json.dumps(data,indent=2)+"\n")
    print("R72_SHARD_PASS",json.dumps({
        "shard":args.shard,"gbd":case["gbd"],
        "solved":sum(x["solved_within_total_cap"] for x in results),
        "times":{mode:[x["solver_wall_s"] for x in results if x["mode"]==mode]
                 for mode in MODES}}),flush=True)

def audit(args):
    root=Path(args.sources)
    mf=json.loads((root/"manifest.json").read_text())
    check(mf["protocol"]==PROTO and mf["ready"]==N and
          mf["no_prior_accepted_or_attempted_gbd_reused"],
          "frozen cohort provenance incomplete")
    cases=[];rows=[];binary_set=set()
    for i in range(N):
        path=Path(args.combined)/f"r72-shard-{i}"/"results"/"r72-shard.json"
        j=json.loads(path.read_text())
        check(j["protocol"]==PROTO and j["shard"]==i,
              "wrong run or shard")
        c=mf["cases"][i]
        check(j["case"]["gbd"]==c["gbd"] and
              j["case"]["sha256"]==c["sha256"],"frozen SHA drift")
        binary_set.add(j["binary_sha"])
        check(len(j["rows"])==len(MODES)*REPS,
              "incomplete repeated experiment")
        for rep in range(REPS):
            rr=[x for x in j["rows"] if x["rep"]==rep]
            check(len(rr)==len(MODES) and
                  {x["mode"] for x in rr}==set(MODES),"paired mode mismatch")
        for x in j["rows"]:
            check(x["answer"] in ("SAT","UNSAT","UNKNOWN") and
                  (x["answer"]=="UNKNOWN" or
                   x["answer"]==c["official_status"]), "invalid solver verdict")
            rows.append(x)
        cases.append(j)
    check(len(binary_set)==1 and len(rows)==N*REPS*len(MODES),
          "binary drift or missing trials")
    summary={}
    for mode in MODES:
        rr=[r for r in rows if r["mode"]==mode]
        summary[mode]=dict(trials=len(rr),
            solved=sum(r["solved_within_total_cap"] for r in rr),
            timeouts=sum(not r["solved_within_total_cap"] for r in rr),
            par2_total_s=round(sum(r["par2_s"] for r in rr),6),
            solved_total_wall_s=round(sum(r["end_to_end_wall_s"] for r in rr
                            if r["solved_within_total_cap"]),6))
    orig=summary["original"]["par2_total_s"]
    for mode in MODES[1:]:
        summary[mode]["gain_vs_kissat_pct"]=round(
            100*(orig-summary[mode]["par2_total_s"])/orig,5)
    report=dict(protocol=PROTO,status="PASS",n_sources=N,
        n_trials=len(rows),screen_5_to_30_s_verified=True,
        selection_biased_to_clean_kissat=True,
        registry=mf["registry"],source_catalog_sha=mf["source_catalog_sha"],
        summary=summary,cases=cases,
        limitations=mf["limitations"]+[
            "Preselection by Kissat means measured improvements may reflect regression to the mean.",
            "Two repeats and eight sources do not establish population performance",
            "UNSAT relies on official 2026 labels; 2025 selected cases only SAT with checked witness",
            "PAR2 penalizes every timeout at 2x 45 seconds"
        ])
    Path(args.json).write_text(json.dumps(report,indent=2)+"\n")
    text=["# R72: eight previously unused official 2026/2025 sources, benchmarked",
      "Every source was not present in the R63-R71 documented source/attempt registry.",
      "Kissat prescreen 5-30 seconds selected the examples; selection is NOT blind.",
      "",
      "| Source | Year | Kissat prescreen (s) | Kissat rep0/rep1 | R65 rep0/rep1 | Filter rep0/rep1 |",
      "|---|---:|---:|---|---|---|"]
    for c in cases:
        by_mode={m:sorted((r for r in c["rows"] if r["mode"]==m),
                           key=lambda r:r["rep"]) for m in MODES}
        def fmt(m):
            return " / ".join(
                (f"{r['end_to_end_wall_s']:.3f}s" if r["solved_within_total_cap"]
                 else "TIMEOUT") for r in by_mode[m])
        text.append(f"| {c['case']['gbd'][:12]} | {c['case']['source_year']} | "
                    f"{c['case']['screen_kissat_wall_s']:.3f} | "
                    f"{fmt('original')} | {fmt('full_r65')} | "
                    f"{fmt('bcp_filtered')} |")
    text+=["","| Mode | Solved / 16 | PAR2 total seconds |",
        "|---|---:|---:|"]
    for mode in MODES:
        s=summary[mode]
        text.append(f"| {mode} | {s['solved']}/{s['trials']} | "
                    f"{s['par2_total_s']:.3f} |")
    text+=["","## Limitations"]+["- "+v for v in report["limitations"]]
    Path(args.md).write_text("\n".join(text)+"\n")
    print("R72_FINAL_AUDIT_PASS",json.dumps({
        "sources":N,"trials":len(rows),"summary":summary,
        "years":dict(collections.Counter(c["case"]["source_year"] for c in cases)),
        "historical_excluded":mf["registry"]["total_excluded_ids"]}),flush=True)

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="cmd",required=True)
    f=sub.add_parser("freeze")
    for k in ("r63","r66","r67","r67final","kissat","out"):
        f.add_argument("--"+k,required=True)
    m=sub.add_parser("measure")
    for k in ("sources","kissat","out"):m.add_argument("--"+k,required=True)
    m.add_argument("--shard",type=int,required=True)
    a=sub.add_parser("audit")
    for k in ("sources","combined","json","md"):
        a.add_argument("--"+k,required=True)
    args=p.parse_args()
    if args.cmd=="freeze":freeze(args)
    elif args.cmd=="measure":measure(args)
    else:audit(args)

if __name__=="__main__":
    main()
