#!/usr/bin/env python3
"""DRNAS C6: Factorial CNF dedup × CryptoMiniSat inprocessing, real SAT/UNSAT.

6 selected original development SHA, paired C4/C5 frozen seeds, 6 arms:
  cpp_native, cpp_dedup (exact frozen C2 controls)
  c6_native_nobve, c6_dedup_nobve (CMS bounded variable elimination off)
  c6_native_nosimplify, c6_dedup_nosimplify (CMS global simplification off)
3 repetitions and 35s wall cap, real end-to-end PAR2. SAT model always
replayed on original SHA. UNSAT has only previous CaDiCaL independent
solver agreement; no independent LRAT. This is a causal DEVELOPMENT test
not a blind performance claim. Never auto-promote experimental modes.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,pathlib,random,subprocess,sys,time
import c5_early_cdcl_bounded as c5
import c4_duplicate_order_causal as c4
import r195_native_cms_benchmark as cms

OUT=pathlib.Path("c6_out")
PROTO="DRNAS-C6-6SHA-DUPLICATES-X-CMS-INPROCESSING-6ARMS-3REP-35S-v1"
MODES=("cpp_native","cpp_dedup",
       "c6_native_nobve","c6_dedup_nobve",
       "c6_native_nosimplify","c6_dedup_nosimplify")
CAP=35.0
REPS=3
CONTROL_MODES=("cpp_native","cpp_dedup")
GATE_BY_MODE={m:("cpp_dedup" if m in
    ("cpp_dedup","c6_dedup_nobve","c6_dedup_nosimplify")
     else "cpp_native") for m in MODES}
def need(b,msg):
    if not b:raise RuntimeError("C6_FAIL_CLOSED "+str(msg))
def sources():
    cc=c5.source_cases()
    need(len(cc)==6 and len({x["sha256"] for x in cc})==6,
         "C5 source SHA registry drifted")
    return cc
def seed(c,rep):
    return c5.c5_seed(c,rep)
def binary(mode):
    return "c2/bin/native" if mode in CONTROL_MODES else "c6/bin/native"
def native_gate(stdout,mode):
    gate=c4.gate_native(stdout,GATE_BY_MODE[mode])
    need(gate["certificate"]==
         ("original_CNF_clause_identity"
           if GATE_BY_MODE[mode]=="cpp_dedup"
           else "two_original_CNF_binary_clauses_transitive_closure"),
         "gate certificate incorrect")
    if mode in ("cpp_native","c6_native_nobve","c6_native_nosimplify"):
        need(not gate["applied"] and gate["clauses_removed"]==0,
             "native arm changed original clauses")
    else:
        need(gate["taut_clauses_removed"]==0 and
             gate["duplicate_literals_removed"]==0 and
             gate["variables_eliminated"]==0,
             "dedup arm changed non-duplicate mechanism")
    return gate
def run(c,rep,mode):
    need(mode in MODES and rep in range(REPS),"unregistered mode/repetition")
    path=c["path"]
    need(hashlib.sha256(path.read_bytes()).hexdigest()==c["sha256"],
         "source SHA changed")
    env=os.environ.copy()
    env.pop("DRNAS_MAX_CONFLICTS",None)
    start=time.perf_counter()
    try:
        p=subprocess.run([str(pathlib.Path(binary(mode)).resolve()),
                          str(path.resolve()),mode,str(seed(c,rep))],
                         capture_output=True,text=True,errors="replace",
                         check=False,timeout=CAP,env=env)
    except subprocess.TimeoutExpired:
        p=None
    elapsed=time.perf_counter()-start
    status="TIMEOUT";gate={};stats=None;verified=False
    if p is not None:
        need(p.returncode==0,"CMS native exited nonzero "+str(p.returncode)+" "+p.stderr[-700:])
        gate=native_gate(p.stdout,mode)
        status,model,stats=cms.parsed_native(p.stdout)
        need(status in ("SAT","UNSAT","TIMEOUT"),"unsupported real terminal")
        if status=="SAT":
            cms.verify_model(path,model);verified=True
        if status in ("SAT","UNSAT"):
            need(status==c["expected_status"],"SAT/UNSAT vs pinned source contradiction")
    if status not in ("SAT","UNSAT") or elapsed>CAP:
        status="TIMEOUT";verified=False
    need(status!="SAT" or verified,"SAT witness not proven on original CNF")
    return dict(protocol=PROTO,cohort="six frozen C4/C5 development SHA not blind",
        gbd=c["gbd"],sha256=c["sha256"],source_control=bool(c["control"]),
        original_reference_status=c["expected_status"],mode=mode,
        rep=rep,seed=seed(c,rep),cap_s=CAP,status=status,
        original_SAT_witness_verified=verified,
        independent_UNSAT_LRAT=False,wall_s=round(elapsed,6),
        par2_s=round(elapsed if status in ("SAT","UNSAT") else CAP*2,6),
        gate=gate,native_stats=stats,
        source_binary="C2_FROZEN" if mode in CONTROL_MODES else "C6_DIAGNOSTIC",
        build_sha=os.getenv("GITHUB_SHA","LOCAL"))
def parity_selftest():
    # No silent change in the compiled C6 solver's original path.
    # Both controls must produce identical full model and CDCL counts on one
    # SAT source and one UNSAT source; the original source is independently checked.
    samples=[sources()[0],sources()[5]]
    confirmed=[]
    for item in samples:
        for mode in CONTROL_MODES:
            got=[]
            for exe in ("c2/bin/native","c6/bin/native"):
                p=subprocess.run([exe,str(item["path"]),mode,
                       str(seed(item,0))],capture_output=True,text=True,
                       check=True,timeout=35)
                status,model,stats=cms.parsed_native(p.stdout)
                g=native_gate(p.stdout,mode)
                if status=="SAT":cms.verify_model(item["path"],model)
                need(status==item["expected_status"],"reference SAT UNSAT status drift")
                got.append((status,model,stats,g.get("clauses_removed")))
            need(got[0]==got[1],"C2 frozen vs C6 compiler baseline changed outcome/stats")
            confirmed.append(dict(sha256=item["sha256"],mode=mode,
                                  status=got[0][0],conflicts=got[0][2]["conflicts"]))
    print("C6_FROZEN_C2_BINARY_PARITY_PASS",json.dumps(confirmed,sort_keys=True),flush=True)
def shard(index):
    cc=sources()
    need(index in range(6),"shard outside frozen 6-source pool")
    item=cc[index]
    OUT.mkdir(exist_ok=True)
    rows=[]
    for rep in range(REPS):
        arms=list(MODES)
        random.Random(PROTO+"|"+item["sha256"]+"|"+str(rep)).shuffle(arms)
        for mode in arms:
            x=run(item,rep,mode)
            rows.append(x)
            (OUT/("shard-%d.json"%index)).write_text(
                json.dumps(rows,indent=2,sort_keys=True)+"\n")
            print("C6_TRIAL",json.dumps(x,sort_keys=True),flush=True)
    need(len(rows)==REPS*len(MODES),"incomplete C6 source shard")
    print("C6_SHARD_PASS",index,len(rows),flush=True)
def prior_c5():
    files=list(pathlib.Path("c6_prior_c5").rglob("shard-*.json"))
    need(len(files)==6,"prior C5 early-bounded source files missing")
    rows=[]
    for f in files:
        part=json.loads(f.read_text())
        need(len(part)==27,"incomplete C5 prior bounded source")
        rows.extend(part)
    need(len(rows)==162,"C5 prior 162 bounded attempts incomplete")
    cc={x["sha256"]:x for x in sources()}
    exact={}
    for x in rows:
        c=cc.get(x["sha256"])
        need(c is not None and x["protocol"]==c5.PROTO and
             x["seed"]==seed(c,x["rep"]) and x["mode"] in c5.MODES and
             x["budget_conflicts"] in c5.BUDGETS,
             "C5 original SHA/seed/window drift")
        key=(x["sha256"],x["rep"],x["mode"],x["budget_conflicts"])
        need(key not in exact,"C5 duplicate early row")
        exact[key]=x
    need(len(exact)==162,"C5 prior original SHA not fully paired")
    return exact
def audit():
    cc=sources()
    per_sha={c["sha256"]:c for c in cc}
    allrows=[]
    for shard_id in range(6):
        f=OUT/("shard-%d.json"%shard_id)
        need(f.is_file(),"missing source shard")
        part=json.loads(f.read_text())
        need(len(part)==REPS*len(MODES),"partial source shard")
        allrows.extend(part)
    need(len(allrows)==6*REPS*len(MODES),"not 108 original SAT/UNSAT trials")
    complete=collections.defaultdict(dict)
    for x in allrows:
        c=per_sha.get(x["sha256"])
        need(c is not None and x["gbd"]==c["gbd"],"alien original SHA")
        need(x["protocol"]==PROTO and x["seed"]==seed(c,x["rep"]) and
             x["rep"] in range(REPS) and x["mode"] in MODES and x["cap_s"]==CAP,
             "protocol/seed/mode changed")
        need(x["status"] in ("SAT","UNSAT","TIMEOUT"),"unsupported terminal")
        if x["status"]!="TIMEOUT":
            need(x["status"]==c["expected_status"],"SAT/UNSAT reference contradiction")
            need(abs(x["par2_s"]-x["wall_s"])<0.000002,
                 "solved result PAR2 wrong")
            if x["status"]=="SAT":
                need(x["original_SAT_witness_verified"],"missing SAT original CNF witness")
            need(isinstance(x["gate"],dict) and "mode" in x["gate"],
                 "native terminal missing exact gate certificate")
        else:
            need(x["par2_s"]==2*CAP and
                 not x["original_SAT_witness_verified"],
                 "missing PAR2 timeout penalty")
            need(not x["gate"] and x["native_stats"] is None,
                 "timeout fabricated completed native stats")
        key=(x["sha256"],x["rep"])
        need(x["mode"] not in complete[key],"duplicate exact source/seed/arm")
        complete[key][x["mode"]]=x
    need(len(complete)==6*REPS and
         all(set(g)==set(MODES) for g in complete.values()),
         "incomplete 18 paired source-seed groups")
    scores={}
    for mode in MODES:
        a=[x for x in allrows if x["mode"]==mode]
        scores[mode]=dict(trials=len(a),
             solved=sum(x["status"]!="TIMEOUT" for x in a),
             SAT=sum(x["status"]=="SAT" for x in a),
             UNSAT_no_independent_LRAT=sum(x["status"]=="UNSAT" for x in a),
             timeouts=sum(x["status"]=="TIMEOUT" for x in a),
             PAR2_s=round(sum(x["par2_s"] for x in a),6),
             real_wall_s=round(sum(x["wall_s"] for x in a),6),
             duplicate_clauses_removed=sum(
                   x["gate"].get("duplicate_clauses_removed",0) for x in a),
             gate_s=round(sum(x["gate"].get("native_gate_s",0) for x in a),6))
    baseline=scores["cpp_native"]["PAR2_s"]
    for mode in MODES:scores[mode]["speedup_vs_native_x"]=round(baseline/scores[mode]["PAR2_s"],6)
    prior=prior_c5()
    crossed=[]
    for c in cc:
        sl=[x for x in allrows if x["sha256"]==c["sha256"]]
        result={mode:dict(solved=sum(x["status"]!="TIMEOUT" for x in sl
                                            if x["mode"]==mode),
                 PAR2_s=round(sum(x["par2_s"] for x in sl
                                            if x["mode"]==mode),6))
                     for mode in MODES}
        early_native=[]
        for rep in range(REPS):
            for mode in CONTROL_MODES:
                early=prior[(c["sha256"],rep,mode,5000)]
                terminal=complete[(c["sha256"],rep)][mode]
                early_native.append(dict(rep=rep,mode=mode,
                    early_status=early["bounded_status"],
                    conflicts=early["native_stats"]["conflicts"] if early["native_stats"] else None,
                    decisions=early["native_stats"]["decisions"] if early["native_stats"] else None,
                    propagations=early["native_stats"]["propagations"] if early["native_stats"] else None,
                    final_status=terminal["status"],final_PAR2_s=terminal["par2_s"]))
        crossed.append(dict(gbd=c["gbd"],sha256=c["sha256"],
            source_control=c["control"],results=result,
            early5000_linked_same_seed=early_native))
    result=dict(protocol=PROTO,run_sha=os.getenv("GITHUB_SHA","LOCAL"),
         cohort="four C4 chosen positives + two previous C5 no-duplicate source controls",
         development_not_blind=True,sources=6,repetitions=REPS,
         modes=list(MODES),end_to_end_real_sat_unsat=True,
         cap_s=CAP,paired_source_seed_groups=len(complete),trials=len(allrows),
         original_SAT_models_checked=True,UNSAT_independent_LRAT=False,
         no_auto_promotion=True, C5_bounded_prior_run=42520894229,
         C2_frozen_binary_control=True,
         scores=scores,per_source=crossed)
    OUT.mkdir(exist_ok=True)
    (OUT/"report.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("C6_FINAL",json.dumps({k:v for k,v in result.items()
          if k!="per_source"},sort_keys=True),flush=True)
if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=("verify","selftest","shard","audit"))
    ap.add_argument("--shard",type=int,default=0)
    z=ap.parse_args()
    if z.action=="verify":
        print("C6_FROZEN_SIX_ORIGINAL_SHA_PASS",len(sources()),flush=True)
    elif z.action=="selftest":parity_selftest()
    elif z.action=="shard":shard(z.shard)
    else:audit()
