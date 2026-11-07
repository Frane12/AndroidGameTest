#!/usr/bin/env python3
"""DRNAS TA3: prospective source-feature adaptive SAT selection, 24 original CNFs.

Development: R199/TA2; evaluation: 24 distinct SAT2025 original source SHA,
frozen before any TA3 trial. Eight paired arms x two reps = 384 trials.
Features may use only original DIMACS (never known result/performance).
Pre-solver feature scans and router subprocess startup count against 20s cap.
SAT witnesses verified on ORIGINAL. Generic UNSAT has no independent LRAT.
TA2 portfolio uses conditional CMS/Kissat host selection; R28 only when
source-syntactic evidence is strong. A shadow pays the same feature cost.
"""
from __future__ import annotations

import argparse
import collections
import concurrent.futures
import hashlib
import json
import lzma
import pathlib
import random
import statistics
import subprocess
import time
import urllib.request

import drnas_ta2_structural_profile as structure
import r199_unseen_mixed40_crossbackend as previous

ROOT = pathlib.Path("ta3")
SOURCE = ROOT / "sources"
PROTO = "DRNAS-TA3-24-SAT2025-PROSPECTIVE-8ARM-2REP-v1"
CAP = 20.0
REPS = 2
SHARDS = 8
MODES = (
    "cms_plain", "cms_r28", "cms_ta2",
    "kissat_plain", "kissat_r28", "kissat_ta2",
    "ta2_portfolio", "ta2_portfolio_shadow",
)
previous.certified.CAP = CAP


def need(yes, message):
    if not yes:
        raise RuntimeError("TA3_FAIL_CLOSED " + str(message))


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def save(path, payload):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n")


def candidates():
    document = json.loads((ROOT / "candidates.json").read_text())
    cases = document["cases"]
    need(len(cases) == 24 and len({c["sha256"] for c in cases}) == 24,
         "holdout must contain 24 unique source SHAs")
    old1 = json.loads(pathlib.Path("r189/frozen/manifest.json").read_text())
    old2 = json.loads(pathlib.Path("r199/candidates.json").read_text())
    seen = {c["sha256"] for c in old1["cases"]} | {
        c["sha256"] for c in old2["cases"]}
    need(not seen.intersection(c["sha256"] for c in cases),
         "TA3 not source-disjoint from R189/R199")
    need(len({c["family"] for c in cases}) == 24, "family duplication")
    cohorts = {g: [c for c in cases if c["group"] == g] for g in (
        "parity_crafted", "hardware_graph", "industrial_planning", "csp_puzzles")}
    need(all(len(a) == 6 for a in cohorts.values()), "unbalanced source groups")
    need(sum(c["expected"] == "SAT" for c in cases) == 12
         and sum(c["expected"] == "UNSAT" for c in cases) == 12,
         "expected 12 SAT and 12 UNSAT")
    return cases, cohorts


def fetch():
    cases, _ = candidates()
    SOURCE.mkdir(parents=True, exist_ok=True)
    def get(c):
        dest = SOURCE / (c["id"] + ".cnf")
        if dest.is_file() and sha(dest) == c["sha256"]:
            return
        error = None
        for attempt in range(4):
            try:
                request = urllib.request.Request(
                    c["url"], headers={"User-Agent": "DRNAS-TA3-2025-Prospective/1"})
                with urllib.request.urlopen(request, timeout=120) as response:
                    blob = response.read(16_000_001)
                need(len(blob) < 16_000_001, "compressed source exceeds limit")
                data = lzma.decompress(blob)
                need(len(data) == c["bytes"], "decompressed bytes mismatch " + c["id"])
                need(hashlib.sha256(data).hexdigest() == c["sha256"],
                     "external original SHA mismatch " + c["id"])
                need(b"p cnf " in data[:10000], "not valid DIMACS header " + c["id"])
                dest.write_bytes(data)
                return
            except Exception as exc:
                error = exc
                time.sleep(2 + attempt * 3)
        raise RuntimeError("cannot restore source " + c["id"] + ": " + str(error))
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as workers:
        list(workers.map(get, cases))
    for c in cases:
        need(sha(SOURCE / (c["id"] + ".cnf")) == c["sha256"],
             "source changed during preparation " + c["id"])
    save(ROOT / "manifest.json", {"protocol": PROTO, "cases": cases,
         "SHA_source_disjoint_from_R189_and_R199": True})
    print("TA3_SOURCE_FROZEN", json.dumps({"cases": len(cases),
          "SAT": 12, "UNSAT": 12, "manifest_sha": sha(ROOT / "manifest.json")},
          sort_keys=True), flush=True)


def verify():
    cases, cohorts = candidates()
    manifest = json.loads((ROOT / "manifest.json").read_text())
    need([c["sha256"] for c in manifest["cases"]] ==
         [c["sha256"] for c in cases], "frozen source set drift")
    pins = json.loads((ROOT / "pins.json").read_text())
    for file_name, digest in pins.items():
        need(sha(file_name) == digest, "pin mismatch " + file_name)
    for c in cases:
        need(sha(SOURCE / (c["id"] + ".cnf")) == c["sha256"],
             "original source changed " + c["id"])
    buckets = [[] for _ in range(SHARDS)]
    # Deterministic 3 cases per shard, no duplication, no trial outcomes used.
    flat = []
    for g in ("parity_crafted", "hardware_graph",
              "industrial_planning", "csp_puzzles"):
        flat.extend(sorted(cohorts[g], key=lambda c: c["sha256"]))
    for i, c in enumerate(flat):
        buckets[i % SHARDS].append(c)
    need(all(len(b) == 3 for b in buckets), "not three original CNFs per shard")
    return cases, buckets


def fast_features(path):
    """A small bounded source-only scan. No results, timings or learned hints."""
    old_clause = structure.SAMPLE_CLAUSES
    old_lits = structure.SAMPLE_LITERALS
    try:
        structure.SAMPLE_CLAUSES = 512
        structure.SAMPLE_LITERALS = 6144
        coarse = structure.feature(path)
        # Deeper sampling is conditional on preliminary XOR evidence, and is
        # still charged to the same end-to-end benchmark wall-clock.
        if (coarse["complete_xor3_templates_sample"] >= 2
            and coarse["declared_clauses"] <= 2500
            and coarse["sample_fraction_clauses"] < 0.95):
            structure.SAMPLE_CLAUSES = 4096
            structure.SAMPLE_LITERALS = 45000
            coarse = structure.feature(path)
    finally:
        structure.SAMPLE_CLAUSES = old_clause
        structure.SAMPLE_LITERALS = old_lits
    return coarse


def decision(features, mode):
    """Frozen explainable structural rules, not a fitted model."""
    xor3 = features["complete_xor3_templates_sample"]
    binary = features["binary_fraction"]
    horn = features["horn_clause_fraction"]
    long = features["long_clause_fraction"]
    skew = features["variable_occurrence_p90_over_median"]
    size = features["declared_clauses"]
    covered_fraction = features["sample_fraction_clauses"]
    pure_xor_hint = (size <= 2500 and covered_fraction >= 0.95
                     and xor3 >= 6 and binary < 0.12 and long < 0.16)
    # All four families are interpreted independently of SAT/UNSAT labels.
    if mode in ("cms_ta2", "kissat_ta2"):
        backend = "cms" if mode == "cms_ta2" else "kissat"
        return backend + ("_r28" if pure_xor_hint else "_plain"), (
            "source_complete_xor_hint" if pure_xor_hint else "host_safe_fallback")
    if mode in ("ta2_portfolio", "ta2_portfolio_shadow"):
        if pure_xor_hint:
            backend = "cms"
            reason = "small_source_xor_candidate"
        elif xor3 >= 2:
            backend = "cms"
            reason = "source_parity_plus_cnf"
        elif binary >= 0.60:
            backend = "kissat"
            reason = "binary_implication_graph"
        elif horn >= 0.95:
            backend = "kissat"
            reason = "horn_dominant"
        elif long >= 0.38:
            backend = "kissat"
            reason = "long_clause_dominant"
        elif skew >= 7.5:
            backend = "kissat"
            reason = "variable_hub_skew"
        else:
            backend = "cms"
            reason = "mixed_residual"
        selected = backend + ("_r28" if pure_xor_hint else "_plain")
        if mode == "ta2_portfolio_shadow":
            return "cms_plain", "shadow_did_not_use_selection:" + selected
        return selected, reason
    need(False, "invalid TA2 mode " + mode)


def command(selected, source):
    return previous.commands(selected, source)


def trial(case, mode, rep, shard):
    source = SOURCE / (case["id"] + ".cnf")
    need(sha(source) == case["sha256"], "SHA changed before trial")
    started = time.perf_counter()
    selected = mode
    route = "fixed_reference"
    features = None
    profile_s = 0.0
    if mode.endswith("_ta2") or mode.startswith("ta2_portfolio"):
        features = fast_features(source)
        profile_s = time.perf_counter() - started
        selected, route = decision(features, mode)
    need(selected in ("cms_plain", "cms_r28", "kissat_plain", "kissat_r28"),
         "invalid selected executor " + selected)
    if time.perf_counter() - started >= CAP - .08:
        status = "TIMEOUT"
        model = {}
        r28_route = None
    else:
        status, model, r28_route, _raw, _rc = previous.certified.timed_command(
            command(selected, source), started)
    # R199-style end-to-end charge: include profiling, selection and solver.
    elapsed = min(CAP, time.perf_counter() - started)
    if elapsed >= CAP:
        status = "TIMEOUT"
    proof = "CAP_TIMEOUT"
    if status == "SAT":
        n, clauses = previous.certified.gf_src.gf.dimacs(source)
        previous.certified.gf_src.gf.sat_check(clauses, model)
        proof = "SAT_WITNESS_ORIGINAL_VERIFIED"
    elif status == "UNSAT":
        if r28_route and r28_route.startswith("certified_xor_contradiction"):
            proof = "R28_SOURCE_GF2_CONTRADICTION"
        else:
            proof = "NO_INDEPENDENT_LRAT"
    need(status in ("SAT", "UNSAT", "TIMEOUT"), "unexpected solver status")
    need(status == "TIMEOUT" or status == case["expected"],
         "reference SAT/UNSAT classification mismatch " + case["id"])
    data = {
        "id": case["id"], "sha256": case["sha256"], "family": case["family"],
        "group": case["group"], "mode": mode, "selected": selected,
        "routing_reason": route, "rep": rep, "shard": shard,
        "status": status, "elapsed_s": round(elapsed, 6),
        "par2_s": round(2 * CAP if status == "TIMEOUT" else elapsed, 6),
        "profile_s": round(profile_s, 6), "proof": proof,
        "r28_route": r28_route,
        "source_sha256": case["sha256"],
    }
    if features:
        data["source_features"] = {
            "sampled_clauses": features["sampled_clauses"],
            "sample_fraction_clauses": features["sample_fraction_clauses"],
            "binary_fraction": features["binary_fraction"],
            "horn_clause_fraction": features["horn_clause_fraction"],
            "long_clause_fraction": features["long_clause_fraction"],
            "complete_xor3_templates_sample":
                features["complete_xor3_templates_sample"],
            "variable_occurrence_p90_over_median":
                features["variable_occurrence_p90_over_median"],
        }
    print("TA3_TRIAL", json.dumps(data, sort_keys=True), flush=True)
    return data


def shard(index):
    _all, groups = verify()
    need(0 <= index < SHARDS, "bad shard index")
    records = []
    for case in groups[index]:
        for rep in range(REPS):
            order = list(MODES)
            random.Random(PROTO + case["sha256"] + str(rep)).shuffle(order)
            for mode in order:
                records.append(trial(case, mode, rep, index))
                save(ROOT / ("shard-%d.json" % index), records)
    need(len(records) == len(groups[index]) * REPS * len(MODES),
         "partial paired shard " + str(index))
    print("TA3_SHARD_PASS", index, len(records), flush=True)


def audit():
    cases, groups = verify()
    records = []
    pairs = set()
    case_map = {c["sha256"]: c for c in cases}
    for i, group in enumerate(groups):
        path = ROOT / ("shard-%d.json" % i)
        need(path.is_file(), "missing shard " + str(i))
        rows = json.loads(path.read_text())
        need(len(rows) == len(group) * REPS * len(MODES),
             "wrong shard trials " + str(i))
        need({r["sha256"] for r in rows} ==
             {c["sha256"] for c in group}, "wrong shard sources")
        for r in rows:
            need(r["sha256"] in case_map, "unknown formula")
            need(r["id"] == case_map[r["sha256"]]["id"], "source ID drift")
            k = (r["sha256"], r["rep"], r["mode"])
            need(k not in pairs, "duplicate paired trial")
            pairs.add(k)
            need(r["status"] in ("SAT", "UNSAT", "TIMEOUT"), "bad status")
            need(r["status"] == "TIMEOUT" or
                 r["status"] == case_map[r["sha256"]]["expected"], "incorrect answer")
            need(r["status"] != "SAT" or
                 r["proof"] == "SAT_WITNESS_ORIGINAL_VERIFIED", "SAT model not verified")
            par2 = 2 * CAP if r["status"] == "TIMEOUT" else r["elapsed_s"]
            need(abs(r["par2_s"] - par2) < .00002, "PAR2 mismatch")
            records.append(r)
    need(len(records) == 24 * REPS * len(MODES) == 384,
         "not 384 prospective paired trials")
    for c in cases:
        for rep in range(REPS):
            rr = [r for r in records
                  if r["sha256"] == c["sha256"] and r["rep"] == rep]
            need({r["mode"] for r in rr} == set(MODES),
                 "modes not paired at source/rep")
            need(len({r["status"] for r in rr
                      if r["status"] != "TIMEOUT"}) <= 1,
                 "contradictory SAT/UNSAT answers")
    totals = {}
    for label, sources in [("all", cases)] + [
        (g, [c for c in cases if c["group"] == g]) for g in
        ("parity_crafted", "hardware_graph", "industrial_planning", "csp_puzzles")]:
        hashes = {c["sha256"] for c in sources}
        cohort = [r for r in records if r["sha256"] in hashes]
        modes = {}
        for mode in MODES:
            rr = [r for r in cohort if r["mode"] == mode]
            modes[mode] = {
                "attempts": len(rr),
                "solved": sum(r["status"] != "TIMEOUT" for r in rr),
                "SAT": sum(r["status"] == "SAT" for r in rr),
                "UNSAT": sum(r["status"] == "UNSAT" for r in rr),
                "PAR2_s": round(sum(r["par2_s"] for r in rr), 6),
                "profile_s": round(sum(r["profile_s"] for r in rr), 6),
                "backend_cms": sum(r["selected"].startswith("cms") for r in rr),
                "backend_kissat": sum(r["selected"].startswith("kissat") for r in rr),
                "r28_selections": sum(r["selected"].endswith("_r28") for r in rr),
            }
        comparison = {}
        pairs_to_compare = (
            ("cms_ta2", "cms_plain"),
            ("kissat_ta2", "kissat_plain"),
            ("ta2_portfolio", "cms_plain"),
            ("ta2_portfolio", "kissat_plain"),
            ("ta2_portfolio", "ta2_portfolio_shadow"),
            ("cms_r28", "cms_plain"),
            ("kissat_r28", "kissat_plain"),
        )
        for candidate, host in pairs_to_compare:
            base = {(r["sha256"], r["rep"]): r for r in cohort if r["mode"] == host}
            candidate_rows = [r for r in cohort if r["mode"] == candidate]
            wins = losses = ties = 0
            for r in candidate_rows:
                d = r["par2_s"] - base[(r["sha256"], r["rep"])]["par2_s"]
                if d < -.001:
                    wins += 1
                elif d > .001:
                    losses += 1
                else:
                    ties += 1
            baseline_par2 = modes[host]["PAR2_s"]
            candidate_par2 = modes[candidate]["PAR2_s"]
            comparison[candidate + "__vs__" + host] = {
                "wins": wins, "losses": losses, "ties": ties,
                "host_PAR2_s": baseline_par2,
                "candidate_PAR2_s": candidate_par2,
                "par2_reduction_percent": round(
                    100 * (baseline_par2 - candidate_par2) / baseline_par2, 3)
                    if baseline_par2 else None,
            }
        totals[label] = {"cases": len(sources),
                         "modes": modes, "comparisons": comparison}
    result = {
        "protocol": PROTO, "status": "TA3_AUDIT_PASS",
        "cases": 24, "paired_trials": len(records),
        "repetitions": REPS, "cap_s": CAP,
        "original_manifest_sha256": sha(ROOT / "manifest.json"),
        "SHA_source_disjoint_R189_R199": True,
        "rules_precommitted_before_TA3_results": True,
        "preprocess_time_in_elapsed": True,
        "SAT_witness_original_checked": True,
        "independent_generic_UNSAT_LRAT": False,
        "results": totals,
    }
    save(ROOT / "report.json", result)
    save(ROOT / "all_trials.json", records)
    lines = [
        "# DRNAS TA3 — prospective adaptive structural selector",
        "",
        "24 distinct original SAT2025 CNFs, 12 SAT + 12 UNSAT; 8 strategies,",
        "2 paired repetitions, 20s full wall cap per trial (384 attempts).",
        "Original SHA disjoint from R189 and R199. SAT witnesses checked;",
        "generic CDCL UNSAT outcomes not independently LRAT verified.",
        "",
        "## Four signed percentage scorecards (PAR2 reduction; negative = regression)",
        "",
        "| CMS+TA2 vs CMS | Kissat+TA2 vs Kissat | TA2 portfolio vs CMS | TA2 portfolio vs Kissat |",
        "|---|---|---|---|",
    ]
    matches = [totals["all"]["comparisons"][c + "__vs__" + h][
                "par2_reduction_percent"] for c,h in (
                ("cms_ta2", "cms_plain"),
                ("kissat_ta2", "kissat_plain"),
                ("ta2_portfolio", "cms_plain"),
                ("ta2_portfolio", "kissat_plain"))]
    lines += ["| " + " | ".join(("%+.2f%%" % x) for x in matches) + " |",
              "", "Important: these are PAR2 changes, not raw runtime speedups.",
              "", "| Cohort | Mode | Solved / attempts | PAR2 s | Profile overhead s |",
              "|---|---|---:|---:|---:|"]
    for group, detail in totals.items():
        for name, m in detail["modes"].items():
            lines.append("| %s | %s | %d/%d | %.3f | %.3f |" %
                (group, name, m["solved"], m["attempts"],
                 m["PAR2_s"], m["profile_s"]))
    lines += ["", "## Paired comparisons", "",
              "| Group | Comparison | W/L/T | PAR2 change |",
              "|---|---|---|---:|"]
    for group, detail in totals.items():
        for name, m in detail["comparisons"].items():
            lines.append("| %s | %s | %d/%d/%d | %+0.2f%% |" %
                (group, name, m["wins"], m["losses"], m["ties"],
                 m["par2_reduction_percent"]))
    (ROOT / "summary.md").write_text("\n".join(lines) + "\n")
    print("TA3_FINAL", json.dumps({"status": result["status"],
          "trials": result["paired_trials"], "all": totals["all"]},
          sort_keys=True), flush=True)


def smoke():
    previous.certified.deriv.selftest()
    p = ROOT / "smoke.cnf"
    p.parent.mkdir(parents=True, exist_ok=True)
    # XOR3 parity on {1,2,3} plus binary implications and unit clauses.
    p.write_text(
        "p cnf 4 7\n"
        "1 2 3 0\n"
        "-1 -2 3 0\n"
        "-1 2 -3 0\n"
        "1 -2 -3 0\n"
        "1 4 0\n"
        "-4 2 0\n"
        "3 0\n")
    info = fast_features(p)
    need(info["sampled_clauses"] == 7, "not complete sample")
    need(info["complete_xor3_templates_sample"] == 1, "missed source XOR3")
    for mode in ("cms_ta2", "kissat_ta2", "ta2_portfolio", "ta2_portfolio_shadow"):
        route, reason = decision(info, mode)
        need(route in ("cms_plain", "kissat_plain", "cms_r28", "kissat_r28"),
             "invalid route " + reason)
    for host in ("cms_plain", "kissat_plain", "cms_r28", "kissat_r28"):
        t0 = time.perf_counter()
        status, model, route, _raw, _rc = previous.certified.timed_command(
            command(host, p), t0)
        need(status == "SAT", "smoke solver unsound " + host)
    print("TA3_SMOKE_PASS", flush=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=("fetch", "smoke", "shard", "audit"))
    cli.add_argument("--shard", type=int, default=0)
    args = cli.parse_args()
    if args.action == "fetch":
        fetch()
    elif args.action == "smoke":
        smoke()
    elif args.action == "shard":
        shard(args.shard)
    else:
        audit()
