#!/usr/bin/env python3
"""C16P paired real E2E benchmark of independent native-C process portfolios.

No shared CDCL state; no learned model. C15D original sources are historical,
not globally blind. SAT is checked by the native C controller on original CNF.
UNSAT is ONLY a published-reference agreement, not independent LRAT.
CPU metric = sum of reaped children CPU seconds; resource fair comparison
must show wall, CPU and worker counts (2/3 cores vs single).
"""
from __future__ import annotations
import argparse, collections, hashlib, json, os, pathlib, random, subprocess, time
ROOT=pathlib.Path("c15d_sources")
OUT=pathlib.Path("c16p_out")
PROTO="DRNAS-C16P-12HISTORICAL-5ARMS-2REPS-30S-E2E-v1"
CAP=30.0
REPS=2
SHARDS=6
MODES=("kissat","cadical","novivify","p2","p3")
BINARY="c16p_bin/drnas_c16p"
KISSAT="built/bin/kissat_4_0_4"
CADICAL="c8c/bin/instrumented"
def need(condition,msg):
    if not condition:raise RuntimeError("C16P_FAIL_CLOSED "+str(msg))
def digest(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for part in iter(lambda:f.read(1<<20),b""):h.update(part)
    return h.hexdigest()
def save(p,content):
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(content,sort_keys=True,indent=2)+"\n")
def cases():
    m=ROOT/"manifest.json"
    need(m.exists(),"C15D original manifest missing")
    d=json.loads(m.read_text())
    need(len(d["cases"])==12,"frozen case count differs")
    cc=d["cases"]
    need(len({x["sha256"] for x in cc})==12,"duplicate original SHA")
    for x in cc:
        p=ROOT/x["filename"]
        need(x["cohort"] in ("development_c14","development_c8h","prospective_official"),"cohort drift")
        need(x["status"] in ("SAT","UNSAT"),"reference drift")
        need(p.exists() and digest(p)==x["sha256"],"original SHA changed")
    return cc
def smoke():
    # Check three actual baseline solvers and both portfolio modes on known easy SAT.
    OUT.mkdir(parents=True,exist_ok=True)
    p=OUT/"smoke.cnf";p.write_text("p cnf 3 3\n1 2 0\n-1 3 0\n2 3 0\n")
    for arm in MODES:
        proc=subprocess.run([str(pathlib.Path(BINARY).resolve()),arm,str(p.resolve()),
          str(pathlib.Path(KISSAT).resolve()),str(pathlib.Path(CADICAL).resolve()),"5","SAT"],
          text=True,capture_output=True,timeout=10)
        lines=[v for v in proc.stdout.splitlines() if v.startswith("C16P_RESULT ")]
        need(len(lines)==1,arm+": missing C16P JSON "+proc.stderr[-300:])
        r=json.loads(lines[0].split(" ",1)[1])
        need(proc.returncode==10 and r["status"]=="SAT" and r["sat_original_verified"]
          and not r["invalid_result_detected"],arm+": SAT smoke failed "+proc.stdout[-500:])
    # External check that UNSAT is rejected in strict mode, accepted only with explicit flag.
    q=OUT/"smoke_unsat.cnf";q.write_text("p cnf 1 2\n1 0\n-1 0\n")
    strict=subprocess.run([str(pathlib.Path(BINARY).resolve()),"cadical",str(q.resolve()),
          str(pathlib.Path(KISSAT).resolve()),str(pathlib.Path(CADICAL).resolve()),"5","UNSAT"],
          text=True,capture_output=True,timeout=10)
    need(strict.returncode==0 and json.loads(strict.stdout.split("C16P_RESULT ")[1])["status"]=="UNKNOWN",
         "missing proof accepted in strict mode")
    permissive=subprocess.run([str(pathlib.Path(BINARY).resolve()),"cadical",str(q.resolve()),
          str(pathlib.Path(KISSAT).resolve()),str(pathlib.Path(CADICAL).resolve()),"5","UNSAT",
          "--reference-unsat-agreement"],text=True,capture_output=True,timeout=10)
    v=json.loads(permissive.stdout.split("C16P_RESULT ")[1])
    need(permissive.returncode==20 and v["status"]=="UNSAT" and
         v["unsat_reference_agreement_only"] and not v["unsat_independent_proof"],
         "benchmark agreement mode incorrectly claimed independent proof")
    print("C16P_SMOKE_5_MODES_SAT_ORIGINAL_AND_EXPLICIT_UNSAT_PASS",flush=True)
def trial(x,arm,rep,pos,seed):
    p=(ROOT/x["filename"]).resolve()
    need(digest(p)==x["sha256"],"source changed before each attempt")
    cmd=[str(pathlib.Path(BINARY).resolve()),arm,str(p),
        str(pathlib.Path(KISSAT).resolve()),str(pathlib.Path(CADICAL).resolve()),
        str(CAP),x["status"]]
    if x["status"]=="UNSAT":cmd.append("--reference-unsat-agreement")
    begun=time.perf_counter()
    z=subprocess.run(cmd,text=True,capture_output=True,timeout=CAP+8)
    measured=time.perf_counter()-begun
    lines=[v for v in z.stdout.splitlines() if v.startswith("C16P_RESULT ")]
    need(len(lines)==1,"missing controller result: "+z.stderr[-1500:])
    v=json.loads(lines[0].split(" ",1)[1])
    need(z.returncode in (0,10,20),"native C controller crashed "+z.stderr[-500:])
    need(z.returncode=={"UNKNOWN":0,"SAT":10,"UNSAT":20}[v["status"]],"return code mismatch")
    need(v["status"]=="UNKNOWN" or v["status"]==x["status"],"reference disagreement")
    need(v["status"]!="SAT" or v["sat_original_verified"],"unverified SAT")
    need(v["status"]!="UNSAT" or (v["unsat_reference_agreement_only"] and not v["unsat_independent_proof"]),"UNSAT mislabeled")
    need(v["processes"]=={"p2":2,"p3":3}.get(arm,1),"worker count differs")
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
    need(len(cc)==2,"shard partition changed")
    OUT.mkdir(parents=True,exist_ok=True);rows=[]
    for x in cc:
        for rep in range(REPS):
            seed=int(hashlib.sha256((PROTO+"|"+x["sha256"]+"|"+str(rep)).encode()).hexdigest()[:8],16)
            order=list(MODES);random.Random(seed).shuffle(order)
            for pos,mode in enumerate(order):
                r=trial(x,mode,rep,pos,seed)
                rows.append(r);save(OUT/("shard-%d.json"%index),rows)
                print("C16P_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==20,"incomplete shard")
    print("C16P_SHARD_PASS",index,len(rows),flush=True)
def audit():
    cc=cases();bysha={x["sha256"]:x for x in cc};rows=[]
    for i in range(SHARDS):
        p=OUT/("shard-%d.json"%i);need(p.exists(),"missing shard")
        a=json.loads(p.read_text());need(len(a)==20,"partial shard");rows+=a
    need(len(rows)==120,"paired attempts missing")
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
        return result
    summary=dict(protocol=PROTO,real_E2E_trials=120,source_count=12,
      cap_s=CAP,independent_solver_seeds=False,independent_UNSAT_LRAT=False,
      historical_official_cohorts_not_blind=True,
      portfolio_compares_wall_not_equal_cpu_effort=True,
      total_cpu_work_is_child_cpu_sum_no_parent_verification_cpu=True,
      source_SHA_original_verified=True,
      statuses_SAT_original_witness_checked=True,UNSAT_only_frozen_reference_agreement=True,
      no_adaptive_routing=True,no_auto_promotion=True,
      cohorts={k:aggregate([r for r in rows if r["cohort"]==k])
             for k in ("all","development_c14","development_c8h","prospective_official") if k=="all" or any(r["cohort"]==k for r in rows)},
      per_case=[dict(gbd=x["gbd"],cohort=x["cohort"],
         arms={a:dict(PAR2_s=round(sum(r["PAR2_s"] for r in rows if r["source_sha256"]==x["sha256"] and r["arm"]==a),6),
                      solved=sum(r["status"]!="UNKNOWN" for r in rows if r["source_sha256"]==x["sha256"] and r["arm"]==a)) for a in MODES}) for x in cc])
    summary["cohorts"]["all"]=aggregate(rows)
    save(OUT/"report.json",summary)
    print("C16P_FINAL",json.dumps({k:v for k,v in summary.items() if k!="per_case"},sort_keys=True),flush=True)
    for x in summary["per_case"]:print("C16P_CASE",json.dumps(x,sort_keys=True),flush=True)
def main():
    p=argparse.ArgumentParser();p.add_argument("action",choices=("verify","smoke","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="verify":print("C16P_SOURCE_SHA_VERIFIED",len(cases()),flush=True)
    elif a.action=="smoke":smoke()
    elif a.action=="shard":shard(a.shard)
    else:audit()
if __name__=="__main__":main()
