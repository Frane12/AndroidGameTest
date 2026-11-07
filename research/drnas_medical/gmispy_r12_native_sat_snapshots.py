#!/usr/bin/env python3
"""DRNAS Medical R12: true native R195 policies on R9 gene-knockout SAT snapshots.

This is a SAT-core bridge, NOT a full native replacement of incremental R9:
R9's PySAT CaDiCaL still generates the immutable clauses and validates the
complete gMCS result; three modes of the SAME pinned native R195/CaDiCaL binary
then replay identical extracted CNFs. No Human-GEM/gMCSpy comparison here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import re
import statistics
import subprocess
import time
from unittest.mock import patch

import gmispy_r9_scaling as r9
import gmispy_r8_iml1515 as r8
import gmispy_r11_phenotype_cache as r11

PROTO = "DRNAS-MEDICAL-R12-NATIVE-EXACT-CNF-SNAPSHOTS-20261107-v1"
SIZES = (24, 48, 96, 192, 384)
MODES = ("default", "dual_keep_default", "dual_keep_guarded")
REPS = 2
CAP_S = 2.0
R195_SHA = "9d19a4ab2da1dc87ddc8a61156c2742078628642"
R10_RUN = 42286261326
SELECT_CALLS = (1, 3, 16)


def need(value, reason):
    if not value:
        raise RuntimeError("R12_FAIL_CLOSED " + reason)


def read(path):
    return json.loads(pathlib.Path(path).read_text())


def save(path, data):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canon(items):
    return sorted(tuple(sorted(v)) for v in items)


def parse_dimacs(path):
    clauses, current, count, width = [], [], None, None
    for line in pathlib.Path(path).read_text().splitlines():
        if not line.strip() or line.lstrip().startswith(("c", "%")):
            continue
        if line.startswith("p "):
            need(width is None, "duplicate DIMACS header")
            fields = line.split()
            need(len(fields) == 4 and fields[1] == "cnf", "bad DIMACS header")
            width, count = int(fields[2]), int(fields[3])
            continue
        need(width is not None, "clauses before DIMACS header")
        for item in map(int, line.split()):
            if item == 0:
                clauses.append(tuple(current))
                current = []
            else:
                need(1 <= abs(item) <= width, "literal exceeds DIMACS width")
                current.append(item)
    need(width is not None and not current and len(clauses) == count,
         "DIMACS clause count mismatch")
    return width, clauses


def check_model(clauses, model):
    chosen = set(model)
    need(not any(-v in chosen for v in chosen), "contradictory SAT assignment")
    need(all(any(v in chosen for v in clause) for clause in clauses),
         "native SAT model does not satisfy original CNF")


class CaptureSolver:
    def __init__(self, original, stage, *args, **kwargs):
        self.inner = original(*args, **kwargs)
        need(kwargs.get("name") == "cadical195", "R9 backend unexpectedly changed")
        self.stage = stage
        self.clauses = [tuple(c) for c in kwargs.get("bootstrap_with", [])]
        self.call_count = 0
        self.selected = {}
        self.last = None

    def __enter__(self):
        self.inner.__enter__()
        return self

    def __exit__(self, *args):
        return self.inner.__exit__(*args)

    def add_clause(self, clause, *args, **kwargs):
        result = self.inner.add_clause(clause, *args, **kwargs)
        self.clauses.append(tuple(clause))
        return result

    def solve(self, *args, **kwargs):
        need(not args and not kwargs, "unexpected R9 solve assumptions")
        self.call_count += 1
        result = bool(self.inner.solve())
        # Clause tuples are immutable; shallow list copy is safe and cheap.
        snapshot = (self.call_count, result, list(self.clauses))
        if self.call_count in SELECT_CALLS:
            self.selected[self.call_count] = snapshot
        self.last = snapshot
        return result

    def get_model(self, *args, **kwargs):
        return self.inner.get_model(*args, **kwargs)

    def __getattr__(self, key):
        return getattr(self.inner, key)


def freeze(source, frozen, reference, n, out):
    from pysat.solvers import Solver as OriginalSolver
    need(n in SIZES, "unexpected gene cohort")
    out = pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    genes, expected = r11.frozen_reference(source, frozen, reference, n)
    model, model_data = r8.load_frozen(source)
    rules = r8.all_rules(model)
    threshold = float(model_data["wildtype_biomass"]) * 0.01
    used = []

    def factory(*args, **kwargs):
        solver = CaptureSolver(OriginalSolver, len(used) + 1, *args, **kwargs)
        used.append(solver)
        return solver

    tick = time.perf_counter()
    with patch("pysat.solvers.Solver", factory):
        result = r9.solve(model, genes, rules, threshold, 150.0)
    generate_s = round(time.perf_counter() - tick, 6)
    need(result["status"] == "SOLVED" and result["SAT_UNSAT_stages"] == 3,
         "R9 reference generator did not terminate all cardinalities")
    need(canon(result["minimal_sets"]) == canon(expected),
         "R9 result differs from frozen R10 gMCS reference")
    need(len(used) == 3 and all(s.last and s.last[1] is False for s in used),
         "expected exactly three UNSAT-terminated SAT stages")
    cases = []
    seen = set()
    from pysat.solvers import Solver
    for solver in used:
        sampled = list(solver.selected.values()) + [solver.last]
        for call, expected_sat, clauses in sampled:
            width = max(abs(v) for clause in clauses for v in clause)
            data = (f"p cnf {width} {len(clauses)}\n" +
                    "".join(" ".join(str(v) for v in clause) + " 0\n"
                            for clause in clauses))
            digest = sha(data.encode())
            if digest in seen:
                continue
            seen.add(digest)
            name = f"stage{solver.stage}-call{call}-{digest[:12]}.cnf"
            path = out / name
            path.write_text(data)
            new_width, check_clauses = parse_dimacs(path)
            need(new_width == width and len(check_clauses) == len(clauses),
                 "frozen DIMACS roundtrip failed")
            with Solver(name="g4", bootstrap_with=clauses) as validator:
                actual_sat = bool(validator.solve())
                need(actual_sat == expected_sat, "independent SAT answer differs")
                if actual_sat:
                    check_model(clauses, validator.get_model())
            cases.append({
                "name": name, "SHA256": digest, "stage": solver.stage,
                "call": call, "clauses": len(clauses), "variables": width,
                "expected": "SAT" if expected_sat else "UNSAT",
                "independent_glucose4_verified": True,
            })
    need(len(cases) >= 3 and any(c["expected"] == "SAT" for c in cases)
         and any(c["expected"] == "UNSAT" for c in cases),
         "SAT/UNSAT snapshot diversity missing")
    report = {
        "protocol": PROTO, "n": n, "R10_reference_run": R10_RUN,
        "source_SHA256": r9.SOURCE_SHA, "gene_SHA256": r9.hgenes(genes),
        "R195_pinned_commit": R195_SHA, "snapshots": cases,
        "R9_complete_exact_results_match": True,
        "R9_independent_exhaustive_reference_only_for_24_48": n in (24, 48),
        "generator_s_excluded_from_native_core_timings": generate_s,
        "generator_sat_calls_per_stage": [x.call_count for x in used],
        "not_full_native_GMCS_pipeline": True,
        "not_published_gMCSpy_comparison": True,
        "not_human_cancer_model": True,
    }
    save(out / "manifest.json", report)
    print("R12_FREEZE_PASS", json.dumps({
        "n": n, "snapshots": len(cases), "sat_calls": report["generator_sat_calls_per_stage"],
        "generator_s": generate_s,
    }, sort_keys=True), flush=True)


def native_trial(binary, path, mode, seed, expected, clauses, variables):
    begin = time.perf_counter()
    try:
        p = subprocess.run(
            [str(binary), str(path), str(CAP_S), mode, "0", str(seed)],
            capture_output=True, text=True, timeout=CAP_S + 6.0,
        )
    except subprocess.TimeoutExpired:
        return {"status": "TIMEOUT", "wall_s": round(time.perf_counter()-begin, 7)}
    elapsed = round(time.perf_counter() - begin, 7)
    need(p.returncode == 0, "native process crash " + p.stderr[-350:])
    statuses = re.findall(r"^R182_STATUS status=(SAT|UNSAT|TIMEOUT)\b",
                          p.stdout, flags=re.MULTILINE)
    need(len(statuses) == 1, "native status missing or duplicated")
    status = statuses[0]
    need(status == expected or status == "TIMEOUT",
         "native and independent SAT solvers disagree on SHA CNF")
    vals = []
    if status == "SAT":
        for line in p.stdout.splitlines():
            if line.startswith("v "):
                fields = [int(x) for x in line.split()[1:]]
                need(fields and fields[-1] == 0, "native model syntax")
                vals.extend(fields[:-1])
        need(all(1 <= abs(v) <= variables for v in vals),
             "native model variable out of bounds")
        check_model(clauses, vals)
    return {
        "status": status, "wall_s": elapsed,
        "solver_s": (float(re.search(r"solver_s=([0-9.]+)", p.stdout).group(1))
                     if re.search(r"solver_s=([0-9.]+)", p.stdout) else None),
        "SAT_model_checked": status == "SAT",
    }


def paired(cases_dir, binary, out):
    cases_dir = pathlib.Path(cases_dir)
    binary = pathlib.Path(binary).resolve()
    need(binary.is_file(), "missing actual compiled native R195 binary")
    manifest = read(cases_dir / "manifest.json")
    need(manifest["protocol"] == PROTO and
         manifest["R195_pinned_commit"] == R195_SHA and
         manifest["R9_complete_exact_results_match"] is True,
         "frozen source manifest mismatch")
    pin = sha(binary.read_bytes())
    rows = []
    for rep in range(REPS):
        for case in manifest["snapshots"]:
            path = cases_dir / case["name"]
            need(sha(path.read_bytes()) == case["SHA256"], "CNF modified after freezing")
            variables, clauses = parse_dimacs(path)
            need(variables == case["variables"] and len(clauses) == case["clauses"],
                 "frozen DIMACS mismatch")
            seed = (11, 17)[rep]
            order = MODES if rep == 0 else tuple(reversed(MODES))
            for mode in order:
                result = native_trial(binary, path.resolve(), mode, seed,
                                      case["expected"], clauses, variables)
                row = {**result, "n": manifest["n"], "SHA256": case["SHA256"],
                       "stage": case["stage"], "call": case["call"],
                       "expected": case["expected"], "mode": mode,
                       "seed": seed, "rep": rep, "native_SHA256": pin}
                rows.append(row)
                print("R12_TRIAL", json.dumps({
                    "n": row["n"], "mode": mode, "rep": rep,
                    "status": row["status"], "expected": row["expected"],
                    "wall_s": row["wall_s"], "stage": row["stage"],
                    "call": row["call"],
                }, sort_keys=True), flush=True)
                save(out, {"protocol": PROTO, "partial": True, "rows": rows})
    all_solved = all(x["status"] == x["expected"] for x in rows)
    totals = {mode: round(sum(x["wall_s"] for x in rows if x["mode"] == mode), 7)
              for mode in MODES}
    ratios = ({mode: round(totals["default"] / totals[mode], 6)
               for mode in MODES[1:]} if all_solved and all(
                   x > 0 for x in totals.values()) else {})
    report = {
        "protocol": PROTO, "partial": False, "n": manifest["n"],
        "source_SHA256": manifest["source_SHA256"],
        "gene_SHA256": manifest["gene_SHA256"],
        "native_SHA256": pin, "R195_pinned_commit": R195_SHA,
        "R10_reference_run": R10_RUN,
        "snapshots": len(manifest["snapshots"]),
        "rows": rows, "total_wall_s": totals, "ratios_vs_native_clean": ratios,
        "all_SAT_UNSAT_correct": all_solved, "all_modes_completed": all_solved,
        "timing_includes_native_process_startup": True,
        "not_full_native_GMCS_pipeline": True,
        "not_a_medical_speedup_claim": True,
    }
    save(out, report)
    print("R12_COHORT_FINAL", json.dumps({
        "n": report["n"], "snapshots": report["snapshots"],
        "all_correct": all_solved, "totals_s": totals, "ratios": ratios,
    }, sort_keys=True), flush=True)


def audit(paths, out):
    need(len(paths) == len(SIZES), "five cohort reports required")
    records = [read(x) for x in paths]
    need([x["n"] for x in records] == list(SIZES), "missing cohort")
    for obj in records:
        need(obj["protocol"] == PROTO and obj["partial"] is False
             and obj["source_SHA256"] == r9.SOURCE_SHA
             and obj["R195_pinned_commit"] == R195_SHA
             and obj["R10_reference_run"] == R10_RUN
             and len(obj["rows"]) == obj["snapshots"] * REPS * len(MODES),
             "incomplete audit data")
        need({x["mode"] for x in obj["rows"]} == set(MODES),
             "missing solver arm")
        need(all(x["native_SHA256"] == obj["native_SHA256"] and
                 x["expected"] in ("SAT", "UNSAT") and
                 x["status"] in ("SAT", "UNSAT", "TIMEOUT")
                 for x in obj["rows"]), "untrusted native evidence")
        need(all(x["status"] in (x["expected"], "TIMEOUT") for x in obj["rows"]),
             "wrong SAT answer entered audit")
    need(len({x["native_SHA256"] for x in records}) == 1,
         "different native binary compiled across cohorts")
    final = {
        "protocol": PROTO,
        "status": ("COMPLETE_SAT_CORE_PAIRED" if all(
            x["all_modes_completed"] for x in records) else
            "PARTIAL_NATIVE_TIMEOUTS_NO_SPEEDUP_CLAIM"),
        "R195_pinned_commit": R195_SHA,
        "same_native_binary_SHA256": records[0]["native_SHA256"],
        "cohorts": [{
            "n": r["n"], "snapshots": r["snapshots"],
            "trials": len(r["rows"]), "all_modes_completed": r["all_modes_completed"],
            "total_wall_s": r["total_wall_s"],
            "paired_ratio_native_default_over_DRNAS": r["ratios_vs_native_clean"],
        } for r in records],
        "no_full_native_biological_algorithm_comparison": True,
        "no_gMCSpy_or_Human_GEM_comparison": True,
        "biological_SAT_instances_from_frozen_bacterial_iML1515": True,
        "separate_native_process_each_SAT_call": True,
        "no_general_complexity_claim": True,
    }
    save(out, final)
    print("R12_FINAL", json.dumps(final, sort_keys=True), flush=True)


def selftest():
    need(r9.SOURCE_SHA == "9c772d44ca43350e40dc7ee86c7aa148796856be1eea45e5406c6df8f7dcde28",
         "reference SBML hash drift")
    need(len(MODES) == 3 and REPS == 2 and set(SIZES) == {24,48,96,192,384},
         "protocol constants drift")
    check_model([(1,), (-1, 2)], [1, 2])
    print("R12_SELFTEST_PASS", json.dumps({
        "modes": MODES, "sizes": SIZES, "R195": R195_SHA,
    }), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("selftest", "freeze", "paired", "audit"))
    p.add_argument("--source", default="r12/r9/source")
    p.add_argument("--frozen", default="r12/r9/frozen")
    p.add_argument("--reference", default="r12/reference/summary.json")
    p.add_argument("--n", type=int, default=24)
    p.add_argument("--case-dir")
    p.add_argument("--binary")
    p.add_argument("--out", default="r12/out")
    p.add_argument("--inputs", nargs="*")
    a = p.parse_args()
    if a.action == "selftest":
        selftest()
    elif a.action == "freeze":
        freeze(a.source, a.frozen, a.reference, a.n, a.out)
    elif a.action == "paired":
        need(a.case_dir is not None and a.binary is not None,
             "missing case dir / native binary")
        paired(a.case_dir, a.binary, a.out)
    else:
        audit(a.inputs or [], a.out)
