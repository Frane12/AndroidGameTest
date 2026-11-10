#!/usr/bin/env python3
"""DRNAS SHORTFROZEN1 - 5 previously frozen easy/medium original CNF SHA.
8 variants: native1, native_altseed, native_split4, shape gate, 1s probe,
Kissat 4.0.4, CaDiCaL 3.0.1, CryptoMiniSat 5.17.
10-second full E2E, 2 reps each, 5 source-scoped shards, 80 paired trials.

Every run hashes original file and parses source INSIDE E2E timer, pins ONE
logical CPU per child, verifies original SAT model, penalizes unverified UNSAT.
UNSAT agreement by Kissat + CaDiCaL is not an independent proof.
The original 5 cases are reference-conditioned reused sources, not blind.
No native code or solver binaries are changed by this experiment.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,math,os,pathlib,random,tempfile,time
import drnas_equiv9_prospective_seed_holdout as e9
import drnas_equiv10m5_frozen_rescue as m5
import drnas_equiv8_native_seed_hedge as e8

ROOT=pathlib.Path("mre_shortfrozen1")
CMS=pathlib.Path("mre_equiv12/bin/cryptominisat5")
PROTO="DRNAS-SHORTFROZEN1-FIVE-SHA-8ARMS-2REP-10S-ONECPU-v1"
ARMS=("native1","native_altseed","native_split4","native_shape_gate",
      "native_probe1","kissat1","cadical301_default","cms517_default")
CAP=10.0
COUNT=5
REPS=2
SHARDS=5
EXPECTED=COUNT*REPS*len(ARMS)
GATE_VARS=2000
GATE_CLAUSES=15000
PROBE_S=1.0
CMS_COMMIT="03954f7f7815ea3984774c95a66e7c224cd25952"

def need(ok,msg):
    if not ok:raise RuntimeError("SHORTFROZEN1_FAIL_CLOSED "+str(msg))
def digest(path):return e9.digest(path)
def write(path,obj):
    p=pathlib.Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def originals():
    old=m5.verify()
    need(old["trial_count"]==50 and len(old["cases"])==COUNT,
         "source roster is not exact EQUIV10M5 frozen five")
    need(collections.Counter(x["reference_band"] for x in old["cases"])==
         {"easy":1,"medium":4},"reference band changed")
    return old
def selftest():
    ROOT.mkdir(parents=True,exist_ok=True)
    need(all(p.is_file() for p in (e9.NATIVE,e9.KISSAT,e9.CAD,CMS)),
         "source-pinned binaries missing")
    with tempfile.TemporaryDirectory() as folder:
        src=pathlib.Path(folder)/"toy.cnf"
        src.write_text("p cnf 3 3\n1 2 0\n-1 2 0\n-2 3 0\n")
        case=dict(filename=str(src),sha256=digest(src),gbd="toy")
        for arm in ARMS:
            r=trial(case,0,arm,toy=True)
            need(r["status"]=="SAT" and r["SAT_original_witness_verified"],
                 "SAT original model selftest: "+arm)
    print("SHORTFROZEN1_SELFTEST_PASS",json.dumps({
        "original_SAT_model_verified_arms":len(ARMS),
        "one_cpu":True,"synthetic_source_sha_checked":True,
        "candidate_source_selection_fixed_before_benchmark":True
    },sort_keys=True),flush=True)

def freeze():
    old=originals()
    need(CMS.is_file(),"pinned CMS binary missing")
    ROOT.mkdir(parents=True,exist_ok=True)
    m=dict(protocol=PROTO,
        source="unchanged five EQUIV10M5 originally reference-selected 2024/25 CNFs",
        known_source=True,globally_blind=False,no_reselection=True,
        original_selection="1 easy, 4 medium, all five 2026-11-10 frozen cases",
        original_frozen_manifest_sha256=digest(m5.ROOT/"manifest.json"),
        original_E9_manifest_sha256=digest(e9.ROOT/"manifest.json"),
        selected_cases=old["cases"],caps_s=CAP,replications=REPS,
        shards=SHARDS,arms=list(ARMS),total_trials=EXPECTED,
        single_logical_CPU=True,no_parallel_children=True,
        source_only_shape_rule=dict(variables_gte=GATE_VARS,
                                    clauses_gte=GATE_CLAUSES),
        one_second_cold_probe_s=PROBE_S,
        sat_original_witness_required=True,
        UNSAT_requires_original_Kissat_and_CaDiCaL_agreement=True,
        UNSAT_no_independent_LRAT=True,no_automatic_promotion=True,
        source_code_sha256=digest(__file__),
        binary_sha256={
          "native":digest(e9.NATIVE),
          "kissat":digest(e9.KISSAT),
          "cadical":digest(e9.CAD),
          "cms":digest(CMS)},
        cms_source_commit=CMS_COMMIT,
        backend="pinned EQUIV12 native, Kissat, CaDiCaL, CMS 5.17")
    write(ROOT/"manifest.json",m)
    verify()
    print("SHORTFROZEN1_FREEZE_PASS",json.dumps({
      "selected_original_sha":len(old["cases"]),"easy":1,"medium":4,
      "arms":len(ARMS),"reps":REPS,"total_trials":EXPECTED,"cap_s":CAP,
      "not_blind":True},sort_keys=True),flush=True)

def verify():
    old=originals()
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["selected_cases"]==old["cases"] and
         m["caps_s"]==CAP and m["replications"]==REPS and
         m["arms"]==list(ARMS) and m["total_trials"]==EXPECTED and
         m["shards"]==SHARDS,"source-locked protocol drift")
    need(m["original_frozen_manifest_sha256"]==
         digest(m5.ROOT/"manifest.json") and
         m["original_E9_manifest_sha256"]==
         digest(e9.ROOT/"manifest.json") and
         m["source_code_sha256"]==digest(__file__) and
         m["binary_sha256"]=={
             "native":digest(e9.NATIVE),"kissat":digest(e9.KISSAT),
             "cadical":digest(e9.CAD),"cms":digest(CMS)},
         "frozen source/code/binary SHA drift")
    for c in old["cases"]:
        need(digest(e9.SOURCE/c["filename"])==c["sha256"],
             "original CNF SHA changed")
    return m

def features(n,clauses):
    return {"variables":n,"clauses":len(clauses),
            "binary":sum(len(c)==2 for c in clauses)}
def policy(arm,values):
    if arm=="native_shape_gate":
        return "alt" if (values["variables"]>=GATE_VARS or
                         values["clauses"]>=GATE_CLAUSES) else "base"
    if arm=="native_altseed":return "alt"
    return "base"

def cms_stage(src,clauses,cpu,limit,folder):
    started=time.perf_counter()
    prev=e9.x22.child_cpu()
    child=e9.x22.launch("cms",[
        str(CMS),"--verb","0","-t","1",str(src)],cpu,folder)
    status="TIMEOUT";witness=False
    try:
        while child["p"].poll() is None and time.perf_counter()-started < limit-.018:
            time.sleep(.004)
        if child["p"].poll() is not None:
            stdout,_=e9.x22.read_output(child)
            status,witness=e9.x22.solver_result(
                "cms",child["p"].returncode,stdout,clauses,{})
    finally:
        e9.x22.cleanup([child])
    elapsed=time.perf_counter()-started
    if elapsed>=limit or status not in ("SAT","UNSAT"):
        status="TIMEOUT";witness=False
    need(status!="SAT" or witness,"CMS invalid original SAT model")
    return dict(stage=0,budget_s=round(limit,6),status=status,
        SAT_original_witness_verified=witness,
        E2E_stage_s=round(elapsed,6),
        child_CPU_stage_s=round(e9.x22.child_cpu()-prev,6))

def trial(case,rep,arm,toy=False):
    need(arm in ARMS and rep in (0,1),"unknown arm or repeat")
    src=(pathlib.Path(case["filename"]) if toy else e9.SOURCE/case["filename"])
    started=time.perf_counter()
    prev=e9.x22.child_cpu()
    need(digest(src)==case["sha256"],"original SHA mismatch")
    n,clauses=e9.x22.read_cnf(src)
    need(n>0 and len(clauses)>0,"empty or invalid original source")
    props=features(n,clauses)
    base,alt=e9.seedpair(case["sha256"],rep)
    choice=policy(arm,props)
    cpu=min(os.sched_getaffinity(0))
    if arm in ("kissat1","cadical301_default","cms517_default"):
        plan=[(arm,base,CAP)]
    elif arm=="native_altseed" or arm=="native_shape_gate":
        plan=[("native1",alt if choice=="alt" else base,CAP)]
    elif arm=="native_split4":
        plan=[("native1",base,4.0),("native1",alt,CAP)]
    elif arm=="native_probe1":
        plan=[("native1",base,PROBE_S),("native1",alt,CAP)]
    else:
        plan=[("native1",base,CAP)]
    stages=[]
    status="TIMEOUT"
    with tempfile.TemporaryDirectory(dir=ROOT) as temp:
        for idx,(backend,seed,limit) in enumerate(plan):
            available=CAP-(time.perf_counter()-started)
            if available<.07:break
            budget=min(limit,available)
            stage=(cms_stage(src,clauses,cpu,budget,temp)
                   if backend=="cms517_default" else
                   e8.one_stage(backend,src,clauses,seed,cpu,budget,temp,idx))
            stages.append(stage)
            if stage["status"] in ("SAT","UNSAT"):
                status=stage["status"]
                break
    elapsed=time.perf_counter()-started
    if elapsed>=CAP:status="TIMEOUT"
    verified=(status=="SAT" and
      any(v["status"]=="SAT" and v["SAT_original_witness_verified"]
          for v in stages))
    need(status!="SAT" or verified,"SAT original witness invalid")
    need(digest(src)==case["sha256"],"CNF changed during trial")
    return dict(protocol=PROTO,sha256=case["sha256"],gbd=case["gbd"],
       cohort="preused_E10M5_frozen_easy_medium",reference_band=case.get("reference_band","toy"),
       arm=arm,rep=rep,cap_s=CAP,one_logical_CPU=True,pinned_cpu=cpu,
       seed_base=base,seed_alt=alt,seed_policy=choice,
       source_features=props,child_starts=len(stages),stages=stages,
       status=status,SAT_original_witness_verified=verified,
       UNSAT_independent_LRAT=False,original_sha256_verified=True,
       wall_E2E_s=round(elapsed,6),
       child_CPU_s=round(e9.x22.child_cpu()-prev,6))

def shard(idx):
    need(idx in range(SHARDS),"unregistered shard")
    m=verify()
    c=m["selected_cases"][idx]
    rows=[]
    for rep in range(REPS):
        arms=list(ARMS)
        random.Random(c["sha256"]+"|SHORTFROZEN1|"+str(rep)).shuffle(arms)
        for arm in arms:
            row=trial(c,rep,arm)
            row["shard"]=idx
            rows.append(row)
            write(ROOT/f"shard-{idx}.json",rows)
            print("SHORTFROZEN1_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==REPS*len(ARMS),"missing shard trials")
    print("SHORTFROZEN1_SHARD_PASS",idx,len(rows),flush=True)

def audit():
    m=verify()
    rows=[]
    for idx,c in enumerate(m["selected_cases"]):
        p=ROOT/f"shard-{idx}.json"
        need(p.is_file(),"missing shard artifact "+str(idx))
        records=json.loads(p.read_text())
        need(len(records)==REPS*len(ARMS) and
             {r["sha256"] for r in records}=={c["sha256"]},
             "shard source mismatch")
        rows.extend(records)
    keys={(r["sha256"],r["rep"],r["arm"]) for r in rows}
    expected={(c["sha256"],rep,arm) for c in m["selected_cases"]
              for rep in range(REPS) for arm in ARMS}
    need(len(rows)==len(keys)==len(expected)==EXPECTED and
         keys==expected,"incomplete matched source matrix")
    bysha=collections.defaultdict(list)
    for r in rows:
        need(r["protocol"]==PROTO and r["cap_s"]==CAP and
             r["one_logical_CPU"] is True and r["original_sha256_verified"] and
             r["child_starts"]==len(r["stages"]) and r["child_starts"]<=2 and
             r["wall_E2E_s"]<=CAP+.07 and
             r["status"] in ("SAT","UNSAT","TIMEOUT") and
             (r["status"]!="SAT" or r["SAT_original_witness_verified"]),
             "invalid original single-core SAT/UNSAT trial")
        bysha[r["sha256"]].append(r)
    agree=set()
    for sha,rr in bysha.items():
        non_timeout={r["status"] for r in rr if r["status"]!="TIMEOUT"}
        need(len(non_timeout)<=1,"original SAT vs UNSAT conflicting "+sha)
        if (any(r["arm"]=="kissat1" and r["status"]=="UNSAT" for r in rr)
           and any(r["arm"]=="cadical301_default" and r["status"]=="UNSAT" for r in rr)):
            agree.add(sha)
    def accepted(r):
        return r["status"]=="SAT" or (r["status"]=="UNSAT" and r["sha256"] in agree)
    def score(group):
        return dict(attempts=len(group),
            solved=sum(accepted(r) for r in group),
            SAT_original_verified=sum(r["status"]=="SAT" for r in group),
            UNSAT_original_backend_agreement_no_LRAT=sum(
               r["status"]=="UNSAT" and r["sha256"] in agree for r in group),
            UNSAT_unverified=sum(r["status"]=="UNSAT" and r["sha256"] not in agree
                                 for r in group),
            timeouts=sum(r["status"]=="TIMEOUT" for r in group),
            PAR2_s=round(sum(r["wall_E2E_s"] if accepted(r) else
                              2*CAP for r in group),6),
            CPU_s=round(sum(r["child_CPU_s"] for r in group),6),
            second_seed_solves=sum(r["status"]=="SAT" and r["child_starts"]==2
                                   for r in group))
    scores={arm:score([r for r in rows if r["arm"]==arm]) for arm in ARMS}
    for arm in ARMS:
        scores[arm]["speedup_vs_kissat_PAR2_x"]=round(
            scores["kissat1"]["PAR2_s"]/scores[arm]["PAR2_s"],6)
        scores[arm]["speedup_vs_native_PAR2_x"]=round(
            scores["native1"]["PAR2_s"]/scores[arm]["PAR2_s"],6)
    per_shard={str(i):{arm:score([r for r in rows if r["shard"]==i
                                      and r["arm"]==arm]) for arm in ARMS}
               for i in range(SHARDS)}
    paired={}
    index={(r["sha256"],r["rep"],r["arm"]):r for r in rows}
    for arm in ARMS:
        if arm=="native1":continue
        deltas=[(index[(c["sha256"],rep,"native1")]["wall_E2E_s"]
                    if accepted(index[(c["sha256"],rep,"native1")]) else 2*CAP)
             -(index[(c["sha256"],rep,arm)]["wall_E2E_s"]
                    if accepted(index[(c["sha256"],rep,arm)]) else 2*CAP)
             for c in m["selected_cases"] for rep in range(REPS)]
        paired[arm]=dict(pairs=len(deltas),
            wins=sum(d>.02 for d in deltas),
            regressions=sum(d<-.02 for d in deltas),
            ties=sum(abs(d)<=.02 for d in deltas),
            net_PAR2_benefit_s=round(sum(deltas),6))
    report=dict(protocol=PROTO,source_count=COUNT,total_trials=len(rows),
        original_sha_verified=True,sat_witness_verified=True,
        one_logical_CPU=True,no_parallel_children=True,
        frozen_reference_conditioned_not_blind=True,
        certification="SAT original witness, UNSAT only Kissat+CaDiCaL backend source-agree, no LRAT",
        UNSAT_consensus_original_SHA=sorted(agree),
        no_auto_promotion=True,short_cap_s=CAP,
        scores=scores,per_shard=per_shard,paired_vs_native1=paired,
        per_sha={sha:dict(reference_band=rr[0]["reference_band"],
             shape_policy=next(x["seed_policy"] for x in rr
                          if x["arm"]=="native_shape_gate"),
             per_arm={arm:[dict(rep=r["rep"],status=r["status"],
                               E2E_s=r["wall_E2E_s"],CPU_s=r["child_CPU_s"])
                          for r in rr if r["arm"]==arm] for arm in ARMS})
                for sha,rr in bysha.items()})
    write(ROOT/"report.json",report)
    print("SHORTFROZEN1_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    ap.add_argument("--shard",type=int,default=0)
    a=ap.parse_args()
    if a.action=="shard":shard(a.shard)
    elif a.action=="verify":
        verify();print("SHORTFROZEN1_VERIFY_PASS",flush=True)
    else:globals()[a.action]()
