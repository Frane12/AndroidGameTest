#!/usr/bin/env python3
"""DMD5: exhaustive six-lemma subset ablation, then fixed-shape transfer.

TRAIN: all 64 subsets of exactly six independently source-proved DMD1/DMD2
lemmas on one known SAT EQUIV7 original, two repeated 4-s one-core trials.
The *same* CaDiCaL 2.1.0 binary adds chosen source-consequent clauses
before solving; no external IPASIR observer runs in either active/control.
All trials rerun DMD1+proof replay+DMD2 gate INSIDE full E2E budget.

TRANSFER: preregister winner's clause length/polarity shapes using train only,
then test on the other 24 EQUIV7 original SHA (DMD4-disjoint but not globally
unseen) with clean, Kissat, all proved DMD1, DMD2 gate and frozen shape arms.
No independent UNSAT LRAT: backend-only UNSAT; SAT witness replayed on
the exact original CNF; no promotion.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, os, pathlib, random, re, resource
import tempfile, time
import dmd1_bench as d1

PROTO="DRNAS-DMD5-6LEMMA-FULL-SUBSET-ABLAT-TRANSFER-v1"
ROOT=pathlib.Path("mre_dmd5")
SOURCE=pathlib.Path("mre_equiv7")
DMD1=ROOT/"bin/dmd1_anf"
GATE=ROOT/"bin/dmd2_gate"
LIVE=ROOT/"bin/dmd5_live"
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
TRAIN_SHA="5e7c2b214b6a3e7b97b947c5b0f8ffa2b5588892636690dfdf9b20989b17fd1f"
TRAIN_FILE="5ac44f542fd2cd4492067deb7791629a.cnf"
TRAIN_CAP=4.0
TRANSFER_CAP=6.0
REPS=2
SHARDS=4
TRANSFER_ARMS=("cadical_clean","kissat_original","dmd1_all","dmd2_gate","dmd5_frozen_shapes")
DMD1_MS=200
GATE_MS=90
d1.ROOT=ROOT

def need(ok,msg):
    if not ok:raise RuntimeError("DMD5_FAIL_CLOSED "+str(msg))
def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()
def read_cases():
    m=json.loads((SOURCE/"manifest.json").read_text())
    need(len(m["cases"])==48 and m["sample_policy"].startswith("SHA-salted official"),
         "EQUIV7 source manifest drift")
    raw=sorted(m["cases"],key=lambda c:c["sha256"])
    all_cases=[]
    for c in raw:
        p=SOURCE/"cases"/c["filename"]
        need(p.is_file() and d1.sha(p)==c["sha256"],"original source SHA mismatch")
        all_cases.append(dict(filename=c["filename"],sha256=c["sha256"],path=str(p)))
    train=next((c for c in all_cases if c["sha256"]==TRAIN_SHA),None)
    need(train is not None and train["filename"]==TRAIN_FILE,"training identity drift")
    need(train in all_cases[:24],"train source not from DMD4 known cohort")
    remaining=all_cases[24:]
    need(len(remaining)==24 and all(c["sha256"]!=TRAIN_SHA for c in remaining),
         "DMD4-disjoint transfer is not disjoint")
    return train,remaining

def core():
    return min(os.sched_getaffinity(0))
def used_cpu(who):
    u=resource.getrusage(who)
    return u.ru_utime+u.ru_stime
def add_cnf(path,n,original,chosen):
    with pathlib.Path(path).open("w") as f:
        f.write(f"p cnf {n} {len(original)+len(chosen)}\n")
        for c in [*original,*chosen]:
            f.write(" ".join(str(l) for l in c)+" 0\n")
def shape(clause):
    return f"length{len(clause)}_pos{sum(v>0 for v in clause)}"
def parse_native(out):
    v=[x[len("DMD5_RESULT "):] for x in out.splitlines()
       if x.startswith("DMD5_RESULT ")]
    need(len(v)==1,"missing DMD5 native result")
    data=json.loads(v[0])
    need(data["mode"] in ("clean","clauses_only") and not data["callback_error"],
         "unexpected native mode/callback error")
    metrics={}
    for line in out.splitlines():
        if not line.startswith("c "):continue
        for k in ("decisions","conflicts","learned","propagations"):
            m=re.search(r"\b"+k+r"\s*:\s*([0-9][0-9,]*)",line)
            if m:metrics[k]=int(m.group(1).replace(",",""))
    return data,metrics
def verify_sat(out,original):
    vals={}
    for line in out.splitlines():
        if not line.startswith("v "):continue
        for t in line.split()[1:]:
            v=int(t)
            if not v:continue
            need(abs(v) not in vals or vals[abs(v)]==(v>0),
                 "conflicting SAT assignments")
            vals[abs(v)]=v>0
    need(vals and d1.holds(original,vals),"SAT witness does not satisfy ORIGINAL CNF")
    return True

def discover(case,work,pinned,gate=True):
    original=pathlib.Path(case["path"])
    n,clauses=d1.read_cnf(original)
    aug=work/"full.cnf"
    proof_path=work/"proof.json"
    rc,out,err,sec,cpu,timeout=d1.run_process(
       [DMD1,original,aug,proof_path,DMD1_MS,48],2.0,pinned)
    need(not timeout and rc==0 and proof_path.is_file(),
         "DMD1 native extraction failed "+err[-200:])
    proof=json.loads(proof_path.read_text())
    d1.proof_replay(original,aug,proof)
    all_lemmas=[tuple(l["clause"]) for l in proof["lemmas"]]
    gate_lemmas=[]
    gate_info=dict(candidates=0,selected=0,selected_indices=[],
                   novel_directions=0,timed_out=False)
    if gate and all_lemmas:
        target=work/"gated.cnf"
        rc,output,err,sec_g,cpu_g,timeout=d1.run_process(
           [GATE,original,aug,target,GATE_MS],1.0,pinned)
        cpu+=cpu_g
        need(not timeout and rc==0,"DMD2 gate failed "+err[-200:])
        z=[x[len("DMD2_GATE "):] for x in output.splitlines()
           if x.startswith("DMD2_GATE ")]
        need(len(z)==1,"native gate telemetry missing")
        gate_info=json.loads(z[0])
        indexes=gate_info["selected_indices"]
        need(gate_info["candidates"]==len(all_lemmas) and
             gate_info["selected"]==len(indexes) and
             len(indexes)==len(set(indexes)) and
             all(type(i)==int and 0<=i<len(all_lemmas) for i in indexes),
             "gate subset inconsistent")
        gate_lemmas=[all_lemmas[i] for i in indexes]
        need(target.is_file()==bool(gate_lemmas),"gate CNF existence mismatch")
        if gate_lemmas:
            nn,cl=d1.read_cnf(target)
            need(nn==n and cl==clauses+gate_lemmas,"gate modified original or selected wrong subset")
    return n,clauses,proof,all_lemmas,gate_lemmas,gate_info,cpu

def frozen():
    train,transfer=read_cases()
    with tempfile.TemporaryDirectory(prefix="dmd5-freeze-") as tmp:
        n,clauses,proof,all_lemmas,gate_lemmas,gate_info,cpu=discover(
            train,pathlib.Path(tmp),core())
    need(len(all_lemmas)==13 and len(gate_lemmas)==6,
         "expected 13 original source-proved clauses and SIX gated clauses")
    ids=gate_info["selected_indices"]
    obj=dict(protocol=PROTO,training_sha256=TRAIN_SHA,training_file=TRAIN_FILE,
       source_n=n,source_clause_count=len(clauses),
       proof_replayed=True,DMD1_original_lemmas=all_lemmas,
       gated_lemmas=gate_lemmas,gate_indexes=ids,
       gated_shapes=[shape(v) for v in gate_lemmas],
       original_provenance=proof["lemmas"],
       derived_sha256=digest(gate_lemmas),
       transfer_SHA256=[c["sha256"] for c in transfer],
       not_blind=True)
    ROOT.mkdir(exist_ok=True)
    (ROOT/"freeze.json").write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
    print("DMD5_FREEZE_PASS",json.dumps({k:v for k,v in obj.items()
        if k not in ("original_provenance","DMD1_original_lemmas")},
        sort_keys=True),flush=True)
    return obj
def check_frozen():
    f=json.loads((ROOT/"freeze.json").read_text())
    need(f["protocol"]==PROTO and f["training_sha256"]==TRAIN_SHA and
         f["derived_sha256"]==digest(f["gated_lemmas"]) and
         len(f["gated_lemmas"])==6,"frozen train lemmas drift")
    return f

def solve(source,n,clauses,extra,solver,cap,begin,work,pinned):
    available=cap-(time.monotonic()-begin)
    if available<0.22:
        return "TIMEOUT",False,{},0.
    if solver=="kissat":
        rc,out,err,sec,scpu,timed=d1.run_process(
            [KISSAT,source],available,pinned)
        if timed:return "TIMEOUT",False,{},scpu
        verdict,verified=d1.outcome(rc,out,clauses)
        return verdict,verified,{},scpu
    target=work/"selected.cnf"
    add_cnf(target,n,clauses,extra)
    mode="clauses_only" if extra else "clean"
    ncap=max(0.20,available-0.15)
    rc,out,err,sec,scpu,timed=d1.run_process(
       [LIVE,source,target,mode,f"{ncap:.5f}"],available,pinned)
    if timed:return "TIMEOUT",False,{},scpu
    need(rc in (0,10,20),"CaDiCaL abnormal exit "+err[-250:])
    d,s=parse_native(out)
    need(d["mode"]==mode and d["candidate_lemmas"]==len(extra),"native injected lemma count")
    status=d["status"]
    need((rc==0 and status=="TIMEOUT") or (rc==10 and status=="SAT") or
         (rc==20 and status=="UNSAT"),"native status/exit mismatch")
    verified=verify_sat(out,clauses) if status=="SAT" else False
    need(verified==d["model_original_verified"],"native and independent SAT checks differ")
    return status,verified,s,scpu

def trial_ablate(mask,rep):
    f=check_frozen()
    train,_=read_cases()
    begin=time.monotonic()
    pre_cpu=used_cpu(resource.RUSAGE_CHILDREN)
    with tempfile.TemporaryDirectory(prefix="dmd5-ablate-") as t:
        work=pathlib.Path(t)
        n,clauses,proof,all_l,gate_l,gate,child=discover(train,work,core())
        need(digest(gate_l)==f["derived_sha256"] and
             [list(x) for x in gate_l]==f["gated_lemmas"],
             "training lemma signature changed; refuse comparison")
        chosen=[v for i,v in enumerate(gate_l) if mask & (1<<i)]
        status,verified,stats,scpu=solve(
            train["path"],n,clauses,chosen,"cadical",TRAIN_CAP,begin,work,core())
    elapsed=time.monotonic()-begin
    if status=="TIMEOUT" and elapsed>TRAIN_CAP:elapsed=TRAIN_CAP
    result=dict(protocol=PROTO,phase="ablation",cohort="known_dev_original",
       sha256=TRAIN_SHA,filename=TRAIN_FILE,
       mask=mask,rep=rep,selected_lemma_indices=[i for i in range(6) if mask&(1<<i)],
       selected_count=len(chosen),selected_shapes=[shape(v) for v in chosen],
       selected_digest=digest(chosen),
       status=status,sat_original_verified=verified,UNSAT_independent_LRAT=False,
       PAR2_s=round(elapsed if status!="TIMEOUT" else 2*TRAIN_CAP,6),
       e2e_s=round(elapsed,6),
       cdcl_stats=stats,cap_s=TRAIN_CAP,
       full_CPU_s=round(used_cpu(resource.RUSAGE_CHILDREN)-pre_cpu,6),
       one_logical_cpu=True,proof_replayed=True)
    return result

def ablate(shard):
    need(0<=shard<SHARDS,"bad ablation shard")
    f=check_frozen()
    ROOT.mkdir(exist_ok=True)
    masks=[m for m in range(64) if m%SHARDS==shard]
    runs=[(m,r) for m in masks for r in range(REPS)]
    random.Random(30201+shard).shuffle(runs)
    rows=[]
    for mask,rep in runs:
        row=trial_ablate(mask,rep)
        rows.append(row)
        (ROOT/f"ablation-{shard}.json").write_text(json.dumps(rows,sort_keys=True))
        print("DMD5_ABLATE_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==32,"ablation shard missing trials")
    print("DMD5_ABLATE_SHARD_PASS",shard,len(rows),flush=True)

def select():
    f=check_frozen()
    rows=[]
    for shard in range(SHARDS):
        p=ROOT/f"ablation-{shard}.json"
        need(p.is_file(),"missing ablation shard")
        q=json.loads(p.read_text())
        need(len(q)==32,"bad ablation shard trial count")
        rows.extend(q)
    expected={(m,rep) for m in range(64) for rep in range(REPS)}
    found={(x["mask"],x["rep"]) for x in rows}
    need(len(rows)==len(found)==len(expected)==128 and found==expected,
         "ablation 128 unique trial mismatch")
    cost={}
    for m in range(64):
        q=[x for x in rows if x["mask"]==m]
        need(len(q)==2 and all(x["proof_replayed"] for x in q),
             "training proof not replayed")
        cost[m]=dict(PAR2_s=round(sum(x["PAR2_s"] for x in q),6),
                     solved=sum(x["status"]!="TIMEOUT" for x in q),
                     verified_sat=sum(x["sat_original_verified"] for x in q),
                     decision_sum=sum(x["cdcl_stats"].get("decisions",0) for x in q),
                     conflict_sum=sum(x["cdcl_stats"].get("conflicts",0) for x in q),
                     selected_count=m.bit_count())
    valid=[m for m in range(64) if cost[m]["verified_sat"]==2]
    need(valid,"no solved ablation masks; conservative selection impossible")
    best=min(valid,key=lambda m:(cost[m]["PAR2_s"],m.bit_count(),m))
    threshold=cost[best]["PAR2_s"]*1.05
    close=[m for m in valid if cost[m]["PAR2_s"]<=threshold]
    winner=min(close,key=lambda m:(m.bit_count(),cost[m]["PAR2_s"],m))
    baseline=cost[0]["PAR2_s"]
    improvement=1-cost[winner]["PAR2_s"]/baseline
    accepted=bool(winner and cost[0]["verified_sat"]==2 and improvement>=0.05)
    selected=[f["gated_lemmas"][i] for i in range(6) if winner&(1<<i)] if accepted else []
    shapes=sorted(set(shape(v) for v in selected))
    learned=dict(protocol=PROTO,training_sha256=TRAIN_SHA,study_only=True,
       selected_mask=winner if accepted else 0,
       raw_winning_mask=winner,
       winning_clauses=selected,
       winning_shape_classes=shapes,
       no_promotion=True,
       one_training_source_only=True,
       selection_requires_two_verified_SAT=True,
       reference_mask0_PAR2_s=baseline,
       winning_PAR2_s=cost[winner]["PAR2_s"],
       estimated_relative_gain=round(improvement,6),
       accepted_for_exploratory_transfer=accepted,
       all_mask_results={str(k):v for k,v in cost.items()},
       leave_one_out={str(i):dict(without=cost[63^(1<<i)],
           full=cost[63],PAR2_loss_removing_lemma=round(
                  cost[63^(1<<i)]["PAR2_s"]-cost[63]["PAR2_s"],6))
                  for i in range(6)},
       singletons={str(i):cost[1<<i] for i in range(6)},
       candidate_lemma_source_provenance=f["original_provenance"])
    (ROOT/"selection.json").write_text(json.dumps(learned,indent=2,sort_keys=True)+"\n")
    print("DMD5_SELECTION_PASS",json.dumps({k:v for k,v in learned.items()
       if k not in ("all_mask_results","candidate_lemma_source_provenance")},
       sort_keys=True),flush=True)

def trial_transfer(case,arm,rep,selection):
    need(arm in TRANSFER_ARMS and rep in (0,1),"unregistered transfer arm")
    need(case["sha256"] in selection["transfer_sha"],"transfer SHA not preregistered")
    source=pathlib.Path(case["path"])
    begin=time.monotonic()
    before=used_cpu(resource.RUSAGE_CHILDREN)
    n,clauses=d1.read_cnf(source)
    proof_count=0
    gated_count=0
    chosen=[]
    with tempfile.TemporaryDirectory(prefix="dmd5-transfer-") as t:
        w=pathlib.Path(t)
        if arm not in ("cadical_clean","kissat_original"):
            nn,cc,proof,all_l,gate_l,gate,cpu=discover(
                case,w,core(),gate=(arm=="dmd2_gate"))
            need(n==nn and clauses==cc,"source CNF modified by preprocessing")
            proof_count=len(all_l)
            gated_count=len(gate_l)
            if arm=="dmd1_all":chosen=all_l
            elif arm=="dmd2_gate":chosen=gate_l
            else:
                keep=set(selection["winning_shape_classes"])
                chosen=[v for v in all_l if shape(v) in keep] if keep else []
        status,verified,stats,scpu=solve(
            source,n,clauses,chosen,
            "kissat" if arm=="kissat_original" else "cadical",
            TRANSFER_CAP,begin,w,core())
    elapsed=time.monotonic()-begin
    if status=="TIMEOUT" and elapsed>TRANSFER_CAP:elapsed=TRANSFER_CAP
    return dict(protocol=PROTO,phase="transfer",cohort="DMD4_disjoint_EQUIV7_original",
       sha256=case["sha256"],filename=case["filename"],arm=arm,rep=rep,
       status=status,SAT_original_witness_verified=verified,
       UNSAT_independent_LRAT=False,
       PAR2_s=round(elapsed if status!="TIMEOUT" else 2*TRANSFER_CAP,6),
       e2e_s=round(elapsed,6),cap_s=TRANSFER_CAP,
       full_CPU_s=round(used_cpu(resource.RUSAGE_CHILDREN)-before,6),
       one_logical_cpu=True,
       source_derived_lemmas=proof_count,
       gate_selected_count=gated_count,appended_lemmas=len(chosen),
       appended_shapes=dict(collections.Counter(shape(v) for v in chosen)),
       cdcl_stats=stats,
       train_shape_signature=digest(selection["winning_shape_classes"]),
       source_SHA_verified=True)

def transfer(shard):
    need(0<=shard<SHARDS,"bad transfer shard")
    p=ROOT/"selection.json"
    need(p.is_file(),"selection not frozen")
    learned=json.loads(p.read_text())
    selection={**learned,"transfer_sha":check_frozen()["transfer_SHA256"]}
    need(selection["protocol"]==PROTO,"selector protocol drift")
    _,cases=read_cases()
    own=[c for i,c in enumerate(cases) if i%SHARDS==shard]
    need(len(own)==6,"transfer shard size drift")
    ROOT.mkdir(exist_ok=True)
    rows=[]
    for case in own:
        for rep in range(REPS):
            arms=list(TRANSFER_ARMS)
            random.Random(case["sha256"]+str(rep)).shuffle(arms)
            for arm in arms:
                x=trial_transfer(case,arm,rep,selection)
                rows.append(x)
                (ROOT/f"transfer-{shard}.json").write_text(json.dumps(rows,sort_keys=True))
                print("DMD5_TRANSFER_TRIAL",json.dumps(x,sort_keys=True),flush=True)
    need(len(rows)==60,"transfer shard incomplete")
    print("DMD5_TRANSFER_SHARD_PASS",shard,len(rows),flush=True)

def audit():
    train,holdout=read_cases()
    freeze=check_frozen()
    selection=json.loads((ROOT/"selection.json").read_text())
    ablation=sum([json.loads((ROOT/f"ablation-{i}.json").read_text())
                  for i in range(SHARDS)],[])
    transfer=sum([json.loads((ROOT/f"transfer-{i}.json").read_text())
                  for i in range(SHARDS)],[])
    need(len(ablation)==128 and len(transfer)==240,
         "total original source trials incomplete")
    unique={(x["sha256"],x["rep"],x["arm"]) for x in transfer}
    expected={(c["sha256"],rep,arm) for c in holdout
              for rep in range(REPS) for arm in TRANSFER_ARMS}
    need(unique==expected and len(unique)==240,
         "transfer 240 SHA/seed/arm mismatch")
    need({x["sha256"] for x in transfer}.isdisjoint({TRAIN_SHA}),
         "training source leaked into holdout")
    scored={}
    for arm in TRANSFER_ARMS:
        vals=[r for r in transfer if r["arm"]==arm]
        scored[arm]=dict(trials=len(vals),
            solved=sum(r["status"]!="TIMEOUT" for r in vals),
            SAT_verified=sum(r["status"]=="SAT" for r in vals),
            UNSAT_backend_no_independent_LRAT=sum(r["status"]=="UNSAT" for r in vals),
            PAR2_s=round(sum(r["PAR2_s"] for r in vals),6),
            CPU_s=round(sum(r["full_CPU_s"] for r in vals),6),
            appended_lemmas=sum(r["appended_lemmas"] for r in vals),
            compared_conflicts_reported=sum(r["cdcl_stats"].get("conflicts",0) for r in vals),
            compared_decisions_reported=sum(r["cdcl_stats"].get("decisions",0) for r in vals))
    ref=scored["cadical_clean"]["PAR2_s"]
    for arm,v in scored.items():
        v["relative_PAR2_vs_clean"]=round(ref/v["PAR2_s"],5) if v["PAR2_s"] else None
    per_case={}
    for c in holdout:
        these=[r for r in transfer if r["sha256"]==c["sha256"]]
        per_case[c["sha256"]]=dict(filename=c["filename"],by_arm={
            arm:dict(solved=sum(r["status"]!="TIMEOUT" for r in these if r["arm"]==arm),
                PAR2_s=round(sum(r["PAR2_s"] for r in these if r["arm"]==arm),6),
                appended=sum(r["appended_lemmas"] for r in these if r["arm"]==arm))
            for arm in TRANSFER_ARMS})
    for r in transfer:
        need(r["protocol"]==PROTO and r["one_logical_cpu"] and r["cap_s"]==TRANSFER_CAP,
             "original source E2E protocol drift")
        need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"bad transfer verdict")
        need(r["status"]!="SAT" or r["SAT_original_witness_verified"],
             "SAT source model not verified")
        need(r["train_shape_signature"]==digest(selection["winning_shape_classes"]),
             "selector edited after freezing")
    report=dict(protocol=PROTO,TRAIN_source=TRAIN_SHA,
       train_ablation_original_128_trials=128,
       transfer_DMD4_disjoint_original_24_SHA=24,
       transfer_E2E_trials=240,total_E2E_trials=368,
       single_logical_CPU_per_solver=True,
       training_4s_cap=TRAIN_CAP,transfer_6s_cap=TRANSFER_CAP,
       training_not_blind=True,holdout_not_globally_unseen=True,
       source_local_lemma_proofs_replayed=True,
       SAT_original_model_independently_replayed=True,
       UNSAT_independent_LRAT=False,
       no_auto_promotion=True,
       remarks="Clause-only CaDiCaL removes IPASIR observer overhead; winning lemma patterns from ONE training source could overfit, and DMD4-disjoint EQUIV7 original formulas were historically used by EQUIV7",
       selector={k:v for k,v in selection.items() if k not in (
           "all_mask_results","candidate_lemma_source_provenance")},
       transfer_scores=scored,by_source=per_case,
       ablation_rows=ablation,transfer_rows=transfer)
    ROOT.mkdir(exist_ok=True)
    (ROOT/"report.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("DMD5_FINAL",json.dumps({k:v for k,v in report.items()
          if k not in ("ablation_rows","transfer_rows","by_source")},
          sort_keys=True),flush=True)

def selftest():
    need(all(p.is_file() for p in (DMD1,GATE,LIVE,KISSAT)),"native executable missing")
    f=frozen()
    one=trial_ablate(0,0)
    full=trial_ablate(63,0)
    need(one["status"]=="SAT" and one["sat_original_verified"] and
         full["status"]=="SAT" and full["sat_original_verified"],
         "train control vs all failed")
    print("DMD5_SELFTEST_PASS",json.dumps(
        dict(n_local_proved=len(f["DMD1_original_lemmas"]),
          n_gated=len(f["gated_lemmas"]),
          clean_E2E=one["e2e_s"],all_E2E=full["e2e_s"],
          both_SAT_original=True),sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","ablate","select","transfer","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    {"selftest":selftest,"ablate":lambda:ablate(a.shard),
     "select":select,"transfer":lambda:transfer(a.shard),"audit":audit}[a.action]()
