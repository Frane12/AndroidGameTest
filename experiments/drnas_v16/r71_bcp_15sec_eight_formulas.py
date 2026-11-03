#!/usr/bin/env python3
"""R71: controlled 15s ablation on 8 SHA-frozen R67 official CNFs.

Compare unchanged pinned Kissat, full R65 implied-clause augmentation, and
filtered augmentation retaining clauses NOT *proven* by bounded original-CNF
BCP. Soundness is inherited from original R65's derivation: filtering can
only remove clauses, never add unproved ones. R68 2s diagnostics are reused
without repeating those pulses. Diagnostic replay, not a blind holdout.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import random
import tempfile
import time
from pathlib import Path

import r28_exact_gf2_benchmark as r28
import r63_real2026_xor_prevalence_fallback as r63
import r64_mixed_xor_implied as r64
import r65_xor_cnf_feedback as r65
import r68_xor_2sec_forensics as r68

PROTOCOL = "DRNAS-R71-R67-8CASE-15S-BCP-FILTER-20261103-v1"
R67_PROTOCOL = "DRNAS-R67-BLIND-STRUCTURAL-DIAGNOSTIC-20261103-v1"
MODES = ("original", "full_r65", "bcp_filtered")
REPS = 2
# Fixed R70 order seed preserves matched method order across 10s and 15s tests.
ORDER_SEED_PROTOCOL = "DRNAS-R70-R67-8CASE-10S-BCP-FILTER-20261103-v1"
CAP = 15.0
BCP_BUDGET = 2.0
SHARDS = 8


def check(ok, why):
    if not ok:
        raise RuntimeError("R71_FAIL_CLOSED " + str(why))


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as src:
        for chunk in iter(lambda: src.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def select_cases(manifest):
    """Precommit: 3 eligible XOR + 2 partial + 2 no-exact + 1 unscannable.

    8 actual official frozen R67 formulas, same inputs across all three modes.
    Controls expose run-to-run noise where no R65 XOR intervention is possible.
    """
    cases = manifest["cases"]
    salt = "R70-CONTROL-20261103-SHA-FROZEN-V1"
    eligible = [c for c in cases if c["r67_features"]["r65_eligible"]]
    check(len(eligible) == 3, "R67 eligible XOR count drift")
    selection = list(eligible)
    for group, count in (("partial_only", 2), ("no_exact", 2), ("unscannable", 1)):
        pool = [c for c in cases if c["group"] == group and c not in selection]
        pool.sort(key=lambda c: hashlib.sha256(
            (salt + ":" + c["sha256"]).encode()).hexdigest())
        check(len(pool) >= count, "insufficient R67 controls: " + group)
        selection.extend(pool[:count])
    check(len(selection) == 8 and len({c["sha256"] for c in selection}) == 8,
          "R71 sample not eight unique original CNFs")
    return selection


def load(args):
    root = Path(args.sources)
    mf = json.loads((root / "manifest.json").read_text())
    prior = json.loads(Path(args.prior).read_text())
    check(mf["protocol"] == R67_PROTOCOL
          and prior["protocol"] == R67_PROTOCOL and prior["status"] == "PASS",
          "R67 manifest or final audit missing")
    check(len(mf["cases"]) == 25 and
          prior["diagnostics"]["actual_sources"] == 25, "cohort drift")
    check({c["gbd"] for c in mf["cases"]} ==
          {c["gbd"] for c in prior["per_formula"]}, "case identity drift")
    eligible = select_cases(mf)
    check(len(eligible) == SHARDS, "R71 cohort changed")
    binary = Path(args.kissat).resolve()
    check(binary.is_file() and digest(binary) == prior["binary_sha"][0],
          "pinned Kissat SHA differs from R67")
    return root, eligible, binary


def prove_cnf_bcp(cnf, clause, occurrences, xrefs, deadline):
    """True only if original-CNF unit propagation proves the whole unit/binary.

    For a v b, CNF under not-a must force b (or conflict), equivalently it
    may force a under not-b. A False result is UNKNOWN, not non-redundancy.
    """
    check(1 <= len(clause) <= 2, "R65 clauses must be unit/binary")
    for first in clause:
        if time.monotonic() > deadline:
            raise r65.ProbeBudget("CNF BCP classification deadline")
        conflict, assigned = r65.propagate(
            cnf, [], occurrences, xrefs,
            assumption=-first, deadline=deadline)
        if conflict:
            return True
        if len(clause) == 2:
            second = next(x for x in clause if x != first)
            if assigned.get(abs(second)) == (second > 0):
                return True
    return False


def classify_clauses(cnf, clauses):
    start = time.monotonic()
    network = r65.build_network(0, cnf, [])
    check(network is not None, "empty original CNF")
    occ, xrefs, _ = network
    deadline = time.monotonic() + BCP_BUDGET
    filtered = []
    bcp = []
    unknown = 0
    for c in clauses:
        try:
            proved = prove_cnf_bcp(cnf, c, occ, xrefs, deadline)
        except r65.ProbeBudget:
            proved = False
            unknown += 1
        if proved:
            bcp.append(c)
        else:
            filtered.append(c)
    check(len(filtered) + len(bcp) == len(clauses),
          "clause partition not complete")
    return filtered, {
        "derived": len(clauses),
        "cnf_bcp_proved": len(bcp),
        "not_proven_or_budget": len(filtered),
        "budget_unknown": unknown,
        "classification_s": round(time.monotonic()-start,6),
        "classification_is_sufficient_only": True,
        "proven_clause_samples": [list(x) for x in bcp[:8]],
        "retained_clause_samples": [list(x) for x in filtered[:8]]
    }


def prepare(root, case):
    source = root / case["filename"]
    check(source.is_file() and digest(source) == case["sha256"],
          "frozen original CNF SHA changed")
    # Ineligible controls need no XOR preprocessing: do not parse huge CNFs
    # just to decide that no XOR clauses should be appended.
    if not case["r67_features"]["r65_eligible"]:
        return source, [], [], [], {
            "derived": 0, "cnf_bcp_proved": 0,
            "not_proven_or_budget": 0, "budget_unknown": 0,
            "classification_s": 0.0, "classification_is_sufficient_only": True,
            "proven_clause_samples": [], "retained_clause_samples": [],
            "prep_s": 0.0, "preprocess_route": "R67_ineligible_control",
            "end_to_end_overhead_s": 0.0
        }
    n, cnf = r28.load_clauses(source)
    check(n == case["variables"] and len(cnf) == case["clauses"],
          "original CNF headers mismatch")
    t0 = time.monotonic()
    try:
        clauses, info = r65.derive_for_source(
            source, case, time.monotonic() + r65.MAX_PREP_S)
    except (r65.ProbeBudget, TimeoutError):
        clauses, info = [], {"route": "budget_fallback"}
    prep_s = time.monotonic()-t0
    if prep_s > r65.MAX_PREP_S:
        clauses, info = [], {"route": "budget_fallback"}
    filtered, stats = classify_clauses(cnf, clauses)
    check(set(map(tuple,filtered)).issubset(set(map(tuple,clauses))),
          "filter introduced clause")
    return source, cnf, clauses, filtered, {
        **stats, "prep_s":round(prep_s,6),
        "preprocess_route":info.get("route", "unknown"),
        "end_to_end_overhead_s":round(prep_s+stats["classification_s"],6)
    }


def measure(args):
    check(0 <= args.shard < SHARDS, "shard out of range")
    r65.MAX_PREP_S = 2.0
    root, cases, binary = load(args)
    case = cases[args.shard]
    source, cnf, all_clauses, filtered, diag = prepare(root, case)
    # One logical core per worker, as in prior R67 matched runs.
    if hasattr(os, "sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    rows = []
    with tempfile.TemporaryDirectory(prefix="drnas-r69-") as tmp:
        full_path = Path(tmp) / "full.cnf"
        filter_path = Path(tmp) / "filtered.cnf"
        if all_clauses:
            r64.augment(source, full_path, case["variables"],case["clauses"],all_clauses)
        else:
            full_path = source
        if filtered:
            r64.augment(source, filter_path, case["variables"],case["clauses"],filtered)
        else:
            filter_path = source
        targets = dict(original=source,full_r65=full_path,bcp_filtered=filter_path)
        # Randomize order deterministically by rep to reduce systematic run-order effects.
        for rep in range(REPS):
            modes = list(MODES)
            seed = int(hashlib.sha256(
                (ORDER_SEED_PROTOCOL+case["sha256"]+str(rep)).encode()).hexdigest(),16)
            random.Random(seed).shuffle(modes)
            for mode in modes:
                # uses the R68 SIGINT stats extractor and original SAT-witness verifier
                r68.PULSE_SECONDS = CAP
                result = r68.short_pulse(binary, targets[mode],
                                         source, case["official_status"])
                row = dict(gbd=case["gbd"],rep=rep,mode=mode,**result)
                rows.append(row)
                print("R71_PULSE",json.dumps({
                    "id":case["gbd"][:12], "rep":rep, "mode":mode,
                    "answer":result["answer"],
                    "wall_s":result["wall_s"],
                    "conflicts":result["early_counters"].get("conflicts"),
                    "decisions":result["early_counters"].get("decisions"),
                    "propagations":result["early_counters"].get("propagations"),
                    "restarts":result["early_counters"].get("restarts"),
                    "new_clauses":len(all_clauses) if mode=="full_r65"
                         else len(filtered) if mode=="bcp_filtered" else 0
                },sort_keys=True),flush=True)
    check(len(rows)==REPS*len(MODES), "six solver pulses required")
    result = dict(protocol=PROTOCOL,shard=args.shard,gbd=case["gbd"],
        sha256=case["sha256"], binary_sha=digest(binary),
        case_group=case["group"], official_status=case["official_status"],
        cap_s=CAP,reps=REPS,modes=list(MODES),
        diagnostics=diag, rows=rows)
    out = Path(args.out)
    out.mkdir(parents=True,exist_ok=True)
    (out/"r71-shard.json").write_text(json.dumps(result,indent=2)+"\n")
    print("R71_SHARD_PASS",json.dumps({
        "shard":args.shard,"id":case["gbd"],"pulses":len(rows),
        "derived":len(all_clauses),"bcp_proved":diag["cnf_bcp_proved"],
        "retained":len(filtered)}),flush=True)


def audit(args):
    manifest = json.loads((Path(args.sources)/"manifest.json").read_text())
    check(manifest["protocol"]==R67_PROTOCOL,"wrong source manifest")
    selected = select_cases(manifest)
    check(len(selected)==SHARDS,"target source count mismatch")
    rows=[]
    cases=[]
    pins=set()
    for shard in range(SHARDS):
        p=Path(args.combined)/f"r71-shard-{shard}"/"results"/"r71-shard.json"
        data=json.loads(p.read_text())
        case=selected[shard]
        check(data["protocol"]==PROTOCOL and data["shard"]==shard
            and data["gbd"]==case["gbd"] and data["sha256"]==case["sha256"]
            and data["cap_s"]==CAP and data["reps"]==REPS
            and data["modes"]==list(MODES), "shard provenance mismatch")
        pins.add(data["binary_sha"])
        check(len(data["rows"])==REPS*len(MODES), "incomplete shard")
        for rep in range(REPS):
            r=[x for x in data["rows"] if x["rep"]==rep]
            check({x["mode"] for x in r}==set(MODES) and len(r)==len(MODES),
                  "duplicate or missing mode")
            check(all(x["gbd"]==case["gbd"] and
                x["answer"] in ("UNKNOWN","SAT","UNSAT") and
                x["wall_s"]>=0 and
                (x["answer"]=="UNKNOWN" or x["answer"]==case["official_status"])
                for x in r), "invalid SAT output")
        for row in data["rows"]:
            rows.append({**row,"shard":shard})
        cases.append(data)
    check(len(pins)==1 and len(rows)==SHARDS*REPS*len(MODES),
          "binary mismatch or total pulse mismatch")
    summary={}
    for mode in MODES:
        rr=[x for x in rows if x["mode"]==mode]
        summary[mode]=dict(
            trials=len(rr),solved=sum(x["answer"]!="UNKNOWN" for x in rr),
            unknown=sum(x["answer"]=="UNKNOWN" for x in rr),
            mean_conflicts_per_pulse=round(
                sum(x["early_counters"].get("conflicts",0) for x in rr)/
                max(1,len(rr)),2),
            mean_decisions_per_pulse=round(
                sum(x["early_counters"].get("decisions",0) for x in rr)/
                max(1,len(rr)),2),
            mean_propagations_per_pulse=round(
                sum(x["early_counters"].get("propagations",0) for x in rr)/
                max(1,len(rr)),2))
    result=dict(protocol=PROTOCOL,status="PASS",
        sources=SHARDS,pulses=len(rows),cap_s=CAP,
        groups=list(MODES),binary_sha=list(pins)[0],
        summary=summary,cases=cases,
        limitations=[
            "Eight R67 official formulas were already observed (3 XOR-eligible + 5 controls): not blind.",
            "15-second censored dynamics, not an official full solving benchmark.",
            "CNF-BCP proof shows a clause is already derivable by basic propagation; such clauses can still accelerate CDCL.",
            "Failure to prove by bounded BCP does not establish novelty or usefulness.",
            "Preprocess and classification costs excluded from 15s Kissat pulses but recorded in each case.",
            "No solver API modification; all variants solved using the same pinned Kissat binary.",
            "Short-run conflict/propagation counts are diagnostics, not direct measures of solving speed.",
            "SAT witness checked against original CNF; UNSAT relies on official status absent independent proof.",
            "Two repetitions on eight instances are too few for statistically robust speedup claims."
        ])
    Path(args.json).write_text(json.dumps(result,indent=2)+"\n")
    lines=["# R71: 15-second BCP redundancy ablation on 8 frozen official R67 formulas",
        f"{SHARDS} sources; {REPS} repetitions × {len(MODES)} Kissat modes = {len(rows)} pulses.",
        "Interpret early counters, not as solved speedup unless a model/certificate is actually produced.",
        "",
        "| Formula | Derived R65 | CNF BCP proven | Retained filtered | Prep+filter (s) |",
        "|---|---:|---:|---:|---:|"]
    for c in cases:
        d=c["diagnostics"]
        lines.append(f"| {c['gbd'][:12]} | {d['derived']} | "
            f"{d['cnf_bcp_proved']} | {d['not_proven_or_budget']} | "
            f"{d['end_to_end_overhead_s']:.3f} |")
    lines += ["","| Mode | Solved | Unknown | Mean conflicts / 15s | Mean propagations / 15s |",
              "|---|---:|---:|---:|---:|"]
    for mode in MODES:
        s=summary[mode]
        lines.append(f"| {mode} | {s['solved']}/{s['trials']} | "
            f"{s['unknown']} | {s['mean_conflicts_per_pulse']:.1f} | "
            f"{s['mean_propagations_per_pulse']:.1f} |")
    lines += ["","## Instance-level paired early counters",
      "| Source | Rep | Original conflicts | Full conflicts | Filtered conflicts | "
      "Original propagations | Full propagations | Filtered propagations |",
      "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for c in cases:
        for rep in range(REPS):
            rs={r["mode"]:r for r in c["rows"] if r["rep"]==rep}
            gc=lambda mode,key: rs[mode]["early_counters"].get(key,"n/a")
            lines.append(f"| {c['gbd'][:12]} | {rep} | "
                f"{gc(MODES[0],'conflicts')} | {gc(MODES[1],'conflicts')} | {gc(MODES[2],'conflicts')} | "
                f"{gc(MODES[0],'propagations')} | {gc(MODES[1],'propagations')} | {gc(MODES[2],'propagations')} |")
    lines += ["","## Interpretation safeguards"]+["- "+s for s in result["limitations"]]
    Path(args.md).write_text("\n".join(lines)+"\n")
    print("R71_FINAL_AUDIT_PASS",json.dumps({
        "sources":SHARDS,"pulses":len(rows),"summary":summary,
        "proven_bcp":sum(c["diagnostics"]["cnf_bcp_proved"] for c in cases),
        "retained":sum(c["diagnostics"]["not_proven_or_budget"] for c in cases),
        "derived":sum(c["diagnostics"]["derived"] for c in cases)
    }),flush=True)


def main():
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest="cmd",required=True)
    m=sub.add_parser("measure")
    for k in ("sources","prior","kissat","out"):
        m.add_argument("--"+k,required=True)
    m.add_argument("--shard",required=True,type=int)
    a=sub.add_parser("audit")
    for k in ("sources","combined","json","md"):
        a.add_argument("--"+k,required=True)
    args=parser.parse_args()
    if args.cmd=="measure":
        measure(args)
    else:
        audit(args)


if __name__=="__main__":
    main()
