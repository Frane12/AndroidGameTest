#!/usr/bin/env python3
"""DRNAS X13E: causal certified-reduction test on two X13C positives + six
reference-confirmed X11 historical controls. Historical hard replay
and reference-screened easy samples are NOT a blind or prospective holdout.
A solved SAT witness is checked on the original CNF; UNSAT is agreement-only,
never a claim of independent LRAT. No changes to stable solver or main.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import pathlib
import random
import re
import sys

import mre_x13b_sample_gate as b
import mre_x6_fresh_short as x6
import mre_x11_placebo_causal as x11
import mre7_extended_easy_freeze as pool
import mre7_reference_easy_freeze as fetch
import mre6b_blind_freeze as prior

ROOT = pathlib.Path("mre_x13e")
EASY = ROOT / "easy"
PROTO = "DRNAS-X13E-2HARD45-6X11REFEASY15-4ARM-2SEED-E2E-20261109-v3"
SALT = PROTO + "-SOURCE-ONLY-RANK"
ARMS = ("original", "reduce", "kissat", "cadical")
REPS, SHARDS, EASY_TARGET, YEAR_QUOTA = 2, 8, 6, 2
HARD_CAP, EASY_CAP, SCREEN_CAP = 45.0, 15.0, 10.0
YEARS = ("2021", "2022", "2023")
HARD_SHA = (
    "0743c859e08f35e0bab70c335a6c6e084a99dca6953db909e3255923900bf43a",
    "44f8473284ac4998a23f8120280e5d971d100358091169ed17275c74d46f56a2",
)
EXPECTED_REMOVED = (192, 507)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def need(ok, message):
    b.need(ok, "X13E: " + message)


def configure():
    b.ROOT = ROOT
    b.REPS = REPS
    b.SHARDS = SHARDS
    b.ARMS = ARMS
    b.PROTO = PROTO


def hashes():
    return {
        "native": b.sha("mre_x4/bin/native"),
        "kissat": b.sha("built/bin/kissat_4_0_4"),
        "cadical": b.sha("/usr/bin/cadical"),
        "cms_lib": b.sha("mre5/lib/libcryptominisat5.so.5.11"),
    }


def source_path(c):
    return pathlib.Path(c["source_dir"]) / c["filename"]


def historical_exclusions():
    """A documented partial historical registry, not an exhaustive guarantee."""
    names = ("mre7_easy/manifest.json", "mre11b_blind/manifest.json",
             "mre_x6fresh/manifest.json")
    ids, shas = set(), set()
    registry = []
    def visit(v):
        if isinstance(v, dict):
            for x in v.values():
                visit(x)
        elif isinstance(v, list):
            for x in v:
                visit(x)
        elif isinstance(v, str):
            if re.fullmatch("[0-9a-f]{32}", v):
                ids.add(v)
            elif re.fullmatch("[0-9a-f]{64}", v):
                shas.add(v)
    for filename in names:
        p = pathlib.Path(filename)
        need(p.is_file(), "prior registry missing: " + filename)
        visit(json.loads(p.read_text()))
        registry.append({"file": filename, "sha256": b.sha(p)})
    need(prior.PRIOR.is_file(), "missing historical GBD registry")
    for v in prior.PRIOR.read_text().splitlines():
        if re.fullmatch("[0-9a-f]{32}", v.strip()):
            ids.add(v.strip())
    registry.append({"file": str(prior.PRIOR), "sha256": b.sha(prior.PRIOR)})
    return ids, shas, registry


def make_hard():
    manifest = x6.verify()
    catalog = {c["sha256"]: c for c in manifest["cases"]}
    need(all(s in catalog for s in HARD_SHA), "X13C positive SHAs not in frozen X6fresh")
    results = []
    for i, srcsha in enumerate(HARD_SHA):
        c = dict(catalog[srcsha], tier="hard", cohort="X13C_replay_positive_not_blind",
                 cap_s=HARD_CAP, source_dir="mre_x6fresh")
        n, cls = x11.x9.x2.parse(source_path(c))
        _, reduction = b.transform(cls, "reduce")
        need(reduction["deleted"] == EXPECTED_REMOVED[i],
             "prior X13C clause-reduction positive drift")
        c["expected_reduction"] = reduction["deleted"]
        results.append(c)
    return results


def screen_reference(c):
    """Reference-only eligibility BEFORE measured four-arm pairing.
    Select with 10s Kissat SAT witness or 10s Kissat + CaDiCaL UNSAT agreement.
    This makes the easy cohort reference-biased, never a blind evaluation.
    """
    old = b.CAP
    old_root = x11.ROOT
    try:
        b.CAP = SCREEN_CAP
        x11.ROOT = EASY
        k = b.trial(c, 0, "kissat")
        out = {"kissat_status": k["status"], "kissat_s": k["elapsed_s"]}
        if k["status"] == "SAT" and k["SAT_original_witness_verified"]:
            out["status"] = "SAT"
            return out
        if k["status"] == "UNSAT":
            d = b.trial(c, 0, "cadical")
            out.update(cadical_status=d["status"], cadical_s=d["elapsed_s"])
            if d["status"] == "UNSAT":
                out["status"] = "UNSAT"
                out["UNSAT_cross_solver_agreement_not_LRAT"] = True
                return out
        out["status"] = "NOT_EASY"
        return out
    finally:
        b.CAP = old
        x11.ROOT = old_root


def freeze():
    """Historical reference-conditioned control, not a fresh blind holdout.

    Select six X11 originals using ONLY two-repetition Kissat/CaDiCaL
    decisions from frozen X13D before any X13E measurement. Avoid the
    unsatisfiable 2021 minisat1m two-per-year quota. Source SHAs remain
    immutable and the original X13C two-source arm remains unchanged.
    """
    configure()
    b.selftest()
    hard = make_hard()
    historical = ROOT / "reference-history.json"
    need(historical.is_file(), "missing frozen X13D original reference report")
    report = json.loads(historical.read_text())
    need(report["experiment"] == "X13D" and report["sources"] == 32
         and report["trials"] == 576 and len(report["rows"]) == 576,
         "incorrect historical X13D reference report")
    old = x11.verify()
    need(len(old["cases"]) == 32, "wrong frozen X11 source roster")
    cases_by_sha = {c["sha256"]: c for c in old["cases"]}
    by_sha = collections.defaultdict(list)
    for r in report["rows"]:
        need(r["original_sha256"] in cases_by_sha, "reference report has unknown SHA")
        by_sha[r["original_sha256"]].append(r)
    need(set(by_sha) == set(cases_by_sha), "historical reference roster drift")
    current_hashes = hashes()
    ready, trace = [], []
    for sha, c in cases_by_sha.items():
        entries = by_sha[sha]
        k = [r for r in entries if r["arm"] == "kissat"]
        d = [r for r in entries if r["arm"] == "cadical"]
        need(len(k) == len(d) == REPS, "reference repeats missing")
        need(all(r["binary_sha256"] == current_hashes[arm]
                 for arm, rr in (("kissat", k), ("cadical", d)) for r in rr),
             "historical reference backend binary mismatch")
        need(all(r["gbd"] == c["gbd"] for r in k + d),
             "historical reference original mismatch")
        statuses = {r["status"] for r in k + d}
        yes = (statuses == {"SAT"} and
               all(r["SAT_original_witness_verified"] for r in k + d))
        no = statuses == {"UNSAT"}  # independent solver agreement, not LRAT
        within = all(r["elapsed_s"] < SCREEN_CAP for r in k + d)
        matched = (yes or no) and within
        row = dict(gbd=c["gbd"], sha256=sha, status=next(iter(statuses))
                   if len(statuses) == 1 else "MIXED",
                   max_reference_s=max(r["elapsed_s"] for r in k + d),
                   qualified=matched,
                   historical_x13d_not_blind=True)
        trace.append(row)
        if matched:
            ready.append(c)
    need(len(ready) >= EASY_TARGET,
         "less than six independently reference-confirmed historical inputs")
    ready.sort(key=lambda c: digest((SALT + "|" + c["sha256"]).encode()))
    selected = []
    for c in ready[:EASY_TARGET]:
        selected.append(dict(c, tier="easy",
            cohort="X11_X13D_reference_confirmed_historical_NOT_BLIND",
            year=str(c.get("year", "historical_X11")),
            cap_s=EASY_CAP, source_dir="mre_x11",
            reference_eligibility=dict(
                status=next(r["status"] for r in by_sha[c["sha256"]]
                            if r["arm"] == "kissat"),
                prior_run=42567410128,
                confirmed_by="Kissat_and_CaDiCaL_two_repetitions",
                SCREEN_CAP_s=SCREEN_CAP,
                UNSAT_independent_LRAT=False)))
    need(len(selected) == EASY_TARGET, "historical easy cardinality")
    cases = hard + selected
    need(len({c["sha256"] for c in cases}) == SHARDS and
         len({c["gbd"] for c in cases}) == SHARDS,
         "repeated original case")
    ROOT.mkdir(exist_ok=True)
    b.save(ROOT / "selection-trace.json", trace)
    m = dict(protocol=PROTO, cases=cases, arms=ARMS, reps=REPS,
             cap_hard_s=HARD_CAP, cap_easy_s=EASY_CAP,
             cap_reference_screen_s=SCREEN_CAP,
             reference_prior_run=42567410128,
             reference_history_sha256=b.sha(historical),
             x11_source_manifest_sha256=b.sha("mre_x11/manifest.json"),
             reference_source_pool="X11 frozen SHA originals, X13D historical reference-only",
             reference_screened_easy_cohort_not_blind=True,
             historical_hard_not_blind=True, historical_easy_not_blind=True,
             retrospective_control_not_prospective=True,
             no_auto_promotion=True, SAT_original_witness_required=True,
             UNSAT_independent_LRAT=False,
             UNSAT_cross_solver_agreement_required=True,
             source_selection="6 X11 historical original SHA ranked by fixed salt only "
                 "AFTER independent Kissat/CaDiCaL agree SAT or UNSAT "
                 "and both seeds solve under 10s; no DRNAS timing used in eligibility",
             e2e_timing="includes CNF preprocessing, writing, launching and solving",
             binary_sha256=current_hashes,
             expected_trials=SHARDS * REPS * len(ARMS))
    b.save(ROOT / "manifest.json", m)
    verify()
    print("X13E_FROZEN", len(cases), m["expected_trials"], flush=True)


def verify():
    configure()
    x6.verify()
    m = json.loads((ROOT / "manifest.json").read_text())
    need(m["protocol"] == PROTO and m["expected_trials"] == 64 and
         tuple(m["arms"]) == ARMS and m["reps"] == REPS, "protocol mismatch")
    need(m["binary_sha256"] == hashes(), "pinned solver SHA changed")
    need(m["reference_history_sha256"] == b.sha(ROOT / "reference-history.json"),
         "historical reference report changed")
    need(m["x11_source_manifest_sha256"] == b.sha("mre_x11/manifest.json"),
         "historical X11 roster changed")
    need(len(m["cases"]) == SHARDS and
         len({c["sha256"] for c in m["cases"]}) == SHARDS, "source cardinality")
    for idx, c in enumerate(m["cases"]):
        p = source_path(c)
        need(p.is_file() and b.sha(p) == c["sha256"], "original source SHA drift")
        need(c["cap_s"] == (HARD_CAP if idx < 2 else EASY_CAP),
             "case cap drift")
        if idx < 2:
            need(c["sha256"] == HARD_SHA[idx] and
                 c["expected_reduction"] == EXPECTED_REMOVED[idx],
                 "hard positive mismatch")
        else:
            need(c["reference_eligibility"]["status"] in ("SAT", "UNSAT"),
                 "unqualified easy case")
    return m


def run_shard(index):
    m = verify()
    need(index in range(SHARDS), "bad shard")
    c = m["cases"][index]
    b.CAP = c["cap_s"]
    x11.ROOT = pathlib.Path(c["source_dir"])
    rows = []
    for rep in range(REPS):
        order = list(ARMS)
        random.Random(x11.seed(c, rep)).shuffle(order)
        for arm in order:
            r = b.trial(c, rep, arm)
            need(r["original_sha256"] == c["sha256"] and
                 r["cap_s"] == c["cap_s"], "trial provenance mismatch")
            r.update(tier=c["tier"], year=c["year"], source_dir=c["source_dir"])
            if c["tier"] == "hard" and arm == "reduce":
                need(r["reduction"]["deleted"] == c["expected_reduction"],
                     "hard positive reducer changed")
            rows.append(r)
            b.save(ROOT / ("shard-%d.json" % index), rows)
            print("X13E_TRIAL", json.dumps(r, sort_keys=True), flush=True)
    need(len(rows) == 8, "short shard")
    print("X13E_SHARD_PASS", index, len(rows), flush=True)


def audit():
    m = verify()
    cases = {c["sha256"]: c for c in m["cases"]}
    rows = []
    for idx in range(SHARDS):
        rows += json.loads((ROOT / ("shard-%d.json" % idx)).read_text())
    expected = {(sha, rep, arm) for sha in cases
                for rep in range(REPS) for arm in ARMS}
    observed = {(r["original_sha256"], r["rep"], r["arm"]) for r in rows}
    need(len(rows) == len(observed) == m["expected_trials"] and
         observed == expected, "missing/duplicated original-sha paired trials")
    for sha, c in cases.items():
        rr = [r for r in rows if r["original_sha256"] == sha]
        solved = {r["status"] for r in rr if r["status"] in ("SAT", "UNSAT")}
        need(len(solved) <= 1, "SAT/UNSAT disagreement on one original CNF")
        native_unsat = any(r["status"] == "UNSAT" and
                           r["arm"] in ("original", "reduce") for r in rr)
        kissat_unsat = any(r["status"] == "UNSAT" and r["arm"] == "kissat" for r in rr)
        cadical_unsat = any(r["status"] == "UNSAT" and r["arm"] == "cadical" for r in rr)
        unsat_crosschecked = ((native_unsat and (kissat_unsat or cadical_unsat)) or
                              (kissat_unsat and cadical_unsat))
        for r in rr:
            ref = "kissat" if r["arm"] == "kissat" else (
                  "cadical" if r["arm"] == "cadical" else "native")
            need(r["protocol"] == PROTO and
                 r["seed"] == x11.seed(c, r["rep"]) and
                 r["gbd"] == c["gbd"] and r["cap_s"] == c["cap_s"] and
                 r["binary_sha256"] == m["binary_sha256"][ref],
                 "protocol, binary or seed mismatch")
            need(r["status"] != "SAT" or
                 r["SAT_original_witness_verified"], "unverified SAT witness")
            need(r["status"] != "TIMEOUT" or
                 r["PAR2_s"] == 2*c["cap_s"], "incorrect PAR2 timeout penalty")
            need(r["status"] == "TIMEOUT" or
                 (r["elapsed_s"] <= c["cap_s"] and
                  r["PAR2_s"] == r["elapsed_s"]), "incorrect solved E2E PAR2")
            r["accepted"] = (r["status"] == "SAT" or
                             r["status"] == "UNSAT" and unsat_crosschecked)
            r["audited_PAR2_s"] = (r["PAR2_s"] if r["accepted"]
                                  else 2*c["cap_s"])
    def scores(part):
        by = {}
        for arm in ARMS:
            rr = [r for r in part if r["arm"] == arm]
            by[arm] = dict(trials=len(rr),
                           solved=sum(r["accepted"] for r in rr),
                           SAT=sum(r["accepted"] and r["status"] == "SAT" for r in rr),
                           UNSAT_crosschecked=sum(r["accepted"] and r["status"] == "UNSAT" for r in rr),
                           timeouts=sum(r["status"] == "TIMEOUT" for r in rr),
                           PAR2_s=round(sum(r["audited_PAR2_s"] for r in rr), 6),
                           prep_s=round(sum(r["preprocess_s"] for r in rr), 6),
                           clauses_deleted=sum(r["reduction"].get("deleted", 0) for r in rr))
        for arm, item in by.items():
            for base in ("original", "kissat", "cadical"):
                ref = by[base]["PAR2_s"]
                item["pct_less_PAR2_vs_" + base] = round(100*(1-item["PAR2_s"]/ref), 4)
                item["speedup_vs_" + base] = round(ref/item["PAR2_s"], 5)
        return by
    per_source = []
    for sha, c in cases.items():
        part = [r for r in rows if r["original_sha256"] == sha]
        per_source.append(dict(gbd=c["gbd"], sha256=sha, tier=c["tier"],
                               cap_s=c["cap_s"], year=c["year"],
                               results=scores(part)))
    results = dict(protocol=PROTO, count=len(cases), trials=len(rows),
                   no_auto_promotion=True, historical_hard_not_blind=True,
                   reference_screened_easy_not_blind=True,
                   UNSAT_independent_LRAT=False,
                   overall=scores(rows),
                   hard=scores([r for r in rows if r["tier"] == "hard"]),
                   easy=scores([r for r in rows if r["tier"] == "easy"]),
                   per_source=per_source, rows=rows)
    b.save(ROOT / "report.json", results)
    headline = {k:v for k,v in results.items() if k not in ("per_source","rows")}
    print("X13E_FINAL", json.dumps(headline, sort_keys=True), flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("selftest", "freeze", "verify", "shard", "audit"))
    p.add_argument("--shard", type=int, default=0)
    args = p.parse_args()
    configure()
    if args.action == "selftest":
        b.selftest()
        need(len(HARD_SHA)==2 and SHARDS==8 and REPS==2 and
             len(ARMS)==4, "locked matrix changed")
        print("X13E_SELFTEST_PASS", flush=True)
    elif args.action == "freeze":
        freeze()
    elif args.action == "verify":
        verify()
        print("X13E_VERIFY_PASS", flush=True)
    elif args.action == "shard":
        run_shard(args.shard)
    else:
        audit()


if __name__ == "__main__":
    main()
