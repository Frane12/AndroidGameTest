#!/usr/bin/env python3
"""DRNAS LEGO-3: short 5s proof-carrying grammar with measured BCP usefulness.

Learner records propagation gain of proven relation procedures, never truth.
80 positive + 16 negative generated training cases, plus 8 disjoint real SHA
train; 32 positive +8 negative+8 real E2E eval, 2 repeats, 5 arms = 480.
All accepted SAT witnesses checked on original CNF; no LRAT claims.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
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
import drnas_lego2_positive_real as lego2

ROOT=pathlib.Path("mre_lego3")
PROTO="DRNAS-LEGO3-BCP-LEARN-8FAMILY-REAL-SHORT5-20261109-v1"
ARMS=("race_original","gf2_x24","lego_static","lego_up_local","lego_up_learned")
CAP=5.0
REPS=2
SHARDS=8
FAMILIES=8
TRAIN_PER_FAMILY=10
EVAL_PER_FAMILY=4
TRAIN_NEG=16
EVAL_NEG=8
TRAIN_REAL=8
EVAL_REAL=8
EVAL_COUNT=FAMILIES*EVAL_PER_FAMILY+EVAL_NEG+EVAL_REAL
EXPECTED=EVAL_COUNT*REPS*len(ARMS)
MAX_ANALYSIS_S=1.15
MAX_TRAIN_S=.8
MAX_BCP_FORMULA_S=.13
MAX_BCP_CANDIDATE_S=.004
MAX_BCP_INPUT_CLAUSES=1200
MAX_BCP_CANDIDATES=36
MAX_BCP_PROBES=4
MAX_NEW_CLAUSES=20
MAX_SELECTED_ROWS=10

# Each row represents a family of low-width equations, some with implied
# two-way paths. These templates are structurally different, not just SHA
# variants of one identical two-cube gadget.
TEMPLATES=(
    (((1,2,3),(2,3,4)),((4,5),),(5,)),                         # 2 xor cubes + SCC
    (((1,2,3),(2,3,4),(4,6,7),(6,7,8)),((8,9),),(9,)),        # 4 xor + SCC
    (((1,2,3,4),(2,3,4,5)),((5,6),),(6,)),                    # 4-CNF overlapping 3
    (((1,2,3),(2,3,4),(4,5,6),(5,6,7)),((7,8),),(8,)),        # 2-level cancellation
    (((1,2),(2,3,4),(3,4,5)),((5,6),),(6,)),                  # XOR2 seed
    (((1,2,3),(2,3,4),(1,4,5)),((5,6),),(6,)),                # XOR cycle => unit
    (((1,2,3),(2,3,4)),((4,5),(5,8)),(8,)),                   # multiple graph bridges
    (((1,2,3,4),(2,3,4,5),(1,5,6)),((6,7),),(7,)),            # XOR4 + XOR3 mixed
)

def need(ok,why):
    if not ok:raise RuntimeError("LEGO3_FAIL_CLOSED "+str(why))
def sha(p):return x22.digest(p)
def save(p,obj):return x22.save(p,obj)

def generate(seed,family,negative=False):
    """Source-proven relations with randomized variable renaming/polarity.
    All clauses must satisfy a planted witness; negative remove both complete
    XOR cubes and one direction of each SCC (not 'false' XOR facts).
    """
    rng=random.Random(seed)
    eqs,bridges,tails=TEMPLATES[family]
    n=96
    assign={v:bool(rng.getrandbits(1)) for v in range(1,n+1)}
    logical=[]
    for vs in eqs:
        rhs=sum(assign[v] for v in vs)&1
        block=lego2.xor_block(vs,rhs)
        if negative:block=block[:-1]
        logical.extend(block)
    mid=23
    for a,b in bridges:
        # Signed equivalence x_a XOR x_b = known parity, encoded as
        # two separate (length-2) binary implication paths.
        parity=assign[a]^assign[b]
        signed_b=b if not parity else -b
        p1,p2=mid,mid+1;mid+=2
        need(mid<40,"aux collision")
        source_truth=assign[a]
        s1=p1 if assign[p1]==source_truth else -p1
        s2=p2 if assign[p2]==source_truth else -p2
        segment=[(-a,s1),(-s1,signed_b),
                 (-signed_b,s2),(-s2,a)]
        if negative:segment=segment[:-1]
        logical.extend(segment)
    # Make the proven short relation useful for BCP: short one-directional
    # tails attached to the derived endpoint. These create no SCC closure.
    for k,t in enumerate(tails):
        prev=t if assign[t] else -t
        for step in range(3):
            v=40+k*4+step
            nxt=v if assign[v] else -v
            logical.append((-prev,nxt))
            prev=nxt
    # Distractor 3-/4-clauses over disconnected vars; no artificial
    # short relations or intentionally leaked real source identities.
    noise_vars=list(range(60,n+1))
    for _ in range(10+seed%11):
        vs=rng.sample(noise_vars,rng.choice((3,4)))
        lits=[v if rng.getrandbits(1) else -v for v in vs]
        if not any(assign[abs(v)]==(v>0) for v in lits):
            lits[0]=-lits[0]
        logical.append(tuple(lits))
    need(x22.holds(logical,assign),"generator planted witness invalid")
    perm=list(range(1,n+1));rng.shuffle(perm)
    mapping={i:perm[i-1] for i in range(1,n+1)}
    signs={i:1 if rng.getrandbits(1) else -1 for i in range(1,n+1)}
    witness={mapping[i]:assign[i] if signs[i]>0 else not assign[i]
             for i in range(1,n+1)}
    clauses=[]
    for clause in logical:
        c=[(1 if lit>0 else -1)*mapping[abs(lit)]*signs[abs(lit)]
           for lit in clause]
        rng.shuffle(c);clauses.append(tuple(c))
    rng.shuffle(clauses)
    need(x22.holds(clauses,witness),"renamed planted witness invalid")
    txt="p cnf %d %d\n"%(n,len(clauses))
    txt+="".join(" ".join(map(str,c))+" 0\n" for c in clauses)
    return txt,witness

def make_sources():
    (x22.ROOT/"cases").mkdir(parents=True,exist_ok=True)
    train=[];evaluation=[]
    for family in range(FAMILIES):
        for i in range(TRAIN_PER_FAMILY+EVAL_PER_FAMILY):
            istrain=i<TRAIN_PER_FAMILY
            seed=(1710000 if istrain else 2810000)+family*12007+i*229
            txt,witness=generate(seed,family,False)
            fname="lego3-%s-pos-f%d-%02d.cnf"%(
                 "tr" if istrain else "ev",family,i)
            path=x22.ROOT/"cases"/fname;path.write_text(txt)
            need(x22.holds(x22.read_cnf(path)[1],witness),
                 "generated source not SAT")
            row=dict(filename=fname,sha256=sha(path),gbd="LEGO3_f%d_%d"%(family,i),
                cohort="train_positive" if istrain else "eval_positive",
                family=family,expected_sat=True,seed=seed,synthetic=True)
            (train if istrain else evaluation).append(row)
    for i in range(TRAIN_NEG+EVAL_NEG):
        istrain=i<TRAIN_NEG
        family=i%FAMILIES
        seed=(3810000 if istrain else 4810000)+family*12007+i*233
        txt,witness=generate(seed,family,True)
        fname="lego3-%s-neg-%02d.cnf"%("tr" if istrain else "ev",i)
        path=x22.ROOT/"cases"/fname;path.write_text(txt)
        need(x22.holds(x22.read_cnf(path)[1],witness),
             "negative control planted witness invalid")
        row=dict(filename=fname,sha256=sha(path),gbd="LEGO3_neg_%d"%i,
            cohort="train_negative" if istrain else "eval_negative",
            family=family,expected_sat=True,seed=seed,synthetic=True)
        (train if istrain else evaluation).append(row)
    # Recycled original SHA: use disjoint train/eval subsets.
    originals=sorted(x22.verify_frozen()["cases"],key=lambda c:c["sha256"])
    need(len(originals)==24,"reference roster size")
    for selection,target,cohort in (
        ((0,3,6,9,12,15,18,21),train,"train_real_reused_x22"),
        ((1,4,7,10,13,16,19,22),evaluation,"eval_real_reused_x22")):
        for i in selection:
            c=dict(originals[i]);c.update(cohort=cohort,family=-1,
                 expected_sat=False,synthetic=False)
            target.append(c)
    need(len(train)==TRAIN_PER_FAMILY*FAMILIES+TRAIN_NEG+TRAIN_REAL,
         "train size")
    need(len(evaluation)==EVAL_COUNT,"evaluation size")
    need(len({c["sha256"] for c in train+evaluation})==len(train+evaluation),
         "SHA leaked train/eval")
    return train,evaluation

def bcp(clauses,assumptions,deadline,max_rounds=8):
    assigned={}
    for lit in assumptions:
        var=abs(lit);v=lit>0
        if var in assigned and assigned[var]!=v:return assigned,True
        assigned[var]=v
    for _ in range(max_rounds):
        if time.perf_counter()>deadline:return assigned,False
        changed=False
        for clause in clauses:
            sat=False;unassigned=0;pending=0
            for lit in clause:
                v=assigned.get(abs(lit))
                if v is None:
                    unassigned+=1;pending=lit
                elif v==(lit>0):
                    sat=True;break
            if sat:continue
            if unassigned==0:return assigned,True
            if unassigned==1:
                v=abs(pending);sign=pending>0
                if v in assigned:
                    if assigned[v]!=sign:return assigned,True
                else:
                    assigned[v]=sign;changed=True
        if not changed:break
    return assigned,False

def candidate_key(row):
    # Name-independent grammar: no literal identities, no original SHA.
    return "%s|depth%d|w%d"%(row["signature"],min(3,row["depth"]),
                               len(row["vs"]))

def proposal(row,clauses,already=None):
    original={tuple(sorted(set(c))) for c in clauses} if already is None else already
    return [tuple(c) for c in lego.clauses_for(row)
            if tuple(sorted(set(c))) not in original]

def probes_for(row):
    vs=row["vs"]
    if not vs:return [()]
    if len(vs)==1:return [(),(vs[0],),(-vs[0],)]
    a,b=vs
    return [(a,),(-a,),(b,),(-b,)][:MAX_BCP_PROBES]

def measure_up(clauses,row,deadline):
    """Direct bounded unit-propagation gain. No CDCL conclusions or proof.
    This is a diagnostic proxy, NOT E2E solver improvement.
    """
    proposed=proposal(row,clauses)
    if not proposed:return (0.0,0,0.0)
    if len(clauses)>MAX_BCP_INPUT_CLAUSES:return (0.0,0,0.0)
    start=time.perf_counter()
    stop=min(deadline,start+MAX_BCP_CANDIDATE_S)
    gain=0.;completed=0
    for assumed in probes_for(row):
        if time.perf_counter()>=stop:break
        baseline,bad=bcp(clauses,assumed,stop)
        if time.perf_counter()>=stop:break
        strengthened,nowbad=bcp(itertools.chain(clauses,proposed),assumed,stop)
        if time.perf_counter()>=stop:break
        if bad:continue
        new=sum(v not in baseline for v in strengthened)
        gain+=min(new,10)
        if nowbad and not bad:gain+=5
        completed+=1
    return (gain,completed,time.perf_counter()-start)

def read_grammar(src):
    n,clauses=x22.read_cnf(src)
    with tempfile.TemporaryDirectory(dir=lego.ROOT) as temp:
        leaves,proof,state=lego.get_leaves(src,clauses,pathlib.Path(temp))
        if state!="verified":return clauses,leaves,[],dict(state=state,
                     proof=proof,grammar={})
        candidates,gram=lego.make_grammar(leaves,clauses)
    return clauses,leaves,candidates,dict(state="verified",
                                         proof=proof,grammar=gram)

def scored_candidates(clauses,candidates,table,mode,deadline):
    original={tuple(sorted(set(c))) for c in clauses}
    edges=lego.read_binary(clauses)
    ranked=[];diag=dict(probed=0,probe_completed=0,probe_gain=0.0,
                        probe_s=0.,proof_candidates=len(candidates),
                        candidate_cap_hit=False)
    seen=set()
    for row in candidates:
        if time.perf_counter()>=deadline:break
        key=(row["rhs"],row["vs"])
        if key in seen:continue
        seen.add(key)
        new=proposal(row,clauses,original)
        if not new:continue
        structural=lego.structural_reward(edges,new)
        hist=table.get(candidate_key(row),{})
        mean=hist.get("gain_sum",0.0)/max(1,hist.get("probe_count",0))
        local_gain=0.
        if mode=="local" and diag["probed"]<MAX_BCP_CANDIDATES:
            gain,probes,elapsed=measure_up(clauses,row,deadline)
            diag["probed"]+=1;diag["probe_completed"]+=probes
            diag["probe_gain"]+=gain;diag["probe_s"]+=elapsed
            local_gain=gain/max(1,probes)
        if mode=="learned":
            # Prior matters only for ranking independently source-proven rows.
            score=(mean if hist.get("probe_count",0)>=4 else 0,
                   structural,-len(row["refs"]),-row["depth"])
        elif mode=="local":
            score=(local_gain,structural,-len(row["refs"]),-row["depth"])
        else:
            score=(structural,-len(row["refs"]),-row["depth"])
        ranked.append((score,row,new,structural,mean,local_gain))
    ranked.sort(key=lambda x:x[0],reverse=True)
    return ranked,diag

def select(clauses,leaves,ranked,deadline):
    existing={tuple(sorted(set(c))) for c in clauses}
    added=[];selected=[]
    for score,row,all_clauses,structural,mean,local_gain in ranked:
        if time.perf_counter()>=deadline or len(selected)>=MAX_SELECTED_ROWS:break
        fresh=[c for c in all_clauses
               if tuple(sorted(set(c))) not in existing]
        if not fresh or len(fresh)+len(added)>MAX_NEW_CLAUSES:continue
        need(lego.replay(leaves,row["refs"],clauses)==(row["rhs"],row["vs"]),
             "source proof mismatch on selected relation")
        for c in fresh:existing.add(tuple(sorted(set(c))));added.append(c)
        selected.append(dict(rule=candidate_key(row),
             depth=row["depth"],new_clauses=len(fresh),
             structural_proxy=structural,train_gain_mean=mean,
             local_gain=local_gain,source_leaves=len(row["refs"])))
    return added,selected

def analyze(src,table,mode):
    start=time.perf_counter()
    deadline=start+MAX_ANALYSIS_S
    clauses,leaves,candidates,source=read_grammar(src)
    if source["state"]!="verified":
        return [],dict(**source,selected=[],diagnostics={},
                       elapsed_s=round(time.perf_counter()-start,6))
    if time.perf_counter()>=deadline:
        return [],dict(**source,state="budget_grammar",
                       selected=[],diagnostics={},
                       elapsed_s=round(time.perf_counter()-start,6))
    ranked,diag=scored_candidates(clauses,candidates,table,mode,deadline)
    if time.perf_counter()>=deadline:
        return [],dict(**source,state="budget_probes",
                       selected=[],diagnostics=diag,
                       elapsed_s=round(time.perf_counter()-start,6))
    added,selected=select(clauses,leaves,ranked,deadline)
    if time.perf_counter()>=deadline:
        return [],dict(**source,state="budget_select",
                       selected=[],diagnostics=diag,
                       elapsed_s=round(time.perf_counter()-start,6))
    return added,dict(**source,state="verified_added" if added else
                      "verified_no_gain",selected=selected,
                      diagnostics=diag,
                      elapsed_s=round(time.perf_counter()-start,6))

def train_table(training):
    table={};details=[]
    for case in training:
        src=x22.ROOT/"cases"/case["filename"]
        need(sha(src)==case["sha256"],"train original SHA changed")
        start=time.perf_counter()
        clauses,leaves,candidates,info=read_grammar(src)
        rows=0;gains=0;probe_total=0;time_spent=0.
        if info["state"]=="verified" and time.perf_counter()-start<MAX_TRAIN_S:
            deadline=min(time.perf_counter()+MAX_BCP_FORMULA_S,
                         start+MAX_TRAIN_S)
            originals={tuple(sorted(set(c))) for c in clauses}
            seen=set()
            for row in candidates:
                if time.perf_counter()>=deadline or rows>=MAX_BCP_CANDIDATES:break
                if (row["rhs"],row["vs"]) in seen:continue
                seen.add((row["rhs"],row["vs"]))
                if not proposal(row,clauses,originals):continue
                need(lego.replay(leaves,row["refs"],clauses)==
                     (row["rhs"],row["vs"]),"train proof invalid")
                gain,probes,spent=measure_up(clauses,row,deadline)
                if not probes:continue
                key=candidate_key(row)
                hist=table.setdefault(key,dict(observations=0,
                  gain_sum=0.,probe_count=0,diag_s=0.,positive_cases=0))
                hist["observations"]+=1;hist["gain_sum"]+=gain
                hist["probe_count"]+=probes;hist["diag_s"]+=spent
                hist["positive_cases"]+=+(gain>0)
                rows+=1;gains+=gain;probe_total+=probes;time_spent+=spent
        details.append(dict(sha256=case["sha256"],cohort=case["cohort"],
             family=case["family"],candidate_rows=len(candidates),
             measured_rows=rows,measured_probes=probe_total,
             gain_total=gains,diagnostic_s=round(time_spent,6),
             elapsed_s=round(time.perf_counter()-start,6),
             extraction=info["state"],source_equations=
               info.get("proof",{}).get("total_leaves",0)))
    for value in table.values():
        value["gain_sum"]=round(value["gain_sum"],6)
        value["diag_s"]=round(value["diag_s"],6)
    need(len(table)>=3,"no diverse grammar rules learned")
    need(sum(x["gain_total"]>0 for x in details)>=12,
         "training found insufficient UP gain")
    return table,details

def selftest():
    lego.ROOT.mkdir(parents=True,exist_ok=True)
    ROOT.mkdir(parents=True,exist_ok=True)
    checks=[]
    for family in range(FAMILIES):
        for negative in (False,True):
            seed=(830011 if not negative else 940011)+family*121
            txt,witness=generate(seed,family,negative)
            with tempfile.TemporaryDirectory(dir=ROOT) as t:
                src=pathlib.Path(t)/"toy.cnf";src.write_text(txt)
                n,clauses=x22.read_cnf(src)
                need(x22.holds(clauses,witness),"toy witness invalid")
                added,report=analyze(src,{},"local")
                need(report["state"] in ("verified_added","verified_no_gain"),
                     "toy source proof or budget failed "+report["state"])
                if negative:need(not added,"false negative-control inference")
                checks.append((family,negative,len(added),report))
                rng=random.Random(seed+9)
                for _ in range(100):
                    model={i:bool(rng.getrandbits(1)) for i in range(1,n+1)}
                    need(x22.holds(clauses,model)==x22.holds(clauses+added,model),
                         "truth-table sample invalid")
    positives=sum(bool(n) for _,neg,n,_ in checks if not neg)
    need(positives>=6,"diverse positive controls did not produce implications")
    need(any(c[3]["diagnostics"]["probe_gain"]>0 for c in checks if not c[1]),
         "toy UP measurement produced no new propagation")
    print("LEGO3_SELFTEST_PASS "+json.dumps(dict(
       positive_families=positives,negative_families=FAMILIES,
       toy_probes=sum(c[3]["diagnostics"]["probe_completed"] for c in checks),
       toy_UP_gain=sum(c[3]["diagnostics"]["probe_gain"] for c in checks)),
       sort_keys=True),flush=True)

def freeze():
    ROOT.mkdir(parents=True,exist_ok=True);lego.ROOT.mkdir(parents=True,exist_ok=True)
    need(x24.BIN.exists(),"native GF2 missing")
    need(pathlib.Path("prior_x22/report.json").exists(),"original agreement missing")
    selftest()
    train,evaluation=make_sources()
    table,details=train_table(train)
    save(ROOT/"model.json",table);save(ROOT/"train_report.json",details)
    save(ROOT/"manifest.json",dict(protocol=PROTO,
       arms=ARMS,cap_s=CAP,shards=SHARDS,repetitions=REPS,
       train=train,evaluation=evaluation,expected_trials=EXPECTED,
       train_count=len(train),eval_count=len(evaluation),
       model_sha256=sha(ROOT/"model.json"),
       train_report_sha256=sha(ROOT/"train_report.json"),
       code_sha256=sha(__file__),
       lego1_sha256=sha("research/drnas_lego1_proof_grammar.py"),
       lego2_sha256=sha("research/drnas_lego2_positive_real.py"),
       x24_binary_sha256=sha(x24.BIN),
       x22_manifest_sha256=sha(x22.ROOT/"manifest.json"),
       x22_report_sha256=sha("prior_x22/report.json"),
       train_eval_original_SHA_disjoint=True,
       synthetic_not_real_world_speed_evidence=True,
       reused_real_not_blind=True,
       independent_LRAT=False,no_auto_promotion=True,
       training_score="bounded_unit_propagation_gain_not_CDCL",
       max_candidate_diagnostic_s=MAX_BCP_CANDIDATE_S,
       max_formula_diagnostic_s=MAX_BCP_FORMULA_S))
    verify()
    summary=dict(train_sources=len(train),eval_sources=len(evaluation),
       families=FAMILIES,learned_signatures=len(table),
       training_equations=sum(d["source_equations"] for d in details),
       training_probes=sum(d["measured_probes"] for d in details),
       training_UP_gain=sum(d["gain_total"] for d in details),
       diagnostics_s=round(sum(d["diagnostic_s"] for d in details),6),
       eval_positive=FAMILIES*EVAL_PER_FAMILY,eval_negative=EVAL_NEG,
       eval_real=EVAL_REAL,arms=ARMS,repetitions=REPS,
       short5_trials=EXPECTED)
    save(ROOT/"train_summary.json",summary)
    print("LEGO3_FROZEN "+json.dumps(summary,sort_keys=True),flush=True)

def verify():
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["arms"]==list(ARMS) and
         m["cap_s"]==CAP and m["expected_trials"]==EXPECTED and
         len(m["train"])==TRAIN_PER_FAMILY*FAMILIES+TRAIN_NEG+TRAIN_REAL
         and len(m["evaluation"])==EVAL_COUNT,"manifest layout changed")
    pinned=dict(model_sha256=sha(ROOT/"model.json"),
        train_report_sha256=sha(ROOT/"train_report.json"),
        code_sha256=sha(__file__),
        lego1_sha256=sha("research/drnas_lego1_proof_grammar.py"),
        lego2_sha256=sha("research/drnas_lego2_positive_real.py"),
        x24_binary_sha256=sha(x24.BIN),
        x22_manifest_sha256=sha(x22.ROOT/"manifest.json"),
        x22_report_sha256=sha("prior_x22/report.json"))
    for key,v in pinned.items():need(m[key]==v,"frozen SHA drift "+key)
    all_sources=m["train"]+m["evaluation"]
    need(len({x["sha256"] for x in all_sources})==len(all_sources),
         "train/eval SHA leakage")
    for c in all_sources:
        src=x22.ROOT/"cases"/c["filename"]
        need(sha(src)==c["sha256"],"original source SHA changed")
        if c["synthetic"]:
            txt,witness=generate(c["seed"],c["family"],
                 c["cohort"].endswith("negative"))
            need(src.read_text()==txt,"synthetic generator drift")
            need(x22.holds(x22.read_cnf(src)[1],witness),
                 "synthetic witness invalid")
    return m

def run_trial(case,rep,arm,model):
    src=x22.ROOT/"cases"/case["filename"]
    need(sha(src)==case["sha256"],"trial SHA mismatch")
    if arm in ("race_original","gf2_x24"):
        if arm=="race_original":
            old=x22.CAP
            try:
                x22.CAP=CAP
                row=x22.trial(case,rep,"race_original")
            finally:x22.CAP=old
        else:
            old=x24.CAP
            try:
                x24.CAP=CAP
                row=x24.run_gf2(case,rep)
            finally:x24.CAP=old
        row.update(protocol=PROTO,arm=arm,lego3={})
    else:
        start=time.perf_counter();start_cpu=x22.child_cpu()
        added=[];report={};status="TIMEOUT";checked=False;winner=None
        cpu=x22.cpus()
        with tempfile.TemporaryDirectory(dir=ROOT) as d:
            d=pathlib.Path(d)
            try:
                if arm=="lego_static":
                    added,report=lego.analyze(src,{},"static")
                else:
                    added,report=analyze(src,model,
                         "local" if arm=="lego_up_local" else "learned")
            except Exception as e:
                added=[];report=dict(state="fail_closed",
                    exception=str(e)[:220],selected=[],diagnostics={})
            prep=time.perf_counter()-start
            original_n,original=x22.read_cnf(src)
            if added:
                aug=d/"enhanced.cnf"
                with aug.open("w") as f:
                    f.write("p cnf %d %d\n"%(original_n,len(original)+len(added)))
                    for c in itertools.chain(original,added):
                        f.write(" ".join(map(str,c))+" 0\n")
                need(x22.read_cnf(aug)[1]==original+added,
                     "augmented CNF differs from verified clauses")
                chosen=aug
            else:chosen=src
            entries=[]
            try:
                if time.perf_counter()-start<CAP-.1:
                    entries.append(x22.launch("kissat",
                         [x22.KISSAT,"--seed="+str(x22.seed(case,rep)),src],
                         cpu[0],d))
                    entries.append(x22.launch("cadical",
                          [x22.CADICAL,chosen],cpu[1],d))
                    while time.perf_counter()-start<CAP:
                        for entry in entries:
                            if entry["read"] or entry["p"].poll() is None:continue
                            entry["read"]=True
                            stdout,err=x22.read_output(entry)
                            status,checked=x22.solver_result(entry["name"],
                                entry["p"].returncode,stdout,original,{})
                            winner=entry["name"];break
                        if winner or all(e["read"] for e in entries):break
                        time.sleep(.003)
            finally:x22.cleanup(entries)
        elapsed=time.perf_counter()-start
        if elapsed>CAP or status not in ("SAT","UNSAT"):
            status="TIMEOUT";winner=None;checked=False
        row=dict(protocol=PROTO,arm=arm,cap_s=CAP,rep=rep,
           seed=x22.seed(case,rep),gbd=case["gbd"],
           original_sha256=case["sha256"],
           E2E_s=round(elapsed,6),
           child_cpu_s=round(x22.child_cpu()-start_cpu,6),
           status=status,winner=winner,
           SAT_original_witness_verified=checked,
           UNSAT_independent_LRAT=False,
           preprocessing_E2E_s=round(prep,6),
           clauses_added=len(added),lego3=report)
    row["cohort"]=case["cohort"]
    row["family"]=case["family"]
    row["synthetic"]=case["synthetic"]
    row["expected_sat"]=case["expected_sat"]
    need(sha(src)==case["sha256"],"post trial source mutated")
    return row

def shard(i):
    need(0<=i<SHARDS,"shard id")
    m=verify();model=json.loads((ROOT/"model.json").read_text())
    subset=m["evaluation"][i::SHARDS];rows=[]
    need(len(subset)==EVAL_COUNT//SHARDS,"shard case distribution")
    for case in subset:
        for rep in range(REPS):
            arms=list(ARMS);random.Random(x22.seed(case,rep)).shuffle(arms)
            for arm in arms:
                row=run_trial(case,rep,arm,model)
                rows.append(row)
                save(ROOT/("shard-%d.json"%i),rows)
                print("LEGO3_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==EXPECTED//SHARDS,"incomplete shard")
    print("LEGO3_SHARD_PASS",i,len(rows),flush=True)

def audit():
    m=verify();rows=[]
    for i in range(SHARDS):
        f=ROOT/("shard-%d.json"%i)
        need(f.exists(),"missing shard JSON")
        part=json.loads(f.read_text())
        need(len(part)==EXPECTED//SHARDS,"incomplete shard")
        rows.extend(part)
    need(len(rows)==EXPECTED,"incomplete full benchmark")
    seen=set();ref=json.loads(pathlib.Path("prior_x22/report.json").read_text())
    unsat=ref["confirmed_original_UNSAT"]
    cases={c["sha256"]:c for c in m["evaluation"]}
    for r in rows:
        key=(r["original_sha256"],r["rep"],r["arm"])
        need(key not in seen and r["protocol"]==PROTO
             and r["cap_s"]==CAP,"duplicate or invalid trial")
        seen.add(key)
        c=cases[r["original_sha256"]]
        need(r["cohort"]==c["cohort"] and
             r["family"]==c["family"],"cohort mislabel")
        if r["status"]=="SAT":
            need(r["SAT_original_witness_verified"],
                 "unverified SAT original witness")
            need(not unsat.get(r["original_sha256"],False),
                 "SAT disagrees with original-SHA UNSAT reference")
        if c["expected_sat"]:
            need(r["status"]!="UNSAT","synthetic SAT fixture declared UNSAT")
    scores={}
    cohorts=("all","eval_positive","eval_negative","eval_real_reused_x22")
    for arm in ARMS:
        scores[arm]={}
        for cohort in cohorts:
            s=[r for r in rows if r["arm"]==arm and
               (cohort=="all" or r["cohort"]==cohort)]
            accepted=[r for r in s if r["status"]=="SAT" or
                 (r["status"]=="UNSAT" and
                  unsat.get(r["original_sha256"],False))]
            scores[arm][cohort]=dict(trials=len(s),
              accepted_solved=len(accepted),
              verified_SAT=sum(r["status"]=="SAT" for r in accepted),
              source_UNSAT_cross_agreement_no_LRAT=sum(
                r["status"]=="UNSAT" for r in accepted),
              PAR2_s=round(sum(r["E2E_s"] if r in accepted else 2*CAP
                                for r in s),6),
              child_CPU_s=round(sum(r.get("child_cpu_s",0) for r in s),6),
              added_proven_clauses=sum(r.get("clauses_added",0) for r in s),
              preprocessing_s=round(sum(r.get("preprocessing_E2E_s",0)
                                        for r in s),6),
              UP_probe_gain=round(sum(r.get("lego3",{}).get("diagnostics",{})
                                       .get("probe_gain",0) for r in s),3),
              UP_probe_count=sum(r.get("lego3",{}).get("diagnostics",{})
                                    .get("probe_completed",0) for r in s),
              fallback=sum(r.get("lego3",{}).get("state","").startswith(
                        ("budget","fail","native")) for r in s))
    for cohort in cohorts:
        base=scores["race_original"][cohort]["PAR2_s"]
        for arm in ARMS:
            scores[arm][cohort]["delta_PAR2_pct"]=round(
                   100*(scores[arm][cohort]["PAR2_s"]/base-1),4)
    positive=sum(r.get("clauses_added",0)>0 for r in rows
                 if r["cohort"]=="eval_positive" and
                    r["arm"]=="lego_up_learned")
    neg=sum(r.get("clauses_added",0) for r in rows if
             r["cohort"]=="eval_negative" and r["arm"].startswith("lego_"))
    need(positive>=32,"insufficient positive-control proof detection")
    need(neg==0,"unexpected negative-control clauses")
    report=dict(protocol=PROTO,scores=scores,
         positive_learned_trials_with_additions=positive,
         negative_added_clauses=neg,not_blind_recycled_real=True,
         no_auto_promotion=True,independent_LRAT=False,
         train_sources=len(m["train"]),eval_sources=EVAL_COUNT,
         total_trials=EXPECTED)
    save(ROOT/"report.json",report)
    print("LEGO3_FINAL "+json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","freeze","shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    ROOT.mkdir(parents=True,exist_ok=True);lego.ROOT.mkdir(parents=True,exist_ok=True)
    if a.action=="shard":shard(a.shard)
    else:globals()[a.action]()
