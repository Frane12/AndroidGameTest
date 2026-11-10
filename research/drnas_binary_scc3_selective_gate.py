#!/usr/bin/env python3
"""DRNAS BINARY-SCC3: selective source SCC gate and matched no-op probe.
Previously seen 17 frozen SHA; mechanism test, NOT BLIND.
Gate: >=64 proven aliases, >=8% variables, >=2% affected literals.
Includes full source-feature screening in gate/probe E2E budgets.
Independent original Tarjan/map/clause replay and model lift from SCC2.
UNSAT requires original Kissat+CaDiCaL agreement, no independent LRAT.
"""
from __future__ import annotations
import argparse,collections,json,os,pathlib,random,time
import drnas_binary_scc2_e2e as s2
import drnas_binary_scc1_source_audit as s1
import drnas_equiv9_prospective_seed_holdout as e9

ROOT=pathlib.Path("mre_binary_scc3")
PROTO="BINARY-SCC3-17SHA-SOURCE-GATED-PROBE-8ARM-2REP-15SEC-v1"
ARMS=tuple(f"{backend}_{mode}" for backend in ("kissat","cadical")
           for mode in ("orig","clean","probe","gate"))
CAP=15.0
SMOKE_CAP=6.0
REPS=2
SHARDS=6
EXPECTED=17*REPS*len(ARMS)
MIN_ALIASES=64
MIN_VAR_FRAC=.08
MIN_HIT_FRAC=.02

def need(v,why):
    if not v:raise RuntimeError("SCC3_FAIL_CLOSED "+str(why))

def dump(p,data):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")

def cases():
    cs=s2.verify()["cases"]
    need(len(cs)==17,"frozen SCC2 cohort drift")
    return cs

def features(c):
    src=e9.SOURCE/c["filename"]
    need(e9.digest(src)==c["sha256"],"original SHA changed")
    n,clauses=e9.x22.read_cnf(src)
    graph,_,_=s1.independent_graph(n,clauses)
    comp,_=s1.independent_tarjan(graph)
    mapping,conflicts,_=s1.verified_alias_map(comp,n)
    need(not conflicts,"contradictory 2-SAT core: no LRAT")
    need(len(mapping)==s2.EXPECTED_ALIASES.get(c["sha256"],0),
         "independent alias count differs from SCC1")
    altered={a for a,b in mapping}
    touched=sum(abs(l) in altered for cl in clauses for l in cl)
    lit_total=sum(len(cl) for cl in clauses)
    eligible=(len(mapping)>=MIN_ALIASES and
              len(mapping)/max(1,n)>=MIN_VAR_FRAC and
              touched/max(1,lit_total)>=MIN_HIT_FRAC)
    return dict(vars=n,clauses=len(clauses),aliases=len(mapping),
        affected_literals=touched,total_literals=lit_total,
        eligible=eligible)

def all_signals(cs):
    return {c["sha256"]:features(c) for c in cs}

def freeze():
    ROOT.mkdir(parents=True,exist_ok=True)
    cs=cases()
    signal=all_signals(cs)
    m=dict(protocol=PROTO,cases=cs,signals=signal,arms=list(ARMS),
        trial_count=EXPECTED,cap_s=CAP,reps=REPS,shards=SHARDS,
        smoke_cap_s=SMOKE_CAP,smoke_originals=6,
        aliases_threshold=MIN_ALIASES,
        var_fraction_threshold=MIN_VAR_FRAC,lit_fraction_threshold=MIN_HIT_FRAC,
        experimental_previously_seen_not_blind=True,
        one_logical_CPU=True,no_parallel_child_solvers=True,
        source_SHA_unchanged=True,independent_original_Tarjan=True,
        independent_clause_replay=True,SAT_original_model_lift=True,
        independent_UNSAT_LRAT=False,clean_control=True,
        same_source_screen_probe=True,no_auto_promotion=True,
        predecessor_manifest_SHA=e9.digest(s2.ROOT/"manifest.json"),
        code_SHA=e9.digest(__file__),
        native_reducer_SHA=e9.digest(s2.BIN),solver_binaries=s2.bins())
    dump(ROOT/"manifest.json",m)
    verify()
    print("SCC3_FROZEN "+json.dumps(dict(sources=len(cs),
        eligible_SHA=[c["sha256"] for c in cs if signal[c["sha256"]]["eligible"]],
        alias_positive=[(c["sha256"][:12],signal[c["sha256"]]["aliases"])
                for c in cs if signal[c["sha256"]]["aliases"]>0],
        trials=EXPECTED,smoke_trials=6*len(ARMS)),
        sort_keys=True),flush=True)

def verify():
    cs=cases()
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["cases"]==cs and
         m["arms"]==list(ARMS) and m["trial_count"]==EXPECTED and
         m["cap_s"]==CAP and m["reps"]==REPS and m["shards"]==SHARDS and
         m["aliases_threshold"]==MIN_ALIASES and
         m["var_fraction_threshold"]==MIN_VAR_FRAC and
         m["lit_fraction_threshold"]==MIN_HIT_FRAC,
         "manifest changed")
    need(m["predecessor_manifest_SHA"]==e9.digest(s2.ROOT/"manifest.json")
         and m["code_SHA"]==e9.digest(__file__)
         and m["native_reducer_SHA"]==e9.digest(s2.BIN)
         and m["solver_binaries"]==s2.bins(),"scripts/binaries changed")
    need(m["signals"]==all_signals(cs),"source feature drift")
    return m

def attempt(c,rep,arm,cap):
    need(arm in ARMS and rep in (0,1) and cap in (CAP,SMOKE_CAP),
         "invalid trial key")
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    start=time.perf_counter();parent_cpu_start=time.process_time()
    backend,mode=arm.split("_")
    scr=None;chosen=arm
    if mode in ("probe","gate"):
        scr=features(c)
        enabled=(mode=="gate" and scr["eligible"])
        chosen=backend+("_scc" if enabled else "_orig")
    else:enabled=False
    prep=time.perf_counter()-start
    remain=cap-prep
    need(remain>.1,"gate preprocessing exhausted budget")
    result=s2.trial(c,rep,chosen,cap=remain)
    wall=time.perf_counter()-start
    status=result["status"]
    witness=result["SAT_original_witness_verified"]
    if wall>=cap:status="TIMEOUT";witness=False
    need(status!="SAT" or witness,"SAT original model invalid")
    return dict(protocol=PROTO,sha256=c["sha256"],gbd=c["gbd"],rep=rep,
        arm=arm,selected_arm=chosen,gate_applied=enabled,features=scr,
        cap_s=cap,status=status,SAT_original_witness_verified=
        bool(witness if status=="SAT" else False),UNSAT_independent_LRAT=False,
        original_sha256_verified=result["original_sha256_verified"],
        original_source_unchanged=result["original_input_unchanged"],
        no_parallel_child_solvers=not result["concurrent_solver_children"],
        one_logical_CPU=cpu,validated_aliases=result["validated_aliases"],
        screen_E2E_s=round(prep,6),wall_E2E_s=round(wall,6),
        reduction_proof_E2E_s=result["reducer_plus_proof_E2E_s"],
        child_CPU_s=result["child_CPU_s"],
        parent_CPU_s=round(result["parent_CPU_s"]+
                            time.process_time()-parent_cpu_start-
                            result["parent_CPU_s"],6))

def selftest():
    ROOT.mkdir(parents=True,exist_ok=True)
    s2.selftest()
    cs=cases()
    assert len(cs)==17
    sig=all_signals(cs)
    need({k:v["aliases"] for k,v in sig.items() if v["aliases"]}==
         s2.EXPECTED_ALIASES,"source-alias selftest disagreement")
    print("SCC3_SELFTEST_PASS "+json.dumps(dict(
        exhaustive_2SAT_quotient_selftests=True,
        independent_Tarjan_reproduces_17_SHA=True,
        zero_new_UNSAT_proof_claims=True),sort_keys=True),flush=True)

def smoke():
    m=verify(); cs=m["cases"];sig=m["signals"]
    pos=sorted([c for c in cs if sig[c["sha256"]]["aliases"]>0],
               key=lambda c:c["sha256"])
    zeros=sorted([c for c in cs if sig[c["sha256"]]["aliases"]==0],
                 key=lambda c:c["sha256"])
    need(len(pos)==3 and len(zeros)>=3,"smoke source strata")
    chosen=pos+zeros[:3];rows=[]
    for c in chosen:
        for arm in ARMS:
            row=attempt(c,0,arm,SMOKE_CAP)
            rows.append(row);dump(ROOT/"smoke.json",rows)
            print("SCC3_SMOKE_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==48,"smoke paired incomplete")
    print("SCC3_SMOKE_PASS "+json.dumps(dict(sources=6,trials=len(rows),
        gate_activations=sum(r["gate_applied"] for r in rows)),sort_keys=True),
        flush=True)

def shard(idx):
    m=verify()
    need(idx in range(SHARDS),"bad shard")
    cs=[c for i,c in enumerate(m["cases"]) if i%SHARDS==idx]
    rows=[]
    for c in cs:
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(c["sha256"]+"SCC3"+str(rep)).shuffle(arms)
            for arm in arms:
                r=attempt(c,rep,arm,CAP)
                r["shard"]=idx
                need(r["wall_E2E_s"]<=CAP+.1,"E2E limit")
                rows.append(r);dump(ROOT/f"shard-{idx}.json",rows)
                print("SCC3_TRIAL "+json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==len(cs)*REPS*len(ARMS),"shard incomplete")
    print("SCC3_SHARD_PASS "+json.dumps(dict(idx=idx,
        cases=len(cs),trials=len(rows)),sort_keys=True),flush=True)

def audit():
    m=verify();cs=m["cases"];known={c["sha256"]:c for c in cs}
    rows=[]
    for idx in range(SHARDS):
        r=json.loads((ROOT/f"shard-{idx}.json").read_text())
        need(len(r)==len([c for i,c in enumerate(cs) if i%SHARDS==idx])*
             REPS*len(ARMS),"shard count")
        rows+=r
    expected={(c["sha256"],rep,arm) for c in cs for rep in range(REPS)
              for arm in ARMS}
    actual={(r["sha256"],r["rep"],r["arm"]) for r in rows}
    need(len(rows)==len(actual)==len(expected)==EXPECTED and
         actual==expected,"SHA pairing mismatch")
    bysha=collections.defaultdict(list)
    for r in rows:
        need(r["protocol"]==PROTO and r["cap_s"]==CAP and
             r["original_sha256_verified"] and r["original_source_unchanged"]
             and r["no_parallel_child_solvers"] and
             r["wall_E2E_s"]<=CAP+.1 and
             r["status"] in ("SAT","UNSAT","TIMEOUT") and
             (r["status"]!="SAT" or r["SAT_original_witness_verified"]),
             "invalid trial")
        backend,mode=r["arm"].split("_")
        if mode in ("probe","gate"):
            need(r["features"]==m["signals"][r["sha256"]],
                 "gate feature changed")
            expected_gate=mode=="gate" and r["features"]["eligible"]
            need(r["gate_applied"]==expected_gate and
                r["selected_arm"]==backend+("_scc" if expected_gate else "_orig"),
                "probe/gate routing corrupted")
        else:
            need(r["features"] is None and r["selected_arm"]==r["arm"],
                 "reference routing modified")
        bysha[r["sha256"]].append(r)
    agreed=set()
    for sha,rr in bysha.items():
        statuses={r["status"] for r in rr if r["status"]!="TIMEOUT"}
        need(len(statuses)<=1,"SAT/UNSAT conflicting original source "+sha)
        if any(r["arm"]=="kissat_orig" and r["status"]=="UNSAT" for r in rr) and \
           any(r["arm"]=="cadical_orig" and r["status"]=="UNSAT" for r in rr):
            agreed.add(sha)
    def ok(r):return r["status"]=="SAT" or \
           (r["status"]=="UNSAT" and r["sha256"] in agreed)
    def par(r):return r["wall_E2E_s"] if ok(r) else 2*CAP
    def score(rr):
        return dict(n=len(rr),solved=sum(ok(r) for r in rr),
            SAT_verified=sum(r["status"]=="SAT" for r in rr),
            UNSAT_original_agreement_no_LRAT=sum(
                r["status"]=="UNSAT" and ok(r) for r in rr),
            UNSAT_unverified=sum(r["status"]=="UNSAT" and not ok(r) for r in rr),
            TIMEOUT=sum(r["status"]=="TIMEOUT" for r in rr),
            PAR2_s=round(sum(par(r) for r in rr),6),
            child_CPU_s=round(sum(r["child_CPU_s"] for r in rr),6),
            parent_CPU_s=round(sum(r["parent_CPU_s"] for r in rr),6),
            wall_total_s=round(sum(r["wall_E2E_s"] for r in rr),6),
            screen_E2E_s=round(sum(r["screen_E2E_s"] for r in rr),6),
            reduction_proof_E2E_s=round(sum(r["reduction_proof_E2E_s"] for r in rr),6),
            gate_activations=sum(r["gate_applied"] for r in rr))
    scores={a:score([r for r in rows if r["arm"]==a]) for a in ARMS}
    paired={}
    for backend in ("kissat","cadical"):
        for mode in ("orig","clean","probe","gate"):
            a=f"{backend}_{mode}"
            scores[a]["speedup_vs_original_PAR2_x"]=round(
                scores[backend+"_orig"]["PAR2_s"]/scores[a]["PAR2_s"],6)
            scores[a]["speedup_vs_probe_PAR2_x"]=round(
                scores[backend+"_probe"]["PAR2_s"]/scores[a]["PAR2_s"],6)
            if mode=="orig":continue
            delta=[]
            for sha,rr in bysha.items():
                for rep in range(REPS):
                    one=next(r for r in rr if r["arm"]==a and r["rep"]==rep)
                    ref=next(r for r in rr if r["arm"]==backend+"_orig"
                             and r["rep"]==rep)
                    delta.append(par(one)-par(ref))
            paired[a]=dict(wins=sum(x<-.02 for x in delta),
                losses=sum(x>.02 for x in delta),
                ties=sum(abs(x)<=.02 for x in delta),
                best_gain_s=round(min(delta),6),
                worst_regression_s=round(max(delta),6))
    elig={sha for sha,s in m["signals"].items() if s["eligible"]}
    report=dict(protocol=PROTO,source_count=17,trials=EXPECTED,
        not_blind=True,no_auto_promotion=True,one_logical_CPU=True,
        original_SHA_unchanged=True,
        independent_original_Tarjan_alias_check=True,
        independent_clause_replay_and_model_lift=True,
        independent_UNSAT_LRAT=False,
        UNSAT_original_reference_agreement=sorted(agreed),
        source_only_gate_eligible=sorted(elig),
        scores=scores,paired_vs_original=paired,
        by_gate_class={name:{a:score([r for r in rows if r["arm"]==a and
                                       (r["sha256"] in elig)==which])
                             for a in ARMS}
            for name,which in (("eligible",True),("ineligible",False))},
        per_shard={str(i):{a:score([r for r in rows if r["arm"]==a and
                                    r["shard"]==i]) for a in ARMS}
                   for i in range(SHARDS)},
        per_sha={sha:dict(gbd=known[sha]["gbd"],signals=m["signals"][sha],
                 arms={a:[dict(rep=r["rep"],status=r["status"],
                              time_s=r["wall_E2E_s"])
                          for r in rr if r["arm"]==a]
                       for a in ARMS}) for sha,rr in bysha.items()})
    dump(ROOT/"report.json",report)
    print("SCC3_FINAL "+json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","verify","smoke","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    if args.action=="shard":shard(args.shard)
    else:
        {"selftest":selftest,"freeze":freeze,"verify":verify,
         "smoke":smoke,"audit":audit}[args.action]()
        if args.action=="verify":print("SCC3_VERIFY_PASS",flush=True)
