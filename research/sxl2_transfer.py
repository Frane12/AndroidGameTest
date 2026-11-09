#!/usr/bin/env python3
"""SXL2 transfer, deliberately disjoint from DMD8 work:
source-proved native ANF CNF additions with NO tree, tested on SHA-frozen
EQUIV2 originals after reference-only selection. No globally blind claim.
All costs E2E, 1 logical CPU; SAT model checked on original; UNSAT backend only.
"""
import argparse
import collections
import hashlib
import json
import os
import pathlib
import random
import resource
import tempfile
import time

import dmd1_bench as d1

P="DRNAS-SXL2-ANF-DOSE-EQUIV2-REFONLY-ONECPU-v1"
ROOT=pathlib.Path("mre_sxl2")
REGISTRY=pathlib.Path("mre_x20")
GEN=ROOT/"bin/dmd3x_native"
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
CADICAL=pathlib.Path("mre_equiv2/bin/cadical_3_0_1")
BASE_SHA="c96ebe32a7e333a02acad462679a0bbfbeeec54a7f9210421c4c0c8d53bbf95f"
ARMS=("kissat_original","cadical_original","sxl2_all","sxl2_short1","sxl2_short4","sxl2_shadow")
SHARDS=4
REPS=2
CAP=12.0
SCREEN_CAP=8.0

def check(v,reason):
    if not v:raise RuntimeError("SXL2_FAIL_CLOSED "+str(reason))

def pin():
    cpus=os.sched_getaffinity(0)
    check(bool(cpus),"no cpu")
    cpu=min(cpus)
    os.sched_setaffinity(0,{cpu})
    return cpu

def cpu():
    a,b=resource.getrusage(resource.RUSAGE_SELF),resource.getrusage(resource.RUSAGE_CHILDREN)
    return a.ru_utime+a.ru_stime+b.ru_utime+b.ru_stime

def manifest():
    x=json.loads((REGISTRY/"manifest.json").read_text())
    check(len(x["cases"])==24,"EQUIV2 24-source registry drift")
    return x

def registry():
    cases=[]
    for c in manifest()["cases"]:
        file=REGISTRY/c["filename"]
        check(file.is_file() and d1.sha(file)==c["sha256"],"original SHA mismatch")
        cases.append(dict(sha256=c["sha256"],filename=c["filename"],
                          path=str(file),gbd=c.get("gbd")))
    check(len({x["sha256"] for x in cases})==24,"duplicate EQUIV2 source")
    return sorted(cases,key=lambda x:x["sha256"])

def baseline_exclusion():
    old=json.loads(pathlib.Path("sxl1_freeze.json").read_text())
    check(old["protocol"]=="DRNAS-SXL-ANF-BINARY-TREE-ONECPU-E2E-v1",
          "SXL baseline freeze mismatch")
    check(len(old["cases"])==8,"SXL previous 8-source freeze differs")
    return {x["sha256"] for x in old["cases"]}

def screen():
    pin();ROOT.mkdir(parents=True,exist_ok=True)
    check(d1.sha(KISSAT)==BASE_SHA,"pinned Kissat drift")
    excluded=baseline_exclusion()
    pool=[x for x in registry() if x["sha256"] not in excluded]
    records=[]
    for c in pool:
        _,clauses=d1.read_cnf(c["path"])
        rc,out,err,wall,childcpu,timed=d1.run_process(
            [KISSAT,"--seed=1000",c["path"]],SCREEN_CAP,pin())
        status,witness=("TIMEOUT",False) if timed else d1.outcome(rc,out,clauses)
        row=dict(**c,reference_status=status,reference_s=round(wall,6),
                 reference_cpu_s=round(childcpu,6),
                 SAT_original_verified=witness,eligible=not timed)
        records.append(row)
        print("SXL2_REFERENCE_SCREEN "+json.dumps(row,sort_keys=True),flush=True)
    selected=[x for x in records if x["eligible"]][:8]
    check(len(selected)>=4,"not enough reference-completed disjoint cases")
    freeze=dict(protocol=P,origin="EQUIV2 original CNF 24 SHA",reused_in_wider_project=True,
                globally_unseen=False,selection="reference_only_8s_then_sha_first8",
                excluded_SXL1_shas=sorted(excluded),cases=selected,screen=records,
                kissat_sha256=BASE_SHA,arms=ARMS,reps=REPS,cap_s=CAP,
                expected=len(selected)*len(ARMS)*REPS)
    (ROOT/"freeze.json").write_text(json.dumps(freeze,indent=2,sort_keys=True)+"\n")
    print("SXL2_FREEZE_PASS "+json.dumps(dict(selected=len(selected),screened=len(records),
          excluded_overlap=len(excluded),expected=freeze["expected"],cap_s=CAP),sort_keys=True),flush=True)

def frozen():
    f=json.loads((ROOT/"freeze.json").read_text())
    check(f["protocol"]==P and f["kissat_sha256"]==d1.sha(KISSAT),"freeze drift")
    cases={x["sha256"]:x for x in registry()}
    excluded=baseline_exclusion()
    check(4<=len(f["cases"])<=8,"unexpected selected size")
    for x in f["cases"]:
        check(x["sha256"] not in excluded and x["sha256"] in cases and
              x["path"]==cases[x["sha256"]]["path"] and x["eligible"],
              "source or exclusion changed")
    return f

def write_subset(target,n,original,lemmas):
    # Mutate temporary copy only; original always preserved byte-for-byte.
    target.write_text("p cnf %d %d\n"%(n,len(original)+len(lemmas))+
       "".join(" ".join(map(str,c))+" 0\n" for c in original+lemmas))

def extraction(source,tmp,remaining):
    output,proofpath=tmp/"all.cnf",tmp/"proof.json"
    rc,out,err,wall,child,timed=d1.run_process(
        [GEN,source,output,proofpath,20,64,"all"],min(remaining,2.0),pin())
    if timed:return None
    check(rc==0 and proofpath.is_file(),"extractor failed: "+err[-300:])
    proof=json.loads(proofpath.read_text())
    check(proof["dmd3x_protocol"]=="DMD3X-NATIVE-STRUCTURE-ROOT-BCP-v1" and
          proof["gate_mode"]=="all","generator protocol changed")
    n,original=d1.proof_replay(pathlib.Path(source),output,proof)
    return n,original,proof,output

def rank(lemmas,original):
    degree=collections.Counter(abs(l) for c in original for l in c)
    return sorted(range(len(lemmas)),key=lambda i:(
        len(lemmas[i]["clause"]),
        -sum(degree[abs(l)] for l in lemmas[i]["clause"]),i))

def trial(case,arm,rep):
    core=pin()
    start=time.monotonic();cpu0=cpu()
    source=pathlib.Path(case["path"])
    check(d1.sha(source)==case["sha256"],"input SHA changed")
    n,clauses=d1.read_cnf(source)
    status="TIMEOUT";witness=False;extracted=0;injected=0;proof_replayed=False
    selector="none";target=source;abstain=False
    with tempfile.TemporaryDirectory(prefix="sxl2-") as t:
        tmp=pathlib.Path(t)
        if arm not in ("kissat_original","cadical_original"):
            result=extraction(source,tmp,max(.001,CAP-(time.monotonic()-start)))
            if result is None:abstain=True
            else:
                nn,orig,proof,aug=result
                check(nn==n and orig==clauses,"extraction changed original CNF")
                extracted=len(proof["lemmas"]);proof_replayed=True
                if extracted and arm=="sxl2_all":
                    target=aug;injected=extracted;selector="all_source_proven"
                elif extracted and arm in ("sxl2_short1","sxl2_short4"):
                    dose=1 if arm=="sxl2_short1" else 4
                    ids=rank(proof["lemmas"],clauses)[:dose]
                    selected=[proof["lemmas"][i] for i in ids]
                    appended=[tuple(l["clause"]) for l in selected]
                    candidate=tmp/"selected.cnf"
                    write_subset(candidate,n,clauses,appended)
                    sub=dict(proof,lemmas=selected)
                    d1.proof_replay(source,candidate,sub)
                    target=candidate;injected=len(selected);selector="source_short_degree"
                elif arm=="sxl2_shadow":selector="source_proof_placebo"
        prep=time.monotonic()-start
        remaining=CAP-prep
        if not abstain and remaining>.01:
            binary=CADICAL if arm=="cadical_original" else KISSAT
            rc,out,err,wall,child,timed=d1.run_process(
                 [binary,"--seed=%d"%(1001+rep),target]
                 if arm!="cadical_original" else [binary,target],
                 remaining,core)
            if not timed:status,witness=d1.outcome(rc,out,clauses)
    elapsed=time.monotonic()-start
    if status=="TIMEOUT":elapsed=min(elapsed,CAP)
    check(status!="SAT" or witness,"invalid original SAT model")
    check(elapsed<=CAP+.10,"E2E budget exceeded")
    return dict(protocol=P,original_sha256=case["sha256"],arm=arm,rep=rep,
       cap_s=CAP,cpu_affinity=[core],original_SHA_verified=d1.sha(source)==case["sha256"],
       status=status,SAT_original_witness_verified=witness,UNSAT_independent_LRAT=False,
       E2E_s=round(elapsed,6),PAR2_s=round(elapsed if status!="TIMEOUT" else 2*CAP,6),
       full_CPU_s=round(cpu()-cpu0,6),prep_s=round(prep,6),
       extracted=extracted,injected=injected,selector=selector,
       source_local_proofs_replayed=proof_replayed,abstained=abstain,
       binary_sha256=d1.sha(KISSAT),native_sha256=d1.sha(GEN),shard=-1)

def bench(shard):
    check(0<=shard<SHARDS,"bad shard")
    frozen_sources=frozen()["cases"]
    rows=[]
    ROOT.mkdir(parents=True,exist_ok=True)
    for i,c in enumerate(frozen_sources):
        if i%SHARDS!=shard:continue
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(c["sha256"]+str(rep)).shuffle(arms)
            for arm in arms:
                row=trial(c,arm,rep)
                row["shard"]=shard
                rows.append(row)
                (ROOT/("shard-%d.json"%shard)).write_text(json.dumps(rows,sort_keys=True)+"\n")
                print("SXL2_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    print("SXL2_SHARD_PASS",shard,len(rows),flush=True)

def score(rows):
    return dict(attempts=len(rows),solved=sum(x["status"]!="TIMEOUT" for x in rows),
       SAT_verified=sum(x["SAT_original_witness_verified"] for x in rows),
       UNSAT_backend_no_LRAT=sum(x["status"]=="UNSAT" for x in rows),
       PAR2_s=round(sum(x["PAR2_s"] for x in rows),6),
       full_CPU_s=round(sum(x["full_CPU_s"] for x in rows),6),
       prep_s=round(sum(x["prep_s"] for x in rows),6),
       injected=sum(x["injected"] for x in rows),
       abstained=sum(x["abstained"] for x in rows))

def audit():
    freeze=frozen();rows=[]
    per_shard={}
    for i in range(SHARDS):
        f=ROOT/("shard-%d.json"%i)
        check(f.is_file(),"missing "+str(f))
        zs=json.loads(f.read_text());rows.extend(zs)
        per_shard[str(i)]={a:score([r for r in zs if r["arm"]==a]) for a in ARMS}
    expected={(x["sha256"],a,j) for x in freeze["cases"] for a in ARMS for j in range(REPS)}
    got={(x["original_sha256"],x["arm"],x["rep"]) for x in rows}
    check(len(rows)==len(got)==len(expected) and got==expected,"paired SHA matrix drift")
    check(all(r["protocol"]==P and r["original_SHA_verified"] and
              r["binary_sha256"]==BASE_SHA and len(r["cpu_affinity"])==1 and
              0<=r["E2E_s"]<=CAP+.10 and
              (r["status"]!="SAT" or r["SAT_original_witness_verified"]) and
              (r["injected"]==0 or r["source_local_proofs_replayed"])
              for r in rows),"integrity proof CPU SHA status failure")
    check(len({r["native_sha256"] for r in rows})==1,"binary drift")
    for sha in {r["original_sha256"] for r in rows}:
        statuses={r["status"] for r in rows if r["original_sha256"]==sha and r["status"]!="TIMEOUT"}
        check(len(statuses)<=1,"SAT/UNSAT disagreement")
    scores={arm:score([r for r in rows if r["arm"]==arm]) for arm in ARMS}
    k=scores["kissat_original"]["PAR2_s"]
    for a in scores:scores[a]["speedup_x_vs_kissat"]=round(k/scores[a]["PAR2_s"],6)
    report=dict(protocol=P,total_trials=len(rows),sources=len(freeze["cases"]),
       source_disjoint_from_SXL1_frozen8=True,not_globally_unseen=True,
       reference_only_picked=True,one_cpu=True,SAT_original_verified=True,
       UNSAT_independent_LRAT=False,no_auto_promotion=True,
       scores=scores,per_shard=per_shard)
    (ROOT/"audit.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n")
    print("SXL2_FINAL "+json.dumps(report,sort_keys=True),flush=True)

def selftest():
    pin()
    check(d1.sha(KISSAT)==BASE_SHA,"Kissat pin changed")
    with tempfile.TemporaryDirectory() as d:
        t=pathlib.Path(d);original=[(1,2,3),(1,2,-3)]
        source=t/"sample.cnf"
        write_subset(source,3,original,[])
        result=extraction(source,t,2.0)
        check(result is not None,"synthetic native extractor failure")
        _,base,proof,aug=result
        selected=proof["lemmas"][:1]
        if selected:
            target=t/"selected.cnf"
            write_subset(target,3,original,[tuple(selected[0]["clause"])])
            d1.proof_replay(source,target,dict(proof,lemmas=selected))
        check(len(original)==len(base),"changed original")
    print("SXL2_SELFTEST_PASS native_source_local_proof_replay",flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("mode",choices=("selftest","screen","bench","audit"))
    parser.add_argument("--shard",type=int,default=0)
    args=parser.parse_args()
    if args.mode=="bench":bench(args.shard)
    else:globals()[args.mode]()
