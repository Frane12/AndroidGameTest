#!/usr/bin/env python3
"""DRNAS C2: isolate the benefit of source-CNF cleaning, without changing CNF semantics.

Preregistered hypothesis: exact duplicate-clause removal (rather than XOR/GF2,
local repeated literal removal, or tautology removal) explains the gain on
the C1 220bb8aa... SAT source. The 5 C1 sources are DEVELOPMENT ONLY.
This is a purely observational ablation. No adaptive selector/promotion.
"""
from __future__ import annotations
import argparse, collections, hashlib, itertools, json, os, pathlib, random, subprocess, sys, time
import mre11b_prospective_freeze as frozen
import mre11b_prospective_benchmark as ref
import r195_native_cms_benchmark as cms

ROOT=pathlib.Path("c2_out")
GBDS=(
    "a9c0f64594a3eaede246b31eb3bc839b",
    "5ac44f542fd2cd4492067deb7791629a",
    "028d0cc7af63e9bba5795f20e24db4f6",
    "220bb8aa093e502c47afcdac3140d67c",
    "01d142c43f3ce9a8c5ef7a1ecdbb6cba",
)
MODES=("cadical","cpp_native","cpp_dedup","cpp_taut","cpp_local","cpp_clean","cpp_joint")
PROTO="DRNAS-C2-CNF-CLAUSE-ABLATION-5SOURCE-7ARMS-2REPS-35S-v1"
CAP=35
REPS=2
def need(b,msg):
    if not b: raise RuntimeError("C2_FAIL_CLOSED "+str(msg))
def manifest():
    m=frozen.verify()
    d={c["gbd"]:c for c in m["source_cases"]}
    need(len(d)==8 and all(k in d for k in GBDS),"frozen 8-SHA source registry changed")
    for gbd in GBDS:
        c=d[gbd];p=frozen.ROOT/c["filename"]
        need(hashlib.sha256(p.read_bytes()).hexdigest()==c["sha256"],"source SHA mismatch")
    return d
def parse_native_gate(stdout,mode):
    lines=[x.split(" ",1)[1] for x in stdout.splitlines() if x.startswith("MRE10_GATE ")]
    need(len(lines)==1,"C++ gate telemetry missing")
    gate=json.loads(lines[0])
    need(gate["mode"]==mode,"gate mode changed")
    expected="original_CNF_clause_identity" if mode in ("cpp_dedup","cpp_taut","cpp_local") else "two_original_CNF_binary_clauses_transitive_closure"
    need(gate.get("certificate")==expected,"source certificate tag mismatch")
    for k in ("taut_clauses_removed","duplicate_clauses_removed","duplicate_literals_removed"):
        need(isinstance(gate.get(k),int) and gate[k]>=0,"missing ablation counters")
    if mode=="cpp_native":
        need(not gate["applied"],"native must never alter source")
    if mode=="cpp_dedup":
        need(gate["taut_clauses_removed"]==0 and gate["duplicate_literals_removed"]==0 and gate["variables_eliminated"]==0,"dedup modified other mechanisms")
    if mode=="cpp_taut":
        need(gate["duplicate_clauses_removed"]==0 and gate["duplicate_literals_removed"]==0 and gate["variables_eliminated"]==0,"taut modified other mechanisms")
    if mode=="cpp_local":
        need(gate["taut_clauses_removed"]==0 and gate["duplicate_clauses_removed"]==0 and gate["variables_eliminated"]==0,"local modified other mechanisms")
    if mode=="cpp_clean":
        need(gate["variables_eliminated"]==0,"clean must not rename")
    return gate
def trial(c,rep,mode):
    need(rep in range(REPS) and mode in MODES,"unknown benchmark arm")
    p=frozen.ROOT/c["filename"]
    need(hashlib.sha256(p.read_bytes()).hexdigest()==c["sha256"],"source drift")
    seed=ref.seed_for(c,rep)
    cmd=(["/usr/bin/cadical",str(p.resolve())] if mode=="cadical"
         else [str(pathlib.Path("c2/bin/native").resolve()),str(p.resolve()),mode,str(seed)])
    start=time.perf_counter()
    env=os.environ.copy()
    env.pop("DRNAS_MAX_CONFLICTS",None)
    try:
        run=subprocess.run(cmd,capture_output=True,text=True,errors="replace",
            timeout=CAP,check=False,env=env)
    except subprocess.TimeoutExpired:
        run=None
    status="TIMEOUT";verified=False;native=None;gate={}
    if run is not None:
        if mode=="cadical":
            status,model=ref.external_parse(run)
        else:
            need(run.returncode==0,"native failed: "+run.stderr[-500:])
            gate=parse_native_gate(run.stdout,mode)
            status,model,native=cms.parsed_native(run.stdout)
        if status=="SAT":
            cms.verify_model(p,model)
            verified=True
    seconds=time.perf_counter()-start
    if status not in ("SAT","UNSAT") or seconds>CAP:
        status="TIMEOUT";verified=False
    need(status!="SAT" or verified,"SAT witness is not original-CNF certified")
    return dict(protocol=PROTO,source_sha256=c["sha256"],gbd=c["gbd"],
       original_year=c["year"],rep=rep,seed=seed,mode=mode,
       status=status,original_SAT_verified=verified,
       UNSAT_independent_LRAT=False,cap_s=CAP,
       wall_s=round(seconds,6),par2_s=round(seconds if status in ("SAT","UNSAT") else 2*CAP,6),
       independent_seed_applied=(mode!="cadical"),native=native,gate=gate,
       build_sha=os.environ.get("GITHUB_SHA","LOCAL"))
def shard(index):
    d=manifest()
    need(index in range(5),"index outside preregistered five formulas")
    ROOT.mkdir(exist_ok=True)
    c=d[GBDS[index]]
    rows=[]
    for rep in range(REPS):
        arms=list(MODES)
        random.Random(PROTO+"|"+c["sha256"]+"|"+str(rep)).shuffle(arms)
        for mode in arms:
            row=trial(c,rep,mode)
            rows.append(row)
            (ROOT/("shard-%d.json"%index)).write_text(json.dumps(rows,indent=2,sort_keys=True)+"\n")
            print("C2_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==REPS*len(MODES),"incomplete shard")
    print("C2_SHARD_PASS",index,len(rows),flush=True)
def read_clauses(path):
    result=[];n=None;buffer=[]
    for line in path.read_text().splitlines():
        l=line.strip()
        if not l or l.startswith("c"):continue
        if l.startswith("p "):
            _,typ,vars_,count=l.split()
            need(typ=="cnf","bad test cnf")
            n=int(vars_)
            continue
        for token in l.split():
            lit=int(token)
            if lit==0:result.append(tuple(buffer));buffer=[]
            else:buffer.append(lit)
    need(n is not None and not buffer,"incomplete test CNF")
    return n,result
def evaluate(clauses,assignment):
    return all(any(assignment[abs(lit)-1]==(lit>0) for lit in clause) for clause in clauses)
def selftest():
    ROOT.mkdir(exist_ok=True)
    p=ROOT/"selftest.cnf"
    p.write_text("p cnf 4 8\n1 2 0\n2 1 0\n1 -1 3 0\n1 1 4 0\n4 1 0\n-2 3 0\n3 -2 0\n-4 0\n")
    base_vars,base=read_clauses(p)
    expected={"cpp_native":(0,0,0),"cpp_dedup":(0,3,0),
        "cpp_taut":(1,0,0),"cpp_local":(0,0,1)}
    for mode in ("cpp_native","cpp_dedup","cpp_taut","cpp_local","cpp_clean"):
        dst=ROOT/("selftest-"+mode+".cnf")
        result=subprocess.run(["c2/bin/emit","--emit",str(p),mode,str(dst)],
            capture_output=True,text=True,check=True)
        gate=parse_native_gate(result.stdout,mode)
        n,clauses=read_clauses(dst)
        need(n==base_vars,"number of variables changed in simple ablation")
        for assignment in itertools.product((False,True),repeat=n):
            need(evaluate(base,assignment)==evaluate(clauses,assignment),
                 "truth table mismatch for "+mode)
        if mode in expected:
            t,d,l=expected[mode]
            need((gate["taut_clauses_removed"],gate["duplicate_clauses_removed"],gate["duplicate_literals_removed"])==(t,d,l),
                 "synthetic mechanism count mismatch "+mode)
        if mode=="cpp_clean":
            need(gate["taut_clauses_removed"]==1 and gate["duplicate_clauses_removed"]==3 and gate["duplicate_literals_removed"]==1,
                 "full clean expected known ablation effects")
    # Rebuilt native mode must reproduce frozen original program's decisions.
    parity=[]
    for exe in ("mre10/bin/native","c2/bin/native"):
        run=subprocess.run([exe,str(p),"cpp_native","42"],capture_output=True,text=True,check=True)
        status,model,stats=cms.parsed_native(run.stdout)
        need(status=="SAT","native smoke reference status failed")
        cms.verify_model(p,model)
        parity.append((status,stats))
    need(parity[0]==parity[1],"frozen native binary vs C2 native CDCL counters differ")
    print("C2_SELFTEST_PASS truth_tables=5 assignments=16 frozen_native_exact_CDCL_stats=true",flush=True)
def audit():
    d=manifest();rows=[]
    for shard_id in range(len(GBDS)):
        path=ROOT/("shard-%d.json"%shard_id)
        need(path.exists(),"missing shard")
        shard_rows=json.loads(path.read_text())
        need(len(shard_rows)==REPS*len(MODES),"incomplete shard rows")
        rows.extend(shard_rows)
    need(len(rows)==len(GBDS)*REPS*len(MODES),"wrong total attempt count")
    pairs=collections.defaultdict(dict)
    statuses=collections.defaultdict(set)
    for x in rows:
        c=d.get(x["gbd"])
        need(c is not None and x["gbd"] in GBDS and c["sha256"]==x["source_sha256"],"source provenance mismatch")
        need(x["protocol"]==PROTO and x["seed"]==ref.seed_for(c,x["rep"]) and x["cap_s"]==CAP,"protocol seed budget drift")
        need(x["mode"] in MODES and x["status"] in ("SAT","UNSAT","TIMEOUT"),"arm/status mismatch")
        need(x["status"]!="SAT" or x["original_SAT_verified"],"invalid SAT witness")
        if x["status"]!="TIMEOUT":statuses[x["gbd"]].add(x["status"])
        key=(x["source_sha256"],x["rep"])
        need(x["mode"] not in pairs[key],"duplicate source rep arm")
        pairs[key][x["mode"]]=x
    need(len(pairs)==len(GBDS)*REPS,"incomplete pair count")
    for pair in pairs.values():need(set(pair)==set(MODES),"incomplete benchmark arms")
    for status_set in statuses.values():need(len(status_set)<=1,"SAT/UNSAT contradiction")
    scores={}
    for mode in MODES:
        group=[x for x in rows if x["mode"]==mode]
        scores[mode]=dict(trials=len(group),SAT=sum(x["status"]=="SAT" for x in group),
            UNSAT_without_LRAT=sum(x["status"]=="UNSAT" for x in group),
            solved=sum(x["status"]!="TIMEOUT" for x in group),
            timeouts=sum(x["status"]=="TIMEOUT" for x in group),
            par2_s=round(sum(x["par2_s"] for x in group),6),
            wall_s=round(sum(x["wall_s"] for x in group),6),
            taut_removed=sum(x["gate"].get("taut_clauses_removed",0) for x in group),
            duplicates_removed=sum(x["gate"].get("duplicate_clauses_removed",0) for x in group),
            local_literals_removed=sum(x["gate"].get("duplicate_literals_removed",0) for x in group))
    for mode in MODES:
        scores[mode]["speedup_vs_native_x"]=round(scores["cpp_native"]["par2_s"]/scores[mode]["par2_s"],6)
    result=dict(protocol=PROTO,run_sha=os.environ.get("GITHUB_SHA","LOCAL"),
        cohort="C1 selected development five original SHA, NOT independent blind",
        source_SHA=[d[gbd]["sha256"] for gbd in GBDS],cases=5,repeats=REPS,
        cap_s=CAP,trials=len(rows),paired_source_reps=len(pairs),
        original_SAT_witness_replayed=True,independent_UNSAT_LRAT=False,
        independent_cadical_per_rep_seed=False,no_auto_promotion=True,
        scores=scores)
    (ROOT/"report.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("C2_FINAL",json.dumps(result,sort_keys=True),flush=True)
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("selftest","shard","audit"))
    parser.add_argument("--shard",type=int,default=0)
    args=parser.parse_args()
    if args.action=="selftest":selftest()
    elif args.action=="shard":shard(args.shard)
    else:audit()
