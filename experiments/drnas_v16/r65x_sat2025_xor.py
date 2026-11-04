#!/usr/bin/env python3
"""R65x experimental real SAT2025 XOR-stratified paired replay.

Reuse 12 SHA-frozen real SAT2025 CNFs from R85 (4 exact-XOR, 8 controls).
This is method-development on previously benchmarked inputs, NOT a blind
holdout nor an official SAT Competition ranking. Original status is UNKNOWN:
SAT models are checked on original CNFs; UNSAT is NOT independently certified.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import random
import re
import subprocess
import tempfile
import time

import r28_exact_gf2_benchmark as r28
import r32p_real_satcomp26_benchmark as r32p
import r63_real2026_xor_prevalence_fallback as r63
import r64_mixed_xor_implied as r64
import r65_xor_cnf_feedback as r65
import r65c_smart_or as smart

PROTO = "DRNAS-R65X-FROZEN-SAT2025-XOR-20261104-v1"
SOURCE_PROTO = "DRNAS-R85-ABCD-FRESH-OFFICIAL2025-XOR-STRATIFIED-20261104-v1"
MODES = ("clean_kissat", "r65_feedback", "r65x_smart_or")
SHARDS = 12
REPS = 2
CAP = 40.0

def ck(test, message):
    if not test:
        raise RuntimeError("R65X_FAIL_CLOSED " + str(message))

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")

def verified_2025(worker, original, case):
    """Override R65C's official-status check (R85's labels are UNKNOWN)."""
    code = worker["proc"].poll()
    if code is None:
        return None
    ck(code in (10, 20), "Kissat exit " + str(code))
    answer = "SAT" if code == 10 else "UNSAT"
    if answer == "SAT":
        worker["out"].seek(0)
        r32p.verify_sat_witness(original, worker["out"].read())
        return answer, "SAT_original_model_verified"
    return answer, "UNSAT_Kissat_status_only_no_LRAT"

smart.verified_outcome = verified_2025

def plain(source, case, kissat, gf2, native=False, start=None, target=None):
    """Same total 40s wall cap, original SAT model check, fail-closed errors."""
    begin = time.monotonic() if start is None else start
    left = CAP - (time.monotonic() - begin)
    answer = "TIMEOUT"
    proof = "none"
    route = "timeout"
    if left > 0:
        command = ([str(gf2), str(source), str(kissat)] if native
                   else [str(kissat), str(target or source)])
        try:
            result = subprocess.run(command, capture_output=True, text=True,
                                    errors="replace", timeout=left,
                                    preexec_fn=r63.child)
            ck(result.returncode in (10, 20),
               "unexpected Kissat/native exit " + str(result.returncode) +
               " " + result.stderr[-250:])
            answer = "SAT" if result.returncode == 10 else "UNSAT"
            route = "plain_original" if target is None else "augmented_certified"
            if native:
                marks = re.findall(r"^c R28_ROUTE (\\S+)", result.stdout, re.M)
                ck(len(marks) == 1, "missing native route")
                route = marks[0]
                ck(route in ("fallback", "certified_pure_xor_sat",
                             "certified_xor_contradiction"), "invalid native route")
                if route == "certified_pure_xor_sat":
                    ck(case["supported"] and case["pure_exact_xor"],
                       "native positive certificate without independently exact XOR")
                if route == "certified_xor_contradiction":
                    ck(case["supported"] and case["complete_blocks"] > 0,
                       "native contradiction on unsupported parity")
                    _, clauses = r28.load_clauses(source)
                    ck(r28.check_gf2_unsat_proof(result.stdout, clauses),
                       "independent native GF2 contradiction proof failed")
                    proof = "GF2_independently_verified"
            if answer == "SAT":
                r32p.verify_sat_witness(source, result.stdout)
                proof = "SAT_original_model_verified"
            elif proof == "none":
                proof = "UNSAT_Kissat_status_only_no_LRAT"
        except subprocess.TimeoutExpired:
            pass
    elapsed = time.monotonic() - begin
    if elapsed > CAP:
        answer, proof, route = "TIMEOUT", "none", "censored_over_wall_cap"
    wall = min(elapsed, CAP)
    return dict(answer=answer, wall_s=round(wall, 6),
                par2_s=round(wall if answer != "TIMEOUT" else 2*CAP, 6),
                native_route=route, proof=proof)

def old_r65(source, case, kissat, gf2):
    """Unmodified R65 implication policy, adapted only for UNKNOWN 2025 label."""
    begin = time.monotonic()
    if case["supported"] and case["pure_exact_xor"]:
        ans = plain(source, case, kissat, gf2, native=True, start=begin)
        ans.update(preprocess_s=0.0, added_clauses=0, probes=0)
        return ans
    derived = []
    info = {"route":"skip", "probes":0}
    if case["supported"] and case["complete_blocks"]:
        try:
            derived, info = r65.derive_for_source(
                source, case, begin + r65.MAX_PREP_S)
        except (r65.ProbeBudget, TimeoutError):
            derived, info = [], {"route":"budget_fallback", "probes":0}
    prep = time.monotonic() - begin
    if prep > r65.MAX_PREP_S:
        derived, info = [], {"route":"budget_fallback", "probes":0}
    with tempfile.TemporaryDirectory(prefix="r65x-2025-") as work:
        target = None
        if derived:
            target = Path(work) / "augmented.cnf"
            r64.augment(source, target, case["variables"], case["clauses"], derived)
        ans = plain(source, case, kissat, gf2, start=begin, target=target)
    ans.update(preprocess_s=round(prep, 6), added_clauses=len(derived),
               probes=info.get("probes", 0))
    return ans

def new_r65x(source, case, kissat, gf2):
    if case["supported"] and case["pure_exact_xor"]:
        ans = plain(source, case, kissat, gf2, native=True)
        ans.update(policy="cooperative_only", dispatch="gf2_pure",
                   workers_started=1, winner="r65_exact_gf2",
                   preprocess_s=0.0, added_clauses=0, signal_score=0.0,
                   probes=0)
        return ans
    return smart.smart_one(source, case, kissat, gf2)

def selftest():
    smart.selftest()
    ck(MODES[0] == "clean_kissat" and len(MODES) == 3,
       "paired modes drift")
    print("R65X_2025_SOUNDNESS_SELFTEST_PASS", flush=True)

def freeze(args):
    root = Path(args.sources)
    old = json.loads((root / "manifest.json").read_text())
    ck(old["protocol"] == SOURCE_PROTO and len(old["cases"]) == 12,
       "expected frozen R85 12 original SAT2025 CNFs")
    cases = old["cases"]
    ck(sum(int(c["structural_xor_positive"]) for c in cases) == 4,
       "R85 exact XOR-positive structural cohort drift")
    ck(all(c["year"] == 2025 and c["official_status"] == "UNKNOWN"
           and not c["source_verified_status"] for c in cases),
       "unexpected source status or year")
    ck(len({c["sha256"] for c in cases}) == 12, "duplicate original SHA")
    for c in cases:
        path = root / c["filename"]
        ck(sha(path) == c["sha256"], "original CNF SHA mismatch")
        check = r63.inspect_exact_xor(path, c["variables"], c["clauses"])
        ck(check["supported"] == c["supported"] and
           check["complete_blocks"] == c["complete_blocks"] and
           check["pure_exact_xor"] == c["pure_exact_xor"] and
           check["partial_support_groups"] == c["partial_support_groups"],
           "recomputed structural features changed")
        ck(bool(check["complete_blocks"]) == bool(c["structural_xor_positive"]),
           "positive/negative split changed")
    spec = dict(protocol=PROTO, source_protocol=SOURCE_PROTO,
                source_manifest_sha=sha(root / "manifest.json"),
                source_run_id=41769665589, selection="Frozen R85: four proven exact XOR CNFs and eight structural controls; no outcome-based reselection",
                modes=MODES, shards=SHARDS, repeats=REPS, cap_s=CAP,
                groups={"xor_exact":4, "control":8},
                cases=cases,
                limitations=["R85 source cohort already benchmarked; NOT blind holdout",
                  "2015? No: exactly SAT Competition 2025 original CNFs from frozen GBD source URLs",
                  "2025 official SAT/UNSAT status unavailable; SAT original model verified, UNSAT no LRAT",
                  "Positive XOR group deliberately enriched, not representative of the 2025 competition",
                  "Both R65x workers share one CPU and 40s end-to-end limit",
                  "Stock Kissat exchange at launch only; no live learnt-clause API"])
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    save(out / "manifest.json", spec)
    print("R65X_2025_FREEZE_PASS", json.dumps({
        "sources":12, "xor_exact":4, "control":8,
        "sha":spec["source_manifest_sha"]}), flush=True)

def measure(args):
    sources = Path(args.sources)
    spec = json.loads((Path(args.spec) / "manifest.json").read_text())
    ck(spec["protocol"] == PROTO and
       spec["source_manifest_sha"] == sha(sources / "manifest.json"),
       "protocol/source-manifest drift")
    ck(0 <= args.shard < SHARDS, "shard out of range")
    if hasattr(os, "sched_setaffinity"):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    kissat = Path(args.kissat).resolve()
    gf2 = Path(args.gf2).resolve()
    ck(kissat.is_file() and gf2.is_file(), "pinned binaries missing")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    case = spec["cases"][args.shard]
    source = (sources / case["filename"]).resolve()
    ck(sha(source) == case["sha256"], "source tampered")
    save(out / "meta.json", dict(protocol=PROTO, shard=args.shard,
         source_manifest_sha=sha(sources / "manifest.json"),
         spec_sha=sha(Path(args.spec) / "manifest.json"),
         kissat_sha=sha(kissat), gf2_sha=sha(gf2), core_count=1))
    rows = []
    for rep in range(REPS):
        order = list(MODES)
        seed = hashlib.sha256((PROTO + case["sha256"] + str(rep)).encode()).hexdigest()
        random.Random(int(seed,16)).shuffle(order)
        for mode in order:
            if mode == "clean_kissat":
                result = plain(source, case, kissat, gf2)
            elif mode == "r65_feedback":
                result = old_r65(source, case, kissat, gf2)
            else:
                result = new_r65x(source, case, kissat, gf2)
            row = dict(gbd=case["gbd"], source_sha=case["sha256"],
                       group=case["group"], rep=rep, mode=mode, **result)
            rows.append(row)
            save(out / "rows.json", rows)
            print("R65X_2025_TRIAL", case["gbd"], case["group"],
                  rep, mode, result["answer"], "wall", result["wall_s"],
                  "PAR2", result["par2_s"], result.get("native_route"),
                  flush=True)
    ck(len(rows) == REPS*len(MODES), "shard incomplete")
    print("R65X_2025_SHARD_PASS", args.shard, len(rows), flush=True)

def audit(args):
    spec = json.loads((Path(args.spec) / "manifest.json").read_text())
    ck(spec["protocol"] == PROTO and len(spec["cases"]) == SHARDS,
       "invalid source freeze")
    rows = []
    pins = set()
    for i,c in enumerate(spec["cases"]):
        folder = Path(args.combined) / ("r65x-shard-" + str(i)) / "results"
        meta = json.loads((folder / "meta.json").read_text())
        ck(meta["protocol"] == PROTO and meta["shard"] == i and
           meta["spec_sha"] == sha(Path(args.spec) / "manifest.json") and
           meta["source_manifest_sha"] == spec["source_manifest_sha"] and
           meta["core_count"] == 1, "metadata drift")
        pins.add((meta["kissat_sha"], meta["gf2_sha"]))
        part = json.loads((folder / "rows.json").read_text())
        ck(len(part) == len(MODES)*REPS, "missing shard trials")
        for rep in range(REPS):
            one = [r for r in part if r["rep"] == rep]
            ck({r["mode"] for r in one} == set(MODES), "missing paired mode")
            ck(all(r["source_sha"] == c["sha256"] and
                   r["gbd"] == c["gbd"] and r["group"] == c["group"]
                   for r in one), "source or group mismatch")
            known = {r["answer"] for r in one if r["answer"] != "TIMEOUT"}
            ck(len(known) <= 1, "disagreeing SAT/UNSAT answers")
        rows.extend(part)
    ck(len(pins) == 1 and len(rows) == SHARDS*REPS*len(MODES),
       "binary drift or missing trials")
    groups = {}
    for name in ("ALL","xor_exact","control"):
        chosen = [r for r in rows if name == "ALL" or r["group"] == name]
        stats = {}
        for mode in MODES:
            arr = [r for r in chosen if r["mode"] == mode]
            stats[mode] = dict(trials=len(arr),
                solved=sum(r["answer"] != "TIMEOUT" for r in arr),
                par2_s=round(sum(r["par2_s"] for r in arr),6))
        base = stats["clean_kissat"]["par2_s"]
        stats["gain_pct"] = round(100*(1-stats["r65x_smart_or"]["par2_s"]/base),4)
        groups[name] = stats
    per_formula = []
    for c in spec["cases"]:
        rr = [r for r in rows if r["source_sha"] == c["sha256"]]
        per_formula.append(dict(gbd=c["gbd"], sha256=c["sha256"],
            group=c["group"], blocks=c["complete_blocks"],
            coverage=c["coverage_fraction"],
            par2={m:round(sum(r["par2_s"] for r in rr if r["mode"]==m),6)
                  for m in MODES},
            dispatch=dict(collections.Counter(
                r.get("dispatch","") for r in rr if r["mode"]=="r65x_smart_or"))))
    report = dict(protocol=PROTO,status="PASS_DEVELOPMENT_REPLAY",
        trials=len(rows), source_count=SHARDS, total_cpu_cores=1,
        source_manifest_sha=spec["source_manifest_sha"],
        groups=groups, per_formula=per_formula,
        warnings=spec["limitations"])
    save(args.json, report)
    lines = ["# R65x real SAT2025 XOR-related formulas", "",
             "**Development replay on R85's 12 previously tested 2025 CNFs; NOT blind holdout.**",
             "40s total per run, one CPU, PAR2 timeout=80s. UNSAT is unverified by LRAT.",
             "", "| Group | Kissat PAR2 | R65 PAR2 | R65x PAR2 | R65x gain |",
             "|---|---:|---:|---:|---:|"]
    for g,stats in groups.items():
        p=[stats[m]["par2_s"] for m in MODES]
        lines.append(f"| {g} | {p[0]:.3f}s | {p[1]:.3f}s | {p[2]:.3f}s | {stats['gain_pct']:+.3f}% |")
    lines += ["", "| GBD | Group | XOR blocks | Kissat | R65 | R65x |",
              "|---|---|---:|---:|---:|---:|"]
    for x in per_formula:
        p=[x["par2"][m] for m in MODES]
        lines.append(f"| {x['gbd'][:12]} | {x['group']} | {x['blocks']} | {p[0]:.3f}s | {p[1]:.3f}s | {p[2]:.3f}s |")
    lines += ["", "## Limitations"] + ["- "+m for m in spec["limitations"]]
    Path(args.md).write_text("\n".join(lines)+"\n")
    print("R65X_2025_FINAL_AUDIT_PASS",json.dumps(
        {"trials":len(rows),"groups":groups},sort_keys=True),flush=True)

def main():
    parser=argparse.ArgumentParser()
    subs=parser.add_subparsers(dest="cmd",required=True)
    subs.add_parser("selftest")
    f=subs.add_parser("freeze")
    f.add_argument("--sources",required=True)
    f.add_argument("--out",required=True)
    m=subs.add_parser("measure")
    for arg in ("sources","spec","kissat","gf2","out"):
        m.add_argument("--"+arg,required=True)
    m.add_argument("--shard",type=int,required=True)
    a=subs.add_parser("audit")
    for arg in ("spec","combined","json","md"):
        a.add_argument("--"+arg,required=True)
    args=parser.parse_args()
    {"selftest":selftest,
     "freeze":lambda:freeze(args),
     "measure":lambda:measure(args),
     "audit":lambda:audit(args)}[args.cmd]()

if __name__=="__main__":
    main()
