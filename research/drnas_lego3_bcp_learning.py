#!/usr/bin/env python3
"""DRNAS LEGO3: heterogeneous equation table learned from bounded real BCP effects.
Proof authority remains the original CNF, never the learned weights.
"""
from __future__ import annotations
import argparse
import collections
import itertools
import json
import math
import pathlib
import random
import tempfile
import time

import drnas_x22_parallel_reducer as x22
import drnas_x24_gf2_proof_first as x24
import drnas_lego1_proof_grammar as lego

ROOT=pathlib.Path("mre_lego3")
PROTO="DRNAS-LEGO3-BCP-RELATION-TABLE-DIVERSE-560-SHORT5-20261109-v1"
ARMS=("race_original","gf2_x24","lego_static","lego_learned","lego_online_bcp")
SHARDS=8
REPS=2
CAP=5.0
TRAIN_COUNT=64
POS_COUNT=24
NEG_COUNT=8
REAL_COUNT=24
EVAL_COUNT=POS_COUNT+NEG_COUNT+REAL_COUNT
EXPECTED=EVAL_COUNT*REPS*len(ARMS)
PER_EQ_BCP_CAP_S=0.0025
PER_FORMULA_BCP_CAP_S=0.18
PER_FORMULA_TOTAL_PREP_S=0.90
MAX_BCP_CLAUSES=1800
MAX_BCP_VARS=512
MAX_CANDIDATES=96
MAX_SELECTED=12
MAX_ADDED=24
BCP_ROUNDS=25
# LEGO-1 native GF2 extraction .65s was a costly outlier. Keep equation
# sampling cheap; if extraction exceeds budget, abstain to original solver.
lego.HELPER_CAP=0.45
lego.MAX_PREP=PER_FORMULA_TOTAL_PREP_S
lego.MAX_JOINS=1400
lego.MAX_ROWS=200

def need(v,msg):
    if not v:raise RuntimeError("LEGO3_FAIL_CLOSED "+str(msg))
def save(path,obj):x22.save(path,obj)
def sha(path):return x22.digest(path)

FAMILIES=(
    ([(1,2,3),(2,3,4)],[(4,5,6,7),(5,8,9,10)],[]),
    ([(1,2,3,4),(2,3,4,5)],[(5,6,7,8)],[]),
    ([(1,2),(2,3),(3,4,5)],[(5,6,7,8)],[]),
    ([(1,2,3),(2,3,4),(3,4,5),(4,5,6)],[(6,7,8,9)],[]),
    ([(1,2,3),(2,3,4)],[(4,5,6,7),(5,8,9,10),(8,11,12,13)],[]),
    ([(1,2,3),(2,3,4)],[(4,5,6,7)],[1]),
    ([(1,2,3,4),(1,2,3,5),(4,6,7)],[(5,6,8,9)],[]),
    ([(1,2),(2,3,4),(3,4,5),(5,6,7,8)],[(5,9,10,11)],[]),
)

def xor_clauses(vs,rhs):
    return [tuple(-v if bits[i] else v for i,v in enumerate(vs))
        for bits in itertools.product((0,1),repeat=len(vs))
        if sum(bits)%2!=rhs]

def generator(seed,family,positive):
    """Eight distinct structures; permutation, sign, clause order and noise.
    One planted satisfying witness; no SAT label is learned as a feature."""
    rng=random.Random(seed)
    n=30
    base={i:rng.choice((False,True)) for i in range(1,n+1)}
    equations,cycles,units=FAMILIES[family]
    equations=list(equations)
    # Additional structurally diverse complete source equations.
    if seed%3==0:
        equations.extend(((14,15,16),(15,16,17)))
    elif seed%3==1:
        equations.extend(((14,15,16,17),(15,16,17,18)))
    else:
        equations.extend(((14,15),(15,16,17),(16,17,18,19)))
    if seed%2==0:
        cycles=list(cycles)+[(14,20,21,22)]
    clauses=[]
    raw_equations=0
    for vs in equations:
        rhs=sum(base[v] for v in vs)%2
        group=xor_clauses(vs,rhs)
        if not positive:group=group[:-1]
        clauses.extend(group)
        raw_equations+=1
    raw_graph_cycles=len(cycles)
    for cyc in cycles:
        root=cyc[0]
        def signed(v):
            return v if base[v]==base[root] else -v
        ll=list(map(signed,cyc))
        group=[(-ll[i],ll[(i+1)%len(ll)]) for i in range(len(ll))]
        if not positive:group=group[:-1]
        clauses.extend(group)
    if positive:
        for v in units:clauses.append((v if base[v] else -v,))
    # Disconnected, varied 2/3/4/5-literal noise: prevents shortcutting
    # by repeated trivial input, while preserving a planted SAT model.
    for _ in range(8+(seed%11)):
        k=rng.choice((2,3,4,5))
        var=rng.sample(list(range(23,n+1)),min(k,8))
        clause=[rng.choice((-1,1))*v for v in var]
        if not x22.holds([tuple(clause)],base):
            clause[0]=var[0] if base[var[0]] else -var[0]
        clauses.append(tuple(clause))
    perm=list(range(1,n+1));rng.shuffle(perm)
    ren={i:perm[i-1] for i in range(1,n+1)}
    signs={i:rng.choice((-1,1)) for i in range(1,n+1)}
    witness={ren[i]:bool(base[i])^(signs[i]<0) for i in range(1,n+1)}
    scrambled=[]
    for clause in clauses:
        new=[(1 if v>0 else -1)*signs[abs(v)]*ren[abs(v)] for v in clause]
        rng.shuffle(new);scrambled.append(tuple(new))
    rng.shuffle(scrambled)
    need(x22.holds(scrambled,witness),"planted SAT witness not valid")
    source="p cnf %d %d\n"%(n,len(scrambled))
    source+="".join(" ".join(map(str,c))+" 0\n" for c in scrambled)
    return source,witness,dict(source_equations=raw_equations,
        graph_cycles=raw_graph_cycles,clause_count=len(scrambled),family=family)

def synthetic_roster():
    (x22.ROOT/"cases").mkdir(parents=True,exist_ok=True)
    train=[];evaluation=[]
    groups=(
       ("train_pos",TRAIN_COUNT,10081019,True,train),
       ("eval_pos",POS_COUNT,20561019,True,evaluation),
       ("eval_negative",NEG_COUNT,30561019,False,evaluation))
    for cohort,total,base_seed,ispositive,part in groups:
        for i in range(total):
            family=i%len(FAMILIES)
            seed=base_seed+101*i+7919*family
            source,witness,features=generator(seed,family,ispositive)
            name="lego3-%s-%03d.cnf"%(cohort,i)
            file=x22.ROOT/"cases"/name
            file.write_text(source)
            need(x22.holds(x22.read_cnf(file)[1],witness),
                 "synthetic reference witness invalid")
            part.append(dict(filename=name,sha256=sha(file),
               year=2026,gbd="LEGO3_"+cohort+"_"+str(i),
               cohort=cohort,seed=seed,expected_sat=True,
               **features))
    return train,evaluation

def real_roster():
    parent=x22.verify_frozen()
    real=sorted(parent["cases"],key=lambda x:x["sha256"])
    need(len(real)==REAL_COUNT,"real sources not complete")
    result=[]
    for item in real:
        record=dict(item)
        record.update(cohort="real_reused_x22",family=-1,
                      expected_sat=False,source_equations=None,
                      graph_cycles=None)
        result.append(record)
    return result

def bcp(clauses,assumptions,deadline):
    """Actual unit-clause propagation to fixed point on a given assignment.
    Diagnostic BCP ONLY; it does not measure CDCL decisions or SAT speed."""
    assignment={}
    for lit in assumptions:
        v=abs(lit);value=lit>0
        if v in assignment and assignment[v]!=value:return True,assignment,False
        assignment[v]=value
    for _ in range(BCP_ROUNDS):
        if time.perf_counter()>deadline:return False,{},True
        changed=False
        for clause in clauses:
            satisfied=False;free=0;last=0
            for lit in clause:
                v=abs(lit)
                if v not in assignment:
                    free+=1;last=lit
                elif assignment[v]==(lit>0):
                    satisfied=True;break
            if satisfied:continue
            if not free:return True,assignment,False
            if free==1:
                value=last>0;v=abs(last)
                if v in assignment and assignment[v]!=value:
                    return True,assignment,False
                if v not in assignment:
                    assignment[v]=value;changed=True
        if not changed:return False,assignment,False
    return False,assignment,True

def candidate_probes(row):
    vs=list(row["vs"])
    # Interventions over proven relation's own variables; deterministic.
    probes=[(v,) for v in vs]+[(-v,) for v in vs]
    # Two-variable partial contexts can expose propagations that single
    # assignments miss, but are capped and do not use an actual solution.
    if len(vs)>1:probes.extend(((vs[0],-vs[1]),(-vs[0],vs[1])))
    return probes[:8]

def bcp_reward(clauses,row,added,absolute_deadline):
    now=time.perf_counter()
    deadline=min(now+PER_EQ_BCP_CAP_S,absolute_deadline)
    if now>=deadline:return None,"equation_budget"
    pre=0; conflicts=0;probe_count=0
    for probe in candidate_probes(row):
        if time.perf_counter()>deadline:return None,"equation_budget"
        original_conf,source_assign,timeout=bcp(clauses,probe,deadline)
        if timeout:return None,"equation_budget"
        if original_conf:continue
        enlarged_conf,extended_assign,timeout=bcp(clauses+added,probe,deadline)
        if timeout:return None,"equation_budget"
        probe_count+=1
        if enlarged_conf:
            conflicts+=1
        else:
            need(all(extended_assign.get(k)==v
                     for k,v in source_assign.items()),
                 "monotonic BCP violated")
            pre+=len(extended_assign)-len(source_assign)
    return dict(extra_propagations=pre,earlier_conflicts=conflicts,
       probes=probe_count,BCP_weight=pre+3*conflicts),None

def candidate_options(leaves,clauses,candidates,absolute_deadline):
    seen=set()
    source={tuple(sorted(set(c))) for c in clauses}
    options=[]
    for row in candidates[:MAX_CANDIDATES]:
        if time.perf_counter()>absolute_deadline:break
        key=(row["rhs"],row["vs"])
        if key in seen:continue
        seen.add(key)
        try:
            proposed=[c for c in lego.clauses_for(row)
                      if tuple(sorted(set(c))) not in source]
            if not proposed:continue
            need(lego.replay(leaves,row["refs"],clauses)==
                 (row["rhs"],row["vs"]),"candidate source proof mismatch")
            options.append(dict(row=row,proposed=proposed,
               signature=row["signature"]))
        except Exception:raise
    return options

def bcp_sample_options(clauses,options,deadline,max_items=MAX_CANDIDATES):
    stats=collections.Counter()
    for item in options[:max_items]:
        if time.perf_counter()>deadline:
            stats["global_budget"]+=1
            break
        if len(clauses)>MAX_BCP_CLAUSES:
            item["bcp"]=None;stats["large_clause_skip"]+=1;continue
        gain,reason=bcp_reward(clauses,item["row"],item["proposed"],deadline)
        item["bcp"]=gain
        stats["scored" if gain is not None else (reason or "unknown")]+=1
    return dict(stats)

def select(clauses,leaves,options,model,policy,deadline):
    edges=lego.read_binary(clauses)
    if policy=="online":
        bcp_stats=bcp_sample_options(
            clauses,options,min(deadline,time.perf_counter()+PER_FORMULA_BCP_CAP_S))
    else:bcp_stats={}
    for item in options:
        row=item["row"];sig=item["signature"]
        hist=model.get(sig,{})
        avg=(hist.get("sum_bcp_weight",0)/max(1,hist.get("count",0))
             if hist.get("count",0)>=2 else 0.0)
        structural=lego.structural_reward(edges,item["proposed"])
        if policy=="learned":
            rank=(avg,math.log1p(hist.get("sources",0)),structural,
                  -len(row["refs"]))
        elif policy=="online":
            instant=(item.get("bcp") or {}).get("BCP_weight",0)
            rank=(instant,structural,-len(row["refs"]))
        else:
            rank=(structural,-len(row["refs"]),-row["depth"])
        item["rank"]=rank
    options.sort(key=lambda it:it["rank"],reverse=True)
    added=[];selected=[];existing={tuple(sorted(set(c))) for c in clauses}
    for item in options:
        if len(selected)>=MAX_SELECTED or len(added)>=MAX_ADDED:break
        if time.perf_counter()>deadline:break
        row=item["row"]
        extra=[c for c in item["proposed"] if tuple(sorted(set(c))) not in existing]
        if not extra or len(extra)+len(added)>MAX_ADDED:continue
        need(lego.replay(leaves,row["refs"],clauses)==
             (row["rhs"],row["vs"]),"final source proof replay")
        for c in extra:existing.add(tuple(sorted(set(c))));added.append(c)
        selected.append(dict(signature=row["signature"],depth=row["depth"],
            width=len(row["vs"]),proof_sources=len(row["refs"]),
            clauses=len(extra),bcp_score=(item.get("bcp") or {}).get("BCP_weight"),
            learned_samples=model.get(row["signature"],{}).get("count",0)))
    return added,selected,bcp_stats

def analyze(src,model,policy,training=False):
    begin=time.perf_counter()
    deadline=begin+PER_FORMULA_TOTAL_PREP_S
    n,clauses=x22.read_cnf(src)
    report=dict(state="unset",source_clauses=len(clauses),source_variables=n,
        source_XOR_equations=0,candidate_rows=0,
        score_stats={},selected=[],runtime_s=0)
    with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
        leaves,original_proof,state=lego.get_leaves(src,clauses,pathlib.Path(tmp))
        report.update(source_XOR_equations=original_proof.get("complete_xor_blocks",0),
            source_graph_relations=original_proof.get("graph_leaves",0),
            proof_replayed=original_proof.get("proof_replayed",False))
        if state!="verified":
            report["state"]=state
            report["runtime_s"]=time.perf_counter()-begin
            return [],report
        if time.perf_counter()>deadline:
            report["state"]="budget_after_leaves"
            report["runtime_s"]=time.perf_counter()-begin
            return [],report
        candidates,grammar=lego.make_grammar(leaves,clauses)
        report.update(grammar=grammar,candidate_rows=len(candidates))
        if time.perf_counter()>deadline:
            report["state"]="budget_after_grammar"
            report["runtime_s"]=time.perf_counter()-begin
            return [],report
        options=candidate_options(leaves,clauses,candidates,deadline)
        report["nontrivial_candidates"]=len(options)
        if training:
            stats=bcp_sample_options(clauses,options,
                     min(deadline,time.perf_counter()+PER_FORMULA_BCP_CAP_S))
            report.update(state="train_proof_replayed",
                          score_stats=stats,runtime_s=time.perf_counter()-begin)
            return options,report
        added,selected,stats=select(clauses,leaves,options,model,policy,deadline)
        if time.perf_counter()>deadline:
            report["state"]="budget_after_score"
            report["runtime_s"]=time.perf_counter()-begin
            return [],report
        report.update(state="verified_added" if added else "verified_no_gain",
            score_stats=stats,selected=selected,
            runtime_s=time.perf_counter()-begin)
        return added,report

def train_table(training_cases):
    table={};reports=[];num_equations=0;num_candidates=0
    for case in training_cases:
        src=x22.ROOT/"cases"/case["filename"]
        need(sha(src)==case["sha256"],"training source SHA changed")
        options,report=analyze(src,{},policy="online",training=True)
        num_equations+=report.get("source_XOR_equations",0)
        num_candidates+=len(options)
        unique_seen=set()
        for item in options:
            obs=item.get("bcp")
            if obs is None:continue
            sig=item["signature"]
            d=table.setdefault(sig,dict(count=0,sources=0,
                sum_bcp_weight=0,sum_extra_propagations=0,
                sum_earlier_conflicts=0,max_depth=0))
            d["count"]+=1
            d["sum_bcp_weight"]+=obs["BCP_weight"]
            d["sum_extra_propagations"]+=obs["extra_propagations"]
            d["sum_earlier_conflicts"]+=obs["earlier_conflicts"]
            d["max_depth"]=max(d["max_depth"],item["row"]["depth"])
            if sig not in unique_seen:d["sources"]+=1;unique_seen.add(sig)
        reports.append(dict(source_sha256=case["sha256"],family=case["family"],
            equations=report.get("source_XOR_equations",0),
            candidates=len(options),scored=report["score_stats"].get("scored",0),
            reason=report["state"]))
    need(num_equations>=TRAIN_COUNT*2,"too few training equation witnesses")
    need(len(table)>=3,"relation score table too sparse")
    return table,reports,dict(training_equations_including_sources=num_equations,
        training_candidate_relations=num_candidates,
        fingerprints=len(table),
        scored_candidates=sum(d["count"] for d in table.values()),
        useful_signatures=sum(d["sum_bcp_weight"]>0 for d in table.values()))

def selftest():
    ROOT.mkdir(parents=True,exist_ok=True)
    lego.ROOT.mkdir(parents=True,exist_ok=True)
    need(x24.BIN.exists(),"native gf2 required")
    passed_pos=0
    for family in range(8):
        seed=20561019+101*family+7919*family
        src,witness,meta=generator(seed,family,True)
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            path=pathlib.Path(tmp)/"toy.cnf";path.write_text(src)
            clauses=x22.read_cnf(path)[1]
            need(x22.holds(clauses,witness),"positive SAT witness")
            added,report=analyze(path,{},"online")
            need(report["state"] in ("verified_added","verified_no_gain"),
                 "positive proof analysis failed "+str((family,report)))
            need(len(added)>0,"positive control didn't derive any new clause "+str(family))
            passed_pos+=1
            rnd=random.Random(seed+11)
            for j in range(100):
                assignment={i:rnd.choice((False,True)) for i in range(1,31)}
                need(x22.holds(clauses,assignment)==
                     x22.holds(clauses+added,assignment),
                     "synthetic model preservation")
    passed_neg=0
    for family in range(8):
        seed=30561019+101*family+7919*family
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            source,witness,meta=generator(seed,family,False)
            path=pathlib.Path(tmp)/"negative.cnf";path.write_text(source)
            clauses=x22.read_cnf(path)[1]
            need(x22.holds(clauses,witness),"negative witness")
            added,report=analyze(path,{},"online")
            need(report["state"] in ("verified_added","verified_no_gain"),
                 "negative proof failed "+str((family,report)))
            need(not added,"incomplete XOR/implications accepted "+str(family))
            passed_neg+=1
    print("LEGO3_SELFTEST_PASS",json.dumps(dict(
        positive=passed_pos,negative=passed_neg,
        bcp_probes_per_candidate_max=8,
        per_equation_bcp_limit_ms=PER_EQ_BCP_CAP_S*1000,
        per_formula_bcp_limit_ms=PER_FORMULA_BCP_CAP_S*1000,
        strict_e2e_cap_s=CAP),sort_keys=True),flush=True)

def freeze():
    ROOT.mkdir(parents=True,exist_ok=True)
    lego.ROOT.mkdir(parents=True,exist_ok=True)
    need(pathlib.Path("prior_x22/report.json").exists(),"original reference missing")
    selftest()
    train,evaluation=synthetic_roster()
    evaluation+=real_roster()
    need(len(evaluation)==EVAL_COUNT and len(train)==TRAIN_COUNT,
         "synthetic/real counts invalid")
    allcases=train+evaluation
    need(len({x["sha256"] for x in allcases})==len(allcases),"repeated source SHA")
    table,reports,totals=train_table(train)
    save(ROOT/"model.json",table)
    save(ROOT/"training.json",reports)
    fingerprints=dict(model_sha256=sha(ROOT/"model.json"),code_sha256=sha(__file__),
        lego1_code_sha256=sha("research/drnas_lego1_proof_grammar.py"),
        x24_binary_sha256=sha(x24.BIN),
        x22_manifest_sha256=sha(x22.ROOT/"manifest.json"),
        x22_reference_sha256=sha("prior_x22/report.json"))
    save(ROOT/"manifest.json",dict(protocol=PROTO,
        arms=list(ARMS),cap_s=CAP,training=train,evaluation=evaluation,
        reps=REPS,shards=SHARDS,expected_trials=EXPECTED,
        train_count=TRAIN_COUNT,positive_count=POS_COUNT,
        negative_count=NEG_COUNT,real_count=REAL_COUNT,
        metrics="unit propagation gains measured on bounded partial assignments; E2E SAT separate",
        per_equation_bcp_ms=1000*PER_EQ_BCP_CAP_S,
        per_formula_bcp_ms=1000*PER_FORMULA_BCP_CAP_S,
        prep_budget_s=PER_FORMULA_TOTAL_PREP_S,
        training_totals=totals,
        positive_tests_generated_with_planted_SAT_witness=True,
        negative_XOR_blocks_incomplete=True,
        real_sources_reused_x22_not_blind=True,
        independent_LRAT=False,no_auto_promotion=True,
        **fingerprints))
    verify()
    print("LEGO3_FROZEN",json.dumps(dict(
         training=TRAIN_COUNT,positive=POS_COUNT,negative=NEG_COUNT,real=REAL_COUNT,
         trials=EXPECTED,shards=SHARDS,arms=ARMS,training_totals=totals,
         max_equation_score_ms=PER_EQ_BCP_CAP_S*1000,
         cap_s=CAP),sort_keys=True),flush=True)

def verify():
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["cap_s"]==CAP and m["arms"]==list(ARMS)
       and m["expected_trials"]==EXPECTED and len(m["training"])==TRAIN_COUNT
       and len(m["evaluation"])==EVAL_COUNT,"manifest mismatch")
    for k,path in dict(model_sha256=ROOT/"model.json",code_sha256=__file__,
           lego1_code_sha256="research/drnas_lego1_proof_grammar.py",
           x24_binary_sha256=x24.BIN,
           x22_manifest_sha256=x22.ROOT/"manifest.json",
           x22_reference_sha256="prior_x22/report.json").items():
        need(m[k]==sha(path),"frozen SHA changed "+k)
    cases=m["training"]+m["evaluation"]
    need(len(set(c["sha256"] for c in cases))==len(cases),"train leakage")
    for c in cases:
        src=x22.ROOT/"cases"/c["filename"]
        need(sha(src)==c["sha256"],"original SHA changed")
        if c["family"]>=0:
            txt,w,meta=generator(c["seed"],c["family"],
                               c["cohort"]!="eval_negative")
            need(src.read_text()==txt,"generator/source drift")
    return m

def trial(case,rep,arm,model):
    src=x22.ROOT/"cases"/case["filename"]
    need(sha(src)==case["sha256"],"original SHA drift")
    if arm in ("race_original","gf2_x24"):
        r=lego.trial(case,rep,arm,{})
        r.update(protocol=PROTO,cohort=case["cohort"],family=case["family"])
        return r
    policy={"lego_static":"static","lego_learned":"learned",
            "lego_online_bcp":"online"}[arm]
    begin=time.perf_counter();cpu_before=x22.child_cpu()
    added=[];report={};status="TIMEOUT";winner=None;checked=False
    cpus=x22.cpus()
    with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
        folder=pathlib.Path(tmp)
        try:
            added,report=analyze(src,model,policy)
        except Exception as exc:
            added=[];report=dict(state="failed_closed",error=str(exc)[:250])
        n,original=x22.read_cnf(src)
        if added:
            out=folder/"augmented.cnf"
            with out.open("w") as stream:
                stream.write("p cnf %d %d\n"%(n,len(original)+len(added)))
                for clause in itertools.chain(original,added):
                    stream.write(" ".join(map(str,clause))+" 0\n")
            need(len(x22.read_cnf(out)[1])==len(original)+len(added),
                 "injected DIMACS invalid")
            second=out
        else:second=src
        prep=time.perf_counter()-begin
        entries=[]
        try:
            if prep<CAP-0.1:
                entries.append(x22.launch("kissat",[x22.KISSAT,
                    "--seed="+str(x22.seed(case,rep)),src],cpus[0],folder))
                entries.append(x22.launch("cadical",[x22.CADICAL,second],
                                         cpus[1],folder))
                while time.perf_counter()-begin<CAP:
                    for e in entries:
                        if e["read"] or e["p"].poll() is None:continue
                        e["read"]=True
                        stdout,stderr=x22.read_output(e)
                        result,verified=x22.solver_result(
                            e["name"],e["p"].returncode,stdout,original,{})
                        status=result;checked=verified;winner=e["name"]
                        break
                    if winner:break
                    if all(e["read"] for e in entries):break
                    time.sleep(.003)
        finally:x22.cleanup(entries)
    elapsed=time.perf_counter()-begin
    if elapsed>CAP or status not in ("SAT","UNSAT"):
        status="TIMEOUT";winner=None;checked=False
    need(sha(src)==case["sha256"],"post solve source SHA changed")
    return dict(protocol=PROTO,cohort=case["cohort"],family=case["family"],
        arm=arm,rep=rep,seed=x22.seed(case,rep),gbd=case["gbd"],
        original_sha256=case["sha256"],status=status,winner=winner,
        SAT_original_witness_verified=checked,UNSAT_independent_LRAT=False,
        cap_s=CAP,E2E_s=round(elapsed,6),
        child_cpu_s=round(x22.child_cpu()-cpu_before,6),
        preprocessing_E2E_s=round(prep,6),clauses_added=len(added),lego=report)

def shard(i):
    m=verify();need(0<=i<SHARDS,"shard index")
    model=json.loads((ROOT/"model.json").read_text())
    rows=[]
    selection=m["evaluation"][i::SHARDS]
    need(len(selection)==EVAL_COUNT//SHARDS,"source shard width")
    for case in selection:
        for rep in range(REPS):
            order=list(ARMS);random.Random(x22.seed(case,rep)).shuffle(order)
            for arm in order:
                r=trial(case,rep,arm,model)
                rows.append(r);save(ROOT/("shard-%d.json"%i),rows)
                print("LEGO3_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==EXPECTED//SHARDS,"incomplete shard")
    print("LEGO3_SHARD_PASS",i,len(rows),flush=True)

def audit():
    m=verify()
    rows=[]
    for i in range(SHARDS):
        f=ROOT/("shard-%d.json"%i)
        need(f.exists(),"missing shard "+str(i))
        part=json.loads(f.read_text())
        need(len(part)==EXPECTED//SHARDS,"shard incomplete")
        rows+=part
    need(len(rows)==EXPECTED,"incomplete trials")
    sources={c["sha256"]:c for c in m["evaluation"]}
    reference=json.loads(pathlib.Path("prior_x22/report.json").read_text())
    confirmed=reference["confirmed_original_UNSAT"]
    seen=set()
    status_by_source=collections.defaultdict(set)
    for r in rows:
        src=r["original_sha256"]
        need(src in sources and r["protocol"]==PROTO and r["arm"] in ARMS
             and r["cap_s"]==CAP and r["cohort"]==sources[src]["cohort"],
             "invalid trial metadata")
        key=(src,r["rep"],r["arm"])
        need(key not in seen,"duplicate pair");seen.add(key)
        if r["status"]=="SAT":
            need(r["SAT_original_witness_verified"],
                 "SAT result missing original source witness")
            need(not confirmed.get(src,False),"SAT original UNSAT disagreement")
        if sources[src]["expected_sat"]:
            need(r["status"]!="UNSAT","planted SAT contradicted")
        if r["status"]!="TIMEOUT":status_by_source[src].add(r["status"])
    need(all(len(v)<=1 for v in status_by_source.values()),
         "solver SAT UNSAT verdict mismatch")
    stats={}
    cohorts=("all","eval_pos","eval_negative","real_reused_x22")
    for arm in ARMS:
        stats[arm]={}
        for cohort in cohorts:
            part=[r for r in rows if r["arm"]==arm
                  and (cohort=="all" or r["cohort"]==cohort)]
            accepted=[r for r in part if r["status"]=="SAT"
                      or (r["status"]=="UNSAT"
                      and confirmed.get(r["original_sha256"],False))]
            stats[arm][cohort]=dict(
                trials=len(part),accepted_solved=len(accepted),
                SAT_original_witness_verified=sum(r["status"]=="SAT" for r in accepted),
                UNSAT_original_agreement_no_LRAT=sum(r["status"]=="UNSAT" for r in accepted),
                PAR2_s=round(sum(r["E2E_s"] if r in accepted else 2*CAP
                                 for r in part),6),
                child_CPU_s=round(sum(r.get("child_cpu_s",0) for r in part),6),
                preprocessing_s=round(sum(r.get("preprocessing_E2E_s",0)
                                          for r in part),6),
                implied_clauses=sum(r.get("clauses_added",0) for r in part),
                proof_replays=sum(r.get("lego",{}).get("state") in
                   ("verified_added","verified_no_gain") for r in part),
                max_join_depth=max((s.get("depth",0) for r in part
                   for s in r.get("lego",{}).get("selected",[])),default=0),
                score_probes=sum(r.get("lego",{}).get("score_stats",{}).get("scored",0)
                                   for r in part),
                equation_budget_abstentions=sum(str(
                   r.get("lego",{}).get("state","")).startswith("budget_")
                   for r in part))
    for cohort in cohorts:
        baseline=stats["race_original"][cohort]["PAR2_s"]
        for arm in ARMS:
            s=stats[arm][cohort]
            s["PAR2_delta_vs_original_pct"]=round(
                  100*(s["PAR2_s"]/baseline-1),4)
    positive=sum(r.get("clauses_added",0)>0 for r in rows
                 if r["arm"]=="lego_static" and r["cohort"]=="eval_pos")
    negative=sum(r.get("clauses_added",0) for r in rows
                 if r["arm"].startswith("lego") and r["cohort"]=="eval_negative")
    need(positive>=POS_COUNT,"too few positive proof detection events")
    need(negative==0,"negative controls acquired unexpected clauses")
    report=dict(protocol=PROTO,total_trials=EXPECTED,
        training_table=json.loads((ROOT/"manifest.json").read_text())["training_totals"],
        positive_proof_detections=positive,
        negative_control_derived_clauses=negative,
        results=stats,
        training_learned_from_bounded_BCP_not_solver_runtime=True,
        no_fresh_real_blind_holdout=True,
        no_independent_LRAT=True,no_auto_promotion=True)
    save(ROOT/"report.json",report)
    print("LEGO3_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("selftest","freeze","shard","audit"))
    parser.add_argument("--shard",type=int,default=0)
    args=parser.parse_args()
    ROOT.mkdir(parents=True,exist_ok=True)
    lego.ROOT.mkdir(parents=True,exist_ok=True)
    if args.action=="shard":shard(args.shard)
    else:globals()[args.action]()
