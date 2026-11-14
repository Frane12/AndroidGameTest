#!/usr/bin/env python3
"""QUOTA7 REAL36: frozen original SAT2024, OFF vs FULL vs QUOTA_ONLY.

All 36 original source SHA-pinned CNFs from historical REAL36, two paired
repetitions, 8-second CPU budget per solver, 4 disjoint source shards.
Native X5 baseline and two continuous retention modes from frozen RET6
builder. This is retrospective validation, not independent blind holdout.
Each solved SAT assignment checked on original CNF; each UNSAT proof checked
using frozen drat-trim. No false claims for UNKNOWN or timeouts.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,random,statistics,sys
from pathlib import Path
import drnas_retain6_real14 as RET
import drnas_x55_cpu_real36 as REAL

OUT=Path("quota7_real36")
OUT.mkdir(exist_ok=True)
ARMS=("OFF","FULL","QUOTA_ONLY")
REPS=2
SHARDS=4
CAP=8.0
RET.CAP=CAP

def emit(t,x):print(t+" "+json.dumps(x,sort_keys=True),flush=True)
def digest(b):return hashlib.sha256(b).hexdigest()
def save(p,x):Path(p).write_text(json.dumps(x,sort_keys=True,indent=2)+"\n")

def source_protocol():
    sources,old=REAL.official_manifest()
    assert len(sources)==36 and len({s["sha256"] for s in sources})==36
    ids=[int(s["id"]) for s in sources]
    assert len(set(ids))==36
    for s in sources:
        data=Path(s["path"]).read_bytes()
        assert digest(data)==s["sha256"],("ORIGINAL_SHA_MISMATCH",s["id"])
    protocol={
        "status":"FROZEN_BEFORE_SOLVER",
        "source":"original SAT Competition 2024 REAL36",
        "historical_REAL36_run":43387395060,
        "historical_manifest_sha256":old["manifest_sha256"],
        "source_count":len(sources),
        "source_ids":ids,
        "source_sha256":[s["sha256"] for s in sources],
        "families":dict(collections.Counter(s["family"] for s in sources)),
        "arms":list(ARMS),"repetitions":REPS,"cap_s":CAP,
        "shards":SHARDS,
        "single_logical_CPU_per_solver":True,
        "same_native_solver_no_portfolio":True,
        "independent_original_CNF_model_and_DRAT_checks":True,
        "source_set_retrospective_not_blind":True,
        "no_fitted_parameters":True,
        "main_not_modified":True,"no_promotion":True,
        "metrics":["PAR2_verified","cpu","wall","maxrss","conflicts",
                   "learned","deleted","verified_count","first_reduce_state"],
    }
    return sources,protocol

def run_shard(k):
    assert 0<=k<SHARDS
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    assert len(os.sched_getaffinity(0))==1
    sources,protocol=source_protocol()
    folder=OUT/str(k)
    folder.mkdir(exist_ok=True,parents=True)
    save(folder/"protocol.json",protocol)
    selected=[s for i,s in enumerate(sources) if i%SHARDS==k]
    assert len(selected)==9
    emit("QUOTA7_FROZEN",{"shard":k,"source_ids":[s["id"] for s in selected],
        "protocol_sha256":digest((folder/"protocol.json").read_bytes()),
        "repetitions":REPS,"cap_s":CAP})
    random.Random(141211+k).shuffle(selected)
    pairs=[]
    for s in selected:
        for rep in range(REPS):
            order=list(ARMS)
            random.Random(int(s["sha256"][:12],16)+rep*91).shuffle(order)
            result={}
            for arm in order:result[arm]=RET.trial(s,arm)
            statuses={x["status"] for x in result.values() if x["verified"]}
            assert len(statuses)<=1,("CONTRADICTORY_CERTIFIED_RESULTS",s["id"],rep)
            signature=("first_reduce_conflicts","first_reduce_decisions",
                       "first_reduce_hash")
            first=[tuple(result[a]["retention"][key] for key in signature)
                   for a in ARMS]
            assert len(set(first))==1,("NOT_SAME_PRE_REDUCTION_STATE",s["id"],rep,first)
            row={"id":s["id"],"family":s["family"],"sha256":s["sha256"],
                 "rep":rep,"arms":result}
            pairs.append(row)
            emit("QUOTA7_PAIR",{
                "shard":k,"id":s["id"],"rep":rep,"family":s["family"],
                "status":{a:result[a]["status"] for a in ARMS},
                "verified":{a:result[a]["verified"] for a in ARMS},
                "PAR2_s":{a:round(result[a]["PAR2_s"],5) for a in ARMS},
                "cpu_s":{a:result[a]["cpu_s"] for a in ARMS},
                "conflicts":{a:result[a]["conflicts"] for a in ARMS},
                "maxrss_kib":{a:result[a]["maxrss_kib"] for a in ARMS}})
    (folder/"pairs.jsonl").write_text(
        "".join(json.dumps(p,sort_keys=True)+"\n" for p in pairs))
    emit("QUOTA7_SHARD_COMPLETE",{"shard":k,"sources":len(selected),
         "pairs":len(pairs),"one_cpu":True})

def finalize():
    sources,protocol=source_protocol()
    pairs=[]
    for k in range(SHARDS):
        folder=OUT/str(k)
        assert json.loads((folder/"protocol.json").read_text())==protocol
        for line in (folder/"pairs.jsonl").read_text().splitlines():
            pairs.append(json.loads(line))
    assert len(pairs)==36*REPS
    assert len({(p["id"],p["rep"]) for p in pairs})==36*REPS
    expected={(s["id"],r) for s in sources for r in range(REPS)}
    assert {(p["id"],p["rep"]) for p in pairs}==expected
    arms={}
    for a in ARMS:
        results=[p["arms"][a] for p in pairs]
        arms[a]={
            "attempts":len(results),
            "verified":sum(r["verified"] for r in results),
            "unique_solved":len({p["id"] for p in pairs if p["arms"][a]["verified"]}),
            "PAR2_verified_s":round(sum(r["PAR2_s"] for r in results),5),
            "CPU_s":round(sum(r["cpu_s"] or 0 for r in results),5),
            "maxrss_kib":max((r["maxrss_kib"] or 0 for r in results),default=0),
            "total_deleted":sum(r["retention"]["total_deleted"] for r in results),
            "effective_reductions":sum(r["retention"]["effective_reductions"] for r in results)
        }
    paired={}
    for a in ("FULL","QUOTA_ONLY"):
        outcomes={"win":0,"loss":0,"tie":0,"both_timeout":0}
        for p in pairs:
            x=p["arms"][a];y=p["arms"]["OFF"]
            if not x["verified"] and not y["verified"]:
                outcomes["both_timeout"]+=1;continue
            if x["PAR2_s"]+0.01<y["PAR2_s"]:outcomes["win"]+=1
            elif y["PAR2_s"]+0.01<x["PAR2_s"]:outcomes["loss"]+=1
            else:outcomes["tie"]+=1
        paired[a+"_vs_OFF"]=outcomes
    report={
        "status":"COMPLETE","original_sources":36,"paired_source_repetitions":72,
        "solver_executions":216,"cap_s":CAP,
        "one_logical_cpu_per_solver":True,"original_CNF_verification":True,
        "pre_first_reduction_state_identical":True,
        "not_blind":True,"not_promoted":True,"main_untouched":True,
        "no_claim_of_general_speedup":True,
        "arms":arms,"paired":paired,
        "protocol_sha256":digest(json.dumps(protocol,sort_keys=True).encode())
    }
    save(OUT/"final_report.json",report)
    emit("QUOTA7_FINAL",report)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("stage",choices=("shard","final"))
    ap.add_argument("--shard",type=int,default=0)
    args=ap.parse_args()
    run_shard(args.shard) if args.stage=="shard" else finalize()
