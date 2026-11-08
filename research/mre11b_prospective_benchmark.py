#!/usr/bin/env python3
"""MRE11b: new original SAT2021-23 SHA-frozen metadata-easy cohort.
Source selection uses published MiniSat1m metadata, not CMS/MRE performance.
Original SAT witnesses checked. UNSAT not independently LRAT certified.
""".
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,subprocess,time
import mre11b_prospective_freeze as frozen
import r195_native_cms_benchmark as cms

ROOT=pathlib.Path("mre11b_bench")
SRC=frozen.ROOT
PROTO=frozen.PROTO
MODES=frozen.MODES
CAP=frozen.CAP
REPS=frozen.REPS
SHARDS=4
def need(v,msg):
    if not v:raise RuntimeError("MRE11B_FAIL_CLOSED "+str(msg))
def seed_for(c,rep):
    s=("DRNAS-MRE11B-PROSPECTIVE-SOURCE-SHA-SEED|"+c["sha256"]+"|"+str(rep))
    return int(hashlib.sha256(s.encode()).hexdigest()[:8],16)
def gate_parse(output):
    lines=[l.split(" ",1)[1] for l in output.splitlines() if l.startswith("MRE10_GATE ")]
    need(len(lines)==1,"no exactly one source-certified in-process C++ gate event")
    data=json.loads(lines[0])
    need(data["certificate"]=="two_original_CNF_binary_clauses_transitive_closure",
         "missing original source equality proof")
    return data
def external_parse(p):
    # SAT competition exit codes. Confirm output agreement and parse v-witness.
    need(p.returncode in (0,10,20),"reference solver error: "+p.stderr[-300:])
    answer=("SAT" if p.returncode==10 else "UNSAT" if p.returncode==20 else "UNKNOWN")
    solutions=[line[2:].split() for line in p.stdout.splitlines()
               if line.startswith("v ")]
    model={}
    for row in solutions:
        for t in row:
            lit=int(t)
            if lit:model[abs(lit)]=(lit>0)
    need(answer=="UNKNOWN" or ("s SATISFIABLE" if answer=="SAT" else "s UNSATISFIABLE") in p.stdout,
         "exit status differs from textual reference verdict")
    return answer,model
def trial(c,rep,mode,cpp,kissat,cadical):
    need(rep in range(REPS) and mode in MODES,"nonfrozen arm")
    source=SRC/c["filename"]
    need(hashlib.sha256(source.read_bytes()).hexdigest()==c["sha256"],
         "input SHA differs from frozen official formula")
    start=time.perf_counter()
    env=os.environ.copy()
    env.pop("DRNAS_MAX_CONFLICTS",None)
    if mode=="kissat":cmd=[str(pathlib.Path(kissat).resolve()),str(source.resolve())]
    elif mode=="cadical":cmd=[str(pathlib.Path(cadical).resolve()),str(source.resolve())]
    else:cmd=[str(pathlib.Path(cpp).resolve()),str(source.resolve()),mode,str(seed_for(c,rep))]
    status="TIMEOUT";model_verified=False;native=None;gate={}
    solver_s=0.0
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,errors="replace",
                         check=False,timeout=CAP,env=env)
    except subprocess.TimeoutExpired:p=None
    solver_s=time.perf_counter()-start
    if p is not None:
        if mode in ("kissat","cadical"):
            status,model=external_parse(p)
        else:
            need(p.returncode==0,"native C++ CMS crashed: "+p.stderr[-600:])
            gate=gate_parse(p.stdout)
            status,model,native=cms.parsed_native(p.stdout)
        if status=="SAT":
            cms.verify_model(source,model)
            model_verified=True
    elapsed=time.perf_counter()-start
    if status in ("SAT","UNSAT") and elapsed>CAP:
        status="TIMEOUT";model_verified=False
    if status=="UNKNOWN":status="TIMEOUT"
    need(status!="SAT" or model_verified,"SAT without independent original witness")
    return dict(protocol=PROTO,source_sha256=c["sha256"],gbd=c["gbd"],
        official_status=c["official_status"],year=c["year"],rep=rep,
        mode=mode,seed=seed_for(c,rep),
        independent_seed_applied=(mode not in ("kissat","cadical")),
        status=status,model_original_verified=model_verified,
        UNSAT_reported_without_independent_LRAT=(status=="UNSAT"),
        cap_s=CAP,wall_s=round(elapsed,6),par2_s=round(elapsed if status in ("SAT","UNSAT") else 2*CAP,6),
        native=native,gate=gate,original_unseen_in_declared_registry=True,
        proof_limitation="Published MiniSat1m label is NOT a SAT status; UNSAT requires independent cross-solver agreement, no LRAT",
        build_sha=os.getenv("GITHUB_SHA","local"))
def shard(idx,cpp,kissat,cadical):
    m=frozen.verify()
    need(idx in range(SHARDS),"wrong shard")
    cases=[c for i,c in enumerate(m["source_cases"]) if i%SHARDS==idx]
    need(len(cases)==2,"unexpected source distribution")
    ROOT.mkdir(exist_ok=True)
    rows=[]
    for c in cases:
        for rep in range(REPS):
            arms=list(MODES)
            random.Random(PROTO+"|"+c["sha256"]+"|"+str(rep)).shuffle(arms)
            for mode in arms:
                r=trial(c,rep,mode,cpp,kissat,cadical)
                rows.append(r)
                (ROOT/("shard-%d.json"%idx)).write_text(json.dumps(rows,sort_keys=True)+"\n")
                print("MRE11B_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==2*REPS*len(MODES),"missing shard trial")
    print("MRE11B_SHARD_PASS",idx,len(rows),flush=True)
def audit():
    m=frozen.verify()
    cases=m["source_cases"];lookup={c["sha256"]:c for c in cases}
    rows=[]
    for i in range(SHARDS):
        f=ROOT/("shard-%d.json"%i)
        need(f.exists(),"missing shard "+str(i))
        rows.extend(json.loads(f.read_text()))
    need(len(rows)==8*REPS*len(MODES),"not 8x2x8 exact paired trials")
    paired=collections.defaultdict(dict)
    for x in rows:
        c=lookup.get(x["source_sha256"])
        need(c is not None and c["gbd"]==x["gbd"] and x["protocol"]==PROTO,
             "source/sha/protocol drift")
        need(x["seed"]==seed_for(c,x["rep"]),"wrong seed")
        need(x["official_status"]=="UNKNOWN","source metadata must not leak outcome")
        need(x["status"] in ("SAT","UNSAT","TIMEOUT"),"invalid solver status")
        if x["status"]=="SAT":need(x["model_original_verified"],"unverified model")
        key=(x["source_sha256"],x["rep"])
        need(x["mode"] not in paired[key],"duplicate mode")
        paired[key][x["mode"]]=x
    need(len(paired)==8*REPS,"missing complete paired source reps")
    for p in paired.values():need(set(p)==set(MODES),"missing candidate or reference")
    # Across all 8 arms and 2 seeds: a witnessed SAT and any reported UNSAT
    # are incompatible. Fail closed rather than averaging contradictory claims.
    statuses=collections.defaultdict(set)
    reference_agreements=collections.defaultdict(set)
    for x in rows:
        if x["status"] in ("SAT","UNSAT"):statuses[x["source_sha256"]].add(x["status"])
        if x["mode"] in ("kissat","cadical") and x["status"]=="UNSAT":
            reference_agreements[x["source_sha256"]].add(x["mode"])
    for sha,known in statuses.items():
        need(len(known)<=1,"contradictory independent SAT vs UNSAT reports")
    unsat_reference_shas=set(reference_agreements)
    # These are cross-solver agreements, not independently verified LRAT proof.
    for sha in unsat_reference_shas:
        need("UNSAT" in statuses[sha],"reference UNSAT inconsistency")
    scores={}
    for mode in MODES:
        a=[x for x in rows if x["mode"]==mode]
        scores[mode]=dict(trials=len(a),SAT=sum(x["status"]=="SAT" for x in a),
            UNSAT_reported_without_LRAT=sum(x["status"]=="UNSAT" for x in a),
            UNSAT_cross_solver_agreed=sum(x["status"]=="UNSAT" and x["source_sha256"] in unsat_reference_shas for x in a),
            solved=sum(x["status"] in ("SAT","UNSAT") for x in a),
            timeouts=sum(x["status"]=="TIMEOUT" for x in a),
            par2_s=round(sum(x["par2_s"] for x in a),6),
            full_wall_s=round(sum(x["wall_s"] for x in a),6),
            gate_activations=sum(bool(x["gate"].get("applied")) for x in a))
    native=scores["cpp_native"]["par2_s"]
    for mode in MODES:scores[mode]["speedup_vs_cpp_native_PAR2_x"]=round(native/scores[mode]["par2_s"],6)
    report=dict(protocol=PROTO,official_year=c["year"],
        original_source_count=8,official_verified_SAT=4,official_verified_UNSAT=4,
        fully_source_frozen_before_solver_trials=True,
        declared_prior_registry_disjoint_but_global_not_proven=True,
        benchmark_is_prospective_no_runtime_selection=True,
        original_sources=[dict(gbd=c["gbd"],sha256=c["sha256"],source_year=c["year"]) for c in cases],
        cap_s=CAP,repeat_count=REPS,trials=len(rows),
        original_SAT_witness_independently_replayed=True,
        UNSAT_independent_LRAT=False,
        UNSAT_cross_solver_agreement_not_LRAT=True,
        kissat_and_cadical_have_no_per_repeat_seed_setting=True,
        no_promotion_without_broader_holdout=True,
        scores=scores)
    (ROOT/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("MRE11B_FINAL",json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--cpp",default="mre10/bin/native")
    p.add_argument("--kissat",default="built/bin/kissat_4_0_4")
    p.add_argument("--cadical",default="/usr/bin/cadical")
    a=p.parse_args()
    if a.action=="shard":shard(a.shard,a.cpp,a.kissat,a.cadical)
    else:audit()
