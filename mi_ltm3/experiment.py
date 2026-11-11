"""MI-LTM3 actual one-CPU native CDCL training and frozen holdout benchmark.

Training-only SQLite is carried across GitHub runs. Each run adds 192 fresh
training CNFs; holdout's 192 source SHAs remain frozen, and are NEVER written
to either training table. BASE vs MI_FORCED vs LTM_GATE is measured end-to-end
including gating, probing, conversion to CNF and native CDCL subprocess.
"""
import argparse
import hashlib
import json
import os
import statistics
import sys
import time
from collections import Counter,defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"mi_ltm1"))
from native_paired import BIN, implied_cnf, parse_model, solve
from probe import probe_cnf
from relational_memory import extract_patterns
from design import (FAMILIES,cohort,digest_manifest,dimacs,opportunity_key,
                    satisfies,source_parity_unsat)
from policy import TrainingMemory,action
from strict_runner import run_strict
from xor_multistep import closure, audit_provenance

CAP_S=3.0
REPS=2
MAX_EXTRA_CLAUSES=64
MAX_PROBE_S=.03
OUT=ROOT/"mi_ltm3"


def independently_audit_inferences(clauses,report):
    """Independently check all complete source encodings and XOR provenance.

    We do NOT use the source detector's assertion as proof. Each source row
    must have all of its parity-forbidding original CNF clauses present.
    Every delivered consequence must equal the GF(2) sum of those rows.
    """
    source={frozenset(c) for c in clauses}
    equations=report["xor_equations"]
    for eq in equations:
        variables=tuple(sorted(eq["variables"]))
        rhs=int(eq["rhs"])
        assert len(variables) in (2,3)
        for bits in range(1<<len(variables)):
            if bits.bit_count()%2==rhs:
                continue
            expected=frozenset(-v if bits&(1<<j) else v
                               for j,v in enumerate(variables))
            if expected not in source:
                raise AssertionError("False source XOR row: absent original CNF clause")
    for con in report["consequences"]:
        vars_=set()
        rhs=0
        indices=con["source_equations"]
        if not indices:
            raise AssertionError("Missing XOR provenance")
        for idx in indices:
            if not 0<=idx<len(equations):
                raise AssertionError("Out-of-range XOR proof source")
            eq=equations[idx]
            vars_.symmetric_difference_update(eq["variables"])
            rhs^=eq["rhs"]
        if sorted(vars_)!=con["variables"] or rhs!=con["rhs"]:
            raise AssertionError("Incorrect GF(2) derivation")


def run_arm(case,arm,rep,policy,tmp):
    assert arm in ("BASE","MI_FORCED","MI_CHAIN","LTM_GATE","LTM_NATIVE","LTM_NATIVE_GATE")
    start=time.perf_counter()
    if arm in ("LTM_GATE","LTM_NATIVE_GATE"):
        if not policy["positive_classes"]:
            # An empty policy cannot select an intervention. Do not scan CNF.
            key=case["feature_key"]  # offline reporting only
            active,reason="BASE","empty_policy_fast_abstain"
        else:
            key=opportunity_key(case["clauses"],case["n"])
            active,reason=action(policy,key)
    else:
        key=case["feature_key"]
        active=("LTM_NATIVE" if arm=="LTM_NATIVE" else "MI_CHAIN" if arm=="MI_CHAIN" else "MI_XOR" if arm=="MI_FORCED" else "BASE")
        reason="forced_native_diagnostic" if arm=="LTM_NATIVE" else "forced_chain" if arm=="MI_CHAIN" else "forced_probe" if arm=="MI_FORCED" else "control"
    added=[]
    detected_rows=0
    consequences=0
    probe_s=0.0
    aborted=False
    chain_ops=0
    chain_truncated=False
    chain_results=0
    if active in ("MI_XOR","MI_CHAIN"):
        before=time.perf_counter()
        report=probe_cnf(case["raw"],max_clauses=10000,
                         max_rows=96,max_width=3)
        if report["status"]=="diagnostic_only":
            independently_audit_inferences(case["clauses"],report)
            detected_rows=len(report["xor_equations"])
            candidates=list(report["consequences"])
            if active=="MI_CHAIN" and detected_rows:
                chain=closure(report["xor_equations"],max_rows=96,
                              max_steps=12000,budget_s=.010)
                chain_ops=chain["elimination_ops"]
                chain_truncated=chain["truncated"]
                for item in chain["consequences"]:
                    if not audit_provenance(report["xor_equations"],item):
                        raise AssertionError("Multi-step source provenance invalid")
                chain_results=len(chain["consequences"])
                keys={(tuple(x["variables"]),x["rhs"]) for x in candidates}
                for item in chain["consequences"]:
                    consequence_key=(tuple(item["variables"]),item["rhs"])
                    if consequence_key not in keys:
                        keys.add(consequence_key)
                        candidates.append(item)
            proof_report=dict(report,consequences=candidates)
            independently_audit_inferences(case["clauses"],proof_report)
            consequences=len(candidates)
            ordered=sorted(candidates,
                           key=lambda c:({"conflict":0,"unit":1,
                                          "binary_xor":2}.get(c["kind"],3),
                                         len(c["variables"])))
            existing={frozenset(c) for c in case["clauses"]}
            for con in ordered:
                for clause in implied_cnf(con):
                    reduced=frozenset(clause)
                    if reduced in existing:
                        continue
                    existing.add(reduced)
                    added.append(tuple(clause))
                    if len(added)>=MAX_EXTRA_CLAUSES:
                        break
                if len(added)>=MAX_EXTRA_CLAUSES:
                    break
        probe_s=time.perf_counter()-before
        if probe_s>MAX_PROBE_S or report["status"]=="abstain":
            added=[]
            aborted=True
            reason="probe_budget_abstain"
    work=case["clauses"]+added
    path=tmp/("ltm3_%s_%s_%d.cnf" % (case["family"],arm,rep))
    path.write_text(dimacs(case["n"],work))
    seed=int.from_bytes(hashlib.sha256(
        ("%s/%d" % (case["sha"],rep)).encode()).digest()[:8],"big")
    remaining=CAP_S-(time.perf_counter()-start)
    if remaining>.005:
        rc,stdout,child_s,native_reason=run_strict(
            BIN,path,seed,remaining,mode="LTM_NATIVE" if active=="LTM_NATIVE" else "A")
    else:
        rc,stdout,child_s,native_reason=0,"",0.0,"budget_exhausted"
        aborted=True
        reason="total_budget_exceeded"
    e2e=time.perf_counter()-start
    if e2e>CAP_S:
        rc,stdout=0,""
        aborted=True
        reason="total_budget_exceeded"
    expected=case["expect"]
    if rc not in (0,10,20):
        raise AssertionError(("Unexpected native process result",rc,case["sha"]))
    if rc==10:
        if expected!="SAT_PLANTED":
            raise AssertionError("Solver SAT contradicts source-certified UNSAT")
        assignments=parse_model(stdout)
        if (len(assignments)!=case["n"] or
                not satisfies(case["clauses"],assignments)):
            raise AssertionError("Invalid SAT witness on original CNF")
        status="SAT_ORIGINAL_VERIFIED"
    elif rc==20:
        if expected!="UNSAT_GF2_PROVEN":
            raise AssertionError("Solver UNSAT contradicts planted original SAT model")
        proof,rows=source_parity_unsat(case["clauses"])
        if not proof:
            raise AssertionError("Independent original-source GF2 UNSAT proof failed")
        status="UNSAT_SOURCE_GF2_VERIFIED"
    else:
        status="UNKNOWN"
    telemetry={}
    for line in stdout.splitlines():
        if line.startswith("ATLAS13_TRIAL "):
            telemetry=dict(part.split("=",1) for part in line.split()[1:]
                           if "=" in part)
    solved=status in ("SAT_ORIGINAL_VERIFIED","UNSAT_SOURCE_GF2_VERIFIED")
    return dict(family=case["family"],case=case["case"],
                generation=case["generation"],split=case["split"],
                sha256=case["sha"],variables=case["n"],
                source_clauses=len(case["clauses"]),rep=rep,arm=arm,
                action=active,reason=reason,feature_key=key,
                matched=bool(policy and key in policy["feature_classes"]),
                status=status,solved=solved,verified=solved,
                trial_audited=True,
                independent_LRAT=False,original_source_checked=True,
                e2e_s=round(e2e,7),
                par2_s=round(e2e if solved else 2*CAP_S,7),
                probe_s=round(probe_s,7),probe_aborted=aborted,
                native_runner_reason=native_reason,
                chain_ops=chain_ops,chain_truncated=chain_truncated,
                chain_consequences=chain_results,
                detected_xor_rows=detected_rows,
                derived_consequences=consequences,
                added_clauses=len(added),
                conflicts=int(telemetry.get("conflicts","0")),
                decisions=int(telemetry.get("decisions","0")),
                decision_hash=telemetry.get("ltm3_decision_hash"),
                native_branch_checks=int(telemetry.get("ltm3_branch_checks","0")),
                native_branch_overrides=int(telemetry.get("ltm3_branch_overrides","0")),
                native_exit=rc,one_logical_cpu=True)


def summary(items):
    result={}
    for arm in sorted({item["arm"] for item in items}):
        rows=[x for x in items if x["arm"]==arm]
        result[arm]=dict(trials=len(rows),solved=sum(x["solved"] for x in rows),
                         sat=sum(x["status"]=="SAT_ORIGINAL_VERIFIED" for x in rows),
                         unsat_source_proved=sum(
                             x["status"]=="UNSAT_SOURCE_GF2_VERIFIED" for x in rows),
                         unknown=sum(x["status"]=="UNKNOWN" for x in rows),
                         PAR2_s=round(sum(x["par2_s"] for x in rows),6),
                         E2E_s=round(sum(x["e2e_s"] for x in rows),6),
                         median_e2e_ms=round(statistics.median(
                             x["e2e_s"] for x in rows)*1000,4),
                         conflicts=sum(x["conflicts"] for x in rows),
                         decisions=sum(x["decisions"] for x in rows),
                         activated=sum(x["action"] in ("MI_XOR","MI_CHAIN","LTM_NATIVE") for x in rows),
                         native_branch_checks=sum(x.get("native_branch_checks",0) for x in rows),
                         native_branch_overrides=sum(x.get("native_branch_overrides",0) for x in rows),
                         matched=sum(x["matched"] for x in rows),
                         added_clauses=sum(x["added_clauses"] for x in rows),
                         probes_abstained=sum(x["probe_aborted"] for x in rows),
                         chain_ops=sum(x["chain_ops"] for x in rows),
                         chain_consequences=sum(x["chain_consequences"] for x in rows))
    return result


def paired_wins(trials,a,b):
    index={(r["sha256"],r["rep"],r["arm"]):r for r in trials}
    pairs=sorted({(r["sha256"],r["rep"]) for r in trials
                  if r["arm"]==a})
    diffs=[]
    for sha,rep in pairs:
        ar=index[(sha,rep,a)]
        br=index[(sha,rep,b)]
        diffs.append(ar["par2_s"]-br["par2_s"])
    return dict(pairs=len(diffs),b_faster=sum(d>0 for d in diffs),
                a_faster=sum(d<0 for d in diffs),
                equal=sum(d==0 for d in diffs),
                median_PAR2_saving_s=round(statistics.median(diffs),7))


def train(memory,case,results):
    by={(r["rep"],r["arm"]):r for r in results}
    for rep in range(REPS):
        base=by[(rep,"BASE")]
        force=by[(rep,"MI_CHAIN")]
        memory.insert_pair(sha=case["sha"],rep=rep,
                           generation=case["generation"],family=case["family"],
                           key=case["feature_key"],base=base,force=force)
    memory.insert_patterns(case["sha"],extract_patterns(case["raw"]))


def diagnose_templates(cases,policy):
    catalogue=policy["known_patterns"]
    details={}
    hits=Counter()
    for case in cases:
        patterns=extract_patterns(case["raw"])
        match={k:v for k,v in patterns.items() if
               k in catalogue and catalogue[k]["kind"]==v}
        entry=details.setdefault(case["family"],dict(
            formulas=0,recognized=0,pattern_matches=0,total_patterns=0))
        entry["formulas"]+=1
        entry["recognized"]+=bool(match)
        entry["pattern_matches"]+=len(match)
        entry["total_patterns"]+=len(patterns)
        hits.update(match.keys())
    return dict(by_family=details,
                recognized_holdout_formulas=sum(
                    x["recognized"] for x in details.values()),
                total_holdout_patterns=sum(
                    x["total_patterns"] for x in details.values()),
                matched_holdout_patterns=sum(
                    x["pattern_matches"] for x in details.values()),
                top_patterns=hits.most_common(20))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--smoke",action="store_true")
    parser.add_argument("--training-generation",type=int,
                        default=int(os.getenv("GITHUB_RUN_NUMBER","1")))
    args=parser.parse_args()
    if args.training_generation<1:
        raise ValueError("Training generation must be positive")
    if not BIN.exists():
        raise FileNotFoundError("Missing native standalone ATLAS15 binary")
    cases=cohort(training_generation=args.training_generation)
    train_cases=[x for x in cases if x["split"]=="train"]
    holdout_cases=[x for x in cases if x["split"]=="holdout"]
    assert {x["sha"] for x in train_cases}.isdisjoint(
        {x["sha"] for x in holdout_cases})
    digest,manifest=digest_manifest(cases)
    OUT.mkdir(exist_ok=True)
    smoke=args.smoke
    if smoke:
        train_cases=[next(x for x in train_cases if x["family"]==f)
                     for f in FAMILIES]
        holdout_cases=[next(x for x in holdout_cases if x["family"]==f)
                       for f in FAMILIES]
    dbfile=OUT/("training_smoke.sqlite" if smoke else "training.sqlite")
    mem=TrainingMemory(dbfile)
    output=[]
    with TemporaryDirectory() as temporary:
        tmp=Path(temporary)
        for count,case in enumerate(train_cases,1):
            case["feature_key"]=opportunity_key(case["clauses"],case["n"])
            rows=[]
            for rep in range(REPS):
                order=("BASE","MI_FORCED","MI_CHAIN") if rep%2==0 else (
                    "MI_CHAIN","MI_FORCED","BASE")
                for arm in order:
                    trial=run_arm(case,arm,rep,None,tmp)
                    rows.append(trial)
                    output.append(trial)
            train(mem,case,rows)
            if count%24==0 or count==len(train_cases):
                print("MI_LTM3_TRAIN_PROGRESS",count,len(train_cases),flush=True)
        holdout_sha={x["sha"] for x in holdout_cases}
        frozen=mem.freeze(holdout_sha)
        policy_path=OUT/("policy_smoke.json" if smoke else "policy_frozen.json")
        policy_path.write_text(json.dumps(frozen,indent=2,sort_keys=True))
        mem.close()
        readonly=TrainingMemory(dbfile,readonly=True)
        assert readonly.readonly
        reloaded=readonly.freeze(holdout_sha)
        assert reloaded==frozen, "Frozen policy changed on read-only reopen"
        if {x["sha"] for x in holdout_cases}&{
            r[0] for r in readonly.db.execute("SELECT formula_sha FROM pairs")}:
            raise AssertionError("Holdout data leaked into long-term memory")
        print("MI_LTM3_LEARNING",json.dumps({
            "training_runs":len(train_cases),
            "historical_train_shas":frozen["train_formula_count"],
            "feature_classes":len(frozen["feature_classes"]),
            "positive_classes":len(frozen["positive_classes"]),
            "stored_relational_patterns":len(frozen["known_patterns"]),
            "policy_sha256":frozen["sha256"]},sort_keys=True),flush=True)
        for count,case in enumerate(holdout_cases,1):
            case["feature_key"]=opportunity_key(case["clauses"],case["n"])
            for rep in range(REPS):
                arms=("BASE","LTM_GATE","MI_FORCED","MI_CHAIN") if rep%2==0 else (
                    "MI_CHAIN","MI_FORCED","LTM_GATE","BASE")
                for arm in arms:
                    output.append(run_arm(case,arm,rep,frozen,tmp))
            if count%24==0 or count==len(holdout_cases):
                print("MI_LTM3_HOLDOUT_PROGRESS",count,len(holdout_cases),
                      flush=True)
        readonly.close()
    train_trials=[x for x in output if x["split"]=="train"]
    holdout_trials=[x for x in output if x["split"]=="holdout"]
    # Separate diagnostic only: offline template discovery time is NOT included
    # in LTM_GATE E2E. The gate uses only cheap opportunity features.
    templates=diagnose_templates(holdout_cases,frozen)
    by_family={f:summary([x for x in holdout_trials if x["family"]==f])
               for f in FAMILIES}
    totals=dict(train=summary(train_trials),holdout=summary(holdout_trials),
                holdout_by_family=by_family,
                paired_forced=paired_wins(holdout_trials,"BASE","MI_FORCED"),
                paired_gated=paired_wins(holdout_trials,"BASE","LTM_GATE"),
                paired_chain=paired_wins(holdout_trials,"BASE","MI_CHAIN"))
    report=dict(project="DRNAS MI-LTM3",version=1,
                training_generation=args.training_generation,
                smoke=smoke,formula_manifest_sha=digest,
                manifest=manifest if not smoke else [],
                train_current=len(train_cases),
                holdout_current=len(holdout_cases),
                source_SHA_disjoint=True,repeats=REPS,
                cap_s=CAP_S,one_logical_cpu=True,
                policy_frozen_before_holdout=True,
                repeated_holdout_after_first_run_is_nonblind=True,
                unsat_source_GF2_checked_not_LRAT=True,
                memory_formula_count=frozen["train_formula_count"],
                memory_class_count=len(frozen["feature_classes"]),
                memory_positive_classes=len(frozen["positive_classes"]),
                template_diagnostics=templates,policy=frozen,
                summary=totals,trials=output,
                caveat=("Generated medium CNF only; no general SAT competition "
                        "claim. Separate offline template diagnosis is not "
                        "included in gating E2E. No stored formula deduction "
                        "is reused without fresh source proof."))
    report_file=ROOT/("MI_LTM3_SMOKE.json" if smoke else "MI_LTM3_FINAL.json")
    report_file.write_text(json.dumps(report,indent=2,sort_keys=True))
    print("MI_LTM3_FINAL",json.dumps({
        "train":totals["train"],"holdout":totals["holdout"],
        "paired_forced":totals["paired_forced"],
        "paired_gated":totals["paired_gated"],
        "paired_chain":totals["paired_chain"],
        "templates":templates,"policy_sha256":frozen["sha256"],
        "positive_classes":len(frozen["positive_classes"]),
        "historical_training_shas":frozen["train_formula_count"],
        "run_train_cases":len(train_cases),
        "run_holdout_cases":len(holdout_cases)},sort_keys=True),flush=True)


if __name__=="__main__":
    main()
