#!/usr/bin/env python3
"""R175 causal source-certified XOR conflict clauses: R173, R174-B, shadow,
short4 and budget8, 25 original CNFs x2 repeats x5 arms. Known development
cases, NOT BLIND. Native conflicts and decisions are measured, not inferred.
At equal time caps, fewer conflicts can also indicate slower propagation.
"""
import argparse,hashlib,json,os,pathlib,random,subprocess,time
import r173_residual_gate_benchmark as base174

ROOT=pathlib.Path("r175")
base174.ROOT=ROOT
base174.base.ROOT=ROOT
base174.base.FROZEN=ROOT/"frozen"
MODES=("r173_selective","r174_b","r175_shadow","r175_short4","r175_budget8")
NATIVE={"r174_b":"gauss_feedback","r175_shadow":"gauss_shadow",
        "r175_short4":"gauss_short4","r175_budget8":"gauss_budget8"}
REPS=2
SHARDS=5
PROTO="DRNAS-R175-CERTIFIED-CONFLICT-CAUSAL-v1"
need=base174.need
sha=base174.sha
save=base174.save
rd=base174.rd

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
        raise RuntimeError("R175_NATIVE_STUCK "+case["id"]) from exc
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
      conflicts_per_second=round(stats["conflicts"]/wall,3) if stats.get("conflicts") is not None and wall>0 else None,
      utility_windows=int(native.get("utility_windows",0)),
      utility_sleeps=int(native.get("utility_sleeps",0)),
      utility_wakes=int(native.get("utility_wakes",0)))

def trial(case,mode,rep,prep,binary):
    if mode in ("clean","r173_selective"):
        return base174.trial(case,mode,rep,prep,binary)
    cap=90.0 if case["cohort"]=="mixed_residual" else 7.0
    src=base174.base.FROZEN/(case["id"]+".cnf")
    start=time.perf_counter()
    exact=base174.exact.solve(src)
    router_s=time.perf_counter()-start
    need(exact["source_sha256"]==case["sha256"],"source SHA changed")
    if exact["pure_exact"]:
        need(exact["status"] in ("SAT","UNSAT"),"exact route unresolved")
        result=dict(status=exact["status"],elapsed=round(router_s,6),
          native_mode="none_exact",native_s=0,source_rows=exact["xor_rows"],
          gauss_units=0,conflicts=None,decisions=None,native_reason_clauses=0,
          preprocess_s=0.0)
        route="exact_pure_xor"
    else:
        need(exact["status"]=="NOT_PURE","unsafe router acceptance")
        eligible=(prep["full_rows"]>=8 and prep["boundary_rows"]>=4
            and prep["diverse_boundary_vars"]>=12
            and prep["preprocessing_s"]<=min(1.5,0.07*cap))
        route=(mode+"_residual_gauss" if eligible else mode+"_clean_fallback")
        if eligible:
            result=capped_native(case,NATIVE[mode],cap,binary,prep,router_s)
        else:
            result=base174.capped_native(case,"clean",cap,binary,prep,
                                         router_s+prep["preprocessing_s"])
        result["gate_eligible"]=eligible
        result["gate_full_rows"]=prep["full_rows"]
    result.update(id=case["id"],sha256=case["sha256"],cohort=case["cohort"],
      family=case.get("family",""),mode=mode,repeat=rep,cap=cap,route=route,
      router_check_s=round(router_s,6),pure_exact=exact["pure_exact"],
      original_source_sha_verified=True,
      proof="ORIGINAL_SAT_CHECKED" if result["status"]=="SAT"
         else "EXACT_GF2_CONTRADICTION_REPLAYED_NO_LRAT"
         if route=="exact_pure_xor" and result["status"]=="UNSAT"
         else "NATIVE_UNSAT_NO_INDEPENDENT_LRAT" if result["status"]=="UNSAT"
         else "TIMEOUT")
    result["par2"]=round(2*cap if result["status"]=="TIMEOUT"
                   else min(cap,result["elapsed"]),6)
    return result

def shard(index,binary):
    need(0<=index<SHARDS,"bad shard")
    need(binary.is_file(),"no native executable")
    pin=rd(ROOT/"build-pin.json")
    need(sha(binary)==pin["binary_sha256"],"native SHA mismatch")
    need(pin["source_commit"]==os.environ.get("GITHUB_SHA",pin["source_commit"]),
         "source SHA drift")
    if hasattr(os,"sched_getaffinity"):
        available=os.sched_getaffinity(0)
        if available:os.sched_setaffinity(0,{min(available)})
    cases=base174.cases()
    (ROOT/"empty-rows.tsv").write_text("")
    rows=[]
    for i,case in enumerate(cases):
        if i%SHARDS!=index:continue
        prep=base174.base.prepare(case)
        for rep in range(REPS):
            order=list(MODES)
            random.Random(PROTO+case["sha256"]+str(rep)).shuffle(order)
            for mode in order:
                row=trial(case,mode,rep,prep,binary)
                rows.append(row)
                save(ROOT/f"shard-{index}.json",rows)
                print("R175_TRIAL",json.dumps({k:row.get(k) for k in
                    ("id","cohort","mode","repeat","status","route","elapsed",
                     "par2","conflicts","decisions","native_reason_clauses",
                      "feedback_candidates","feedback_consumed",
                      "feedback_shadow_admitted","feedback_rejected_width",
                      "feedback_rejected_budget")},sort_keys=True),flush=True)
    need(len(rows)==5*REPS*len(MODES),"incomplete shard")
    print("R175_SHARD_PASS",index,len(rows),flush=True)

def audit():
    cases=base174.cases()
    rows=[];seen=set()
    for idx in range(SHARDS):
        data=rd(ROOT/f"shard-{idx}.json")
        need(len(data)==5*REPS*len(MODES),"missing shard")
        for x in data:
            k=(x["sha256"],x["repeat"],x["mode"])
            need(k not in seen,"duplicate trial")
            seen.add(k);rows.append(x)
    need(len(rows)==25*REPS*len(MODES)==250,"incomplete 250 trials")
    from r166x_certified_gauss import replay
    for c in cases:
        source=base174.base.FROZEN/(c["id"]+".cnf")
        need(sha(source)==c["sha256"],"source checksum drift")
        prep=rd(ROOT/("prep-"+c["id"]+".json"))
        cert=rd(ROOT/("cert-"+c["id"]+".json"))
        base174.base.independent_cert(c,cert)
        gaussdir=ROOT/("gauss-"+c["id"])
        need(sha(gaussdir/"gauss-cert.json")==prep["gauss_certificate_sha"],
             "Gaussian proof SHA drift")
        need(replay(source,cert,gaussdir/"gauss-cert.json",
                    gaussdir/"gauss.tsv",gaussdir/"gauss-units.tsv"),
             "Gaussian replay failed")
        group=[z for z in rows if z["id"]==c["id"]]
        need(len(group)==REPS*len(MODES),"missing paired case")
        need(len({z["status"] for z in group if z["status"]!="TIMEOUT"})<=1,
             "contradictory SAT/UNSAT")
        for rep in range(REPS):
            arms={z["mode"]:z for z in group if z["repeat"]==rep}
            need(set(arms)==set(MODES),"missing paired arm")
            for z in arms.values():
                need(z["sha256"]==c["sha256"],"paired source mismatch")
                need(abs(z["par2"]-(2*z["cap"] if z["status"]=="TIMEOUT"
                     else min(z["cap"],z["elapsed"])))<1e-4,"bad PAR2")
                need(z["status"]!="SAT" or z["proof"]=="ORIGINAL_SAT_CHECKED",
                     "SAT source witness missing")
    summary={}
    by_cohort={}
    for mode in MODES:
        group=[z for z in rows if z["mode"]==mode]
        summary[mode]={"attempts":len(group),
            "solved":sum(z["status"]!="TIMEOUT" for z in group),
            "PAR2_s":round(sum(z["par2"] for z in group),5),
            "feedback_consumed":sum(z.get("feedback_consumed",0) for z in group),
            "utility_sleeps":sum(z.get("utility_sleeps",0) for z in group)}
        by_cohort[mode]={co:{"solved":sum(z["status"]!="TIMEOUT"
            for z in group if z["cohort"]==co),
            "PAR2_s":round(sum(z["par2"] for z in group if z["cohort"]==co),5)}
            for co in sorted({z["cohort"] for z in group})}
    paired=[]
    for c in cases:
        for rep in range(REPS):
            a={z["mode"]:z for z in rows if z["id"]==c["id"] and z["repeat"]==rep}
            for mode in MODES[1:]:
                old=a["r173_selective"];new=a[mode]
                both=old["status"]!="TIMEOUT" and new["status"]!="TIMEOUT"
                paired.append({"id":c["id"],"cohort":c["cohort"],"repeat":rep,
                    "variant":mode,"delta_PAR2_s":round(old["par2"]-new["par2"],6),
                    "both_solved":both,
                    "speedup_if_both_solved":round(old["elapsed"]/new["elapsed"],5)
                    if both and new["elapsed"]>0 else None})
    report={"status":"R175_PAIRED_CAUSAL_AUDIT_PASS_NOT_BLIND","protocol":PROTO,
      "formulas":25,"attempts":len(rows),"known_development_sources":True,
      "independent_source_certificates":True,"SAT_originals_checked":True,
      "independent_UNSAT_LRAT":False,"summary":summary,
      "by_cohort":by_cohort,"paired":paired,"records":rows}
    save(ROOT/"report.json",report)
    with (ROOT/"summary.md").open("w") as f:
        f.write("# R174 B/C feedback and utility — development paired originals\n\n")
        f.write("| Arm | Solved | PAR2 s | Consumed conflict clauses | Utility sleeps |\n")
        f.write("|---|---:|---:|---:|---:|\n")
        for k,v in summary.items():
            f.write(f'| {k} | {v["solved"]}/{v["attempts"]} | {v["PAR2_s"]} | {v["feedback_consumed"]} | {v["utility_sleeps"]} |\n')
        f.write("\nKnown original CNFs, NOT BLIND. UNSAT lacks independent LRAT.\n")
    print("R175_FINAL",json.dumps({"summary":summary,"by_cohort":by_cohort},
                                  sort_keys=True),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("shard","audit"))
    parser.add_argument("--shard",type=int,default=0)
    parser.add_argument("--binary",default="r175/r175-native")
    args=parser.parse_args()
    shard(args.shard,pathlib.Path(args.binary)) if args.action=="shard" else audit()
