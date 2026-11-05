#!/usr/bin/env python3
"""R68: very short R67 real-formula XOR-CNF mechanism experiment.

Replay ONLY the three SHA-frozen, R65-eligible SAT2026 CNFs from R67.
One 2-second Kissat pulse on original and augmented CNF per source.
R65 reasoning is measured separately and is NOT hidden from total cost.
Short pulses cannot establish 60-second solve speedup; record useful
early-solver counters only when emitted, plus exact passive BCP diagnostics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import signal
import subprocess
import tempfile
import time
from pathlib import Path

import r28_exact_gf2_benchmark as r28
import r32p_real_satcomp26_benchmark as r32p
import r63_real2026_xor_prevalence_fallback as r63
import r64_mixed_xor_implied as r64
import r65_xor_cnf_feedback as r65

PROTO = "DRNAS-R68-2SEC-EARLY-XOR-FORENSICS-20261103-v1"
PREVIOUS = "DRNAS-R67-BLIND-STRUCTURAL-DIAGNOSTIC-20261103-v1"
PULSE_SECONDS = 2.0
MAX_BCP_SECONDS = 0.6


def check(ok, why):
    if not ok:
        raise RuntimeError("R68_FAIL_CLOSED " + str(why))


def digest(p):
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def bcp_redundancy(cnf, equations, clauses):
    """Check whether original CNF alone proves derived clauses by one-assumption BCP.

    Sufficient test only: no proof of non-redundancy when this fails.
    0.6-second total bound; at most 8 clauses per source.
    """
    deadline = time.monotonic() + MAX_BCP_SECONDS
    network = r65.build_network(0, cnf, [])
    if network is None:
        return {"checked": 0, "bcp_demonstrated": 0, "unknown": min(8, len(clauses))}
    occurrences, xrefs, _ = network
    checked, redundant = 0, 0
    sample = clauses[:8]
    for clause in sample:
        if time.monotonic() >= deadline:
            break
        # For (a OR b), assume NOT a; CNF-only BCP must infer b or conflict.
        # For (a), assume NOT a; BCP conflict proves the unit.
        first = clause[0]
        try:
            conflict, assigned = r65.propagate(cnf, [], occurrences, xrefs,
                assumption=-first, deadline=deadline)
        except r65.ProbeBudget:
            break
        demonstrated = bool(conflict)
        if len(clause) == 2 and not demonstrated:
            second = clause[1]
            demonstrated = (assigned.get(abs(second)) == (second > 0))
        checked += 1
        redundant += int(demonstrated)
    return {"sampled": len(sample), "checked": checked,
            "bcp_demonstrated": redundant, "unknown": len(sample)-checked,
            "interpretation": "Sufficient CNF-only BCP proof; undemonstrated != useful"}


def parse_statistics(txt):
    out = {}
    for line in txt.splitlines():
        if not line.lstrip().startswith("c "):
            continue
        for label in ("conflicts", "decisions", "propagations", "restarts"):
            found = re.search(r"\b" + label + r"\s*:?\s*([\d,]+)", line, re.I)
            if found:
                out[label] = int(found.group(1).replace(",", ""))
    return out


def short_pulse(binary, cnf, original, official):
    start = time.monotonic()
    # Interrupt to request statistics, but no assumption that this build emits them.
    with subprocess.Popen([str(binary), str(cnf)], stdout=subprocess.PIPE,
          stderr=subprocess.PIPE, text=True, errors="replace",
          preexec_fn=r63.child) as process:
        try:
            stdout, stderr = process.communicate(timeout=PULSE_SECONDS)
            interrupted = False
        except subprocess.TimeoutExpired:
            interrupted = True
            process.send_signal(signal.SIGINT)
            try:
                stdout, stderr = process.communicate(timeout=0.45)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
    elapsed = time.monotonic()-start
    rc = process.returncode
    answer = "UNKNOWN"
    if not interrupted and rc in (10,20):
        answer = "SAT" if rc == 10 else "UNSAT"
        check(answer == official, "original official verdict contradiction")
        if answer == "SAT":
            r32p.verify_sat_witness(original, stdout)
    elif not interrupted:
        check(rc in (10,20), "unexpected solver exit: " + str(rc) + " " + stderr[-300:])
    return {"answer": answer, "interrupted": interrupted,
            "wall_s": round(elapsed, 5), "return_code": rc,
            "early_counters": parse_statistics(stdout+"\n"+stderr),
            "statistics_available": bool(parse_statistics(stdout+"\n"+stderr)),
            "note": ("Early pulse only; timeout is not a 60-second solve failure"
                     if interrupted else "Full answer observed within short pulse")}


def run(a):
    root = Path(a.sources)
    historical = json.loads(Path(a.prior).read_text())
    frozen = json.loads((root/"manifest.json").read_text())
    check(frozen["protocol"] == PREVIOUS and historical["protocol"] == PREVIOUS
          and historical["status"] == "PASS", "R67 provenance missing")
    check(len(frozen["cases"]) == historical["diagnostics"]["actual_sources"] == 25,
          "not the complete R67 frozen cohort")
    prior_cases = {c["gbd"]: c for c in historical["per_formula"]}
    check(set(prior_cases) == {c["gbd"] for c in frozen["cases"]},
          "R67 per-case identity drift")
    eligible = [c for c in frozen["cases"]
                if c["r67_features"]["r65_eligible"]]
    check(len(eligible) == 3, "unexpected eligibility cohort size")
    binary = Path(a.kissat).resolve()
    check(binary.is_file() and digest(binary) == historical["binary_sha"][0],
          "Kissat binary SHA drift")
    r65.MAX_PREP_S = 2.0
    cases = []
    for case in eligible:
        src = root / case["filename"]
        check(src.is_file() and digest(src) == case["sha256"],
              "original DIMACS hash mismatch")
        start = time.monotonic()
        try:
            clauses, details = r65.derive_for_source(src,case,
                time.monotonic() + r65.MAX_PREP_S)
            route = "derived" if clauses else "no_new_clauses"
        except (r65.ProbeBudget, TimeoutError) as e:
            clauses, details = [], {"route": "bounded_fallback",
                                     "reason": str(e)}
            route = "bounded_fallback"
        prep_s = time.monotonic()-start
        if prep_s > r65.MAX_PREP_S:
            clauses = []
            route = "prep_budget_fallback"
        n, cnf = r28.load_clauses(src)
        check(n == case["variables"] and len(cnf) == case["clauses"],
              "DIMACS clause count mismatch")
        bcp = bcp_redundancy(cnf, [], clauses)
        with tempfile.TemporaryDirectory(prefix="r68-short-") as td:
            target = Path(td)/"augmented.cnf"
            if clauses:
                r64.augment(src,target,n,len(cnf),clauses)
            else:
                target = src
            before = short_pulse(binary,src,src,case["official_status"])
            after = short_pulse(binary,target,src,case["official_status"])
        row = {"gbd":case["gbd"], "group":case["group"],
            "source_sha256":case["sha256"], "status":case["official_status"],
            "xor_blocks":case["complete_blocks"],
            "bridge_clauses":case["r67_features"]["xor_cnf_bridge_clauses"],
            "derived_count":len(clauses), "preprocess_s":round(prep_s,6),
            "preprocess_route":route, "details":details, "bcp":bcp,
            "kissat_original":before, "kissat_augmented":after,
            "r67_previous_delta_par2_s":
                prior_cases[case["gbd"]]["r65_vs_kissat_saved_s"],
            "r67_added_clause_trials":
                prior_cases[case["gbd"]]["r65_added_clause_trials"]}
        cases.append(row)
        print("R68_QUICK_CASE",json.dumps({
            "id":case["gbd"],"derived":len(clauses),
            "prep_s":round(prep_s,3),"CNF_BCP":bcp,
            "original":before,"augmented":after
        },sort_keys=True),flush=True)
    report = {"protocol":PROTO,"status":"PASS",
        "source":"SHA-frozen R67 official SAT Competition 2026 formulas",
        "actual_formulas":len(cases),
        "tests_per_formula":2,
        "pulse_cap_s":PULSE_SECONDS,
        "total_solver_pulses":len(cases)*2,
        "derived_clause_formula_count":sum(c["derived_count"]>0 for c in cases),
        "preprocess_total_s":round(sum(c["preprocess_s"] for c in cases),6),
        "cases":cases,
        "limitations":[
            "Intentionally only 2 seconds per Kissat pulse; not a full SAT benchmark.",
            "Order is original then augmented; do not infer causality from small pulse differences.",
            "Kissat may emit no counters on SIGINT; record missing metrics, do not invent.",
            "XOR-CNF preprocessing cost excluded from 2s Kissat pulse but reported separately.",
            "Only three previously seen R67 eligible formulas: diagnostic replay, not blind holdout.",
            "BCP check is sufficient-only and may not detect learned-clause redundancy.",
            "No claim of speedup if both modes do not solve or counters are unavailable.",
            "Unsolved long formulas are expected; this experiment measures early mechanism."
        ]}
    out=Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out/"r68-quick.json").write_text(json.dumps(report,indent=2)+"\n")
    lines=["# DRNAS R68: 2-second XOR-CNF early-dynamics forensic test",
      "3 previously SHA-frozen official 2026 formulas; 2s maximum per solver pulse;",
      "6 short pulses total. This is a diagnostic, **not** an official ranking.",
      "",
      "| Formula | XOR blocks | CNF bridge clauses | Derived | Prep (s) | CNF BCP verified | Kissat original (s) | Kissat augmented (s) | Counters? |",
      "|---|---:|---:|---:|---:|---:|---:|---:|---|"]
    for c in cases:
        lines.append(f"| {c['gbd'][:12]} | {c['xor_blocks']} | "
           f"{c['bridge_clauses']} | {c['derived_count']} | "
           f"{c['preprocess_s']:.4f} | {c['bcp']['bcp_demonstrated']}/{c['bcp']['checked']} | "
           f"{c['kissat_original']['wall_s']:.3f} | "
           f"{c['kissat_augmented']['wall_s']:.3f} | "
           f"{'yes' if c['kissat_original']['statistics_available'] or c['kissat_augmented']['statistics_available'] else 'no'} |")
    lines += ["", "## Interpretation and limits"]+["- "+s for s in report["limitations"]]
    (out/"r68-quick.md").write_text("\n".join(lines)+"\n")
    print("R68_QUICK_AUDIT_PASS",json.dumps({
        "sources":len(cases),"solver_pulses":len(cases)*2,
        "active":report["derived_clause_formula_count"],
        "preprocess_total_s":report["preprocess_total_s"],
        "counters_available":sum(
            x["kissat_original"]["statistics_available"] or
            x["kissat_augmented"]["statistics_available"] for x in cases)
    }),flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--sources",required=True)
    p.add_argument("--prior",required=True)
    p.add_argument("--kissat",required=True)
    p.add_argument("--out",required=True)
    run(p.parse_args())


if __name__ == "__main__":
    main()
