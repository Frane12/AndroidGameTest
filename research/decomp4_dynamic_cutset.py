#!/usr/bin/env python3
"""DRNAS DECOMP4: bounded *conditional* cutset screening after 1 or 2
source-selected decision assignments followed by exact Boolean UP.

This is a proxy for early CDCL decision prefixes, NOT live CDCL trail
instrumentation and NOT a SAT/UNSAT performance benchmark. Under each
decision prefix, UP conditionally preserves the original CNF semantics.
A detected component split applies only under its assumptions.

72 frozen EQUIV2/EQUIV7 originals, one logical CPU, SHA matched;
two equal-budget source-only decision policies (impact and SHA control),
with matched signs, depth-1 and depth-2. No SAT/UNSAT claims or PAR2.
"""
import argparse
import collections
import hashlib
import itertools
import json
import math
import os
import pathlib
import random
import time

import dmd1_bench as d1
import decomp2_exact_bench as d2
import decomp3_rootup_screen as d3

ROOT=pathlib.Path("mre_decomp4")
PROTO="DRNAS-DECOMP4-DECISION-UP-CUTSET-72-SHA-SCREEN-v1"
SHARDS=4
CASE_BUDGET=3.0
PER_POLICY=1.25
PER_PROBE=.42
ROOT_UP_BUDGET=.75
FIRST=4

def must(v,reason):
    if not v:raise RuntimeError("DECOMP4_FAIL_CLOSED "+str(reason))

def affinity():
    c=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{c})
    return c

def initial_sources():
    entries,duplicates=d3.source_cases()
    must(len(entries)==72 and duplicates==0,"EQUIV2/EQUIV7 source union drift")
    return entries

def freeze():
    affinity();ROOT.mkdir(exist_ok=True)
    cases=initial_sources()
    meta=dict(protocol=PROTO,cases=cases,source_count=len(cases),
              selection="all 72 exact frozen original SHA; no solver outcomes",
              policies=["impact_source_short_clause_score","SHA_seeded_random_control"],
              depth1_variables=FIRST,depth2_pairs=1,
              polarity_branches_both=True,seconds_per_policy=PER_POLICY,
              case_budget_s=CASE_BUDGET,
              original_SHA_verified=True,
              not_globally_unseen=True,not_live_CDCL=True,
              no_SAT_UNSAT_claims=True,no_automatic_promotion=True)
    (ROOT/"freeze.json").write_text(json.dumps(meta,indent=2,sort_keys=True)+"\n")
    print("DECOMP4_FREEZE_PASS "+json.dumps(dict(
        original_sources=len(cases),sha_unique=True,
        cohort_counts=dict(collections.Counter(c["cohort"] for c in cases)),
        trial_mode="conditional_UP_graph_only",seconds_per_policy=PER_POLICY),
        sort_keys=True),flush=True)

def frozen():
    m=json.loads((ROOT/"freeze.json").read_text())
    must(m["protocol"]==PROTO and len(m["cases"])==72,
         "frozen protocol/size changed")
    cases=initial_sources()
    must([c["sha256"] for c in cases]==[c["sha256"] for c in m["cases"]],
         "frozen SHA list changed")
    return m["cases"]

def root_component(cs):
    if not cs:return [],0,0
    groups=d2.components(cs)
    groups.sort(key=lambda g:(-len(g),g[0]))
    main=[cs[i] for i in groups[0]]
    return main,len(groups),len(groups[0])

def heuristic_vars(clauses,sha):
    """Uses source geometry only; never SAT status and no previous result."""
    degree=collections.Counter()
    short=collections.Counter()
    for c in clauses:
        vars_=set(abs(l) for l in c)
        for v in vars_:
            degree[v]+=1
            if len(vars_)<=3:short[v]+=1
    if not degree:return [],[]
    vars_=list(degree)
    impact=sorted(vars_,key=lambda v:(
      -4*short[v]-degree[v],-short[v],-degree[v],v))[:FIRST]
    randomized=sorted(vars_)
    random.Random("DECOMP4-SHA-CTRL-"+sha).shuffle(randomized)
    # Same probe count and polarity assignments as the source-derived policy.
    return impact,randomized[:FIRST]

def decision_prefixes(vars_):
    out=[]
    for v in vars_:
        out.append((v,));out.append((-v,))
    if len(vars_)>=2:
        v,w=vars_[0],vars_[1]
        for a in (v,-v):
            for b in (w,-w):
                out.append((a,b))
    return out

def trial_prefix(main,n,decisions,remaining):
    if remaining<=.01:return dict(status="ABSTAIN",reason="budget")
    st,forced,residual,reason=d3.rootup(
        main+[tuple([lit]) for lit in decisions],n,
        seconds=min(PER_PROBE,max(.02,remaining)))
    if st!="OK":
        return dict(status=st,reason=reason,forced=len(forced),
                    parts=[],second=0,strong=False,meaningful=False)
    groups=d2.components(residual)
    parts=sorted((len(g) for g in groups),reverse=True)
    large=parts[1] if len(parts)>1 else 0
    # Distinguish tiny disconnected tails from candidate material improvements.
    base=len(main)
    meaningful=(large>=10 and large>=math.ceil(.001*base))
    strong=(large>=max(30,math.ceil(.01*base)))
    return dict(status="OK",reason="conditional_residual",
         forced=len(forced),remaining_clauses=len(residual),
         parts=parts[:8],second=large,component_count=len(parts),
         strong=strong,meaningful=meaningful)

def scan(case):
    affinity()
    start=time.perf_counter()
    path=pathlib.Path(case["path"])
    must(d1.sha(path)==case["sha256"],"original source SHA drift")
    n,original=d1.read_cnf(path)
    st,root_force,residual,root_reason=d3.rootup(
        original,n,seconds=ROOT_UP_BUDGET)
    result=dict(protocol=PROTO,sha256=case["sha256"],
        cohort=case["cohort"],original_sha_verified=True,
        original_variables=n,original_clauses=len(original),
        root_up_status=st,root_forced=len(root_force),
        root_reason=root_reason,root_components=None,
        root_largest_clauses=None,
        policies={},examined_conditional_prefixes=0,
        meaningful_prefixes=0,strong_prefixes=0,
        SAT_solved=False,UNSAT_solved=False,PAR2_s=None,
        not_live_CDCL=True,one_logical_cpu=True,
        cpu_affinity=sorted(os.sched_getaffinity(0)))
    if st!="OK":
        result["wall_s"]=round(time.perf_counter()-start,6)
        return result
    main,component_count,largest=root_component(residual)
    result.update(root_components=component_count,
                  root_largest_clauses=largest,
                  residual_clause_count=len(residual))
    impact,control=heuristic_vars(main,case["sha256"])
    policies=[("impact",impact),("control",control)]
    # Randomize policy execution order by SHA before any result is observed,
    # to prevent a systematic advantage under the per-case wall budget.
    random.Random("DECOMP4-POLICY-ORDER-"+case["sha256"]).shuffle(policies)
    for name,vars_ in policies:
        policy_start=time.perf_counter()
        outcomes=[]
        if main:
            for literals in decision_prefixes(vars_):
                if time.perf_counter()-policy_start>=PER_POLICY:break
                if time.perf_counter()-start>=CASE_BUDGET:break
                result["examined_conditional_prefixes"]+=1
                before=time.perf_counter()
                row=trial_prefix(main,n,literals,
                    min(PER_POLICY-(time.perf_counter()-policy_start),
                        CASE_BUDGET-(time.perf_counter()-start)))
                row.update(prefix=list(literals),depth=len(literals),
                           wall_s=round(time.perf_counter()-before,6))
                outcomes.append(row)
        ok=[x for x in outcomes if x["status"]=="OK"]
        meaningful=[x for x in ok if x["meaningful"]]
        strong=[x for x in ok if x["strong"]]
        candidate=max(ok,key=lambda x:(x["second"],-x["depth"]),
                      default=None)
        result["policies"][name]=dict(vars=vars_,probes=len(outcomes),
          completed=len(ok),abstained=sum(x["status"]=="ABSTAIN" for x in outcomes),
          conflict=sum(x["status"]=="CONFLICT" for x in outcomes),
          meaningful=len(meaningful),strong=len(strong),
          max_second_clause_part=candidate["second"] if candidate else 0,
          best_prefix=candidate["prefix"] if candidate else [],
          best_parts=candidate["parts"] if candidate else [],
          wall_s=round(time.perf_counter()-policy_start,6),
          probes_detail=outcomes)
        result["meaningful_prefixes"]+=len(meaningful)
        result["strong_prefixes"]+=len(strong)
    must(d1.sha(path)==case["sha256"],"original SHA mutated")
    result["wall_s"]=round(time.perf_counter()-start,6)
    return result

def bench(shard):
    must(0<=shard<SHARDS,"invalid shard")
    allcases=frozen()
    ROOT.mkdir(exist_ok=True)
    out=[]
    for i,c in enumerate(allcases):
        if i%SHARDS!=shard:continue
        t=scan(c)
        out.append(t)
        (ROOT/("shard-%d.json"%shard)).write_text(
            json.dumps(out,indent=2,sort_keys=True)+"\n")
        # Compact, whole-result rows in artifact, structured summary in log.
        print("DECOMP4_TRIAL "+json.dumps(dict(
          sha256=t["sha256"],cohort=t["cohort"],root=t["root_up_status"],
          main_clauses=t["root_largest_clauses"],root_forced=t["root_forced"],
          policies={k:{x:v for x,v in p.items() if x!="probes_detail"}
                    for k,p in t["policies"].items()},
          elapsed_s=t["wall_s"]),sort_keys=True),flush=True)
    must(len(out)==len(allcases[shard::SHARDS]),"incomplete shard")
    print("DECOMP4_SHARD_PASS",shard,len(out),flush=True)

def audit():
    freeze_data=frozen()
    results=[];per_shard={}
    for i in range(SHARDS):
        path=ROOT/("shard-%d.json"%i)
        must(path.is_file(),"missing shard")
        a=json.loads(path.read_text())
        must(len(a)==len(freeze_data[i::SHARDS]),
             "incomplete shard "+str(i))
        results.extend(a)
        per_shard[str(i)]=dict(
          sources=len(a),
          completed_root=sum(x["root_up_status"]=="OK" for x in a),
          useful_sources=sum(any(p["meaningful"] for p in x["policies"].values())
                             for x in a),
          wall_s=round(sum(x["wall_s"] for x in a),6))
    must(len(results)==72 and len({x["sha256"] for x in results})==72,
         "SHA source count/duplication mismatch")
    must(set(x["sha256"] for x in results)==
         set(x["sha256"] for x in freeze_data),"source set differs")
    must(all(x["protocol"]==PROTO and x["original_sha_verified"]
             and x["one_logical_cpu"] and len(x["cpu_affinity"])==1
             and not x["SAT_solved"] and not x["UNSAT_solved"]
             and x["not_live_CDCL"] and x["PAR2_s"] is None
             for x in results),"audit metadata invalid")
    score={}
    for policy in ("impact","control"):
        p=[(x,y[policy]) for x in results if policy in x["policies"]
           for y in [x["policies"]]]
        score[policy]=dict(
            sources=len(p),probes=sum(y["probes"] for _,y in p),
            completed=sum(y["completed"] for _,y in p),
            conflict=sum(y["conflict"] for _,y in p),
            abstained=sum(y["abstained"] for _,y in p),
            meaningful_prefixes=sum(y["meaningful"] for _,y in p),
            strong_prefixes=sum(y["strong"] for _,y in p),
            sources_with_meaningful=sum(y["meaningful"]>0 for _,y in p),
            sources_with_strong=sum(y["strong"]>0 for _,y in p),
            total_wall_s=round(sum(y["wall_s"] for _,y in p),6))
    winners=[x for x in results if any(p["meaningful"]>0
                                     for p in x["policies"].values())]
    winners.sort(key=lambda x:(-max(p["max_second_clause_part"]
                                   for p in x["policies"].values()),x["sha256"]))
    report=dict(protocol=PROTO,source_count=72,
        source_SHA_verified=True,root_up_pass=sum(x["root_up_status"]=="OK"
                                                   for x in results),
        root_conflict=sum(x["root_up_status"]=="CONFLICT" for x in results),
        root_abstain=sum(x["root_up_status"]=="ABSTAIN" for x in results),
        policy_scores=score,per_shard=per_shard,
        sources_with_any_meaningful=len(winners),
        total_wall_s=round(sum(x["wall_s"] for x in results),6),
        top_candidates=[dict(
          sha=x["sha256"],cohort=x["cohort"],
          root_forced=x["root_forced"],root_largest=x["root_largest_clauses"],
          impact={k:v for k,v in x["policies"].get("impact",{}).items()
                  if k in ("best_prefix","best_parts","max_second_clause_part",
                           "meaningful","strong","probes")},
          control={k:v for k,v in x["policies"].get("control",{}).items()
                  if k in ("best_prefix","best_parts","max_second_clause_part",
                           "meaningful","strong","probes")})
          for x in winners[:12]],
        SAT_solved=0,UNSAT_solved=0,PAR2_s=None,
        not_CDCL_instrumented=True,
        not_globally_unseen=True,no_auto_promotion=True)
    (ROOT/"audit.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("DECOMP4_FINAL "+json.dumps(report,sort_keys=True),flush=True)

def selftest():
    affinity()
    rng=random.Random(46739)
    ntests=0
    for i in range(180):
        n=rng.randrange(2,7)
        clauses=[tuple((1 if rng.randrange(2) else -1)*v
                  for v in rng.sample(range(1,n+1),rng.randrange(1,n+1)))
                  for _ in range(rng.randrange(1,14))]
        x=rng.randrange(1,n+1);sign=rng.choice((-1,1))
        selected=(x*sign,)
        if n>=3 and rng.randrange(2):
            y=rng.choice([z for z in range(1,n+1) if z!=x])
            selected+=(y*rng.choice((-1,1)),)
        st,forced,residual,reason=d3.rootup(
            clauses+[tuple([lit]) for lit in selected],n,seconds=2)
        must(st in ("OK","CONFLICT"),"toy proof timeout")
        for bits in itertools.product((False,True),repeat=n):
            state=dict(zip(range(1,n+1),bits))
            original_sat=(d1.holds(clauses,state) and
                         all(state[abs(l)]==(l>0) for l in selected))
            if st=="CONFLICT":
                must(not original_sat,"branch false UNSAT")
            else:
                predicted=(all(state[v]==b for v,b in forced.items())
                           and d1.holds(residual,state))
                must(predicted==original_sat,"branch residual changes model set")
        if st=="OK":
            comp=d2.components(residual)
            supports=[{abs(l) for j in part for l in residual[j]} for part in comp]
            must(all(not(supports[j]&supports[k])
                     for j in range(len(comp)) for k in range(j+1,len(comp))),
                 "overlapping components")
        ntests+=1
    # Known conditional split: root connected via x=1, x=false leaves 2 parts.
    bridge=[(1,2,4),(1,2,5),(1,3,6),(1,3,7)]
    root=d2.components(bridge)
    st,forced,residual,reason=d3.rootup(bridge+[(-1,)],7,seconds=2)
    parts=sorted((len(x) for x in d2.components(residual)),reverse=True)
    must(len(root)==1 and st=="OK" and parts==[2,2],
         "synthetic depth1 bridge split not detected")
    print("DECOMP4_SELFTEST_PASS "+json.dumps({
      "exhaustive_conditional_model_set_cases":ntests,
      "positive_bridge_split_parts":parts,
      "one_CPU":True,"conditional_UP":True,
      "not_CDCL_live_trail":True},sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("cmd",choices=("selftest","freeze","bench","audit"))
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    if args.cmd=="bench":bench(args.shard)
    else:globals()[args.cmd]()
