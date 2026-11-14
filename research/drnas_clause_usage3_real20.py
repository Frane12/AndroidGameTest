#!/usr/bin/env python3
"""CLAUSE-USAGE3 REAL20: lifetime knowledge utility on original SAT2024 CNFs.

Preselected 20 cases from frozen REAL36 by immutable IDs, original SHA
verified against the original 2024 SAT-Competition source archive.
Native X5 baseline vs already-existing X5 retain policy; same instrumented
binary and one logical CPU. Records actual post-birth future BCP and conflict
analysis uses of first 100 learned clauses after 100 and 500 conflicts.

Censoring is explicit: cohort age >=100/500 is required, and matched arms
must BOTH reach at least 200/600 total conflicts for aggregate comparisons.
Never infer a speed advantage from an unverified UNKNOWN outcome.
"""
from __future__ import annotations
import hashlib,json,os,random,resource,signal,subprocess,sys,tempfile,time
from pathlib import Path

R=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(R/"research")]
import drnas_x55_cpu_real36 as REAL

OUT=Path("clause_usage3_real20")
OUT.mkdir(exist_ok=True)
BINARY=(R/"build/drnas-clause-usage3").resolve()
CONTROL=(R/"build/drnas-clause-usage3-reference").resolve()
DRAT=(R/"build/drat-trim").resolve()
CAP=4.0
IDS=(0,2,3,5,6,8,9,12,14,15,16,18,19,20,22,23,24,26,28,31)
MODES=("BASELINE","RETAIN")
BINS=("LBD<=2","LBD3-6","LBD>=7")

def sha(data):return hashlib.sha256(data).hexdigest()
def emit(key, data):print(key+" "+json.dumps(data,sort_keys=True),flush=True)
def saved(path,data):
    path=Path(path)
    path.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")

def parse_stats(err,instrumented):
    out={}
    for line in err.splitlines():
        k,sp,p=line.partition(" ")
        if k not in ("X41_STATS","X5_STATS","CLAUSE_USAGE3"):continue
        if k in out:raise RuntimeError(("DUPLICATE_TELEMETRY",k))
        out[k]=json.loads(p)
    required=("X41_STATS","X5_STATS","CLAUSE_USAGE3") if instrumented else ("X41_STATS","X5_STATS")
    if not all(k in out for k in required):raise RuntimeError(
        ("MISSING_TELEMETRY",list(out),err[-1200:]))
    return out

def trial(source,mode,instrumented=True):
    binpath=BINARY if instrumented else CONTROL
    raw=Path(source["path"]).read_bytes()
    assert sha(raw)==source["sha256"]
    n,clauses=REAL.parse_cnf(raw)
    assert n==source["nvars"] and len(clauses)==source["nclauses"],(
        "SOURCE_DIMENSIONS_CHANGED",source["id"])
    with tempfile.TemporaryDirectory() as tmp:
        proof=Path(tmp)/"proof.drat"
        cmd=[str(binpath),str(Path(source["path"]).resolve()),"--mode","core",
             "--time",str(CAP),"--stats","--x5-no-minimize",
             "--proof",str(proof),
             "--x5-retain" if mode=="RETAIN" else "--x5-no-retain"]
        before=resource.getrusage(resource.RUSAGE_CHILDREN)
        start=time.perf_counter()
        p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           text=True,start_new_session=True)
        killed=False
        try:stdout,stderr=p.communicate(timeout=CAP+1.0)
        except subprocess.TimeoutExpired:
            killed=True
            os.killpg(p.pid,signal.SIGKILL)
            stdout,stderr=p.communicate()
        wall=time.perf_counter()-start
        after=resource.getrusage(resource.RUSAGE_CHILDREN)
        cpu=max(0.0,(after.ru_utime+after.ru_stime)-(before.ru_utime+before.ru_stime))
        if not killed:assert p.returncode in (0,10,20),(
            "INVALID_EXEC_CODE",source["id"],mode,p.returncode,stderr[-500:])
        status="TIMEOUT" if killed else "SAT" if p.returncode==10 else (
            "UNSAT" if p.returncode==20 else "UNKNOWN")
        valid=False;check_s=0.0
        if status=="SAT":
            valid=REAL.check_sat(stdout,clauses,n)
            assert valid,("INVALID_SAT_MODEL_ORIGINAL_CNF",source["id"],mode)
        if status=="UNSAT":
            assert proof.is_file() and proof.stat().st_size>0,(
                "MISSING_ORIGINAL_PROOF",source["id"],mode)
            t=time.perf_counter()
            chk=subprocess.run([str(DRAT),str(Path(source["path"]).resolve()),
                                str(proof)],capture_output=True,text=True,timeout=65)
            check_s=time.perf_counter()-t
            valid=chk.returncode==0 and "s VERIFIED" in chk.stdout
            assert valid,("UNVERIFIED_UNSAT",source["id"],mode,chk.stdout[-350:],chk.stderr[-350:])
        if killed:
            telemetry={}
        else:
            telemetry=parse_stats(stderr,instrumented)
            assert telemetry["X41_STATS"]["status"]==status,(
                "X5_STATUS_MISMATCH",source["id"])
        stats=telemetry.get("X41_STATS",{})
        q=telemetry.get("CLAUSE_USAGE3",{})
        if instrumented:
            assert isinstance(q.get("bins"),list) and len(q["bins"])==3,(
                "QUALITY_METRIC_MISSING",source["id"],mode)
            assert all(x["label"]==BINS[i] for i,x in enumerate(q["bins"]))
            assert q["final_conflicts"]==stats["conflicts"]
            assert sum(x["born"] for x in q["bins"])==q["first100_learned"]
            for x in q["bins"]:
                assert 0<=x["used100_distinct"]<=x["eligible100"]<=x["born"]<=100
                assert 0<=x["used500_distinct"]<=x["eligible500"]<=x["born"]<=100
                assert x["eligible500"]<=x["eligible100"]
                assert x["used100_distinct"]<=x["used500_distinct"]
        return {
            "arm":mode,"instrumented":instrumented,"status":status,
            "verified":valid,"accepted":valid and wall<=CAP,
            "wall_e2e_s":wall,"solver_cpu_s":cpu,"proof_check_s":check_s,
            "PAR2_verified_s":wall if valid and wall<=CAP else 2*CAP,
            "conflicts":stats.get("conflicts"),"decisions":stats.get("decisions"),
            "propagations":stats.get("propagations"),
            "learned":stats.get("learnt"),"removed":stats.get("reduce_removed"),
            "protected":telemetry.get("X5_STATS",{}).get("protected_clauses"),
            "quality":q}

def totals(pairs,flag=None):
    included=[p for p in pairs if flag is None or flag(p)]
    result={}
    for arm in MODES:
        rows=[p[arm] for p in included]
        result[arm]={
            "n":len(rows),"verified":sum(x["verified"] for x in rows),
            "accepted":sum(x["accepted"] for x in rows),
            "PAR2_verified_s":round(sum(x["PAR2_verified_s"] for x in rows),5),
            "cpu_s":round(sum(x["solver_cpu_s"] for x in rows),5),
            "removed_total":sum(x["removed"] or 0 for x in rows),
            "protected_total":sum(x["protected"] or 0 for x in rows),
            "conflicts_total":sum(x["conflicts"] or 0 for x in rows)
        }
    return result

def lifetime(pairs,horizon):
    assert horizon in (100,500)
    valid=[p for p in pairs if
           all((p[a]["conflicts"] or 0)>=100+horizon for a in MODES)]
    result={}
    for arm in MODES:
        entry={"sources":len(valid),"born":0,"eligible":0,"distinct_used":0,
               "BCP_events":0,"analysis_events":0,"by_LBD":[]}
        for b in range(3):
            binrows=[p[arm]["quality"]["bins"][b] for p in valid]
            r={"label":BINS[b],"born":sum(x["born"] for x in binrows),
               "eligible":sum(x["eligible"+str(horizon)] for x in binrows),
               "distinct_used":sum(x["used"+str(horizon)+"_distinct"] for x in binrows),
               "BCP_events":sum(x["bcp"+str(horizon)+"_events"] for x in binrows),
               "analysis_events":sum(x["analysis"+str(horizon)+"_events"] for x in binrows)}
            entry["by_LBD"].append(r)
            for k in ("born","eligible","distinct_used","BCP_events","analysis_events"):
                entry[k]+=r[k]
        entry["used_fraction"]=(entry["distinct_used"]/entry["eligible"]
                                if entry["eligible"] else None)
        result[arm]=entry
    return {"both_eligible_source_count":len(valid),"arms":result,
            "censoring":"both_solvers_reached_first100_plus_horizon_conflicts"}

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    assert len(os.sched_getaffinity(0))==1
    for path in (BINARY,CONTROL,DRAT):assert path.is_file(),path
    sources,old=REAL.official_manifest()
    index={int(s["id"]):s for s in sources}
    assert len(index)==36 and len(IDS)==20 and all(i in index for i in IDS)
    selected=[index[i] for i in IDS]
    assert len({s["sha256"] for s in selected})==20
    freeze={
        "status":"FROZEN_BEFORE_BENCHMARK","source_archive":"SAT Competition 2024",
        "original_real36_run":43387395060,
        "original_manifest_sha256":old["manifest_sha256"],
        "frozen_selected_ids":list(IDS),
        "original_CNF_count":len(selected),"original_source_SHA256":[s["sha256"] for s in selected],
        "family_counts":{k:sum(s["family"]==k for s in selected)
                         for k in sorted({s["family"] for s in selected})},
        "one_logical_cpu":True,"same_binary":True,
        "arms":list(MODES),"max_seconds_per_trial":CAP,
        "main_unmodified":True,"no_promotion":True,
        "source_is_retrospective_not_blind":True,
        "no_statistical_training_or_adaptation":True,
        "quality_cohort":"clauses_learned_at_conflicts_1_through_100",
        "quality_windows":"post_birth_100_and_500_conflicts_only_for_fully_exposed_clauses",
        "matched_windows_require_both_reach_200_and_600_conflicts":True,
        "retention_mode_is_not_pure_LBD_only":True
    }
    manifest=OUT/"protocol.json"
    saved(manifest,freeze)
    emit("CLAUSE_USAGE3_FROZEN",{
        "selected_ids":list(IDS),"source_count":len(selected),
        "manifest_sha256":sha(manifest.read_bytes()),
        "families":freeze["family_counts"],"one_cpu":True})
    random.Random(141139).shuffle(selected)
    pairs=[]
    checks=[]
    for idx,s in enumerate(selected):
        order=list(MODES)
        random.Random(int(s["sha256"][:12],16)).shuffle(order)
        trials={}
        for arm in order:trials[arm]=trial(s,arm)
        a,b=trials["BASELINE"],trials["RETAIN"]
        assert not (a["verified"] and b["verified"] and a["status"]!=b["status"]),(
            "CONTRADICTORY_VERIFIED_RESULT",s["id"])
        if (a["conflicts"] or 0)>=100 and (b["conflicts"] or 0)>=100:
            aa,bb=a["quality"]["bins"],b["quality"]["bins"]
            assert [(x["born"],x["lbd_sum"],x["length_sum"]) for x in aa]==[
                (x["born"],x["lbd_sum"],x["length_sum"]) for x in bb],(
                "PRE_RETENTION_COHORT_ALREADY_DIFFERENT",s["id"])
        # Same-binary observational smoke: compare 4 instances if fully
        # resolved; timeout makes counter equality unsuitable for an assertion.
        if idx<4:
            original=trial(s,"BASELINE",instrumented=False)
            if original["verified"] and a["verified"]:
                assert all(original[k]==a[k] for k in (
                    "status","conflicts","decisions","propagations","learned","removed")),(
                    "INSTRUMENTATION_CHANGED_NATIVE_CDCL",s["id"])
                checks.append(s["id"])
        record={"id":s["id"],"family":s["family"],"sha256":s["sha256"],
                "nvars":s["nvars"],"nclauses":s["nclauses"],
                "BASELINE":a,"RETAIN":b}
        pairs.append(record)
        emit("CLAUSE_USAGE3_PAIR",{
            "id":s["id"],"family":s["family"],
            "baseline_status":a["status"],"retain_status":b["status"],
            "baseline_conflicts":a["conflicts"],"retain_conflicts":b["conflicts"],
            "baseline_removals":a["removed"],"retain_removals":b["removed"],
            "baseline_tracked":a["quality"].get("first100_learned"),
            "retain_tracked":b["quality"].get("first100_learned"),
            "baseline_500_exposed":sum(q["eligible500"] for q in a["quality"]["bins"]),
            "retain_500_exposed":sum(q["eligible500"] for q in b["quality"]["bins"])})
    report={
        "status":"COMPLETE","original_CNFs":len(pairs),
        "original_models_or_DRAT_verified_total":sum(
            p[a]["verified"] for p in pairs for a in MODES),
        "both_verified":sum(p["BASELINE"]["verified"] and p["RETAIN"]["verified"]
                            for p in pairs),
        "same_binary_diagnostic_vs_control_smoke_verified":checks,
        "all_pairs_SHA_pinned":True,
        "all_pair_results":totals(pairs),
        "after_100_conflicts":lifetime(pairs,100),
        "after_500_conflicts":lifetime(pairs,500),
        "pairs_with_reduction":sum(
            ((p["BASELINE"]["removed"] or 0)>0 or
             (p["RETAIN"]["removed"] or 0)>0) for p in pairs),
        "no_training_or_refit":True,"one_cpu":True,"no_main_changes":True,
        "solver_promoted":False,"retrospective_not_blind":True,
        "no_general_speedup_claim":True,
        "protocol_sha256":sha(manifest.read_bytes())
    }
    (OUT/"paired.jsonl").write_text(
        "".join(json.dumps(p,sort_keys=True)+"\n" for p in pairs))
    saved(OUT/"report.json",report)
    emit("CLAUSE_USAGE3_FINAL",report)

if __name__=="__main__":main()
