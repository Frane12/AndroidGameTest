#!/usr/bin/env python3
"""X9: source-only X8/C13/C14 route; 12 SHA-disjoint-from-C13 official2026 CNFs.

Sources previously used in C14NV, hence HISTORICAL, not fully blind or an
official competition ranking. Nine paired 25s E2E arms: native original,
two X8 transformations, two CaDiCaL switches, Kissat, default CaDiCaL,
X9 selector and no-X8 ablation. The selector never probes a solver. All routing
time and transformations fall within each 25-second wall-clock cap.
"""
from __future__ import annotations
import argparse, collections, json, os, pathlib, random, shutil, subprocess, time
import drnas_x8_worldcup_mid16 as w

w.PROTO="DRNAS-X9-C14NV12-SHA-STRUCTURAL-GATE-9ARMS-2SEEDS-25S-v1"
w.SRC=pathlib.Path("x9_sources")
w.OUT=pathlib.Path("x9_out")
w.X8_BINARY=pathlib.Path("x9_bin/mre_x8/bin/native")
w.KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
w.CADICAL=pathlib.Path("c8c/bin/plain")
w.CAP=25.0
w.TARGET=w.MIN_READY=12
w.SHARDS=6
w.REPS=2
w.ARMS=("kissat_404","cadical_173","cadical_noelim","cadical_novivify",
        "cms_orig","x8_shifted","x8_spread100","x9_selective","x9_no_x8")
C14_SRC=pathlib.Path("c14nv_sources")
C14_SHA="73bd88baae02e65de28aa541e8e46e73ecbe2be89f0698ac2d0afaa9a7cf6712"
C14_PROTO="DRNAS-C14NV-H2-NEW12-5ARM-2REP-30S-v1"
C13_SHA="e1563f7acb67bbbca4a8ff7d982e9c7e25c59e3a8b1941e6d660ae6cf1be45f3"
C13_MAN=pathlib.Path("x9_prior_c13/c13_sources/manifest.json")
CMS=x8_binary=w.X8_BINARY
C14_NO_VIVIFY=pathlib.Path("c8c/bin/instrumented")
KNOWN_X8_GBDS=("220bb8aa093e502c47afcdac3140d67c",
                "fdfcd52a21824b7181d66672f283ba04",
                "695d8f6a2ee6e89e5a4f5d94abc3aca6",
                "578f9377bfbfcc6ea3a18eb630667956")

# Freeze thresholds before any X9 time measurements. Not fitted on this cohort.
RULE=dict(
  parse_only_if_bytes_le=1_000_000,
  parse_only_if_vars_le=700,
  parse_only_if_clauses_le=12_000,
  shifted_duplicates_min=50,shifted_duplicates_max=4000,
  shifted_duplicate_ratio_min=0.02,shifted_duplicate_ratio_max=0.40,
  noelim_variables_min=200,noelim_variables_max=1500,noelim_max_density=60,
  novivify_max_variables=1800,novivify_min_density=60,
  novivify_max_density=130,novivify_max_dup_ratio=0.10,
  fallback="kissat_404"
)

def need(ok,msg):w.need(ok,msg)
def save(p,data):w.save(p,data)
def eligible_for_x8(n,m,size):
    return n<=700 and m<=12_000 and size<=1_000_000
def shape(p,n,m,size):
    """Cheap header geometry first; only parse bounded-small CNFs for duplication."""
    feat=dict(nvars=n,nclauses=m,bytes=size,density=round(m/n,9),
              duplicate_rows=None,duplicate_fraction=None,full_scan=False)
    if eligible_for_x8(n,m,size):
        nv,clauses=w.x2.parse(p)
        need(nv==n and len(clauses)==m,"DIMACS scan geometry inconsistent")
        keys=(w.x4.x3.key(clause) for clause in clauses)
        d=m-len(set(keys))
        feat.update(duplicate_rows=d,duplicate_fraction=round(d/m,9),full_scan=True)
    return feat
def policy(feat,allow_x8):
    n=feat["nvars"];m=feat["nclauses"];den=feat["density"]
    d=feat["duplicate_rows"];ratio=feat["duplicate_fraction"]
    if (allow_x8 and feat["full_scan"] and d is not None and
        50<=d<=4000 and 0.02<=ratio<=0.40):
        return "x8_shifted","bounded_shift_50to4000"
    if 200<=n<=1500 and den<=60:
        return "cadical_noelim","C13_C14_noelim_shape"
    if n<=1800 and 60<den<=130 and (ratio is None or ratio<0.10):
        return "cadical_novivify","C14_no_vivify_shape"
    return "kissat_404","Kissat_source_only_fallback"

def freeze():
    need(C14_SRC.joinpath("manifest.json").is_file() and
         w.digest(C14_SRC/"manifest.json")==C14_SHA,"frozen C14NV source manifest drift")
    need(C13_MAN.is_file() and w.digest(C13_MAN)==C13_SHA,
         "historical C13 exclusion manifest unavailable")
    raw=json.loads((C14_SRC/"manifest.json").read_text())
    old=json.loads(C13_MAN.read_text())
    need(raw["protocol"]==C14_PROTO and len(raw["cases"])==12 and len(old["cases"])==12,
         "unexpected source manif/protocol")
    oldgbd={c["gbd"] for c in old["cases"]}|set(KNOWN_X8_GBDS)
    oldsha={c["sha256"] for c in old["cases"]}
    w.SRC.mkdir(parents=True,exist_ok=True)
    selected=[]
    for c in raw["cases"]:
        need(c["gbd"] not in oldgbd and c["sha256"] not in oldsha,
             "C14NV source overlaps previously used C13/X8")
        p=C14_SRC/c["filename"]
        need(p.exists() and p.stat().st_size==c["bytes"] and
             w.digest(p)==c["sha256"],"original C14NV source SHA changed")
        dest=w.SRC/c["filename"]
        shutil.copyfile(p,dest)
        f=shape(dest,c["nvars"],c["nclauses"],c["bytes"])
        a,reason=policy(f,True)
        b,_=policy(f,False)
        row=dict(gbd=c["gbd"],sha256=c["sha256"],filename=c["filename"],
                 bytes=c["bytes"],nvars=c["nvars"],nclauses=c["nclauses"],
                 official_ca3_s=None,reference=c["status"],features=f,
                 x9_route=a,x9_reason=reason,x9_no_x8_route=b,
                 source_already_used_in_C14NV=True)
        selected.append(row)
        print("X9_SOURCE",json.dumps({k:row[k] for k in
              ("gbd","reference","nvars","nclauses","features","x9_route","x9_reason")},sort_keys=True),flush=True)
    need(len(selected)==12 and len({r["sha256"] for r in selected})==12,
         "duplicate source SHA")
    need(collections.Counter(r["reference"] for r in selected)=={"SAT":6,"UNSAT":6},
         "6/6 official SAT/UNSAT status quota missing")
    m=dict(protocol=w.PROTO,source_count=12,target=12,seed_repeats=w.REPS,
           cap_s=w.CAP,arms=list(w.ARMS),cases=selected,
           frozen_rule=RULE,original_C14NV_manifest_sha256=C14_SHA,
           previous_C14NV_outcomes_exist=True,
           previous_C13_outcomes_exist=True,previous_X8_WC2_outcomes_exist=True,
           SHA_disjoint_from_C13_and_X8_development=True,
           historical_NOT_fully_blind=True,not_official_ranking=True,
           source_frozen_before_local_solver=True,
           no_in_solver_probe=True,no_auto_promotion=True,
           SAT_original_witness_check=True,UNSAT_independent_LRAT=False)
    save(w.SRC/"manifest.json",m)
    (w.SRC/"source.sha256").write_text("".join(
         r["sha256"]+"  "+r["filename"]+"\n" for r in selected))
    print("X9_FROZEN",json.dumps(dict(sources=12,sha=w.digest(w.SRC/"manifest.json"),
          routes=dict(collections.Counter(x["x9_route"] for x in selected))),sort_keys=True),flush=True)

def cases():
    arr=w.cases()
    need(len(arr)==12,"X9 source count")
    for c in arr:
        a,_=policy(c["features"],True)
        b,_=policy(c["features"],False)
        need(a==c["x9_route"] and b==c["x9_no_x8_route"],
             "frozen selector result drift")
    return arr

def run(c,arm,rep):
    original=w.SRC/c["filename"]
    need(w.digest(original)==c["sha256"],"source SHA changed")
    start=time.perf_counter()
    route=arm
    route_reason="fixed_arm"
    feat=None
    if arm in ("x9_selective","x9_no_x8"):
        feat=shape(original,c["nvars"],c["nclauses"],c["bytes"])
        need(feat==c["features"],"precommitted selector input drift")
        route,route_reason=policy(feat,arm=="x9_selective")
        expected=c["x9_route"] if arm=="x9_selective" else c["x9_no_x8_route"]
        need(route==expected,"dynamic route disagrees with frozen choice")
    path=original
    moved=0
    if route in ("x8_shifted","x8_spread100"):
        path,moved=w.transformed(c,route,rep)
    # all selector decisions and transforms are inside the same E2E 25s cap
    if route=="kissat_404":
        cmd=[str(w.KISSAT.resolve()),str(original.resolve())]
    elif route in ("cadical_173","cadical_noelim"):
        cmd=[str(w.CADICAL.resolve())]
        if route=="cadical_noelim":cmd+=["--no-elim"]
        cmd+=[str(original.resolve())]
    elif route=="cadical_novivify":
        cmd=[str(C14_NO_VIVIFY.resolve()),"--no-vivify",str(original.resolve())]
    else:
        need(route in ("cms_orig","x8_shifted","x8_spread100"),
             "unknown backend route")
        cmd=[str(w.X8_BINARY.resolve()),str(path.resolve()),"x_native",str(w.seed(c,rep))]
    prep=time.perf_counter()-start
    env=os.environ.copy()
    for key in ("DRNAS_MAX_CONFLICTS","DRNAS_X7_TRACE","DRNAS_X8_TRACE",
                "DRNAS_C8I_EARLY_GATE16","DRNAS_C8I_GATE_TRACE"):
        env.pop(key,None)
    proc=None
    remaining=w.CAP-(time.perf_counter()-start)
    if remaining>0:
        try:
            proc=subprocess.run(cmd,env=env,capture_output=True,text=True,
                    errors="replace",timeout=remaining,check=False)
        except subprocess.TimeoutExpired:
            pass
    elapsed=time.perf_counter()-start
    state="TIMEOUT";verified=False;native=None
    if proc is not None:
        if route in ("kissat_404","cadical_173","cadical_noelim","cadical_novivify"):
            need(proc.returncode in (10,20),"reference backend exit "+str(proc.returncode))
            state,model=w.ref.external_parse(proc)
        else:
            need(proc.returncode==0,"X8 CMS native crash: "+(proc.stderr or "")[-400:])
            state,model,native=w.base.cms.parsed_native(proc.stdout)
            gate=w.base.parse_gate(proc.stdout,"x_native")
            need(not gate["applied"] and gate["clauses_removed"]==0,
                 "native gate changed original SAT formula")
        need(state in ("SAT","UNSAT","UNKNOWN","TIMEOUT","BUDGET"),"invalid result")
        if state=="SAT":
            w.cms.verify_model(original,model);verified=True
        if state in ("SAT","UNSAT"):
            need(state==c["reference"],"published official2026 status disagreement")
    if elapsed>w.CAP or state not in ("SAT","UNSAT"):
        state="TIMEOUT";verified=False
    return dict(protocol=w.PROTO,gbd=c["gbd"],sha256=c["sha256"],
                arm=arm,route=route,reason=route_reason,rep=rep,seed=w.seed(c,rep),
                original_sha256_verified=True,cap_s=w.CAP,source_reference=c["reference"],
                status=state,PAR2_s=round(elapsed if state!="TIMEOUT" else 2*w.CAP,6),
                wall_s=round(elapsed,6),prep_s=round(prep,6),
                SAT_original_witness_verified=verified,UNSAT_independent_LRAT=False,
                source_historical_C14NV=True,router_no_probe=True,
                selector_features=feat,shifted_duplicate_rows=moved if route.startswith("x8_") else None,
                native_stats=native)

def shard(index):
    need(index in range(w.SHARDS),"invalid shard index")
    cs=[c for i,c in enumerate(cases()) if i%w.SHARDS==index]
    need(len(cs)==2,"expected two originals per shard")
    rows=[]
    for c in cs:
        for rep in range(w.REPS):
            order=list(w.ARMS)
            random.Random(w.seed(c,rep)).shuffle(order)
            for arm in order:
                row=run(c,arm,rep)
                rows.append(row)
                save(w.OUT/f"shard-{index}.json",rows)
                print("X9_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==2*w.REPS*len(w.ARMS),"incomplete paired X9 shard")
    print("X9_SHARD_PASS",index,len(rows),flush=True)

def audit():
    cs=cases();lookup={c["sha256"]:c for c in cs};rows=[]
    for idx in range(w.SHARDS):
        part=json.loads((w.OUT/f"shard-{idx}.json").read_text())
        need(len(part)==2*w.REPS*len(w.ARMS),"missing trial in shard")
        rows.extend(part)
    expected={(c["sha256"],rep,arm) for c in cs for rep in range(w.REPS) for arm in w.ARMS}
    got={(r["sha256"],r["rep"],r["arm"]) for r in rows}
    need(len(rows)==len(got)==len(expected) and got==expected,
         "unpaired original SHA/rep/arm key")
    scores={}
    for r in rows:
        c=lookup[r["sha256"]]
        need(r["gbd"]==c["gbd"] and r["protocol"]==w.PROTO and
             r["seed"]==w.seed(c,r["rep"]) and r["cap_s"]==w.CAP,
             "trial source/protocol/seed mismatch")
        expected_route=c["x9_route"] if r["arm"]=="x9_selective" else (
            c["x9_no_x8_route"] if r["arm"]=="x9_no_x8" else r["arm"])
        need(r["route"]==expected_route,"selector route changed after freezing")
        if r["status"]=="TIMEOUT":
            need(r["PAR2_s"]==2*w.CAP,"invalid PAR2 timeout")
        else:
            need(r["status"]==c["reference"] and
                 abs(r["PAR2_s"]-r["wall_s"])<=0.000002,
                 "incorrect or unverified terminal status")
            if r["status"]=="SAT":
                need(r["SAT_original_witness_verified"],"SAT model not independently verified")
    for arm in w.ARMS:
        x=[r for r in rows if r["arm"]==arm]
        scores[arm]=dict(n=len(x),solved=sum(r["status"]!="TIMEOUT" for r in x),
             sat=sum(r["status"]=="SAT" for r in x),
             unsat_reference_without_LRAT=sum(r["status"]=="UNSAT" for r in x),
             timeouts=sum(r["status"]=="TIMEOUT" for r in x),
             PAR2_s=round(sum(r["PAR2_s"] for r in x),6))
    baseline=scores["kissat_404"]["PAR2_s"]
    for arm in w.ARMS:
        scores[arm]["speedup_vs_kissat_x"]=round(baseline/scores[arm]["PAR2_s"],6)
    individual=[]
    for c in cs:
        x=[r for r in rows if r["sha256"]==c["sha256"]]
        individual.append(dict(gbd=c["gbd"],sha256=c["sha256"],reference=c["reference"],
           features=c["features"],frozen_route=c["x9_route"],
           no_x8_route=c["x9_no_x8_route"],
           par2={a:round(sum(r["PAR2_s"] for r in x if r["arm"]==a),6) for a in w.ARMS},
           solved={a:sum(r["status"]!="TIMEOUT" for r in x if r["arm"]==a) for a in w.ARMS}))
    def paired_comp(a,b):
        won=lost=tied=0
        for c in cs:
            for rep in range(w.REPS):
                x=next(r["PAR2_s"] for r in rows if r["sha256"]==c["sha256"] and r["rep"]==rep and r["arm"]==a)
                y=next(r["PAR2_s"] for r in rows if r["sha256"]==c["sha256"] and r["rep"]==rep and r["arm"]==b)
                if x<y-1e-5:won+=1
                elif x>y+1e-5:lost+=1
                else:tied+=1
        return dict(wins=won,losses=lost,ties=tied)
    pairs={a:paired_comp("x9_selective",a) for a in
           ("kissat_404","cadical_173","cms_orig","x9_no_x8","x8_shifted","x8_spread100")}
    report=dict(protocol=w.PROTO,source_count=12,seed_count=w.REPS,
         n_trials=len(rows),cap_s=w.CAP,score=scores,paired_selector=pairs,
         per_source=individual,route_counts=dict(collections.Counter(c["x9_route"] for c in cs)),
         source_historical_C14NV_not_fully_blind=True,
         indexed_source_disjoint_from_C13_and_X8_development=True,
         actual_E2E_including_selector_and_reorder=True,
         SAT_original_witnesses_checked=True,UNSAT_independent_LRAT=False,
         no_auto_promotion=True,not_official_competition=True)
    save(w.OUT/"report.json",report)
    print("X9_FINAL",json.dumps({k:v for k,v in report.items() if k!="per_source"},sort_keys=True),flush=True)

def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        p=pathlib.Path(tmp)/"a.cnf"
        clauses=[(1,-2),(1,-2),(-1,2),(-1,2),(3,),(3,)]
        w.x2.write(p,3,clauses)
        a=shape(p,3,len(clauses),p.stat().st_size)
        need(a["duplicate_rows"]==3,"canonical duplicate keys wrong")
        need(policy(a,True)[0]==policy(a,False)[0],"tiny ineligible x8 gate failed")
        feat=dict(nvars=550,nclauses=6000,bytes=110000,density=10,
            duplicate_rows=1000,duplicate_fraction=1000/6000,full_scan=True)
        need(policy(feat,True)[0]=="x8_shifted" and
             policy(feat,False)[0]=="cadical_noelim","selector ablation sanity failed")
    print("X9_SELFTEST_PASS",flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    if a.action=="selftest":selftest()
    elif a.action=="freeze":freeze()
    elif a.action=="verify":
        z=cases();print("X9_VERIFY_PASS",len(z),flush=True)
    elif a.action=="shard":shard(a.shard)
    else:audit()
