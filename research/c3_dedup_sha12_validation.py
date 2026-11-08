#!/usr/bin/env python3
"""C3: predeclared SHA-disjoint, *development* external validation of exact CNF duplicate removal.

Twelve ORIGINAL SAT2021-25 formulas pinned by MRE11-EASY12; chosen independently
of C2 dedup results, but already tested by earlier DRNAS workflows (NOT blind).
Hypothesis: exact canonical source duplicate removal gives a reproducible
end-to-end solved/PAR2 advantage on different original CNFs when duplicates exist,
and negligible overhead when duplicates are absent. Falsifier: no duplicates on
this independent cohort, nonpositive paired PAR2/solved, or regressions.
No adaptive selector. No promotion. Original SAT model replay; UNSAT only
prior CaDiCaL reference agreement, independent LRAT unavailable.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, os, pathlib, random, statistics, subprocess, sys, time
import c2_cnf_clean_ablation as c2
import r195_native_cms_benchmark as cms

ROOT=pathlib.Path("c3_out")
SRC=pathlib.Path("mre11_easy")
PROTO="DRNAS-C3-12SHA-SOURCE-DISJOINT-CNF-DEDUP-4ARMS-4REPS-12S-v1"
CAP=12.0
REPS=4
MODES=("cpp_native","cpp_dedup","cpp_clean","cadical")
SHARDS=4
PINNED_SHAS=frozenset((
"ae9ec25d79e840a6794724857b894bf47e595a17c5893170f38526a41380f472",
"7b886432bf5f8c0e873e9bb0a01d32346e24380911d982573add2178a2a56fe6",
"eb9a4740b712b149f08d5b430ae5907109eac3f231ce549a281703bc8e0965fb",
"ed070d2f6b9e3c4f918b5412413b94e806c06005c2c308b17bc6a25ad1ebf5af",
"ead603b38fca048e96b4592c141bcd553856388479c1930042a1dfe176a44272",
"d6397d0bf73b9901e8af7c694ec6abf86cd3ecca029c44884183b5236304dbdf",
"6582502357d5960da9e8059fc1211e82d821944cae07d22ebef91509af7909ba",
"404763ef74f0191d82f16eddd540e6d885e61d34c2a88920c1c5b11c6691b126",
"7f25d0862e92fb60d957ea903ded020ec2b83b2ceec2ba4bf015bdcb1d4c3ac1",
"b84bff752c8292bacf847078d0fe2c2bf8ef86f429c08250e973a0525b607c39",
"818eea0ab4e59102c589549d3ca487bf7c8a03e1e51644a126cba75a911e53de",
"ac6db654d4234532285b256732cbe65c140714b23c4827b7c62daf0cd39119d9",
))
C2_SHAS=frozenset((
"d677593932dde9b85d7229a513983e72fd77a850711fea7f6434eb973b144b92",
"5e7c2b214b6a3e7b97b947c5b0f8ffa2b5588892636690dfdf9b20989b17fd1f",
"de34fcdd49b1f5b696eaa195103b46e1be306f15ef6380dbf0965bae4856e654",
"69aa8b6bb96a5952fedf1007994b4255d06f7e32023390bc4c342b1b30a0356a",
"14a232cc56fe164bba98501891983cc55181e13e1d80d865159362f20e1a62e9",
))
def need(ok,msg):
    if not ok:raise RuntimeError("C3_FAIL_CLOSED "+str(msg))
def original_cases():
    manifest=json.loads((SRC/"manifest.json").read_text())
    need(manifest["source_reuse_development_not_blind"] is True,"must retain development provenance")
    need(manifest["protocol"]=="DRNAS-MRE11-EASY12-2021-2025-DEVREPLAY-5ARMS-4SEEDS-12S-v1","wrong source cohort")
    need(manifest["expected_trials"]==240,"source selection changed")
    cases=manifest["cases"]
    need(len(cases)==12 and len(set(c["sha256"] for c in cases))==12,"source size / duplicate SHA")
    need(set(c["sha256"] for c in cases)==PINNED_SHAS,"SHA list changed after preregistration")
    need(not(PINNED_SHAS&C2_SHAS),"C2 overlap found")
    for c in cases:
        p=SRC/c["filename"]
        need(p.is_file(),"missing source original")
        need(hashlib.sha256(p.read_bytes()).hexdigest()==c["sha256"],"original source SHA drift")
        need(c["reference_screen_status"] in ("SAT","UNSAT"),"prior source label must not be UNKNOWN")
    return cases
def seed(c,rep):
    return int(hashlib.sha256((PROTO+"|"+c["sha256"]+"|"+str(rep)).encode()).hexdigest()[:8],16)
def trial(c,mode,rep):
    need(mode in MODES and rep in range(REPS),"arm/rep invalid")
    path=SRC/c["filename"]
    need(hashlib.sha256(path.read_bytes()).hexdigest()==c["sha256"],"source altered")
    cmd=(["/usr/bin/cadical",str(path.resolve())] if mode=="cadical" else
         [str(pathlib.Path("c2/bin/native").resolve()),str(path.resolve()),mode,str(seed(c,rep))])
    env=os.environ.copy();env.pop("DRNAS_MAX_CONFLICTS",None)
    start=time.perf_counter()
    try:
        result=subprocess.run(cmd,capture_output=True,text=True,errors="replace",check=False,
            timeout=CAP,env=env)
    except subprocess.TimeoutExpired:
        result=None
    status="TIMEOUT";gate={};stats=None;verified=False
    if result is not None:
        if mode=="cadical":
            status,model=c2.ref.external_parse(result)
        else:
            need(result.returncode==0,"native failed "+result.stderr[-500:])
            gate=c2.parse_native_gate(result.stdout,mode)
            status,model,stats=cms.parsed_native(result.stdout)
        if status=="SAT":
            cms.verify_model(path,model);verified=True
    wall=time.perf_counter()-start
    if status not in ("SAT","UNSAT") or wall>CAP:
        status="TIMEOUT";verified=False
    if status!="TIMEOUT":
        need(status==c["reference_screen_status"],"contradicts original reference SAT/UNSAT")
    need(status!="SAT" or verified,"SAT without checked original model")
    return dict(protocol=PROTO,sha256=c["sha256"],gbd=c["gbd"],year=c["year"],
        source_provenance="MRE11-EASY12 prior development/replay (not blind)",
        rep=rep,seed=seed(c,rep),mode=mode,status=status,
        prior_reference_status=c["reference_screen_status"],original_SAT_witness_verified=verified,
        UNSAT_independent_LRAT=False,wall_s=round(wall,6),
        par2_s=round(wall if status in ("SAT","UNSAT") else 2*CAP,6),
        cap_s=CAP,gate=gate,native_stats=stats,
        independent_seed_applied=mode!="cadical",build_sha=os.environ.get("GITHUB_SHA","LOCAL"))
def source_shard(i):
    cases=original_cases()
    need(i in range(SHARDS),"invalid shard")
    chosen=[x for j,x in enumerate(cases) if j%SHARDS==i]
    need(len(chosen)==3,"not exactly three source originals per shard")
    ROOT.mkdir(exist_ok=True)
    rows=[]
    for c in chosen:
        for rep in range(REPS):
            arms=list(MODES)
            random.Random(PROTO+"|"+c["sha256"]+"|"+str(rep)).shuffle(arms)
            for mode in arms:
                row=trial(c,mode,rep);rows.append(row)
                (ROOT/("shard-%d.json"%i)).write_text(json.dumps(rows,indent=2,sort_keys=True)+"\n")
                print("C3_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==3*REPS*len(MODES),"incomplete shard")
    print("C3_SHARD_PASS",i,len(rows),flush=True)
def audit():
    cases=original_cases()
    by_sha={x["sha256"]:x for x in cases}
    rows=[]
    for i in range(SHARDS):
        path=ROOT/("shard-%d.json"%i)
        need(path.is_file(),"missing shard "+str(i))
        sl=json.loads(path.read_text())
        need(len(sl)==3*REPS*len(MODES),"partial shard")
        rows.extend(sl)
    need(len(rows)==12*REPS*len(MODES),"wrong trial count")
    paired=collections.defaultdict(dict)
    for x in rows:
        c=by_sha.get(x["sha256"])
        need(c is not None and x["gbd"]==c["gbd"],"alien original SHA/GBD")
        need(x["protocol"]==PROTO and x["seed"]==seed(c,x["rep"]) and x["cap_s"]==CAP,"unfrozen seed or cap")
        need(x["mode"] in MODES and x["status"] in ("SAT","UNSAT","TIMEOUT"),"invalid mode/terminal")
        need(x["status"]=="TIMEOUT" or x["status"]==c["reference_screen_status"],"SAT UNSAT contradiction")
        need(x["status"]!="SAT" or x["original_SAT_witness_verified"],"missing original witness")
        need(x["rep"] in range(REPS),"unregistered seed repetition")
        need(x["wall_s"]>=0 and x["cap_s"]==CAP,"wall time/cap invalid")
        if x["status"]=="TIMEOUT":
            need(x["par2_s"]==2*CAP and not x["original_SAT_witness_verified"],
                 "timeout must carry PAR2 penalty and no SAT witness")
            # Subprocess timeout does not return C++ gate telemetry; empty gate is valid here.
            need(not x["gate"] and x["native_stats"] is None,
                 "timeout must not fabricate complete native counters")
        else:
            need(abs(x["par2_s"]-x["wall_s"])<=0.000002,
                 "terminal PAR2 must equal measured end-to-end time")
            if x["mode"]!="cadical":
                need(isinstance(x["gate"],dict) and "applied" in x["gate"],
                     "terminal native result missing gate telemetry")
        if x["mode"]=="cpp_native":
            need(not x["gate"].get("applied"),"native must be unmodified")
        if x["mode"]=="cpp_dedup" and x["status"]!="TIMEOUT":
            need(all(key in x["gate"] for key in
                     ("duplicate_literals_removed","taut_clauses_removed",
                      "variables_eliminated","duplicate_clauses_removed")),
                 "terminal dedup missing source-cert telemetry")
            need(x["gate"]["duplicate_literals_removed"]==0 and
                 x["gate"]["taut_clauses_removed"]==0 and
                 x["gate"]["variables_eliminated"]==0,
                 "dedup changed other mechanism")
        key=(x["sha256"],x["rep"])
        need(x["mode"] not in paired[key],"duplicate paired key")
        paired[key][x["mode"]]=x
    need(len(paired)==12*REPS and all(set(x)==set(MODES) for x in paired.values()),"incomplete pairing")
    scores={}
    for mode in MODES:
        vals=[x for x in rows if x["mode"]==mode]
        scores[mode]=dict(trials=len(vals),
            solved=sum(x["status"] in ("SAT","UNSAT") for x in vals),
            SAT=sum(x["status"]=="SAT" for x in vals),
            UNSAT_without_independent_LRAT=sum(x["status"]=="UNSAT" for x in vals),
            timeouts=sum(x["status"]=="TIMEOUT" for x in vals),
            par2_s=round(sum(x["par2_s"] for x in vals),6),
            wall_s=round(sum(x["wall_s"] for x in vals),6),
            duplicate_clauses_removed=sum(x["gate"].get("duplicate_clauses_removed",0) for x in vals),
            native_gate_s=round(sum(x["gate"].get("native_gate_s",0) for x in vals),6))
    for mode in MODES:
        scores[mode]["PAR2_speedup_vs_native_x"]=round(scores["cpp_native"]["par2_s"]/scores[mode]["par2_s"],6)
    per_source=[]
    for c in cases:
        ss=[x for x in rows if x["sha256"]==c["sha256"]]
        g={mode:[x for x in ss if x["mode"]==mode] for mode in MODES}
        per_source.append(dict(gbd=c["gbd"],sha256=c["sha256"],year=c["year"],
            source_clauses=c["clauses"],source_vars=c["variables"],
            observed_duplicate_clauses=g["cpp_dedup"][0]["gate"].get("duplicate_clauses_removed",0),
            by_mode={k:dict(solved=sum(x["status"]!="TIMEOUT" for x in v),
                par2_s=round(sum(x["par2_s"] for x in v),6),
                median_wall_s=round(statistics.median(x["wall_s"] for x in v),6) if v else None)
                for k,v in g.items()}))
    result=dict(protocol=PROTO,preregistered_source_count=12,trials=len(rows),
        paired_source_reps=len(paired),cohort="C2 SHA-disjoint MRE11-EASY12 previous development, NOT global blind",
        frozen_sha256=sorted(PINNED_SHAS),repeats=REPS,cap_s=CAP,
        original_SAT_replay=True,UNSAT_independent_LRAT=False,
        same_exact_frozen_C2_native_binary=True,no_auto_promotion=True,
        cadical_independent_seed_applied=False,scores=scores,per_source=per_source)
    (ROOT/"report.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("C3_FINAL",json.dumps({k:v for k,v in result.items() if k!="per_source"},sort_keys=True),flush=True)
if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("action",choices=("verify","shard","audit"))
    a.add_argument("--shard",type=int,default=0)
    args=a.parse_args()
    if args.action=="verify":
        print("C3_SHA_DISJOINT_FROZEN_PASS",len(original_cases()),flush=True)
    elif args.action=="shard":source_shard(args.shard)
    else:audit()
