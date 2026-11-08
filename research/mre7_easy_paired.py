#!/usr/bin/env python3
"""DRNAS MRE7 locked easy-source *solve-to-verdict* paired benchmark.

Frozen source cohort selected by unrelated CMS reference ONLY before this
gate was ever evaluated. All modes use same source SHA, same pinned CMS binary
and seed, total wall cap includes preprocessing. UNSAT has independent
CaDiCaL agreement at pre-screen but not an LRAT; label explicitly.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,math,os,pathlib,random,re,statistics,subprocess,tempfile,time
import mre7_reference_easy_freeze as frozen
import mre6d_all_equalities as equal
import r164_pure_exact_gf2 as exact
import r195_native_cms_benchmark as r195

PROTO="DRNAS-MRE7-PILOT6-REFERENCE-SELECTED-4ARMS-2REPS-8S-v1"
ROOT=pathlib.Path("mre7_bench")
MODES=("cms_native","all_equalities","gate_auto","kissat")
REPS=2
CAP=8.0
SHARDS=3
MIN_DROP_FRACTION=0.06
MIN_ELIM_FRACTION=0.04
MIN_DROP_CLAUSES=64
MIN_ELIM_VARIABLES=32

def need(cond,msg):
    if not cond:raise RuntimeError("MRE7_BENCH_FAIL_CLOSED "+str(msg))
def seed_for(case,rep):
    return int(hashlib.sha256(("MRE7-FROZEN-SEED|"+case["sha256"]+"|"+str(rep)).encode()).hexdigest()[:8],16)
def gate_decision(original,n):
    cnf,_,mapping,evidence=equal.quotient(original)
    removed=len(original)-len(cnf)
    elim=len(mapping)
    act=(bool(mapping) and removed>=MIN_DROP_CLAUSES
         and elim>=MIN_ELIM_VARIABLES
         and removed/len(original)>=MIN_DROP_FRACTION
         and elim/n>=MIN_ELIM_FRACTION)
    return cnf,mapping,dict(candidate_equalities=evidence["pairs"],
        eliminated_variables=elim,clauses_removed=removed,
        fraction_removed=round(removed/len(original),6),
        fraction_eliminated=round(elim/n,6),
        decision="APPLY" if act else "ABSTAIN",eligible=act,
        evidence=evidence,origin="only two original binary CNF clauses with full transitive replay")
def original_status(case):
    return case["reference_screen_status"]
def trial(case,rep,mode,cms_binary,kissat_binary):
    need(mode in MODES,"unknown arm")
    source=frozen.ROOT/case["filename"]
    need(frozen.sha(source.read_bytes())==case["sha256"],"original source SHA mismatch")
    t0=time.perf_counter()
    prep0=time.perf_counter()
    decision=dict(decision="NATIVE_NO_TRANSFORM")
    map_=None; runsource=source
    with tempfile.TemporaryDirectory(prefix="mre7-fast-") as t:
        root=pathlib.Path(t)
        if mode in ("all_equalities","gate_auto"):
            n,original=exact.parse_dimacs(source)
            cnf,mapping,decision=gate_decision(original,n)
            if mode=="all_equalities" and bool(mapping):
                map_=mapping
            if mode=="gate_auto" and decision["eligible"]:
                map_=mapping
            if map_:
                runsource=root/"quotient.cnf"
                # CNF is equisatisfiable by original-CNF replayed direct
                # equivalences. SAT model is lifted and checked on original.
                from mre1_cross_representation import write_cnf
                write_cnf(runsource,n,cnf,[])
            if mode=="all_equalities":
                decision["decision"]="APPLY" if map_ else "ABSTAIN_NO_EQ"
            if mode=="gate_auto" and not map_:
                decision["decision"]="ABSTAIN"
        prep=time.perf_counter()-prep0
        left=CAP-(time.perf_counter()-t0)
        status="TIMEOUT";stats=None;model_verified=False;runtime=None;stderr=""
        if left>=0.05:
            seed=seed_for(case,rep)
            if mode=="kissat":
                args=[str(pathlib.Path(kissat_binary).resolve()),
                      str(runsource.resolve())]
            else:
                empty=root/"empty.tsv";empty.write_text("")
                args=[str(pathlib.Path(cms_binary).resolve()),
                      str(runsource.resolve()),str(empty.resolve()),str(empty.resolve()),
                      "cms_native",str(seed)]
            env=os.environ.copy()
            n0=time.perf_counter()
            try:
                p=subprocess.run(args,capture_output=True,text=True,errors="replace",
                     env=env,timeout=left,check=False)
            except subprocess.TimeoutExpired:p=None
            runtime=time.perf_counter()-n0
            if p is not None:
                stderr=p.stderr[-400:]
                if mode=="kissat":
                    # Kissat standard SAT-competition exit codes.
                    need(p.returncode in (0,10,20),"Kissat native error "+stderr)
                    if p.returncode==10:status="SAT"
                    elif p.returncode==20:status="UNSAT"
                    elif p.returncode==0:status="UNKNOWN"
                    model={}
                    for line in p.stdout.splitlines():
                        if line.startswith("v "):
                            for lit in map(int,line[2:].split()):
                                if lit:model[abs(lit)]=(lit>0)
                else:
                    need(p.returncode==0,"CMS bridge failure: "+stderr)
                    status,model,stats=r195.parsed_native(p.stdout)
                if status=="SAT":
                    if map_:model=equal.reconstruct(model,map_)
                    r195.verify_model(source,model)
                    model_verified=True
                need(status not in ("SAT","UNSAT") or
                     status==original_status(case),
                     "solved verdict contradicts reference-screen original")
        elapsed=time.perf_counter()-t0
        need(status!="SAT" or model_verified,"invalid SAT witness")
        if elapsed>CAP and status in ("SAT","UNSAT"):
            status="TIMEOUT";model_verified=False
        return dict(protocol=PROTO,year=case["year"],gbd=case["gbd"],
            source_sha256=case["sha256"],reference_screen_status=original_status(case),
            reference_screen_s=case["reference_screen_s"],
            mode=mode,rep=rep,seed=seed_for(case,rep),status=status,
            elapsed_wall_s=round(elapsed,6),preprocessing_s=round(prep,6),
            native_subprocess_s=round(runtime,6) if runtime is not None else None,
            par2_s=round(elapsed if status in ("SAT","UNSAT") else 2*CAP,6),
            original_sat_model_verified=model_verified,
            unsat_cross_solver_cadical_at_source_freeze=(original_status(case)=="UNSAT"),
            independent_UNSAT_LRAT=False,native_stats=stats,
            gate=decision,quotient_applied=bool(map_),
            proof_type="original_binary_equivalence_transitive_closure" if map_ else None,
            study_source_disjoint_declared_registry=True,
            worker_commit=os.environ.get("GITHUB_SHA","local"))

def shard(idx,cms_binary,kissat_binary):
    need(0<=idx<SHARDS,"invalid shard index")
    m=frozen.verify()
    cases=[c for i,c in enumerate(m["selected_cases"]) if i%SHARDS==idx]
    need(bool(cases),"no cases in shard")
    ROOT.mkdir(parents=True,exist_ok=True)
    rows=[]
    for case in cases:
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(PROTO+case["sha256"]+str(rep)).shuffle(modes)
            for mode in modes:
                r=trial(case,rep,mode,cms_binary,kissat_binary)
                rows.append(r)
                (ROOT/("shard-%d.json"%idx)).write_text(json.dumps(rows,sort_keys=True)+"\n")
                print("MRE7_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==len(cases)*REPS*len(MODES),"incomplete source shard")
    print("MRE7_SHARD_PASS",idx,len(cases),len(rows),flush=True)

def audit():
    manifest=frozen.verify()
    rows=[]
    for idx in range(SHARDS):
        path=ROOT/("shard-%d.json"%idx)
        need(path.exists(),"missing benchmark shard "+str(idx))
        rows+=json.loads(path.read_text())
    n=len(manifest["selected_cases"])
    need(6<=n<20 and len(rows)==n*REPS*len(MODES),"incomplete or non-pilot cohort")
    expected={c["sha256"]:c for c in manifest["selected_cases"]}
    paired=collections.defaultdict(dict)
    for r in rows:
        c=expected.get(r["source_sha256"])
        need(c is not None and r["gbd"]==c["gbd"],"source not in frozen cohort")
        need(r["protocol"]==PROTO and r["rep"] in range(REPS),"protocol mismatch")
        if r["status"]=="SAT":need(r["original_sat_model_verified"],"SAT model not checked")
        if r["status"]=="UNSAT":
            need(c["reference_screen_status"]=="UNSAT","UNSAT not independently cross-checked at freeze")
        key=(c["sha256"],r["rep"])
        need(r["mode"] not in paired[key],"duplicate arm")
        paired[key][r["mode"]]=r
    need(len(paired)==n*REPS,"missing case or seed")
    for p in paired.values():
        need(set(p)==set(MODES),"incomplete four-way pairing")
        need(len({v["seed"] for v in p.values()})==1,"unequal paired seed")
    scores={}
    for mode in MODES:
        selected=[r for r in rows if r["mode"]==mode]
        scores[mode]=dict(trials=len(selected),
            SAT=sum(r["status"]=="SAT" for r in selected),
            UNSAT_crosschecked_no_LRAT=sum(r["status"]=="UNSAT" for r in selected),
            timeouts=sum(r["status"]=="TIMEOUT" for r in selected),
            unknown=sum(r["status"]=="UNKNOWN" for r in selected),
            solved=sum(r["status"] in ("SAT","UNSAT") for r in selected),
            par2_s=round(sum(r["par2_s"] for r in selected),6),
            total_wall_s=round(sum(r["elapsed_wall_s"] for r in selected),6),
            total_prep_s=round(sum(r["preprocessing_s"] for r in selected),6),
            gate_activated=sum(r["gate"].get("decision")=="APPLY" for r in selected),
            gate_abstentions=sum(r["gate"].get("decision")=="ABSTAIN" for r in selected))
    comparisons=[]
    for (sha,rep),arms in paired.items():
        base=arms["cms_native"]
        gate=arms["gate_auto"]
        comparisons.append(dict(gbd=base["gbd"],year=base["year"],rep=rep,
            status_native=base["status"],status_gate=gate["status"],
            source_SHA256=sha,baseline_wall_s=base["elapsed_wall_s"],
            gate_wall_s=gate["elapsed_wall_s"],gain_s=round(
            base["elapsed_wall_s"]-gate["elapsed_wall_s"],6),
            gate_decision=gate["gate"]["decision"],applied=gate["quotient_applied"],
            baseline_par2_s=base["par2_s"],gate_par2_s=gate["par2_s"]))
    report=dict(protocol=PROTO,source_selection=manifest["protocol"],
        source_count=n,measurements=len(rows),repeats=REPS,
        total_wall_cap_s=CAP,pilot_reference_preselected_only=True,
        selection_conditioned_on_reference_easiness=True,\n        source_count_insufficient_for_20_case_holdout=True,
        source_disjoint_declared_registry=True,history_registry_not_exhaustive=True,
        no_posthoc_source_exclusion=True,independent_unsat_lrat=False,\n        pilot_only_no_promotion=True,
        SAT_original_model_check_required=True,all_scores=scores,
        cases=comparisons,not_auto_promoted=True)
    ROOT.mkdir(parents=True,exist_ok=True)
    (ROOT/"report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("MRE7_FINAL",json.dumps({k:v for k,v in report.items() if k!="cases"},
        sort_keys=True),flush=True)

def selftest():
    original=[(-1,2),(1,-2),(-2,3),(2,-3),(3,4),(5,)]
    result,mapping,decision=gate_decision(original,5)
    need(len(mapping)==2 and not decision["eligible"],"small quotient must abstain")
    need(len(MODES)==4 and REPS==2 and CAP==8.0 and SHARDS==3,"protocol drift")
    print("MRE7_BENCH_SELFTEST_PASS",PROTO,flush=True)

if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("action",choices=("selftest","shard","audit"))
    a.add_argument("--shard",type=int,default=0)
    a.add_argument("--cms",default="mre7_easy/bin/native")
    a.add_argument("--kissat",default="built/bin/kissat_4_0_4")
    p=a.parse_args()
    if p.action=="selftest":selftest()
    elif p.action=="shard":shard(p.shard,p.cms,p.kissat)
    else:audit()
