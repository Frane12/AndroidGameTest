#!/usr/bin/env python3
"""SIG1 serial proof-checked trials, graph-disjoint train/validate/holdout.

Every candidate mode uses the SAME compiled signal native solver and exact
same original CNF.  No source labels enter solver execution. Only TRAIN
outcomes select the threshold; holdout never influences the policy file.
"""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import random
import signal
import subprocess
import sys
import tempfile
import time

R=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(R/"research"),str(R/"tests"),
             str(R/"research/drnas_deltax_guard")]
from test_drnas_deltax import validate_alias,canon
from test_drnas_deltacoop2 import check_witness
import drnas_x55_cpu_real36 as B

BIN=R/"build/drnas-deltax-signal"
CHECKER=R/"build/drat-trim"
THRESHOLDS=(0,4,8,16)
CAP=3.0
# The holdout is never read by the fit function.
SPLITS=("train","validation","holdout")
SIZES={"train":30,"validation":15,"holdout":15}

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,obj):
    p=Path(path);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def emit(tag,obj):print(tag+" "+json.dumps(obj,sort_keys=True),flush=True)

def sources(split):
    assert split in SPLITS
    root=R/"deltax_signal1_inputs"
    all_rows=json.loads((root/"manifest.json").read_text())
    manifest=root/(split+"_manifest.json")
    rows=json.loads(manifest.read_text())
    assert len({r["graph_id"] for r in rows})==SIZES[split] and len(rows)==SIZES[split]*3
    assert all(r["split"]==split for r in rows)
    assert len({r["sha256"] for r in all_rows})==180
    others={r["graph_id"] for r in all_rows if r["split"]!=split}
    assert not others.intersection(r["graph_id"] for r in rows)
    for r in rows:assert sha(R/r["path"])==r["sha256"],("SOURCE_SHA_DRIFT",r["name"])
    return rows,sha(manifest)

def run_one(source,mode,folder,cap=CAP):
    assert mode in ("join","deltax-guard") or mode in (
        "deltax-signal-"+str(n) for n in THRESHOLDS)
    src=R/source["path"]
    assert sha(src)==source["sha256"]
    n,cs=B.parse_cnf(src.read_bytes())
    assert n==source["nvars"] and len(cs)==source["nclauses"]
    assert source["source_kind"]=="new_matched_graph_signal"
    with tempfile.TemporaryDirectory() as td:
        proof=Path(td)/"trial.drat"
        cmd=[str(BIN.resolve()),str(src.resolve()),
             "--mode","core","--time",str(max(.05,cap-.10)),
             "--stats","--x5-no-minimize","--coop4","gate",
             "--coop4-eager","--coop5","off",
             "--delta2",mode,"--proof",str(proof)]
        start=time.perf_counter()
        p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           text=True,start_new_session=True)
        expired=False
        try:stdout,stderr=p.communicate(timeout=cap+.22)
        except subprocess.TimeoutExpired:
            expired=True;os.killpg(p.pid,signal.SIGKILL);stdout,stderr=p.communicate()
        wall=time.perf_counter()-start
        status="TIMEOUT" if expired else "UNKNOWN"
        if not expired:
            assert p.returncode in (0,10,20,153),(
                "PROCESS_ERROR",source["name"],mode,p.returncode,stderr[-700:])
            if p.returncode==10:
                assert B.check_sat(stdout,cs,n),("WRONG_SAT",source["name"],mode)
                status="SAT_VERIFIED"
            elif p.returncode==20:
                assert proof.exists() and proof.stat().st_size,(
                    "UNSAT_WITHOUT_ORIGINAL_PROOF",source["name"],mode)
                try:
                    checked=subprocess.run([str(CHECKER),str(src),str(proof)],
                                  text=True,capture_output=True,timeout=35)
                    assert checked.returncode==0 and "s VERIFIED" in checked.stdout,(
                        "UNSAT_PROOF_INVALID",source["name"],mode,
                        checked.stdout[-500:],checked.stderr[-500:])
                    status="UNSAT_CERTIFIED"
                except subprocess.TimeoutExpired:
                    status="UNSAT_CHECK_TIMEOUT"
        labels={};alias=[];causes=[];signal_events=[]
        original={canon(c) for c in cs}
        for line in stderr.splitlines():
            tag,_,body=line.partition(" ")
            if tag in ("X41_STATS","DELTAX_STATS","DELTAX_GUARD_STATS",
                       "DELTAX_GUARD_SOURCE","DELTAX_CAUSAL_STATS",
                       "DELTAX_SIGNAL_STATS","DELTA2_JOIN"):
                assert tag not in labels,("DUPLICATED_TELEMETRY",tag)
                labels[tag]=json.loads(body)
            elif tag=="DELTAX_ALIAS":
                e=json.loads(body)
                validate_alias(e,original)
                assert e["installed"]==(mode=="deltax-guard" or
                                       mode.startswith("deltax-signal-"))
                alias.append(e)
            elif tag=="DELTAX_CAUSAL_PROPAGATION":
                causes.append(json.loads(body))
            elif tag=="DELTAX_SIGNAL_EVENT":
                signal_events.append(json.loads(body))
            elif tag=="DELTA2_WITNESS":
                w=json.loads(body)
                check_witness(w)
                assert all(canon(c) in original for side in ("left","right")
                           for c in w[side]["cnf"]),(
                    "NON_SOURCE_WITNESS",source["name"])
        if not expired:
            assert all(k in labels for k in (
                "X41_STATS","DELTAX_STATS","DELTAX_GUARD_STATS",
                "DELTAX_GUARD_SOURCE","DELTAX_CAUSAL_STATS",
                "DELTAX_SIGNAL_STATS")),(
                "MISSING_STATS",source["name"],mode,stderr[-1100:])
        native=labels.get("X41_STATS",{})
        guard=labels.get("DELTAX_GUARD_STATS",{})
        proofguard=labels.get("DELTAX_GUARD_SOURCE",{})
        delta=labels.get("DELTAX_STATS",{})
        sig=labels.get("DELTAX_SIGNAL_STATS",{})
        causal=labels.get("DELTAX_CAUSAL_STATS",{})
        if not expired:
            assert proofguard["invalid_derivations_rejected"]==0,(
                "SOURCE_RESOLUTION_FALSE_CANDIDATE",source["name"],mode)
            assert guard["inconsistent_clones"]==0,(
                "CLONE_DISAGREEMENT",source["name"],mode)
            assert delta["mode"]==mode and sig["mode"]==mode
            if mode=="join":
                assert delta["proof_carrying_injected"]==0
                assert guard["checks"]==0 and sig["tested"]==0
            elif mode=="deltax-guard":
                assert sig["tested"]==0
                assert guard["accepted"]==delta["proof_carrying_injected"]
                assert guard["checks"]==(
                    guard["accepted"]+guard["rejected"]+guard["budget_rejections"])
            else:
                assert sig["tested"]==sig["preapproved"]+sig["vetoed"]
                assert guard["accepted"]==delta["proof_carrying_injected"]
                assert guard["checks"]==(
                    guard["accepted"]+guard["rejected"]+guard["budget_rejections"])
                assert guard["checks"]<=sig["preapproved"]
                threshold=int(mode.rsplit("-",1)[1])
                assert sig["min_reach"]==threshold
                assert all(x["min_unassigned_reach"]==threshold for x in signal_events)
                assert all(x["accepted_by_signal"]==(x["unassigned_reach"]>=threshold)
                           for x in signal_events)
            assert len(alias)<=delta["proof_carrying_injected"]
            assert len(causes)<=causal["real_enqueues_with_deltax_reason"]
            valid_alias={canon(e["forward"]) for e in alias}
            for evt in causes:
                assert canon(evt["reason_clause"]) in valid_alias
                assert evt["literal"] in evt["reason_clause"]
        verified=wall<=cap and status in ("SAT_VERIFIED","UNSAT_CERTIFIED")
        if verified:
            expected="SAT_VERIFIED" if source["expected"]=="SAT" else "UNSAT_CERTIFIED"
            assert status==expected,("GRAPH_CERTIFICATE_CONTRADICTED",
                                     source["name"],mode,status,expected)
        row={
            "name":source["name"],"graph_id":source["graph_id"],
            "family":source["family"],"split":source["split"],
            "variant":source["variant"],"source_sha256":source["sha256"],
            "mode":mode,"status":status,"verified":verified,
            "wall_s":round(wall,7),
            "decisions":native.get("decisions"),"conflicts":native.get("conflicts"),
            "guard_checks":guard.get("checks",0),
            "guard_accepted":guard.get("accepted",0),
            "guard_rejected":guard.get("rejected",0),
            "guard_budget_rejected":guard.get("budget_rejections",0),
            "proof_clauses":delta.get("proof_carrying_injected",0),
            "causal_reason_enqueues":causal.get("real_enqueues_with_deltax_reason",0),
            "signal_tested":sig.get("tested",0),
            "signal_passed":sig.get("preapproved",0),
            "signal_vetoed":sig.get("vetoed",0),
            "signal_reach_sum":sig.get("sum_unassigned_reach",0),
            "source_invalid":proofguard.get("invalid_derivations_rejected",0),
            "clone_inconsistent":guard.get("inconsistent_clones",0),
        }
        folder.mkdir(parents=True,exist_ok=True)
        if alias or signal_events or causes:
            save(folder/(source["name"]+"--"+mode+".events.json"),
                {"source_sha256":source["sha256"],
                 "aliases":alias,"signal":signal_events,"causal":causes})
        return row

def phase(split,modes,dirname):
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    records,manifest_sha=sources(split)
    output=R/dirname
    output.mkdir(parents=True,exist_ok=False)
    results=[]
    with (output/"trials.jsonl").open("w") as dest:
        for source in records:
            arms=list(modes)
            random.Random(int(source["sha256"][:16],16)).shuffle(arms)
            for mode in arms:
                row=run_one(source,mode,output/"events")
                results.append(row)
                dest.write(json.dumps(row,sort_keys=True)+"\n")
                dest.flush()
                emit("DELTAX_SIGNAL_TRIAL",{
                    "split":split,"name":row["name"],"mode":mode,
                    "status":row["status"],"decisions":row["decisions"],
                    "conflicts":row["conflicts"],"verified":row["verified"],
                    "signal_tested":row["signal_tested"],
                    "signal_vetoed":row["signal_vetoed"],
                    "guard_accepted":row["guard_accepted"]})
    expected={(s["sha256"],a) for s in records for a in modes}
    actual={(r["source_sha256"],r["mode"]) for r in results}
    assert len(results)==len(expected) and actual==expected
    outcome=collections.defaultdict(set)
    for r in results:
        if r["verified"]:outcome[r["source_sha256"]].add(r["status"])
    assert all(len(v)<=1 for v in outcome.values())
    assert not any(r["source_invalid"] or r["clone_inconsistent"] for r in results)
    stats={
        "status":"COMPLETE","split":split,"graph_groups":SIZES[split],
        "unique_cnfs":len(records),"trials":len(results),
        "source_manifest_sha256":manifest_sha,
        "modes":list(modes),"verified":sum(r["verified"] for r in results),
        "unknown":sum(not r["verified"] for r in results),
        "source_proofs_valid":True,"one_cpu":True,
        "independent_graph_split":True,"no_promotion":True,
    }
    save(output/"phase.json",stats)
    emit("DELTAX_SIGNAL_PHASE",stats)
    return results

def fit():
    rows=phase("train",("join","deltax-guard")+
           tuple("deltax-signal-"+str(t) for t in THRESHOLDS),
           "deltax_signal_train")
    by={(r["graph_id"],r["variant"],r["mode"]):r for r in rows}
    graph_ids=sorted({r["graph_id"] for r in rows})
    assert len(graph_ids)==30
    models=[]
    for threshold in THRESHOLDS:
        mode="deltax-signal-"+str(threshold)
        changes=[]
        # The statistic's independent units are GRAPHS, not 3 variants.
        for graph in graph_ids:
            decision_gain=0;conflict_gain=0;accepted=0;checks=0
            for variant in ("off","low1","high1"):
                base=by[(graph,variant,"join")]
                signal=by[(graph,variant,mode)]
                if not(base["verified"] and signal["verified"]):
                    # Incomplete pairs cannot demonstrate safe advantage.
                    decision_gain-=20;conflict_gain-=20
                    continue
                decision_gain+=max(-30,min(30,base["decisions"]-signal["decisions"]))
                conflict_gain+=max(-30,min(30,base["conflicts"]-signal["conflicts"]))
                accepted+=signal["guard_accepted"]
                checks+=signal["guard_checks"]
            changes.append({"graph":graph,"decision_gain":decision_gain,
                            "conflict_gain":conflict_gain,"accepted":accepted,
                            "checks":checks})
        positive=sum(x["decision_gain"]>0 or x["conflict_gain"]>0 for x in changes)
        negative=sum(x["decision_gain"]<0 or x["conflict_gain"]<0 for x in changes)
        # Risk-sensitive, source-level SCORE chosen on TRAIN only.
        score=(sum(x["decision_gain"]+4*x["conflict_gain"] for x in changes)
              -15*negative - 0.02*sum(x["checks"] for x in changes))
        if threshold>0 and positive==0:score-=1000
        models.append({"min_reach":threshold,"score":round(score,4),
                      "graph_gains":positive,"graph_regressions":negative,
                      "accepted_total":sum(x["accepted"] for x in changes),
                      "clone_checks":sum(x["checks"] for x in changes)})
    # Nonnegative threshold, stronger filter on score ties (less compute);
    # no validation/holdout is read at selection time.
    selected=max(models,key=lambda x:(x["score"],x["min_reach"]))
    dataset=R/"deltax_signal1_inputs"
    policy={
        "version":"SIGNAL1","status":"FROZEN_TRAIN_ONLY",
        "min_unassigned_binary_reach":selected["min_reach"],
        "feature":"number of distinct currently-unassigned variables reachable "
                  "within <=3 original-binary-implication hops from unassigned "
                  "endpoints of a source-RUP certified guarded equality",
        "training_graph_groups":30,"validation_graph_groups":15,
        "holdout_graph_groups":15,
        "train_manifest_sha256":sha(dataset/"train_manifest.json"),
        "validation_manifest_sha256":sha(dataset/"validation_manifest.json"),
        "holdout_manifest_sha256":sha(dataset/"holdout_manifest.json"),
        "source_binary_sha256":sha(BIN),
        "train_trials_sha256":sha(R/"deltax_signal_train/trials.jsonl"),
        "threshold_candidates":list(THRESHOLDS),
        "train_model_comparisons":models,
        "selection_uses_validation":False,"selection_uses_holdout":False,
        "not_promoted":True,
    }
    save(R/"deltax_signal_train/policy.json",policy)
    emit("DELTAX_SIGNAL_TRAIN_FROZEN",{
        "min_reach":selected["min_reach"],"train_score":selected["score"],
        "graph_gains":selected["graph_gains"],
        "graph_regressions":selected["graph_regressions"],
        "policy_sha256":sha(R/"deltax_signal_train/policy.json")})

def eval_split(split):
    assert split in ("validation","holdout")
    policy_file=R/"deltax_signal_train/policy.json"
    policy=json.loads(policy_file.read_text())
    assert policy["status"]=="FROZEN_TRAIN_ONLY"
    assert policy["source_binary_sha256"]==sha(BIN),("BINARY_DRIFT",split)
    assert not policy["selection_uses_validation"] and not policy["selection_uses_holdout"]
    assert policy[split+"_manifest_sha256"]==sha(
        R/"deltax_signal1_inputs"/(split+"_manifest.json"))
    threshold=policy["min_unassigned_binary_reach"]
    modes=("join","deltax-guard","deltax-signal-"+str(threshold))
    directory="deltax_signal_"+split
    rows=phase(split,modes,directory)
    by={(r["graph_id"],r["variant"],r["mode"]):r for r in rows}
    groups=sorted({r["graph_id"] for r in rows})
    wins=losses=ties=0;gain_conf=0;gain_dec=0
    for graph in groups:
        graph_dec=graph_conf=0
        for variant in ("off","low1","high1"):
            j=by[(graph,variant,"join")]
            s=by[(graph,variant,modes[2])]
            if j["verified"] and s["verified"]:
                graph_dec+=j["decisions"]-s["decisions"]
                graph_conf+=j["conflicts"]-s["conflicts"]
        if graph_dec>0 and graph_conf>=0:wins+=1
        elif graph_dec<0 or graph_conf<0:losses+=1
        else:ties+=1
        gain_dec+=graph_dec;gain_conf+=graph_conf
    result={
        "status":"COMPLETE","split":split,"policy_sha256":sha(policy_file),
        "trained_min_reach":threshold,"independent_graph_groups":len(groups),
        "verified_attempts":sum(r["verified"] for r in rows),
        "all_attempts":len(rows),"wins_graph_groups":wins,
        "regressed_graph_groups":losses,"neutral_graph_groups":ties,
        "paired_decision_gain":gain_dec,"paired_conflict_gain":gain_conf,
        "guard_approved":sum(r["guard_accepted"] for r in rows if r["mode"]==modes[2]),
        "signal_rejected":sum(r["signal_vetoed"] for r in rows if r["mode"]==modes[2]),
        "only_original_model_and_DRAT_results_counted":True,
        "no_model_selection_from_this_split":True,"no_promotion":True
    }
    save(R/directory/"summary.json",result)
    emit("DELTAX_SIGNAL_"+split.upper()+"_RESULT",result)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("stage",choices=("train","validation","holdout","smoke"))
    a=p.parse_args()
    if a.stage=="train":fit()
    elif a.stage in ("validation","holdout"):eval_split(a.stage)
    else:
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
        rows,_=sources("train")
        chosen=[next(x for x in rows if x["family"]==f and x["variant"]=="high1")
                for f in ("planted","k4","odd_wheel","even_wheel")]
        result=[run_one(s,m,R/"deltax_signal_smoke/events",1.8)
                for s in chosen for m in ("join","deltax-guard","deltax-signal-0","deltax-signal-8")]
        assert len(result)==16
        assert sum(r["verified"] for r in result)>=12
        save(R/"deltax_signal_smoke/report.json",{
             "status":"PASS","trials":len(result),
             "source_proof_errors":sum(r["source_invalid"] for r in result),
             "clone_inconsistent":sum(r["clone_inconsistent"] for r in result),
             "distinct_source_sha":len({r["source_sha256"] for r in result}),
             "original_verified":sum(r["verified"] for r in result)})
        emit("DELTAX_SIGNAL_SMOKE_PASS",{
            "trials":16,"verified":sum(r["verified"] for r in result)})
