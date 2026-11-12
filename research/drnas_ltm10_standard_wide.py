#!/usr/bin/env python3
"""DRNAS LTM10 WIDE: 300 source-disjoint synthetic CNFs, 6 native/reference arms.
Single CPU, paired E2E, 3 reps; report SAT witnesses and unverified UNSAT separately.
Frozen policy learned ONLY on the separate training indices 501..504.
"""
import hashlib
import json
import os
import pathlib
import resource
import shutil
import statistics
import subprocess
import time
from collections import defaultdict

import drnas_atlas13_generator as G
import drnas_ltm10_adaptive as A
import drnas_ltm9_wide as W

ROOT = pathlib.Path("ltm10_standard_wide")
CAP = 8.0
SEEDS = (17, 29, 43)
ARMS = ("LTM8_FAST", "LTM9_FAST", "LTM10_LEARNED",
        "Kissat", "CryptoMiniSat", "CaDiCaL")
TRAIN_INDICES = (501, 502, 503, 504)
TEST_INDICES = tuple(range(701, 731))
PREVIOUS_INDICES = (93, 94, 211, 212, *range(311, 321), *TRAIN_INDICES, *range(601, 611))

def obj(n, clauses, family, idx, cases_dir):
    raw = A.cnf(n, clauses)
    sha = hashlib.sha256(raw).hexdigest()
    path = cases_dir / (sha + ".cnf")
    path.write_bytes(raw)
    return dict(n=n, clauses=clauses, family=family, index=idx,
                sha256=sha, path=path, bucket=A.features(n, clauses))

def make_cases(indices, out_dir):
    return [obj(*G.build(f, i)[:2], f, i, out_dir)
            for f in G.CATEGORIES for i in indices]

def execute(arm, case, policy, seed, cap=CAP):
    # Native solvers inherit the same singleton affinity; external solvers use one thread.
    if arm == "LTM10_LEARNED":
        command = [A.BIN, str(case["path"]), "--mode", "LTM8_FAST",
                   "--time", str(cap), "--seed", str(seed),
                   "--policy", A.POLICIES[policy]]
    else:
        command = W.command(arm, case["path"], cap, seed)
    env = dict(os.environ, DRNAS_LTM8_MEMORY="", OMP_NUM_THREADS="1",
               OPENBLAS_NUM_THREADS="1", MKL_NUM_THREADS="1")
    start = time.monotonic()
    output = ""
    errors = ""
    try:
        p = subprocess.run(command, capture_output=True, text=True, timeout=cap,
                           env=env, preexec_fn=lambda: resource.setrlimit(
                               resource.RLIMIT_AS, (3*1024**3, 3*1024**3)))
        rc, output, errors = p.returncode, p.stdout, p.stderr
    except subprocess.TimeoutExpired:
        rc = 124
    elapsed = time.monotonic() - start
    if rc == 10:
        status = "SAT_VERIFIED" if A.witness_ok(case["n"],case["clauses"],output) else "INVALID_SAT"
    elif rc == 20:
        status = "UNSAT_UNVERIFIED"
    elif rc == 124:
        status = "TIMEOUT"
    elif rc == 0:
        status = "UNKNOWN"
    else:
        status = "ERROR"
    return dict(arm=arm, family=case["family"], index=case["index"],
                sha256=case["sha256"], seed=seed, policy=policy,
                status=status, returncode=rc,
                e2e_s=round(elapsed,6),
                PAR2_reported_s=round(elapsed if status in ("SAT_VERIFIED","UNSAT_UNVERIFIED") else 2*cap,6),
                PAR2_verified_s=round(elapsed if status=="SAT_VERIFIED" else 2*cap,6),
                php_marker=("LTM9_PHP_CERT" in output),
                diagnostics=(output+errors)[-1000:] if status in ("INVALID_SAT","ERROR") else "")

def get_memory(train, root):
    evidence = defaultdict(lambda:defaultdict(list))
    with (root/"training.jsonl").open("w") as log:
        for c in train:
            for name, policy in A.POLICIES.items():
                r=execute("LTM10_LEARNED",c,name,17,cap=2.0)
                record=dict(stage="TRAIN",sha256=c["sha256"],bucket=c["bucket"],**r)
                log.write(json.dumps(record)+"\n")
                if r["status"] in ("INVALID_SAT","ERROR"):
                    raise RuntimeError("Invalid training result: "+str(record))
                evidence[c["bucket"]][name].append(r["PAR2_reported_s"])
    memory={}
    for bucket, arms in evidence.items():
        medians={name:round(statistics.median(v),6) for name,v in arms.items() if len(v)>=3}
        baseline=statistics.median(arms["conservative"])
        best=min(medians,key=medians.get) if medians else "conservative"
        chosen=best if best!="conservative" and medians[best]<.9*baseline else "conservative"
        memory[bucket]=dict(policy=chosen,observations=len(arms["conservative"]),medians=medians)
    (root/"frozen_memory.json").write_text(json.dumps(memory,indent=2,sort_keys=True))
    return memory

def stats(rows):
    x={}
    for arm in ARMS:
        subset=[r for r in rows if r["arm"]==arm]
        x[arm]=dict(trials=len(subset),
             solved_reported=sum(r["status"] in ("SAT_VERIFIED","UNSAT_UNVERIFIED") for r in subset),
             SAT_verified=sum(r["status"]=="SAT_VERIFIED" for r in subset),
             UNSAT_unverified=sum(r["status"]=="UNSAT_UNVERIFIED" for r in subset),
             timeout=sum(r["status"]=="TIMEOUT" for r in subset),
             unknown=sum(r["status"]=="UNKNOWN" for r in subset),
             errors=sum(r["status"] in ("INVALID_SAT","ERROR") for r in subset),
             php_markers=sum(r["php_marker"] for r in subset),
             total_e2e_s=round(sum(r["e2e_s"] for r in subset),6),
             PAR2_reported_s=round(sum(r["PAR2_reported_s"] for r in subset),6),
             PAR2_verified_s=round(sum(r["PAR2_verified_s"] for r in subset),6))
    return x

def main():
    core = min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{core})
    for name in ("kissat","cryptominisat5","cadical",A.BIN,"mre_atlas23/bin/drnas_ltm8_base"):
        if name in ("kissat","cryptominisat5","cadical"):
            assert shutil.which(name), "Missing reference: "+name
        else:
            assert pathlib.Path(name).is_file(), "Missing native solver: "+name
    if ROOT.exists():
        raise RuntimeError("Output folder exists; refusing to reuse holdout or memory")
    ROOT.mkdir(); cdir=ROOT/"cases"; cdir.mkdir()
    train=make_cases(TRAIN_INDICES,cdir)
    test=make_cases(TEST_INDICES,cdir)
    prior=make_cases(PREVIOUS_INDICES,cdir)
    train_sha={c["sha256"] for c in train}
    test_sha={c["sha256"] for c in test}
    prior_sha={c["sha256"] for c in prior}
    assert len(train_sha)==40
    assert len(test_sha)==300
    assert not test_sha & train_sha
    # 'prior' intentionally includes training indices, but not new held-out indices.
    assert not test_sha & prior_sha
    memory=get_memory(train,ROOT)
    manifest=dict(source="ATLAS13 synthetic generator (NOT official SAT Competition)",
       source_indices=list(TEST_INDICES), test_unique=len(test_sha),
       training_indices=list(TRAIN_INDICES), train_unique=len(train_sha),
       historical_overlap_sha_count=len(test_sha & prior_sha),
       cap_s=CAP, repeat_seeds=SEEDS, logical_cpus=1, cpu_affinity=core,
       arms=ARMS, fixed_baseline_policy="1.0,0.85",
       CMS_seed="default (repetition for timing only)",
       independent_UNSAT_proof=False,
       note="SAT witness checked against original CNF; UNSAT return codes not independent proof; frozen strategy before holdout. SHA disjointness does not prove semantic novelty.",
       training=[dict(family=c["family"],index=c["index"],sha256=c["sha256"]) for c in train],
       holdout=[dict(family=c["family"],index=c["index"],sha256=c["sha256"]) for c in test])
    (ROOT/"manifest.json").write_text(json.dumps(manifest,indent=2))
    # Remove generated CNFs: manifest identifies deterministic reproducible input SHA.
    for p in cdir.glob("*.cnf"):
        if p.stem not in train_sha and p.stem not in test_sha:
            p.unlink()
    rows=[]; claims={}; disagreements=[];bad=[]
    with (ROOT/"results.jsonl").open("w") as log:
        for ci,c in enumerate(test):
            choice=memory.get(c["bucket"],{}).get("policy","conservative")
            for rep,seed in enumerate(SEEDS):
                offset=(ci+rep)%len(ARMS)
                for arm in ARMS[offset:]+ARMS[:offset]:
                    r=execute(arm,c,choice if arm=="LTM10_LEARNED" else "conservative",seed)
                    r["rep"]=rep
                    r["shard"]=(c["index"]-TEST_INDICES[0])//5
                    rows.append(r)
                    log.write(json.dumps(r)+"\n")
                    if r["status"] in ("INVALID_SAT","ERROR"):
                        bad.append(r)
                    if r["status"] in ("SAT_VERIFIED","UNSAT_UNVERIFIED"):
                        this_claim="SAT" if r["status"]=="SAT_VERIFIED" else "UNSAT"
                        previous=claims.setdefault(c["sha256"],this_claim)
                        if previous!=this_claim:disagreements.append(r)
            if (ci+1)%25==0:
                log.flush()
                print("LTM10_WIDE_PROGRESS",json.dumps(dict(cases_done=ci+1,trials_done=len(rows))),flush=True)
    totals=stats(rows)
    ref_to_ltm10={ref:round(totals[ref]["PAR2_reported_s"]/max(1e-9,totals["LTM10_LEARNED"]["PAR2_reported_s"]),4)
                  for ref in ARMS if ref!="LTM10_LEARNED"}
    groups={f:stats([r for r in rows if r["family"]==f]) for f in G.CATEGORIES}
    shards={str(sh):stats([r for r in rows if r["shard"]==sh]) for sh in range(6)}
    paired={}
    for r in rows:
        paired.setdefault((r["sha256"],r["rep"]),{})[r["arm"]]=r
    regressions=[]
    for key,arms in paired.items():
        a=arms["LTM9_FAST"]["PAR2_reported_s"];b=arms["LTM10_LEARNED"]["PAR2_reported_s"]
        regressions.append(dict(sha256=key[0],rep=key[1],LTM9_PAR2=a,LTM10_PAR2=b,delta_s=round(b-a,6)))
    worst=sorted(regressions,key=lambda x:x["delta_s"],reverse=True)[:12]
    result=dict(totals=totals,families=groups,shards=shards,reference_to_LTM10_reported_PAR2_ratios=ref_to_ltm10,
                greatest_LTM10_regressions=worst,selected_policies={k:v["policy"] for k,v in memory.items()},
                training_unique=40,test_unique=300,paired_trials=len(rows),
                discrepancies=len(disagreements),invalid=len(bad),
                independent_UNSAT_proof=False,
                note="Experimental synthetic-only results. UNSAT returns unverified unless independently certified.")
    (ROOT/"summary.json").write_text(json.dumps(result,indent=2))
    print("LTM10_WIDE_FINAL",json.dumps(dict(totals=totals,
          reference_to_LTM10_reported_PAR2_ratios=ref_to_ltm10,
          selected_policies=result["selected_policies"],discrepancies=len(disagreements),
          invalid=len(bad))),flush=True)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as out:
            out.write("300 synthetic SHA-disjoint CNFs × 3 repeats × 6 arms = 5400 E2E trials; one logical CPU; 8-second cap per trial. Train 40 additional SHA-disjoint CNFs.\\n\\n")
            out.write("| Solver | Reported solved | SAT checked | UNSAT unverified | Timeouts | PAR2 reported (s) | PAR2 verified (s) |\\n|---|---:|---:|---:|---:|---:|---:|\\n")
            for arm,s in totals.items():
                out.write(f"| {arm} | {s['solved_reported']}/{s['trials']} | {s['SAT_verified']} | {s['UNSAT_unverified']} | {s['timeout']} | {s['PAR2_reported_s']:.4f} | {s['PAR2_verified_s']:.4f} |\\n")
            out.write("\\n**UNSAT returns not independently proof-verified.** Reported PAR2 is exploratory; verify columns before claiming solver superiority.\\n")
    if disagreements or bad:
        raise RuntimeError(f"Invalid SAT or cross-solver contradiction: invalid={len(bad)} disagree={len(disagreements)}")
if __name__=="__main__":
    main()
