#!/usr/bin/env python3
"""CLCF5: counterfactual first-reduction learned clause selection on real SAT2024.

Exactly one early deletion-selection event differs. BASE (unchanged activity
ranking), LBD (delete high LBD), RECENT (delete least recently reason-used),
HASH (blind deterministic sham). Same deletion budget, same native X5 core,
one logical CPU, no learning from formula identities, original-CNF proofs.

The cohort is selected from previously used REAL36 for mechanistic diagnosis,
NOT a prospective blind industrial holdout. UNKNOWN gets PAR2 timeout penalty.
"""
from __future__ import annotations
import hashlib, json, os, random, resource, signal, subprocess, sys, tempfile, time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"research"))
import drnas_x55_cpu_real36 as REAL

OUT=Path("clause_cf5_real14")
OUT.mkdir(exist_ok=True)
BIN=(ROOT/"build/drnas-clause-cf5").resolve()
REF=(ROOT/"build/drnas-clause-cf5-reference").resolve()
DRAT=(ROOT/"build/drat-trim").resolve()
CAP=4.0
IDS=(0,3,5,6,9,12,15,16,19,20,23,24,28,31)
ARMS=("BASE","LBD","RECENT","HASH")

def sha(raw):return hashlib.sha256(raw).hexdigest()
def emit(label,data):print(label+" "+json.dumps(data,sort_keys=True),flush=True)
def save(path,data):Path(path).write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")

def trial(source,arm,reference=False):
    raw=Path(source["path"]).read_bytes()
    assert sha(raw)==source["sha256"],("SOURCE_SHA_DRIFT",source["id"])
    n,cs=REAL.parse_cnf(raw)
    assert n==source["nvars"] and len(cs)==source["nclauses"]
    with tempfile.TemporaryDirectory() as tmp:
        proof=Path(tmp)/"source.drat"
        cmd=[str(REF if reference else BIN),str(Path(source["path"]).resolve()),
             "--mode","core","--time",str(CAP),"--stats",
             "--x5-no-minimize","--x5-no-retain","--proof",str(proof)]
        if not reference:cmd+=["--cf5-policy",arm]
        before=resource.getrusage(resource.RUSAGE_CHILDREN)
        started=time.perf_counter()
        p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           text=True,start_new_session=True)
        killed=False
        try:stdout,stderr=p.communicate(timeout=CAP+.8)
        except subprocess.TimeoutExpired:
            killed=True
            try:os.killpg(p.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            stdout,stderr=p.communicate()
        wall=time.perf_counter()-started
        after=resource.getrusage(resource.RUSAGE_CHILDREN)
        cpu=max(0.,(after.ru_utime+after.ru_stime)-(before.ru_utime+before.ru_stime))
        if not killed:
            assert p.returncode in (0,10,20),(
                "SOLVER_EXECUTION_ERROR",source["id"],arm,p.returncode,stderr[-850:])
        status="TIMEOUT" if killed else {
            10:"SAT",20:"UNSAT",0:"UNKNOWN"}.get(p.returncode,"UNKNOWN")
        verified=False
        if status=="SAT":
            verified=REAL.check_sat(stdout,cs,n)
            assert verified,("INVALID_ORIGINAL_SAT",source["id"],arm)
        if status=="UNSAT":
            assert proof.exists() and proof.stat().st_size>0,(
                "MISSING_UNSAT_PROOF",source["id"],arm)
            chk=subprocess.run([str(DRAT),str(Path(source["path"]).resolve()),
                                str(proof)],capture_output=True,text=True,timeout=65)
            verified=chk.returncode==0 and "s VERIFIED" in chk.stdout
            assert verified,("INVALID_ORIGINAL_UNSAT_DRAT",source["id"],arm,
                             chk.stdout[-400:],chk.stderr[-400:])
        telemetry={}
        if not killed:
            for ln in stderr.splitlines():
                k,sep,payload=ln.partition(" ")
                if k in ("X41_STATS","X5_STATS","CLCF5_STATS"):
                    assert k not in telemetry,("DUPLICATE_TELEMETRY",k)
                    telemetry[k]=json.loads(payload)
            assert "X41_STATS" in telemetry and "X5_STATS" in telemetry
            if not reference:assert "CLCF5_STATS" in telemetry
            assert telemetry["X41_STATS"]["status"]==status
        stats=telemetry.get("X41_STATS",{})
        reduce=telemetry.get("CLCF5_STATS",{})
        if not reference:
            assert reduce.get("policy")==arm
            assert len(reduce["by_LBD"])==3
            count=reduce["candidates"];removed=reduce["deleted"]
            assert count==sum(x["candidates"] for x in reduce["by_LBD"])
            assert removed==sum(x["deleted"] for x in reduce["by_LBD"])
            assert count==removed+sum(x["retained"] for x in reduce["by_LBD"])
            if reduce["first_effective_reduce"]:
                assert count>=128 and removed==count//2
                assert reduce["first_reduce_conflicts"]>=2200
            else:assert count==removed==0
        return {
            "arm":arm,"reference":reference,"status":status,
            "verified":verified,"accepted":verified and wall<=CAP,
            "wall_e2e_s":wall,"cpu_s":cpu,
            "PAR2_verified_s":wall if verified and wall<=CAP else CAP*2,
            "conflicts":stats.get("conflicts"),
            "decisions":stats.get("decisions"),
            "propagations":stats.get("propagations"),
            "learnt":stats.get("learnt"),
            "removed_total":stats.get("reduce_removed"),
            "quality":reduce}

def aggregate(rows):
    result={}
    for arm in ARMS:
        arr=[row["arms"][arm] for row in rows]
        result[arm]={
            "attempts":len(arr),
            "verified":sum(x["verified"] for x in arr),
            "PAR2_verified_s":round(sum(x["PAR2_verified_s"] for x in arr),5),
            "CPU_s":round(sum(x["cpu_s"] for x in arr),5),
            "conflicts_completed_only":sum(x["conflicts"] or 0 for x in arr
                                            if x["accepted"]),
            "first_reductions":sum(x["quality"]["first_effective_reduce"] for x in arr),
            "post500_exposed":sum(x["quality"]["post500_observed"] for x in arr),
            "post500_reason_BCP_events":sum(
                sum(b["post500_bcp"] for b in x["quality"]["by_LBD"])
                for x in arr if x["quality"]["post500_observed"]),
            "post500_reason_analysis_events":sum(
                sum(b["post500_analysis"] for b in x["quality"]["by_LBD"])
                for x in arr if x["quality"]["post500_observed"]),
        }
    return result

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    assert len(os.sched_getaffinity(0))==1
    assert BIN.is_file() and REF.is_file() and DRAT.is_file()
    all_sources,real=REAL.official_manifest()
    by_id={s["id"]:s for s in all_sources}
    assert len(all_sources)==36 and len(IDS)==14 and len(set(IDS))==14
    sources=[by_id[i] for i in IDS]
    assert len({s["sha256"] for s in sources})==len(sources)
    frozen={
        "status":"FROZEN_BEFORE_SOLVING",
        "source_kind":"original SAT Competition 2024 retrospective REAL36",
        "original_archive_run":43387395060,
        "real36_manifest_sha256":real["manifest_sha256"],
        "selected_ids":list(IDS),
        "selected_sha256":[s["sha256"] for s in sources],
        "families":{k:sum(s["family"]==k for s in sources)
                    for k in sorted({s["family"] for s in sources})},
        "arms":list(ARMS),
        "source_count":len(sources),
        "cap_s":CAP,
        "same_number_deleted_at_first_effective_reduce":True,
        "only_first_effective_reduce_selection_changes":True,
        "all_arms_lbd_recency_sham_predefined":True,
        "no_cohort_training_or_tuning":True,
        "one_logical_cpu":True,"no_parallel_solver":True,
        "no_main_edits":True,"no_promotion":True,
        "post_observation_windows":[100,500],
        "source_labels_never_used_by_solver":True,
        "not_new_blind_industrial_holdout":True}
    manifest=OUT/"manifest.json"
    save(manifest,frozen)
    emit("CLCF5_FROZEN",{
        "count":len(sources),"source_ids":list(IDS),
        "sha256":sha(manifest.read_bytes()),"families":frozen["families"]})
    random.Random(141155).shuffle(sources)
    rows=[]
    for idx,s in enumerate(sources):
        modes=list(ARMS)
        random.Random(int(s["sha256"][:14],16)).shuffle(modes)
        current={}
        for mode in modes:current[mode]=trial(s,mode)
        if any(x["verified"] for x in current.values()):
            statuses={x["status"] for x in current.values() if x["verified"]}
            assert len(statuses)==1,("CONTRADICTORY_ORIGINAL_CNF_SOLUTIONS",s["id"])
        baseline=current["BASE"]["quality"]
        signature=("first_effective_reduce","first_reduce_conflicts",
                   "first_reduce_decisions","candidates","deleted",
                   "first_candidate_digest")
        for mode in ARMS:
            current_sign=current[mode]["quality"]
            assert all(baseline[f]==current_sign[f] for f in signature),(
                "NOT_A_PAIRED_FIRST_REDUCTION_STATE",s["id"],mode,
                {f:baseline[f] for f in signature},
                {f:current_sign[f] for f in signature})
        if idx<3:
            exact=trial(s,"BASE",reference=True)
            # A 4s cutoff can censor baseline: exact equality is meaningful
            # for both-completed only. Never promote UNKNOWN to solved.
            if exact["verified"] and current["BASE"]["verified"]:
                for field in ("status","conflicts","decisions",
                              "propagations","learnt","removed_total"):
                    assert exact[field]==current["BASE"][field],(
                        "OBSERVATION_CHANGED_CDCL",s["id"],field)
        row={"id":s["id"],"family":s["family"],"source_sha256":s["sha256"],
             "arms":current}
        rows.append(row)
        emit("CLCF5_PAIR",{
            "id":s["id"],"family":s["family"],
            "first_reduce":baseline["first_effective_reduce"],
            "first_reduction_candidates":baseline["candidates"],
            "first_reduction_deleted":baseline["deleted"],
            "status":{m:current[m]["status"] for m in ARMS},
            "verified":{m:current[m]["verified"] for m in ARMS},
            "PAR2_s":{m:round(current[m]["PAR2_verified_s"],4) for m in ARMS},
            "conflicts":{m:current[m]["conflicts"] for m in ARMS}})
    with (OUT/"paired.jsonl").open("w") as f:
        for p in rows:f.write(json.dumps(p,sort_keys=True)+"\n")
    # Comparison is observational, not a fitted optimal new policy.
    result={
        "status":"COMPLETE","source_count":len(rows),
        "paired_same_first_reduction_checked":len(rows),
        "first_reduction_triggered":sum(
            r["arms"]["BASE"]["quality"]["first_effective_reduce"] for r in rows),
        "post500_all_arms_exposed":sum(all(
            r["arms"][m]["quality"]["post500_observed"] for m in ARMS) for r in rows),
        "all_arms_verified":sum(all(
            r["arms"][m]["verified"] for m in ARMS) for r in rows),
        "aggregate":aggregate(rows),
        "no_branching_or_CDCL_proof_policy_changes":True,
        "original_models_and_unsat_drat_independently_checked":True,
        "one_cpu":True,"no_model_fitting":True,
        "not_blind_holdout":True,"no_main_change":True,
        "not_promoted":True,"not_general_speedup_claim":True,
        "manifest_sha256":sha(manifest.read_bytes())}
    save(OUT/"report.json",result)
    emit("CLCF5_FINAL",result)

if __name__=="__main__":main()
