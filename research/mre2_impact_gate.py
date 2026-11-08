#!/usr/bin/env python3
"""DRNAS MRE2: proof-replayed cross-representation lemmas + bounded
single-assumption unit-propagation impact gate.

NOT a live CDCL trail observer. This is a pre-solve impact predictor. Every
lemma is verified as a logical consequence of ORIGINAL CNF before gating.
Compare all arms with OTF Gauss OFF to isolate the effect of added CNF lemmas.
SAT witnesses are checked against ORIGINAL CNF; UNSAT lacks independent LRAT.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import pathlib
import random
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import mre1_cross_representation as mre1
import r195_native_cms_benchmark as r195
import r164_pure_exact_gf2 as exact

PROTO = "DRNAS-MRE2-IMPACT-GATE-32SHA-5ARM-2REP-30S-v1"
MODES = ("cms_native", "xor_no_otf", "mre1_all_no_otf",
         "mre2_shadow_no_otf", "mre2_active_no_otf")
CAP, REPS, SHARDS = 30.0, 2, 8
ROOT = pathlib.Path("mre2")
GATE_BUDGET_S = 0.45
MAX_GATE_CNF = 35000
MAX_GATE_CANDIDATES = 96
MAX_SELECTED = 20
MIN_BINARY_IMPACT = 2


def need(ok, reason):
    if not ok:
        raise RuntimeError("MRE2_FAIL_CLOSED " + str(reason))


class BCPProbe:
    """Sound CNF unit-propagation closure for a few short assumed trails.

    Records all original clauses; on each assigned literal only visits clauses
    containing its negation. Selected proven lemmas are added incrementally.
    This is not a CDCL callback and makes no claim about solver heuristics.
    """
    def __init__(self, clauses):
        self.by_literal = collections.defaultdict(list)
        self.units = []
        self.has_empty = False
        for clause in clauses:
            self.add(tuple(clause))

    def add(self, clause):
        if len(clause) == 0:
            self.has_empty = True
        elif len(clause) == 1:
            self.units.append(clause[0])
        for literal in clause:
            self.by_literal[literal].append(clause)

    def closure(self, assumptions=()):
        if self.has_empty:
            return False, {}
        q = collections.deque(self.units)
        q.extend(assumptions)
        assignments = {}
        while q:
            lit = q.popleft()
            var, value = abs(lit), lit > 0
            if var in assignments:
                if assignments[var] != value:
                    return False, assignments
                continue
            assignments[var] = value
            for clause in self.by_literal.get(-lit, ()):
                unknown = 0
                last = 0
                satisfied = False
                for other in clause:
                    assigned = assignments.get(abs(other))
                    if assigned is None:
                        unknown += 1
                        last = other
                    elif assigned == (other > 0):
                        satisfied = True
                        break
                if not satisfied:
                    if unknown == 0:
                        return False, assignments
                    if unknown == 1:
                        q.append(last)
        return True, assignments


def gate(original, proofs, budget_s=GATE_BUDGET_S):
    """Choose short *already certified* lemmas whose bounded UP probes help.

    Binary (a v b): examine the original CNF's UP closure under ~a and ~b.
    Measure newly forced literals/conflicts when b or a is added. Require
    >=2 points to avoid importing every merely non-duplicated implication.
    Chosen lemmas are included in subsequent probe baselines.
    """
    began = time.perf_counter()
    stats = dict(probed=0, considered=0, selected=0, rejected=0,
                 novel_units=0, new_implications=0, new_conflicts=0,
                 impact_score=0, gate_s=0.0, abstain=None,
                 budget_exhausted=False, method="bounded_original_CNF_UP")
    if len(original) > MAX_GATE_CNF:
        stats["abstain"] = "large_cnf"
        stats["gate_s"] = round(time.perf_counter()-began, 6)
        return [], stats
    probe = BCPProbe(original)
    root_ok, root = probe.closure()
    if not root_ok:
        stats["abstain"] = "original_root_UP_unsat"
        stats["gate_s"] = round(time.perf_counter()-began, 6)
        return [], stats

    selected = []
    for record in proofs[:MAX_GATE_CANDIDATES]:
        if len(selected) >= MAX_SELECTED:
            stats["abstain"] = "selected_cap"
            break
        if time.perf_counter()-began >= budget_s:
            stats["budget_exhausted"] = True
            stats["abstain"] = "gate_cpu_cap"
            break
        clause = tuple(record["clause"])
        stats["considered"] += 1
        impact = 0
        implications = 0
        conflicts = 0
        if len(clause) == 0:
            # Empty clause is replay-certified; must be imported.
            impact = 100
            conflicts = 1
        elif len(clause) == 1:
            lit = clause[0]
            existing = root.get(abs(lit))
            if existing is None:
                ok2, afterward = probe.closure((lit,))
                implications = max(1, len(afterward)-len(root))
                conflicts = int(not ok2)
                impact = 2 + implications + 8*conflicts
            elif existing != (lit > 0):
                impact = 100
                conflicts = 1
        elif len(clause) == 2:
            a, b = clause
            for assumed, implied in ((-a, b), (-b, a)):
                if time.perf_counter()-began >= budget_s:
                    stats["budget_exhausted"] = True
                    break
                ok_before, before = probe.closure((assumed,))
                stats["probed"] += 1
                if not ok_before:
                    continue
                if before.get(abs(implied)) == (implied > 0):
                    continue
                ok_after, after = probe.closure((assumed, implied))
                stats["probed"] += 1
                if not ok_after:
                    conflicts += 1
                    impact += 8
                else:
                    delta = len(after)-len(before)
                    if delta > 0:
                        implications += delta
                        impact += delta
        # Every accepted lemma remains independently certified by MRE1.
        accept = impact >= (MIN_BINARY_IMPACT if len(clause) == 2 else 1)
        if accept:
            selected.append(record)
            probe.add(clause)
            root_ok, root = probe.closure()
            stats["novel_units"] += int(len(clause) <= 1)
            stats["new_implications"] += implications
            stats["new_conflicts"] += conflicts
            stats["impact_score"] += impact
            if not root_ok:
                stats["abstain"] = "root_conflict_after_proven_lemma"
                break
        else:
            stats["rejected"] += 1
        if stats["budget_exhausted"]:
            stats["abstain"] = "gate_cpu_cap"
            break
    stats["selected"] = len(selected)
    stats["gate_s"] = round(time.perf_counter()-began, 6)
    return selected, stats


def selftest():
    # Complete parity-CNF blocks prove x1=1 although original UP cannot.
    original = (r195.xor_cnf((1, 2, 3), 0)
                + r195.xor_cnf((2, 3), 1)
                + [(4, 5), (-4, 6), (-6, 5)])
    source, proofs, stats = mre1.derive(original, max_s=5)
    need(stats["proof_replayed"] and proofs, "MRE1 proofs missing")
    mre1.verify_proofs(original, source, proofs)
    selected, g = gate(original, proofs, budget_s=5)
    selected_clauses = {tuple(p["clause"]) for p in selected}
    need((1,) in selected_clauses, "novel GF2 unit not accepted")
    probe = BCPProbe(original)
    need(probe.closure()[1].get(1) is None,
         "x1 should not be fixed by original UP")
    # Already present clause has no single-assumption novelty.
    duplicate, dup_stats = gate([(1, 2)], [{"clause": (1, 2)}], budget_s=5)
    need(not duplicate and dup_stats["rejected"] == 1,
         "redundant binary implication accepted")
    # New, but only one directional implication: gate rejects at threshold 2.
    one, one_stats = gate([(1, 2, 3), (-3, 2)],
                               [{"clause": (1, 2)}], budget_s=5)
    need(not one and one_stats["rejected"] == 1,
         "one weak implication should be rejected")
    print("MRE2_SELFTEST_PASS",
          json.dumps(dict(derived=len(proofs), selected=len(selected),
                          unit_found=True, duplicate_rejected=True,
                          weak_rejected=True, gate=g), sort_keys=True),
          flush=True)


def trial(case, rep, mode, binary):
    source_file = r195.FROZEN / case["name"]
    need(r195.digest(source_file) == case["sha256"], "frozen SHA mismatch")
    started = time.perf_counter()
    n, original = exact.parse_dimacs(source_file)
    rows, proofs, active = [], [], []
    stats = dict(source_rows=0, derived_clauses=0, proof_replayed=True,
                 rounds=0)
    gate_stats = dict(probed=0, considered=0, selected=0, rejected=0,
                      new_implications=0, new_conflicts=0,
                      impact_score=0, gate_s=0., abstain="mode_without_gate")
    if mode != "cms_native":
        if len(original) <= 150000:
            if mode == "xor_no_otf":
                rows = r195.certified_source_rows(original)[:mre1.MAX_SOURCE_ROWS]
                mre1.replay_source_xors(original, rows)
            else:
                rows, proofs, stats = mre1.derive(original)
                # Replay is mandatory even when shadowing or selecting none.
                need(stats.get("proof_replayed"), "MRE1 proof replay absent")
                if mode.startswith("mre2_"):
                    active, gate_stats = gate(original, proofs)
        else:
            gate_stats["abstain"] = "large_source_guard"
    prep_s = time.perf_counter()-started
    seed = int(hashlib.sha256((PROTO+case["sha256"]+str(rep))
                              .encode()).hexdigest()[:8], 16)
    selected = (proofs if mode == "mre1_all_no_otf" else
                active if mode == "mre2_active_no_otf" else [])
    native_mode = ("cms_native" if mode == "cms_native"
                   else "source_xor_no_gauss")
    result, model, native = "TIMEOUT", {}, {}
    with tempfile.TemporaryDirectory(prefix="drnas-mre2-") as d:
        d = pathlib.Path(d)
        cnf = d/"in.cnf"
        rowfile = d/"source.tsv"
        emptyfile = d/"empty.tsv"
        mre1.write_cnf(cnf, n, original, selected)
        mre1.write_xors(rowfile, rows)
        emptyfile.write_text("")
        remaining = CAP - (time.perf_counter()-started)
        if remaining > 0.10:
            try:
                p = subprocess.run(
                    [str(pathlib.Path(binary).resolve()), str(cnf),
                     str(rowfile), str(emptyfile), native_mode, str(seed)],
                    text=True, capture_output=True, timeout=remaining,
                    check=False)
            except subprocess.TimeoutExpired:
                p = None
            if p is not None:
                need(p.returncode == 0,
                     "native CMS invalid witness/adapter: " + p.stderr[-1200:])
                result, model, native = r195.parsed_native(p.stdout)
                if result == "SAT":
                    r195.verify_model(source_file, model)
    elapsed = time.perf_counter()-started
    if elapsed >= CAP:
        result = "TIMEOUT"
    if result != "TIMEOUT":
        need(result == case["expected"], "verdict mismatch")
    return dict(protocol=PROTO, id=case["name"],
                source_sha256=case["sha256"], cohort=case["cohort"],
                rep=rep, mode=mode, status=result,
                elapsed_s=round(elapsed, 6),
                par2_s=round(2*CAP if result == "TIMEOUT" else elapsed, 6),
                prep_s=round(prep_s, 6),
                source_rows=len(rows), derived_clauses=len(proofs),
                imported_lemmas=len(selected),
                gate=gate_stats, native_mode=native_mode,
                otf_gauss=False,
                proof=("ORIGINAL_CNF_SAT_MODEL_CHECKED" if result == "SAT"
                       else "UNSAT_NO_INDEPENDENT_LRAT" if result == "UNSAT"
                       else "CAP_TIMEOUT"),
                cms_conflicts=native.get("conflicts"),
                cms_decisions=native.get("decisions"),
                github_sha=os.environ.get("GITHUB_SHA", "local"))


def shard(shard_no, binary):
    need(0 <= shard_no < SHARDS, "invalid shard")
    ROOT.mkdir(parents=True, exist_ok=True)
    cases = r195.cases()
    results = []
    for case in cases[shard_no::SHARDS]:
        for rep in range(REPS):
            modes = list(MODES)
            random.Random(PROTO + case["sha256"] + str(rep)).shuffle(modes)
            for mode in modes:
                row = trial(case, rep, mode, binary)
                results.append(row)
                (ROOT / ("shard-%d.json" % shard_no)).write_text(
                    json.dumps(results, sort_keys=True)+"\n")
                print("MRE2_TRIAL", json.dumps(row, sort_keys=True),
                      flush=True)
    need(len(results) == len(cases[shard_no::SHARDS])*REPS*len(MODES),
         "incomplete shard")
    print("MRE2_SHARD_PASS", shard_no, len(results), flush=True)


def audit():
    cases = r195.cases()
    rows = []
    for shard_no in range(SHARDS):
        rows += json.loads((ROOT/("shard-%d.json" % shard_no)).read_text())
    need(len(rows) == len(cases)*REPS*len(MODES) == 320,
         "incomplete 320 trial set")
    paired = collections.defaultdict(dict)
    for row in rows:
        need(row["protocol"] == PROTO and row["otf_gauss"] is False,
             "mixed protocol or OTF configs")
        key = (row["source_sha256"], row["rep"])
        need(row["mode"] not in paired[key], "duplicate arm")
        paired[key][row["mode"]] = row
        need(row["proof"] == "ORIGINAL_CNF_SAT_MODEL_CHECKED"
             if row["status"] == "SAT" else True,
             "unverified SAT witness")
        need(row["native_mode"] ==
             ("cms_native" if row["mode"] == "cms_native"
              else "source_xor_no_gauss"), "native mode drift")
    for pair in paired.values():
        need(set(pair) == set(MODES), "missing paired mode")
        need(len({x["status"] for x in pair.values()
                  if x["status"] != "TIMEOUT"}) <= 1,
             "solver status discrepancy")
    groups = ("all", "reused_official_2026",
              "reused_synthetic_controls", "new_mixed_xor_cnf")
    totals = {}
    for group in groups:
        subset = [r for r in rows if group == "all" or r["cohort"] == group]
        totals[group] = {}
        for mode in MODES:
            a = [r for r in subset if r["mode"] == mode]
            totals[group][mode] = dict(
                attempts=len(a),
                solved=sum(r["status"] != "TIMEOUT" for r in a),
                par2_s=round(sum(r["par2_s"] for r in a), 6),
                prep_s=round(sum(r["prep_s"] for r in a), 6),
                derived_clauses=sum(r["derived_clauses"] for r in a),
                imported_lemmas=sum(r["imported_lemmas"] for r in a),
                gate_probe_calls=sum(r["gate"]["probed"] for r in a),
                gate_conflicts=sum(r["gate"]["new_conflicts"] for r in a),
                gate_implications=sum(r["gate"]["new_implications"] for r in a))
    report = dict(protocol=PROTO, cohort="development reused NOT blind",
                  source_count=len(cases), measurements=len(rows),
                  independent_UNSAT_LRAT=False,
                  original_SAT_model_verified=True,
                  full_wall_includes_preprocessing=True,
                  ALL_OTF_GAUSS_OFF=True, matched_native_config=True,
                  gate_is_pre_solve_NOT_live_CDCL=True,
                  impacts_are_bounded_UP_probes_NOT_runtime_reasons=True,
                  totals=totals)
    (ROOT/"report.json").write_text(json.dumps(report, indent=2,
                                               sort_keys=True)+"\n")
    print("MRE2_FINAL", json.dumps(report, sort_keys=True), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("selftest", "shard", "audit"))
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--binary", default="mre2/native")
    args = parser.parse_args()
    if args.action == "selftest":
        selftest()
    elif args.action == "shard":
        shard(args.shard, args.binary)
    else:
        audit()
