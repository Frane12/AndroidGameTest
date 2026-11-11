#!/usr/bin/env python3
"""ATLAS18 selective GF(2) pilot: untouched ATLAS16 native controls, fresh SHA.

Smoke source index 95, blind SHA-paired source index 96.
Never claim LRAT: GF2_UNSAT_VERIFIED is an original-CNF-derived parity core.
Includes Python gate cost in E2E and per-attempt CPU accounting.
"""
import argparse
import collections
import hashlib
import json
import pathlib
import resource
import time

import drnas_atlas_wide500 as W
import drnas_atlas_selective_gf2 as GF2
import drnas_atlas16_benchmark as B
from drnas_atlas15_benchmark import source_xors_independent

ROOT = pathlib.Path("mre_atlas18")
ROOT.mkdir(exist_ok=True)
B.ROOT = ROOT
CAP = 10.0
B.CAP = CAP
ARMS = ("A", "C6_KEEP", "C6_KEEP_GAUSS", "C6_SELECTIVE", "KISSAT", "CMS")
CATEGORIES = tuple(W.SOURCES + W.SYNTH)
REPS = 2

def cpu_total(usage):
    return usage.ru_utime + usage.ru_stime

def source_set(mode, shard):
    assert mode in ("smoke", "blind") and 0 <= shard < 4
    index = 95 if mode == "smoke" else 96
    originals = W.source_corpus(limit=97)
    result = []
    for ci, cat in enumerate(CATEGORIES):
        if mode == "blind" and ci % 4 != shard:
            continue
        if cat in originals:
            n, clauses, sha, entry = originals[cat][index]
            origin = "SATLIB-original"
        else:
            n, clauses = W.synth_one(cat, index)
            sha = hashlib.sha256(W.canonical(n, clauses)).hexdigest()
            entry = "deterministic:%s:%s" % (cat, index)
            origin = "generated"
        assert hashlib.sha256(W.canonical(n, clauses)).hexdigest() == sha
        result.append(dict(category=cat, index=index, vars=n,
                           clauses_count=len(clauses), sha256=sha,
                           entry=entry, origin=origin, clauses=clauses))
    if mode == "smoke":
        result = [result[0],
                  next(x for x in result if x["category"] == "xor_chain_unsat")]
    assert len(result) == (2 if mode == "smoke" else 5)
    assert len({x["sha256"] for x in result}) == len(result)
    # Index 96 is distinct from ATLAS16 35..84, ATLAS17 85..94,
    # and the ATLAS18 smoke-only index 95.
    assert all(x["index"] == index for x in result)
    forbidden = set()
    for filename, key in (
        ("research/atlas_wide500_memory.json", "train_samples"),
        ("research/atlas_prospective_v1_summary.json", "source_sha"),
        ("research/drnas_blocker_blind100_r3_summary.json", "source_sha256")
    ):
        p = pathlib.Path(filename)
        if p.exists():
            forbidden.update(json.loads(p.read_text()).get(key, []))
    assert not forbidden.intersection(x["sha256"] for x in result)
    return result

def selftest():
    GF2.selftest()
    contradiction = (GF2.parity_cnf((1, 2), 0)
                     + GF2.parity_cnf((2, 3), 0)
                     + GF2.parity_cnf((1, 3), 1))
    rows = source_xors_independent(contradiction)
    assert GF2.gaussian_rank(rows)[2], "independent GF2 contradiction missed"
    gate = GF2.screen(contradiction, min_rows=2, min_density=0.002)
    assert gate["gate"] == "shadow" and gate["contradiction"]
    assert GF2.screen([[1, 2, 3], [-1, 2, 3]])["gate"] == "off"
    print("ATLAS18_PROOF_GATE_SELFTEST_PASS", flush=True)

def trial(source, arm, rep, policy):
    # Each solver runs on the same unchanged canonical original CNF and seed
    # as ATLAS16. Only the new arm chooses between existing native modes.
    before_self = cpu_total(resource.getrusage(resource.RUSAGE_SELF))
    before_child = cpu_total(resource.getrusage(resource.RUSAGE_CHILDREN))
    gate = dict(gate="not_applicable", reason="control", rows=0)
    actual = arm
    gate_s = 0.0
    if arm == "C6_SELECTIVE":
        start_gate = time.monotonic()
        gate = GF2.screen(source["clauses"], max_width=5, min_rows=2,
                          min_density=0.002, max_rows=1024)
        gate_s = time.monotonic() - start_gate
        actual = "C6_KEEP_GAUSS" if gate["gate"] == "shadow" else "C6_KEEP"
    gate = dict(gate, dispatch=actual)
    old_cap = B.CAP
    try:
        # Screened arm has its predispatch cost deducted from the time cap.
        B.CAP = max(0.05, CAP - gate_s) if arm == "C6_SELECTIVE" else CAP
        r = B.run_solver(source, actual, rep, policy)
    finally:
        B.CAP = old_cap
    after_self = cpu_total(resource.getrusage(resource.RUSAGE_SELF))
    after_child = cpu_total(resource.getrusage(resource.RUSAGE_CHILDREN))
    cpu_s = max(0.0, after_child-before_child + after_self-before_self)
    r["arm"] = arm
    r["dispatch"] = actual
    r["gauss_gate"] = gate
    r["gate_wall_s"] = round(gate_s, 7)
    r["CPU_s"] = round(cpu_s, 6)
    r["E2E_s"] = round(r["E2E_s"]+gate_s, 6)
    # Always charge the exact original 2*CAP penalty, including for a
    # screened arm whose subprocess received a slightly shorter budget.
    if r["status"] in ("SAT_VERIFIED", "GF2_UNSAT_VERIFIED"):
        r["PAR2_verified_s"] = r["E2E_s"]
    else:
        r["PAR2_verified_s"] = 2*CAP
    if r["status"] != "UNKNOWN":
        r["PAR2_reported_s"] = r["E2E_s"]
    else:
        r["PAR2_reported_s"] = 2*CAP
    if r["status"] == "GF2_UNSAT_VERIFIED":
        # A second GF(2) elimination checks unsatisfiability over rows
        # reconstructed only from ORIGINAL CNF clauses, not solver claims.
        rank, dependent, contradiction = GF2.gaussian_rank(
            source_xors_independent(source["clauses"]))
        assert contradiction, "source GF2 recheck failed: " + source["sha256"]
        r["proof_audit"] = dict(kind="source_GF2_core_not_LRAT",
                                independent_parity_recheck=True,
                                rank=rank, dependent=dependent)
    else:
        r["proof_audit"] = dict(kind="none", independent_parity_recheck=False)
    assert r["UNSAT_independent_LRAT"] is False
    return r

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", required=True, choices=("smoke", "blind"))
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--selftest", action="store_true")
    args = parser.parse_args()
    selftest()
    sources = source_set(args.mode, args.shard)
    policy_path = pathlib.Path("training/ATLAS15_POLICY.txt")
    policy = policy_path.read_text().strip() if policy_path.exists() else "1.0,0.85"
    manifest = [{k:v for k,v in s.items() if k != "clauses"} for s in sources]
    manifest_sha = hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()
    print("ATLAS18_MANIFEST "+json.dumps(dict(mode=args.mode,shard=args.shard,
        sources=manifest,manifest_sha256=manifest_sha,arms=ARMS,
        cap=CAP,reps=REPS,oneCPU=True,nonblind_replay=False),sort_keys=True),flush=True)
    rows = []
    journal = ROOT/("events_%s_h%d.jsonl"%(args.mode,args.shard))
    with journal.open("w",buffering=1) as out:
        for i,source in enumerate(sources):
            for rep in range(REPS):
                rotated = list(ARMS)
                offset = (i+rep*3) % len(rotated)
                rotated = rotated[offset:]+rotated[:offset]
                by_arm = {}
                for arm in rotated:
                    r = trial(source,arm,rep,policy)
                    record = dict(mode=args.mode,shard=args.shard,**r)
                    rows.append(record)
                    by_arm[arm] = record
                    out.write(json.dumps(dict(event="trial_completed",**record),
                                         sort_keys=True)+"\n")
                    print("ATLAS18_TRIAL "+json.dumps(record,sort_keys=True),flush=True)
                statuses = {r["status"] for r in by_arm.values()}
                assert not ("SAT_VERIFIED" in statuses and
                            ("GF2_UNSAT_VERIFIED" in statuses or
                             "UNSAT_UNVERIFIED" in statuses)), (
                                "SAT/UNSAT disagreement: "+source["sha256"])
    assert len(rows)==len(sources)*REPS*len(ARMS)
    summary={}
    for arm in ARMS:
        subset=[r for r in rows if r["arm"]==arm]
        assert len(subset)==len(sources)*REPS
        summary[arm]=dict(
            trials=len(subset),
            solved=sum(r["status"] in ("SAT_VERIFIED","GF2_UNSAT_VERIFIED") for r in subset),
            SAT=sum(r["status"]=="SAT_VERIFIED" for r in subset),
            GF2_UNSAT=sum(r["status"]=="GF2_UNSAT_VERIFIED" for r in subset),
            UNSAT_unverified=sum(r["status"]=="UNSAT_UNVERIFIED" for r in subset),
            PAR2_s=round(sum(r["PAR2_verified_s"] for r in subset),4),
            PAR2_reported_s=round(sum(r["PAR2_reported_s"] for r in subset),4),
            E2E_s=round(sum(r["E2E_s"] for r in subset),4),
            CPU_s=round(sum(r["CPU_s"] for r in subset),4),
            gate_on=sum(r["gauss_gate"]["gate"]=="shadow" for r in subset),
            deleted=sum(r["native_telemetry"]["atlas15_deleted"] for r in subset),
            compactions=sum(r["native_telemetry"]["atlas16_compactions"] for r in subset),
            peak_rss_kb=max([r["native_telemetry"]["atlas16_maxrss_kb"] for r in subset] or [0]))
    audit=dict(mode=args.mode,shard=args.shard,source_manifest=manifest,
        manifest_sha256=manifest_sha,rows=rows,summary=summary,oneCPU=True,
        nonblind_replay=False,LRAT_certified=0,
        verified_GF2_is_original_source_parity_core=True)
    out_path=ROOT/("audit_%s_h%d.json"%(args.mode,args.shard))
    out_path.write_text(json.dumps(audit,sort_keys=True,indent=2))
    print("ATLAS18_FINAL "+json.dumps(dict(mode=args.mode,shard=args.shard,
        summary=summary),sort_keys=True),flush=True)

if __name__ == "__main__":
    main()
