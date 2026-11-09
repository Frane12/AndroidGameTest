#!/usr/bin/env python3
"""SEED2: prior-SEED1-only trained structural stump, SHA-disjoint prospective holdout.

A/B seeds and original source witness checks match the earlier SEED1 experiment.
All arms use exactly ONE pinned Linux logical CPU per solver. No portfolio.
Training never touches selection/solver outcomes of prospective held-out CNFs.
UNSAT is counted only when original-input Kissat and CaDiCaL independently agree;
that is not an LRAT certificate.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, os, pathlib, random, statistics
import tempfile, time

import drnas_x22_parallel_reducer as x22
import drnas_x16_singlecore_dual as x16
import drnas_x14_adaptive_portfolio as x14
import drnas_seed1_dual_seed_holdout as seed1

ROOT=pathlib.Path("mre_seed2")
SOURCE=ROOT/"cases"
OLD=pathlib.Path("prior_seed1/mre_seed1")
NATIVE=pathlib.Path("mre_x4/bin/native")
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
CAD3=ROOT/"bin/cadical_3_0_1"
PROTO="DRNAS-SEED2-24NEW-SOURCE-STUMP-6ARMS-2REPS-20S-E2E-v1"
SALT="DRNAS-SEED2-20261109-SOURCE-ONLY-TRAIN-PRIOR-v1"
ARMS=("native_a","native_b","native_selected","native_inverse_placebo",
      "kissat_a","cadical3_both")
FEATURES=("vars","clauses","binary_ratio","horn_ratio","bytes")
CAP=20.0
TARGET=24
REPS=2
SHARDS=8
EXPECTED=TARGET*REPS*len(ARMS)

def need(ok,why):
    if not ok:raise RuntimeError("SEED2_FAIL_CLOSED "+str(why))
def digest(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1048576),b""):h.update(b)
    return h.hexdigest()
def save(path,val):
    path=pathlib.Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(val,sort_keys=True,indent=2)+"\n")
def binaries():
    for path in (NATIVE,KISSAT,CAD3):
        need(path.is_file(),"missing binary "+str(path))
    return dict(native=digest(NATIVE),kissat=digest(KISSAT),cadical301=digest(CAD3))
def features(path,n,clauses):
    binary=sum(len(c)==2 for c in clauses)
    horn=sum(sum(lit>0 for lit in c)<=1 for c in clauses)
    return dict(vars=n,clauses=len(clauses),bytes=path.stat().st_size,
                binary_ratio=round(binary/max(1,len(clauses)),6),
                horn_ratio=round(horn/max(1,len(clauses)),6))
def training_data():
    m=json.loads((OLD/"manifest.json").read_text())
    report=json.loads((OLD/"report.json").read_text())
    need(m["protocol"].startswith("DRNAS-SEED1-") and
         report["protocol"]==m["protocol"] and len(m["cases"])==24,
         "prior training cohort mismatch")
    bysha={c["sha256"]:c for c in m["cases"]}
    rr=report["rows"]
    need(len(rr)==336,"prior SEED1 training trial count drift")
    consensus=set()
    for sha in bysha:
        case=[r for r in rr if r["original_sha256"]==sha]
        if any(r["arm"]=="kissat_a" and r["status"]=="UNSAT" for r in case) and \
           any(r["arm"]=="cadical3_both" and r["status"]=="UNSAT" for r in case):
            consensus.add(sha)
    pairs=collections.defaultdict(lambda:{"native_a":{},"native_b":{}})
    for row in rr:
        if row["arm"] not in ("native_a","native_b"):continue
        sha=row["original_sha256"]
        need(sha in bysha and row["rep"] in (0,1),"bad historical paired key")
        need(row["status"]!="SAT" or row["SAT_original_witness_verified"],
             "historical model not verified")
        ok=row["status"]=="SAT" or (row["status"]=="UNSAT" and sha in consensus)
        need(row["rep"] not in pairs[sha][row["arm"]],"duplicate historical key")
        pairs[sha][row["arm"]][row["rep"]]=row["E2E_s"] if ok else 2*CAP
    samples=[]
    for sha,c in bysha.items():
        pair=pairs[sha]
        need(all(set(pair[a])=={0,1} for a in ("native_a","native_b")),
             "incomplete historical A/B")
        need(all(z in c for z in FEATURES),"prior source signals missing")
        score_a=sum(pair["native_a"].values())
        score_b=sum(pair["native_b"].values())
        samples.append(dict(sha=sha,feature={k:c[k] for k in FEATURES},
                            par2_a=score_a,par2_b=score_b))
    need(len(samples)==24,"training sources drift")
    return samples,m,report

def pick(model,feat):
    if model["type"]=="constant":return model["seed"]
    left=feat[model["feature"]]<=model["threshold"]
    return model["left_seed"] if left else model["right_seed"]
def loss(model, samples):
    return sum(p["par2_a"] if pick(model,p["feature"])=="A" else p["par2_b"]
               for p in samples)
def fit(samples):
    need(len(samples)>=20,"too few training examples")
    # Explicitly low-capacity: one axis-aligned threshold on five cheap source-only features.
    baseline={"type":"constant","seed":"B"}
    best=baseline;cost=loss(baseline,samples)
    for key in FEATURES:
        values=sorted(set(s["feature"][key] for s in samples))
        for a,b in zip(values,values[1:]):
            threshold=(a+b)/2
            left=sum(s["feature"][key]<=threshold for s in samples)
            if left<5 or len(samples)-left<5:continue
            for lo,hi in (("A","B"),("B","A")):
                test=dict(type="stump",feature=key,threshold=threshold,
                          left_seed=lo,right_seed=hi)
                val=loss(test,samples)
                if val<cost-1e-7:best=test;cost=val
    gain=loss(baseline,samples)-cost
    # If there is no meaningful training gain, deliberately abstain.
    if gain<5.0:return baseline
    return best
def train():
    samples,manifest,_=training_data()
    model=fit(samples)
    cv=0.0;cv_b=0.0;cv_a=0.0
    for held in samples:
        others=[s for s in samples if s["sha"]!=held["sha"]]
        p=fit(others)
        cv+=loss(p,[held])
        cv_b+=held["par2_b"]
        cv_a+=held["par2_a"]
    score=dict(training_n=len(samples),features=FEATURES,
       source_only_classifier=True,model=model,
       training_PAR2_s=round(loss(model,samples),6),
       training_fixed_a_PAR2_s=round(sum(s["par2_a"] for s in samples),6),
       training_fixed_b_PAR2_s=round(sum(s["par2_b"] for s in samples),6),
       LOOCV_selector_PAR2_s=round(cv,6),
       LOOCV_fixed_a_PAR2_s=round(cv_a,6),
       LOOCV_fixed_b_PAR2_s=round(cv_b,6),
       note="LOOCV reflects only previously observed SEED1 cohort, not new holdout")
    print("SEED2_TRAIN",json.dumps(score,sort_keys=True),flush=True)
    return score

def freeze():
    ROOT.mkdir(exist_ok=True);SOURCE.mkdir(exist_ok=True)
    training=train()
    binary_hash=binaries()
    old_excluded_ids,old_excluded_sha,old_exclusions=seed1.exclude()
    previous=json.loads((OLD/"manifest.json").read_text())
    for c in previous["cases"]:
        old_excluded_ids.add(c["gbd"]);old_excluded_sha.add(c["sha256"])
    need(len(old_excluded_sha)>=72,"inadequate prior SHA exclusions")
    import mre7_extended_easy_freeze as pool
    import mre7_reference_easy_freeze as downloader
    candidates=[];indexes={}
    for year in ("2021","2022","2023"):
        ids,indexsha=pool.getids("track=main_"+year)
        easy,es=pool.getids("track=main_"+year+" and minisat1m=yes")
        need(len(ids)==400 and set(easy)<=set(ids),"index mismatch "+year)
        indexes[year]=dict(main_sha256=indexsha,easy_sha256=es)
        es=set(easy)
        candidates.extend((0,year,g) for g in easy if g not in old_excluded_ids)
        candidates.extend((1,year,g) for g in ids
                          if g not in es and g not in old_excluded_ids)
    candidates.sort(key=lambda t:(t[0],hashlib.sha256(
        (SALT+"|"+t[1]+"|"+t[2]).encode()).hexdigest()))
    cases=[];trace=[];seen=set()
    for tier,year,gbd in candidates:
        if len(cases)>=TARGET:break
        if gbd in seen:continue
        seen.add(gbd)
        need(len(seen)<=1120,"source scan exceeded bounds")
        p=SOURCE/(gbd+".cnf")
        entry=dict(year=year,gbd=gbd,index_tier=tier)
        try:
            raw=downloader.get("https://benchmark-database.de/file/"+gbd,
                               12*1024*1024,seconds=20)
            data,_=downloader.prior.r32p.decode(raw)
            need(len(data)<=12*1024*1024,"source bytes cap")
            n,k=downloader.prior.r32p.parse_dimacs_metadata(data)
            need(0<n<=12000 and 0<k<=85000,"source geometry cap")
            sha=hashlib.sha256(data).hexdigest()
            need(sha not in old_excluded_sha,"previously recorded SHA")
            p.write_bytes(data)
            nn,clauses=x22.read_cnf(p)
            need(nn==n and len(clauses)==k,"CNF geometry mismatch")
            feat=features(p,n,clauses)
            decision=pick(training["model"],feat)
            case=dict(year=year,gbd=gbd,filename=p.name,sha256=sha,
                      feature=feat,precommitted_selection=decision,
                      index_tier=tier)
            cases.append(case)
            old_excluded_sha.add(sha)
            entry.update(action="frozen_original",sha256=sha,selector=decision)
        except Exception as e:
            p.unlink(missing_ok=True)
            entry.update(action="skipped_without_solving",reason=str(e)[:140])
        trace.append(entry)
        print("SEED2_SOURCE",json.dumps(entry,sort_keys=True),flush=True)
        save(ROOT/"selection-progress.json",
             dict(count=len(cases),trace=trace))
    need(len(cases)==TARGET,"fewer than 24 original fresh SHA")
    need(len({c["sha256"] for c in cases})==TARGET,"SHA duplicated")
    manifest=dict(protocol=PROTO,source_cases=cases,
       source_count=TARGET,expected_trials=EXPECTED,arms=ARMS,reps=REPS,shards=SHARDS,
       cap_s=CAP,salt=SALT,training=training,
       old_seed1_report_sha256=digest(OLD/"report.json"),
       old_seed1_manifest_sha256=digest(OLD/"manifest.json"),
       code_sha256=digest(__file__),binary_sha256=binary_hash,
       source_indexes=indexes,selection_trace=trace,
       prior_exclusions=old_exclusions,excluded_prior_seed1=True,
       excluded_X20_X21_EQ6_EQ7=True,source_only_preselection=True,
       no_outcome_conditioning_in_holdout=True,independent_UNSAT_LRAT=False,
       global_history_exhaustive=False,not_globally_blind=True,
       no_auto_promotion=True,
       cpu_policy="each arm only one pinned logical CPU; no multi-solver parallelism")
    save(ROOT/"manifest.json",manifest)
    verify()
    print("SEED2_FROZEN",json.dumps(dict(sources=TARGET,trials=EXPECTED,
        predicted_seeds=dict(collections.Counter(c["precommitted_selection"] for c in cases)),
        years=dict(collections.Counter(c["year"] for c in cases)),training=training),
        sort_keys=True),flush=True)

def verify():
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and len(m["source_cases"])==TARGET and
         m["expected_trials"]==EXPECTED and m["arms"]==list(ARMS),
         "frozen protocol drift")
    need(m["code_sha256"]==digest(__file__),"code mutated")
    need(m["binary_sha256"]==binaries(),"solver binary drift")
    seen=set()
    for c in m["source_cases"]:
        p=SOURCE/c["filename"]
        need(digest(p)==c["sha256"] and c["sha256"] not in seen,"source SHA changed")
        seen.add(c["sha256"])
        n,clauses=x22.read_cnf(p)
        need(features(p,n,clauses)==c["feature"],"source features changed")
        need(pick(m["training"]["model"],c["feature"])==
             c["precommitted_selection"],"selector drift")
    return m
def selftest():
    binaries()
    old,_,_=training_data()
    t=train()
    need(t["training_n"]==24 and t["model"]["type"] in ("stump","constant"),
         "training invalid")
    a,b=seed1.seeds({"sha256":"f"*64},0)
    need(a!=b and a<268435456 and b<268435456,"seed bounds")
    need(TARGET%SHARDS==0 and len(ARMS)==6,"shard matrix")
    print("SEED2_SELFTEST_PASS",json.dumps(dict(model=t["model"],arms=ARMS)),flush=True)
def trial(c,rep,arm,m):
    need(arm in ARMS and 0<=rep<REPS,"unregistered trial")
    src=SOURCE/c["filename"]
    need(digest(src)==c["sha256"],"source mutation")
    cpu=sorted(os.sched_getaffinity(0))[0]
    before=x22.child_cpu()
    start=time.perf_counter()
    n,clauses=x22.read_cnf(src)
    selected=None;gate_s=0.0
    if arm in ("native_selected","native_inverse_placebo"):
        t=time.perf_counter()
        actual=features(src,n,clauses)
        need(actual==c["feature"],"source feature mismatch")
        selected=pick(m["training"]["model"],actual)
        if arm=="native_inverse_placebo":
            selected="A" if selected=="B" else "B"
        gate_s=time.perf_counter()-t
    a,b=seed1.seeds(c,rep)
    if arm=="native_a":choice="A"
    elif arm=="native_b":choice="B"
    elif arm in ("native_selected","native_inverse_placebo"):choice=selected
    else:choice="A"
    seed=a if choice=="A" else b
    if arm.startswith("native"):
        backend="native";cmd=x16.command("native",src,seed)
    elif arm=="kissat_a":
        backend="kissat";cmd=x16.command("kissat",src,seed)
    else:
        backend="cadical";cmd=[str(CAD3),"--no-congruence","--no-reluctant",str(src)]
    status="TIMEOUT";witness=False
    with tempfile.TemporaryDirectory(dir=ROOT) as td:
        child=x22.launch("solver",cmd,cpu,td)
        try:
            while child["p"].poll() is None and time.perf_counter()-start<CAP-.02:
                time.sleep(.005)
            if child["p"].poll() is not None:
                stdout,stderr=x22.read_output(child)
                if backend=="cadical":
                    status,witness=x22.solver_result("cadical",child["p"].returncode,
                                                  stdout,clauses,{})
                else:
                    status=x14.outcome_of(backend,child["p"].returncode,
                                         stdout,stderr,src)
                    witness=status=="SAT"
        finally:x22.cleanup([child])
    elapsed=time.perf_counter()-start
    if elapsed>=CAP or status not in ("SAT","UNSAT"):
        status="TIMEOUT";witness=False
    need(status!="SAT" or witness,"SAT model failed original CNF verification")
    return dict(protocol=PROTO,arm=arm,rep=rep,original_sha256=c["sha256"],
       gbd=c["gbd"],seed_a=a,seed_b=b,selected_seed=choice,actual_seed=seed,
       status=status,E2E_s=round(elapsed,6),
       child_CPU_s=round(x22.child_cpu()-before,6),gate_s=round(gate_s,6),
       SAT_original_witness_verified=witness,UNSAT_independent_LRAT=False,
       logical_cpu_budget=1,pinned_cpu=cpu,cap_s=CAP)
def shard(idx):
    m=verify();need(0<=idx<SHARDS,"index")
    subset=m["source_cases"][idx::SHARDS]
    need(len(subset)==TARGET//SHARDS,"imbalance")
    rows=[]
    for c in subset:
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(seed1.seeds(c,rep)[0]).shuffle(arms)
            for arm in arms:
                r=trial(c,rep,arm,m)
                rows.append(r)
                save(ROOT/("shard-%d.json"%idx),rows)
                print("SEED2_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==TARGET//SHARDS*REPS*len(ARMS),"missing shard")
    print("SEED2_SHARD_PASS",idx,len(rows),flush=True)
def audit():
    m=verify();rows=[]
    for i in range(SHARDS):
        rr=json.loads((ROOT/("shard-%d.json"%i)).read_text())
        need(len(rr)==TARGET//SHARDS*REPS*len(ARMS),"incomplete shard")
        rows+=rr
    sources={c["sha256"]:c for c in m["source_cases"]}
    keys={(r["original_sha256"],r["rep"],r["arm"]) for r in rows}
    exp={(sha,r,a) for sha in sources for r in range(REPS) for a in ARMS}
    need(len(rows)==EXPECTED==len(keys)==len(exp) and keys==exp,"trial coverage drift")
    grouped=collections.defaultdict(list)
    for r in rows:
        need(r["protocol"]==PROTO and r["original_sha256"] in sources and
             r["cap_s"]==CAP and r["logical_cpu_budget"]==1,
             "trial identity mismatch")
        need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"invalid outcome")
        need(r["status"]!="SAT" or r["SAT_original_witness_verified"],
             "unverified SAT witness")
        a,b=seed1.seeds(sources[r["original_sha256"]],r["rep"])
        need(r["seed_a"]==a and r["seed_b"]==b,"seed mutated")
        grouped[r["original_sha256"]].append(r)
    consensus=set()
    for sha,rr in grouped.items():
        verdicts={r["status"] for r in rr if r["status"]!="TIMEOUT"}
        need(len(verdicts)<=1,"inconsistent original SAT/UNSAT "+sha)
        if any(r["arm"]=="kissat_a" and r["status"]=="UNSAT" for r in rr) and \
           any(r["arm"]=="cadical3_both" and r["status"]=="UNSAT" for r in rr):
            consensus.add(sha)
    def accepted(r):
        return r["status"]=="SAT" or (r["status"]=="UNSAT" and
                                      r["original_sha256"] in consensus)
    score={}
    for arm in ARMS:
        a=[r for r in rows if r["arm"]==arm]
        score[arm]=dict(attempts=len(a),solved=sum(accepted(r) for r in a),
          verified_SAT=sum(r["status"]=="SAT" for r in a),
          UNSAT_agreed_no_LRAT=sum(r["status"]=="UNSAT" and accepted(r) for r in a),
          UNSAT_unconfirmed=sum(r["status"]=="UNSAT" and not accepted(r) for r in a),
          PAR2_s=round(sum(r["E2E_s"] if accepted(r) else 2*CAP for r in a),6),
          CPU_PAR2_s=round(sum(r["child_CPU_s"] if accepted(r) else 2*CAP
                              for r in a),6),
          child_CPU_s=round(sum(r["child_CPU_s"] for r in a),6),
          feature_gate_s=round(sum(r["gate_s"] for r in a),6))
    for v in score.values():
        v["PAR2_delta_pct_vs_native_b"]=round(
            100*(v["PAR2_s"]/score["native_b"]["PAR2_s"]-1),5)
    paired={}
    for arm in ARMS:
        if arm=="native_b":continue
        wins=losses=ties=0
        for sha,rr in grouped.items():
            case=[r for r in rr if r["arm"]==arm]
            base=[r for r in rr if r["arm"]=="native_b"]
            t=sum(r["E2E_s"] if accepted(r) else 2*CAP for r in case)
            b=sum(r["E2E_s"] if accepted(r) else 2*CAP for r in base)
            if t<b-.1:wins+=1
            elif b<t-.1:losses+=1
            else:ties+=1
        paired[arm]=dict(wins=wins,losses=losses,ties=ties)
    report=dict(protocol=PROTO,sources=TARGET,trials=EXPECTED,cap_s=CAP,reps=REPS,
      no_auto_promotion=True,trained_only_on_SEED1=True,disjoint_recorded_SHA=True,
      globally_blind=False,independent_UNSAT_LRAT=False,
      UNSAT_consensus_sources=len(consensus),
      frozen_model=m["training"]["model"],training_diagnostic=m["training"],
      predicted_seeds=dict(collections.Counter(c["precommitted_selection"]
                                               for c in m["source_cases"])),
      scores=score,paired=paired,rows=rows)
    save(ROOT/"report.json",report)
    print("SEED2_FINAL",json.dumps({k:v for k,v in report.items() if k!="rows"},
                                   sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    if args.action=="shard":shard(args.shard)
    else:globals()[args.action]()
