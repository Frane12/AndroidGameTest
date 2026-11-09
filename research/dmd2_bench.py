#!/usr/bin/env python3
"""DMD2 SHA-paired E2E benchmark: baseline, DMD1, and procedural feedback."""
import argparse
import collections
import hashlib
import json
import os
import pathlib
import random
import sys
import tempfile
import time

import dmd1_bench as d1
import dmd2_procedural as proc

PROTO = "DRNAS-DMD2-32SHA-5ARMS-2REP-6S-ONECPU-PAR2-v1"
ARMS = ("kissat_original", "dmd1_15_active", "dmd2_20_active",
        "dmd2_60_shadow", "dmd2_60_active")
CAP = 6.0
REPS = 2
SHARDS = 4
ROOT = pathlib.Path("mre_dmd2")
BIN = pathlib.Path("mre_dmd2/bin/dmd1_anf")


def need(cond, msg):
    if not cond:
        raise RuntimeError("DMD2_AUDIT_REFUSED " + msg)


def write_toy(path, n, clauses):
    path.write_text("p cnf %d %d\n" % (n, len(clauses)) +
                    "".join(" ".join(map(str, c)) + " 0\n" for c in clauses))


def bridge_cases():
    """Controls only, NOT hardcoded transformation templates."""
    toy = ROOT / "bridge"
    toy.mkdir(parents=True, exist_ok=True)
    core = [(1,-2,3), (1,2,-3), (2,3), (-2,-3)]
    models = [
        (5, core + [(-1,4),(-4,5)]),
        (8, core + [(-1,4),(-4,7),(-7,8),(5,6),(-5,-6)]),
        (10, core + [(4,-5,6),(4,5,-6),(5,6),(-5,-6),
                     (-1,7),(-4,8),(-7,-8,9),(-9,10)]),
        (7, core + [(-1,4),(-4,5),(-5,6),(-6,7),(-7,1)])
    ]
    out = []
    for i, (n, clauses) in enumerate(models):
        path = toy/("bridge-%d.cnf" % i)
        write_toy(path, n, clauses)
        out.append(dict(cohort="synthetic_procedural_control", filename=path.name,
                        sha256=d1.sha(path), path=str(path)))
    return out


def cases():
    old = d1.cases()
    need(len(old) == 28, "not DMD1 frozen 24+4 sample")
    all_cases = old + bridge_cases()
    need(len(all_cases) == 32 and
         len(set(c["sha256"] for c in all_cases)) == 32,
         "duplicates or missing sources")
    return all_cases


def run_trial(case, arm, rep):
    cpu = sorted(os.sched_getaffinity(0))[0]
    start = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="dmd2-e2e-") as td:
        tmp = pathlib.Path(td)
        original = pathlib.Path(case["path"])
        _, original_clauses = d1.read_cnf(original)
        target = original
        metrics = dict(steps_executed=0, cycles_pruned=0, added=0,
                       nonlinear_relations=0, new_bcp_units=0,
                       short_lemmas=0, proof_checked=False,
                       feedback_reward=0.0, prep_wall_s=0.0)
        if arm == "dmd1_15_active":
            aug, cert = tmp/"dmd1.cnf", tmp/"dmd1-proof.json"
            rc, out, err, _, _, timed = d1.run_process(
                [BIN, original, aug, cert, 15, 48], CAP, cpu)
            need(not timed and rc == 0 and cert.is_file(), "DMD1 failed: " + err[-300:])
            p = json.loads(cert.read_text())
            d1.proof_replay(original, aug, p)
            if p["lemmas"]:
                target = aug
            metrics.update(added=len(p["lemmas"]),
                nonlinear_relations=p["nonlinear_relations"], proof_checked=True)
        elif arm.startswith("dmd2_"):
            budget = 20 if arm == "dmd2_20_active" else 60
            aug, chain = tmp/"dmd2.cnf", tmp/"dmd2-chain.json"
            rc, out, err, _, _, timed = d1.run_process([
                sys.executable, pathlib.Path("research/dmd2_procedural.py"),
                original, aug, chain, "--max-ms", budget, "--max-steps", 3
            ], CAP, cpu)
            need(not timed and rc == 0 and chain.is_file(),
                 "DMD2 chained proof failed: " + err[-500:])
            p = json.loads(chain.read_text())
            need(p["protocol"] == proc.PROTO and
                 p["original_sha256"] == case["sha256"] and
                 p["all_step_proofs_independently_replayed"],
                 "unverified algebra chain")
            need((p["appended_lemmas"] > 0) == aug.exists(),
                 "missing or unexpected augmentation")
            if aug.exists():
                nn, cc = d1.read_cnf(aug)
                need(nn == d1.read_cnf(original)[0] and
                     cc[:len(original_clauses)] == original_clauses and
                     len(cc) - len(original_clauses) == p["appended_lemmas"],
                     "original CNF changed by DMD2")
            if arm != "dmd2_60_shadow" and p["appended_lemmas"]:
                target = aug
            metrics.update(steps_executed=p["steps_executed"],
                cycles_pruned=p["cycles_pruned"],
                added=p["appended_lemmas"],
                short_lemmas=p["short_lemmas"],
                nonlinear_relations=p["nonlinear_relations"],
                new_bcp_units=sum(s["bcp_new_units"] for s in p["steps"]),
                feedback_reward=sum(s["feedback_reward"] for s in p["steps"]),
                proof_checked=True)
        metrics["prep_wall_s"] = round(time.monotonic()-start, 6)
        remaining = CAP - (time.monotonic()-start)
        if remaining <= 0:
            status, checked, cpu_s = "TIMEOUT", False, 0
        else:
            rc, out, err, _, cpu_s, timed = d1.run_process(
                [d1.KISSAT, target], remaining, cpu)
            if timed:
                status, checked = "TIMEOUT", False
            else:
                status, checked = d1.outcome(rc, out, original_clauses)
        elapsed = time.monotonic()-start
        return dict(protocol=PROTO, arm=arm, rep=rep, cohort=case["cohort"],
            source_sha256=case["sha256"], filename=case["filename"],
            allocated_logical_cpus=1, cpu_affinity=[cpu],
            cap_s=CAP, E2E_s=round(elapsed,6),
            PAR2_s=round(elapsed if status!="TIMEOUT" else 2*CAP,6),
            status=status, SAT_original_witness_verified=checked,
            UNSAT_independent_LRAT=False, child_CPU_s=round(cpu_s,6), **metrics)


def selftest():
    ROOT.mkdir(parents=True, exist_ok=True)
    cpu=sorted(os.sched_getaffinity(0))[0]
    os.sched_setaffinity(0, {cpu})
    rnd = random.Random(917366)
    count, added, procedural = 0, 0, 0
    with tempfile.TemporaryDirectory(prefix="dmd2-test-") as td:
        work = pathlib.Path(td)
        tests = []
        tests.extend(bridge_cases())
        for i in range(48):
            n = rnd.randint(2,7)
            clauses=[]
            for _ in range(rnd.randint(3,19)):
                k = rnd.randint(1,min(4,n))
                vs=rnd.sample(range(1,n+1),k)
                clauses.append(tuple(x if rnd.getrandbits(1) else -x for x in vs))
            path=work/("r%03d.cnf"%i)
            write_toy(path,n,clauses)
            tests.append(dict(path=str(path),filename=path.name,cohort="random",
                              sha256=d1.sha(path)))
        for test in tests:
            original=pathlib.Path(test["path"])
            n,clauses=d1.read_cnf(original)
            aug,cert=work/"aug.cnf",work/"chain.json"
            aug.unlink(missing_ok=True)
            res=proc.discover(original,aug,cert,max_ms=180,max_steps=3)
            final=d1.read_cnf(aug)[1] if aug.exists() else clauses
            for m in range(1<<n):
                bits={i+1:bool(m & (1<<i)) for i in range(n)}
                need(d1.holds(clauses,bits)==d1.holds(final,bits),
                     "semantic equivalence changed: "+test["filename"])
            count+=1
            added+=res["appended_lemmas"]
            procedural+=res["steps_executed"]
    print("DMD2_SELFTEST_PASS",json.dumps(dict(exhaustively_verified_cases=count,
        checked_chain_steps=procedural, additional_lemmas=added,
        no_model_mismatch=True)),flush=True)


def bench(shard):
    need(0 <= shard < SHARDS, "bad shard")
    cs=cases()
    cpu=sorted(os.sched_getaffinity(0))[0]
    os.sched_setaffinity(0, {cpu})
    rows=[]
    for i, case in enumerate(cs):
        if i % SHARDS != shard:
            continue
        for rep in range(REPS):
            arms=list(ARMS)
            random.Random(int(case["sha256"][:12],16)+rep).shuffle(arms)
            for arm in arms:
                result=run_trial(case,arm,rep)
                rows.append(result)
                print("DMD2_TRIAL",json.dumps(result,sort_keys=True),flush=True)
    expected=(len(cs)//SHARDS)*REPS*len(ARMS)
    need(len(rows)==expected,"incomplete trial count")
    ROOT.mkdir(exist_ok=True)
    (ROOT/("shard-%d.json"%shard)).write_text(json.dumps(rows,sort_keys=True))
    print("DMD2_SHARD_PASS",shard,expected,flush=True)


def summary(rows):
    return dict(trials=len(rows), solved=sum(x["status"]!="TIMEOUT" for x in rows),
        SAT_verified=sum(x["status"]=="SAT" and x["SAT_original_witness_verified"] for x in rows),
        UNSAT_no_LRAT=sum(x["status"]=="UNSAT" for x in rows),
        PAR2_s=round(sum(x["PAR2_s"] for x in rows),5),
        E2E_s=round(sum(x["E2E_s"] for x in rows),5),
        added_lemmas=sum(x["added"] for x in rows),
        short_lemmas=sum(x["short_lemmas"] for x in rows),
        algebraic_relations=sum(x["nonlinear_relations"] for x in rows),
        derived_BCP_units=sum(x["new_bcp_units"] for x in rows),
        executed_chain_steps=sum(x["steps_executed"] for x in rows),
        sum_preprocessing_s=round(sum(x["prep_wall_s"] for x in rows),5))


def audit():
    cs=cases()
    by_sha={x["sha256"]:x for x in cs}
    rows=[]
    per_shard={}
    for shard in range(SHARDS):
        path=ROOT/("shard-%d.json"%shard)
        need(path.is_file(),"missing shard")
        current=json.loads(path.read_text())
        need(len(current)==len(cs)//SHARDS*REPS*len(ARMS),"bad shard size")
        rows.extend(current)
        per_shard[str(shard)]={arm:summary([x for x in current if x["arm"]==arm])
                              for arm in ARMS}
    expected={(x["sha256"],rep,arm) for x in cs for rep in range(REPS) for arm in ARMS}
    keyset={(x["source_sha256"],x["rep"],x["arm"]) for x in rows}
    need(len(rows)==320 and len(keyset)==320 and keyset==expected,
         "SHA paired source/arm count")
    for x in rows:
        need(x["protocol"]==PROTO and x["allocated_logical_cpus"]==1 and
             len(x["cpu_affinity"])==1 and x["cohort"]==by_sha[x["source_sha256"]]["cohort"],
             "protocol/source/core mismatch")
        need(x["status"]!="SAT" or x["SAT_original_witness_verified"],"unverified SAT")
        need(x["arm"]=="kissat_original" or x["proof_checked"],"missing algebra proof replay")
        need(abs(x["PAR2_s"]-(12.0 if x["status"]=="TIMEOUT" else x["E2E_s"]))<1e-4,
             "PAR2 mismatch")
    for c in cs:
        for rep in range(REPS):
            z=[x for x in rows if x["source_sha256"]==c["sha256"] and x["rep"]==rep]
            results=set(x["status"] for x in z if x["status"]!="TIMEOUT")
            need(len(results)<=1,"contradictory SAT / UNSAT verdict on original SHA")
    scores={arm:summary([x for x in rows if x["arm"]==arm]) for arm in ARMS}
    cohorts=sorted(set(x["cohort"] for x in rows))
    per_cohort={cohort:{arm:summary([x for x in rows
                            if x["cohort"]==cohort and x["arm"]==arm])
                            for arm in ARMS} for cohort in cohorts}
    baseline={(x["source_sha256"],x["rep"]):x for x in rows
              if x["arm"]=="kissat_original"}
    paired={}
    for arm in ARMS:
        if arm=="kissat_original":continue
        wins=losses=ties=0;speedups=[];regressions=[]
        for r in rows:
            if r["arm"]!=arm:continue
            a=baseline[(r["source_sha256"],r["rep"])]
            delta=r["PAR2_s"]-a["PAR2_s"]
            if delta < -0.01:wins+=1;speedups.append(delta)
            elif delta > 0.01:losses+=1;regressions.append(delta)
            else:ties+=1
        paired[arm]=dict(wins=wins,losses=losses,ties=ties,
                         largest_gain_s=round(min(speedups),4) if speedups else None,
                         largest_regression_s=round(max(regressions),4) if regressions else None)
    k=scores["kissat_original"]["PAR2_s"]
    output=dict(protocol=PROTO, sources=len(cs),original_cases=24,
        previously_seen_development=True, synthetic_controls=8,
        trials=320, repeats=REPS, cap_s=CAP, one_logical_cpu=True,
        SAT_witness_original=True, independent_UNSAT_LRAT=False,
        proof_chain_independent_stage_replay=True,
        PAR2_speedup_vs_kissat={arm:round(k/max(v["PAR2_s"],1e-9),6)
                                for arm,v in scores.items()},
        scores=scores,per_shard=per_shard,per_cohort=per_cohort,
        paired=paired,no_auto_promotion=True)
    (ROOT/"audit.json").write_text(json.dumps(output,sort_keys=True,indent=2))
    print("DMD2_FINAL",json.dumps(output,sort_keys=True),flush=True)


if __name__=="__main__":
    a=argparse.ArgumentParser()
    a.add_argument("action",choices=("selftest","bench","audit"))
    a.add_argument("--shard",type=int,default=0)
    opt=a.parse_args()
    try:
        if opt.action=="selftest":selftest()
        elif opt.action=="bench":bench(opt.shard)
        else:audit()
    except Exception as exc:
        print("DMD2_FATAL",str(exc),file=sys.stderr,flush=True)
        raise
