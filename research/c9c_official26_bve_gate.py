#!/usr/bin/env python3
"""C9c 10-12 new official2026 originals, 4 arms, 2 repeats, 60s E2E PAR2.

The C9 source-only rule (nvars <=1500 -> CaDiCaL --no-elim) was locked
in C9 run 42527824455 before C9c source SHA freeze and any C9c runs.
Run E2E directly on exact original CNF; no oracle and no pilot.
External CaDiCaL and Kissat repetitions are NOT independent seeds.
SAT witness independently checked on original SHA; UNSAT only published
status agreement, without LRAT. No auto-promotion; must report regressions.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,subprocess,time
import c9c_official26_freeze as freeze
import c9b_official26_bve_gate as old
import mre11b_prospective_benchmark as ref
import r195_native_cms_benchmark as cms
PROTO="DRNAS-C9C-OFFICIAL2026-12SHA-4ARM-2REP-60S-E2E-v1"
CAP=60.0
REPS=2
SHARDS=4
ARMS=("cadical","cadical_noelim","kissat","c9_route")
ROOT=pathlib.Path("c9c_out")
LOCKED_POLICY="nvars<=1500 => cadical_noelim else cadical"
def need(ok,msg):
    if not ok:raise RuntimeError("C9C_FAIL_CLOSED "+str(msg))
def cases():
    ref=old.rule_locked()
    need(ref["final_all19_candidate_rule_for_future_prospective_test"]["rule"]
        ==["nvars",1500,"le"],"C9 prior frozen model drift")
    arr=freeze.cases()
    return [dict(gbd=x["gbd"],sha256=x["sha256"],
       path=freeze.ROOT/x["filename"],
       nvars=x["variables"],nclauses=x["clauses"],
       reference_status=x["status"]) for x in arr]
def select(c):
    return "cadical_noelim" if c["nvars"]<=1500 else "cadical"
def cli(mode,path):
    p=str(path.resolve())
    if mode=="cadical":return ["/usr/bin/cadical",p]
    if mode=="cadical_noelim":return ["/usr/bin/cadical","--no-elim",p]
    if mode=="kissat":return [str(pathlib.Path("built/bin/kissat_4_0_4").resolve()),p]
    raise ValueError("invalid reference backend "+str(mode))
def smoke():
    ROOT.mkdir(exist_ok=True)
    tiny=ROOT/"smoke.cnf"
    tiny.write_text("p cnf 4 4\n1 2 0\n-1 2 0\n2 3 0\n4 0\n")
    for mode in ("cadical","cadical_noelim","kissat"):
        p=subprocess.run(cli(mode,tiny),capture_output=True,
          text=True,errors="replace",timeout=10,check=False)
        status,model=ref.external_parse(p)
        need(status=="SAT",mode+" failed original SAT")
        cms.verify_model(tiny,model)
    assert len(cases())>=freeze.MIN_READY
    print("C9C_STANDARD_SOLVER_SAT_WITNESS_SMOKE_PASS",flush=True)
def trial(c,rep,arm):
    need(rep in range(REPS) and arm in ARMS,"unknown mode / repetition")
    src=c["path"]
    need(freeze.digest(src)==c["sha256"],"source SHA changed during SAT test")
    t=time.perf_counter()
    if arm=="c9_route":
        n,m=old.source_header(src)
        need(n==c["nvars"] and m==c["nclauses"],"source header mutated")
        mode=select(c)
    else:mode=arm
    cmd=cli(mode,src)
    rem=CAP-(time.perf_counter()-t)
    p=None
    if rem>0:
        try:
            p=subprocess.run(cmd,capture_output=True,text=True,
                   errors="replace",timeout=rem,check=False)
        except subprocess.TimeoutExpired:pass
    elapsed=time.perf_counter()-t
    status="TIMEOUT";verified=False
    if p is not None:
        status,model=ref.external_parse(p)
        need(status in ("SAT","UNSAT","UNKNOWN","TIMEOUT"),"unknown solver terminal")
        if status=="SAT":
            cms.verify_model(src,model)
            verified=True
        if status in ("SAT","UNSAT"):
            need(status==c["reference_status"],
                 "official published SAT/UNSAT contradiction")
    if elapsed>CAP or status not in ("SAT","UNSAT"):
        status="TIMEOUT";verified=False
    return dict(protocol=PROTO,gbd=c["gbd"],sha256=c["sha256"],
       status=status,mode=arm,selected_backend=mode,
       source_nvars=c["nvars"],source_nclauses=c["nclauses"],
       published_reference_status=c["reference_status"],rep=rep,cap_s=CAP,
       wall_s=round(elapsed,6),
       PAR2_s=round(elapsed if status in ("SAT","UNSAT") else 2*CAP,6),
       SAT_original_witness_verified=verified,
       independent_UNSAT_LRAT=False,
       independent_external_seed=False,
       source_only_router_header_charged=(arm=="c9_route"),
       original_SHA_unmodified=True,
       build_sha=os.getenv("GITHUB_SHA","local"))
def shard(i):
    need(i in range(SHARDS),"invalid shard")
    cc=cases();selected=[c for j,c in enumerate(cc) if j%SHARDS==i]
    ROOT.mkdir(exist_ok=True);rows=[]
    (ROOT/("shard-%d.json"%i)).write_text("[]\n")
    for c in selected:
        for rep in range(REPS):
            order=list(ARMS)
            rnd=int(hashlib.sha256((PROTO+"|"+c["sha256"]+"|"+str(rep)).encode()).hexdigest()[:14],16)
            random.Random(rnd).shuffle(order)
            for arm in order:
                r=trial(c,rep,arm);rows.append(r)
                (ROOT/("shard-%d.json"%i)).write_text(
                    json.dumps(rows,indent=2,sort_keys=True)+"\n")
                print("C9C_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==len(selected)*REPS*len(ARMS),"partial real SAT shard")
    print("C9C_SHARD_PASS",i,len(rows),flush=True)
def audit():
    cc=cases();bysha={c["sha256"]:c for c in cc}
    rows=[]
    for i in range(SHARDS):
        p=ROOT/("shard-%d.json"%i)
        need(p.is_file(),"missing C9c shard "+str(i))
        a=json.loads(p.read_text())
        expected=len([c for j,c in enumerate(cc) if j%SHARDS==i])*REPS*len(ARMS)
        need(len(a)==expected,"partial source locked shard "+str(i))
        rows+=a
    need(len(rows)==len(cc)*REPS*len(ARMS),
         "missing real full E2E SAT attempts")
    paired=collections.defaultdict(dict)
    for r in rows:
        c=bysha.get(r["sha256"])
        need(c is not None and c["gbd"]==r["gbd"] and
             r["protocol"]==PROTO and r["mode"] in ARMS and
             r["rep"] in range(REPS) and r["cap_s"]==CAP,
             "alien source or cap")
        expect=select(c) if r["mode"]=="c9_route" else r["mode"]
        need(r["selected_backend"]==expect and
             r["status"] in ("SAT","UNSAT","TIMEOUT"),
             "unregistered gate or terminal")
        if r["mode"]=="c9_route":need(r["source_only_router_header_charged"],
                                    "unpaid source scan")
        if r["status"]=="TIMEOUT":
            need(r["PAR2_s"]==2*CAP and
                 not r["SAT_original_witness_verified"],
                 "incorrect timeout penalty")
        else:
            need(r["status"]==c["reference_status"] and
                 abs(r["PAR2_s"]-r["wall_s"])<0.000002,
                 "SAT/UNSAT mismatch or wrong solved PAR2")
            if r["status"]=="SAT":
                need(r["SAT_original_witness_verified"],
                     "unverified SAT model against exact original")
        key=(c["sha256"],r["rep"])
        need(r["mode"] not in paired[key],"duplicate paired arm")
        paired[key][r["mode"]]=r
    need(len(paired)==len(cc)*REPS and all(set(v)==set(ARMS) for v in paired.values()),
         "source-rep-arm matrix incomplete")
    scores={}
    for mode in ARMS:
        a=[r for r in rows if r["mode"]==mode]
        scores[mode]=dict(n=len(a),solved=sum(r["status"]!="TIMEOUT" for r in a),
            SAT=sum(r["status"]=="SAT" for r in a),
            UNSAT_prior_reference_no_LRAT=sum(r["status"]=="UNSAT" for r in a),
            timeouts=sum(r["status"]=="TIMEOUT" for r in a),
            PAR2_s=round(sum(r["PAR2_s"] for r in a),6),
            measured_wall_s=round(sum(r["wall_s"] for r in a),6))
    base=scores["cadical"]["PAR2_s"]
    for mode in ARMS:
        scores[mode]["speedup_vs_CaDiCaL_PAR2_x"]=round(
            base/scores[mode]["PAR2_s"],6)
    per=[]
    for c in cc:
        rr=[r for r in rows if r["sha256"]==c["sha256"]]
        sub={}
        for mode in ARMS:
            a=[r for r in rr if r["mode"]==mode]
            sub[mode]=dict(solved=sum(r["status"]!="TIMEOUT" for r in a),
                PAR2_s=round(sum(r["PAR2_s"] for r in a),6),
                wall_s=[r["wall_s"] for r in sorted(a,key=lambda x:x["rep"])],
                statuses=[r["status"] for r in sorted(a,key=lambda x:x["rep"])])
        per.append(dict(gbd=c["gbd"],sha256=c["sha256"],
            nvars=c["nvars"],reference_status=c["reference_status"],
            selector_on=select(c)=="cadical_noelim",
            regression_s=round(sub["c9_route"]["PAR2_s"]-sub["cadical"]["PAR2_s"],6),
            by_mode=sub))
    sel=[x for x in per if x["selector_on"]]
    reg=[x for x in per if x["regression_s"]>0.05]
    best=[x for x in per if x["regression_s"]<-.05]
    case_bonus=max(((-x["regression_s"]) for x in per),default=0)
    gain=base-scores["c9_route"]["PAR2_s"]
    report=dict(protocol=PROTO,
        cohort="official2026 newly SHA-frozen C9c source-only; historical registry not exhaustive",
        original_source_lock=True,source_SHA_disjoint_C9_19_and_C9b_X5_3=True,
        cap_s=CAP,REPS=REPS,source_count=len(cc),full_trials=len(rows),
        original_witnesses_replayed=True,
        UNSAT_independent_LRAT=False,external_repeats_not_independent_seed=True,
        mode_uses_locked_C9_rule=LOCKED_POLICY,
        no_auto_promotion=True,
        selected_small_sources=len(sel),selected_large_sources=len(per)-len(sel),
        gate_winning_formulas=len(best),gate_regressed_formulas=len(reg),
        max_regression_s=max([x["regression_s"] for x in per]+[0.]),
        aggregate_gain_s=round(gain,6),largest_single_case_gain_s=round(case_bonus,6),
        gain_excluding_largest_case_s=round(gain-case_bonus,6),
        scores=scores,per_source=per)
    ROOT.mkdir(exist_ok=True)
    (ROOT/"report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("C9C_FINAL",json.dumps({k:v for k,v in report.items() if k!="per_source"},
          sort_keys=True),flush=True)
    for x in per:print("C9C_CASE",json.dumps(x,sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("action",choices=("verify","smoke","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="verify":
        print("C9C_2026_LOCK_PASS",len(cases()),flush=True)
    elif a.action=="smoke":smoke()
    elif a.action=="shard":shard(a.shard)
    else:audit()
