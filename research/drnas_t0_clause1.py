#!/usr/bin/env python3
"""T0-CLAUSE1 diagnostic: early CDCL learned clause quality vs true first branch.

Pinned X5 with observation-only telemetry. 60 published original SATLIB CNFs
from sha-sorted positions 22..31, disjoint from T0 studies at 0..21.
Comparison: same full original CNF, one original polarity, one first polarity
flipped. No solver makes decisions from telemetry. No training or tuning.
Every solved SAT model and every solved UNSAT proof is independently verified.
"""
from __future__ import annotations
import collections, hashlib, json, os, random, signal, subprocess, tempfile, time
from pathlib import Path
import drnas_t0_frontier1 as F
import drnas_t0_interaction2 as I

ROOT=Path("t0_clause1")
ROOT.mkdir(exist_ok=True)
I.ROOT=ROOT
I.START=22
I.PER_FAMILY=10
CAP=2.0
BIN=Path("build/drnas-t0-clause1").resolve()

def emit(tag,obj):
    print(tag+" "+json.dumps(obj,sort_keys=True,separators=(",",":")),flush=True)

def run(src,first_flip,n,clauses,instrumented=True):
    program=BIN if instrumented else F.BIN
    with tempfile.TemporaryDirectory() as d:
        proof=Path(d)/"original.drat"
        cmd=[str(program),str(Path(src["path"]).resolve()),
             "--mode","core","--time",str(CAP),"--stats",
             "--x5-no-minimize","--branch-at","1",
             "--proof",str(proof)]
        if first_flip:cmd.append("--flip-branch")
        t=time.perf_counter()
        p=subprocess.Popen(cmd,text=True,stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE,start_new_session=True)
        expired=False
        try:out,err=p.communicate(timeout=CAP+0.8)
        except subprocess.TimeoutExpired:
            expired=True
            os.killpg(p.pid,signal.SIGKILL)
            out,err=p.communicate()
        wall=time.perf_counter()-t
        if not expired:
            assert p.returncode in (0,10,20),(
                "SOLVER_EXIT",src["name"],instrumented,p.returncode,err[-900:])
        status="TIMEOUT" if expired else (
            "SAT" if p.returncode==10 else "UNSAT" if p.returncode==20
            else "UNKNOWN")
        verified=False
        if status=="SAT":
            verified=F.check_sat(out,n,clauses)
            assert verified,("INVALID_SAT_MODEL",src["name"],first_flip)
        elif status=="UNSAT":
            assert proof.is_file() and proof.stat().st_size>0,(
                "MISSING_ORIGINAL_DERIVATION",src["name"])
            check=subprocess.run([str(F.DRAT),src["path"],str(proof)],
                text=True,capture_output=True,timeout=40)
            verified=(check.returncode==0 and "s VERIFIED" in check.stdout)
            assert verified,("INVALID_ORIGINAL_DRAT",src["name"],first_flip,
                             check.stdout[-400:],check.stderr[-300:])
        if verified:
            assert status==src["label"],("SATLIB_LABEL_CONFLICT",src["name"],status)
        stats={}
        for line in err.splitlines():
            name,sep,part=line.partition(" ")
            if name in ("X41_STATS","X45_COMPARE","T0_CLAUSE_STATS"):
                assert name not in stats,("DUPLICATE_TELEMETRY",name)
                stats[name]=json.loads(part)
        if not expired:
            assert "X41_STATS" in stats and "X45_COMPARE" in stats
            if instrumented:assert "T0_CLAUSE_STATS" in stats
        core=stats.get("X41_STATS",{})
        compare=stats.get("X45_COMPARE",{})
        quality=stats.get("T0_CLAUSE_STATS",{})
        return {
            "mode":"instrumented" if instrumented else "frozen_reference",
            "first_flip":first_flip,"status":status,"verified":verified,
            "e2e_s":wall,"par2_verified_s":wall if verified and wall<=CAP else CAP*2,
            "conflicts":core.get("conflicts"),"decisions":core.get("decisions"),
            "propagations":core.get("propagations"),
            "first_reached":compare.get("reached",False),
            "baseline_literal":compare.get("baseline_literal"),
            "actual_literal":compare.get("actual_literal"),
            "pre_state_digest":compare.get("pre_state_digest"),
            "quality":quality}

def predict(a,b,metric,low_better=True,margin=0.25):
    # Fixed before the benchmark. Require EXACT 8 learnt clauses on each side
    # so censored, trivially solved arms do not bias the quality sample.
    x,y=a["quality"],b["quality"]
    if x.get("early8")!=8 or y.get("early8")!=8:return 0
    v1=x[metric]/8;v2=y[metric]/8
    delta=v2-v1
    if abs(delta)<=margin:return 0
    return (1 if delta<0 else -1) if low_better else (
           1 if delta>0 else -1)

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    assert len(os.sched_getaffinity(0))==1
    assert BIN.is_file() and F.BIN.is_file() and F.DRAT.is_file()
    sources=[]
    for fam in F.SETS:sources.extend(I.new_sources(fam))
    assert len(sources)==60 and len({r["sha256"] for r in sources})==60
    # Freeze the source SHA set, fixed scores and denominators BEFORE any solve.
    frozen={
        "status":"FROZEN_BEFORE_SOLVER",
        "source_count":len(sources),
        "cohort":"published SATLIB entries 22..31 in each of six archives",
        "disjoint_from_t0_previous":True,
        "arms":"same native CDCL / original vs flipped FIRST POLARITY",
        "native_source":"pinned source X5_NO_MIN; only first branching polarity differs",
        "diagnostic":"LBD length backjump depth first 8/16 learned plus later real reuse",
        "primary_prediction":"lower mean LBD in first EXACT 8 learned, margin 0.25",
        "secondary_prediction":"lower mean learned clause length in first EXACT 8, margin 0.5",
        "predictions_are_retrospective":"requires first 8 conflicts; NOT a free T0 prediction",
        "one_logical_cpu":True,"cap_s":CAP,"no_train_no_refit":True,
        "labels_not_passed_to_solver":True,"real_industrial_holdout":False,
        "main_modified":False,"no_promotion":True,"sources":sources}
    m=ROOT/"manifest.json"
    m.write_text(json.dumps(frozen,indent=2,sort_keys=True)+"\n")
    emit("T0_CLAUSE_FROZEN",{"count":len(sources),"sha256":F.sha(m.read_bytes()),
         "primary":"lower_early8_LBD","from_previous_sources":False})
    rng=random.Random(141135)
    rng.shuffle(sources)
    rows=[]
    for index,src in enumerate(sources):
        raw=Path(src["path"]).read_bytes()
        assert F.sha(raw)==src["sha256"]
        n,clauses=F.parse(raw)
        order=[False,True]
        random.Random(int(src["sha256"][:12],16)).shuffle(order)
        result={}
        for flip in order:result[flip]=run(src,flip,n,clauses)
        a,b=result[False],result[True]
        assert a["verified"] and b["verified"],(
            "UNVERIFIED_MATCHED_RESULT",src["name"])
        assert a["first_reached"] and b["first_reached"],(
            "MISSING_FIRST_BRANCH",src["name"])
        assert a["pre_state_digest"]==b["pre_state_digest"],(
            "DIFFERENT_FIRST_DECISION_SNAPSHOT",src["name"])
        assert a["baseline_literal"]==b["baseline_literal"]!=0
        assert a["actual_literal"]==a["baseline_literal"]
        assert b["actual_literal"]==-a["actual_literal"]
        # An observational instrument must preserve the original X5
        # solve counters and decision snapshot, not merely SAT/UNSAT.
        if index<6:
            original=run(src,False,n,clauses,instrumented=False)
            assert original["verified"] and original["status"]==a["status"]
            for key in ("conflicts","decisions","propagations","first_reached",
                        "baseline_literal","actual_literal","pre_state_digest"):
                assert original[key]==a[key],(
                    "TELEMETRY_ALTERED_CDCL",src["name"],key,original[key],a[key])
        truth=F.compare(a,b)
        primary=predict(a,b,"glue_sum8",True,0.25)
        secondary=predict(a,b,"length_sum8",True,0.5)
        row={
            "name":src["name"],"family":src["family"],"sha256":src["sha256"],
            "base":a,"flip":b,"actual":truth,
            "predict_lbd8":primary,"predict_length8":secondary}
        rows.append(row)
        emit("T0_CLAUSE_PAIR",{
            "index":index,"family":src["family"],"name":src["name"],
            "actual":truth,"lbd8_guess":primary,"len8_guess":secondary,
            "base_conflicts":a["conflicts"],"flip_conflicts":b["conflicts"],
            "base_lbd8_sum":a["quality"]["glue_sum8"],
            "flip_lbd8_sum":b["quality"]["glue_sum8"],
            "base_early":a["quality"]["early8"],
            "flip_early":b["quality"]["early8"],
            "base_reuse":a["quality"]["early16_distinct_reused"],
            "flip_reuse":b["quality"]["early16_distinct_reused"]})
    def score(pred):
        sel=[r for r in rows if r[pred] and r["actual"]]
        flip=[r for r in rows if r[pred]==1]
        return {"nonabstain":sum(bool(r[pred]) for r in rows),
            "informative":len(sel),
            "correct":sum(r[pred]==r["actual"] for r in sel),
            "wrong":sum(r[pred]!=r["actual"] for r in sel),
            "predicted_flip_wins":sum(r["actual"]==1 for r in flip),
            "predicted_flip_losses":sum(r["actual"]==-1 for r in flip)}
    early16=[r for r in rows if r["base"]["quality"]["early16"]==16 and r["flip"]["quality"]["early16"]==16]
    reuse=[r for r in early16 if
           r["base"]["quality"]["early16_distinct_reused"]!=r["flip"]["quality"]["early16_distinct_reused"]]
    distinct_more_better=sum(
        ((r["flip"]["quality"]["early16_distinct_reused"]-
           r["base"]["quality"]["early16_distinct_reused"])*r["actual"]>0)
        for r in reuse if r["actual"])
    final={
        "status":"COMPLETE","sources":len(rows),
        "original_SAT_or_DRAT_verified_pairs":len(rows),
        "first_snapshot_matched_pairs":len(rows),
        "instrumented_vs_original_equal_smoke":6,
        "observed_flip_better":sum(r["actual"]==1 for r in rows),
        "observed_base_better":sum(r["actual"]==-1 for r in rows),
        "observed_neutral":sum(r["actual"]==0 for r in rows),
        "both_8_conflict_windows":sum(
            r["base"]["quality"]["early8"]==8 and
            r["flip"]["quality"]["early8"]==8 for r in rows),
        "both_16_conflict_windows":len(early16),
        "lbd8":score("predict_lbd8"),
        "length8":score("predict_length8"),
        "reuse_comparable_pairs":len(reuse),
        "more_distinct_reuse_on_better_arm":distinct_more_better,
        "totals":{
            "base_conflicts":sum(r["base"]["conflicts"] for r in rows),
            "flip_conflicts":sum(r["flip"]["conflicts"] for r in rows),
            "base_decisions":sum(r["base"]["decisions"] for r in rows),
            "flip_decisions":sum(r["flip"]["decisions"] for r in rows)},
        "one_logical_cpu":True,"no_model_training":True,
        "not_blind_realworld":True,"not_general_speedup_claim":True,
        "no_main_modification":True,"no_promotion":True,
        "manifest_sha256":F.sha(m.read_bytes())}
    (ROOT/"rows.jsonl").write_text(
        "".join(json.dumps(x,sort_keys=True)+"\n" for x in rows))
    (ROOT/"report.json").write_text(json.dumps(final,indent=2,sort_keys=True)+"\n")
    emit("T0_CLAUSE_FINAL",final)

if __name__=="__main__":main()
