#!/usr/bin/env python3
"""DRNAS Medical R14: strictly gated CaDiCaL learnt-clause reuse ACROSS gene-KO stages.

R9 already reuses learnt clauses WITHIN one k-stage. This experiment compares:
 - baseline: EXACT R9 3 separate incremental CaDiCaL instances (unchanged)
 - gated_fresh: EXACT R9 logic rebuilt with separate activation-guarded stage solvers
 - shared_gated: ONE CaDiCaL instance across k=1,2,3 with guarded stage CNFs

Per-stage cardinality and candidate-block clauses are guarded. Invariant GPR
and independently certified original flux-witness clauses are unconditional.
Inactive stages are explicitly assumed false. Aux ids reused between stages
are safe under the assumptions; fresh oracle validation checks truth anyway.

This remains bacterial iML1515 gene-KO, NOT a human cancer or gMCSpy benchmark.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import pathlib
import statistics
import time
from unittest.mock import patch

import gmispy_r9_scaling as r9
import gmispy_r8_iml1515 as r8
import gmispy_r11_phenotype_cache as r11
import gmispy_r7_witness as r7

PROTO = "DRNAS-MEDICAL-R14-CROSS-STAGE-GATED-LEARNING-20261107-v1"
R10_REF_RUN = 42286261326
R9_RUN = 42239472392
SOURCE_SHA = "9c772d44ca43350e40dc7ee86c7aa148796856be1eea45e5406c6df8f7dcde28"
SIZES = (24, 48, 96, 192, 384)
ARMS = ("baseline", "gated_fresh", "shared_gated")
REPS = 3
CAP = 150.0


def need(ok, reason):
    if not ok:
        raise RuntimeError("R14_FAIL_CLOSED " + str(reason))


def save(path, obj):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def load(path):
    return json.loads(pathlib.Path(path).read_text())


def canon(sets):
    return tuple(sorted(tuple(sorted(s)) for s in sets))


def litmax(clauses):
    return max((abs(x) for clause in clauses for x in clause), default=0)


class GatedStage:
    """Minimal PySAT adapter supporting exactly the R9 interface."""

    def __init__(self, parent, inner, stage, activation):
        self.parent, self.inner = parent, inner
        self.stage, self.activation = stage, activation
        self.calls = 0
        self.adds = 0
        self.sat_s = 0.0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.parent.end_stage(self)
        return False

    def add_clause(self, clause, *args, **kwargs):
        need(not args and not kwargs, "unexpected add_clause API")
        # Stage-local: includes exact-assignment fallback and minimality blocks.
        self.inner.add_clause([-self.activation] + list(clause))
        self.adds += 1

    def solve(self, *args, **kwargs):
        need(not args and not kwargs, "unexpected assumptions or solve arguments")
        # Active k=true, every other stage=false. Old stage clauses never apply.
        assumptions = [
            x if x == self.activation else -x
            for x in self.parent.activation_literals
        ]
        tick = time.perf_counter()
        answer = bool(self.inner.solve(assumptions=assumptions))
        self.sat_s += time.perf_counter() - tick
        self.calls += 1
        return answer

    def get_model(self, *args, **kwargs):
        need(not args and not kwargs, "unexpected get_model API")
        return self.inner.get_model()


class StageCoordinator:
    def __init__(self, original_cls, genes, rules, arm):
        from pysat.card import CardEnc, EncType
        self.original_cls = original_cls
        self.arm = arm
        self.base = [tuple(c) for c in r7.GPRCNF(genes, rules).clauses]
        self.top = r7.GPRCNF(genes, rules).top
        self.card = []
        for k in (1, 2, 3):
            c = CardEnc.equals(lits=list(range(1, len(genes)+1)), bound=k,
                               encoding=EncType.seqcounter, top_id=self.top)
            self.card.append([tuple(row) for row in c.clauses])
        end = max(self.top, litmax(self.base),
                  *(litmax(c) for c in self.card))
        self.activation_literals = (end+1, end+2, end+3)
        self.instantiated = 0
        self.shared = None
        self.closed = False
        self.stages = []
        self.solver_creations = 0
        self.global_witness_clauses = set()

    def factory(self, *args, **kwargs):
        need(not args and kwargs.get("name") == "cadical195",
             "R9 changed PySAT backend or constructor signature")
        need(self.instantiated < 3, "unexpected fourth k-stage solver")
        bootstrap = [tuple(c) for c in kwargs.get("bootstrap_with", ())]
        kindex = self.instantiated
        prefix = self.base + self.card[kindex]
        need(bootstrap[:len(prefix)] == prefix,
             "R9 invariant GPR/cardinality input changed or mismatched")
        global_cuts = bootstrap[len(prefix):]
        need(all(litmax([c]) <= self.top for c in global_cuts),
             "unexpected global-witness clause variable outside GPR range")
        if self.arm == "shared_gated":
            if self.shared is None:
                self.shared = self.original_cls(name="cadical195",
                                                bootstrap_with=self.base)
                self.solver_creations += 1
            inner = self.shared
        else:
            inner = self.original_cls(name="cadical195",
                                      bootstrap_with=self.base)
            self.solver_creations += 1
        # Flux-witness clauses are certified in R9's primal LP, and R9
        # appends them to the initial CNF of ALL later stages unconditionally.
        for cut in global_cuts:
            if self.arm != "shared_gated" or cut not in self.global_witness_clauses:
                inner.add_clause(list(cut))
            self.global_witness_clauses.add(cut)
        # Exact-k sequential-counter constraints are conditional on k.
        act = self.activation_literals[kindex]
        for clause in self.card[kindex]:
            inner.add_clause([-act] + list(clause))
        stage = GatedStage(self, inner, kindex+1, act)
        self.stages.append(stage)
        self.instantiated += 1
        return stage

    def end_stage(self, stage):
        if self.arm == "gated_fresh":
            stage.inner.delete()

    def close(self):
        if self.shared is not None:
            self.shared.delete()
            self.shared = None
        self.closed = True

    def audit(self):
        need(self.instantiated == 3 and len(self.stages) == 3,
             "did not visit all 3 R9 stages")
        need(self.solver_creations == (1 if self.arm == "shared_gated" else 3),
             "solver lifetime accounting mismatch")
        return {
            "solver_creations": self.solver_creations,
            "cross_stage_same_solver": self.arm == "shared_gated",
            "native_sat_calls": sum(x.calls for x in self.stages),
            "native_sat_call_seconds": round(sum(x.sat_s for x in self.stages), 6),
            "stage_sat_call_seconds": [round(x.sat_s, 6) for x in self.stages],
            "stage_add_clause_calls": [x.adds for x in self.stages],
            "globally_shared_original_flux_cuts": len(self.global_witness_clauses),
            "stage_activation_literals": list(self.activation_literals),
        }


def run_trial(model, genes, rules, threshold, expected, arm, rep, n):
    from pysat.solvers import Solver as OriginalSolver
    need(arm in ARMS and rep in range(REPS), "unknown arm or repetition")
    coordinator = None
    tick = time.perf_counter()
    if arm == "baseline":
        result = r9.solve(model, genes, rules, threshold, CAP)
        bridge = {
            "solver_creations": 3,
            "cross_stage_same_solver": False,
            "native_sat_calls": result["sat_calls"],
            "native_sat_call_seconds": None,
            "stage_sat_call_seconds": None,
            "stage_add_clause_calls": None,
            "globally_shared_original_flux_cuts": None,
        }
    else:
        coordinator = StageCoordinator(OriginalSolver, genes, rules, arm)
        try:
            with patch("pysat.solvers.Solver", coordinator.factory):
                result = r9.solve(model, genes, rules, threshold, CAP)
        finally:
            coordinator.close()
        bridge = coordinator.audit()
        need(bridge["native_sat_calls"] == result["sat_calls"],
             "native SAT solve calls mismatch")
    driver_s = time.perf_counter() - tick
    need(result["status"] == "SOLVED" and result["SAT_UNSAT_stages"] == 3,
         "missing exact-k UNSAT termination")
    reference_match = canon(result["minimal_sets"]) == canon(expected)
    need(reference_match, "frozen R10 minimal genetic intervention set changed")
    independent = r9.verify_sets(model, genes, rules, threshold, result["minimal_sets"])
    need(independent["sound_minimal"], "independent gene/reaction FBA validation failed")
    stages = result["stages"]
    need([x["k"] for x in stages] == [1, 2, 3],
         "R9 stage order drift")
    step_s = [stages[0]["wall_elapsed_s"]]
    step_s += [round(stages[i]["wall_elapsed_s"] -
                     stages[i-1]["wall_elapsed_s"], 6) for i in (1, 2)]
    return {
        "arm": arm, "n": n, "rep": rep,
        "protocol": PROTO,
        "wall_s": result["wall_s"],
        "driver_wall_s": round(driver_s, 6),
        "stage_s": step_s,
        "sat_calls": result["sat_calls"],
        "lp_calls": result["lp_calls"],
        "flux_cuts": result["flux_cuts"],
        "minimal_sets": result["minimal_sets"],
        "minimal_count": len(expected),
        "reference_match": reference_match,
        "independent_FBA_verified": True,
        "independent_FBA_checks": independent["independent_checks"],
        "R9_stats": {k: v for k, v in result.items()
                     if k in ("candidate_only_safe_fallbacks",
                              "numerically_ambiguous_flux_support",
                              "duplicate_flux_clause_suppressed")},
        "bridge": bridge,
        "source_SHA256": SOURCE_SHA,
        "gene_SHA256": r9.hgenes(genes),
        "R10_reference_run": R10_REF_RUN,
        "exhaustive_reference_only_24_48": n in (24, 48),
        "not_native_DRNAS_solver": True,
        "not_cancer_model": True,
    }


def cohort(source, frozen, reference, n, out):
    need(n in SIZES, "cohort outside predeclared sizes")
    genes, expected = r11.frozen_reference(source, frozen, reference, n)
    model, manifest = r8.load_frozen(source)
    rules = r8.all_rules(model)
    threshold = float(manifest["wildtype_biomass"]) * .01
    need(threshold > 0 and len(genes) == n, "invalid model target")
    rows = []
    for rep in range(REPS):
        order = ARMS[rep:] + ARMS[:rep]
        for arm in order:
            trial = run_trial(model, genes, rules, threshold, expected,
                              arm, rep, n)
            rows.append(trial)
            save(out, {"protocol": PROTO, "partial": True,
                       "n": n, "rows": rows})
            print("R14_TRIAL", json.dumps({
                k: trial[k] for k in ("n", "rep", "arm", "wall_s",
                                     "sat_calls", "lp_calls", "flux_cuts",
                                     "reference_match")
            }, sort_keys=True), flush=True)
    need(len(rows) == len(ARMS)*REPS, "incomplete full-algorithm matrix")
    data = {arm: [x["wall_s"] for x in rows if x["arm"] == arm]
            for arm in ARMS}
    for arm in ARMS:
        need(len(data[arm]) == REPS, "missing paired arm")
    medians = {arm: round(statistics.median(data[arm]), 6) for arm in ARMS}
    paired = {arm: [round(b/t, 6)
                    for b,t in zip(data["baseline"], data[arm])]
              for arm in ARMS[1:]}
    report = {
        "protocol": PROTO, "partial": False,
        "n": n, "source_SHA256": SOURCE_SHA,
        "gene_SHA256": r9.hgenes(genes),
        "R9_reference_run": R9_RUN, "R10_reference_run": R10_REF_RUN,
        "expected_minimal_count": len(expected),
        "rows": rows, "wall_s_by_arm": data,
        "median_wall_s": medians,
        "paired_base_over_arm": paired,
        "all_correct": True,
        "independent_FBA": True,
        "same_biological_model_and_gene_set": True,
        "full_R9_gMCS_workflow_timed": True,
        "not_native_R195": True,
        "not_human_cancer": True,
        "no_complete_exhaustive_reference_above_48": True,
    }
    save(out, report)
    print("R14_COHORT_FINAL", json.dumps({
        "n": n, "median_s": medians, "paired_speedup": paired,
        "all_correct": True,
        "mean_sat_calls": {arm: round(statistics.mean(
            r["sat_calls"] for r in rows if r["arm"] == arm), 2)
            for arm in ARMS},
    }, sort_keys=True), flush=True)


def audit(paths, out):
    need(len(paths) == len(SIZES), "five cohorts required")
    records = [load(x) for x in paths]
    need([r["n"] for r in records] == list(SIZES),
         "missing/duplicate/unordered cohort")
    for obj in records:
        need(obj["protocol"] == PROTO and obj["partial"] is False
             and obj["source_SHA256"] == SOURCE_SHA
             and obj["R9_reference_run"] == R9_RUN
             and obj["R10_reference_run"] == R10_REF_RUN
             and obj["all_correct"] and obj["independent_FBA"]
             and len(obj["rows"]) == REPS*len(ARMS),
             "R14 cohort not certified complete")
        need(len({r["gene_SHA256"] for r in obj["rows"]}) == 1
             and all(x["source_SHA256"] == SOURCE_SHA
                     and x["reference_match"] and x["independent_FBA_verified"]
                     and x["minimal_count"] == obj["expected_minimal_count"]
                     and x["wall_s"] <= CAP
                     for x in obj["rows"]),
             "R14 SAT/biology truth or timing invalid")
        for arm in ARMS:
            hits = sorted((r for r in obj["rows"] if r["arm"] == arm),
                          key=lambda x: x["rep"])
            need([x["rep"] for x in hits] == list(range(REPS)),
                 "missing paired trials")
            want = 1 if arm == "shared_gated" else 3
            need(all(x["bridge"]["solver_creations"] == want for x in hits),
                 "misleading solver reuse claim")
    median_ratios = {
        str(obj["n"]): {
            arm: round(obj["median_wall_s"]["baseline"] /
                       obj["median_wall_s"][arm], 6)
            for arm in ARMS[1:]}
        for obj in records
    }
    wins = {arm: sum(obj["median_wall_s"][arm] <
                     obj["median_wall_s"]["baseline"] for obj in records)
            for arm in ARMS[1:]}
    report = {
        "protocol": PROTO,
        "status": "COMPLETE_CORRECT_FULL_BIOLOGY_PAIRED",
        "R9_reference_run": R9_RUN, "R10_reference_run": R10_REF_RUN,
        "source_SHA256": SOURCE_SHA,
        "sizes": list(SIZES), "arms": list(ARMS), "repetitions": REPS,
        "trials": sum(len(x["rows"]) for x in records),
        "cohorts": [{"n": x["n"], "medians_s": x["median_wall_s"],
                     "paired_speedup": x["paired_base_over_arm"],
                     "median_speedup": median_ratios[str(x["n"])],
                     "expected_minimal_count": x["expected_minimal_count"],
                     "all_correct": x["all_correct"]}
                    for x in records],
        "median_speedup_by_cohort": median_ratios,
        "wins_on_cohorts": wins,
        "no_promotion_until_new_blind_confirmation": True,
        "baseline_R9_already_incremental_within_each_k": True,
        "experimental_reuse_across_k_only": True,
        "full_bacterial_iML1515_CEGAR_gMCS_pipeline_measured": True,
        "not_R195_native_CaDiCaL": True,
        "not_human_cancer": True,
        "no_general_complexity_claim": True,
        "no_exhaustive_completeness_above_48": True,
    }
    save(out, report)
    print("R14_FINAL", json.dumps(report, sort_keys=True), flush=True)


def selftest():
    need(SIZES == (24, 48, 96, 192, 384) and REPS == 3
         and len(ARMS) == 3 and CAP == 150.,
         "protocol drift")
    from pysat.solvers import Solver
    # Pre-flight assumption-based gated stage independence and retained state
    # on synthetic CNF without any biomed assertion.
    with Solver(name="cadical195", bootstrap_with=[[1, 2]]) as solver:
        a1, a2 = 5, 6
        solver.add_clause([-a1, 1])
        solver.add_clause([-a2, -1])
        need(solver.solve(assumptions=[a1, -a2]), "stage1 inconsistent")
        need(solver.solve(assumptions=[a2, -a1]), "stage2 inconsistent")
        need(not solver.solve(assumptions=[a1, a2]), "incompatible stages leaked")
    print("R14_SELFTEST_PASS", json.dumps({
        "arms": ARMS, "sizes": SIZES, "reps": REPS,
        "gate_assumptions": "SAT/SAT/UNSAT independent stages",
    }), flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("selftest", "cohort", "audit"))
    p.add_argument("--source", default="r14/r9/source")
    p.add_argument("--frozen", default="r14/r9/frozen")
    p.add_argument("--reference", default="r14/reference/summary.json")
    p.add_argument("--n", type=int)
    p.add_argument("--out", default="r14/result.json")
    p.add_argument("--inputs", nargs="*")
    a = p.parse_args()
    if a.action == "selftest":
        selftest()
    elif a.action == "cohort":
        need(a.n is not None, "cohort size required")
        cohort(a.source, a.frozen, a.reference, a.n, a.out)
    else:
        audit(a.inputs or [], a.out)
