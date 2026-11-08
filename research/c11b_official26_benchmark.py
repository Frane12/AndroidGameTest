#!/usr/bin/env python3
"""DRNAS C11b 5-arm SHA-frozen 2026 E2E triple-backend portfolio.

The exact source-only structural C10 route (from C10a, developed on C8D
and C9c) is frozen before NEW source selection. Reference solver binaries
CaDiCaL 1.7.3, Kissat 4.0.4, and C9 old no-elim route.
5 arms x 2 repetitions x 6-12 new ORIGINAL SHA (60s PAR2).
SAT witness checked on original. UNSAT published reference only, no LRAT.
External CLI repeats are NOT independent seeds, no solver hint/test snooping.
No run-time feedback/online pilot. Charged header inspection at selection.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,subprocess,time
import c11b_official26_freeze as freeze
import c9b_official26_bve_gate as old
import mre11b_prospective_benchmark as ref
import r195_native_cms_benchmark as cms

PROTO="DRNAS-C11B-2026-12SHA-5ARM-2REPS-60S-REAL-PAR2-v1"
OUT=pathlib.Path("c11b_out")
CAP=60.0;REPS=2;SHARDS=4
ARMS=("cadical","cadical_noelim","kissat","c10_old","c11_triple")
C11_RULE=freeze.FROZEN_RULE
def need(ok,msg):
    if not ok:raise RuntimeError("C11B_FAIL_CLOSED "+str(msg))
def cases():
    cc=freeze.cases()
    return [dict(gbd=x["gbd"],sha256=x["sha256"],
       path=freeze.ROOT/x["filename"],nvars=x["variables"],
       nclauses=x["clauses"],prior_status=x["status"]) for x in cc]
def c10_choice(n,m):
    return "kissat" if n<=400 or (m/n)>=200 or (n>=25000 and (m/n)<=2) else "cadical"
def c11_choice(n,m):
    if 200<=n<=1500 and (m/n)<=60:return "cadical_noelim"
    return c10_choice(n,m)
def command(which,src):
    p=str(src.resolve())
    if which=="cadical":return ["/usr/bin/cadical",p]
    if which=="cadical_noelim":return ["/usr/bin/cadical","--no-elim",p]
    if which=="kissat":
        return [str(pathlib.Path("built/bin/kissat_4_0_4").resolve()),p]
    raise RuntimeError("unknown standard solver")
def locked():
    a=json.loads(freeze.PREVC11A.read_text())
    need(a["protocol"]==freeze.C11A_PROTO and
         a["policy_frozen_for_C11b"]==C11_RULE and
         a["source_SHA_count"]==39 and a["no_auto_promotion"],
         "C11a 39 SHA development policy changed after source freeze")
def smoke():
    locked()
    cc=cases()
    OUT.mkdir(exist_ok=True)
    tiny=OUT/"smoke.cnf"
    tiny.write_text("p cnf 4 4\n1 2 0\n-1 2 0\n2 3 0\n4 0\n")
    for x in ("cadical","cadical_noelim","kissat"):
        p=subprocess.run(command(x,tiny),capture_output=True,
                        text=True,errors="replace",check=False,timeout=10)
        status,model=ref.external_parse(p)
        need(status=="SAT","baseline solver missing "+x)
        cms.verify_model(tiny,model)
    need(len(cc)>=freeze.MIN_READY,"source freeze missing")
    need(c11_choice(600,5405)=="cadical_noelim" and
         c11_choice(250,12250)=="cadical_noelim" and
         c11_choice(324,313486)=="kissat" and
         c11_choice(41734,62284)=="kissat" and
         c11_choice(5892,20000)=="cadical" and
         c11_choice(30000,30000)=="kissat",
         "source-only structural policy drift")
    print("C11B_STANDARD_BACKENDS_THREE_WAY_SOURCE_RULE_SMOKE_PASS",flush=True)
def trial(c,rep,arm):
    need(rep in range(REPS) and arm in ARMS,
         "unsupported repetition or arm")
    src=c["path"]
    need(freeze.digest(src)==c["sha256"],"original CNF SHA changed")
    start=time.perf_counter()
    if arm in ("c10_old","c11_triple"):
        # Header parsing is part of E2E wall time, not a free prerequisite.
        n,m=old.source_header(src)
        need(n==c["nvars"] and m==c["nclauses"],"CNF source mutated")
        route=c10_choice(n,m) if arm=="c10_old" else c11_choice(n,m)
    else:route=arm
    cmd=command(route,src)
    p=None
    remaining=CAP-(time.perf_counter()-start)
    if remaining>0:
        try:p=subprocess.run(cmd,capture_output=True,text=True,errors="replace",
                            check=False,timeout=remaining)
        except subprocess.TimeoutExpired:pass
    elapsed=time.perf_counter()-start
    status="TIMEOUT";verified=False
    if p is not None:
        status,model=ref.external_parse(p)
        need(status in ("SAT","UNSAT","UNKNOWN","TIMEOUT"),
             "unregistered solver result")
        if status=="SAT":
            cms.verify_model(src,model)
            verified=True
        if status in ("SAT","UNSAT"):
            need(status==c["prior_status"],
                 "published SAT/UNSAT reference disagreement")
    if elapsed>CAP or status not in ("SAT","UNSAT"):
        status="TIMEOUT";verified=False
    return dict(protocol=PROTO,gbd=c["gbd"],sha256=c["sha256"],
        vars=c["nvars"],clauses=c["nclauses"],reference=c["prior_status"],
        rep=rep,arm=arm,routed_backend=route,cap_s=CAP,
        status=status,original_SAT_witness_checked=verified,
        UNSAT_without_independent_LRAT=(status=="UNSAT"),
        original_SHA_unchanged=True,
        source_selection_overhead_charged=arm in ("c10_old","c11_triple"),
        wall_s=round(elapsed,6),
        PAR2_s=round(elapsed if status in ("SAT","UNSAT") else 2*CAP,6),
        independent_external_seed=False,
        build_sha=os.environ.get("GITHUB_SHA","local"))
def shard(i):
    need(i in range(SHARDS),"unknown parallel shard")
    cc=cases()
    subset=[c for j,c in enumerate(cc) if j%SHARDS==i]
    OUT.mkdir(exist_ok=True)
    rows=[]
    (OUT/("shard-%d.json"%i)).write_text("[]\n")
    for c in subset:
        for rep in range(REPS):
            order=list(ARMS)
            random.Random(PROTO+"|"+c["sha256"]+"|"+str(rep)).shuffle(order)
            for mode in order:
                row=trial(c,rep,mode)
                rows.append(row)
                (OUT/("shard-%d.json"%i)).write_text(
                    json.dumps(rows,sort_keys=True,indent=2)+"\n")
                print("C11B_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==len(subset)*REPS*len(ARMS),
         "partial source-matched PAR2 benchmark")
    print("C11B_SHARD_PASS",i,len(rows),flush=True)
def audit():
    cc=cases()
    bysha={x["sha256"]:x for x in cc}
    rows=[]
    for i in range(SHARDS):
        p=OUT/("shard-%d.json"%i)
        need(p.is_file(),"missing shard")
        part=json.loads(p.read_text())
        expect=len([c for j,c in enumerate(cc) if j%SHARDS==i])*REPS*len(ARMS)
        need(len(part)==expect,"partial shard")
        rows+=part
    need(len(rows)==len(cc)*REPS*len(ARMS),
         "missing all 4 arm x 2 repeat E2E trials")
    keys=collections.defaultdict(set)
    for r in rows:
        c=bysha.get(r["sha256"])
        need(c is not None and c["gbd"]==r["gbd"] and r["protocol"]==PROTO
             and r["arm"] in ARMS and r["rep"] in range(REPS)
             and r["cap_s"]==CAP and r["vars"]==c["nvars"],
             "original source or protocol drift")
        expected=c10_choice(c["nvars"],c["nclauses"]) if r["arm"]=="c10_old" \
           else c11_choice(c["nvars"],c["nclauses"]) if r["arm"]=="c11_triple" else r["arm"]
        need(r["routed_backend"]==expected and
             r["status"] in ("SAT","UNSAT","TIMEOUT"),
             "invalid routing or terminal")
        if r["arm"] in ("c10_old","c11_triple"):
            need(r["source_selection_overhead_charged"],
                 "free structural scan not allowed")
        if r["status"]=="TIMEOUT":
            need(r["PAR2_s"]==CAP*2 and
                 not r["original_SAT_witness_checked"],"bad timeout penalty")
        else:
            need(r["status"]==c["prior_status"] and
                 abs(r["PAR2_s"]-r["wall_s"])<0.000002,
                 "official reference disagreement or incorrect PAR2")
            if r["status"]=="SAT":
                need(r["original_SAT_witness_checked"],
                     "SAT witness not checked against original SHA")
        key=(r["sha256"],r["rep"])
        need(r["arm"] not in keys[key],"duplicate paired mode")
        keys[key].add(r["arm"])
    need(len(keys)==len(cc)*REPS and all(v==set(ARMS) for v in keys.values()),
         "source-repetition paired matrix incomplete")
    scores={}
    for arm in ARMS:
        aa=[r for r in rows if r["arm"]==arm]
        scores[arm]=dict(trials=len(aa),
             solved=sum(x["status"]!="TIMEOUT" for x in aa),
             SAT=sum(x["status"]=="SAT" for x in aa),
             UNSAT_prior_agreement_without_LRAT=sum(x["status"]=="UNSAT" for x in aa),
             timeouts=sum(x["status"]=="TIMEOUT" for x in aa),
             PAR2_s=round(sum(x["PAR2_s"] for x in aa),6),
             total_measured_wall_s=round(sum(x["wall_s"] for x in aa),6))
    kiss=scores["kissat"]["PAR2_s"]
    for arm in scores:scores[arm]["PAR2_speedup_vs_Kissat_x"]=round(
        kiss/scores[arm]["PAR2_s"],6)
    per=[]
    for c in cc:
        sub={}
        for arm in ARMS:
            xs=[r for r in rows if r["sha256"]==c["sha256"] and r["arm"]==arm]
            sub[arm]=dict(solved=sum(x["status"]!="TIMEOUT" for x in xs),
                 PAR2_s=round(sum(x["PAR2_s"] for x in xs),6),
                 individual=[dict(rep=x["rep"],status=x["status"],wall_s=x["wall_s"])
                      for x in sorted(xs,key=lambda z:z["rep"])])
        per.append(dict(gbd=c["gbd"],sha256=c["sha256"],
            nvars=c["nvars"],nclauses=c["nclauses"],reference=c["prior_status"],
            density=c["nclauses"]/c["nvars"],
            selected_backend=c11_choice(c["nvars"],c["nclauses"]),
            difference_vs_Kissat_s=round(
                 sub["c11_triple"]["PAR2_s"]-sub["kissat"]["PAR2_s"],6),
            modes=sub))
    regrets=[x["difference_vs_Kissat_s"] for x in per]
    savings=[-x for x in regrets if x<-.02]
    report=dict(protocol=PROTO,
       original_source_count=len(cc),
       end_to_end_real_trials=len(rows),
       source_origin_run="C10b original source SHA-only freeze before all solver tests",
       source_status_balance=dict(collections.Counter(x["prior_status"] for x in cc)),
       original_SHA_verified=True,
       portfolio_rule_frozen_before_source_selection=C11_RULE,
       external_repeats_are_not_independent_seeds=True,
       UNSAT_no_independent_LRAT=True,
       no_auto_promotion=True,
       cap_s=CAP,repeats=REPS,
       selected_CaDiCaL_count=sum(x["selected_backend"]=="cadical" for x in per),
       selected_Kissat_count=sum(x["selected_backend"]=="kissat" for x in per),
       selected_CaDiCaL_noelim_count=sum(x["selected_backend"]=="cadical_noelim" for x in per),
       gained_case_count=sum(x<-.02 for x in regrets),
       regressed_case_count=sum(x>.02 for x in regrets),
       max_regression_s=round(max([0]+regrets),6),
       max_case_gain_s=round(max([0]+savings),6),
       total_gain_vs_Kissat_s=round(kiss-scores["c11_triple"]["PAR2_s"],6),
       total_gain_excluding_largest_single_gain_s=round(
           kiss-scores["c10_structural"]["PAR2_s"]-max([0]+savings),6),
       scores=scores,per_source=per)
    OUT.mkdir(exist_ok=True)
    (OUT/"report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("C11B_FINAL",json.dumps({k:v for k,v in report.items()
            if k!="per_source"},sort_keys=True),flush=True)
    for x in per:
        print("C11B_CASE",json.dumps(x,sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("verify","smoke","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="verify":
        locked();print("C11B_FROZEN_SOURCE_RULE_PASS",len(cases()),flush=True)
    elif a.action=="smoke":smoke()
    elif a.action=="shard":shard(a.shard)
    else:audit()
