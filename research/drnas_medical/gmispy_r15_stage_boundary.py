#!/usr/bin/env python3
"""DRNAS Medical R15: stage-boundary ablation on R9 exact bacterial iML1515.

Goal: locate whether keeping the CaDiCaL process state across k=1->2 or
k=2->3 helps, without changing gene-KO search, objective or frozen reference.

Predeclared arms:
 baseline: 3 independent R9 CaDiCaL solvers, unmodified.
 gated_fresh: 3 new R14 gated solvers; control for activation-clause overhead.
 share_12: same gated solver for k=1 and k=2; fresh solver for k=3.
 share_23: fresh gated solver for k=1; same solver for k=2 and k=3.
 share_all: one gated solver for all three stages, same as R14 shared_gated.

This is a causal ABLATION OF SOLVER STATE LIFETIME, not an isolation of
learned clauses from variable-activity, search history, or other CDCL state.
All arms are verified against frozen R10 gene-intervention sets and
independent gene-vs-reaction knockout FBA.
"""
from __future__ import annotations
import argparse
import json
import pathlib
import statistics
import time
from unittest.mock import patch

from pysat.solvers import Solver as OriginalSolver

import gmispy_r9_scaling as r9
import gmispy_r8_iml1515 as r8
import gmispy_r11_phenotype_cache as r11
import gmispy_r14_cross_stage as r14

PROTO = "DRNAS-MEDICAL-R15-STAGE-BOUNDARY-ABLATION-20261107-v1"
SOURCE_SHA = r14.SOURCE_SHA
R9_RUN, R10_RUN, R14_RUN = r14.R9_RUN, r14.R10_REF_RUN, 42337828969
SIZES = (24, 48, 96, 192, 384)
ARMS = ("baseline", "gated_fresh", "share_12", "share_23", "share_all")
REPS = 3
CAP = 150.0
# Segment equality is the ONLY manipulated solver-lifetime boundary.
SEGMENTS = {
    "gated_fresh": (0, 1, 2),
    "share_12": (0, 0, 1),
    "share_23": (0, 1, 1),
    "share_all": (0, 0, 0),
}
EXPECTED_CONSTRUCTS = {
    "baseline": 3, "gated_fresh": 3, "share_12": 2,
    "share_23": 2, "share_all": 1,
}
need = r14.need
save = r14.save
load = r14.load
canon = r14.canon


class BoundaryCoordinator(r14.StageCoordinator):
    """Use identical R14 clause/gate logic; only reset solver at chosen boundary.

    We force the base R14 coordinator into its native shared_gated path,
    so all exact stage CNF, activation literal, GPR and witness logic is
    identical. Replacing the underlying solver is the only structural change.
    """

    def __init__(self, original_cls, genes, rules, arm):
        need(arm in SEGMENTS, "unsupported R15 boundary arm")
        super().__init__(original_cls, genes, rules, "shared_gated")
        self.r15_arm = arm
        self.segment_map = SEGMENTS[arm]
        self.active_segment = None
        self.boundary_reset_after_k = []
        self.all_global_witness_cuts = set()

    def factory(self, *args, **kwargs):
        need(self.instantiated < 3, "too many SAT stages")
        index = self.instantiated
        segment = self.segment_map[index]
        if self.active_segment is not None and segment != self.active_segment:
            # Reset entire CDCL solver across one boundary, preserving ONLY
            # certified global witness cuts through R9 bootstrap on next stage.
            need(self.shared is not None, "lost prior stage solver")
            self.shared.delete()
            self.shared = None
            self.global_witness_clauses = set()
            self.boundary_reset_after_k.append(index)
        self.active_segment = segment
        stage = super().factory(*args, **kwargs)
        self.all_global_witness_cuts.update(self.global_witness_clauses)
        return stage

    def audit(self):
        need(self.instantiated == 3 and len(self.stages) == 3,
             "not all 3 cardinalities visited")
        want = EXPECTED_CONSTRUCTS[self.r15_arm]
        need(self.solver_creations == want,
             "incorrect stage-boundary solver lifetime")
        reset_expected = [
            i for i in (1, 2)
            if self.segment_map[i] != self.segment_map[i-1]
        ]
        need(self.boundary_reset_after_k == reset_expected,
             "unanticipated reset boundary")
        return {
            "solver_creations": self.solver_creations,
            "segment_map": list(self.segment_map),
            "boundary_reset_after_k": self.boundary_reset_after_k,
            "cross_stage_same_solver": want < 3,
            "native_sat_calls": sum(x.calls for x in self.stages),
            "native_sat_call_seconds": round(sum(x.sat_s for x in self.stages), 7),
            "stage_sat_call_seconds": [round(x.sat_s, 7) for x in self.stages],
            "stage_sat_calls": [x.calls for x in self.stages],
            "stage_add_clause_calls": [x.adds for x in self.stages],
            "globally_certified_witness_cuts": len(self.all_global_witness_cuts),
            "gate_literals": list(self.activation_literals),
        }


def run_trial(model, genes, rules, threshold, expected, arm, rep, n):
    need(arm in ARMS and rep in range(REPS), "invalid trial assignment")
    t = time.perf_counter()
    if arm == "baseline":
        result = r9.solve(model, genes, rules, threshold, CAP)
        detail = {
            "solver_creations": 3,
            "segment_map": [0,1,2],
            "boundary_reset_after_k": [1,2],
            "cross_stage_same_solver": False,
            "native_sat_calls": result["sat_calls"],
            "stage_sat_call_seconds": None,
            "stage_sat_calls": None,
            "native_sat_call_seconds": None,
        }
    else:
        coordinator = BoundaryCoordinator(OriginalSolver, genes, rules, arm)
        try:
            with patch("pysat.solvers.Solver", coordinator.factory):
                result = r9.solve(model, genes, rules, threshold, CAP)
        finally:
            coordinator.close()
        detail = coordinator.audit()
        need(result["sat_calls"] == detail["native_sat_calls"],
             "SAT call accounting mismatch")
    driver_s = time.perf_counter() - t
    need(result["status"] == "SOLVED" and result["SAT_UNSAT_stages"] == 3,
         "missing complete three-stage search")
    need(canon(result["minimal_sets"]) == canon(expected),
         "result differs from R10 frozen biomed reference")
    independent = r9.verify_sets(model, genes, rules, threshold,
                                 result["minimal_sets"])
    need(independent["sound_minimal"],
         "independent gene/reaction LP minimality failed")
    stages = result["stages"]
    need([x["k"] for x in stages] == [1, 2, 3], "R9 stage order drift")
    stage_wall = [stages[0]["wall_elapsed_s"]] + [
        round(stages[i]["wall_elapsed_s"]-stages[i-1]["wall_elapsed_s"],6)
        for i in (1,2)
    ]
    stage_lp = [stages[0]["lp_calls_total"]] + [
        stages[i]["lp_calls_total"]-stages[i-1]["lp_calls_total"]
        for i in (1,2)
    ]
    stage_flux = [stages[0]["flux_cuts_total"]] + [
        stages[i]["flux_cuts_total"]-stages[i-1]["flux_cuts_total"]
        for i in (1,2)
    ]
    return {
        "protocol": PROTO, "n": n, "rep": rep, "arm": arm,
        "wall_s": result["wall_s"], "driver_s": round(driver_s, 6),
        "stage_wall_s": stage_wall, "stage_LP_calls": stage_lp,
        "stage_flux_cuts": stage_flux,
        "stage_minimal_solutions": [x["solutions"] for x in stages],
        "SAT_calls": result["sat_calls"], "LP_calls": result["lp_calls"],
        "flux_cuts": result["flux_cuts"], "minimal_sets": result["minimal_sets"],
        "minimal_count": len(expected), "reference_match": True,
        "independent_gene_and_reaction_FBA": independent["sound_minimal"],
        "independent_checks": independent["independent_checks"],
        "bridge": detail, "source_SHA256": SOURCE_SHA,
        "gene_SHA256": r9.hgenes(genes), "R10_reference_run": R10_RUN,
        "R9_reference_run": R9_RUN,
        "exhaustive_reference_only_24_48": n in (24,48),
        "not_native_R195": True, "not_human_cancer": True,
    }


def cohort(source, frozen, reference, n, out):
    need(n in SIZES, "unplanned cohort")
    genes, expected = r11.frozen_reference(source, frozen, reference, n)
    check_model, check_manifest = r8.load_frozen(source)
    threshold = float(check_manifest["wildtype_biomass"])*.01
    del check_model
    need(len(genes) == n and threshold > 0, "model mismatch")
    rows = []
    for rep in range(REPS):
        arms = ARMS[rep:]+ARMS[:rep]
        for arm in arms:
            # Clean COBRA GLPK state PER ARM as proven necessary in R14.
            model, manifest = r8.load_frozen(source)
            need(abs(float(manifest["wildtype_biomass"])*.01-threshold) < 1e-12,
                 "frozen biomass drift")
            rules = r8.all_rules(model)
            row = run_trial(model, genes, rules, threshold, expected,
                            arm, rep, n)
            rows.append(row)
            save(out, {"protocol": PROTO, "partial": True, "n": n,
                       "rows": rows})
            print("R15_TRIAL", json.dumps({
                k: row[k] for k in ("n","rep","arm","wall_s","SAT_calls",
                                   "LP_calls","flux_cuts","stage_wall_s",
                                   "stage_LP_calls","reference_match")
            }, sort_keys=True), flush=True)
    need(len(rows) == REPS*len(ARMS), "incomplete paired matrix")
    med = {arm: round(statistics.median(
        x["wall_s"] for x in rows if x["arm"] == arm), 6)
        for arm in ARMS}
    ratios = {arm: [
        round(b["wall_s"]/a["wall_s"], 6)
        for b,a in zip(
            sorted((x for x in rows if x["arm"]=="baseline"),
                   key=lambda x:x["rep"]),
            sorted((x for x in rows if x["arm"]==arm),
                   key=lambda x:x["rep"])
        )
    ] for arm in ARMS[1:]}
    # Stage-level LP / solve-time data are diagnostic, NOT an independent
    # proof that learnt clauses alone caused any observed improvement.
    stage_medians = {arm: {
        "seconds": [round(statistics.median(
            x["stage_wall_s"][i] for x in rows if x["arm"] == arm),6)
            for i in range(3)],
        "LP_calls": [statistics.median(
            x["stage_LP_calls"][i] for x in rows if x["arm"] == arm)
            for i in range(3)],
        "SAT_calls": [
            (statistics.median(x["bridge"]["stage_sat_calls"][i]
                for x in rows if x["arm"]==arm)
             if arm != "baseline" else None) for i in range(3)],
    } for arm in ARMS}
    report = {
        "protocol": PROTO, "partial": False, "n": n,
        "source_SHA256": SOURCE_SHA, "gene_SHA256": r9.hgenes(genes),
        "R9_reference_run": R9_RUN, "R10_reference_run": R10_RUN,
        "R14_preceding_run": R14_RUN, "all_reference_correct": True,
        "all_independent_FBA_correct": True, "expected_count": len(expected),
        "rows": rows, "median_wall_s": med,
        "paired_base_over_arm": ratios, "stage_medians": stage_medians,
        "separate_clean_COBRA_model_per_trial": True,
        "solver_loading_excluded_from_timed_R9_wall": True,
        "result_is_state_lifetime_ablation_not_learnt_clause_isolation": True,
        "no_blind_unseen_biological_cohort": True,
    }
    save(out, report)
    print("R15_COHORT_FINAL",json.dumps({
        "n":n, "median_s":med,"paired_speedup":ratios,
        "stage_medians":stage_medians, "all_correct":True,
    },sort_keys=True),flush=True)


def audit(paths, out):
    need(len(paths) == len(SIZES), "five complete cohorts required")
    records=[load(x) for x in paths]
    need([x["n"] for x in records]==list(SIZES),
         "missing or unordered cohort")
    for obj in records:
        need(obj["protocol"]==PROTO and obj["partial"] is False
             and obj["source_SHA256"]==SOURCE_SHA
             and obj["R9_reference_run"]==R9_RUN
             and obj["R10_reference_run"]==R10_RUN
             and obj["all_reference_correct"] and obj["all_independent_FBA_correct"]
             and len(obj["rows"])==REPS*len(ARMS), "incomplete evidence")
        need(len({x["gene_SHA256"] for x in obj["rows"]})==1,
             "gene cohort drift")
        for arm in ARMS:
            series=sorted((x for x in obj["rows"] if x["arm"]==arm),
                          key=lambda x:x["rep"])
            need([x["rep"] for x in series]==list(range(REPS)),
                 "missing or repeated trial")
            need(all(x["bridge"]["solver_creations"]==EXPECTED_CONSTRUCTS[arm]
                     and x["bridge"]["segment_map"]==(
                         list(SEGMENTS[arm]) if arm in SEGMENTS else [0,1,2])
                     and x["reference_match"]
                     and x["independent_gene_and_reaction_FBA"]
                     and x["wall_s"]<=CAP
                     and x["minimal_count"]==obj["expected_count"]
                     and x["source_SHA256"]==SOURCE_SHA
                     for x in series),
                 "solver lifetime / biomedical reference failure")
    speedup={str(x["n"]): {
        arm:round(x["median_wall_s"]["baseline"]/x["median_wall_s"][arm],6)
        for arm in ARMS[1:]} for x in records}
    winner={arm:sum(x["median_wall_s"][arm] <
                    x["median_wall_s"]["baseline"] for x in records)
            for arm in ARMS[1:]}
    final={
        "protocol":PROTO, "status":"COMPLETE_STAGE_BOUNDARY_ABLATION",
        "R9_reference_run":R9_RUN,"R10_reference_run":R10_RUN,
        "R14_preceding_run":R14_RUN,
        "sizes":list(SIZES),"arms":list(ARMS),"repetitions":REPS,
        "total_trials":sum(len(x["rows"]) for x in records),
        "source_SHA256":SOURCE_SHA,
        "cohorts":[{
            "n":x["n"], "medians_s":x["median_wall_s"],
            "paired_ratio":x["paired_base_over_arm"],
            "stage_medians":x["stage_medians"],
            "expected_count":x["expected_count"],
            "all_correct":True
        } for x in records],
        "speedup_median_by_cohort":speedup,
        "wins_on_cohorts":winner,
        "conclusion_scope":"observed R9 solver-state persistence, not isolated learned clauses",
        "not_independent_blind_holdout":True,
        "no_clinical_or_human_cancer_claim":True,
        "no_general_complexity_claim":True,
        "not_native_DRNAS_R195":True,
        "full_bacterial_iML1515_CEGAR_pipeline_measured":True,
    }
    save(out, final)
    print("R15_FINAL",json.dumps(final,sort_keys=True),flush=True)


def selftest():
    from pysat.solvers import Solver
    need(len(ARMS)==5 and REPS==3 and CAP==150.0
         and SIZES==(24,48,96,192,384), "protocol drift")
    need({arm:sum(1 for i in range(3)
                  if i==0 or SEGMENTS[arm][i]!=SEGMENTS[arm][i-1])
          for arm in SEGMENTS}==
         {arm:EXPECTED_CONSTRUCTS[arm] for arm in SEGMENTS},
         "boundary segments disagree with expected construction count")
    # Synthetic stage-gating fail-closed preflight.
    with Solver(name="cadical195", bootstrap_with=[[1,2]]) as s:
        a,b=7,8
        s.add_clause([-a,1])
        s.add_clause([-b,-1])
        need(s.solve(assumptions=[a,-b]), "stage1 unsound")
        need(s.solve(assumptions=[-a,b]), "stage2 unsound")
        need(not s.solve(assumptions=[a,b]), "stage isolation broken")
    print("R15_SELFTEST_PASS",json.dumps({
        "arms":ARMS, "segments":SEGMENTS, "sizes":SIZES,
        "expected_creations":EXPECTED_CONSTRUCTS
    },sort_keys=True),flush=True)


if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","cohort","audit"))
    p.add_argument("--source",default="r15/r9/source")
    p.add_argument("--frozen",default="r15/r9/frozen")
    p.add_argument("--reference",default="r15/reference/summary.json")
    p.add_argument("--n",type=int)
    p.add_argument("--out",default="r15/result.json")
    p.add_argument("--inputs",nargs="*")
    a=p.parse_args()
    if a.action=="selftest":
        selftest()
    elif a.action=="cohort":
        need(a.n is not None,"--n required")
        cohort(a.source,a.frozen,a.reference,a.n,a.out)
    else:
        audit(a.inputs or [],a.out)
