#!/usr/bin/env python3
"""R67: no-rerun, cross-cohort structural attribution of frozen R65/R66 evidence.

R65 is exploratory/replayed; R66 is independent short holdout. Never pool them
as if they were a single prospective benchmark. Report PAR-2 and activation
separately; in particular distinguish R28 GF(2) gain from R65 feedback gain.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
from pathlib import Path

def check(ok, message):
    if not ok:
        raise RuntimeError("R67_FAIL_CLOSED: " + message)

def read(path):
    check(path.is_file(), "missing " + str(path))
    return json.loads(path.read_text())

def sha_index(manifest):
    cases = manifest["cases"]
    hashes = [c["sha256"] for c in cases]
    check(len(set(hashes)) == len(hashes), "duplicated source SHA")
    return set(hashes)

def analyze(a):
    old = Path(a.r65)
    unseen = Path(a.r66)
    x = read(old / "r65-final.json")
    y = read(unseen / "r66-final.json")
    m65 = read(old / "manifest.json")
    m66 = read(unseen / "manifest.json")
    check(x["status"] == "PASS" and y["status"] == "PASS", "upstream audit status")
    hashes65, hashes66 = sha_index(m65), sha_index(m66)
    check(not (hashes65 & hashes66), "R65/R66 source SHA overlap")
    check(len(hashes65) == x["sources"] == 18, "unexpected R65 cohort")
    check(len(hashes66) == y["n_sources"] == 12, "unexpected R66 cohort")
    check(x["trials"] == 108 and y["n_attempts"] == 48, "incomplete upstream trials")

    k = "clean_kissat"
    b = "r28_exact_gf2_fallback"
    f = "r65_xor_cnf_feedback"
    sx = x["summary"]["ALL"]
    sy = y["summary"]["ALL"]
    old_cases = x["per_case"]
    new_cases = y["per_formula"]
    check(len(old_cases) == 18 and len(new_cases) == 12, "missing per-formula rows")
    groups = sorted(set(v["group"] for v in old_cases.values()) |
                    set(v["group"] for v in new_cases))
    strata = {}
    for g in ["ALL"] + groups:
        selected = [v for v in old_cases.values()
                    if g == "ALL" or v["group"] == g]
        total_base = sum(v["par2"][k] for v in selected)
        total_r28 = sum(v["par2"][b] for v in selected)
        total_r65 = sum(v["par2"][f] for v in selected)
        holdout = [v for v in new_cases
                   if g == "ALL" or v["group"] == g]
        strata[g] = {
            "r65_replayed_sources": len(selected),
            "r65_active_clause_sources": sum(v["max_added_clauses"] > 0 for v in selected),
            "r65_kissat_par2_s": round(total_base, 6),
            "r65_r28_par2_s": round(total_r28, 6),
            "r65_feedback_par2_s": round(total_r65, 6),
            "r28_saved_vs_kissat_par2_s": round(total_base - total_r28, 6),
            "feedback_extra_saved_vs_r28_par2_s": round(total_r28 - total_r65, 6),
            "r66_blind_sources": len(holdout),
            "r66_active_feedback_sources": sum(v["r65_added_clause_trials"] > 0 for v in holdout),
            "r66_kissat_par2_s": round(sum(v["kissat_par2_s"] for v in holdout), 6),
            "r66_feedback_par2_s": round(sum(v["r65_par2_s"] for v in holdout), 6),
            "r66_saved_vs_kissat_par2_s": round(sum(v["delta_s"] for v in holdout), 6),
            "r66_benefit_gt_half_s": sum(v["delta_s"] > 0.5 for v in holdout),
            "r66_harm_gt_half_s": sum(v["delta_s"] < -0.5 for v in holdout),
        }
    check(abs(strata["ALL"]["r65_kissat_par2_s"]-sx[k]["par2_s"]) < 0.01,
          "R65 baseline total does not match audit")
    check(abs(strata["ALL"]["r65_feedback_par2_s"]-sx[f]["par2_s"]) < 0.01,
          "R65 treatment total does not match audit")
    check(abs(strata["ALL"]["r66_kissat_par2_s"]-sy[k]["par2_s"]) < 0.01,
          "R66 baseline total does not match audit")
    check(abs(strata["ALL"]["r66_feedback_par2_s"]-sy[f]["par2_s"]) < 0.01,
          "R66 treatment total does not match audit")
    check(y["diagnostics"]["active_r65_cases"] ==
          strata["ALL"]["r66_active_feedback_sources"], "R66 activation inconsistency")

    # Deliberate evidence gate: no training on the R66 holdout, no new solver
    # branch, and no general speedup claim based only on exploratory R65 gain.
    signal = strata["ALL"]
    generalization = "NOT_ESTABLISHED"
    decision = ("Instrument conditional CNF/XOR propagation on structurally "
                "supported samples; freeze a decision rule before a NEW blind "
                "holdout. Keep unchanged Kissat fallback.")
    result = {
        "protocol": "DRNAS-R67-STRUCTURAL-ATTRIBUTION-V1",
        "status": "PASS",
        "mode": "AUDIT_EXISTING_ONLY_NO_SOLVER_RERUN",
        "verified_sha_disjoint": True,
        "exploratory_r65": {
            "sources": 18, "trials": 108, "replayed": True,
            "kissat_par2_s": sx[k]["par2_s"],
            "r28_par2_s": sx[b]["par2_s"],
            "feedback_par2_s": sx[f]["par2_s"],
            "feedback_extra_saved_over_r28_par2_s":
                round(sx[b]["par2_s"]-sx[f]["par2_s"], 6)
        },
        "blind_r66": {
            "sources": 12, "trials": 48,
            "kissat_trials": sy[k]["trials"],
            "kissat_solved": sy[k]["solved"],
            "feedback_solved": sy[f]["solved"],
            "kissat_timeouts": sy[k]["timeouts"],
            "feedback_timeouts": sy[f]["timeouts"],
            "kissat_par2_s": sy[k]["par2_s"],
            "feedback_par2_s": sy[f]["par2_s"],
            "active_cases": signal["r66_active_feedback_sources"],
        },
        "structural_attribution": strata,
        "general_speedup_claim": generalization,
        "decision": decision,
        "limitations": [
            "R65 was exploratory and previously seen; its strata were not prospectively blind.",
            "R66 20-second cap produced substantial right-censoring (timeouts).",
            "Small per-stratum counts preclude strong statistical conclusions.",
            "PAR2 combines solve time with timeout penalties; it is not CPU energy/time.",
            "No R28 arm on R66: do not claim a blind incremental R65-versus-R28 gain.",
            "A structural rule must be frozen before any new holdout.",
        ],
    }
    Path(a.json).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    lines = [
        "# R67 — Frozen structural attribution (no re-run)", "",
        "**PASS: 18 exploratory R65 originals and 12 SHA-disjoint R66 holdout originals.**",
        "This is an audit of existing data, NOT a new benchmark or independent proof of a speedup.",
        "",
        "## End-to-end PAR2 (lower is better)", "",
        "| Cohort | Kissat | R28 GF2 | R65 feedback | Feedback gain beyond R28 |",
        "|---|---:|---:|---:|---:|",
        f"| R65 replay (36 trials/method, cap 40s) | {sx[k]['par2_s']:.3f} | {sx[b]['par2_s']:.3f} | {sx[f]['par2_s']:.3f} | {sx[b]['par2_s']-sx[f]['par2_s']:+.3f} s |",
        f"| R66 unseen (24 trials/method, cap 20s) | {sy[k]['par2_s']:.3f} | n/a | {sy[f]['par2_s']:.3f} | n/a |",
        "",
        f"R66 solved: Kissat {sy[k]['solved']}/{sy[k]['trials']}, R65 {sy[f]['solved']}/{sy[f]['trials']}. "
        f"R65 added clauses on {signal['r66_active_feedback_sources']}/12 unseen formulas.",
        "",
        "## Structural diagnostic", "",
        "| Group | R65 sources | R65 GF2 saved vs Kissat | Extra CNF/XOR saved vs GF2 | R66 sources | R66 activations | R66 saved vs Kissat |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for g, d in strata.items():
        lines.append(f"| {g} | {d['r65_replayed_sources']} | "
                     f"{d['r28_saved_vs_kissat_par2_s']:+.3f} | "
                     f"{d['feedback_extra_saved_vs_r28_par2_s']:+.3f} | "
                     f"{d['r66_blind_sources']} | {d['r66_active_feedback_sources']} | "
                     f"{d['r66_saved_vs_kissat_par2_s']:+.3f} |")
    lines += ["", "## Decision", "**No verified general speedup on blind R66.**",
              decision, "", "## Limits"] + ["- " + s for s in result["limitations"]]
    Path(a.md).write_text("\n".join(lines) + "\n")
    print("R67_ATTRIBUTION_AUDIT_PASS", json.dumps({
        "r65_extra_feedback_gain_s": result["exploratory_r65"]["feedback_extra_saved_over_r28_par2_s"],
        "r66_kissat_par2_s": sy[k]["par2_s"],
        "r66_feedback_par2_s": sy[f]["par2_s"],
        "r66_active_sources": signal["r66_active_feedback_sources"],
        "sha_disjoint": True,
        "decision": generalization,
    }, sort_keys=True), flush=True)

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--r65", required=True)
    p.add_argument("--r66", required=True)
    p.add_argument("--json", required=True)
    p.add_argument("--md", required=True)
    analyze(p.parse_args())
