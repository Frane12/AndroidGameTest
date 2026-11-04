#!/usr/bin/env python3
"""R65C smart OR portfolio: clean Kissat, R65, or both on pinned real SAT2026.

Research-only replay of R65's 18 pre-seen original formulas (NOT a blind holdout).
No speculative parity is ever asserted as a clause. All shared CNF clauses are
proved consequences of the original by R65's complete-XOR+BCP probes. Worker
communication uses proof-carrying implications before launch and verified
completion/cancellation afterward; stock Kissat has no live learnt-clause API.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import random
import signal
import subprocess
import tempfile
import time

import r65_xor_cnf_feedback as r65
import r63_real2026_xor_prevalence_fallback as r63
import r32p_real_satcomp26_benchmark as r32p
import r64_mixed_xor_implied as r64

PROTO = "DRNAS-R65C-SMART-OR-XOR-CNF-20261104-v1"
SHARDS = 8
REPS = 2
CAP = 40.0
MODES = ("clean_kissat", "r65_xor_cnf_feedback", "r65c_smart_or")
TICK_S = 0.02

def ck(ok, why):
    if not ok:
        raise RuntimeError("R65C_FAIL_CLOSED " + str(why))

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def policy(case):
    """Frozen, performance-agnostic structural gate; no oracle/heldout labels."""
    if not case["supported"] or not case.get("complete_blocks"):
        return "standard_only"
    if case.get("pure_exact_xor"):
        return "cooperative_only"
    coverage = float(case.get("coverage_fraction") or 0.0)
    blocks = int(case.get("complete_blocks") or 0)
    if blocks >= 4 and coverage >= 0.20 and not case.get("partial_support_groups"):
        return "cooperative_only"
    return "both_candidate"

def score(info, clauses, prep_s):
    """Signal is heuristic; proof-carrying clauses themselves are never heuristic."""
    return (len(clauses) + 4 * int(info.get("conflicting_probes", 0))
            + 2 * int(info.get("root_units", 0))) / max(0.1, 1.0 + 2 * prep_s)

def terminate(worker):
    if not worker:
        return
    p = worker["proc"]
    if p.poll() is None:
        try:
            os.killpg(p.pid, signal.SIGTERM)
            p.wait(timeout=0.5)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            p.wait()
    worker["out"].close()
    worker["err"].close()

def launch(kissat, source, route):
    out = tempfile.TemporaryFile(mode="w+t", encoding="utf-8", errors="replace")
    err = tempfile.TemporaryFile(mode="w+t", encoding="utf-8", errors="replace")
    try:
        proc = subprocess.Popen([str(kissat), str(source)], stdout=out, stderr=err,
                                start_new_session=True)
    except Exception:
        out.close()
        err.close()
        raise
    return dict(route=route, proc=proc, out=out, err=err)

def verified_outcome(worker, original, case):
    p = worker["proc"]
    code = p.poll()
    if code is None:
        return None
    ck(code in (10, 20), "worker " + worker["route"] + " returned " + str(code))
    answer = "SAT" if code == 10 else "UNSAT"
    ck(answer == case["official_status"], "contradiction of official label")
    if answer == "SAT":
        worker["out"].seek(0)
        r32p.verify_sat_witness(original, worker["out"].read())
        proof = "SAT_original_model_verified"
    else:
        # Kissat itself is not an independently proof-certified UNSAT result.
        proof = "UNSAT_Kissat_official_status_only"
    return answer, proof

def smart_one(source, case, kissat, gf2):
    t0 = time.monotonic()
    deadline = t0 + CAP
    preferred = policy(case)
    if preferred == "cooperative_only" and case.get("pure_exact_xor"):
        row = r65.r65_one(source, case, kissat, gf2)
        row.update(native_route="cooperative_only_pure_exact_" + row["native_route"],
                   policy=preferred, signal_score=0.0, workers_started=1,
                   winner="r65_exact_gf2", dispatch="gf2_pure")
        return row

    workers = []
    w_standard = None
    temp = tempfile.TemporaryDirectory(prefix="r65c-smart-or-")
    info = {"route": "not_applicable", "probes": 0}
    pre_s = 0.0
    derived = []
    score_value = 0.0
    dispatched = "standard_only"
    answer = "TIMEOUT"
    proof = "none"
    winner = "none"

    try:
        # Low/medium confidence: clean Kissat starts immediately. The XOR lane
        # independently computes proof-carrying clauses while it is working.
        if preferred != "cooperative_only":
            w_standard = launch(kissat, source, "standard")
            workers.append(w_standard)
        if preferred != "standard_only":
            try:
                derived, info = r65.derive_for_source(
                    source, case, min(deadline, t0 + r65.MAX_PREP_S))
            except (r65.ProbeBudget, TimeoutError):
                derived, info = [], {"route": "budget_fallback", "probes": 0}
            pre_s = time.monotonic() - t0
            if pre_s > r65.MAX_PREP_S:
                derived, info = [], {"route": "budget_fallback", "probes": 0}
            score_value = score(info, derived, pre_s)

        # If clean already finished, accept its checked result before spending
        # CPU on a second worker. No performance label is consulted by the gate.
        if w_standard is not None and w_standard["proc"].poll() is not None:
            answer, proof = verified_outcome(w_standard, source, case)
            winner = "standard"
            dispatched = "standard_early_finish"
        else:
            sufficient_signal = (len(derived) >= 1 and score_value >= 0.7
                                 and pre_s < r65.MAX_PREP_S
                                 and time.monotonic() < deadline - 0.20)
            if sufficient_signal:
                augmented = Path(temp.name) / "augmented.cnf"
                r64.augment(source, augmented, case["variables"],
                            case["clauses"], derived)
                workers.append(launch(kissat, augmented, "cooperative"))
                dispatched = "cooperative_only" if not w_standard else "both"
            elif preferred == "cooperative_only":
                w_standard = launch(kissat, source, "standard")
                workers.append(w_standard)
                dispatched = "standard_fallback_after_probe"
            else:
                dispatched = "standard_only_low_signal"

            # OR semantics: the first VALID completion wins. Cancel loser.
            while winner == "none" and time.monotonic() < deadline:
                done = [w for w in workers if w["proc"].poll() is not None]
                if done:
                    # When close in time, deterministic ordering prefers clean.
                    done.sort(key=lambda w: 0 if w["route"] == "standard" else 1)
                    w = done[0]
                    answer, proof = verified_outcome(w, source, case)
                    winner = w["route"]
                    break
                time.sleep(min(TICK_S, max(0.0, deadline - time.monotonic())))
    finally:
        started = len(workers)
        for w in workers:
            terminate(w)
        temp.cleanup()

    elapsed = time.monotonic() - t0
    if elapsed > CAP:
        answer, proof, winner = "TIMEOUT", "none", "none"
        dispatched += "_censored"
    wall = min(CAP, elapsed)
    return dict(answer=answer, wall_s=round(wall, 6),
                par2_s=round(wall if answer != "TIMEOUT" else 2*CAP, 6),
                native_route=dispatched, proof=proof, policy=preferred,
                added_clauses=len(derived), probes=info.get("probes", 0),
                preprocess_s=round(pre_s, 6),
                signal_score=round(score_value, 5),
                workers_started=started, winner=winner,
                dispatch=dispatched)

def selftest():
    import itertools
    r65.selftest()
    def eqclauses(vars_, parity):
        return [tuple(-v if (m >> i) & 1 else v for i, v in enumerate(vars_))
                for m in range(1 << len(vars_))
                if (m.bit_count() & 1) != parity]
    mixed = eqclauses((1, 2, 3), 0) + [(-1, 4), (-4, 2)]
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "small.cnf"
        src.write_text("p cnf 4 " + str(len(mixed)) + "\n" +
                       "".join(" ".join(map(str, c)) + " 0\n" for c in mixed))
        eqs, _ = r64.extract_equations(src, 4, len(mixed), time.monotonic())
        derived, info = r65.propose_clauses(
            4, mixed, eqs, time.monotonic() + 2)
        ck(len(derived) > 0, "missing proof-carrying signal")
        for mask in range(16):
            assignment = {i: bool(mask & (1 << (i-1))) for i in range(1, 5)}
            def satisfies(clauses):
                return all(any(assignment[abs(lit)] == (lit > 0) for lit in c)
                           for c in clauses)
            ck(satisfies(mixed) == satisfies(mixed + derived),
               "unsound shared clause")
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "x.cnf"
            r64.augment(src, p, 4, len(mixed), derived)
            ck(p.read_text().startswith(
               "p cnf 4 " + str(len(mixed) + len(derived)) + "\n"),
               "bad augmented header")
    stub = dict(supported=True, complete_blocks=5, coverage_fraction=0.30,
                partial_support_groups=0, pure_exact_xor=False)
    ck(policy(stub) == "cooperative_only", "strong structural gate")
    stub["coverage_fraction"] = .01
    ck(policy(stub) == "both_candidate", "ambiguous structural gate")
    stub["complete_blocks"] = 0
    ck(policy(stub) == "standard_only", "no exact gate")
    ck(score({"conflicting_probes":1,"root_units":1}, [(1,)], .1) > .7,
       "signal threshold")
    print("R65C_SOUND_OR_POLICY_SELFTEST_PASS", flush=True)

def measure(args):
    sources = Path(args.sources)
    root = Path(args.spec)
    spec = json.loads((root / "manifest.json").read_text())
    ck(spec["protocol"] == r65.PROTO and spec["original_manifest_sha"]
       == digest(sources / "manifest.json"), "source or protocol drift")
    ck(0 <= args.shard < SHARDS, "bad shard")
    if hasattr(os, "sched_setaffinity"):
        # Same one CPU as original R65 benchmark; BOTH shares that CPU.
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    kissat = Path(args.kissat).resolve()
    gf2 = Path(args.gf2).resolve()
    ck(kissat.is_file() and gf2.is_file(), "missing pinned binaries")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    meta = dict(protocol=PROTO, shard=args.shard,
                spec_sha=digest(root / "manifest.json"),
                source_sha=digest(sources / "manifest.json"),
                kissat_sha=digest(kissat), gf2_sha=digest(gf2),
                n_cases=len(spec["cases"][args.shard::SHARDS]),
                shared_affinity_cores=1)
    (out / "metadata.json").write_text(json.dumps(meta, indent=2) + "\n")
    rows = []
    for c in spec["cases"][args.shard::SHARDS]:
        source = (sources / c["filename"]).resolve()
        ck(digest(source) == c["sha256"], "original SHA drift")
        for rep in range(REPS):
            modes = list(MODES)
            seed = int(hashlib.sha256(
                ("r65c/" + c["sha256"] + "/" + str(rep)).encode()
            ).hexdigest(), 16)
            random.Random(seed).shuffle(modes)
            for mode in modes:
                if mode == "clean_kissat":
                    row = r63.one(source, c, kissat, gf2, mode)
                elif mode == "r65_xor_cnf_feedback":
                    row = r65.r65_one(source, c, kissat, gf2)
                else:
                    row = smart_one(source, c, kissat, gf2)
                item = dict(gbd=c["gbd"], sha=c["sha256"], group=c["group"],
                            rep=rep, mode=mode, **row)
                rows.append(item)
                (out / "rows.json").write_text(json.dumps(rows, indent=2)+"\n")
                print("R65C_TRIAL", c["gbd"], c["group"], rep, mode,
                      row["answer"], row["wall_s"], "PAR2", row["par2_s"],
                      row.get("native_route"), row.get("winner", "-"),
                      flush=True)
    print("R65C_SHARD_PASS", args.shard, len(rows), flush=True)

def audit(args):
    root = Path(args.spec)
    spec = json.loads((root / "manifest.json").read_text())
    ck(spec["protocol"] == r65.PROTO and len(spec["cases"]) == 18,
       "frozen R65 cohort changed")
    pins = set()
    allrows = []
    for i in range(SHARDS):
        folder = Path(args.combined) / ("r65c-shard-" + str(i)) / "results"
        meta = json.loads((folder / "metadata.json").read_text())
        ck(meta["protocol"] == PROTO and meta["shard"] == i
           and meta["spec_sha"] == digest(root / "manifest.json")
           and meta["shared_affinity_cores"] == 1, "shard pin drift")
        pins.add((meta["kissat_sha"], meta["gf2_sha"], meta["source_sha"]))
        block = json.loads((folder / "rows.json").read_text())
        ck(len(block) == meta["n_cases"] * REPS * len(MODES), "missing trials")
        allrows += block
    ck(len(pins) == 1 and len(allrows) == len(spec["cases"]) * REPS * len(MODES),
       "incomplete paired evidence or binary drift")
    grouped = {}
    per_formula = {}
    for c in spec["cases"]:
        matched = [r for r in allrows if r["gbd"] == c["gbd"]]
        ck(len(matched) == REPS * len(MODES)
           and all(r["sha"] == c["sha256"] for r in matched), "sha/rep drift")
        for rep in range(REPS):
            ck({r["mode"] for r in matched if r["rep"] == rep} == set(MODES),
               "missing paired mode")
        per_formula[c["gbd"]] = dict(
            group=c["group"],
            par2={m:round(sum(r["par2_s"] for r in matched if r["mode"]==m), 6)
                  for m in MODES},
            routes=dict(collections.Counter(
                r["native_route"] for r in matched
                if r["mode"]=="r65c_smart_or")))
    for group in ["ALL"] + list(r64.GROUPS):
        selected = [r for r in allrows if group=="ALL" or r["group"]==group]
        grouped[group] = {
            m: dict(trials=sum(r["mode"]==m for r in selected),
                    solved=sum(r["mode"]==m and r["answer"]!="TIMEOUT"
                               for r in selected),
                    par2_s=round(sum(r["par2_s"] for r in selected
                                     if r["mode"]==m), 6)) for m in MODES}
        baseline=grouped[group][MODES[0]]["par2_s"]
        grouped[group]["smart_gain_pct"] = (
            round(100*(1-grouped[group][MODES[2]]["par2_s"]/baseline),4)
            if baseline else None)
    routes = collections.Counter(r.get("dispatch") for r in allrows
                                  if r["mode"] == MODES[2])
    winners = collections.Counter(r.get("winner") for r in allrows
                                   if r["mode"] == MODES[2])
    res = dict(protocol=PROTO, status="PASS", sources=len(spec["cases"]),
               trials=len(allrows), one_cpu_shared=True,
               groups=grouped, per_formula=per_formula,
               dispatch=dict(routes), winners=dict(winners),
               limitations=["Pre-seen R65/R64/R63 SHA-frozen formulas, not new blind holdout",
                 "Stock Kissat: no live learnt-clause communication; verified CNF implication sharing at launch only",
                 "Both workers share one CPU; wall-clock and PAR2 include preprocessing and verification",
                 "SAT witness checked against original, UNSAT checked against official label only",
                 "Heuristic OR routing is not itself a proof, and performance may regress"])
    Path(args.json).write_text(json.dumps(res, indent=2)+"\n")
    lines = [
        "# DRNAS R65C — smart OR, cooperative / standard / both",
        "",
        "**Development replay on previously seen real SAT2026 formulas, not a blind holdout.**",
        "One CPU for all modes, 40s end-to-end wall cap; PAR2 timeout=80s.",
        "",
        "| Stratum | Kissat PAR2 | R65 PAR2 | Smart OR PAR2 | Smart gain |",
        "|---|---:|---:|---:|---:|"
    ]
    for g, items in grouped.items():
        v=[items[m]["par2_s"] for m in MODES]
        lines.append(f"| {g} | {v[0]:.3f}s | {v[1]:.3f}s | {v[2]:.3f}s | "
                     f"{items['smart_gain_pct']:+.3f}% |")
    lines += ["", "Dispatch: "+json.dumps(dict(routes),sort_keys=True),
              "Winners: "+json.dumps(dict(winners),sort_keys=True),
              "", "## Per formula",
              "| SHA/GBD prefix | Group | Kissat | R65 | Smart OR | Routes |",
              "|---|---|---:|---:|---:|---|"]
    for key,item in per_formula.items():
        vals=[item["par2"][m] for m in MODES]
        lines.append(f"| {key[:12]} | {item['group']} | {vals[0]:.3f} | "
                     f"{vals[1]:.3f} | {vals[2]:.3f} | "
                     f"{json.dumps(item['routes'])} |")
    lines += ["", "## Limitations"] + ["- "+v for v in res["limitations"]]
    Path(args.md).write_text("\n".join(lines)+"\n")
    print("R65C_FINAL_AUDIT_PASS", json.dumps(
        {"trials":len(allrows),"groups":grouped,
         "dispatch":dict(routes),"winners":dict(winners)},sort_keys=True),
         flush=True)

def main():
    p=argparse.ArgumentParser()
    sp=p.add_subparsers(dest="cmd",required=True)
    sp.add_parser("selftest")
    m=sp.add_parser("measure")
    for name in ("sources","spec","kissat","gf2","out"):
        m.add_argument("--"+name,required=True)
    m.add_argument("--shard",required=True,type=int)
    a=sp.add_parser("audit")
    for name in ("spec","combined","json","md"):
        a.add_argument("--"+name,required=True)
    args=p.parse_args()
    if args.cmd=="selftest":
        selftest()
    elif args.cmd=="measure":
        measure(args)
    else:
        audit(args)

if __name__=="__main__":
    main()
