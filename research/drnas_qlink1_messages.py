#!/usr/bin/env python3
"""DRNAS Q-LINK-1: source-proof-carrying guarded relation messages.

Prototype integration: offline BCP probes -> guarded reason clauses on a
second CaDiCaL worker. NOT a live CDCL propagation interface. All claims
are verified against ORIGINAL DIMACS with source parity/implication proofs.
"""
from __future__ import annotations
import argparse
import collections
import itertools
import json
import pathlib
import random
import tempfile
import time

import drnas_x22_parallel_reducer as x22
import drnas_x24_gf2_proof_first as x24
import drnas_lego1_proof_grammar as lego
import drnas_lego3_up_learning as lego3

ROOT=pathlib.Path("mre_qlink1")
PROTO="DRNAS-QLINK1-PROOF-GUARDED-24SOURCE-192E2E-SHORT5-20261109-v1"
ARMS=("race_original","lego3_learned","qlink_shadow","qlink_active")
CAP=5.0
REPS=2
SHARDS=4
TRAIN_COUNT=104
EVAL_POS=8
EVAL_NEG=8
EVAL_REAL=8
EVAL_COUNT=EVAL_POS+EVAL_NEG+EVAL_REAL
EXPECTED=EVAL_COUNT*REPS*len(ARMS)
ANALYSIS_CAP=.42
TRAIN_CAP=.14
MAX_JOIN_TRIES=1200
MAX_JOIN_ROWS=70
MAX_MSG_ROWS=30
MAX_MESSAGES=12
MAX_CLAUSES=24
MAX_PROBE_CLAUSES=1200
MAX_PROBES=36
MAX_WIDTH=5
MAX_REFS=6
BCP_BUDGET=.0025

def need(ok,msg):
    if not ok: raise RuntimeError("QLINK1_FAIL_CLOSED "+str(msg))
def sha(path):return x22.digest(path)
def save(path,obj):return x22.save(path,obj)

def canonical(row):
    return (int(row["rhs"]),tuple(row["vs"]))

def signature(row):
    return "QCL1|"+row["signature"]+"|d%d|w%d|ref%d"%(
      row["depth"],len(row["vs"]),min(5,len(row["refs"])))

def extract(src,deadline):
    original_n,clauses=x22.read_cnf(src)
    with tempfile.TemporaryDirectory(dir=lego.ROOT) as temp:
        leaves,proof,state=lego.get_leaves(src,clauses,pathlib.Path(temp))
    if state!="verified":
        return clauses,leaves,[],dict(state=state,proof=proof,joins=0)
    if time.perf_counter()>=deadline:
        return clauses,leaves,[],dict(state="budget_extract",proof=proof,joins=0)
    base=[]
    for i,(rhs,vs,(kind,_)) in enumerate(leaves[:100]):
        base.append(dict(rhs=rhs,vs=tuple(vs),refs=frozenset((i,)),
                         kind=kind,signature=kind,depth=0))
    seen={canonical(row) for row in base}
    rows=[];attempt=0
    # Proof-carrying JOINs between distinct origin relations.
    def join(left,right,depth):
        nonlocal attempt
        if attempt>=MAX_JOIN_TRIES:return None
        attempt+=1
        if not set(left["vs"]).intersection(right["vs"]):return None
        refs=left["refs"]^right["refs"]
        if not refs or len(refs)>MAX_REFS:return None
        vs=tuple(sorted(set(left["vs"])^set(right["vs"])))
        if not 1<=len(vs)<=MAX_WIDTH:return None
        rhs=left["rhs"]^right["rhs"]
        key=(rhs,vs)
        if key in seen:return None
        seen.add(key)
        row=dict(rhs=rhs,vs=vs,refs=refs,kind="join",
                 depth=depth,signature=lego.signature(left,right,vs))
        need(lego.replay(leaves,refs,clauses)==key,
             "JOIN not proved from original CNF")
        return row
    for i,left in enumerate(base):
        if time.perf_counter()>=deadline or len(rows)>=MAX_JOIN_ROWS:break
        for right in base[i+1:]:
            if len(rows)>=MAX_JOIN_ROWS or time.perf_counter()>=deadline:break
            row=join(left,right,1)
            if row:rows.append(row)
            if attempt>=MAX_JOIN_TRIES:break
    # A second join permits equation-to-equation-to-graph communication,
    # while keeping bounded proof DAGs and no all-pairs global closure.
    first=rows[:20]
    for left in first:
        if time.perf_counter()>=deadline or len(rows)>=MAX_JOIN_ROWS:break
        for right in base[:45]:
            if len(rows)>=MAX_JOIN_ROWS or time.perf_counter()>=deadline:break
            row=join(left,right,2)
            if row:rows.append(row)
            if attempt>=MAX_JOIN_TRIES:break
    return clauses,leaves,rows,dict(state="verified",proof=proof,
                                    joins=attempt,relation_count=len(rows),
                                    base_relations=len(base))

def conditional_clause(row,guard,target):
    """Given XOR row plus guard for all other vars, prove a reason clause."""
    vs=row["vs"];rhs=row["rhs"]
    need(target in vs and len(guard)==len(vs)-1,
         "not exactly one unassigned variable")
    bits={}
    for lit in guard:
        v=abs(lit)
        need(v in vs and v!=target and v not in bits,
             "invalid/conflicting guard")
        bits[v]=(lit>0)
    need(set(bits)==set(vs)-{target},"incomplete guard")
    value=rhs
    for v in bits:value^=int(bits[v])
    effect=target if value else -target
    reason=tuple([-lit for lit in guard]+[effect])
    # Independently verify the guarded implication using complete XOR
    # truth table. No guard-specific unit becomes globally permanent.
    for flags in itertools.product((0,1),repeat=len(vs)):
        assignment=dict(zip(vs,flags))
        if sum(flags)%2!=rhs:continue
        need(any(assignment[abs(lit)]==(lit>0) for lit in reason),
             "guarded reason is not entailed by source-proof relation")
    return dict(guard=tuple(guard),effect=effect,reason=reason,
                watch=vs,ttl=1,epoch=0,proof_refs=tuple(sorted(row["refs"])),
                relation=(rhs,vs),signature=signature(row))

def guard_candidates(row):
    vs=row["vs"]
    target=vs[-1]
    others=vs[:-1]
    # Exact conditional proof clauses. Deterministic, bounded, not
    # determined by planted SAT witness or hidden answer labels.
    combos=list(itertools.product((False,True),repeat=len(others)))
    if len(combos)>4:
        combos=[combos[0],combos[1],combos[-2],combos[-1]]
    for flags in combos:
        guard=tuple(v if bit else -v for v,bit in zip(others,flags))
        yield conditional_clause(row,guard,target)

def probe_bcp(clauses,msg,deadline):
    """ACK means positive benefit under *simulated* trail, not CDCL ACK."""
    if len(clauses)>MAX_PROBE_CLAUSES or time.perf_counter()>=deadline:
        return dict(ack=False,reason="large_or_budget",gain=0,probes=0)
    begin=time.perf_counter()
    stop=min(deadline,begin+BCP_BUDGET)
    before,bad=lego3.bcp(clauses,msg["guard"],stop,max_rounds=8)
    if time.perf_counter()>=stop:
        return dict(ack=False,reason="budget",gain=0,probes=0)
    # Extending with a globally entailed guarded reason.
    after,conflict=lego3.bcp(clauses+[msg["reason"]],
                             msg["guard"],stop,max_rounds=8)
    if time.perf_counter()>=stop:
        return dict(ack=False,reason="budget",gain=0,probes=0)
    if bad:
        return dict(ack=False,reason="baseline_conflict",gain=0,probes=1)
    gain=min(10,len(set(after)-set(before)))+(5 if conflict else 0)
    return dict(ack=gain>0,reason="new_UP" if gain>0 else "duplicate_UP",
                gain=gain,probes=1)

def prepare(src,table,mode):
    start=time.perf_counter();deadline=start+ANALYSIS_CAP
    clauses,leaves,rows,extraction=extract(src,deadline)
    report=dict(state=extraction["state"],base_relations=extraction.get("base_relations",0),
        joins=extraction.get("joins",0),relation_count=len(rows),
        sent=0,acks=0,probe_gain=0,probes=0,source_replayed=0,
        conditional_proofs=0,duplicate=0,dropped=collections.Counter(),
        clause_count=0,selected=[],guarded_only=True,
        live_CDCL_integration=False)
    if extraction["state"]!="verified":
        report["elapsed_s"]=round(time.perf_counter()-start,6)
        report["dropped"]=dict(report["dropped"])
        return [],report
    # Learned prior only orders verified relations; it can never assert
    # something true. No outcome labels or SAT runtime used in training.
    rows.sort(key=lambda r:(
        -table.get(signature(r),{}).get("gain_sum",0)/
             max(1,table.get(signature(r),{}).get("probes",0)),
        len(r["vs"]),len(r["refs"]),r["depth"],tuple(r["vs"])))
    original={tuple(sorted(set(c))) for c in clauses}
    seen=set(original);selected=[];candidates=0;seen_msgs=set()
    for row in rows[:MAX_MSG_ROWS]:
        if time.perf_counter()>=deadline:
            report["dropped"]["budget"]+=1;break
        need(lego.replay(leaves,row["refs"],clauses)==canonical(row),
             "source proof failed before Q-LINK SEND")
        report["source_replayed"]+=1
        for msg in guard_candidates(row):
            if time.perf_counter()>=deadline or report["probes"]>=MAX_PROBES:
                report["dropped"]["budget"]+=1;break
            reason_key=tuple(sorted(set(msg["reason"])))
            if reason_key in seen_msgs:
                report["duplicate"]+=1;continue
            seen_msgs.add(reason_key)
            report["conditional_proofs"]+=1
            if reason_key in seen:
                report["dropped"]["original_clause"]+=1;continue
            ack=probe_bcp(clauses,msg,deadline)
            report["probes"]+=ack["probes"]
            if not ack["ack"]:
                report["dropped"][ack["reason"]]+=1;continue
            report["acks"]+=1
            report["probe_gain"]+=ack["gain"]
            # QLINK shadow does identical proof/replay and message selection
            # but never modifies the solver's input. This isolates overhead.
            if mode=="active" and len(selected)<MAX_CLAUSES and len(selected)<MAX_MESSAGES:
                seen.add(reason_key)
                selected.append(msg["reason"])
                report["sent"]+=1
            else:
                report["dropped"]["shadow" if mode=="shadow" else "send_cap"]+=1
            if len(selected)>=MAX_MESSAGES:break
        if len(selected)>=MAX_MESSAGES:break
    report["clause_count"]=len(selected)
    report["selected"]=[dict(reason=list(c)) for c in selected[:3]]
    report["state"]="verified_sent" if selected else "verified_no_send"
    report["elapsed_s"]=round(time.perf_counter()-start,6)
    report["dropped"]=dict(report["dropped"])
    return selected,report

def train(training):
    table={};logs=[]
    for case in training:
        src=x22.ROOT/"cases"/case["filename"]
        need(sha(src)==case["sha256"],"training SHA mismatch")
        start=time.perf_counter();stop=start+TRAIN_CAP
        clauses,leaves,rows,source=extract(src,stop)
        got=0;acks=0;gain=0
        if source["state"]=="verified" and len(clauses)<=MAX_PROBE_CLAUSES:
            for row in rows[:20]:
                if time.perf_counter()>stop:break
                need(lego.replay(leaves,row["refs"],clauses)==canonical(row),
                     "train source proof mismatch")
                for msg in itertools.islice(guard_candidates(row),2):
                    if time.perf_counter()>stop:break
                    p=probe_bcp(clauses,msg,stop)
                    if not p["probes"]:continue
                    sig=signature(row)
                    item=table.setdefault(sig,dict(probes=0,gain_sum=0,
                                                   ack_count=0,cases=0))
                    item["probes"]+=1
                    item["gain_sum"]+=p["gain"]
                    item["ack_count"]+=int(p["ack"])
                    got+=1;acks+=int(p["ack"]);gain+=p["gain"]
                    if got>=24:break
                if got>=24:break
        logs.append(dict(sha256=case["sha256"],cohort=case["cohort"],
            rows=len(rows),probes=got,acks=acks,gain=gain,
            elapsed_s=round(time.perf_counter()-start,6),
            extractor=source["state"]))
    need(len(table)>=2,"no trainable signatures")
    need(sum(x["gain"]>0 for x in logs)>=6,
         "no positive guarded propagation gain in training")
    return table,logs

def selftest():
    """Proof-carrying messages, guard and stale-epoch safety controls."""
    # XOR(a,b,x)=0 XOR(a,b,y)=1 -> x XOR y =1.
    eq1=lego2_xor((1,2,3),0)
    eq2=lego2_xor((1,2,4),1)
    clauses=eq1+eq2
    leaves=[
      (0,(1,2,3),("xor",tuple(range(4)))),
      (1,(1,2,4),("xor",tuple(range(4,8))))]
    row=dict(rhs=1,vs=(3,4),refs=frozenset((0,1)),
             depth=1,signature="xor:xor")
    need(lego.replay(leaves,row["refs"],clauses)==(1,(3,4)),
         "source XOR proof composition")
    msg=conditional_clause(row,(3,),4)
    need(msg["effect"]==-4 and tuple(msg["reason"])==(-3,-4),
         "conditional message sign or guard")
    x=probe_bcp(clauses,msg,time.perf_counter()+.1)
    need(x["ack"] and x["gain"]>=1,"new guarded propagation absent")
    # The BCP message must not become an unconditional unit:
    positive_models=0
    for bits in itertools.product((False,True),repeat=4):
        assignment=dict(zip(range(1,5),bits))
        if x22.holds(clauses,assignment):
            positive_models+=1
            need(x22.holds(clauses+[msg["reason"]],assignment),
                 "message changed original satisfying set")
    need(positive_models>=2,"not a conditional implication")
    # Freshness. Epoch 2 messages cannot be applied to epoch 3 trail.
    need(not stale_message(dict(msg,epoch=2),3),
         "stale message was accepted")
    # Partially missing XOR cube cannot act as a source leaf.
    negative=eq1[:-1]+eq2[:-1]
    try:
        lego.replay(leaves,row["refs"],negative)
    except (RuntimeError,IndexError):
        pass
    else:
        need(False,"incomplete parity cube incorrectly accepted")
    print("QLINK1_SELFTEST_PASS "+json.dumps(
       dict(new_propagation=x["gain"],full_truth_table_models=positive_models,
            stale_epoch_rejected=True,negative_halfcube_rejected=True,
            conditional_reason_proved=True),sort_keys=True),flush=True)

def stale_message(msg,epoch):
    return msg["epoch"]==epoch and msg["ttl"]>=1

def lego2_xor(vs,rhs):
    out=[]
    for bits in itertools.product((0,1),repeat=len(vs)):
        if sum(bits)%2==rhs:continue
        out.append(tuple(-v if bits[i] else v for i,v in enumerate(vs)))
    return out

def choose():
    frozen=lego3.verify()
    cases=frozen["evaluation"];training=frozen["train"]
    positives=[]
    for family in range(8):
        matching=[c for c in cases if c["cohort"]=="eval_positive"
                  and c["family"]==family]
        need(len(matching)==4,"each family")
        positives.append(matching[2])
    negative=[c for c in cases if c["cohort"]=="eval_negative"]
    real=[c for c in cases if c["cohort"]=="eval_real_reused_x22"]
    need(len(negative)==EVAL_NEG and len(real)==EVAL_REAL,
         "source cohort sizes")
    evaluation=positives+negative+real
    need(len(evaluation)==EVAL_COUNT and len(training)==TRAIN_COUNT,
         "train/eval sizes")
    need(not ({c["sha256"] for c in training}&
              {c["sha256"] for c in evaluation}),"source leakage")
    return training,evaluation

def freeze():
    ROOT.mkdir(parents=True,exist_ok=True);lego.ROOT.mkdir(parents=True,exist_ok=True)
    need(x24.BIN.exists(),"native helper required")
    selftest()
    training,evaluation=choose()
    table,log=train(training)
    save(ROOT/"table.json",table)
    save(ROOT/"train_log.json",log)
    save(ROOT/"manifest.json",dict(protocol=PROTO,arms=ARMS,
         cap_s=CAP,shards=SHARDS,repetitions=REPS,
         train=[dict(c) for c in training],
         evaluation=[dict(c) for c in evaluation],
         expected_trials=EXPECTED,source_original_sha_disjoint=True,
         model_training="bounded_BCP_guarded_benefit_no_solver_labels",
         live_CDCL_integration=False,
         source_real_reused_not_blind=True,independent_LRAT=False,
         no_auto_promotion=True,
         qlink_code_sha256=sha(__file__),
         lego1_sha256=sha("research/drnas_lego1_proof_grammar.py"),
         lego3_sha256=sha("research/drnas_lego3_up_learning.py"),
         lego3_model_sha256=sha(lego3.ROOT/"model.json"),
         lego3_manifest_sha256=sha(lego3.ROOT/"manifest.json"),
         native_gf2_sha256=sha(x24.BIN),
         x22_reference_sha256=sha("prior_x22/report.json"),
         x22_manifest_sha256=sha(x22.ROOT/"manifest.json"),
         table_sha256=sha(ROOT/"table.json"),
         source_train_count=TRAIN_COUNT))
    verify()
    print("QLINK1_FROZEN "+json.dumps(dict(
        train=len(training),positive=EVAL_POS,negative=EVAL_NEG,real=EVAL_REAL,
        table_signatures=len(table),trained_acks=sum(x["acks"] for x in log),
        trained_gain=sum(x["gain"] for x in log),
        trials=EXPECTED,shards=SHARDS,cap_s=CAP),sort_keys=True),flush=True)

def verify():
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["arms"]==list(ARMS) and
         m["cap_s"]==CAP and m["expected_trials"]==EXPECTED and
         len(m["train"])==TRAIN_COUNT and
         len(m["evaluation"])==EVAL_COUNT,"frozen protocol invalid")
    expected=dict(qlink_code_sha256=sha(__file__),
         lego1_sha256=sha("research/drnas_lego1_proof_grammar.py"),
         lego3_sha256=sha("research/drnas_lego3_up_learning.py"),
         lego3_model_sha256=sha(lego3.ROOT/"model.json"),
         lego3_manifest_sha256=sha(lego3.ROOT/"manifest.json"),
         native_gf2_sha256=sha(x24.BIN),
         x22_reference_sha256=sha("prior_x22/report.json"),
         x22_manifest_sha256=sha(x22.ROOT/"manifest.json"),
         table_sha256=sha(ROOT/"table.json"))
    for key,value in expected.items():need(m[key]==value,key+" changed")
    all_cases=m["train"]+m["evaluation"]
    need(len({c["sha256"] for c in all_cases})==len(all_cases),
         "SHA duplicate train/eval")
    for c in all_cases:
        p=x22.ROOT/"cases"/c["filename"]
        need(sha(p)==c["sha256"],"original source SHA mutated")
    return m

def run_trial(case,rep,arm,table,lego_table):
    src=x22.ROOT/"cases"/case["filename"]
    need(sha(src)==case["sha256"],"original pre-trial SHA mismatch")
    if arm in ("race_original","lego3_learned"):
        parent="race_original" if arm=="race_original" else "lego_up_learned"
        old=x22.CAP
        try:
            x22.CAP=CAP
            row=lego3.run_trial(case,rep,parent,lego_table)
        finally:x22.CAP=old
        row.update(protocol=PROTO,arm=arm,qlink={})
    else:
        begin=time.perf_counter();cpu_before=x22.child_cpu()
        status="TIMEOUT";winner=None;verified=False
        cpus=x22.cpus();source_n,source_clauses=x22.read_cnf(src)
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            tmp=pathlib.Path(tmp);added=[]
            try:
                added,telemetry=prepare(src,table,
                     "active" if arm=="qlink_active" else "shadow")
            except Exception as e:
                added=[];telemetry=dict(state="fail_closed",error=str(e)[:240],
                     sent=0,acks=0,probe_gain=0,probes=0,source_replayed=0)
            prep_s=time.perf_counter()-begin
            if added:
                chosen=tmp/"augmented.cnf"
                with chosen.open("w") as f:
                    f.write("p cnf %d %d\n"%(source_n,len(source_clauses)+len(added)))
                    for c in itertools.chain(source_clauses,added):
                        f.write(" ".join(map(str,c))+" 0\n")
                need(x22.read_cnf(chosen)[1]==source_clauses+added,
                     "enhanced DIMACS mismatch")
            else:chosen=src
            entries=[]
            try:
                if time.perf_counter()-begin<CAP-.1:
                    entries.append(x22.launch("kissat",
                         [x22.KISSAT,"--seed="+str(x22.seed(case,rep)),src],
                         cpus[0],tmp))
                    entries.append(x22.launch("cadical",[x22.CADICAL,chosen],
                         cpus[1],tmp))
                    while time.perf_counter()-begin<CAP:
                        for entry in entries:
                            if entry["read"] or entry["p"].poll() is None:continue
                            entry["read"]=True
                            stdout,err=x22.read_output(entry)
                            status,verified=x22.solver_result(entry["name"],
                                  entry["p"].returncode,stdout,source_clauses,{})
                            winner=entry["name"];break
                        if winner or all(x["read"] for x in entries):break
                        time.sleep(.003)
            finally:x22.cleanup(entries)
        elapsed=time.perf_counter()-begin
        if elapsed>CAP or status not in ("SAT","UNSAT"):
            status="TIMEOUT";winner=None;verified=False
        row=dict(protocol=PROTO,arm=arm,rep=rep,cap_s=CAP,
            seed=x22.seed(case,rep),original_sha256=case["sha256"],
            gbd=case["gbd"],status=status,winner=winner,
            SAT_original_witness_verified=verified,
            UNSAT_independent_LRAT=False,E2E_s=round(elapsed,6),
            child_cpu_s=round(x22.child_cpu()-cpu_before,6),
            preprocessing_E2E_s=round(prep_s,6),
            added_guarded_reason_clauses=len(added),qlink=telemetry)
    row.update(cohort=case["cohort"],family=case["family"],
               expected_sat=case["expected_sat"],synthetic=case["synthetic"])
    need(sha(src)==case["sha256"],"post trial source mutated")
    return row

def shard(i):
    need(0<=i<SHARDS,"shard number")
    m=verify()
    learned=json.loads((ROOT/"table.json").read_text())
    lego_table=json.loads((lego3.ROOT/"model.json").read_text())
    cases=m["evaluation"][i::SHARDS];rows=[]
    need(len(cases)==EVAL_COUNT//SHARDS,"shard distribution")
    for case in cases:
        for rep in range(REPS):
            arms=list(ARMS);random.Random(x22.seed(case,rep)).shuffle(arms)
            for arm in arms:
                row=run_trial(case,rep,arm,learned,lego_table)
                rows.append(row);save(ROOT/("shard-%d.json"%i),rows)
                print("QLINK1_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==EXPECTED//SHARDS,"shard incomplete")
    print("QLINK1_SHARD_PASS",i,len(rows),flush=True)

def audit():
    m=verify();rows=[]
    for i in range(SHARDS):
        p=ROOT/("shard-%d.json"%i)
        need(p.exists(),"shard artifact missing")
        part=json.loads(p.read_text())
        need(len(part)==EXPECTED//SHARDS,"shard incomplete")
        rows.extend(part)
    need(len(rows)==EXPECTED,"incomplete E2E trials")
    ref=json.loads(pathlib.Path("prior_x22/report.json").read_text())
    original_unsat=ref["confirmed_original_UNSAT"]
    known={c["sha256"]:c for c in m["evaluation"]}
    seen=set()
    for row in rows:
        key=(row["original_sha256"],row["rep"],row["arm"])
        need(key not in seen and row["arm"] in ARMS and
             row["cap_s"]==CAP and row["protocol"]==PROTO,
             "invalid duplicate row or cap")
        seen.add(key)
        c=known[row["original_sha256"]]
        need(row["cohort"]==c["cohort"],"cohort mislabeled")
        if row["status"]=="SAT":
            need(row["SAT_original_witness_verified"],
                 "SAT not verified against original CNF")
            need(not original_unsat.get(row["original_sha256"],False),
                 "SAT contradicts frozen original UNSAT reference")
        if c["expected_sat"]:need(row["status"]!="UNSAT",
             "planted SAT control contradicted by UNSAT")
        if row["arm"]=="qlink_shadow":
            need(row.get("added_guarded_reason_clauses",0)==0 and
                 row.get("qlink",{}).get("sent",0)==0,
                 "shadow transmitted a QLINK message")
    result={}
    for arm in ARMS:
        result[arm]={}
        for cohort in ("all","eval_positive","eval_negative",
                       "eval_real_reused_x22"):
            subset=[r for r in rows if r["arm"]==arm and
                (cohort=="all" or r["cohort"]==cohort)]
            accepted=[r for r in subset if r["status"]=="SAT" or
                (r["status"]=="UNSAT" and original_unsat.get(
                  r["original_sha256"],False))]
            result[arm][cohort]=dict(trials=len(subset),
                accepted_solved=len(accepted),
                verified_SAT=sum(r["status"]=="SAT" for r in accepted),
                UNSAT_cross_agreement_no_LRAT=sum(r["status"]=="UNSAT"
                                                   for r in accepted),
                PAR2_s=round(sum(r["E2E_s"] if r in accepted else 2*CAP
                                 for r in subset),6),
                child_CPU_s=round(sum(r.get("child_cpu_s",0) for r in subset),6),
                preproc_s=round(sum(r.get("preprocessing_E2E_s",0)
                                     for r in subset),6),
                source_proof_replays=sum(r.get("qlink",{}).get(
                                         "source_replayed",0) for r in subset),
                messages_sent=sum(r.get("qlink",{}).get("sent",0)
                                   for r in subset),
                simulated_acks=sum(r.get("qlink",{}).get("acks",0)
                                     for r in subset),
                simulated_BCP_gain=sum(r.get("qlink",{}).get("probe_gain",0)
                                        for r in subset),
                fallbacks=sum(r.get("qlink",{}).get("state","").startswith(
                        ("budget","fail","native")) for r in subset))
    for cohort in result["race_original"]:
        base=result["race_original"][cohort]["PAR2_s"]
        for arm in ARMS:
            a=result[arm][cohort]
            a["PAR2_delta_vs_original_pct"]=round(100*(a["PAR2_s"]/base-1),4)
    pos=sum(r.get("qlink",{}).get("sent",0)>0 for r in rows
        if r["arm"]=="qlink_active" and r["cohort"]=="eval_positive")
    need(pos>=1,"no proof-safe positive-control QLINK message")
    report=dict(protocol=PROTO,total_trials=len(rows),
       training_sources=TRAIN_COUNT,eval_original_SHA=EVAL_COUNT,
       positive_controls_with_sent_message=pos,scores=result,
       independent_LRAT=False,live_CDCL_integration=False,
       real_recycled_not_blind=True,no_auto_promotion=True)
    save(ROOT/"report.json",report)
    print("QLINK1_FINAL "+json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("selftest","freeze","shard","audit"))
    parser.add_argument("--shard",type=int,default=0)
    args=parser.parse_args()
    ROOT.mkdir(parents=True,exist_ok=True)
    lego.ROOT.mkdir(parents=True,exist_ok=True)
    if args.action=="shard":shard(args.shard)
    else:globals()[args.action]()
