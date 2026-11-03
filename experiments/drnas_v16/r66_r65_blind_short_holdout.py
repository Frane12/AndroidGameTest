#!/usr/bin/env python3
"""R66: new-source blind holdout of the *unchanged* R65 CNF<->XOR algorithm.

Prospective, salted independent selection from SAT Competition 2026 Main:
exclude all previously known R63 historical cohorts, the whole R63 frozen
corpus, and even R63 attempted candidates. Never select by R65 outcome.
Pair pinned clean Kissat against R65 (preprocess + the exact SAME Kissat).
All parsing, preprocessing, solving and source-SAT-witness checks inside cap.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import io
import json
import os
import random
from pathlib import Path

import r28_exact_gf2_benchmark as r28
import r32p_real_satcomp26_benchmark as r32p
import r52_prospective_2026_toprefs as r52
import r63_real2026_xor_prevalence_fallback as r63
import r64_mixed_xor_implied as r64
import r65_xor_cnf_feedback as r65

PROTO = "DRNAS-R66-R65-NEW-SOURCE-BLIND-SHORT-20261103-v1"
SALT = "DRNAS-R66-20261103-INDEPENDENT-PRIOR-EXCLUSION-BLIND-SALT"
CAP = 20.0
REPS = 2
SHARDS = 8
TARGET = 12
MIN_READY = 8
MAX_ATTEMPTS = 96
RAW_CAP = 28 * 1024 * 1024
CNF_CAP = 48 * 1024 * 1024
MODES = ("clean_kissat", "r65_xor_cnf_feedback")
GROUPS = ("mixed_exact", "pure_exact", "partial_only", "no_exact", "unscannable")


def ck(cond, message):
    if not cond:
        raise RuntimeError("R66_FAIL_CLOSED " + str(message))


def digest(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def rank_id(gbd):
    return hashlib.sha256((SALT + ":" + gbd).encode()).hexdigest()


def freeze(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    old_result = json.loads((Path(a.prior) / "r63-final.json").read_text())
    ck(old_result["protocol"] == r63.PROTO, "R63 final protocol drift")
    old = old_result["manifest"]
    ck(old["protocol"] == r63.PROTO and len(old["cases"]) == 32,
       "R63 source registry missing/incomplete")
    seen = set(old["excludes_previously_seen_gbd"])
    seen.update(c["gbd"] for c in old["cases"])
    seen.update(x["gbd"] for x in old["selection_attempts"])
    known_sha = {c["sha256"] for c in old["cases"]}
    ck(len(seen) > 90, "source exclusion registry unexpectedly small")

    index_bytes = r52.fetch_bytes(r52.URI, 100000)
    gbd_ids = [u.strip().rsplit("/", 1)[-1]
               for u in index_bytes.decode().strip().splitlines()]
    ck(len(gbd_ids) == 400 and len(set(gbd_ids)) == 400,
       "official 2026 Main index not the expected 400 IDs")
    score_bytes = r52.fetch_bytes(r52.SCORES, 32 * 1024 * 1024)
    official = [x for x in csv.DictReader(io.StringIO(score_bytes.decode()))
                if x["solverid"] == "biere_cadical3[main]"
                and x["instanceid"] in set(gbd_ids)]
    ck(len(official) == 400, "verified official status list missing")
    status = {x["instanceid"]: x["status"] for x in official}
    candidates = sorted((g for g in gbd_ids if g not in seen), key=rank_id)
    ck(len(candidates) >= MAX_ATTEMPTS, "too few previously unused official IDs")

    r32p.CNF_LIMIT = CNF_CAP
    selected, attempts = [], []
    for g in candidates[:MAX_ATTEMPTS]:
        if len(selected) >= TARGET:
            break
        state = status[g]
        note = {"gbd": g, "official_status": state}
        path = out / (g + ".cnf")
        if state not in ("sat-verified", "unsat-verified"):
            note["state"] = "UNVERIFIED_OFFICIAL_STATUS"
        else:
            try:
                raw, redirect = r32p.request_url(
                    "https://benchmark-database.de/file/" + g,
                    RAW_CAP, seconds=35)
                cnf, encoding = r32p.decode(raw)
                ck(len(cnf) <= CNF_CAP, "uncompressed source > cap")
                n, m = r32p.parse_dimacs_metadata(cnf)
                path.write_bytes(cnf)
                sha = digest(path)
                ck(sha not in known_sha, "previous R63 input SHA reused")
                ck(all(x["sha256"] != sha for x in selected),
                   "duplicate input SHA")
                scanned = r63.inspect_exact_xor(path, n, m)
                case = dict(gbd=g, filename=path.name, sha256=sha,
                    official_status=("SAT" if state == "sat-verified" else "UNSAT"),
                    variables=n, clauses=m, bytes=len(cnf),
                    source_url="https://benchmark-database.de/file/" + g,
                    source_redirect=redirect, compression=encoding,
                    raw_sha256=hashlib.sha256(raw).hexdigest(), **scanned)
                case["group"] = r64.group(case)
                selected.append(case)
                note.update(state="READY", sha256=sha,
                    group=case["group"], bytes=len(cnf))
            except Exception as e:
                path.unlink(missing_ok=True)
                note.update(state="EXCLUDED_SIZE_FETCH_OR_PARSE",
                    reason=(type(e).__name__ + ": " + str(e))[:240])
        attempts.append(note)
        print("R66_SOURCE", json.dumps(note, sort_keys=True), flush=True)
    manifest = dict(protocol=PROTO, source_selection_salt=SALT,
        official_uri=r52.URI, official_scores=r52.SCORES,
        official_index_sha256=hashlib.sha256(index_bytes).hexdigest(),
        official_scores_sha256=hashlib.sha256(score_bytes).hexdigest(),
        r63_final_sha256=digest(Path(a.prior) / "r63-final.json"),
        prior_excluded_gbd_count=len(seen),
        prior_excluded_gbd_sha256=hashlib.sha256(
            "\n".join(sorted(seen)).encode()).hexdigest(),
        cases=selected, selection_attempts=attempts, target=TARGET,
        max_attempts=MAX_ATTEMPTS, min_ready=MIN_READY, shards=SHARDS,
        repeats=REPS, cap_s=CAP, modes=list(MODES),
        restrictions=["Unmodified R65 algorithm from R65 branch commit",
          "Official Main 2026 original CNF, prospective salted ID selection",
          "Excludes all R63 historical IDs, R63 32 sources and attempted IDs",
          "No outcome/structure-based selection, except precommitted size censor",
          "SHA-frozen original sources and pinned original solver binary",
          "Only verified complete sign-mask XOR patterns infer equations",
          "Native guard declines huge/unsupported inputs and falls back",
          "All preprocess, solver and SAT witness verification within 20s",
          "Paired mode order randomly alternated on one pinned CPU per shard",
          "Size-censored sample, not an official competition ranking",
          "UNSAT status cross-checked against official result, not independently proof-certified",
          "Two repeats on limited examples cannot establish a universal speedup"])
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (out / "source.sha256").write_text(
        "".join(c["sha256"] + "  " + c["filename"] + "\n" for c in selected))
    ck(len(selected) >= MIN_READY, f"only {len(selected)} sources ready")
    ck(len({x["sha256"] for x in selected}) == len(selected),
       "source SHA not unique")
    print("R66_FROZEN_PASS", json.dumps(
        {"sources": len(selected), "attempted": len(attempts),
         "groups": dict(collections.Counter(c["group"] for c in selected)),
         "prior_excluded": len(seen)}), flush=True)


def measure(a):
    root, target = Path(a.sources), Path(a.out)
    manifest = json.loads((root / "manifest.json").read_text())
    ck(manifest["protocol"] == PROTO and 0 <= a.shard < SHARDS,
       "source protocol or shard mismatch")
    r63.CAP = CAP
    r65.CAP = CAP
    if hasattr(os, "sched_setaffinity"):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    kissat = Path(a.kissat).resolve()
    gf2 = Path(a.gf2).resolve()
    ck(kissat.is_file() and gf2.is_file(), "pinned executables not found")
    target.mkdir(parents=True, exist_ok=True)
    slice_cases = manifest["cases"][a.shard::SHARDS]
    meta = dict(protocol=PROTO, shard=a.shard,
        manifest_sha=digest(root / "manifest.json"),
        kissat_sha=digest(kissat), gf2_sha=digest(gf2),
        count=len(slice_cases), cap_s=CAP)
    (target / "meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    rows = []
    for c in slice_cases:
        source = (root / c["filename"]).resolve()
        ck(digest(source) == c["sha256"], "original DIMACS SHA drift")
        for rep in range(REPS):
            modes = list(MODES)
            seed = int(hashlib.sha256((PROTO + c["sha256"] + str(rep)).
                      encode()).hexdigest(), 16)
            random.Random(seed).shuffle(modes)
            for mode in modes:
                result = (r65.r65_one(source, c, kissat, gf2)
                          if mode == "r65_xor_cnf_feedback"
                          else r63.one(source, c, kissat, gf2, mode))
                row = dict(gbd=c["gbd"], sha256=c["sha256"],
                    group=c["group"], rep=rep, mode=mode, **result)
                rows.append(row)
                (target / "rows.json").write_text(json.dumps(rows, indent=2) + "\n")
                print("R66_TRIAL", c["gbd"], c["group"], rep,
                    mode, row["answer"], row["wall_s"], "PAR2",
                    row["par2_s"], "added", row.get("added_clauses", 0),
                    "route", row["native_route"], flush=True)
    ck(len(rows) == len(slice_cases) * REPS * len(MODES),
       "incomplete timed rows")
    print("R66_SHARD_PASS", a.shard, len(rows), flush=True)


def audit(a):
    root = Path(a.sources)
    mf = json.loads((root / "manifest.json").read_text())
    ck(mf["protocol"] == PROTO, "wrong source protocol")
    allrows, binary_pin = [], set()
    for shard in range(SHARDS):
        resultdir = Path(a.combined) / f"r66-shard-{shard}" / "results"
        meta = json.loads((resultdir / "meta.json").read_text())
        ck(meta["protocol"] == PROTO and meta["shard"] == shard
            and meta["manifest_sha"] == digest(root / "manifest.json")
            and meta["cap_s"] == CAP, "shard metadata drift")
        binary_pin.add((meta["kissat_sha"], meta["gf2_sha"]))
        rs = json.loads((resultdir / "rows.json").read_text())
        ck(len(rs) == meta["count"] * REPS * len(MODES),
           f"shard {shard} incomplete")
        allrows.extend(rs)
    ck(len(binary_pin) == 1, "nonidentical binary hashes")
    ck(len(allrows) == len(mf["cases"]) * REPS * len(MODES),
       "expected paired trials missing")
    case_rows, allpairs = [], []
    for case in mf["cases"]:
        rs = [x for x in allrows if x["gbd"] == case["gbd"]]
        ck(len(rs) == REPS * len(MODES)
           and all(x["sha256"] == case["sha256"] for x in rs),
           "case identity or SHA drift")
        pairs = []
        for rep in range(REPS):
            s = [x for x in rs if x["rep"] == rep]
            ck(len(s) == len(MODES) and {x["mode"] for x in s} == set(MODES),
               "unpaired baseline and experimental mode")
            pairs.append({x["mode"]: x for x in s})
        clean = sum(x["clean_kissat"]["par2_s"] for x in pairs)
        changed = sum(x["r65_xor_cnf_feedback"]["par2_s"] for x in pairs)
        active = sum(x["r65_xor_cnf_feedback"].get("added_clauses", 0) > 0
                     for x in pairs)
        case_rows.append(dict(gbd=case["gbd"], group=case["group"],
            sha256=case["sha256"], kissat_par2_s=round(clean, 6),
            r65_par2_s=round(changed, 6), delta_s=round(clean - changed, 6),
            r65_added_clause_trials=active,
            r65_added_clause_max=max(
                x["r65_xor_cnf_feedback"].get("added_clauses", 0) for x in pairs)))
        allpairs.extend(pairs)
    bygroup = {}
    for group in ("ALL",) + GROUPS:
        rows = [x for x in allrows if group == "ALL" or x["group"] == group]
        bygroup[group] = {}
        for mode in MODES:
            rr = [x for x in rows if x["mode"] == mode]
            bygroup[group][mode] = {
                "trials": len(rr), "solved": sum(x["answer"] != "TIMEOUT" for x in rr),
                "timeouts": sum(x["answer"] == "TIMEOUT" for x in rr),
                "par2_s": round(sum(x["par2_s"] for x in rr), 6)}
        old = bygroup[group][MODES[0]]["par2_s"]
        new = bygroup[group][MODES[1]]["par2_s"]
        bygroup[group]["gain_pct"] = round(
            100 * (1 - new / old), 4) if old else None
    significant = {"r65_wins_over_0_5s": sum(c["delta_s"] > 0.5 for c in case_rows),
                   "r65_losses_over_0_5s": sum(c["delta_s"] < -0.5 for c in case_rows),
                   "within_0_5s": sum(abs(c["delta_s"]) <= 0.5 for c in case_rows),
                   "active_r65_cases": sum(c["r65_added_clause_trials"] > 0
                                           for c in case_rows),
                   "native_supported_cases": sum(c["group"] != "unscannable"
                                                  for c in mf["cases"])}
    result = dict(protocol=PROTO, status="PASS", n_sources=len(mf["cases"]),
        n_attempts=len(allrows), source_selection=mf,
        summary=bygroup, per_formula=case_rows, diagnostics=significant,
        binary_sha=list(binary_pin)[0],
        limitations=mf["restrictions"])
    Path(a.json).write_text(json.dumps(result, indent=2) + "\n")
    lines = ["# R66: Independent short holdout of unchanged R65 versus pinned Kissat",
      f"**{len(mf['cases'])} new official Main2026 sources**, "
      f"{len(allrows)} measured trials; {REPS} repeats; "
      f"{CAP:g}s cap per mode; {SHARDS} parallel shards.",
      "PAR2 uses 40s for each timeout; smaller is better.",
      "Sources were selected by salted GBD hash *before solving*, "
      "excluding previous R63 known and attempted IDs.",
      "", "| Group | Kissat PAR2 (s) | R65 PAR2 (s) | Gain |",
      "|---|---:|---:|---:|"]
    for group, data in bygroup.items():
        gain = data["gain_pct"]
        gain_text = f"{gain:+.3f}%" if gain is not None else "n/a (0 trials)"
        lines.append(f"| {group} | {data[MODES[0]]['par2_s']:.3f} | "
            f"{data[MODES[1]]['par2_s']:.3f} | {gain_text} |")
    lines += ["", "## R65 active benefit and harm",
      json.dumps(significant, sort_keys=True), "",
      "| ID | Group | Kissat PAR2 (s) | R65 PAR2 (s) | Saved (s) | New clauses trials |",
      "|---|---|---:|---:|---:|---:|"]
    for c in case_rows:
        lines.append(f"| {c['gbd'][:12]} | {c['group']} | "
            f"{c['kissat_par2_s']:.3f} | {c['r65_par2_s']:.3f} | "
            f"{c['delta_s']:+.3f} | {c['r65_added_clause_trials']} |")
    lines += ["", "## Limitations"] + ["- " + x for x in mf["restrictions"]]
    Path(a.md).write_text("\n".join(lines) + "\n")
    print("R66_FINAL_AUDIT_PASS", json.dumps({
        "sources": len(mf["cases"]), "trials": len(allrows),
        "summary": bygroup, "diagnostics": significant}, sort_keys=True),
        flush=True)


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("selftest")
    f = sub.add_parser("freeze")
    for name in ("prior", "out"):
        f.add_argument("--" + name, required=True)
    m = sub.add_parser("measure")
    for name in ("sources", "kissat", "gf2", "out"):
        m.add_argument("--" + name, required=True)
    m.add_argument("--shard", type=int, required=True)
    a = sub.add_parser("audit")
    for name in ("sources", "combined", "json", "md"):
        a.add_argument("--" + name, required=True)
    options = p.parse_args()
    if options.cmd == "selftest":
        r65.selftest()
    elif options.cmd == "freeze":
        freeze(options)
    elif options.cmd == "measure":
        measure(options)
    else:
        audit(options)


if __name__ == "__main__":
    main()
