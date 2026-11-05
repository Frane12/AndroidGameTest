#!/usr/bin/env python3
"""R67: prospective diagnostic of XOR-CNF coupling, without changing R65.

Reuses the tested R66 freeze/measurement engines, but excludes every R66
attempted source, adds the unchanged R28 baseline and passive diagnostics,
and audits all three matched modes.  No feature-derived adaptive gate here.
"""
from __future__ import annotations

import argparse
import collections
import copy
import hashlib
import json
from pathlib import Path
import time
from types import SimpleNamespace

import r28_exact_gf2_benchmark as r28
import r63_real2026_xor_prevalence_fallback as r63
import r64_mixed_xor_implied as r64
import r65_xor_cnf_feedback as r65
import r66_r65_blind_short_holdout as r66

PROTO = "DRNAS-R67-BLIND-STRUCTURAL-DIAGNOSTIC-20261103-v1"
SALT = "DRNAS-R67-EXCLUDE-R63-R66-PRECOMMIT-SHA-SALT-v1"
CAP = 60.0
REPS = 2
SHARDS = 8
TARGET = 30
MIN_READY = 8
MAX_ATTEMPTS = 96
MODES = ("clean_kissat", "r28_exact_gf2_fallback", "r65_xor_cnf_feedback")
GROUPS = ("mixed_exact", "pure_exact", "partial_only", "no_exact", "unscannable")


def check(ok, message):
    if not ok:
        raise RuntimeError("R67_FAIL_CLOSED " + str(message))


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as src:
        for block in iter(lambda: src.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def configure():
    # No edits to r65, r28, r63 or r66 source algorithms; only protocol constants.
    r66.PROTO = PROTO
    r66.SALT = SALT
    r66.CAP = CAP
    r66.REPS = REPS
    r66.SHARDS = SHARDS
    r66.TARGET = TARGET
    r66.MIN_READY = MIN_READY
    r66.MAX_ATTEMPTS = MAX_ATTEMPTS
    r66.MODES = MODES
    r63.CAP = CAP
    r65.CAP = CAP


def passive_features(source, case):
    """Describe actual CNF/exact XOR overlap. Never infer XOR from partials."""
    t0 = time.monotonic()
    features = dict(supported=case["supported"],
                    exact_blocks=case["complete_blocks"],
                    partial_support_groups=case["partial_support_groups"],
                    coverage_fraction=case["coverage_fraction"],
                    source_bytes=case["bytes"],
                    variables=case["variables"], clauses=case["clauses"],
                    r65_eligible=bool(case["supported"] and
                        case["complete_blocks"] and not case["pure_exact_xor"]),
                    xor_variables=0, xor_cnf_bridge_clauses=0,
                    xor_cnf_bridge_variable_count=0,
                    bridge_ratio=None, passive_scan_s=0.0)
    if features["r65_eligible"]:
        eqs, _ = r64.extract_equations(
            source, case["variables"], case["clauses"], time.monotonic())
        check(len(eqs) == case["complete_blocks"],
              "independent exact scanner disagreement")
        xor_vars = set(v for vs, _ in eqs for v in vs)
        exact_supports = {tuple(vs) for vs, _ in eqs}
        n, clauses = r28.load_clauses(source)
        check(n == case["variables"] and len(clauses) == case["clauses"],
              "CNF parser disagreement")
        bridge_count, bridge_variables = 0, set()
        for clause in clauses:
            support = set(abs(v) for v in clause)
            if tuple(sorted(support)) not in exact_supports:
                touched = support & xor_vars
                if touched:
                    bridge_count += 1
                    bridge_variables.update(touched)
        features.update(xor_variables=len(xor_vars),
                        xor_cnf_bridge_clauses=bridge_count,
                        xor_cnf_bridge_variable_count=len(bridge_variables),
                        bridge_ratio=round(bridge_count/max(1,len(clauses)), 7))
    features["passive_scan_s"] = round(time.monotonic()-t0, 6)
    return features


def freeze(args):
    r63_result = json.loads((Path(args.prior) / "r63-final.json").read_text())
    old = r63_result["manifest"]
    check(r63_result["protocol"] == r63.PROTO and
          old["protocol"] == r63.PROTO and len(old["cases"]) == 32,
          "R63 provenance is incomplete")
    r66_prior = json.loads((Path(args.r66) / "new" / "manifest.json").read_text())
    check(r66_prior["protocol"] ==
          "DRNAS-R66-R65-NEW-SOURCE-BLIND-SHORT-20261103-v1",
          "wrong or missing R66 exclusion registry")
    r66_attempts = {x["gbd"] for x in r66_prior["selection_attempts"]}
    r66_attempts.update(x["gbd"] for x in r66_prior["cases"])
    check(len(r66_attempts) >= 12, "R66 attempted IDs incomplete")
    previous_seen = (set(old["excludes_previously_seen_gbd"]) |
                     {x["gbd"] for x in old["cases"]} |
                     {x["gbd"] for x in old["selection_attempts"]})
    check(not (r66_attempts & previous_seen),
          "prior R63/R66 cohorts unexpectedly overlap")
    augmented = copy.deepcopy(r63_result)
    augmented["manifest"]["excludes_previously_seen_gbd"] = sorted(
        set(old["excludes_previously_seen_gbd"]) | r66_attempts)
    ledger = Path(args.out).parent / "r67-source-exclusion-ledger"
    ledger.mkdir(parents=True, exist_ok=True)
    (ledger / "r63-final.json").write_text(json.dumps(augmented, indent=2)+"\n")
    print("R67_PRIOR_EXCLUSION", json.dumps({
        "r63_seen": len(previous_seen), "r66_attempted": len(r66_attempts),
        "candidate_remaining": 400-len(previous_seen | r66_attempts),
        "r63_final_sha256": digest(Path(args.prior)/"r63-final.json"),
        "r66_manifest_sha256": digest(Path(args.r66)/"new"/"manifest.json")
    }), flush=True)
    # Existing, independently tested 2026 Main source fetch, SHA freezer and
    # independent parity inspector.  Target 30; report any size-censor shortfall.
    r66.freeze(SimpleNamespace(prior=str(ledger), out=args.out))
    root = Path(args.out)
    manifest_path = root / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    check(manifest["protocol"] == PROTO, "protocol changed")
    check(not {c["gbd"] for c in manifest["cases"]} &
          (previous_seen | r66_attempts), "old formula leaked into R67")
    for c in manifest["cases"]:
        c["r67_features"] = passive_features(root/c["filename"], c)
    manifest["r67_design"] = dict(
        experiment="diagnostic_only_no_solver_change",
        frozen_modes=list(MODES), repeats=REPS, cap_s=CAP,
        parallel_shards=SHARDS, target_new_sources=TARGET,
        actual_new_sources=len(manifest["cases"]),
        new_source_shortfall=TARGET-len(manifest["cases"]),
        previous_excluded=len(previous_seen | r66_attempts),
        prior_r63_final_sha256=digest(Path(args.prior)/"r63-final.json"),
        prior_r66_manifest_sha256=digest(Path(args.r66)/"new"/"manifest.json"),
        diagnostic_features_measured_before_solver_timing=True,
        notes=[
            "Only verified official Main 2026 sources, SHA-disjoint from prior frozen/attempted R63 and R66 inputs",
            "No XOR conclusion drawn from incomplete parity patterns",
            "Passive structural scan excluded from all solver timings; cost recorded separately",
            "Exact source scan/size guards may leave fewer than 30 eligible instances",
            "No source selected based on observed solver performance or diagnostic feature",
            "Matched randomized 2 repeats per mode, one CPU per shard",
            "The R65, R28 and pinned Kissat algorithms remain unchanged",
            "SAT witnesses checked against originals; UNSAT without independent proof is not independently certified",
            "Timeouts count double in PAR2; this is not an official competition"
        ])
    manifest_path.write_text(json.dumps(manifest, indent=2)+"\n")
    print("R67_FREEZE_PASS", json.dumps({
        "target": TARGET, "actual": len(manifest["cases"]),
        "groups": dict(collections.Counter(c["group"] for c in manifest["cases"])),
        "r65_eligible": sum(c["r67_features"]["r65_eligible"]
                            for c in manifest["cases"]),
        "passive_scan_total_s": round(sum(c["r67_features"]["passive_scan_s"]
                            for c in manifest["cases"]), 3)
    }), flush=True)


def audit(args):
    root = Path(args.sources)
    mf = json.loads((root/"manifest.json").read_text())
    check(mf["protocol"] == PROTO and mf["r67_design"]["frozen_modes"] == list(MODES),
          "wrong manifest or modes")
    rows, pins = [], set()
    for shard in range(SHARDS):
        res = Path(args.combined)/f"r67-shard-{shard}"/"results"
        meta = json.loads((res/"meta.json").read_text())
        check(meta["protocol"] == PROTO and meta["shard"] == shard
              and meta["manifest_sha"] == digest(root/"manifest.json")
              and meta["cap_s"] == CAP and
              meta["count"] == len(mf["cases"][shard::SHARDS]),
              f"shard {shard} metadata drift")
        pins.add((meta["kissat_sha"], meta["gf2_sha"]))
        shard_rows = json.loads((res/"rows.json").read_text())
        check(len(shard_rows) == meta["count"]*REPS*len(MODES),
              f"shard {shard} incomplete")
        rows.extend(shard_rows)
    check(len(pins) == 1 and len(rows) == len(mf["cases"])*REPS*len(MODES),
          "binary drift or missing trials")
    per_case, triples = [], []
    for case in mf["cases"]:
        rr = [x for x in rows if x["gbd"] == case["gbd"]]
        check(len(rr) == REPS*len(MODES) and
              all(x["sha256"] == case["sha256"] and
                  x["group"] == case["group"] for x in rr),
              "case identity mismatch")
        reps = []
        for rep in range(REPS):
            q = [x for x in rr if x["rep"] == rep]
            check(len(q) == len(MODES) and
                  {x["mode"] for x in q} == set(MODES),
                  "unpaired mode or duplicate")
            check(all(x["answer"] in ("SAT", "UNSAT", "TIMEOUT") and
                  0 <= x["wall_s"] <= CAP and
                  x["par2_s"] == (2*CAP if x["answer"] == "TIMEOUT"
                    else x["wall_s"]) for x in q),
                  "invalid runtime or PAR2")
            check(all(x["answer"] in ("TIMEOUT", case["official_status"]) for x in q),
                  "official verdict disagreement")
            reps.append({x["mode"]: x for x in q})
        triples.extend(reps)
        scores = {mode: round(sum(r[mode]["par2_s"] for r in reps),6)
                  for mode in MODES}
        base = scores["clean_kissat"]
        gf = scores["r28_exact_gf2_fallback"]
        new = scores["r65_xor_cnf_feedback"]
        per_case.append(dict(
            gbd=case["gbd"], sha256=case["sha256"],
            group=case["group"], features=case["r67_features"],
            par2_by_mode=scores,
            r65_vs_kissat_saved_s=round(base-new,6),
            r65_vs_r28_saved_s=round(gf-new,6),
            r28_vs_kissat_saved_s=round(base-gf,6),
            r65_added_clause_trials=sum(
                int(x["r65_xor_cnf_feedback"].get("added_clauses",0)>0)
                for x in reps),
            r65_max_added_clauses=max(
                x["r65_xor_cnf_feedback"].get("added_clauses",0)
                for x in reps),
            r65_max_probes=max(
                x["r65_xor_cnf_feedback"].get("probes",0)
                for x in reps),
            r65_preprocess_total_s=round(sum(
                x["r65_xor_cnf_feedback"].get("preprocess_s",0.0)
                for x in reps),6)))
    summary = {}
    for group in ("ALL",)+GROUPS:
        grouprows = [x for x in rows if group=="ALL" or x["group"]==group]
        bymode = {}
        for mode in MODES:
            q = [x for x in grouprows if x["mode"]==mode]
            bymode[mode] = dict(
                trials=len(q), solved=sum(x["answer"]!="TIMEOUT" for x in q),
                timeouts=sum(x["answer"]=="TIMEOUT" for x in q),
                par2_s=round(sum(x["par2_s"] for x in q),6))
        base = bymode[MODES[0]]["par2_s"]
        gf = bymode[MODES[1]]["par2_s"]
        new = bymode[MODES[2]]["par2_s"]
        summary[group] = dict(by_mode=bymode,
            r65_vs_kissat_gain_pct=round(100*(1-new/base),4) if base else None,
            r65_vs_r28_gain_pct=round(100*(1-new/gf),4) if gf else None)
    diagnostics = dict(
        actual_sources=len(mf["cases"]), target_sources=TARGET,
        size_censored_shortfall=TARGET-len(mf["cases"]),
        r65_eligible_sources=sum(c["features"]["r65_eligible"] for c in per_case),
        r65_active_sources=sum(c["r65_added_clause_trials"]>0 for c in per_case),
        r65_extra_wins_over_r28_0_5s=sum(c["r65_vs_r28_saved_s"]>0.5
                                        for c in per_case),
        r65_extra_losses_over_r28_0_5s=sum(c["r65_vs_r28_saved_s"] < -0.5
                                          for c in per_case),
        passive_scan_total_s=round(sum(c["features"]["passive_scan_s"]
                                     for c in per_case),6))
    final = dict(protocol=PROTO, status="PASS", manifest=mf,
                 binary_sha=list(pins)[0], measurements=len(rows),
                 summary=summary, diagnostics=diagnostics,
                 per_formula=per_case)
    Path(args.json).write_text(json.dumps(final,indent=2)+"\n")
    lines = [
        "# R67: Structural diagnostic — unchanged Kissat / R28 / R65",
        f"{len(mf['cases'])} new SHA-disjoint verified official Main2026 CNFs; "
        f"target {TARGET}; {REPS} repetitions, {CAP:g}s per solver, "
        f"{SHARDS} parallel shards.",
        "PAR2: 120 seconds per timeout. Lower is better. All processing "
        "and SAT model verification are inside solver caps.",
        "The passive diagnostic scan happens **outside** solver timing; "
        "its cost is reported separately.",
        "",
        "| Structure | Cases | Kissat PAR2 (s) | R28 PAR2 (s) | R65 PAR2 (s) "
        "| R65 gain vs Kissat | Extra R65 gain vs R28 |",
        "|---|---:|---:|---:|---:|---:|---:|"]
    for group, info in summary.items():
        bm = info["by_mode"]
        cases = len(mf["cases"]) if group=="ALL" else sum(
            c["group"]==group for c in mf["cases"])
        pct = lambda x: "n/a" if x is None else f"{x:+.4f}%"
        lines.append(f"| {group} | {cases} | "
            f"{bm[MODES[0]]['par2_s']:.3f} | "
            f"{bm[MODES[1]]['par2_s']:.3f} | "
            f"{bm[MODES[2]]['par2_s']:.3f} | "
            f"{pct(info['r65_vs_kissat_gain_pct'])} | "
            f"{pct(info['r65_vs_r28_gain_pct'])} |")
    lines += ["", "## Passive features, R65 activations and marginal gains",
              "Measured passive scan cost: "
              f"{diagnostics['passive_scan_total_s']:.3f} s across cohort.",
              "R65 eligible: "
              f"{diagnostics['r65_eligible_sources']}; "
              "actual newly derived clause activations: "
              f"{diagnostics['r65_active_sources']}.",
              "",
              "| Source ID | Group | Exact | Cross clauses | "
              "Active reps | R65 − Kissat saved (s) | R65 − R28 saved (s) |",
              "|---|---|---:|---:|---:|---:|---:|"]
    for c in per_case:
        f = c["features"]
        lines.append(f"| {c['gbd'][:12]} | {c['group']} | "
            f"{f['exact_blocks'] if f['exact_blocks'] is not None else 'n/a'} | "
            f"{f['xor_cnf_bridge_clauses']} | "
            f"{c['r65_added_clause_trials']} | "
            f"{c['r65_vs_kissat_saved_s']:+.3f} | "
            f"{c['r65_vs_r28_saved_s']:+.3f} |")
    lines += ["", "## Interpretation guardrails",
      "- Source preselection is outcome-blind, but size/status censorship "
      "and exact-XOR scarcity limit generalization.",
      "- A pure-XOR win inherited from R28 is NOT evidence of incremental R65 benefit.",
      "- Partial XOR patterns are descriptive only, never treated as proven equations.",
      "- UNSAT answers without independently checked proof are not proof-certified.",
      "- No gate was trained on this test; use distinct future held-out formulas "
      "for any learned selector.",
      f"- Precommitted 30-formula target shortfall: "
      f"{diagnostics['size_censored_shortfall']}." ]
    Path(args.md).write_text("\n".join(lines)+"\n")
    print("R67_FINAL_AUDIT_PASS", json.dumps({
        "summary": summary["ALL"], "diagnostics": diagnostics,
        "groups": {k:summary[k]["r65_vs_r28_gain_pct"] for k in GROUPS}
    },sort_keys=True),flush=True)


def main():
    configure()
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd",required=True)
    sub.add_parser("selftest")
    fr = sub.add_parser("freeze")
    for name in ("prior","r66","out"):
        fr.add_argument("--"+name,required=True)
    m = sub.add_parser("measure")
    for name in ("sources","kissat","gf2","out"):
        m.add_argument("--"+name,required=True)
    m.add_argument("--shard",type=int,required=True)
    a = sub.add_parser("audit")
    for name in ("sources","combined","json","md"):
        a.add_argument("--"+name,required=True)
    args = parser.parse_args()
    if args.cmd == "selftest":
        r65.selftest()
        r63.selftest()
        print("R67_SELFTEST_PASS",flush=True)
    elif args.cmd == "freeze":
        freeze(args)
    elif args.cmd == "measure":
        r66.measure(args)
    else:
        audit(args)


if __name__=="__main__":
    main()
