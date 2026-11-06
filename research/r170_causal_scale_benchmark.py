#!/usr/bin/env python3
"""R170: 405 precommitted paired R169 follow-up trials on ORIGINAL CNFs.
25 previously seen R155 original SHA CNFs * 5 arms * 3 repeats = 375.
2 R169 positive-reason original SHA CNFs * 5 arms * 3 repeats = 30.
20s broad cap, 120s causal focus cap; both TIMEOUTs get PAR2=2*cap.
Not blind. No independent UNSAT LRAT/FRAT. No world record assertions.
Same native executable, native CaDiCaL 2.1.0, deterministic shuffle, CPU pin.
First reason timestamps are observational only; a lower conflict count is
NOT a measure of conflicts "avoided" without counterfactual confirmation.
"""
import argparse, collections, hashlib, json, os, pathlib, random, subprocess, sys, time
sys.path.insert(0,str(pathlib.Path("research").resolve()))
import r165_component_benchmark as base

ROOT=pathlib.Path("r170")
base.ROOT=ROOT
base.FROZEN=ROOT/"frozen"
MODES=("clean","direct_full","direct_two_way","direct_two_way_newonly","direct_two_way_shadow")
REPS=3
SHARDS={"broad":4,"focus":2}
CAPS={"broad":20.0,"focus":120.0}
FOCUS_IDS={"3e912cd2a499b8f956246b866e2f9f64","99718c1729a8de3347a9946f1836421d"}
PROTO="DRNAS-R170-TIMED-CAUSAL-405-20261106-v1"
METRICS=("two_way_sweeps","two_way_row_xors","two_way_proposals","two_way_candidates",
 "two_way_multi_source_candidates","two_way_source_duplicate_units",
 "two_way_shadow_candidates","two_way_used_reasons","two_way_abstentions",
 "two_way_ns","direct_proposals","reason_clauses_completed","propagate_ns",
 "assignment_notify_ns","backtrack_notify_ns","first_proposal_ns","first_used_reason_ns")
def need(ok,why):
    if not ok:raise RuntimeError("R170_FAIL_CLOSED "+str(why))
def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def save(p,data):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
def all_cases():
    manifest=base.rd(base.FROZEN/"manifest.json")
    cases=sorted(manifest["cases"],key=lambda c:(c["cohort"],c["id"]))
    need(len(cases)==25 and len({c["sha256"] for c in cases})==25,"R155 original manifest must contain 25 distinct SHA sources")
    need({c["id"] for c in cases}.issuperset(FOCUS_IDS),"R169 positive-reason IDs not in original frozen manifest")
    for c in cases:
        need(sha(base.FROZEN/(c["id"]+".cnf"))==c["sha256"],"original source SHA drift "+c["id"])
    return cases
def cases_for(tier):
    cases=all_cases()
    if tier=="focus":cases=[c for c in cases if c["id"] in FOCUS_IDS]
    need(len(cases)==(2 if tier=="focus" else 25),"wrong cohort size")
    return cases
def trial(c,mode,rep,prep,binary,tier):
    source=base.FROZEN/(c["id"]+".cnf")
    tsv=ROOT/("full-"+c["id"]+".tsv")
    need(sha(source)==c["sha256"] and sha(tsv)==prep["full_tsv_sha"],"source or certificate changed")
    cap=CAPS[tier]
    charge=0.0 if mode=="clean" else prep["preprocessing_s"]
    need(charge+1.0<=cap,"preprocessing time exceeds cap")
    start=time.perf_counter()
    try:
        proc=subprocess.run([str(binary.resolve()),mode,str(source.resolve()),
           str(tsv.resolve()),str(cap-charge)],stdout=subprocess.PIPE,
           stderr=subprocess.PIPE,timeout=cap+15)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("R170_NATIVE_TERMINATOR_STALLED "+c["id"]) from exc
    wall=time.perf_counter()-start+charge
    need(proc.returncode in (0,10,20),
         "native crashed "+str(proc.returncode)+" "+proc.stderr[-900:].decode(errors="replace"))
    output,native,stats,source_rows,derived=base.parse_native(proc.stdout,mode)
    status={"SAT":"SAT","UNSAT":"UNSAT","UNKNOWN":"TIMEOUT"}[native["status"]]
    need(proc.returncode=={"SAT":10,"UNSAT":20,"TIMEOUT":0}[status],
         "native status/exit discrepancy")
    need(abs(float(native["solver_s"])-(wall-charge))<0.85,"native clock/wall disagreement")
    need(source_rows==(0 if mode=="clean" else prep["full_rows"]),"wrong certified source rows")
    if status=="SAT":
        need(native["source_sat_witness_checked"]=="1","native SAT witness not checked")
        base.sat_check(source,output)
    metrics={k:int(native[k]) for k in METRICS}
    need(metrics["two_way_used_reasons"]<=metrics["two_way_proposals"],"CDCL used reason without emitted GF2 unit")
    need(metrics["two_way_multi_source_candidates"]<=metrics["two_way_candidates"],"invalid Gaussian accounting")
    need(metrics["two_way_shadow_candidates"]<=metrics["two_way_candidates"],"invalid shadow accounting")
    need(metrics["reason_clauses_completed"]>=metrics["two_way_used_reasons"],"incomplete CDCL reason telemetry")
    need((metrics["first_used_reason_ns"]>=0)==(metrics["two_way_used_reasons"]>0),"first used-reason timestamp mismatch")
    need((metrics["first_proposal_ns"]>=0)==(metrics["two_way_proposals"]>0),"first Gaussian proposal timestamp mismatch")
    if mode=="direct_two_way_shadow":
        need(metrics["two_way_proposals"]==metrics["two_way_used_reasons"]==0,
             "shadow emitted or consumed derived Gaussian unit")
    else:
        need(metrics["two_way_shadow_candidates"]==0,"active mode suppressed Gaussian unit")
    if mode in ("clean","direct_full"):
        need(metrics["two_way_proposals"]==metrics["two_way_used_reasons"]==0,
             "Gaussian counts in non-Gaussian control")
    if c["cohort"]=="mixed_residual":
        need(stats.get("conflicts") is not None and stats.get("decisions") is not None,
             "missing native conflict/decision telemetry")
    return dict(protocol=PROTO,tier=tier,id=c["id"],sha256=c["sha256"],
       cohort=c["cohort"],family=c.get("family",""),mode=mode,repeat=rep,
       cap=cap,status=status,elapsed_s=round(wall,6),
       charged_preprocess_s=charge,par2_s=round(2*cap if status=="TIMEOUT"
            else min(cap,wall),6),source_rows=source_rows,derived_rows=derived,
       native_stats=stats,proof=("SOURCE_SAT_INDEPENDENT_CHECK" if status=="SAT"
            else "UNSAT_NO_INDEPENDENT_LRAT" if status=="UNSAT" else "TIMEOUT"),
       **metrics)
def shard(tier,index,binary):
    need(tier in SHARDS and 0<=index<SHARDS[tier],"bad shard selector")
    need(binary.is_file(),"missing native binary")
    pin=base.rd(ROOT/"build-pin.json")
    need(sha(binary)==pin["binary_sha256"],"native SHA mismatch")
    need(pin["source_commit"]==os.getenv("GITHUB_SHA",pin["source_commit"]),"unexpected source commit")
    if hasattr(os,"sched_getaffinity"):
        allowed=os.sched_getaffinity(0)
        if allowed:os.sched_setaffinity(0,{min(allowed)})
    selected=[c for i,c in enumerate(cases_for(tier)) if i%SHARDS[tier]==index]
    rows=[]
    for c in selected:
        prep=base.prepare(c)
        for rep in range(REPS):
            order=list(MODES)
            random.Random(PROTO+c["sha256"]+tier+str(rep)).shuffle(order)
            for mode in order:
                r=trial(c,mode,rep,prep,binary,tier)
                rows.append(r)
                save(ROOT/("shard-"+tier+"-"+str(index)+".json"),rows)
                print("R170_TRIAL",json.dumps({k:r[k] for k in
                    ("tier","id","repeat","mode","status","par2_s",
                     "two_way_proposals","two_way_used_reasons","first_used_reason_ns")},sort_keys=True),flush=True)
    need(len(rows)==len(selected)*REPS*len(MODES),"incomplete shard")
    print("R170_SHARD_PASS",tier,index,len(rows),flush=True)
def audit():
    allset=all_cases()
    cases={c["sha256"]:c for c in allset}
    rows=[]
    for tier,n in SHARDS.items():
        for i in range(n):
            p=ROOT/("shard-"+tier+"-"+str(i)+".json")
            need(p.is_file(),"missing "+str(p))
            data=base.rd(p)
            expected=len([c for j,c in enumerate(cases_for(tier)) if j%n==i])*REPS*len(MODES)
            need(len(data)==expected,"incomplete "+str(p))
            rows+=data
    need(len(rows)==405,"R170 expected exactly 405 trials")
    keys={(r["tier"],r["sha256"],r["repeat"],r["mode"]) for r in rows}
    need(len(keys)==len(rows),"duplicate paired trial")
    proof_sha={}
    for c in allset:
        evidence=base.rd(ROOT/("cert-"+c["id"]+".json"))
        base.independent_cert(c,evidence)
        proof_sha[c["id"]]=sha(ROOT/("cert-"+c["id"]+".json"))
    for tier in SHARDS:
        for c in cases_for(tier):
            subset=[r for r in rows if r["tier"]==tier and r["sha256"]==c["sha256"]]
            need(len(subset)==REPS*len(MODES),"missing paired mode trial")
            solved={r["status"] for r in subset if r["status"]!="TIMEOUT"}
            need(len(solved)<=1,"contradictory SAT/UNSAT outcomes")
    for r in rows:
        need(r["protocol"]==PROTO and r["sha256"] in cases,
             "provenance mismatch")
        need(r["status"]=="TIMEOUT" and abs(r["par2_s"]-2*r["cap"])<1e-4
            or r["status"]!="TIMEOUT" and abs(r["par2_s"]-min(r["cap"],r["elapsed_s"]))<1e-4,
            "invalid PAR2 accounting")
        if r["status"]=="SAT":need(r["proof"]=="SOURCE_SAT_INDEPENDENT_CHECK","unverified SAT")
    summary={}
    paired={}
    for tier in SHARDS:
        vals=[r for r in rows if r["tier"]==tier]
        summary[tier]={}
        for mode in MODES:
            arr=[r for r in vals if r["mode"]==mode]
            summary[tier][mode]=dict(trials=len(arr),solved=sum(r["status"]!="TIMEOUT" for r in arr),
                SAT=sum(r["status"]=="SAT" for r in arr),UNSAT=sum(r["status"]=="UNSAT" for r in arr),
                PAR2_s=round(sum(r["par2_s"] for r in arr),6),
                total_wall_s=round(sum(r["elapsed_s"] for r in arr),6),
                actual_used_GF2_reasons=sum(r["two_way_used_reasons"] for r in arr),
                emitted_derived_GF2_units=sum(r["two_way_proposals"] for r in arr),
                cdcl_conflicts=sum(r["native_stats"].get("conflicts") or 0 for r in arr),
                candidates=sum(r["two_way_multi_source_candidates"] for r in arr),
                first_used_observed_runs=sum(r["first_used_reason_ns"]>=0 for r in arr))
        paired[tier]=[]
        for c in cases_for(tier):
            for rep in range(REPS):
                bymode={r["mode"]:r for r in vals if r["sha256"]==c["sha256"] and r["repeat"]==rep}
                need(set(bymode)==set(MODES),"incomplete paired per-formula arms")
                b=bymode["clean"];n=bymode["direct_two_way_newonly"];s=bymode["direct_two_way_shadow"]
                paired[tier].append(dict(id=c["id"],cohort=c["cohort"],repeat=rep,
                    clean_status=b["status"],novel_status=n["status"],shadow_status=s["status"],
                    clean_par2_s=b["par2_s"],novel_par2_s=n["par2_s"],shadow_par2_s=s["par2_s"],
                    used_reasons=n["two_way_used_reasons"],
                    first_used_reason_s=(round(n["first_used_reason_ns"]/1e9,6)
                        if n["first_used_reason_ns"]>=0 else None),
                    clean_conflicts=b["native_stats"].get("conflicts"),
                    novel_conflicts=n["native_stats"].get("conflicts"),
                    shadow_conflicts=s["native_stats"].get("conflicts"),
                    solved_speed_ratio_clean_over_novel=(round(b["elapsed_s"]/n["elapsed_s"],5)
                         if b["status"]!="TIMEOUT" and n["status"]!="TIMEOUT" and n["elapsed_s"]>0
                         else None)))
    result=dict(status="R170_RESEARCH_AUDIT_PASS_NOT_BLIND",protocol=PROTO,
        source_run=42112755104,r169_run=42153494705,
        original_formulas=25,positive_reason_formulas=2,attempts=405,
        native_binary_pin=base.rd(ROOT/"build-pin.json"),
        cap_s=CAPS,mode_names=MODES,repeats=REPS,
        source_SHA_independently_verified=True,source_XOR_certificates_replayed=True,
        SAT_models_independently_checked=True,UNSAT_independent_LRAT=False,
        proof_cert_sha=proof_sha,results=summary,paired=paired,records=rows,
        caveats=["All 25 original SHA CNFs previously used in development: NOT a blind holdout.",
        "Focus formulas were deliberately selected because R169 showed consumed GF2 reasons.",
        "Equal-capped TIMEOUTs do not permit wall-time speedup assertions.",
        "Total CDCL conflicts at equal wall-time are descriptive, not conflicts demonstrably avoided.",
        "Shadow suppresses derived Gaussian units only; original source GF2 remains active.",
        "No independent LRAT or FRAT UNSAT proof; no competition or world-ranking claim.",
        "No external Kissat benchmarking in this run."])
    save(ROOT/"report.json",result)
    with (ROOT/"summary.md").open("w") as f:
        f.write("# DRNAS R170 — 405 paired timed causal GF2 trials\n\n")
        f.write("**Research-only, not blind:** 25 R155 original CNFs + 2 selected positive-reason reruns.\n\n")
        for tier in SHARDS:
            f.write("## "+tier+" (cap "+str(CAPS[tier])+" s)\n\n")
            f.write("| Mode | Solved | PAR2 s | Emitted derived | CDCL used | First reason runs |\n")
            f.write("|---|---:|---:|---:|---:|---:|\n")
            for mode in MODES:
                d=summary[tier][mode]
                f.write(f'| {mode} | {d["solved"]}/{d["trials"]} | {d["PAR2_s"]:.3f} | {d["emitted_derived_GF2_units"]} | {d["actual_used_GF2_reasons"]} | {d["first_used_observed_runs"]} |\n')
            f.write("\n")
        f.write("No claim of improvement from mere proposal/reason counts or unresolved PAR2 ties.\n")
    print("R170_FINAL",json.dumps({k:result[k] for k in ("status","attempts","original_formulas","positive_reason_formulas","results")},sort_keys=True),flush=True)
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("shard","audit"))
    parser.add_argument("--tier",choices=list(SHARDS),default="broad")
    parser.add_argument("--shard",type=int,default=0)
    parser.add_argument("--binary",default="r170/r170-native")
    args=parser.parse_args()
    shard(args.tier,args.shard,pathlib.Path(args.binary)) if args.action=="shard" else audit()
