#!/usr/bin/env python3
"""R177 research only: frozen original SHA-matched residual-mixed SAT instances.
4 arm paired causality: R174-B, R176 triple, R177 one/two-hop CNF resolution. NOT BLIND or a world ranking.
"""
import argparse,hashlib,json,os,pathlib,random,time,subprocess
import r175_clause_causality_benchmark as prior

ROOT=pathlib.Path("r177")
prior.ROOT=ROOT
prior.base174.ROOT=ROOT
prior.base174.base.ROOT=ROOT
prior.base174.base.FROZEN=ROOT/"frozen"
base174=prior.base174
need=prior.need
sha=prior.sha
save=prior.save
rd=prior.rd
MODES=("r174_b","r177_prev_triple","r177_onehop","r177_twohop")
NATIVE={"r174_b":"gauss_feedback",
        "r177_prev_triple":"gauss_bridge_triple",
        "r177_onehop":"gauss_resolve1",
        "r177_twohop":"gauss_resolve2"}
REPS=2
SHARDS=4
CAP=45.0
PROTO="DRNAS-R177-CERTIFIED-XOR-CNF-ONE-TWO-HOP-v1"

def selected():
    cases=[c for c in base174.cases() if c["cohort"]=="mixed_residual"]
    need(len(cases)==4,"expected exactly 4 frozen original residual-mixed cases")
    need(len({c["sha256"] for c in cases})==4,"non-unique original sources")
    return cases

def capped_native(case, mode, cap, binary, prep, overhead):
    src=base174.base.FROZEN/(case["id"]+".cnf")
    root=ROOT/("gauss-"+case["id"])
    rows=root/"gauss.tsv"
    units=root/"gauss-units.tsv"
    need(sha(rows)==prep["gauss_rows_sha"],"certified rows hash mismatch")
    need(sha(units)==prep["gauss_units_sha"],"certified units hash mismatch")
    charge=float(prep["gauss_preprocessing_s"])
    available=cap-charge-overhead
    if available<1.0:
        return dict(status="TIMEOUT",elapsed=round(charge+overhead,6),
          native_mode="budget_exhausted",native_s=0,source_rows=0,
          gauss_units=0,conflicts=None,decisions=None,
          native_reason_clauses=0,preprocess_s=round(charge,6))
    argv=[str(binary.resolve()),mode,str(src.resolve()),str(rows.resolve()),
          str(available),str(units.resolve())]
    begin=time.perf_counter()
    try:
        proc=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                            timeout=available+12)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("R177_NATIVE_STUCK "+case["id"]) from exc
    wall=time.perf_counter()-begin
    need(proc.returncode in (0,10,20),
        "native error "+proc.stderr[-1200:].decode(errors="replace"))
    txt,native,stats,nrows,_=base174.base.parse_native(proc.stdout,mode)
    status={"SAT":"SAT","UNSAT":"UNSAT","UNKNOWN":"TIMEOUT"}[native["status"]]
    need(proc.returncode=={"SAT":10,"UNSAT":20,"TIMEOUT":0}[status],
         "native exit/status disagreement")
    need(nrows==prep["gauss_source_rows"],"certified row mismatch")
    need(int(native["gauss_units"])==prep["gauss_units"],"certified unit mismatch")
    need(abs(float(native["solver_s"])-wall)<0.9,"native clock mismatch")
    if status=="SAT":
        need(native.get("source_sat_witness_checked")=="1","SAT witness missing")
        base174.base.sat_check(src,txt)
    if case["cohort"]=="mixed_residual":
        need(stats.get("conflicts") is not None and stats.get("decisions") is not None,
             "missing native CDCL conflict/decision counters")
    return dict(status=status,elapsed=round(wall+charge+overhead,6),
      native_mode=mode,native_s=round(wall,6),source_rows=nrows,
      gauss_units=int(native["gauss_units"]),conflicts=stats.get("conflicts"),
      decisions=stats.get("decisions"),
      learned=stats.get("learned"),propagations=stats.get("propagations"),
      native_reason_clauses=int(native["reason_clauses_completed"]),
      preprocess_s=round(charge,6),
      feedback_conflicts=int(native.get("feedback_conflicts_detected",0)),
      feedback_consumed=int(native.get("feedback_clauses_consumed",0)),
      feedback_candidates=int(native.get("feedback_candidates",0)),
      feedback_candidates_width4=int(native.get("feedback_candidates_width4",0)),
      feedback_duplicates=int(native.get("feedback_duplicates",0)),
      feedback_rejected_width=int(native.get("feedback_rejected_width",0)),
      feedback_rejected_budget=int(native.get("feedback_rejected_budget",0)),
      feedback_shadow_admitted=int(native.get("feedback_shadow_admitted",0)),
      feedback_delivered_width4=int(native.get("feedback_delivered_width4",0)),
      feedback_sum_width_delivered=int(native.get("feedback_sum_width_delivered",0)),
      r177_onehop=int(native.get("r177_onehop",0)),
      r177_twohop=int(native.get("r177_twohop",0)),
      r177_proof_checks=int(native.get("r177_proof_checks",0)),
      r177_candidate_examined=int(native.get("r177_candidate_examined",0)),
      conflicts_per_second=round(stats["conflicts"]/wall,3) if stats.get("conflicts") is not None and wall>0 else None,
      utility_windows=int(native.get("utility_windows",0)),
      utility_sleeps=int(native.get("utility_sleeps",0)),
      utility_wakes=int(native.get("utility_wakes",0)))

def trial(case,mode,rep,prep,binary):
    src=base174.base.FROZEN/(case["id"]+".cnf")
    need(sha(src)==case["sha256"],"source SHA mismatch")
    start=time.perf_counter()
    exact=base174.exact.solve(src)
    router_s=time.perf_counter()-start
    need(exact["source_sha256"]==case["sha256"],"router SHA drift")
    need(exact["status"]=="NOT_PURE" and not exact["pure_exact"],
         "expected residual mixed not pure XOR")
    eligible=(prep["full_rows"]>=8 and prep["boundary_rows"]>=4
              and prep["diverse_boundary_vars"]>=12
              and prep["preprocessing_s"]<=min(1.5,0.07*CAP))
    need(eligible,"mixed source not eligible for certified GF2 comparison")
    result=capped_native(case,NATIVE[mode],CAP,binary,prep,router_s)
    need(result["status"] in ("SAT","UNSAT","TIMEOUT"),"bad native status")
    if result["status"]!="TIMEOUT" and result["elapsed"]>CAP:
        result["status"]="TIMEOUT"
    if mode in ("r177_onehop","r177_twohop"):
        need(result["r177_proof_checks"]==result["r177_onehop"]+result["r177_twohop"],
             "R177 missing native resolution proof trace")
        if mode=="r177_onehop":
            need(result["r177_twohop"]==0,"R177 onehop leaked twohop clause")
    result.update(id=case["id"],sha256=case["sha256"],
      cohort=case["cohort"],mode=mode,repeat=rep,
      cap=CAP,original_source_sha_verified=True,
      route=mode+"_residual_gauss",
      proof="ORIGINAL_SAT_CHECKED" if result["status"]=="SAT"
          else "NATIVE_UNSAT_NO_INDEPENDENT_LRAT" if result["status"]=="UNSAT"
          else "TIMEOUT")
    result["par2"]=round(2*CAP if result["status"]=="TIMEOUT"
                         else min(CAP,result["elapsed"]),6)
    return result

def shard(index,binary):
    need(0<=index<SHARDS,"bad shard")
    pin=rd(ROOT/"build-pin.json")
    need(binary.is_file() and sha(binary)==pin["binary_sha256"],
         "native binary not pinned")
    need(pin["source_commit"]==os.environ.get("GITHUB_SHA",pin["source_commit"]),
         "source commit drift")
    if hasattr(os,"sched_getaffinity"):
        available=os.sched_getaffinity(0)
        if available:os.sched_setaffinity(0,{min(available)})
    (ROOT/"empty-rows.tsv").write_text("")
    cases=selected()
    rows=[]
    for i,case in enumerate(cases):
        if i!=index:continue
        prep=base174.base.prepare(case)
        for rep in range(REPS):
            arms=list(MODES)
            random.Random(PROTO+case["sha256"]+str(rep)).shuffle(arms)
            for mode in arms:
                x=trial(case,mode,rep,prep,binary)
                rows.append(x)
                save(ROOT/f"shard-{index}.json",rows)
                print("R177_TRIAL",json.dumps({k:x.get(k) for k in
                    ("id","cohort","repeat","mode","status","elapsed","par2",
                     "conflicts","decisions","native_reason_clauses",
                     "feedback_candidates","feedback_consumed","source_rows",
                     "preprocess_s","r177_onehop","r177_twohop",
                     "r177_proof_checks","r177_candidate_examined")},sort_keys=True),flush=True)
    need(len(rows)==REPS*len(MODES),"shard size mismatch")
    print("R177_SHARD_PASS",index,len(rows),flush=True)

def audit():
    cases=selected()
    rows=[];seen=set()
    for idx in range(SHARDS):
        group=rd(ROOT/f"shard-{idx}.json")
        need(len(group)==REPS*len(MODES),"missing shard")
        for x in group:
            key=(x["sha256"],x["repeat"],x["mode"])
            need(key not in seen,"duplicate paired trial")
            seen.add(key);rows.append(x)
    need(len(rows)==len(cases)*REPS*len(MODES)==32,"missing paired data")
    from r166x_certified_gauss import replay
    for c in cases:
        src=base174.base.FROZEN/(c["id"]+".cnf")
        need(sha(src)==c["sha256"],"source SHA mismatch at audit")
        prep=rd(ROOT/("prep-"+c["id"]+".json"))
        cert=rd(ROOT/("cert-"+c["id"]+".json"))
        base174.base.independent_cert(c,cert)
        g=ROOT/("gauss-"+c["id"])
        need(sha(g/"gauss-cert.json")==prep["gauss_certificate_sha"],
             "Gaussian independent cert SHA mismatch")
        need(replay(src,cert,g/"gauss-cert.json",
                    g/"gauss.tsv",g/"gauss-units.tsv"),
             "Gaussian independent proof replay failure")
        trials=[x for x in rows if x["id"]==c["id"]]
        need(len(trials)==REPS*len(MODES),"unpaired formula")
        for rep in range(REPS):
            group=[x for x in trials if x["repeat"]==rep]
            need(set(x["mode"] for x in group)==set(MODES),
                 "one of the paired modes missing")
            answers={x["status"] for x in group if x["status"]!="TIMEOUT"}
            need(len(answers)<=1,"SAT/UNSAT discrepancy between modes")
            for x in group:
                need(x["sha256"]==c["sha256"] and x["original_source_sha_verified"],
                     "paired source SHA drift")
                need(x["proof"]=="ORIGINAL_SAT_CHECKED" if x["status"]=="SAT"
                     else True,"SAT witness not verified")
                need(abs(x["par2"]-(2*CAP if x["status"]=="TIMEOUT"
                                   else min(CAP,x["elapsed"])))<1e-4,
                     "PAR2 inconsistency")
                need(x["conflicts"] is not None and x["decisions"] is not None,
                     "missing native CDCL telemetry")
    summary={}
    for mode in MODES:
        grp=[x for x in rows if x["mode"]==mode]
        summary[mode]={"attempts":len(grp),
          "solved":sum(x["status"]!="TIMEOUT" for x in grp),
          "par2_s":round(sum(x["par2"] for x in grp),6),
          "conflicts":sum(x["conflicts"] for x in grp),
          "decisions":sum(x["decisions"] for x in grp),
          "feedback_consumed":sum(x["feedback_consumed"] for x in grp),
          "source_rows":sum(x["source_rows"] for x in grp),
          "r177_onehop":sum(x["r177_onehop"] for x in grp),
          "r177_twohop":sum(x["r177_twohop"] for x in grp),
          "r177_proof_checks":sum(x["r177_proof_checks"] for x in grp)}
    paired=[]
    for c in cases:
        for rep in range(REPS):
            arm={x["mode"]:x for x in rows if x["id"]==c["id"] and x["repeat"]==rep}
            for mode in MODES[1:]:
                base,new=arm["r174_b"],arm[mode]
                paired.append({"id":c["id"],"repeat":rep,"mode":mode,
                  "baseline_status":base["status"],"new_status":new["status"],
                  "delta_par2_s":round(base["par2"]-new["par2"],6),
                  "delta_conflicts":base["conflicts"]-new["conflicts"],
                  "delta_decisions":base["decisions"]-new["decisions"]})
    report={"status":"R177_FROZEN_PAIRED_SOURCE_PROOF_PASS_NOT_BLIND",
      "protocol":PROTO,"formulas":len(cases),"attempts":len(rows),
      "not_blind":True,"independent_source_gaussian_proof":True,
      "native_derived_rows_checked_with_explicit_source_traces":True,
      "xor_cnf_resolution_traces_checked":True,
      "SAT_originals_checked":True,"independent_UNSAT_LRAT":False,
      "summary":summary,"paired":paired,"records":rows,
      "caveats":["Development original residual-mixed cases, NOT BLIND",
      "Shortened 45s cap vs R175 90s; compare ONLY arms in this run",
      "Timeout conflict counts at equal caps measure throughput, not speedup",
      "C++ internally replays every derived row XOR source trace; Gaussian source replayed independently",
      "New unit/UNSAT not independent LRAT certified"]}
    save(ROOT/"report.json",report)
    with (ROOT/"summary.md").open("w") as f:
        f.write("# R177 frozen original residual mixed XOR-CNF\n\n")
        f.write("4 original SHA-matched residual-mixed CNFs, 2 repeats, 4 arms, 45s cap. NOT BLIND.\n\n")
        f.write("| Mode | Solved | PAR2 s | Conflicts | Decisions | CNF resolvents |\n|---|---:|---:|---:|---:|---:|\n")
        for mode,x in summary.items():
            f.write(f'| {mode} | {x["solved"]}/{x["attempts"]} | {x["par2_s"]} | {x["conflicts"]} | {x["decisions"]} | {x["r177_onehop"]+x["r177_twohop"]} |\n')
        f.write("\nZero solves is not a speedup regardless of conflict throughput. No LRAT for UNSAT.\n")
    print("R177_FINAL",json.dumps({"summary":summary,"formulas":len(cases),
                                  "attempts":len(rows)},sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="r177/r177-native")
    args=p.parse_args()
    shard(args.shard,pathlib.Path(args.binary)) if args.action=="shard" else audit()
