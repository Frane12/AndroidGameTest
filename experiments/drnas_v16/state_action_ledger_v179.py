#!/usr/bin/env python3
"""DRNAS scientific experiment protocol v1: OBSERVED STATE -> ACTION -> FEEDBACK -> OUTCOME.

Use this module for every SAT experiment. It records precise inputs, environment,
interventions, measured checkpoints and outcomes without claiming that the
observed state exhausts the complete internal state of Kissat.

Mathematical statements are either verified invariants or *falsifiable*
hypotheses. TIMEOUT is not UNSAT. Wall time is not deterministic.
New indicators go in namespaced, versioned extensions; raw events are kept.
"""
from __future__ import annotations
from collections import defaultdict
import hashlib,json,statistics
from pathlib import Path

SCHEMA="drnas.state_action_outcome.v1"
VALID_STATUSES={"SAT","UNSAT","TIMEOUT"}

def canonical(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"),
                      ensure_ascii=False,allow_nan=False)

def sha(obj):
    return hashlib.sha256(canonical(obj).encode("utf8")).hexdigest()

def make_record(*,run,case,environment,action,observation,feedback,outcome,
                extensions=None,hypothesis=None):
    if not case.get("cnf_sha256") or not environment.get("solver_sha256"):
        raise ValueError("Missing immutable CNF or solver digest")
    if outcome.get("status") not in VALID_STATUSES:
        raise ValueError("Outcome must be SAT, UNSAT or TIMEOUT")
    if not isinstance(feedback,list) or not isinstance(observation,dict):
        raise ValueError("Events must be structured")
    if any(e.get("signal") not in {"CONTINUE","ROLLBACK"} for e in feedback):
        raise ValueError("Unknown feedback action")
    ext=extensions if extensions is not None else {}
    if not isinstance(ext,dict) or any("." not in key for key in ext):
        raise ValueError("Extensions require namespaced keys like 'lbd.window256'")
    if outcome["status"]=="UNSAT" and outcome.get("proof_verified") is None:
        outcome={**outcome,"proof_verified":False}
    if outcome["status"]=="SAT" and outcome.get("witness_verified") is not True:
        raise ValueError("A SAT claim requires verified satisfying assignment")
    if hypothesis is not None and (
            "prediction" not in hypothesis or "falsified_when" not in hypothesis):
        raise ValueError("Hypotheses must preregister predictions and falsifiers")
    # These are observable fingerprints, not a hash of all solver internal state.
    input_observed={
      "cnf_sha256":case["cnf_sha256"],
      "solver_sha256":environment["solver_sha256"],
      "nvars":case.get("nvars"),
      "density":case.get("density"),
      "seed":case.get("seed")}
    record={
      "schema_version":SCHEMA,
      "run":run,
      "case":case,
      "environment":environment,
      "action":action,
      "observation":observation,
      "feedback":feedback,
      "outcome":outcome,
      "hypothesis":hypothesis,
      "extensions":ext,
      "fingerprints":{
        "input":sha(input_observed),
        "environment":sha(environment),
        "action":sha(action),
        "checkpoint":sha(observation) if observation else None,
        "observed_trace":sha({"observations":observation,
                              "feedback":feedback,
                              "status":outcome["status"],
                              "final_conflicts":outcome.get("final_conflicts"),
                              "final_restarts":outcome.get("final_restarts")})},
      "limits":{
        "observed_state_is_complete":False,
        "wall_time_deterministic":False,
        "timeout_is_proof_of_unsat":False,
        "unsat_requires_independent_proof":True,
        "rollback_rewinds_solver_state":False},
    }
    return record

def append_jsonl(path,record):
    if record.get("schema_version")!=SCHEMA:
        raise ValueError("Schema mismatch")
    with Path(path).open("a",encoding="utf8") as f:
        f.write(canonical(record)+"\n")

def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]

def audit(records,*,ratio=1.5,min_delta_seconds=0.15):
    records=list(records)
    buckets=defaultdict(list)
    for r in records:
        if r["schema_version"]!=SCHEMA:raise ValueError("Unknown schema")
        fp=r["fingerprints"]
        buckets[(fp["input"],fp["environment"],fp["action"])].append(r)
    issues=[]
    replay_groups=0
    for key,group in buckets.items():
        if len(group)<2:continue
        replay_groups+=1
        status={r["outcome"]["status"] for r in group}
        runs=[r["run"] for r in group]
        if "SAT" in status and "UNSAT" in status:
            issues.append({"kind":"contradictory_sat_unsat",
                 "severity":"critical","runs":runs,
                 "meaning":"Check witness, UNSAT proof and input identity."})
        if "TIMEOUT" in status and ({"SAT","UNSAT"} & status):
            issues.append({"kind":"different_timeout_outcome",
                 "severity":"investigate","runs":runs,
                 "meaning":"CPU scheduling, exact budget or solver trajectory may differ."})
        early={r["fingerprints"]["checkpoint"] for r in group}
        if len(early)>1:
            issues.append({"kind":"observed_checkpoint_divergence",
                 "severity":"investigate","runs":runs,
                 "meaning":"Same declared inputs/action but different observed checkpoints: inspect internal state and parser."})
        completed=[r for r in group if r["outcome"]["status"] in ("SAT","UNSAT")]
        if len(completed)>=2:
            times=[float(r["outcome"]["seconds"]) for r in completed]
            if min(times)>0 and max(times)/min(times)>ratio and max(times)-min(times)>=min_delta_seconds:
                issues.append({"kind":"wall_time_drift","severity":"investigate",
                   "runs":runs,"min_s":min(times),"max_s":max(times),
                   "meaning":"Wall time variability does not disprove deterministic solver semantics."})
            counters={(r["outcome"].get("final_conflicts"),
                       r["outcome"].get("final_restarts")) for r in completed}
            if len(counters)>1 and all(None not in c for c in counters):
                issues.append({"kind":"search_path_divergence",
                   "severity":"investigate","runs":runs,
                   "meaning":"Solve paths/counters differ; audit seed, event ordering and internal state."})
    summaries={
      "schema_version":SCHEMA,"records":len(records),
      "same_input_environment_action_groups_with_repeats":replay_groups,
      "findings":issues,"findings_by_kind":dict((k,sum(x["kind"]==k for x in issues))
                                  for k in sorted({x["kind"] for x in issues})),
      "interpretation":"Observed equivalence never establishes complete internal state equivalence.",
      "logic":"SAT witnesses verified; UNSAT unproven without certificate; TIMEOUT inconclusive."}
    return summaries

def selftest():
    case={"cnf_sha256":"a"*64,"seed":1,"nvars":260,"density":4.26}
    environment={"solver_sha256":"b"*64,"solver_version":"kissat-4.0.4",
                 "compiler":"gcc","host":"ubuntu","cap_seconds":2.5}
    action={"mode":"baseline","restartint":1,"random_seed":"fixed"}
    obs={"checkpoint512":{"conflicts":512,"decisions":855,"propagations":21900}}
    def rec(i,status,seconds,conflicts,extra=None):
        outcome={"status":status,"seconds":seconds,"final_conflicts":conflicts,
                 "final_restarts":2,"witness_verified":status=="SAT"}
        if extra:outcome.update(extra)
        return make_record(run={"id":i,"repeat":i},case=case,
          environment=environment,action=action,observation=obs,
          feedback=[],outcome=outcome,
          hypothesis={"prediction":"same logical status for verified solver",
                      "falsified_when":"same CNF yields SAT and certified UNSAT"})
    rows=[rec(1,"SAT",0.22,550),rec(2,"SAT",1.10,550),rec(3,"TIMEOUT",2.5,None)]
    result=audit(rows)
    kinds={x["kind"] for x in result["findings"]}
    assert "wall_time_drift" in kinds and "different_timeout_outcome" in kinds
    assert "contradictory_sat_unsat" not in kinds
    assert not any(x["severity"]=="critical" for x in result["findings"])
    assert rows[0]["fingerprints"]["input"]==rows[1]["fingerprints"]["input"]
    assert rows[0]["fingerprints"]["action"]==rows[1]["fingerprints"]["action"]
    assert rows[0]["fingerprints"]["checkpoint"]==rows[1]["fingerprints"]["checkpoint"]
    try:
        make_record(run={"id":9},case=case,environment=environment,action=action,
            observation=obs,feedback=[],outcome={"status":"SAT","seconds":.1})
    except ValueError:pass
    else:raise AssertionError("SAT validation guard bypass")
    return result

if __name__=="__main__":
    print("V179_TEMPLATE_SELFTEST_PASS",canonical(selftest()))
