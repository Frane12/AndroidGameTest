#!/usr/bin/env python3
"""DRNAS MRE2-CDCL-P1: two real official SAT2026 sources, live native CDCL counters.

The C++ CryptoMiniSat 5.11.15 native adapter reports its ACTUAL solver
propagations, conflicts, and decisions after solving the CNF. Adding replay-
certified CRR clauses changes the native watched-clause/BCP search, not just
pre-solve unit-propagation probes.

These counts are solver-global, not per-lemma callbacks. This experiment does
NOT assert a true in-CDCL DRNAS callback or independent UNSAT LRAT.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import pathlib
import random
import statistics
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import mre1_cross_representation as mre1
import mre2_impact_gate as mre2
import r195_native_cms_benchmark as r195
import r164_pure_exact_gf2 as exact

PROTOCOL = "DRNAS-MRE2-CDCL-TWO-OFFICIAL-5ARM-2SEED-2REPEAT-v1"
ROOT = pathlib.Path("mre2_cdcl_p1")
CASES = (
    "official-28dcc4119e1bbb5fbd3fdd8f4140f28d.cnf",
    "official-12cd0c3196589ac8105653cbfe613fc6.cnf",
)
# Baseline XOR, all CRR clauses, selected impact-gate CRR clauses, shadow
# (same pre-solve work, no import), and native CMS without imported XORs.
MODES = ("xor_baseline", "crr_all", "crr_gate", "crr_shadow", "cms_native")
REPS = 2
REPEATS = 2
CAP = 22.0


def need(ok, msg):
    if not ok:
        raise RuntimeError("MRE2_CDCL_P1_FAIL_CLOSED " + str(msg))


def select_case(case_no):
    need(0 <= case_no < len(CASES), "case index")
    matched = [c for c in r195.cases() if c["name"] == CASES[case_no]]
    need(len(matched) == 1 and matched[0]["cohort"] == "reused_official_2026",
         "missing SHA-pinned original SAT2026 case")
    return matched[0]


def trial(case, rep, repeat, mode, binary):
    source = r195.FROZEN / case["name"]
    start = time.perf_counter()
    need(r195.digest(source) == case["sha256"], "source SHA drift")
    n, original = exact.parse_dimacs(source)
    rows, proofs, selected = [], [], []
    gate_info = {"selected": 0, "probed": 0, "new_conflicts": 0,
                 "new_implications": 0, "impact_score": 0}
    if mode != "cms_native":
        if mode == "xor_baseline":
            rows = r195.certified_source_rows(original)[:mre1.MAX_SOURCE_ROWS]
            mre1.replay_source_xors(original, rows)
        else:
            rows, proofs, derivation = mre1.derive(original)
            need(derivation["proof_replayed"], "missing certified CRR proof replay")
            if mode in ("crr_gate", "crr_shadow"):
                selected, gate_info = mre2.gate(original, proofs)
                need(len(selected) <= len(proofs), "gate imported unknown lemma")
                available = {tuple(p["clause"]) for p in proofs}
                need(all(tuple(p["clause"]) in available for p in selected),
                     "selected lemma not proof-certified")
    prep_s = time.perf_counter()-start
    if mode == "crr_all":
        imported = proofs
    elif mode == "crr_gate":
        imported = selected
    else:
        imported = []
    seed = int(hashlib.sha256((mre2.PROTO+case["sha256"]+str(rep))
                              .encode()).hexdigest()[:8],16)
    bridge_mode = "cms_native" if mode == "cms_native" else "source_xor_no_gauss"
    status, model, stats = "TIMEOUT", {}, {}
    solver_wall_s = None
    with tempfile.TemporaryDirectory(prefix="drnas-mre2-cdcl-") as d:
        d = pathlib.Path(d)
        cnf, xor, empty = d/"input.cnf", d/"certified.tsv", d/"empty.tsv"
        mre1.write_cnf(cnf, n, original, imported)
        mre1.write_xors(xor, rows)
        empty.write_text("")
        remaining = CAP-(time.perf_counter()-start)
        if remaining >= 0.10:
            t = time.perf_counter()
            try:
                p = subprocess.run(
                    [str(pathlib.Path(binary).resolve()), str(cnf),
                     str(xor), str(empty), bridge_mode, str(seed)],
                    capture_output=True, text=True, timeout=remaining, check=False)
            except subprocess.TimeoutExpired:
                p = None
            solver_wall_s = time.perf_counter()-t
            if p is not None:
                need(p.returncode == 0,
                     "CMS native error (including invalid SAT witness): "+p.stderr[-800:])
                status, model, stats = r195.parsed_native(p.stdout)
                if status == "SAT":
                    r195.verify_model(source, model)
                if status in ("SAT", "UNSAT"):
                    for field in ("propagations", "conflicts", "decisions"):
                        need(field in stats and stats[field] is not None,
                             "missing native CDCL counter "+field)
    wall_s = time.perf_counter()-start
    if wall_s >= CAP:
        status = "TIMEOUT"
    if status != "TIMEOUT":
        need(status == case["expected"], "solver verdict mismatch")
    return dict(protocol=PROTOCOL, case=case["name"],
                cohort=case["cohort"], sha256=case["sha256"],
                rep=rep, repeat=repeat, native_seed=seed, mode=mode,
                status=status, cap_s=CAP, wall_s=round(wall_s,6),
                solver_wall_s=(round(solver_wall_s,6)
                               if solver_wall_s is not None else None),
                prep_s=round(prep_s,6),
                par2_s=round(CAP*2 if status=="TIMEOUT" else wall_s,6),
                native_cdcl_propagations=stats.get("propagations"),
                native_cdcl_conflicts=stats.get("conflicts"),
                native_cdcl_decisions=stats.get("decisions"),
                source_xors=len(rows),
                derived_certified=len(proofs),
                imported_certified=len(imported),
                gate=gate_info,
                otf_gauss=False, cnf_original_preserved=True,
                proof=("ORIGINAL_CNF_SAT_MODEL_CHECKED" if status=="SAT"
                       else "UNSAT_NO_INDEPENDENT_LRAT" if status=="UNSAT"
                       else "CAP_TIMEOUT"),
                provenance_sha=os.environ.get("GITHUB_SHA","local"))


def run_case(case_no, binary):
    case = select_case(case_no)
    ROOT.mkdir(parents=True,exist_ok=True)
    result_path = ROOT/("case-%d.json" % case_no)
    rows = []
    for rep in range(REPS):
        for repeat in range(REPEATS):
            modes = list(MODES)
            random.Random(PROTOCOL + case["sha256"] +
                          str(rep) + ":" + str(repeat)).shuffle(modes)
            for mode in modes:
                row = trial(case, rep, repeat, mode, binary)
                rows.append(row)
                result_path.write_text(json.dumps(rows,sort_keys=True)+"\n")
                print("MRE2_CDCL_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==REPS*REPEATS*len(MODES)==20,"incomplete targeted trial count")
    print("MRE2_CDCL_CASE_PASS",case_no,len(rows),flush=True)


def audit():
    rows = []
    for i in range(len(CASES)):
        rows.extend(json.loads((ROOT/("case-%d.json" % i)).read_text()))
    need(len(rows)==len(CASES)*REPS*REPEATS*len(MODES)==40,
         "missing paired trials")
    paired = collections.defaultdict(dict)
    for row in rows:
        need(row["protocol"]==PROTOCOL and row["otf_gauss"] is False,
             "mismatched protocol/OTF Gauss")
        need(row["sha256"] == select_case(CASES.index(row["case"]))["sha256"],
             "case source mismatch")
        pair=(row["sha256"],row["rep"],row["repeat"])
        need(row["mode"] not in paired[pair],"duplicate mode")
        paired[pair][row["mode"]] = row
        if row["status"]=="SAT":
            need(row["proof"]=="ORIGINAL_CNF_SAT_MODEL_CHECKED",
                 "SAT witness not verified")
    output=[]
    for key,p in paired.items():
        need(set(p)==set(MODES),"missing arms")
        need(len({v["status"] for v in p.values()
                  if v["status"]!="TIMEOUT"}) <= 1,
             "paired SAT/UNSAT disagreement")
        base=p["xor_baseline"]
        for mode in MODES:
            row=p[mode]
            output.append(dict(case=row["case"],rep=row["rep"],
                               repeat=row["repeat"],mode=mode,
                               time_delta_vs_xor_s=round(row["wall_s"]-base["wall_s"],6),
                               decisions_delta_vs_xor=(
                                   row["native_cdcl_decisions"]-base["native_cdcl_decisions"]
                                   if row["native_cdcl_decisions"] is not None
                                   and base["native_cdcl_decisions"] is not None else None),
                               conflicts_delta_vs_xor=(
                                   row["native_cdcl_conflicts"]-base["native_cdcl_conflicts"]
                                   if row["native_cdcl_conflicts"] is not None
                                   and base["native_cdcl_conflicts"] is not None else None),
                               propagations_delta_vs_xor=(
                                   row["native_cdcl_propagations"]-
                                   base["native_cdcl_propagations"]
                                   if row["native_cdcl_propagations"] is not None
                                   and base["native_cdcl_propagations"] is not None else None)))
    grouped = collections.defaultdict(list)
    for row in rows:
        grouped[(row["case"],row["mode"])].append(row)
    totals = {}
    for case in CASES:
        totals[case]={}
        for mode in MODES:
            d=grouped[(case,mode)]
            totals[case][mode]=dict(
                attempts=len(d),
                solved=sum(x["status"]!="TIMEOUT" for x in d),
                par2_s=round(sum(x["par2_s"] for x in d),6),
                median_wall_s=round(statistics.median(x["wall_s"] for x in d),6),
                median_solver_s=round(statistics.median(x["solver_wall_s"]
                    for x in d if x["solver_wall_s"] is not None),6),
                prep_total_s=round(sum(x["prep_s"] for x in d),6),
                mean_cdcl_propagations=round(statistics.mean(
                    x["native_cdcl_propagations"] for x in d
                    if x["native_cdcl_propagations"] is not None),2),
                mean_cdcl_decisions=round(statistics.mean(
                    x["native_cdcl_decisions"] for x in d
                    if x["native_cdcl_decisions"] is not None),2),
                mean_cdcl_conflicts=round(statistics.mean(
                    x["native_cdcl_conflicts"] for x in d
                    if x["native_cdcl_conflicts"] is not None),2),
                imported_lemmas=sum(x["imported_certified"] for x in d),
                source_xors=sum(x["source_xors"] for x in d))
    report=dict(protocol=PROTOCOL, measurements=len(rows),
                case_count=len(CASES),
                repetitions_per_mode_per_case=REPS*REPEATS,
                all_OTF_gauss_disabled=True,
                true_native_CDCL_counters=True,
                NOT_per_lemma_activation_telemetry=True,
                original_SAT_witness_independently_checked=True,
                independent_UNSAT_LRAT=False,
                development_sources_reused_NOT_blind=True,
                totals=totals,paired_deltas=output)
    (ROOT/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    print("MRE2_CDCL_FINAL",json.dumps(report,sort_keys=True),flush=True)


def selftest():
    need(len(CASES)==2 and REPS*REPEATS*len(MODES)==20,
         "pilot protocol error")
    # MRE2 proof replay, selected gate and original-CNF witness verification
    # independently validated by their respective self-tests in CI.
    print("MRE2_CDCL_SELFTEST_PASS",PROTOCOL,flush=True)


if __name__ == "__main__":
    arg=argparse.ArgumentParser()
    arg.add_argument("action",choices=("selftest","case","audit"))
    arg.add_argument("--case-no",type=int,default=0)
    arg.add_argument("--binary",default="mre2_cdcl_p1/native")
    args=arg.parse_args()
    if args.action=="selftest":
        selftest()
    elif args.action=="case":
        run_case(args.case_no,args.binary)
    else:
        audit()
