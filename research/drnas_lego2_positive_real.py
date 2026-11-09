#!/usr/bin/env python3
"""DRNAS LEGO-2, 5-second positive/negative controls plus original real SAT.
LEGO-1's grammar is held fixed; freeze a useful table on disjoint synthetics.
Do not mistake synthetic performance for new real-world SAT generalization.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import itertools
import json
import pathlib
import random
import time

import drnas_x22_parallel_reducer as x22
import drnas_x24_gf2_proof_first as x24
import drnas_lego1_proof_grammar as lego

ROOT=pathlib.Path("mre_lego2")
PROTO="DRNAS-LEGO2-SHORT5-POSNEG-REAL-PROOF-TABLE-20261109-v1"
ARMS=("race_original","gf2_x24","lego_static","lego_learned")
CAP=5.0
REPS=2
SHARDS=4
N_TRAIN=8
N_POS=6
N_NEG=2
N_REAL=4
EXPECTED=(N_POS+N_NEG+N_REAL)*REPS*len(ARMS)

def need(ok,message):
    if not ok:raise RuntimeError("LEGO2_FAIL_CLOSED "+str(message))
def save(path,value):x22.save(path,value)
def sha(path):return x22.digest(path)

def xor_block(vs,rhs):
    out=[]
    for bits in itertools.product((0,1),repeat=len(vs)):
        if sum(bits)%2==rhs:continue
        out.append(tuple(-v if bits[i] else v for i,v in enumerate(vs)))
    return out

def generate(seed,positive):
    """Proof-bearing motif: XOR triple + XOR triple + TWO implied SCC links.
    XOR-only X24 cannot directly read graph-derived implications of length >1.
    Permute variable names, independently flip polarities and clause ordering.
    Negative: remove one clause per XOR and one edge per directed cycle.
    """
    rng=random.Random(seed)
    n=18
    perm=list(range(1,n+1));rng.shuffle(perm)
    ids={i:perm[i-1] for i in range(1,n+1)}
    signs={i:rng.choice((-1,1)) for i in range(1,n+1)}
    witness={ids[i]:(signs[i]<0) for i in range(1,n+1)}
    first=xor_block((1,2,3),0)
    second=xor_block((2,3,4),0)
    chain_a=[(-4,6),(-6,5),(-5,7),(-7,4)]
    chain_b=[(-5,9),(-9,8),(-8,10),(-10,5)]
    if not positive:
        first=first[:-1];second=second[:-1]
        chain_a=chain_a[:-1];chain_b=chain_b[:-1]
    clauses=list(first)+list(second)+chain_a+chain_b
    # Noise uses disconnected variables only, preserving original witness.
    noise_vars=list(range(11,n+1))
    for k in range(4+(seed%5)):
        chosen=rng.sample(noise_vars,rng.choice((3,4)))
        clause=tuple(rng.choice((-1,1))*v for v in chosen)
        if not x22.holds([clause],{i:False for i in range(1,n+1)}):
            clause=tuple([-chosen[0]]+list(clause[1:]))
        clauses.append(clause)
    shuffled=[]
    for clause in clauses:
        new=[int((1 if v>0 else -1)*signs[abs(v)]*ids[abs(v)]) for v in clause]
        rng.shuffle(new);shuffled.append(tuple(new))
    rng.shuffle(shuffled)
    need(x22.holds(shuffled,witness),"generator has no planted witness")
    text="p cnf %d %d\n"%(n,len(shuffled))
    text+="".join(" ".join(map(str,c))+" 0\n" for c in shuffled)
    return text,witness

def make_synthetic():
    (x22.ROOT/"cases").mkdir(parents=True,exist_ok=True)
    train=[];evals=[]
    for cohort,total,start,target in (
        ("train_positive",N_TRAIN,1300911,train),
        ("eval_positive",N_POS,2300911,evals),
        ("eval_negative",N_NEG,3300911,evals)):
        for i in range(total):
            seed=start+i*101
            text,witness=generate(seed,cohort!="eval_negative")
            filename="lego2-%s-%02d.cnf"%(cohort,i)
            path=x22.ROOT/"cases"/filename
            path.write_text(text)
            sig=sha(path)
            need(x22.holds(x22.read_cnf(path)[1],witness),
                 "planted witness inconsistent")
            target.append(dict(filename=filename,sha256=sig,
                year=2026,gbd="LEGO2_"+cohort+"_"+str(i),
                cohort=cohort,expected_sat=True,seed=seed))
    return train,evals

def choose_real():
    manifest=x22.verify_frozen()
    roster=sorted(manifest["cases"],key=lambda c:c["sha256"])
    indices=(2,8,14,20)
    selected=[]
    for idx in indices:
        case=dict(roster[idx])
        case["cohort"]="real_reused_x22"
        case["expected_sat"]=False # False marks UNKNOWN, never assumed UNSAT
        selected.append(case)
    need(len(selected)==N_REAL,"real count")
    return selected

def check_grammar_controls():
    """Exhaustive 10-var projection is avoided; replay and planted witnesses
    checked on each generated seed, plus deterministic random assignments."""
    lego.ROOT.mkdir(parents=True,exist_ok=True)
    for ispositive,seed in ((True,1300911),(True,2300911),
                             (True,2301012),(False,3300911)):
        text,witness=generate(seed,ispositive)
        src=ROOT/("toy-%s-%d.cnf"%("pos" if ispositive else "neg",seed))
        src.write_text(text)
        truth=x22.read_cnf(src)[1]
        need(x22.holds(truth,witness),"toy planted SAT witness invalid")
        added,report=lego.analyze(src,{},"static")
        need(report["state"] in ("verified_added","verified_no_gain"),
             "positive-control preprocessing exceeded budget: "+
             report["state"])
        if ispositive:need(len(added)>=2,
             "positive-control hidden compositional implication missed")
        else:need(not added,
             "negative partial XOR or incomplete implication was accepted")
        rng=random.Random(seed+7)
        for i in range(300):
            model={k:rng.choice((False,True)) for k in range(1,19)}
            need(x22.holds(truth,model)==x22.holds(truth+added,model),
                 "synthetic positive/negative truth table disagreement")
        src.unlink()
    print("LEGO2_SELFTEST_PASS positive/negative proof grammar source replay",
          flush=True)

def freeze():
    lego.ROOT.mkdir(parents=True,exist_ok=True)
    ROOT.mkdir(parents=True,exist_ok=True)
    need(x24.BIN.exists() and pathlib.Path("prior_x22/report.json").exists(),
         "missing frozen native helper/reference")
    check_grammar_controls()
    train,evals=make_synthetic()
    evals.extend(choose_real())
    need(len(train)==N_TRAIN and len(evals)==N_POS+N_NEG+N_REAL,
         "cohort sizes")
    need(len({c["sha256"] for c in train+evals})==len(train)+len(evals),
         "duplicate SHA across training and evaluation")
    table,samples=lego.train(train)
    need(len(table)>=1,"no useful relation fingerprints learned")
    save(ROOT/"model.json",table)
    save(ROOT/"train_report.json",samples)
    save(ROOT/"manifest.json",dict(protocol=PROTO,arms=ARMS,
        training=train,evaluation=evals,
        training_count=N_TRAIN,positive_count=N_POS,
        negative_count=N_NEG,real_count=N_REAL,
        cap_s=CAP,shards=SHARDS,repetitions=REPS,
        expected_trials=EXPECTED,
        model_sha256=sha(ROOT/"model.json"),code_sha256=sha(__file__),
        lego1_code_sha256=sha("research/drnas_lego1_proof_grammar.py"),
        x24_bin_sha256=sha(x24.BIN),
        x22_manifest_sha256=sha(x22.ROOT/"manifest.json"),
        x22_reference_sha256=sha("prior_x22/report.json"),
        synthetic_source_witness_planted=True,
        training_only_synthetic_positive=True,
        evaluation_real_reused_not_blind=True,
        no_auto_promotion=True,UNSAT_independent_LRAT=False))
    check_manifest()
    print("LEGO2_FROZEN",json.dumps(dict(training=N_TRAIN,
        eval_positive=N_POS,eval_negative=N_NEG,eval_real=N_REAL,
        table_rules=len(table),trials=EXPECTED,shards=SHARDS,
        cap_s=CAP),sort_keys=True),flush=True)

def check_manifest():
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["arms"]==list(ARMS) and
         m["expected_trials"]==EXPECTED and m["cap_s"]==CAP and
         len(m["training"])==N_TRAIN and
         len(m["evaluation"])==N_POS+N_NEG+N_REAL,
         "manifest drift")
    hashes=dict(model_sha256=sha(ROOT/"model.json"),
        code_sha256=sha(__file__),
        lego1_code_sha256=sha("research/drnas_lego1_proof_grammar.py"),
        x24_bin_sha256=sha(x24.BIN),
        x22_manifest_sha256=sha(x22.ROOT/"manifest.json"),
        x22_reference_sha256=sha("prior_x22/report.json"))
    for k,v in hashes.items():need(m[k]==v,"frozen hash changed "+k)
    cases=m["training"]+m["evaluation"]
    need(len({c["sha256"] for c in cases})==len(cases),
         "leakage or source SHA duplication")
    for c in cases:
        path=x22.ROOT/"cases"/c["filename"]
        need(sha(path)==c["sha256"],"source SHA changed")
        if c["expected_sat"]:
            text,_=generate(c["seed"],c["cohort"]!="eval_negative")
            need(path.read_text()==text,"synthetic generator drift")
    return m

def trial(case,rep,arm,model):
    r=lego.trial(case,rep,arm,model)
    r["protocol"]=PROTO
    r["cohort"]=case["cohort"]
    r["expected_sat"]=case["expected_sat"]
    return r

def shard(i):
    m=check_manifest();need(0<=i<SHARDS,"shard index")
    model=json.loads((ROOT/"model.json").read_text())
    rows=[]
    for case in m["evaluation"][i::SHARDS]:
        for rep in range(REPS):
            arms=list(ARMS);random.Random(x22.seed(case,rep)).shuffle(arms)
            for arm in arms:
                r=trial(case,rep,arm,model)
                rows.append(r)
                save(ROOT/("shard-%d.json"%i),rows)
                print("LEGO2_TRIAL",json.dumps(r,sort_keys=True),flush=True)
    need(len(rows)==EXPECTED//SHARDS,"short shard incomplete")
    print("LEGO2_SHARD_PASS",i,len(rows),flush=True)

def audit():
    m=check_manifest()
    rows=[]
    for i in range(SHARDS):
        f=ROOT/("shard-%d.json"%i)
        need(f.exists(),"missing shard "+str(i))
        data=json.loads(f.read_text())
        need(len(data)==EXPECTED//SHARDS,"missing trials")
        rows+=data
    need(len(rows)==EXPECTED,"incomplete paired E2E")
    reference=json.loads(pathlib.Path("prior_x22/report.json").read_text())
    original_unsat=reference["confirmed_original_UNSAT"]
    cases={c["sha256"]:c for c in m["evaluation"]}
    seen=set()
    for r in rows:
        key=(r["original_sha256"],r["rep"],r["arm"])
        need(key not in seen and r["protocol"]==PROTO and
             r["arm"] in ARMS and r["cap_s"]==CAP,"invalid trial")
        seen.add(key)
        c=cases[r["original_sha256"]]
        need(r["cohort"]==c["cohort"],"cohort mismatch")
        if r["status"]=="SAT":
            need(r["SAT_original_witness_verified"],
                 "SAT witness not checked against original SHA")
            need(not original_unsat.get(r["original_sha256"],False),
                 "SAT contradicts previous original UNSAT")
        if c["expected_sat"]:need(r["status"]!="UNSAT",
              "synthetic witness contradicts solver UNSAT")
    scores={}
    for arm in ARMS:
        scores[arm]={}
        for cohort in ("all","eval_positive","eval_negative","real_reused_x22"):
            subset=[r for r in rows if r["arm"]==arm and
                    (cohort=="all" or r["cohort"]==cohort)]
            accepted=[r for r in subset if r["status"]=="SAT" or
                      (r["status"]=="UNSAT" and
                       original_unsat.get(r["original_sha256"],False))]
            scores[arm][cohort]=dict(trials=len(subset),accepted_solved=len(accepted),
                verified_SAT=sum(r["status"]=="SAT" for r in accepted),
                original_UNSAT_cross_agreement_not_LRAT=sum(
                      r["status"]=="UNSAT" for r in accepted),
                PAR2_s=round(sum(r["E2E_s"] if r in accepted else 2*CAP
                                  for r in subset),6),
                CPU_s=round(sum(r.get("child_cpu_s",0) for r in subset),6),
                preprocessing_s=round(sum(r.get("preprocessing_E2E_s",0)
                                          for r in subset),6),
                new_proven_clauses=sum(r.get("clauses_added",0) for r in subset),
                proof_replay_complete=sum(r.get("lego",{}).get("state") in
                    ("verified_added","verified_no_gain") for r in subset),
                proof_budget_abstained=sum(str(r.get("lego",{}).get("state",""))
                                          .startswith("budget_") for r in subset),
                max_join_depth=max((s.get("depth",0)
                   for r in subset for s in r.get("lego",{}).get("selected",[])),
                   default=0),
                selected_relations=sum(len(r.get("lego",{}).get("selected",[]))
                                        for r in subset))
    for cohort in scores["race_original"]:
        b=scores["race_original"][cohort]["PAR2_s"]
        for arm in ARMS:
            a=scores[arm][cohort]
            a["PAR2_delta_vs_original_pct"]=round(
                  100*(a["PAR2_s"]/b-1),4) if b else 0
    positive=sum(r.get("clauses_added",0)>0 for r in rows
                 if r["arm"]=="lego_static" and
                    r["cohort"]=="eval_positive")
    negative=sum(r.get("clauses_added",0) for r in rows
                 if r["arm"].startswith("lego_") and
                    r["cohort"]=="eval_negative")
    need(positive>=1,"proof grammar detected zero positive controls")
    need(negative==0,"negative controls gained clauses unexpectedly")
    save(ROOT/"report.json",dict(protocol=PROTO,results=scores,
        positive_detected_static=positive,
        negative_added_clauses=negative,
        rule_count=len(json.loads((ROOT/"model.json").read_text())),
        sources=[dict(c) for c in m["evaluation"]],
        evaluation_not_blind_real_reused=True,
        LRAT_independent=False,
        total_trials=EXPECTED,no_auto_promotion=True))
    print("LEGO2_FINAL",json.dumps(dict(results=scores,
         positive_detected_static=positive,negative_added_clauses=negative),
         sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("freeze","shard","audit","selftest"))
    p.add_argument("--shard",type=int,default=0)
    arg=p.parse_args()
    ROOT.mkdir(parents=True,exist_ok=True)
    lego.ROOT.mkdir(parents=True,exist_ok=True)
    if arg.action=="selftest":check_grammar_controls()
    elif arg.action=="shard":shard(arg.shard)
    else:globals()[arg.action]()
