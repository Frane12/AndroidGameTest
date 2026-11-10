#!/usr/bin/env python3
"""DRNAS GF-GATE1: preregistered selective short GF2 CDCL delivery gate.
Source GF2 rows independently proof-replayed; source-direct-UP redundancy control.
Gate limits: 150ms / 60000 row-updates / 12000 callbacks / 12 deliveries.
Matched shadow pays overhead but never delivers clauses. Not a learned-clause
novelty oracle and not proof of fewer CDCL decisions. Cohort is NONBLIND.

Scope: "novel" only means not a same-literal unit in a directly inspected
ORIGINAL CNF clause on the observed external-propagator trail; NOT novelty
relative to CaDiCaL learned clauses, and NOT proven reduction in decisions.
Rebuild and independently replay every derived XOR parent proof from the
unaltered original CNF within every measured E2E trial.
Previously frozen GF2-S1 cohort is NON-BLIND. One deliberately positive
diagnostic SHA plus five SHA-order-selected originals. Not a SAT competition.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import random
import tempfile
import time

import drnas_gf2_screen6 as sc
import drnas_gf2_cdcl_live5 as live
import drnas_equiv9_prospective_seed_holdout as e9

ROOT = pathlib.Path("mre_gfgate1")
DRIVER = live.DRIVER
PROTO = "DRNAS-GF-GATE1-6SHA-6ARM-2REP-8S-ONECPU-SELECTIVE-UP-NOVEL-v1"
TARGET = "358c1a50db28aab6824d572d9fb22ed5681afbf157d58d13db28d042a95e0bd2"
SHARDS = 6
REPS = 2
CAP = 8.0
ARMS = (
    "cadical_clean", "cadical_novel_active", "cadical_gate_active",
    "cadical_gate_shadow", "cadical_unfiltered_active", "kissat_plain"
)
MODE = {
    "cadical_clean": "clean",
    "cadical_novel_active": "novel_active",
    "cadical_gate_active": "gate_active",
    "cadical_gate_shadow": "gate_shadow",
    "cadical_unfiltered_active": "active",
}
SOURCE_ROW_LIMIT = 48
PAIR_LIMIT = 32
GAUSS_LIMIT = 16


def need(test, message):
    if not test:
        raise RuntimeError("GF_GATE1_FAIL_CLOSED " + str(message))


def checksum(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def save(path, data):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, sort_keys=True, indent=2) + "\n")


def cases():
    roster = sorted(sc.cases(), key=lambda c: c["sha256"])
    need(len(roster) == 17, "source frozen GF2-S1 registry changed")
    known = [c for c in roster if c["sha256"] == TARGET]
    need(len(known) == 1, "previously screened diagnostic SHA absent")
    selected = [c for c in roster if c["sha256"] != TARGET][:5] + known
    selected = sorted(selected, key=lambda c: c["sha256"])
    need(len(selected) == SHARDS and len({c["sha256"] for c in selected}) == SHARDS,
         "SHA collision / cohort not 6")
    return selected


def fingerprints():
    return {
        "experiment_py_sha": checksum(__file__),
        "experiment_cpp_sha": checksum("research/drnas_gf_gate1.cpp"),
        "screen6_sha": checksum("research/drnas_gf2_screen6.py"),
        "live5_py_sha": checksum("research/drnas_gf2_cdcl_live5.py"),
        "original_registry_sha": checksum("mre_gf2_s1/manifest.json"),
        "native_binary_sha": checksum(DRIVER),
        "kissat_binary_sha": checksum(e9.KISSAT),
    }


def row_text(rows):
    return "".join(
        str(len(vs)) + " " + str(rhs) + " " + " ".join(map(str, vs)) + "\n"
        for vs, rhs in rows
    )


def make_rows(case, original, folder):
    """Original complete CNF parity blocks -> proof-replayed bounded short rows."""
    raw, root = sc.full_source_scan(original)
    pairs, triples = sc.pair_trip_screen(raw)
    gauss = sc.gaussian_screen(raw)
    p = [
        pr for pr in pairs["proofs"]
        if pr["strict_shorter_than_every_parent"] and 2 <= len(pr["vars"]) <= 4
    ][:PAIR_LIMIT]
    g = [
        pr for pr in gauss["proofs"]
        if pr["strict_shorter_than_every_parent"] and 2 <= len(pr["vars"]) <= 4
    ][:GAUSS_LIMIT]
    for pr in p + g:
        sc.verify_candidate(pr, raw)
    root_rows = raw[:SOURCE_ROW_LIMIT]
    all_rows = []
    seen = set()
    for vs, rhs in root_rows + [
        (tuple(x["vars"]), x["rhs"]) for x in p + g
    ]:
        key = (tuple(vs), int(rhs))
        need(len(vs) == len(set(vs)) and 2 <= len(vs) <= 6
             and list(vs) == sorted(vs), "malformed independently proven row")
        if key not in seen:
            seen.add(key)
            all_rows.append(key)
    file = pathlib.Path(folder) / "certified.tsv"
    file.write_text(row_text(all_rows))
    expected = len(all_rows)
    reparsed = []
    for line in file.read_text().splitlines():
        k, rhs, *vs = map(int, line.split())
        need(k == len(vs), "native TSV row arity mismatch")
        reparsed.append((tuple(vs), rhs))
    need(reparsed == all_rows, "native TSV not equal to proven rows")
    ev = {
        "source_sha": case["sha256"],
        "original_root_equations": len(raw),
        "root_blocks": root["complete_source_blocks"],
        "root_contradiction": root["source_root_empty_contradictions"],
        "source_unit_rows": root["source_root_unit_rows"],
        "selected_source_rows": len(root_rows),
        "selected_pair_proofs": len(p),
        "selected_gauss_proofs": len(g),
        "native_unique_rows": expected,
        "root_roster_sha": digest(raw),
        "certified_TSV_sha": checksum(file),
        "all_proofs_sha": digest(p + g),
        "pair_enumeration_capped": pairs["pair_enumeration_capped"],
        "gaussian_capped": gauss["gauss_capped"],
        "novelty_definition": "not direct unit of original CNF on observed trail; learned clause novelty unavailable",
    }
    return file, ev


def freeze():
    ROOT.mkdir(parents=True, exist_ok=True)
    need(DRIVER.is_file() and pathlib.Path(e9.KISSAT).is_file(),
         "pinned native or Kissat missing")
    profiles = {}
    for c in cases():
        src = sc.gf.original_path(c)
        need(checksum(src) == c["sha256"], "original CNF SHA changed")
        n, orig = e9.x22.read_cnf(src)
        need(n > 0 and orig, "source CNF invalid")
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            _, ev = make_rows(c, orig, tmp)
        profiles[c["sha256"]] = ev
    m = {
        "protocol": PROTO,
        "cases": cases(),
        "positive_screened_SHA": TARGET,
        "selection": "1 known math-positive diagnostic, 5 lowest other frozen SHA (NONBLIND)",
        "globally_blind": False,
        "one_logical_cpu": True,
        "original_input_never_mutated": True,
        "learned_clause_novelty_oracle": False,
        "only_original_clause_direct_unit_suppression": True,
        "gate_preregistered": {"max_wall_ms":150,"max_row_updates":60000,
            "max_callbacks":12000,"max_clauses":12,"max_xor_row_width":4},
        "gate_novelty_not_learned_clause_oracle": True,
        "no_auto_promotion": True,
        "reps": REPS, "arms": list(ARMS), "cap_s": CAP,
        "trials": SHARDS * REPS * len(ARMS),
        "fingerprints": fingerprints(),
        "profiles": profiles,
    }
    save(ROOT / "manifest.json", m)
    verify()
    print("GF_GATE1_FREEZE_PASS " + json.dumps({
        "sha": SHARDS, "trials": m["trials"], "cap_s": CAP,
        "math_positive_sources": sum(bool(p["selected_pair_proofs"] or p["selected_gauss_proofs"]) for p in profiles.values()),
        "original_SHA_pinned": True, "NONBLIND": True
    }, sort_keys=True), flush=True)


def verify():
    m = json.loads((ROOT / "manifest.json").read_text())
    need(m["protocol"] == PROTO and m["cases"] == cases()
         and m["arms"] == list(ARMS) and m["reps"] == REPS
         and m["trials"] == SHARDS * REPS * len(ARMS)
         and m["cap_s"] == CAP and m["fingerprints"] == fingerprints(),
         "frozen protocol/binaries/source registry mismatch")
    return m


def selftest():
    ROOT.mkdir(parents=True, exist_ok=True)
    live.selftest()  # legacy binary I/O, SAT witnesses, timeout metrics
    probe = subprocess.run([str(DRIVER), "--gate-selftest"],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, timeout=8.0, check=True)
    need("GF_GATE1_SELFTEST_PASS" in probe.stdout,
         "new native clause delivery, placebo or source-UP test failed")
    toy = ROOT / "toy-source-novel.cnf"
    # Four clauses encode an exact 3-XOR on variables 1,2,3.
    clauses = [(-1, 2, 3), (1, -2, 3), (1, 2, -3), (-1, -2, -3)]
    toy.write_text("p cnf 3 4\n" + "".join(
        " ".join(map(str, c)) + " 0\n" for c in clauses
    ))
    n, original = e9.x22.read_cnf(toy)
    raw, _ = sc.full_source_scan(original)
    need(n == 3 and raw, "source-only XOR fixture absent")
    tsv = ROOT / "toy-exact.tsv"
    tsv.write_text(row_text(raw))
    cpu = min(os.sched_getaffinity(0))
    for mode in ("novel_active", "gate_active", "gate_shadow"):
        status, verified, tele, _ = live.run_child(
            [DRIVER, mode, toy, tsv], original, 3.0, cpu
        )
        need(status == "SAT" and verified and tele.get("disabled") == 0,
             "new native mode failed original SAT check: " + mode)
        need(tele.get("learned_clause_novelty_oracle_available") == 0,
             "false novelty-oracle claim")
        need(tele.get("source_novelty_gate") == 1,
             "new native direct original-unit gate not enabled")
        if mode.startswith("gate_"):
            need(tele.get("selective_GF_gate") == 1 and
                 tele.get("gate_max_wall_ms") == 150 and
                 tele.get("gate_max_clauses") == 12,
                 "selective native gate telemetry/budget failed")
            if mode == "gate_shadow":
                need(tele.get("clauses_emitted") == 0, "shadow sent clause")
    toy.unlink()
    tsv.unlink()
    print("GF_GATE1_SELFTEST_PASS " + json.dumps({
        "gate_active_shadow_novel_SAT_original_verified": True,
        "native_clause_delivery_and_source_unit_selftest": True,
        "independent_source_3XOR": True,
        "learned_clause_novelty_oracle": False
    }, sort_keys=True), flush=True)


def one_trial(m, c, rep, arm):
    need(0 <= rep < REPS and arm in ARMS, "bad arm or rep")
    src = sc.gf.original_path(c)
    need(checksum(src) == c["sha256"], "pretrial SHA corrupted")
    cpu = min(os.sched_getaffinity(0))
    os.sched_setaffinity(0, {cpu})
    t0, cpu0 = time.perf_counter(), time.process_time()
    child0 = e9.x22.child_cpu()
    n, original = e9.x22.read_cnf(src)
    status, verified, tele, rowev = "TIMEOUT", False, {}, None
    with tempfile.TemporaryDirectory(dir=ROOT) as folder:
        rows = pathlib.Path(folder) / "empty.tsv"
        rows.write_text("")
        if arm not in ("cadical_clean", "kissat_plain"):
            rows, rowev = make_rows(c, original, folder)
            need(rowev == m["profiles"][c["sha256"]],
                 "replayed proof/row selection changed from freeze")
        prep = time.perf_counter() - t0
        left = CAP - prep
        if left > .10:
            if arm == "kissat_plain":
                cmd = e9.command("kissat1", src, e9.seedpair(c["sha256"], rep)[0])
            else:
                cmd = [DRIVER, MODE[arm], src, rows]
            status, verified, tele, _ = live.run_child(cmd, original, left, cpu)
    elapsed = time.perf_counter() - t0
    if elapsed >= CAP:
        status, verified = "TIMEOUT", False
    need(status != "SAT" or verified, "SAT original model not verified")
    if arm not in ("kissat_plain",):
        need(tele.get("disabled", 0) == 0, "native callback inconsistency")
        if tele:
            need(tele.get("xor_rows", 0) ==
                 (rowev["native_unique_rows"] if rowev else 0),
                 "native received wrong proof rows")
        if arm in ("cadical_gate_active","cadical_gate_shadow","cadical_novel_active"):
            if tele:
                need(tele.get("learned_clause_novelty_oracle_available", 0) == 0,
                     "learned-clause oracle falsely advertised")
                if status in ("SAT", "UNSAT"):
                    need("learned_clause_novelty_oracle_available" in tele,
                         "completed native solve lacks source-novelty declaration")
                if arm.startswith("cadical_gate_") and status in ("SAT", "UNSAT"):
                    need(tele.get("selective_GF_gate") == 1 and
                         tele.get("gate_max_wall_ms") == 150 and
                         tele.get("gate_max_clauses") == 12,
                         "preregistered selective gate disabled or altered")
                    if arm == "cadical_gate_shadow":
                        need(tele.get("clauses_emitted", 0) == 0, "shadow delivered clause")
                    need(tele.get("clauses_emitted", 0) <= 12, "gate clause cap breached")
    need(checksum(src) == c["sha256"], "posttrial original SHA altered")
    return {
        "protocol": PROTO, "source_sha": c["sha256"], "shard": m["cases"].index(c),
        "rep": rep, "arm": arm, "cap_s": CAP, "status": status,
        "SAT_original_model_verified": bool(verified and status == "SAT"),
        "UNSAT_independent_LRAT": False, "original_SHA_verified": True,
        "one_logical_CPU": cpu, "no_parallel_child": True,
        "E2E_s": round(elapsed, 6), "prepass_s": round(prep, 6),
        "CPU_parent_s": round(time.process_time() - cpu0, 6),
        "CPU_child_s": round(e9.x22.child_cpu() - child0, 6),
        "source_GF2_math": rowev,
        "native_metrics": tele,
        "timeout_metrics_are_lower_bounds": status == "TIMEOUT",
    }


def shard(i):
    m = verify()
    need(0 <= i < SHARDS, "bad shard")
    c = m["cases"][i]
    out = []
    for rep in range(REPS):
        order = list(ARMS)
        random.Random(c["sha256"] + "|GF-GATE1|" + str(rep)).shuffle(order)
        for arm in order:
            rec = one_trial(m, c, rep, arm)
            out.append(rec)
            save(ROOT / ("shard-" + str(i) + ".json"), out)
            print("GF_GATE1_TRIAL " + json.dumps(rec, sort_keys=True), flush=True)
    need(len(out) == REPS * len(ARMS), "incomplete paired shard")
    print("GF_GATE1_SHARD_PASS " + json.dumps({
        "shard": i, "trials": len(out), "SHA": c["sha256"]
    }, sort_keys=True), flush=True)


def audit():
    m = verify()
    # Repeat each original-source proof on the exact input, independently of solver outcomes.
    for c in m["cases"]:
        src = sc.gf.original_path(c)
        _, original = e9.x22.read_cnf(src)
        with tempfile.TemporaryDirectory(dir=ROOT) as folder:
            _, ev = make_rows(c, original, folder)
        need(ev == m["profiles"][c["sha256"]], "proof replay failed during audit")
    trials = []
    for i in range(SHARDS):
        f = ROOT / ("shard-" + str(i) + ".json")
        need(f.is_file(), "missing E2E shard " + str(i))
        a = json.loads(f.read_text())
        need(len(a) == REPS * len(ARMS), "incomplete shard")
        need({(r["rep"], r["arm"]) for r in a} ==
             {(rep, arm) for rep in range(REPS) for arm in ARMS},
             "missing or duplicate original paired trial")
        need(all(r["source_sha"] == m["cases"][i]["sha256"] and
                 r["original_SHA_verified"] and r["cap_s"] == CAP for r in a),
             "SHA/cap violation")
        trials.extend(a)
    need(len(trials) == m["trials"], "total trial count changed")
    ref_unsat = {}
    for c in m["cases"]:
        sha = c["sha256"]
        sample = [r for r in trials if r["source_sha"] == sha]
        need(not (any(r["status"] == "SAT" for r in sample)
                  and any(r["status"] == "UNSAT" for r in sample)),
             "SAT/UNSAT discrepancy same original SHA")
        ref_unsat[sha] = (
            any(r["arm"] == "cadical_clean" and r["status"] == "UNSAT" for r in sample)
            and any(r["arm"] == "kissat_plain" and r["status"] == "UNSAT" for r in sample)
        )
    for r in trials:
        if r["status"] == "SAT":
            need(r["SAT_original_model_verified"], "unverified original SAT counted")

    def accepted(r):
        return (r["status"] == "SAT" and r["SAT_original_model_verified"]) or (
            r["status"] == "UNSAT" and ref_unsat[r["source_sha"]])

    def par2(r):
        return r["E2E_s"] if accepted(r) else 2 * CAP

    def stats(items):
        return {
            "n": len(items),
            "solved": sum(bool(accepted(r)) for r in items),
            "verified_SAT": sum(r["status"] == "SAT" for r in items),
            "UNSAT_reference_agreement_no_LRAT":
                sum(r["status"] == "UNSAT" and ref_unsat[r["source_sha"]] for r in items),
            "UNSAT_unverified": sum(r["status"] == "UNSAT" and not ref_unsat[r["source_sha"]] for r in items),
            "timeouts": sum(r["status"] == "TIMEOUT" for r in items),
            "PAR2_s": round(sum(par2(r) for r in items), 6),
            "wall_E2E_s": round(sum(r["E2E_s"] for r in items), 6),
            "total_CPU_s": round(sum(r["CPU_parent_s"] + r["CPU_child_s"] for r in items), 6),
            "prepass_E2E_s": round(sum(r["prepass_s"] for r in items), 6),
            "source_suppressed": sum(r["native_metrics"].get("source_unit_suppressed", 0) for r in items),
            "source_novel_candidate_units": sum(r["native_metrics"].get("source_novel_unit_candidates", 0) for r in items),
            "shadow_candidates": sum(r["native_metrics"].get("shadow_candidates", 0) for r in items),
            "clauses_emitted": sum(r["native_metrics"].get("clauses_emitted", 0) for r in items),
            "clauses_delivered": sum(r["native_metrics"].get("delivery_confirmed", 0) for r in items),
            "CDCL_callbacks": sum(r["native_metrics"].get("live_callbacks", 0) for r in items),
            "CDCL_ready_events": sum(r["native_metrics"].get("ready_events", 0) for r in items),
            "row_updates": sum(r["native_metrics"].get("row_updates", 0) for r in items),
            "gate_stop_events": sum(r["native_metrics"].get("gate_stop_events", 0) for r in items),
            "gate_unit_survived": sum(r["native_metrics"].get("gate_unit_survived", 0) for r in items),
            "gate_rejected_wide": sum(r["native_metrics"].get("gate_rejected_wide", 0) for r in items),
            "gate_source_ambiguous": sum(r["native_metrics"].get("gate_source_ambiguous", 0) for r in items),
        }

    score = {arm: stats([r for r in trials if r["arm"] == arm]) for arm in ARMS}
    reference = score["cadical_clean"]["PAR2_s"]
    for arm in ARMS:
        score[arm]["PAR2_speedup_vs_clean_x"] = round(reference / score[arm]["PAR2_s"], 6)
    matched = {}
    for arm in ARMS:
        if arm == "cadical_clean":
            continue
        for baseline in ("cadical_clean", "cadical_gate_shadow", "cadical_novel_active"):
            if arm == baseline:
                continue
            differences = []
            for c in m["cases"]:
                for rep in range(REPS):
                    u = next(r for r in trials if r["arm"] == arm
                             and r["source_sha"] == c["sha256"] and r["rep"] == rep)
                    v = next(r for r in trials if r["arm"] == baseline
                             and r["source_sha"] == c["sha256"] and r["rep"] == rep)
                    differences.append(par2(u) - par2(v))
            matched[arm + "_vs_" + baseline] = {
                "PAR2_gain_s": round(-sum(differences), 6),
                "wins": sum(d < -0.02 for d in differences),
                "regressions": sum(d > 0.02 for d in differences),
                "ties": sum(abs(d) <= 0.02 for d in differences),
                "best_gain_s": round(min(differences), 6),
                "worst_regression_s": round(max(differences), 6),
            }
    report = {
        "protocol": PROTO, "original_SHA_count": SHARDS, "trials": len(trials),
        "NONBLIND_known_originals": True, "one_logical_CPU_per_child": True,
        "SAT_verified_against_original": True,
        "UNSAT_without_LRAT_only_accepted_on_two_reference_consensus": True,
        "source_GF2_proof_independently_replayed": True,
        "source_clause_novelty_only": True, "learned_clause_novelty_oracle": False,
        "selective_short_GF2_delivery": True, "same_cost_shadow_placebo": True,
        "gate_budget_frozen_before_results": True,
        "proof_of_CDCL_decision_reduction": False, "no_auto_promotion": True,
        "scores": score, "matched": matched,
        "per_shard": {str(i): {arm: stats([
            r for r in trials if r["shard"] == i and r["arm"] == arm
        ]) for arm in ARMS} for i in range(SHARDS)},
        "original_math_profiles": m["profiles"],
    }
    save(ROOT / "report.json", report)
    print("GF_GATE1_FINAL " + json.dumps(report, sort_keys=True), flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("selftest", "freeze", "verify", "shard", "audit"))
    ap.add_argument("--shard", type=int, default=0)
    arg = ap.parse_args()
    if arg.action == "shard":
        shard(arg.shard)
    else:
        globals()[arg.action]()
    if arg.action == "verify":
        print("GF_GATE1_VERIFY_PASS", flush=True)
