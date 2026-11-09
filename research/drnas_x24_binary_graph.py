#!/usr/bin/env python3
"""DRNAS X24: observe directed literal-implication SCC evolution, not binary counts.

Kissat continues on pinned CPU A. Native signed graph scout runs on CPU B.
If original CNF graph has compelling *actual* SCC aliases, replay-verified X22
C++ reducer runs before CaDiCaL; otherwise CaDiCaL starts on source CNF.
This is a REPLAY of X21/X22 sources, not a new blinded holdout.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import os
import pathlib
import random
import subprocess
import tempfile
import time

import drnas_x22_parallel_reducer as x22

ROOT=pathlib.Path("mre_x24")
SCOUT=ROOT/"bin/graph_scout"
PROTO="DRNAS-X24-BINARY-IMPLICATION-SCC-24SHA-7ARM-2REP-15S-20261109-v1"
ARMS=("kissat1","cadical1","race_original","race_quotient",
      "graph_shadow","graph_any","graph_strict")
CAP=15.0
REPS=2
SHARDS=8
EXPECTED=24*REPS*len(ARMS)

def need(ok,message):
    if not ok:raise RuntimeError("X24_FAIL_CLOSED "+str(message))
def save(path,obj):
    x22.save(path,obj)
def digest(path):
    return x22.digest(path)
def decision(graph,arm):
    need(arm in ("graph_shadow","graph_any","graph_strict"),"invalid arm")
    if arm=="graph_shadow":
        return "original","shadow_observe_only"
    if not graph:
        return "original","scanner_failed_safe_original_fallback"
    snapshots=graph["checkpoints"]
    need(len(snapshots)==4,"graph checkpoints missing")
    last=snapshots[-1]
    aliases=last["signed_alias_candidates"]
    contradiction=last["contradictory_variables"]>0
    if contradiction:
        return "original","contradictory_binary_scc_abstain"
    if aliases==0:
        return "original","no_signed_scc_alias"
    if arm=="graph_any":
        return "quotient","at_least_one_source_signed_scc_alias"
    variables=graph["source_vars"]
    # Strongly preregistered gate: not just a count of binary clauses.
    if aliases>=8 and (aliases>=32 or aliases>=0.005*max(1,variables)):
        return "quotient","large_certifiable_signed_scc_component_gain"
    return "original","weak_signed_scc_alias_yield"

def graph_valid(g):
    need(g["source_only"] and g["graph_monotone_edges"],"graph provenance")
    need(g["checkpoint_fractions"]==[0.25,0.5,0.75,1.0],"checkpoint geometry")
    cs=g["checkpoints"]
    need(len(cs)==4 and cs[-1]["clauses"]==g["source_clauses"],
         "incomplete graph scan")
    need(all(a["clauses"]<=b["clauses"] and a["edges"]<=b["edges"] and
             a["signed_alias_candidates"]<=b["signed_alias_candidates"]
             for a,b in zip(cs,cs[1:])),
         "nonmonotone graph evidence")
    return g

def backend_hashes():
    return dict(kissat=digest(x22.KISSAT),cadical=digest(x22.CADICAL),
                reducer=digest(x22.BIN),scout=digest(SCOUT))
def freeze():
    m22=x22.verify_frozen()
    ROOT.mkdir(exist_ok=True)
    cases=[{k:c[k] for k in ("filename","sha256","gbd","year")}
           for c in m22["cases"]]
    save(ROOT/"manifest.json",dict(
        protocol=PROTO,cases=cases,
        arms=ARMS,cap_s=CAP,reps=REPS,shards=SHARDS,expected_trials=EXPECTED,
        predecessor_X22_run=42591977333,
        source_SHA_unchanged=True,former_X21_holdout_reused_not_blind=True,
        no_auto_promotion=True,independent_UNSAT_LRAT=False,
        cpu_budget="two pinned Linux logical CPUs",
        graph_model="signed 2-literal directed implication graph from original CNF",
        checkpoints=[0.25,0.5,0.75,1.0],
        graph_any="any >=1 equivalent variable via graph SCC",
        graph_strict=">=8 aliases and (>=32 aliases or >=0.5% of source vars)",
        graph_shadow="pay for graph monitoring but solve original on CPU B",
        x22_manifest_sha256=digest(x22.ROOT/"manifest.json"),
        original_shas=[c["sha256"] for c in cases],
        code_sha256=digest(__file__),
        binary_sha256=backend_hashes(),
        proof_contract="C++ graph signal only; separate X22 original-CNF edge-path replay "
                       "must certify every alias before any transformed solver"))
    verify()
    print("X24_FROZEN",json.dumps(dict(sources=len(cases),trials=EXPECTED,
        arms=ARMS,protocol=PROTO),sort_keys=True),flush=True)
def verify():
    m22=x22.verify_frozen()
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["arms"]==list(ARMS)
         and len(m["cases"])==24 and m["expected_trials"]==EXPECTED,
         "manifest drift")
    need(m["binary_sha256"]==backend_hashes() and
         m["code_sha256"]==digest(__file__) and
         m["x22_manifest_sha256"]==digest(x22.ROOT/"manifest.json"),
         "binary/code/reference SHA drift")
    need(m["original_shas"]==[c["sha256"] for c in m22["cases"]],
         "source SHA roster drift")
    return m

def graph_trial(case,rep,arm):
    need(arm in ("graph_shadow","graph_any","graph_strict"),"graph arm")
    src=x22.ROOT/"cases"/case["filename"]
    need(digest(src)==case["sha256"],"original CNF SHA mismatch")
    cpu=x22.cpus()
    start=time.perf_counter()
    before=x22.child_cpu()
    status="TIMEOUT";winner=None;sat_verified=False
    graph={};reducer={};aliases={};reason="not_done";chosen="original"
    scout_s=0.0;reducer_s=0.0;cadical_started=False;error=""
    with tempfile.TemporaryDirectory(dir=ROOT) as td:
        tmp=pathlib.Path(td)
        entries=[];scout=None;helper=None
        try:
            n,original=x22.read_cnf(src)
            entries.append(x22.launch("kissat",
                [x22.KISSAT,"--seed="+str(x22.seed(case,rep)),src],cpu[0],td))
            scout=x22.launch("graph_scout",[SCOUT,src],cpu[1],td)
            entries.append(scout)
            while time.perf_counter()-start<CAP:
                for e in entries:
                    if e["read"] or e["p"].poll() is None:continue
                    e["read"]=True
                    stdout,stderr=x22.read_output(e)
                    if e is scout:
                        scout_s=time.perf_counter()-start
                        if e["p"].returncode!=0:
                            reason="graph_probe_failed"
                            error=stderr[-300:]
                            chosen="original"
                        else:
                            records=[s[len("X24_GRAPH "):] for s in stdout.splitlines()
                                     if s.startswith("X24_GRAPH ")]
                            need(len(records)==1,"graph scout telemetry missing")
                            graph=graph_valid(json.loads(records[0]))
                            need(graph["source_clauses"]==len(original) and
                                 graph["source_vars"]==n,"graph input mismatch")
                            chosen,reason=decision(graph,arm)
                        if time.perf_counter()-start>=CAP-.03:
                            break
                        if chosen=="original":
                            entries.append(x22.launch("cadical",[x22.CADICAL,src],cpu[1],td))
                            cadical_started=True
                        else:
                            helper=x22.launch("cpp_reducer",
                                [x22.BIN,"quotient",src,tmp/"reduced.cnf",
                                 tmp/"aliases.map"],cpu[1],td)
                            entries.append(helper)
                        break
                    if e is helper:
                        reducer_s=time.perf_counter()-start
                        if e["p"].returncode!=0:
                            error=stderr[-300:];reason="reducer_failed_original_fallback"
                            chosen="original"
                        else:
                            records=[s[len("X22_REDUCER "):] for s in stdout.splitlines()
                                     if s.startswith("X22_REDUCER ")]
                            need(len(records)==1,"reducer telemetry missing")
                            reducer=json.loads(records[0])
                            aliases=x22.parse_map(tmp/"aliases.map",n)
                            x22.proof_replay(original,aliases)
                            need(digest(src)==case["sha256"],
                                 "source mutated while graph/reducer ran")
                        if time.perf_counter()-start<CAP-.03:
                            destination=(tmp/"reduced.cnf") if chosen=="quotient" else src
                            added=x22.launch("cadical",[x22.CADICAL,destination],cpu[1],td)
                            added["aliases"]=aliases if chosen=="quotient" else {}
                            entries.append(added);cadical_started=True
                        break
                    verdict,proof=x22.solver_result(e["name"],e["p"].returncode,
                        stdout,original,e.get("aliases",{}))
                    winner=e["name"];status=verdict;sat_verified=proof
                    break
                if winner:break
                if all(e["read"] for e in entries):break
                time.sleep(.003)
        finally:x22.cleanup(entries)
    elapsed=time.perf_counter()-start
    if elapsed>CAP or status not in ("SAT","UNSAT"):
        status="TIMEOUT";winner=None;sat_verified=False
    return dict(status=status,winner=winner,
        SAT_original_witness_verified=sat_verified,
        UNSAT_independent_LRAT=False,
        graph=graph,graph_reason=reason,graph_route=chosen,
        scan_E2E_s=round(scout_s,6),reducer_E2E_s=round(reducer_s,6),
        reducer=reducer,aliases_replayed=len(aliases),cadical_launched=cadical_started,
        error=error,
        E2E_s=round(elapsed,6),child_CPU_s=round(x22.child_cpu()-before,6))

def trial(case,rep,arm):
    need(arm in ARMS and rep in (0,1),"invalid arm/rep")
    started=time.perf_counter()
    before=x22.child_cpu()
    if arm.startswith("graph_"):
        result=graph_trial(case,rep,arm)
    else:
        # Identical frozen X22 reference implementation.
        old_cap=x22.CAP
        try:
            x22.CAP=CAP
            r=x22.trial(case,rep,arm)
        finally:
            x22.CAP=old_cap
        result=dict(status=r["status"],winner=r.get("winner"),
            SAT_original_witness_verified=r["SAT_original_witness_verified"],
            UNSAT_independent_LRAT=False,graph={},graph_reason="reference",
            graph_route=arm,scan_E2E_s=0.0,reducer_E2E_s=0.0,
            reducer=r.get("reducer",{}),aliases_replayed=r["aliases_replayed"],
            cadical_launched=r["second_solver_launched"],error="",
            E2E_s=r["E2E_s"],child_CPU_s=r["child_cpu_s"])
    wall=time.perf_counter()-started
    # Include wrapper cost in strict E2E cap.
    result["E2E_s"]=round(wall,6)
    result["child_CPU_s"]=round(x22.child_cpu()-before,6)
    if wall>CAP or result["status"] not in ("SAT","UNSAT"):
        result["status"]="TIMEOUT";result["winner"]=None
        result["SAT_original_witness_verified"]=False
    result.update(protocol=PROTO,arm=arm,rep=rep,
        original_sha256=case["sha256"],gbd=case["gbd"],
        seed=x22.seed(case,rep),cap_s=CAP,
        provisional_PAR2_s=round(wall if result["status"] in ("SAT","UNSAT")
                                else 2*CAP,6))
    return result

def shard(index):
    m=verify()
    need(0<=index<SHARDS,"invalid shard index")
    rows=[]
    for c in m["cases"][index::SHARDS]:
        for rep in range(REPS):
            order=list(ARMS)
            random.Random(x22.seed(c,rep)).shuffle(order)
            for arm in order:
                r=trial(c,rep,arm)
                rows.append(r)
                save(ROOT/("shard-%d.json"%index),rows)
                print("X24_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==42,"incomplete paired shard")
    print("X24_SHARD_PASS",index,len(rows),flush=True)

def audit():
    verify()
    rows=[]
    for shard_index in range(SHARDS):
        group=json.loads((ROOT/("shard-%d.json"%shard_index)).read_text())
        need(len(group)==42,"incomplete shard")
        rows.extend(group)
    need(len(rows)==EXPECTED,"trial count")
    keys=set();bycase=collections.defaultdict(list)
    for r in rows:
        key=(r["original_sha256"],r["rep"],r["arm"])
        need(key not in keys and r["protocol"]==PROTO and
             r["cap_s"]==CAP and r["arm"] in ARMS,"protocol or duplicate row")
        keys.add(key);bycase[r["original_sha256"]].append(r)
        if r["status"]=="SAT":
            need(r["SAT_original_witness_verified"],"unverified SAT witness")
    need(len(keys)==EXPECTED,"coverage count")
    agreement={}
    for source,group in bycase.items():
        verdicts={r["status"] for r in group if r["status"]!="TIMEOUT"}
        need(len(verdicts)<=1,"SAT vs UNSAT contradiction")
        unsat_refs={r["arm"] for r in group
                    if r["status"]=="UNSAT" and
                    r["arm"] in ("kissat1","cadical1")}
        agreement[source]=len(unsat_refs)==2
    summary={}
    for arm in ARMS:
        subset=[r for r in rows if r["arm"]==arm]
        accepted=[r for r in subset if r["status"]=="SAT" or
                  (r["status"]=="UNSAT" and agreement[r["original_sha256"]])]
        summary[arm]=dict(trials=len(subset),accepted_solved=len(accepted),
           SAT_verified=sum(r["status"]=="SAT" for r in accepted),
           UNSAT_2original_solver_agreement_no_LRAT=sum(
               r["status"]=="UNSAT" for r in accepted),
           unconfirmed_UNSAT=sum(r["status"]=="UNSAT" and r not in accepted for r in subset),
           PAR2_s=round(sum(r["E2E_s"] if r in accepted else 2*CAP for r in subset),5),
           child_CPU_s=round(sum(r["child_CPU_s"] for r in subset),5),
           graph_selected_quotient=sum(r["graph_route"]=="quotient" for r in subset),
           graph_original_fallback=sum(r["graph_route"]=="original" for r in subset),
           observed_aliases=sum(r.get("graph",{}).get("checkpoints",[{}])[-1]
                                .get("signed_alias_candidates",0) for r in subset),
           reducer_aliases=sum(r["aliases_replayed"] for r in subset))
    baseline=summary["race_original"]["PAR2_s"]
    for value in summary.values():
        value["PAR2_delta_vs_two_solver_race_pct"]=round(
             100*(value["PAR2_s"]/baseline-1),4) if baseline else None
    report=dict(protocol=PROTO,rows=EXPECTED,scores=summary,
        agreement=agreement,from_replayed_X21_holdout_not_blind=True,
        UNSAT_independent_LRAT=False,
        graph_experiment="directed signed literal SCC trajectories at quarters",
        original_source_SHA_unchanged=True)
    save(ROOT/"report.json",report)
    print("X24_FINAL",json.dumps(summary,sort_keys=True),flush=True)

def selftest():
    examples=[
        ("no_edges",2,[(1,),(2,)],0),
        ("positive_equivalence",2,[(-1,2),(1,-2)],1),
        ("negative_equivalence",2,[(1,2),(-1,-2)],1),
        ("positive_chain_cycle",3,[(-1,2),(-2,3),(-3,1)],2),
        ("no_cycles",3,[(-1,2),(-2,3)],0),
        ("negative_self_cycle",1,[(1,1),(-1,-1)],0)]
    checked=0
    with tempfile.TemporaryDirectory() as td:
        p=pathlib.Path(td)/"case.cnf"
        for name,n,clauses,expected in examples:
            p.write_text("p cnf %d %d\n"%(n,len(clauses))+
                "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
            before=digest(p)
            proc=subprocess.run([str(SCOUT),str(p)],text=True,
                                capture_output=True)
            need(proc.returncode==0,"scout "+name+": "+proc.stderr)
            record=[s[len("X24_GRAPH "):] for s in proc.stdout.splitlines()
                    if s.startswith("X24_GRAPH ")]
            need(len(record)==1,"missing graph telemetry")
            data=graph_valid(json.loads(record[0]))
            need(data["checkpoints"][-1]["signed_alias_candidates"]==expected,
                 "incorrect graph equivalence count "+name)
            need(digest(p)==before,"source mutated")
            checked+=1
    print("X24_SELFTEST_PASS",checked,"graph SCC cases with dynamic checkpoints",flush=True)
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("freeze","shard","audit","selftest"))
    parser.add_argument("--shard",type=int,default=0)
    args=parser.parse_args()
    if args.action=="shard":shard(args.shard)
    else:globals()[args.action]()
