#!/usr/bin/env python3
"""DRNAS C9b — SOURCE-FROZEN official SAT2026 BVE gate prospective check.

Freeze a single earlier C9 LOFO rule: nvars<=1500 -> CaDiCaL 1.7.3 --no-elim,
else CaDiCaL 1.7.3 default. Use independent X5 SAT2026 source-only manifest
frozen BEFORE C9b performance tests, which has 3 source SHA (1 SAT 2 UNSAT).
Four arms: CaDiCaL default, CaDiCaL no elimination, Kissat 4.0.4, and actual
C9 source-header gate; 3 repeats x 3 SHAs x 4 arms = 36 full E2E attempts,
25s cap PAR2. SAT witnesses are verified on exact source CNF; UNSAT is
published prior-reference agreement without independent LRAT.
No independent seed control for external binaries, so repetitions measure
wall noise only. This is a prospective check of C9 (source group holdout
w.r.t. its 19 SHA) but NOT a claim of globally blind/competition result.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,subprocess,time
import mre11b_prospective_benchmark as ref
import r195_native_cms_benchmark as cms

PROTO="DRNAS-C9B-OFFICIAL26-3SHA-4ARMS-3REPS-25S-E2E-PAR2-v1"
ROOT=pathlib.Path("c9b_out")
SRC=pathlib.Path("mre_x5_blind")
C9=pathlib.Path("c9_reference")
ARM=("cadical","cadical_noelim","kissat","c9_route")
CAP=25.0
REPS=3
EXPECTED_X5_PROTO="DRNAS-MRE-X5-SAT2026-PROSPECTIVE-SHIFTED-SPREAD-3ARMS-4SEED-18S-v1"
TRAIN_PROTO="DRNAS-C9-LOFO-19SHA-SOURCE-ONLY-STUMP-6SOLVERS-NO-PILOT-v1"
MODE_SMALL="cadical_noelim"
SMALL_NVAR=1500

def need(ok,msg):
    if not ok:raise RuntimeError("C9B_FAIL_CLOSED "+str(msg))
def digest(path):
    h=hashlib.sha256()
    with pathlib.Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):h.update(b)
    return h.hexdigest()
def source_header(src):
    with pathlib.Path(src).open("rt",encoding="ascii",errors="replace") as f:
        for line in f:
            stripped=line.strip()
            if not stripped or stripped.startswith("c"):continue
            x=stripped.split()
            need(len(x)==4 and x[:2]==["p","cnf"],"DIMACS source header invalid")
            n=int(x[2]);m=int(x[3])
            need(n>0 and m>0,"empty CNF source")
            return n,m
    raise RuntimeError("C9B_FAIL_CLOSED missing CNF header")
def rule_locked():
    a=C9/"report.json"
    need(a.is_file(),"original previous C9 LOFO audited rule report missing")
    report=json.loads(a.read_text())
    need(report["protocol"]==TRAIN_PROTO and report["source_SHA_count"]==19
         and report["C8D_total_real_E2E_trials"]==380 and
         report["no_auto_promotion"],
         "C9 historical LOFO audit not valid")
    choice=report["final_all19_candidate_rule_for_future_prospective_test"]
    need(choice["rule"]==["nvars",SMALL_NVAR,"le"] and
         choice["mode"]==MODE_SMALL,
         "C9 rule changed after looking at official26 sources")
    return report
def cases():
    report=rule_locked()
    manifest=json.loads((SRC/"manifest.json").read_text())
    need(manifest["protocol"]==EXPECTED_X5_PROTO and
         manifest["original_SHA_frozen_before_any_solver"] and
         manifest["year"]==2026,"X5 frozen official SAT2026 source prior lock invalid")
    a=manifest["cases"]
    need(len(a)==3 and manifest["original_source_count"]==3,
         "expected three frozen official26 originals")
    old={x["source_sha256"] for x in report["folds"]}
    cases=[]
    for x in a:
        src=SRC/x["filename"]
        need(src.is_file() and digest(src)==x["sha256"],
             "source original SHA changed")
        need(x["sha256"] not in old,
             "C9 training SHA overlap: no prospective claim")
        n,m=source_header(src)
        need(n==x["variables"] and m==x["clauses"],
             "source header geometry differs from frozen manifest")
        need(x["published_status"] in ("SAT","UNSAT"),
             "original source status not official-verified")
        cases.append(dict(gbd=x["gbd"],sha256=x["sha256"],path=src,
            vars=n,clauses=m,reference_status=x["published_status"]))
    need(len({x["sha256"] for x in cases})==3,
         "duplicate official source SHA")
    return cases
def select(n):
    return MODE_SMALL if n<=SMALL_NVAR else "cadical"
def cli(mode,src):
    if mode=="cadical":return ["/usr/bin/cadical",str(src.resolve())]
    if mode=="cadical_noelim":
        return ["/usr/bin/cadical","--no-elim",str(src.resolve())]
    if mode=="kissat":
        return [str(pathlib.Path("built/bin/kissat_4_0_4").resolve()),
                str(src.resolve())]
    raise RuntimeError("unregistered solver arm")
def smoke():
    ROOT.mkdir(exist_ok=True)
    tiny=ROOT/"c9b-sat-smoke.cnf"
    tiny.write_text("p cnf 4 4\n1 2 0\n-1 2 0\n2 3 0\n4 0\n")
    for m in ("cadical","cadical_noelim","kissat"):
        p=subprocess.run(cli(m,tiny),capture_output=True,text=True,check=False,
                         timeout=10)
        status,model=ref.external_parse(p)
        need(status=="SAT","standard binary or BVE option invalid "+m)
        cms.verify_model(tiny,model)
    r=rule_locked()
    orig=cases()
    need(sum(c["vars"]<=SMALL_NVAR for c in orig)==1,
         "prospective cohort lacks one positive gate and two no-route controls")
    print("C9B_FROZEN_RULE_AND_THREE_REFERENCE_SOLVERS_SMOKE_PASS",
        json.dumps(dict(training_sources=19,new_sources=len(orig),
         activated=[c["gbd"] for c in orig if c["vars"]<=SMALL_NVAR],
         rule=r["final_all19_candidate_rule_for_future_prospective_test"]),
         sort_keys=True),flush=True)
def trial(c,rep,arm):
    need(arm in ARM and rep in range(REPS),"arm/repetition not preregistered")
    src=c["path"]
    need(digest(src)==c["sha256"],"original frozen SHA changed")
    t=time.perf_counter()
    n_header=None
    if arm=="c9_route":
        n_header,_=source_header(src) # charged to real end-to-end time
        chosen=select(n_header)
    else:chosen=arm
    cmd=cli(chosen,src)
    remaining=CAP-(time.perf_counter()-t)
    p=None
    if remaining>0:
        try:p=subprocess.run(cmd,capture_output=True,text=True,
              errors="replace",timeout=remaining,check=False)
        except subprocess.TimeoutExpired:pass
    elapsed=time.perf_counter()-t
    status="TIMEOUT";verified=False
    if p is not None:
        status,model=ref.external_parse(p)
        need(status in ("SAT","UNSAT","UNKNOWN"),"unknown CLI result")
        if status=="SAT":
            cms.verify_model(src,model);verified=True
        if status in ("SAT","UNSAT"):
            need(status==c["reference_status"],
                 "published reference status contradiction")
    if elapsed>CAP or status not in ("SAT","UNSAT"):
        status="TIMEOUT";verified=False
    return dict(protocol=PROTO,gbd=c["gbd"],source_sha256=c["sha256"],
        source_variables=c["vars"],source_clauses=c["clauses"],
        reference_status=c["reference_status"],rep=rep,arm=arm,
        selected_backend=chosen,independent_external_seed=False,
        route_header_charged=(arm=="c9_route"),cap_s=CAP,
        status=status,original_SAT_witness_verified=verified,
        independent_UNSAT_LRAT=False,wall_s=round(elapsed,6),
        PAR2_s=round(elapsed if status in ("SAT","UNSAT") else 2*CAP,6),
        original_SHA_untouched=True,build_sha=os.getenv("GITHUB_SHA","local"))
def shard(i):
    cc=cases()
    need(0<=i<len(cc),"invalid freeze shard")
    c=cc[i];ROOT.mkdir(exist_ok=True)
    out=[]
    for rep in range(REPS):
        order=list(ARM)
        random.Random(PROTO+"|"+c["sha256"]+"|"+str(rep)).shuffle(order)
        for arm in order:
            x=trial(c,rep,arm);out.append(x)
            (ROOT/("shard-%d.json"%i)).write_text(
                json.dumps(out,sort_keys=True,indent=2)+"\n")
            print("C9B_TRIAL",json.dumps(x,sort_keys=True),flush=True)
    need(len(out)==len(ARM)*REPS,"original SHA source shard incomplete")
    print("C9B_SHARD_PASS",i,len(out),flush=True)
def audit():
    cc=cases();bysha={x["sha256"]:x for x in cc}
    paired=collections.defaultdict(dict);rows=[]
    for i,c in enumerate(cc):
        f=ROOT/("shard-%d.json"%i)
        need(f.is_file(),"missing source shard")
        p=json.loads(f.read_text())
        need(len(p)==REPS*len(ARM),"partial shard")
        rows+=p
    need(len(rows)==3*REPS*len(ARM),"36 real attempts missing")
    for x in rows:
        c=bysha.get(x["source_sha256"])
        need(c is not None and x["gbd"]==c["gbd"] and x["protocol"]==PROTO
             and x["arm"] in ARM and 0<=x["rep"]<REPS and
             x["cap_s"]==CAP and x["source_variables"]==c["vars"],
             "original source or protocol drift")
        expect=select(c["vars"]) if x["arm"]=="c9_route" else x["arm"]
        need(x["selected_backend"]==expect and
             x["status"] in ("SAT","UNSAT","TIMEOUT"),
             "illegal arm route or terminal")
        need(x["status"]!="SAT" or x["original_SAT_witness_verified"],
             "SAT without independently verified original model")
        need(x["status"]!="TIMEOUT" or
             (x["PAR2_s"]==CAP*2 and not x["original_SAT_witness_verified"]),
             "timeout was not penalized")
        if x["status"] in ("SAT","UNSAT"):
            need(x["status"]==c["reference_status"] and
                 abs(x["PAR2_s"]-x["wall_s"])<=0.000002,
                 "SAT/UNSAT disagreement or incorrect solved PAR2")
        if x["arm"]=="c9_route":need(x["route_header_charged"],
                 "C9 route did not pay source scan")
        k=(x["source_sha256"],x["rep"])
        need(x["arm"] not in paired[k],"duplicate full original SHA mode")
        paired[k][x["arm"]]=x
    need(len(paired)==3*REPS and all(set(v)==set(ARM) for v in paired.values()),
         "missing source/repetition/mode pair")
    scores={}
    for arm in ARM:
        r=[x for x in rows if x["arm"]==arm]
        scores[arm]=dict(trials=len(r),solved=sum(x["status"]!="TIMEOUT" for x in r),
            SAT=sum(x["status"]=="SAT" for x in r),
            UNSAT_agreement_no_LRAT=sum(x["status"]=="UNSAT" for x in r),
            timeouts=sum(x["status"]=="TIMEOUT" for x in r),
            PAR2_s=round(sum(x["PAR2_s"] for x in r),6),
            actual_wall_s=round(sum(x["wall_s"] for x in r),6))
    scores_base=scores["cadical"]["PAR2_s"]
    for arm in ARM:
        scores[arm]["speedup_vs_CaDiCaL_x"]=round(scores_base/scores[arm]["PAR2_s"],6)
    per_source=[]
    for c in cc:
        data={}
        for arm in ARM:
            a=[x for x in rows if x["source_sha256"]==c["sha256"] and x["arm"]==arm]
            data[arm]=dict(solved=sum(x["status"]!="TIMEOUT" for x in a),
                PAR2_s=round(sum(x["PAR2_s"] for x in a),6),
                individual=[dict(rep=x["rep"],status=x["status"],wall_s=x["wall_s"])
                       for x in sorted(a,key=lambda v:v["rep"])])
        per_source.append(dict(gbd=c["gbd"],sha256=c["sha256"],
            vars=c["vars"],reference_status=c["reference_status"],
            actual_rule_activation=select(c["vars"])!= "cadical",
            arms=data))
    report=dict(protocol=PROTO,cohort="Official SAT2026 3 previously X5-frozen SHA; prospective vs C9 19-SHA rule, not globally blind",
       source_count=3,official_year=2026,C9_training_SHA_disjoint=True,
       origin_freeze_run=42527549486,origin_reference_status_not_LRAT=True,
       independently_seeded_external_solves=False,
       real_E2E_PAR2_including_router_header=True,
       cap_s=CAP,repeats=REPS,attempts=len(rows),
       selected_rule="nvars<=1500 => cadical_noelim else cadical",
       original_SAT_models_checked=True,independent_UNSAT_LRAT=False,
       no_auto_promotion=True,scores=scores,per_source=per_source)
    (ROOT/"report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("C9B_FINAL",json.dumps({k:v for k,v in report.items() if k!="per_source"},
            sort_keys=True),flush=True)
    for x in per_source:
        print("C9B_CASE",json.dumps(x,sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("verify","smoke","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="verify":
        print("C9B_SOURCE_ONLY_LOCK_PASS",
            json.dumps([(c["gbd"],c["vars"],c["reference_status"]) for c in cases()]),flush=True)
    elif a.action=="smoke":smoke()
    elif a.action=="shard":shard(a.shard)
    else:audit()
