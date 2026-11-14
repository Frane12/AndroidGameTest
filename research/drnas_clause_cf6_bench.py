#!/usr/bin/env python3
"""CF6: proof-checked first-reduction matched-clause A/B with full source ledger.

All outcomes on original SAT Competition 2024 CNFs; previously used REAL36,
NOT a blind holdout. Never mix 4 s aggregate with 8 s focused replay.
One solver/process/logical CPU at a time. No policy fit or promotion.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import random
import resource
import signal
import statistics
import subprocess
import sys
import tempfile
import time

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "research"))
import drnas_x55_cpu_real36 as REAL

ARMS = ("BASE", "LBD", "B2L_1", "B2L_8", "B2L_32",
        "L2B_1", "L2B_8", "L2B_32")
IDS = (0, 3, 5, 6, 9, 12, 15, 16, 19, 20, 23, 24, 28, 31)
CAP_REAL = 4.0
CAP_REPLAY = 8.0
REPLAY_ID = 16
REPLAY_REPS = 3
SHARDS = 4
ROOT = Path("cf6")
SOLVER = R / "build/drnas-clause-cf6"
CHECKER = R / "build/drat-trim"

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def write(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")

def emit(marker, obj):
    print(marker + " " + json.dumps(obj, sort_keys=True), flush=True)

def sources():
    originals, frozen = REAL.official_manifest()
    assert len(originals) == 36 and len({s["sha256"] for s in originals}) == 36
    by_id = {s["id"]:s for s in originals}
    picked = [by_id[i] for i in IDS]
    assert len(picked) == 14 and len({s["sha256"] for s in picked}) == 14
    for s in picked:
        raw = Path(s["path"]).read_bytes()
        assert sha(raw) == s["sha256"], ("CF6_SOURCE_DRIFT",s["id"])
    return picked, frozen

def bind_one_cpu():
    allowed = os.sched_getaffinity(0)
    os.sched_setaffinity(0, {min(allowed)})
    assert len(os.sched_getaffinity(0)) == 1

def freeze():
    picked, original = sources()
    assert SOLVER.is_file() and CHECKER.is_file()
    protocol = {
        "protocol":"DRNAS-CF6-FIRST-REDUCTION-EQUAL-BUDGET-V1",
        "original_archive_run":43387395060,
        "dataset":"retrospective SAT Competition 2024 REAL36 original CNFs",
        "real36_manifest_sha256":original["manifest_sha256"],
        "source_count":14,
        "source_ids":list(IDS),
        "source_sha256":[x["sha256"] for x in picked],
        "families":dict(collections.Counter(x["family"] for x in picked)),
        "arms":list(ARMS),
        "cutoff":"first effective reduction: same eligible candidates and deleted count",
        "pair_order":"unlocked candidate CID ascending in frozen same-state heap",
        "swap_levels":[1,8,32],
        "real_repetitions":1,"real_cap_s":CAP_REAL,
        "replay_source":REPLAY_ID,"replay_repetitions":REPLAY_REPS,
        "replay_cap_s":CAP_REPLAY,
        "independent_SAT":"original full-CNF model verification",
        "independent_UNSAT":"original-CNF drat-trim",
        "solver_binary_sha256":sha(SOLVER.read_bytes()),
        "proof_checker_sha256":sha(CHECKER.read_bytes()),
        "one_logical_cpu":True,
        "train_validation_holdout":"none; retrospective diagnostic only",
        "blind_holdout":False,"promote":False,
        "no_main_or_frozen_reference_change":True,
    }
    write(ROOT / "frozen/protocol.json", protocol)
    emit("CF6_FROZEN", {"sources":14,"families":protocol["families"],
                        "solver_sha256":protocol["solver_binary_sha256"]})

def check_protocol():
    s, orig = sources()
    p = json.loads((ROOT/"frozen/protocol.json").read_text())
    assert p["real36_manifest_sha256"] == orig["manifest_sha256"]
    assert p["source_sha256"] == [x["sha256"] for x in s]
    assert p["solver_binary_sha256"] == sha(SOLVER.read_bytes())
    assert p["proof_checker_sha256"] == sha(CHECKER.read_bytes())
    assert not p["blind_holdout"] and not p["promote"]
    return s

def one(source, mode, cap, rep=0, snapshot=None):
    raw=Path(source["path"]).read_bytes()
    assert sha(raw)==source["sha256"]
    n,clauses=REAL.parse_cnf(raw)
    assert n==source["nvars"] and len(clauses)==source["nclauses"]
    with tempfile.TemporaryDirectory() as tmp:
        proof=Path(tmp)/"proof.drat"
        cmd=[str(SOLVER.resolve()),str(Path(source["path"]).resolve()),
             "--mode","core","--time",str(cap),"--stats",
             "--x5-no-minimize","--x5-no-retain","--proof",str(proof),
             "--cf5-policy",mode]
        if snapshot is not None:
            sp=Path(snapshot)
            sp.parent.mkdir(parents=True,exist_ok=True)
            sp.unlink(missing_ok=True)
            cmd.extend(["--cf6-snapshot",str(sp.resolve())])
        before=resource.getrusage(resource.RUSAGE_CHILDREN)
        t0=time.perf_counter()
        p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           text=True,start_new_session=True)
        killed=False
        try:
            stdout,stderr=p.communicate(timeout=cap+0.8)
        except subprocess.TimeoutExpired:
            killed=True
            try:os.killpg(p.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            stdout,stderr=p.communicate()
        wall=time.perf_counter()-t0
        after=resource.getrusage(resource.RUSAGE_CHILDREN)
        cpu=max(0.0, after.ru_utime+after.ru_stime-
                before.ru_utime-before.ru_stime)
        if not killed and p.returncode not in (0,10,20):
            raise RuntimeError(("CF6_PROCESS_FAILURE",source["id"],mode,
                               p.returncode,stderr[-1100:]))
        status="TIMEOUT" if killed else {0:"UNKNOWN",10:"SAT",20:"UNSAT"}[p.returncode]
        model_verified=False
        proof_verified=False
        if status=="SAT":
            model_verified=REAL.check_sat(stdout,clauses,n)
            if not model_verified:
                raise RuntimeError(("CF6_WRONG_SAT",source["id"],mode))
        if status=="UNSAT":
            if not proof.is_file() or proof.stat().st_size == 0:
                raise RuntimeError(("CF6_UNSAT_MISSING_PROOF",source["id"],mode))
            check=subprocess.run([str(CHECKER.resolve()),
                                  str(Path(source["path"]).resolve()),str(proof)],
                                 capture_output=True,text=True,timeout=65)
            proof_verified=check.returncode==0 and "s VERIFIED" in check.stdout
            if not proof_verified:
                raise RuntimeError(("CF6_INVALID_UNSAT_PROOF",source["id"],mode,
                                    check.stdout[-600:],check.stderr[-600:]))
        verified=model_verified or proof_verified
        telemetry={}
        if not killed:
            for line in stderr.splitlines():
                tag,sep,data=line.partition(" ")
                if tag in ("X41_STATS","CLCF5_STATS","CLCF6_STATS"):
                    if tag in telemetry:
                        raise RuntimeError(("CF6_DUPLICATE_STATS",tag))
                    telemetry[tag]=json.loads(data)
            if not all(k in telemetry for k in
                       ("X41_STATS","CLCF5_STATS","CLCF6_STATS")):
                raise RuntimeError(("CF6_MISSING_STATS",source["id"],mode,
                                    list(telemetry),stderr[-1200:]))
            x=telemetry["CLCF6_STATS"]
            q=telemetry["CLCF5_STATS"]
            if x["policy"]!=mode or q["policy"]!=mode:
                raise RuntimeError(("CF6_POLICY_MISMATCH",source["id"],mode))
            if x["same_delete_count"]!=q["deleted"]:
                raise RuntimeError(("CF6_DELETE_MISMATCH",source["id"],mode))
            if x["candidate_count"]!=q["candidates"]:
                raise RuntimeError(("CF6_CANDIDATE_MISMATCH",source["id"],mode))
            if q["first_effective_reduce"]:
                if q["candidates"]<128 or q["deleted"]!=q["candidates"]//2:
                    raise RuntimeError(("CF6_WRONG_DELETE_QUOTA",source["id"],mode))
            else:
                if x["candidate_count"] or x["actual_swaps"]:
                    raise RuntimeError(("CF6_FALSE_FIRST_REDUCTION",source["id"],mode))
            if mode.startswith(("B2L_","L2B_")) and q["first_effective_reduce"]:
                asked=int(mode.split("_")[1])
                assert x["requested_swaps"]==asked
                assert x["actual_swaps"]==min(asked,x["mismatch_pairs"])
                assert x["swapped_in_kept"]==x["swapped_out_deleted"]==x["actual_swaps"]
        status_label=("SAT_VERIFIED" if status=="SAT" else
                      "UNSAT_CERTIFIED" if status=="UNSAT" else status)
        accepted=verified and wall<=cap
        return {
            "id":source["id"],"family":source["family"],
            "source_sha256":source["sha256"],"arm":mode,"rep":rep,"cap_s":cap,
            "status":status_label,"verified":verified,"accepted":accepted,
            "par2_s":wall if accepted else 2*cap,
            "wall_e2e_s":wall,"cpu_s":cpu,
            "conflicts":telemetry.get("X41_STATS",{}).get("conflicts"),
            "decisions":telemetry.get("X41_STATS",{}).get("decisions"),
            "first_reduction":telemetry.get("CLCF5_STATS",{}),
            "cf6":telemetry.get("CLCF6_STATS",{}),
            "snapshot_file":str(snapshot) if snapshot and Path(snapshot).is_file() else None,
        }

def ensure_matched(rows, stage):
    by=collections.defaultdict(dict)
    for r in rows:
        key=(r["source_sha256"],r["rep"],r["cap_s"])
        if r["arm"] in by[key]:
            raise RuntimeError(("CF6_DUPLICATE_ARM",stage,key,r["arm"]))
        by[key][r["arm"]]=r
    for key, arms in by.items():
        if set(arms)!=set(ARMS):
            raise RuntimeError(("CF6_MISSING_ARMS",stage,key,set(ARMS)-set(arms)))
        baseline=arms["BASE"]
        sig=("first_effective_reduce","first_reduce_conflicts",
             "first_reduce_decisions","candidates","deleted",
             "first_candidate_digest")
        for arm,row in arms.items():
            if not row["first_reduction"] or not row["cf6"]:
                raise RuntimeError(("CF6_INCOMPLETE_TELEMETRY",stage,key,arm))
            if any(row["first_reduction"][k]!=baseline["first_reduction"][k]
                   for k in sig):
                raise RuntimeError(("CF6_PRESTATE_NOT_MATCHED",stage,key,arm))
            for k in ("mismatch_pairs","pair_digest"):
                if row["cf6"][k]!=baseline["cf6"][k]:
                    raise RuntimeError(("CF6_CANDIDATE_PAIRS_NOT_MATCHED",key,arm,k))
        certified={r["status"] for r in arms.values() if r["verified"]}
        if len(certified)>1:
            raise RuntimeError(("CF6_CONTRADICTORY_PROOF",stage,key,certified))
    return len(by)

def protocol_preflight():
    bind_one_cpu()
    selection=check_protocol()
    source=next(s for s in selection if s["id"]==REPLAY_ID)
    cases=[]
    for arm in ARMS:
        case=one(source,arm,cap=0.7)
        cases.append(case)
    matched=ensure_matched(cases,"preflight")
    assert matched==1
    base=next(x for x in cases if x["arm"]=="BASE")
    assert base["first_reduction"]["first_effective_reduce"], "CF6 first reduction not exercised"
    assert base["cf6"]["mismatch_pairs"]>32,"CF6 not enough mismatched candidate pairs"
    snap=ROOT/"preflight/candidate_ledger_id16.jsonl"
    trace=one(source,"BASE",cap=0.7,snapshot=snap)
    data=read_ledger(snap,trace)
    emit("CF6_PREFLIGHT_PASS",{
        "matched_policies":len(ARMS),"first_state_digest":base["cf6"]["first_candidate_digest"],
        "candidate_count":len(data),"mismatch_pairs":base["cf6"]["mismatch_pairs"],
        "one_cpu":True,"no_blind_holdout":True
    })

def read_ledger(path,trace):
    path=Path(path)
    if not path.is_file():
        if trace["cf6"] and trace["cf6"]["first_effective_reduce"]:
            raise RuntimeError(("CF6_MISSING_LEDGER",str(path)))
        return []
    items=[json.loads(line) for line in path.read_text().splitlines() if line]
    if len(items)!=trace["cf6"]["candidate_count"]:
        raise RuntimeError(("CF6_LEDGER_SIZE",len(items),trace["cf6"]["candidate_count"]))
    if len({r["cid"] for r in items})!=len(items):
        raise RuntimeError(("CF6_DUPLICATE_CLAUSE_IDS",str(path)))
    if sum(r["base_deleted"] for r in items)!=trace["cf6"]["same_delete_count"]:
        raise RuntimeError(("CF6_BASE_LEDGER_COUNT",str(path)))
    if sum(r["lbd_deleted"] for r in items)!=trace["cf6"]["same_delete_count"]:
        raise RuntimeError(("CF6_LBD_LEDGER_COUNT",str(path)))
    mismatch=sum(r["lbd_deleted"] and not r["base_deleted"] for r in items)
    if mismatch !=trace["cf6"]["mismatch_pairs"]:
        raise RuntimeError(("CF6_PAIR_COUNT",mismatch,trace["cf6"]["mismatch_pairs"]))
    return items

def run_rows(src,cap,reps,output,make_ledgers):
    bind_one_cpu()
    results=[]
    for case in src:
        for rep in range(reps):
            modes=list(ARMS)
            random.Random(600621+case["id"]*1009+rep*41+int(cap)*100).shuffle(modes)
            pair=[]
            for arm in modes:
                item=one(case,arm,cap,rep)
                pair.append(item)
                results.append(item)
                emit("CF6_TRIAL", {k:item[k] for k in
                     ("id","family","arm","rep","status","accepted","par2_s","wall_e2e_s")})
            ensure_matched(pair,"live")
        if make_ledgers:
            snap=output/"ledgers"/("candidate_id%d.jsonl"%case["id"])
            trace=one(case,"BASE",cap=cap,snapshot=snap)
            ledger=read_ledger(snap,trace)
            emit("CF6_LEDGER",{
                "id":case["id"],"candidates":len(ledger),
                "mismatches":trace["cf6"]["mismatch_pairs"]})
    output.mkdir(parents=True,exist_ok=True)
    with (output/"trials.jsonl").open("w") as f:
        for item in results:f.write(json.dumps(item,sort_keys=True)+"\n")
    return results

def shard(index):
    selected=check_protocol()
    if not 0<=index<SHARDS:raise RuntimeError("bad CF6 shard")
    cases=[x for x in selected if x["id"]%SHARDS==index]
    assert cases
    dest=ROOT/"real14"/("shard-%d"%index)
    results=run_rows(cases,CAP_REAL,1,dest,make_ledgers=True)
    assert ensure_matched(results,"real14") == len(cases)
    write(dest/"manifest.json",{
        "shard":index,"source_ids":[x["id"] for x in cases],
        "cases":len(cases),"attempts":len(results),
        "solver_sha":sha(SOLVER.read_bytes()),"cap_s":CAP_REAL})
    emit("CF6_SHARD_PASS", {"index":index,"sources":len(cases),
                           "trials":len(results),"original_real2024":True})

def replay():
    selected=check_protocol()
    source=next(s for s in selected if s["id"]==REPLAY_ID)
    dest=ROOT/"replay16"
    result=run_rows([source],CAP_REPLAY,REPLAY_REPS,dest,make_ledgers=True)
    assert ensure_matched(result,"replay16")==REPLAY_REPS
    write(dest/"manifest.json",{
        "source_id":REPLAY_ID,"source_sha":source["sha256"],
        "repetitions":REPLAY_REPS,"cap_s":CAP_REPLAY,
        "trials":len(result),"solver_sha":sha(SOLVER.read_bytes())})
    emit("CF6_REPLAY_PASS",{"source":REPLAY_ID,"trials":len(result),
                            "repetitions":REPLAY_REPS,"no_blind_claim":True})

def score(rows):
    scores={}
    for arm in ARMS:
        rs=[r for r in rows if r["arm"]==arm]
        scores[arm]={
            "attempts":len(rs),
            "verified_within_cap":sum(r["accepted"] for r in rs),
            "SAT_verified":sum(r["accepted"] and r["status"]=="SAT_VERIFIED" for r in rs),
            "UNSAT_certified":sum(r["accepted"] and r["status"]=="UNSAT_CERTIFIED" for r in rs),
            "timeout_unknown_or_late":sum(not r["accepted"] for r in rs),
            "PAR2_verified_s":round(sum(r["par2_s"] for r in rs),6),
            "mean_actual_swaps":round(sum(r["cf6"]["actual_swaps"] for r in rs)/max(1,len(rs)),3),
            "first_reductions":sum(r["first_reduction"]["first_effective_reduce"] for r in rs),
            "sum_swapped_kept_bcp500":sum(r["cf6"]["swapped_in_bcp500"] for r in rs),
            "sum_swapped_kept_analysis500":sum(r["cf6"]["swapped_in_analysis500"] for r in rs),
        }
    return scores

def family_ci(rows,ref,variant,draws=5000):
    fam=collections.defaultdict(lambda:collections.defaultdict(list))
    for row in rows:
        fam[row["family"]][row["arm"]].append(row["par2_s"])
    groups=sorted(fam)
    assert len(groups)==4
    for group in groups:
        assert len(fam[group][ref])==len(fam[group][variant])
    def measure(selected):
        a=sum(sum(fam[g][ref]) for g in selected)
        b=sum(sum(fam[g][variant]) for g in selected)
        return 100*(a-b)/a if a else 0
    rng=random.Random(660014)
    outcomes=sorted(measure([rng.choice(groups) for _ in groups])
                    for _ in range(draws))
    return {
        "relative_PAR2_reduction_pct":round(measure(groups),5),
        "family_cluster_bootstrap95_pct":[round(outcomes[int((draws-1)*x)],5)
                                        for x in (0.025,0.975)],
        "independent_families":len(groups),
        "not_a_blind_holdout":True
    }

def final():
    p=json.loads((ROOT/"frozen/protocol.json").read_text())
    assert p["source_count"]==14 and not p["blind_holdout"]
    real=[]
    all_ids=[]
    for index in range(SHARDS):
        d=ROOT/"downloads"/("cf6-real14-%d"%index)
        manifest=json.loads((d/"manifest.json").read_text())
        assert manifest["shard"]==index
        assert manifest["cap_s"]==CAP_REAL
        assert manifest["solver_sha"]==p["solver_binary_sha256"]
        rows=[json.loads(x) for x in (d/"trials.jsonl").read_text().splitlines()]
        assert len(rows)==manifest["attempts"]==len(manifest["source_ids"])*len(ARMS)
        assert {x["id"] for x in rows}==set(manifest["source_ids"])
        all_ids+=manifest["source_ids"]
        real+=rows
    assert sorted(all_ids)==sorted(IDS)
    assert len(real)==len(IDS)*len(ARMS)
    replay_dir=ROOT/"downloads"/"cf6-replay16"
    meta=json.loads((replay_dir/"manifest.json").read_text())
    assert meta["source_id"]==REPLAY_ID and meta["cap_s"]==CAP_REPLAY
    assert meta["solver_sha"]==p["solver_binary_sha256"]
    rr=[json.loads(x) for x in (replay_dir/"trials.jsonl").read_text().splitlines()]
    assert len(rr)==REPLAY_REPS*len(ARMS)
    assert ensure_matched(real,"aggregate-real")==14
    assert ensure_matched(rr,"aggregate-replay")==REPLAY_REPS
    comparisons={a:family_ci(real,"BASE",a) for a in ARMS if a!="BASE"}
    result={
        "status":"COMPLETE",
        "sources":14,"source_families":p["families"],
        "one_logical_cpu":True,
        "real14":{"cap_s":CAP_REAL,"distinct_orig2024":14,
                  "attempts":len(real),"arms":score(real),
                  "comparisons_BASE":comparisons},
        "replay16":{"cap_s":CAP_REPLAY,"one_known_scheduling_original":True,
                    "repetitions":REPLAY_REPS,"attempts":len(rr),
                    "arms":score(rr),
                    "single_formula_repeats_not_independent":True},
        "full_candidate_identity_ledgers":True,
        "no_wrong_SAT_UNSAT_observed":True,
        "retrospective_not_blind":True,
        "promotion":False,
        "claims":"Mechanistic single-early-reduction swaps; no general solver speedup claim"
    }
    write(ROOT/"final/report.json",result)
    with (ROOT/"final/trials_real14.jsonl").open("w") as f:
        for row in real:f.write(json.dumps(row,sort_keys=True)+"\n")
    with (ROOT/"final/trials_replay16.jsonl").open("w") as f:
        for row in rr:f.write(json.dumps(row,sort_keys=True)+"\n")
    emit("CF6_FINAL",result)

def main():
    a=argparse.ArgumentParser()
    a.add_argument("action",choices=("freeze","preflight","shard","replay","final"))
    a.add_argument("--shard",type=int,default=0)
    args=a.parse_args()
    if args.action=="freeze":freeze()
    elif args.action=="preflight":protocol_preflight()
    elif args.action=="shard":shard(args.shard)
    elif args.action=="replay":replay()
    elif args.action=="final":final()

if __name__=="__main__":main()
