#!/usr/bin/env python3
"""C16P2A: paired causal two-process immediate portfolio benchmark on 24 original official SHA.

No shared CDCL state; no learned model. C15D original sources are historical,
not globally blind. SAT is checked by the native C controller on original CNF.
UNSAT is ONLY a published-reference agreement, not independent LRAT.
CPU metric = sum of reaped children CPU seconds; resource fair comparison
must show wall, CPU and worker counts (2/3 cores vs single).
"""
from __future__ import annotations
import argparse, collections, hashlib, json, os, pathlib, random, subprocess, time
ROOT=pathlib.Path("c16p2a_sources")
OUT=pathlib.Path("c16p2a_out")
PROTO="DRNAS-C16P2A-24HISTORICAL-6ARMS-2REPS-30S-E2E-v1"
CAP=30.0
REPS=2
SHARDS=8
MODES=("kissat","novivify","p2","p2pin","p2fast","p2reverse")
BINARY="c16p2a_bin/drnas_c16p2a"
KISSAT="built/bin/kissat_4_0_4"
CADICAL="c8c/bin/instrumented"
def need(condition,msg):
    if not condition:raise RuntimeError("C16P2A_FAIL_CLOSED "+str(msg))
def digest(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for part in iter(lambda:f.read(1<<20),b""):h.update(part)
    return h.hexdigest()
def save(p,content):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(content,sort_keys=True,indent=2)+"\n")
def prepare():
    ROOT.mkdir(parents=True,exist_ok=True)
    manifests=[
      ("c15d_sources/manifest.json","c15d_sources","c15d",12),
      ("prior_c12/c12_sources/manifest.json","prior_c12/c12_sources","official2026_C12_historical",8),
      ("prior_c13/c13_sources/manifest.json","prior_c13/c13_sources","official2026_C13_historical",12),
    ]
    cc=[];seen=set();duplicates=[];counts=collections.Counter()
    for name,directory,cohort,expected in manifests:
        m=pathlib.Path(name)
        need(m.is_file(),"source manifest absent "+name)
        d=json.loads(m.read_text())
        need(len(d["cases"])==expected,"unexpected historical source cohort size")
        for x in sorted(d["cases"],key=lambda x:x["sha256"]):
            p=pathlib.Path(directory)/x["filename"]
            need(p.is_file() and digest(p)==x["sha256"],"original source SHA changed "+str(p))
            need(x["status"] in ("SAT","UNSAT"),"missing reference status")
            if x["sha256"] in seen:
                duplicates.append(dict(sha256=x["sha256"],gbd=x["gbd"],cohort=cohort))
                continue
            seen.add(x["sha256"])
            if len(cc)>=24: continue
            case_cohort=x["cohort"] if cohort=="c15d" else cohort
            cc.append(dict(filename=str(p),sha256=x["sha256"],gbd=x["gbd"],
                 cohort=case_cohort,status=x["status"]))
            counts[case_cohort]+=1
    need(len(cc)==24 and len({x["sha256"] for x in cc})==24,
         "insufficient distinct source SHA to freeze 24 originals")
    manifest=dict(protocol=PROTO,cases=cc,source_count=24,cap_s=CAP,
        all_source_SHAs_frozen_prior_to_timing=True,
        source_sha_duplicates_excluded=duplicates,
        source_counts=dict(counts),
        all_sources_previously_seen_in_C12_C13_or_C15D=True,
        not_new_blind_holdout=True,independent_solver_seeds=False,
        independent_UNSAT_LRAT=False,baseline_p2_is_same_C_binary=True,
        experiments_frozen=("p2pin","p2fast","p2reverse"),
        no_auto_promotion=True)
    save(ROOT/"manifest.json",manifest)
    print("C16P2A_FROZEN",json.dumps(dict(sources=24,excluded_duplicate_SHA=len(duplicates),
         cohorts=dict(counts),manifest_sha256=digest(ROOT/"manifest.json")),sort_keys=True),flush=True)
def cases():
    m=ROOT/"manifest.json"
    need(m.is_file(),"missing frozen source manifest")
    d=json.loads(m.read_text())
    need(d["protocol"]==PROTO and d["all_source_SHAs_frozen_prior_to_timing"],"protocol drift")
    cc=d["cases"]
    need(len(cc)==24 and len({x["sha256"] for x in cc})==24,"original SHA count mismatch")
    for x in cc:
        p=pathlib.Path(x["filename"])
        need(p.exists() and digest(p)==x["sha256"],"original SHA verification failed")
        need(x["cohort"] in ("development_c14","development_c8h","prospective_official",
                              "official2026_C12_historical","official2026_C13_historical"),"cohort drift")
        need(x["status"] in ("SAT","UNSAT"),"reference drift")
    return cc
def smoke():
    # Test both backends plus pinned, fast-poll and reversed-launch portfolios.
    OUT.mkdir(parents=True,exist_ok=True)
    p=OUT/"smoke.cnf";p.write_text("p cnf 3 3\n1 2 0\n-1 3 0\n2 3 0\n")
    for arm in MODES:
        proc=subprocess.run([str(pathlib.Path(BINARY).resolve()),arm,str(p.resolve()),
          str(pathlib.Path(KISSAT).resolve()),str(pathlib.Path(CADICAL).resolve()),"5","SAT"],
          text=True,capture_output=True,timeout=10)
        lines=[v for v in proc.stdout.splitlines() if v.startswith("C16P2A_RESULT ")]
        need(len(lines)==1,arm+": missing C16P2A JSON "+proc.stderr[-300:])
        r=json.loads(lines[0].split(" ",1)[1])
        need(proc.returncode==10 and r["status"]=="SAT" and r["sat_original_verified"]
          and not r["invalid_result_detected"],arm+": SAT smoke failed "+proc.stdout[-500:])
    # External check that UNSAT is rejected in strict mode, accepted only with explicit flag.
    q=OUT/"smoke_unsat.cnf";q.write_text("p cnf 1 2\n1 0\n-1 0\n")
    strict=subprocess.run([str(pathlib.Path(BINARY).resolve()),"cadical",str(q.resolve()),
          str(pathlib.Path(KISSAT).resolve()),str(pathlib.Path(CADICAL).resolve()),"5","UNSAT"],
          text=True,capture_output=True,timeout=10)
    need(strict.returncode==0 and json.loads(strict.stdout.split("C16P2A_RESULT ")[1])["status"]=="UNKNOWN",
         "missing proof accepted in strict mode")
    permissive=subprocess.run([str(pathlib.Path(BINARY).resolve()),"cadical",str(q.resolve()),
          str(pathlib.Path(KISSAT).resolve()),str(pathlib.Path(CADICAL).resolve()),"5","UNSAT",
          "--reference-unsat-agreement"],text=True,capture_output=True,timeout=10)
    v=json.loads(permissive.stdout.split("C16P2A_RESULT ")[1])
    need(permissive.returncode==20 and v["status"]=="UNSAT" and
         v["unsat_reference_agreement_only"] and not v["unsat_independent_proof"],
         "benchmark agreement mode incorrectly claimed independent proof")
    print("C16P2A_SMOKE_6_MODES_SAT_ORIGINAL_AND_EXPLICIT_UNSAT_PASS",flush=True)
def trial(x,arm,rep,pos,seed):
    p=pathlib.Path(x["filename"]).resolve()
    need(digest(p)==x["sha256"],"source changed before each attempt")
    cmd=[str(pathlib.Path(BINARY).resolve()),arm,str(p),
        str(pathlib.Path(KISSAT).resolve()),str(pathlib.Path(CADICAL).resolve()),
        str(CAP),x["status"]]
    if x["status"]=="UNSAT":cmd.append("--reference-unsat-agreement")
    begun=time.perf_counter()
    z=subprocess.run(cmd,text=True,capture_output=True,timeout=CAP+8)
    measured=time.perf_counter()-begun
    lines=[v for v in z.stdout.splitlines() if v.startswith("C16P2A_RESULT ")]
    need(len(lines)==1,"missing controller result: "+z.stderr[-1500:])
    v=json.loads(lines[0].split(" ",1)[1])
    need(z.returncode in (0,10,20),"native C controller crashed "+z.stderr[-500:])
    need(z.returncode=={"UNKNOWN":0,"SAT":10,"UNSAT":20}[v["status"]],"return code mismatch")
    need(v["status"]=="UNKNOWN" or v["status"]==x["status"],"reference disagreement")
    need(v["status"]!="SAT" or v["sat_original_verified"],"unverified SAT")
    need(v["status"]!="UNSAT" or (v["unsat_reference_agreement_only"] and not v["unsat_independent_proof"]),"UNSAT mislabeled")
    need(v["processes"]==(1 if arm in ("kissat","novivify") else 2),
         "two-process control mode changed")
    need(v["pinned"]==(arm=="p2pin"),"pinned flag mismatch")
    need(v["poll_us"]==(250 if arm=="p2fast" else 2000),"poll time changed")
    if arm=="p2pin":
        need(len({w["pinned_cpu"] for w in v["workers"]})==2 and
             all(w["pinned_cpu"]>=0 for w in v["workers"]),
             "workers not pinned to distinct CPU cores")
    if arm=="p2reverse":
        need([w["name"] for w in v["workers"]]==["novivify","kissat"],
             "worker order was not reversed")
    else:
        need(v["workers"][0]["name"]=="kissat" if arm!="novivify"
             else v["workers"][0]["name"]=="novivify",
             "unexpected first worker")
    need(not v["invalid_result_detected"],"invalid SAT or status detected")
    need(v["wall_s"]<=CAP+0.2,"excessive time after cap")
    need(v["cpu_sum_s"]>=0,"negative CPU")
    need(v["wall_s"]<=measured+0.05 and measured-v["wall_s"]<1.0,"external harness timing mismatch")
    status=v["status"]
    return dict(protocol=PROTO,gbd=x["gbd"],source_sha256=x["sha256"],
      cohort=x["cohort"],arm=arm,rep=rep,order_position=pos,order_seed=seed,
      runner=os.environ.get("RUNNER_NAME","unknown"),status=status,
      reference=x["status"],cap_s=CAP,PAR2_s=round(v["wall_s"] if status!="UNKNOWN" else CAP*2,6),
      full_E2E_wall_s=v["wall_s"],cpu_sum_s=v["cpu_sum_s"],rss_sum_upper_kb=v["rss_sum_upper_kb"],
      sat_original_verified=v["sat_original_verified"],
      unsat_reference_agreement_only=v["unsat_reference_agreement_only"],
      independent_unsat_LRAT=False,processes=v["processes"],online_cpus=v["online_cpus"],
      winner=v["winner"],workers=v["workers"],
      native_controller_SHA256=digest(BINARY),kissat_SHA256=digest(KISSAT),
      cadical_SHA256=digest(CADICAL),
      independent_solver_seeds=False,no_auto_promotion=True,
      commit_sha=os.environ.get("GITHUB_SHA","local"))
def shard(index):
    need(index in range(SHARDS),"invalid shard")
    cc=[x for i,x in enumerate(cases()) if i%SHARDS==index]
    need(len(cc)==3,"shard partition changed")
    OUT.mkdir(parents=True,exist_ok=True);rows=[]
    for x in cc:
        for rep in range(REPS):
            seed=int(hashlib.sha256((PROTO+"|"+x["sha256"]+"|"+str(rep)).encode()).hexdigest()[:8],16)
            order=list(MODES);random.Random(seed).shuffle(order)
            for pos,mode in enumerate(order):
                r=trial(x,mode,rep,pos,seed)
                rows.append(r);save(OUT/("shard-%d.json"%index),rows)
                print("C16P2A_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==36,"incomplete shard")
    print("C16P2A_SHARD_PASS",index,len(rows),flush=True)
def audit():
    cc=cases();bysha={x["sha256"]:x for x in cc};rows=[]
    for i in range(SHARDS):
        p=OUT/("shard-%d.json"%i);need(p.exists(),"missing shard")
        a=json.loads(p.read_text());need(len(a)==36,"partial shard");rows+=a
    need(len(rows)==288,"paired attempts missing")
    expected={(x["sha256"],r,m) for x in cc for r in range(REPS) for m in MODES}
    keys={(r["source_sha256"],r["rep"],r["arm"]) for r in rows}
    need(keys==expected and len(rows)==len(keys),"source pairing or uniqueness failed")
    for r in rows:
        x=bysha[r["source_sha256"]]
        need(r["cohort"]==x["cohort"] and r["reference"]==x["status"],"cohort reference mismatch")
        need(r["status"] in ("SAT","UNSAT","UNKNOWN"),"bad status")
        need(r["status"]=="UNKNOWN" or r["status"]==x["status"],"reference contradiction")
        need(r["status"]!="SAT" or r["sat_original_verified"],"SAT verification missing")
        need(r["status"]!="UNSAT" or r["unsat_reference_agreement_only"],"UNSAT labeling error")
        need(r["PAR2_s"]==2*CAP if r["status"]=="UNKNOWN" else abs(r["PAR2_s"]-r["full_E2E_wall_s"])<1e-6,
             "PAR2 rule mismatch")
    def aggregate(data):
        result={}
        for arm in MODES:
            rr=[r for r in data if r["arm"]==arm]
            result[arm]=dict(PAR2_s=round(sum(r["PAR2_s"] for r in rr),6),
                solved=sum(r["status"]!="UNKNOWN" for r in rr),
                timeouts=sum(r["status"]=="UNKNOWN" for r in rr),attempts=len(rr),
                child_cpu_sum_s=round(sum(r["cpu_sum_s"] for r in rr),6),
                actual_wall_sum_s=round(sum(r["full_E2E_wall_s"] for r in rr),6),
                winner_distribution=dict(collections.Counter(r["winner"] for r in rr)))
        for arm in MODES:
            result[arm]["speedup_vs_kissat_wall_PAR2_x"]=round(result["kissat"]["PAR2_s"]/result[arm]["PAR2_s"],6)
            result[arm]["speedup_vs_p2_wall_PAR2_x"]=round(result["p2"]["PAR2_s"]/result[arm]["PAR2_s"],6)
            result[arm]["child_CPU_pct_vs_p2"]=round(100*result[arm]["child_cpu_sum_s"]/result["p2"]["child_cpu_sum_s"],3)
        return result
    summary=dict(protocol=PROTO,real_E2E_trials=288,source_count=24,
      cap_s=CAP,independent_solver_seeds=False,independent_UNSAT_LRAT=False,
      historical_official_cohorts_not_blind=True,
      portfolio_compares_wall_not_equal_cpu_effort=True,
      total_cpu_work_is_child_cpu_sum_no_parent_verification_cpu=True,
      source_SHA_original_verified=True,
      statuses_SAT_original_witness_checked=True,UNSAT_only_frozen_reference_agreement=True,
      causal_arms={"p2":"same C binary baseline two simultaneous processes",
             "p2pin":"two simultaneous processes pinned to distinct allowed CPUs",
             "p2fast":"two simultaneous processes with 250us vs 2ms poll",
             "p2reverse":"same two processes launched in reversed order"},
      no_adaptive_routing=True,no_auto_promotion=True,
      cohorts={k:aggregate(rows if k=="all" else [r for r in rows if r["cohort"]==k])
             for k in ("all","development_c14","development_c8h","prospective_official","official2026_C12_historical","official2026_C13_historical") if k=="all" or any(r["cohort"]==k for r in rows)},
      per_case=[dict(gbd=x["gbd"],cohort=x["cohort"],
         arms={a:dict(PAR2_s=round(sum(r["PAR2_s"] for r in rows if r["source_sha256"]==x["sha256"] and r["arm"]==a),6),
                      solved=sum(r["status"]!="UNKNOWN" for r in rows if r["source_sha256"]==x["sha256"] and r["arm"]==a)) for a in MODES}) for x in cc])
    summary["cohorts"]["all"]=aggregate(rows)
    paired=[]
    by={(r["source_sha256"],r["rep"],r["arm"]):r for r in rows}
    for x in cc:
        for rep in range(REPS):
            base=by[(x["sha256"],rep,"p2")]
            for arm in ("p2pin","p2fast","p2reverse"):
                r=by[(x["sha256"],rep,arm)]
                paired.append(dict(gbd=x["gbd"],cohort=x["cohort"],rep=rep,
                    arm=arm,delta_PAR2_s=round(r["PAR2_s"]-base["PAR2_s"],6),
                    delta_cpu_s=round(r["cpu_sum_s"]-base["cpu_sum_s"],6),
                    solved_delta=int(r["status"]!="UNKNOWN")-int(base["status"]!="UNKNOWN")))
    summary["paired_differences_vs_p2"]=paired
    summary["paired_regressions"]={
       arm:dict(pairs=len([x for x in paired if x["arm"]==arm]),
           regression_over_50ms=sum(x["delta_PAR2_s"]>0.05 for x in paired if x["arm"]==arm),
           solves_lost=sum(x["solved_delta"]<0 for x in paired if x["arm"]==arm),
           solves_gained=sum(x["solved_delta"]>0 for x in paired if x["arm"]==arm))
       for arm in ("p2pin","p2fast","p2reverse")}
    save(OUT/"report.json",summary)
    print("C16P2A_FINAL",json.dumps({k:v for k,v in summary.items() if k!="per_case"},sort_keys=True),flush=True)
    for x in summary["per_case"]:print("C16P2A_CASE",json.dumps(x,sort_keys=True),flush=True)
def main():
    p=argparse.ArgumentParser();p.add_argument("action",choices=("prepare","verify","smoke","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="prepare":prepare()
    elif a.action=="verify":print("C16P2A_SOURCE_SHA_VERIFIED",len(cases()),flush=True)
    elif a.action=="smoke":smoke()
    elif a.action=="shard":shard(a.shard)
    else:audit()
if __name__=="__main__":main()
