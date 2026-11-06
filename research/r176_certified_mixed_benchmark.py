#!/usr/bin/env python3
"""R176 research only: frozen original SHA-matched residual-mixed SAT instances.
3 arm paired causality: R174-B feedback / certified GF2 pair / certified GF2
triple closure with short-CNF variable ranking. NOT BLIND or a world ranking.
"""
import argparse,hashlib,json,os,pathlib,random,time
import r175_clause_causality_benchmark as prior

ROOT=pathlib.Path("r176")
prior.ROOT=ROOT
prior.base174.ROOT=ROOT
prior.base174.base.ROOT=ROOT
prior.base174.base.FROZEN=ROOT/"frozen"
base174=prior.base174
need=prior.need
sha=prior.sha
save=prior.save
rd=prior.rd
MODES=("r174_b","r176_pair","r176_triple")
NATIVE={"r174_b":"gauss_feedback",
        "r176_pair":"gauss_bridge_pair",
        "r176_triple":"gauss_bridge_triple"}
REPS=2
SHARDS=4
CAP=45.0
PROTO="DRNAS-R176-RESIDUAL-CNF-GF2-PAIR-TRIPLE-v1"

def selected():
    cases=[c for c in base174.cases() if c["cohort"]=="mixed_residual"]
    need(len(cases)==4,"expected exactly 4 frozen original residual-mixed cases")
    need(len({c["sha256"] for c in cases})==4,"non-unique original sources")
    return cases

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
    result=prior.capped_native(case,NATIVE[mode],CAP,binary,prep,router_s)
    need(result["status"] in ("SAT","UNSAT","TIMEOUT"),"bad native status")
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
                print("R176_TRIAL",json.dumps({k:x.get(k) for k in
                    ("id","cohort","repeat","mode","status","elapsed","par2",
                     "conflicts","decisions","native_reason_clauses",
                     "feedback_candidates","feedback_consumed","source_rows",
                     "preprocess_s")},sort_keys=True),flush=True)
    need(len(rows)==REPS*len(MODES),"shard size mismatch")
    print("R176_SHARD_PASS",index,len(rows),flush=True)

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
    need(len(rows)==len(cases)*REPS*len(MODES)==24,"missing paired data")
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
          "source_rows":sum(x["source_rows"] for x in grp)}
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
    report={"status":"R176_FROZEN_PAIRED_SOURCE_PROOF_PASS_NOT_BLIND",
      "protocol":PROTO,"formulas":len(cases),"attempts":len(rows),
      "not_blind":True,"independent_source_gaussian_proof":True,
      "native_derived_rows_checked_with_explicit_source_traces":True,
      "SAT_originals_checked":True,"independent_UNSAT_LRAT":False,
      "summary":summary,"paired":paired,"records":rows,
      "caveats":["Development original residual-mixed cases, NOT BLIND",
      "Shortened 45s cap vs R175 90s; compare ONLY arms in this run",
      "Timeout conflict counts at equal caps measure throughput, not speedup",
      "C++ internally replays every derived row XOR source trace; Gaussian source replayed independently",
      "New unit/UNSAT not independent LRAT certified"]}
    save(ROOT/"report.json",report)
    with (ROOT/"summary.md").open("w") as f:
        f.write("# R176 frozen original residual mixed XOR-CNF\n\n")
        f.write("4 original SHA-matched residual-mixed CNFs, 2 repeats, 3 arms, 45s cap. NOT BLIND.\n\n")
        f.write("| Mode | Solved | PAR2 s | Conflicts | Decisions | Feedback delivered |\n|---|---:|---:|---:|---:|---:|\n")
        for mode,x in summary.items():
            f.write(f'| {mode} | {x["solved"]}/{x["attempts"]} | {x["par2_s"]} | {x["conflicts"]} | {x["decisions"]} | {x["feedback_consumed"]} |\n')
        f.write("\nZero solves is not a speedup regardless of conflict throughput. No LRAT for UNSAT.\n")
    print("R176_FINAL",json.dumps({"summary":summary,"formulas":len(cases),
                                  "attempts":len(rows)},sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="r176/r176-native")
    args=p.parse_args()
    shard(args.shard,pathlib.Path(args.binary)) if args.action=="shard" else audit()
