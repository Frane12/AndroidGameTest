#!/usr/bin/env python3
"""R13 SAT-core timing on R12's SHA-frozen bacterial iML1515 CNF snapshots.

Pinned R195 logic; adds timing only, never changes search decisions.
NOT full gMCS / gMCSpy / Human-GEM benchmarking.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import pathlib
import re
import subprocess
import time

PROTO = "DRNAS-MEDICAL-R13-PINNED-INSIDE-SOLVE-20261107-v1"
R12_PROTO = "DRNAS-MEDICAL-R12-NATIVE-EXACT-CNF-SNAPSHOTS-20261107-v1"
R195_SHA = "9d19a4ab2da1dc87ddc8a61156c2742078628642"
SOURCE_SHA = "9c772d44ca43350e40dc7ee86c7aa148796856be1eea45e5406c6df8f7dcde28"
SIZES = (24, 48, 96, 192, 384)
MODES = ("default", "dual_keep_default", "dual_keep_guarded")
SEEDS = (11, 17, 23, 29, 31)
CAP_S = 2

def need(cond, msg):
    if not cond:
        raise RuntimeError("R13_FAIL_CLOSED " + str(msg))

def read(path):
    return json.loads(pathlib.Path(path).read_text())

def save(path, obj):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")

def digest(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def instrument(original, output):
    """Insert clocks around ALL calls to CaDiCaL::Solver::solve.

    No solver parameters, control-flow branches, search strategy or result
    handling are changed. The original source SHA is pinned by the CI fetch.
    """
    src = pathlib.Path(original).read_text()
    swaps = [
        ("array<double,2> pilot_s{0,0};",
         "array<double,2> pilot_s{0,0}; double r13_inner_s=0;"),
        ("pilot_s[i]+=took;windows++;",
         "pilot_s[i]+=took; r13_inner_s+=took;windows++;"),
        ("if(result==0&&!deadline.terminate())result=s[sel]->solve();",
         "if(result==0&&!deadline.terminate()){auto tick13=Clock::now(); "
         "result=s[sel]->solve(); r13_inner_s+=chrono::duration<double>(Clock::now()-tick13).count();}"),
        ("pilot_s[0]+=chrono::duration<double>(Clock::now()-tick).count();",
         "double took13=chrono::duration<double>(Clock::now()-tick).count(); "
         "pilot_s[0]+=took13; r13_inner_s+=took13;"),
        ("if(!result&&!deadline.terminate())result=s[0]->solve();",
         "if(!result&&!deadline.terminate()){auto tick13=Clock::now(); "
         "result=s[0]->solve(); r13_inner_s+=chrono::duration<double>(Clock::now()-tick13).count();}"),
        ("if(!deadline.terminate())result=s[0]->solve();",
         "if(!deadline.terminate()){auto tick13=Clock::now(); "
         "result=s[0]->solve(); r13_inner_s+=chrono::duration<double>(Clock::now()-tick13).count();}"),
        ('cout<<"R182_STATUS status="',
         'cout<<fixed<<setprecision(7)<<"R13_TIMING inner_s="<<r13_inner_s'
         '<<" native_s="<<seconds<<" prep_s="<<max(0.0,seconds-r13_inner_s)<<"\\n";'
         '\n    cout<<"R182_STATUS status="'),
    ]
    for old, new in swaps:
        need(src.count(old) == 1, "unrecognized R195 driver structure: " + old)
        src = src.replace(old, new)
    need(src.count("r13_inner_s+=") == 5, "not all five solve paths instrumented")
    pathlib.Path(output).write_text(src)
    print("R13_INSTRUMENT_PASS", json.dumps({
        "pinned_R195_sha": R195_SHA,
        "original_driver_sha256": digest(original),
        "instrumented_driver_sha256": digest(output),
        "only_timing_added": True,
    }), flush=True)

def parse_dimacs(path):
    n = m = None
    clauses = []
    clause = []
    for line in pathlib.Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith(("c", "%")):
            continue
        if line.startswith("p "):
            x = line.split()
            need(len(x) == 4 and x[1] == "cnf" and n is None, "DIMACS header")
            n, m = int(x[2]), int(x[3])
            continue
        need(n is not None, "clauses before DIMACS header")
        for z in (int(y) for y in line.split()):
            if z == 0:
                clauses.append(tuple(clause))
                clause = []
            else:
                need(1 <= abs(z) <= n, "DIMACS variable")
                clause.append(z)
    need(n is not None and m == len(clauses) and not clause, "DIMACS length")
    return n, clauses

def verify_model(clauses, assignments):
    vals = set(assignments)
    need(not any(-v in vals for v in vals), "contradictory model")
    need(all(any(v in vals for v in clause) for clause in clauses),
         "SAT witness fails ORIGINAL frozen CNF")

def run_native(binary, cnf, mode, seed, expect, variables, clauses):
    tick = time.perf_counter()
    try:
        p = subprocess.run([str(binary), str(cnf), str(CAP_S), mode, "0", str(seed)],
                           text=True, capture_output=True, timeout=CAP_S + 8)
    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "wall_s": round(time.perf_counter()-tick, 7)}
    wall = time.perf_counter() - tick
    need(p.returncode == 0, "native crash: " + p.stderr[-300:])
    status = re.findall(r"^R182_STATUS status=(SAT|UNSAT|TIMEOUT)\\b", p.stdout, re.M)
    need(len(status) == 1, "native status missing")
    need(status[0] == expect, "SAT answer differs from independently certified R12")
    timing = re.findall(r"^R13_TIMING inner_s=([0-9.]+) native_s=([0-9.]+) prep_s=([0-9.]+)$",
                        p.stdout, re.M)
    need(len(timing) == 1, "untrusted R13 inside-solve clock")
    inner, native, prep = (float(x) for x in timing[0])
    need(0 <= inner <= native + .0001 and 0 <= prep <= native + .0001,
         "invalid nested clock")
    if status[0] == "SAT":
        vals = []
        for line in p.stdout.splitlines():
            if line.startswith("v "):
                z = [int(v) for v in line.split()[1:]]
                need(z and z[-1] == 0, "native SAT witness syntax")
                vals.extend(z[:-1])
        need(all(1 <= abs(v) <= variables for v in vals), "SAT witness dimension")
        verify_model(clauses, vals)
    policy = re.findall(r"^R195_POLICY (.*)$", p.stdout, re.M)
    need(len(policy) == 1, "R195 policy missing")
    return {
        "status": status[0], "wall_s": round(wall, 7),
        "native_s": native, "inner_s": inner, "prep_s": prep,
        "external_overhead_s": round(max(0.0, wall-native), 7),
        "actual_dual": int(re.search(r"actual_dual=(\\d+)", policy[0]).group(1)),
        "policy_reason": re.search(r"reason=([a-zA-Z_]+)", policy[0]).group(1),
        "SAT_witness_checked": status[0] == "SAT",
    }

def paired(root, binary, n, out):
    from pysat.solvers import Solver
    need(n in SIZES, "not frozen cohort")
    root = pathlib.Path(root)
    binary = pathlib.Path(binary).resolve()
    need(binary.is_file(), "missing native binary")
    manifests = list(root.rglob("manifest.json"))
    need(len(manifests) == 1, "expected exactly one R12 frozen manifest")
    manifest = read(manifests[0])
    need(manifest["protocol"] == R12_PROTO
         and manifest["source_SHA256"] == SOURCE_SHA
         and manifest["R195_pinned_commit"] == R195_SHA
         and manifest["R9_complete_exact_results_match"] is True
         and manifest["n"] == n, "R12 model, gene, source or provenance mismatch")
    rows = []
    cases = []
    # Independent confirmation occurs before (never inside) the timing loop.
    for case in manifest["snapshots"]:
        cnf = (manifests[0].parent / case["name"]).resolve()
        need(cnf.is_file() and digest(cnf) == case["SHA256"],
             "CNF changed from R12 frozen SHA")
        variables, clauses = parse_dimacs(cnf)
        need(variables == case["variables"] and len(clauses) == case["clauses"]
             and case["independent_glucose4_verified"] is True,
             "R12 snapshot metadata invalid")
        with Solver(name="g4", bootstrap_with=clauses) as checker:
            ok = bool(checker.solve())
            need(("SAT" if ok else "UNSAT") == case["expected"],
                 "R13 independent oracle disagrees with R12")
            if ok:
                verify_model(clauses, checker.get_model())
        cases.append((case, cnf, variables, clauses))
    for rep, seed in enumerate(SEEDS):
        for case, cnf, variables, clauses in cases:
            order = MODES[rep % 3:] + MODES[:rep % 3]
            for mode in order:
                result = run_native(binary, cnf, mode, seed, case["expected"],
                                    variables, clauses)
                row = dict(result, mode=mode, n=n, seed=seed, rep=rep,
                           variables=variables, clauses=len(clauses),
                           SHA256=case["SHA256"], stage=case["stage"],
                           expected=case["expected"],
                           binary_SHA256=digest(binary))
                rows.append(row)
                print("R13_TRIAL", json.dumps({
                    k: row[k] for k in ("n", "stage", "mode", "rep", "status",
                                       "inner_s", "native_s", "wall_s")
                }, sort_keys=True), flush=True)
                save(out, {"protocol": PROTO, "partial": True, "rows": rows})
    need(len(rows) == len(cases)*len(SEEDS)*len(MODES), "incomplete paired runs")
    summary = {mode: {field: round(sum(x[field] for x in rows
                                         if x["mode"] == mode), 7)
                      for field in ("inner_s", "native_s", "wall_s", "prep_s",
                                    "external_overhead_s")} for mode in MODES}
    report = dict(protocol=PROTO, n=n, partial=False, source_SHA256=SOURCE_SHA,
                  R195_pinned_commit=R195_SHA, r12_run=42336300298,
                  r12_gene_SHA256=manifest["gene_SHA256"],
                  native_SHA256=digest(binary), snapshots=len(cases),
                  repetitions=len(SEEDS), rows=rows, totals_s=summary,
                  all_correct=True, independent_glucose4_again=True,
                  same_exact_biological_R12_CNF=True,
                  separate_process_timed=True,
                  full_gMCS_DRNAS_not_implemented=True,
                  human_cancer_model=False)
    save(out, report)
    print("R13_COHORT_FINAL", json.dumps({
        "n": n, "snapshots": len(cases), "all_correct": True, "totals_s": summary,
    }, sort_keys=True), flush=True)

def audit(paths, out):
    need(len(paths) == len(SIZES), "five cohorts required")
    records = [read(x) for x in paths]
    need([x["n"] for x in records] == list(SIZES), "missing or unordered cohort")
    for obj in records:
        need(obj["protocol"] == PROTO and obj["partial"] is False
             and obj["R195_pinned_commit"] == R195_SHA
             and obj["source_SHA256"] == SOURCE_SHA
             and obj["r12_run"] == 42336300298
             and obj["all_correct"] and obj["independent_glucose4_again"]
             and obj["repetitions"] == len(SEEDS)
             and len(obj["rows"]) == obj["snapshots"] * len(SEEDS)*len(MODES),
             "incomplete or unverified cohort")
        need(all(x["status"] == x["expected"] for x in obj["rows"]),
             "SAT/UNSAT mismatch")
    need(len({x["native_SHA256"] for x in records}) == 1,
         "not one common pinned native executable")
    fields = ("inner_s", "native_s", "wall_s", "prep_s", "external_overhead_s")
    sums = {mode: {field: round(sum(obj["totals_s"][mode][field]
                                     for obj in records), 7)
                   for field in fields} for mode in MODES}
    holdout = [x for x in records if x["n"] in (192, 384)]
    held = {mode: {field: round(sum(obj["totals_s"][mode][field]
                                     for obj in holdout), 7)
                   for field in fields} for mode in MODES}
    ratios = {mode: {
        "inner_speedup": round(sums["default"]["inner_s"]/sums[mode]["inner_s"], 6)
                          if sums[mode]["inner_s"] else None,
        "native_speedup": round(sums["default"]["native_s"]/sums[mode]["native_s"], 6),
        "wall_speedup": round(sums["default"]["wall_s"]/sums[mode]["wall_s"], 6)
    } for mode in MODES[1:]}
    holdout_eligible = {mode: (
        held[mode]["inner_s"] <= .95 * held["default"]["inner_s"] and
        held[mode]["wall_s"] <= held["default"]["wall_s"]
    ) for mode in MODES[1:]}
    report = dict(protocol=PROTO, status="COMPLETE_R13_NATIVE_CORE",
                  R195_pinned_commit=R195_SHA,
                  native_SHA256=records[0]["native_SHA256"],
                  sources_from_R12_SHA_frozen_iML1515=True,
                  cohorts=[{"n": x["n"], "snapshots": x["snapshots"],
                            "trials": len(x["rows"]), "totals_s": x["totals_s"]}
                           for x in records],
                  trials=sum(len(x["rows"]) for x in records),
                  snapshots=sum(x["snapshots"] for x in records),
                  overall_s=sums, overall_speedup=ratios,
                  heldout_192_384_s=held,
                  holdout_policies_meet_5pct_inner_no_wall_regression=holdout_eligible,
                  policy_promotion="NOT_AUTOMATIC; REQUIRES NEW BLIND RUN AND FULL BIOLOGY VALIDATION",
                  timings_include_process_startup_only_in_wall=True,
                  full_native_gMCS_comparison=False,
                  human_cancer_model=False,
                  general_complexity_claim=False)
    save(out, report)
    print("R13_FINAL", json.dumps(report, sort_keys=True), flush=True)

def selftest():
    sample = pathlib.Path("r13-smoke-original.cpp")
    if sample.exists():
        pass
    need(len(SEEDS) == 5 and len(MODES) == 3 and len(SIZES) == 5,
         "configuration drift")
    verify_model([(1,), (-1, 2)], [1, 2])
    print("R13_SELFTEST_PASS", json.dumps({"R195": R195_SHA,
           "sizes": SIZES, "seeds": SEEDS, "modes": MODES}), flush=True)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("instrument", "paired", "audit", "selftest"))
    p.add_argument("--input")
    p.add_argument("--root")
    p.add_argument("--binary")
    p.add_argument("--n", type=int)
    p.add_argument("--out", default="r13/result.json")
    p.add_argument("--inputs", nargs="*")
    a = p.parse_args()
    if a.action == "instrument":
        need(a.input, "--input required")
        instrument(a.input, a.out)
    elif a.action == "paired":
        need(a.root and a.binary and a.n, "paired inputs missing")
        paired(a.root, a.binary, a.n, a.out)
    elif a.action == "audit":
        audit(a.inputs or [], a.out)
    else:
        selftest()
