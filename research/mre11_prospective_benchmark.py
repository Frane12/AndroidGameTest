#!/usr/bin/env python3
"""MRE11 source-disjoint SAT2026 official original verdict benchmark.

4 verified SAT + 4 verified UNSAT source IDs, source-frozen before running any
variants. 2 repetitions, 6 same-in-process pinned CMS 5.11.15 arms + exact
original Kissat 4.0.4 and CaDiCaL reference comparators. Includes end-to-end
wall and full original SAT model verification. Published SAT2026 verified
UNSAT reference + independent Kissat/CaDiCaL consensus, but NO LRAT.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,subprocess,time
import mre11_prospective_freeze as frozen
import r195_native_cms_benchmark as cms

ROOT=pathlib.Path("mre11_bench")
SRC=frozen.ROOT
PROTO=frozen.PROTO
MODES=frozen.MODES
CAP=frozen.CAP
REPS=frozen.REPS
SHARDS=4
def need(v,msg):
    if not v:raise RuntimeError("MRE11_FAIL_CLOSED "+str(msg))
def seed_for(c,rep):
    s=("DRNAS-MRE11-PROSPECTIVE-ORIGINAL-SHA-SEED|"+c["sha256"]+"|"+str(rep))
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
        need(status not in ("SAT","UNSAT") or
             status==c["original_verified_status"],
             "candidate solver contradicts verified official 2026 label")
    elapsed=time.perf_counter()-start
    if status in ("SAT","UNSAT") and elapsed>CAP:
        status="TIMEOUT";model_verified=False
    if status=="UNKNOWN":status="TIMEOUT"
    need(status!="SAT" or model_verified,"SAT without independent original witness")
    return dict(protocol=PROTO,source_sha256=c["sha256"],gbd=c["gbd"],
        official_status=c["original_verified_status"],year=2026,rep=rep,
        mode=mode,seed=seed_for(c,rep),
        independent_seed_applied=(mode not in ("kissat","cadical")),
        status=status,model_original_verified=model_verified,
        UNSAT_official_verified_without_LRAT=(status=="UNSAT"),
        cap_s=CAP,wall_s=round(elapsed,6),par2_s=round(elapsed if status in ("SAT","UNSAT") else 2*CAP,6),
        native=native,gate=gate,original_unseen_in_declared_registry=True,
        proof_limitation="independently published SAT2026 verdict, no LRAT certificate",
        build_sha=os.getenv("GITHUB_SHA","local"))
def shard(idx,cpp,kissat,cadical):
    m=frozen.verify()
    need(idx in range(SHARDS),"wrong shard")
    cases=[c for i,c in enumerate(m["cases"]) if i%SHARDS==idx]
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
                print("MRE11_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==2*REPS*len(MODES),"missing shard trial")
    print("MRE11_SHARD_PASS",idx,len(rows),flush=True)
def audit():
    m=frozen.verify()
    cases=m["cases"];lookup={c["sha256"]:c for c in cases}
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
        need(x["official_status"]==c["original_verified_status"],"published status drift")
        need(x["status"] in ("SAT","UNSAT","TIMEOUT"),"invalid solver status")
        if x["status"]=="SAT":need(x["model_original_verified"],"unverified model")
        if x["status"]=="UNSAT":
            need(c["original_verified_status"]=="UNSAT","UNSAT original disagreement")
        key=(x["source_sha256"],x["rep"])
        need(x["mode"] not in paired[key],"duplicate mode")
        paired[key][x["mode"]]=x
    need(len(paired)==8*REPS,"missing complete paired source reps")
    for p in paired.values():need(set(p)==set(MODES),"missing candidate or reference")
    scores={}
    for mode in MODES:
        a=[x for x in rows if x["mode"]==mode]
        scores[mode]=dict(trials=len(a),SAT=sum(x["status"]=="SAT" for x in a),
            UNSAT_verified_without_LRAT=sum(x["status"]=="UNSAT" for x in a),
            solved=sum(x["status"] in ("SAT","UNSAT") for x in a),
            timeouts=sum(x["status"]=="TIMEOUT" for x in a),
            par2_s=round(sum(x["par2_s"] for x in a),6),
            full_wall_s=round(sum(x["wall_s"] for x in a),6),
            gate_activations=sum(bool(x["gate"].get("applied")) for x in a))
    native=scores["cpp_native"]["par2_s"]
    for mode in MODES:scores[mode]["speedup_vs_cpp_native_PAR2_x"]=round(native/scores[mode]["par2_s"],6)
    report=dict(protocol=PROTO,official_year=2026,
        original_source_count=8,official_verified_SAT=4,official_verified_UNSAT=4,
        fully_source_frozen_before_solver_trials=True,
        declared_prior_registry_disjoint_but_global_not_proven=True,
        benchmark_is_prospective_no_runtime_selection=True,
        icode_sources=[dict(gbd=c["gbd"],sha256=c["sha256"],status=c["original_verified_status"]) for c in cases],
        cap_s=CAP,repeat_count=REPS,trials=len(rows),
        original_SAT_witness_independently_replayed=True,
        UNSAT_officially_verified_without_LRAT=True,
        kissat_and_cadical_have_no_per_repeat_seed_setting=True,
        no_promotion_without_broader_holdout=True,
        scores=scores)
    (ROOT/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("MRE11_FINAL",json.dumps(report,sort_keys=True),flush=True)
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
