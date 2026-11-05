#!/usr/bin/env python3
"""DRNAS R47 research: certified short cross-clause implications without requiring XOR.

Works with frozen original SATComp2026 CNFs, keeps the original Kissat solver,
counts the entire preprocessing time, never restarts or alters search policy.
A new clause has a two-parent resolution witness from original clauses and
an independent exhaustive 2^<=5-variable entailment check.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import shutil
import statistics
import subprocess
import tempfile
import time

import r46_local_certified_links as r46

PROTO = "DRNAS-R47-PARTIAL-LOCAL-CNF-20261103-v1"
MODES = ("clean", "r46_active", "r47_shadow", "r47_active")
CAP, REPS, SHARDS = 30.0, 2, 4
MAX_FILE_BYTES = 65 * 1024 * 1024
MAX_SAMPLE = 60000
MAX_OCC_PER_SIGN = 24
MAX_PAIR_CHECKS = 16000
MAX_IMPLICATES = 40

def check(ok, message):
    if not ok:
        raise RuntimeError("R47_AUDIT_FAIL " + str(message))

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def sample_original(path):
    # This never changes the source CNF. A logically valid consequence of
    # ANY subset of original clauses is also a consequence of the whole CNF.
    if Path(path).stat().st_size > MAX_FILE_BYTES:
        return None, [], dict(reason="source_size_guard", sampled=0)
    selected = []
    n, m, observed = None, None, 0
    current, wide = [], False
    with open(path, encoding="ascii", errors="strict") as stream:
        for raw in stream:
            line = raw.strip()
            if not line or line.startswith(("c", "%")):
                continue
            if line.startswith("p "):
                fields = line.split()
                check(n is None and len(fields) == 4 and fields[:2] == ["p", "cnf"],
                      "bad original CNF header")
                n, m = int(fields[2]), int(fields[3])
                continue
            check(n is not None, "missing CNF header")
            for word in line.split():
                lit = int(word)
                if lit:
                    check(abs(lit) <= n and lit != 0, "invalid original literal")
                    if len(current) < 4:
                        current.append(lit)
                    else:
                        wide = True
                else:
                    observed += 1
                    if not wide and 1 <= len(current) <= 4 and len(selected) < MAX_SAMPLE:
                        if len({abs(x) for x in current}) == len(current):
                            selected.append(tuple(current))
                    current, wide = [], False
    check(n is not None and not current and not wide and observed == m,
          "original CNF truncated or wrong clause count")
    return n, selected, dict(reason="sampled", sampled=len(selected),
                             original_clauses=m, original_vars=n)

def derive_partial(original):
    n, clauses, trace = sample_original(original)
    trace.update(motifs=0, inspected_pairs=0, derived=0, units=0,
                 binaries=0, ternaries=0, motif_related=0)
    if n is None or not clauses:
        return [], [], trace
    occurrence = collections.defaultdict(list)
    signs = collections.defaultdict(set)
    existing = set()
    for i, c in enumerate(clauses):
        if len(c) <= 3:
            existing.add(frozenset(c))
        for lit in c:
            if len(occurrence[lit]) < MAX_OCC_PER_SIGN:
                occurrence[lit].append(i)
        if len(c) in (3, 4):
            support = tuple(sorted(map(abs, c)))
            neg = {abs(x) for x in c if x < 0}
            mask = sum(1 << j for j, v in enumerate(support) if v in neg)
            signs[support].add(mask)

    # A missing one-of-four parity pattern is NOT promoted to an XOR equation.
    # It merely prioritizes short, independently provable resolution chains.
    focus = set()
    for support, masks in signs.items():
        if len(support) == 3 and len(masks) >= 3:
            for parity in (0, 1):
                required = {i for i in range(8) if i.bit_count() % 2 == parity}
                if len(masks & required) == 3:
                    focus.update(support)
                    trace["motifs"] += 1

    variables = sorted({abs(x) for x in occurrence},
                       key=lambda v: (v not in focus,
                                      -min(len(occurrence.get(v, [])),
                                           len(occurrence.get(-v, []))),
                                      v))
    additions, proofs, known = [], [], set()
    pair_count = 0
    for pivot in variables:
        positive, negative = occurrence.get(pivot, ()), occurrence.get(-pivot, ())
        if not positive or not negative:
            continue
        for ai in positive:
            for bi in negative:
                pair_count += 1
                if pair_count > MAX_PAIR_CHECKS or len(additions) >= MAX_IMPLICATES:
                    break
                a, b = clauses[ai], clauses[bi]
                full = set(a) | set(b)
                support = tuple(sorted({abs(x) for x in full}))
                if len(support) > 5:
                    continue
                consequent = (set(a) - {pivot}) | (set(b) - {-pivot})
                if len(consequent) not in (1, 2, 3):
                    continue
                if any(-lit in consequent for lit in consequent):
                    continue
                result = tuple(sorted(consequent, key=lambda x: (abs(x), x)))
                key = frozenset(result)
                if key in existing or key in known:
                    continue
                parents = [a, b]
                check(r46.certifies(parents, result, support),
                      "resolution certificate fails exhaustive truth-table")
                known.add(key)
                additions.append(result)
                proofs.append(dict(clause=list(result), parent_ids=[ai, bi],
                                   pivot=pivot, support=list(support),
                                   source="partial_motif" if pivot in focus else "generic"))
                if pivot in focus:
                    trace["motif_related"] += 1
            if pair_count > MAX_PAIR_CHECKS or len(additions) >= MAX_IMPLICATES:
                break
        if pair_count > MAX_PAIR_CHECKS or len(additions) >= MAX_IMPLICATES:
            break
    trace["inspected_pairs"] = min(pair_count, MAX_PAIR_CHECKS)
    trace["derived"] = len(additions)
    trace["units"] = sum(len(c) == 1 for c in additions)
    trace["binaries"] = sum(len(c) == 2 for c in additions)
    trace["ternaries"] = sum(len(c) == 3 for c in additions)
    trace["reason"] = "certified_local_resolution" if additions else "no_new_local_consequence"
    # Independent audit using original source clause snippets, not claims
    # about a complete XOR structure or any modification to Kissat.
    for clause, certificate in zip(additions, proofs):
        parents = [clauses[j] for j in certificate["parent_ids"]]
        check(r46.certifies(parents, clause, certificate["support"]),
              "independent local certificate failed")
    return additions, proofs, trace

def augment_original(source, target, new):
    # Preserve ALL original clauses, including long or unsampled ones.
    old_header_found = False
    with open(source, "rt", encoding="ascii") as reader, \
         open(target, "wt", encoding="ascii") as writer:
        for line in reader:
            if not old_header_found and line.startswith("p cnf "):
                fields = line.split()
                check(len(fields) == 4, "invalid source header")
                writer.write(f"p cnf {fields[2]} {int(fields[3]) + len(new)}\n")
                old_header_found = True
            else:
                writer.write(line)
        check(old_header_found, "source without p cnf")
        writer.write("\n")
        for clause in new:
            writer.write(" ".join(map(str, clause)) + " 0\n")

def run_one(source, clean, mode):
    if mode in ("clean", "r46_active"):
        prior_mode = "clean" if mode == "clean" else "active"
        ans = r46.run_one(source, clean, prior_mode)
        return ans
    start = time.monotonic()
    new, proof, trace = derive_partial(source)
    check(len(proof) == len(new), "proof count")
    with tempfile.TemporaryDirectory(prefix="drnas_r47_") as temp:
        candidate = source
        if mode == "r47_active" and new:
            candidate = Path(temp) / "original_plus_proven.cnf"
            augment_original(source, candidate, new)
        remaining = CAP - (time.monotonic() - start)
        if remaining <= 0:
            return dict(answer="TIMEOUT", time_s=round(time.monotonic()-start, 6),
                        par2_s=CAP*2, trace=trace)
        try:
            process = subprocess.run([str(clean), str(candidate)],
                                     capture_output=True, text=True,
                                     errors="replace", timeout=remaining)
        except subprocess.TimeoutExpired:
            return dict(answer="TIMEOUT", time_s=round(time.monotonic()-start, 6),
                        par2_s=CAP*2, trace=trace)
        duration = round(time.monotonic()-start, 6)
        check(process.returncode in (10, 20),
              "Kissat failed code="+str(process.returncode)+" "+process.stderr[-300:])
        answer = "SAT" if process.returncode == 10 else "UNSAT"
        if answer == "SAT":
            r46.r46.verify_sat_witness(source, process.stdout) if hasattr(r46, "r46") else \
                __import__("r32p_real_satcomp26_benchmark").verify_sat_witness(source, process.stdout)
        return dict(answer=answer, time_s=duration, par2_s=duration, trace=trace)

def selftest():
    # A simple implication learned via resolution, without any XOR at all.
    a, b = (1, 2), (-1, 3)
    require_support = (1, 2, 3)
    check(r46.certifies([a, b], (2, 3), require_support),
          "two-parent resolution is not sound")
    with tempfile.TemporaryDirectory() as td:
        p = Path(td)/"test.cnf"
        p.write_text("c R47 test\np cnf 3 2\n1 2 0\n-1 3 0\n")
        new, proof, tr = derive_partial(p)
        check((2, 3) in new and tr["derived"] >= 1,
              "partial non-XOR derivation missing")
        tgt = Path(td)/"aug.cnf"
        augment_original(p, tgt, new)
        n, clauses, _ = r46.read_cnf(tgt)
        check(n == 3 and len(clauses) == 2+len(new),
              "preservation of full source CNF failed")
        for t in itertools.product((False, True), repeat=3):
            truth = {i+1: v for i, v in enumerate(t)}
            lhs = r46.clause_true(a, truth) and r46.clause_true(b, truth)
            rhs = all(r46.clause_true(c, truth) for c in clauses)
            check(lhs == rhs, "source and strengthened CNF not equivalent")
        print("R47_NON_XOR_CERTIFIED_SELFTEST_PASS", tr, flush=True)

def measure(args):
    frozen = Path(args.frozen)
    manifest = json.loads((frozen/"manifest.json").read_text())
    check(manifest["protocol"].startswith("DRNAS-R32P-REAL-SATCOMP2026"),
          "wrong frozen official source")
    check(len(manifest["cases"]) == 8 and 0 <= args.shard < SHARDS,
          "unexpected changed SATComp original cohort")
    clean = Path(args.clean).resolve()
    check(clean.is_file(), "pinned Kissat absent")
    if hasattr(os, "sched_getaffinity"):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out/"meta.json").write_text(json.dumps(dict(protocol=PROTO, shard=args.shard,
         manifest_sha=sha(frozen/"manifest.json"), binary_sha=sha(clean),
         modes=MODES, cap=CAP, reps=REPS), indent=2)+"\n")
    rows = []
    for case in manifest["cases"][args.shard::SHARDS]:
        source = frozen/case["name"]
        check(sha(source) == case["sha256"], "original SHA fingerprint changed")
        for rep in range(REPS):
            modes = list(MODES)
            random.Random(int(hashlib.sha256((case["sha256"]+str(rep)+PROTO).encode()).hexdigest(), 16)).shuffle(modes)
            for mode in modes:
                answer = run_one(source, clean, mode)
                rows.append(dict(source_sha=case["sha256"], gbd=case["gbd"],
                                 repeat=rep, mode=mode, **answer))
                print("R47_TRIAL", case["gbd"], rep, mode, answer, flush=True)
            (out/"rows.json").write_text(json.dumps(rows)+"\n")
    print("R47_SHARD_PASS", args.shard, len(rows), flush=True)

def aggregate(args):
    frozen = Path(args.frozen)
    manifest = json.loads((frozen/"manifest.json").read_text())
    rows, binary_shas = [], set()
    for shard in range(SHARDS):
        root = Path(args.combined)/f"r47-shard-{shard}"/"results"
        meta = json.loads((root/"meta.json").read_text())
        check(meta["protocol"] == PROTO and meta["shard"] == shard and
              meta["manifest_sha"] == sha(frozen/"manifest.json"),
              "shard meta, source or protocol mismatch")
        binary_shas.add(meta["binary_sha"])
        part = json.loads((root/"rows.json").read_text())
        check(len(part) == len(manifest["cases"][shard::SHARDS])*REPS*len(MODES),
              "incomplete pair counts")
        rows.extend(part)
    check(len(binary_shas) == 1 and len(rows) == 8*REPS*len(MODES),
          "incomplete or inconsistent experiment")
    summary = {}
    for mode in MODES:
        part = [x for x in rows if x["mode"] == mode]
        summary[mode] = dict(par2_s=round(sum(x["par2_s"] for x in part), 6),
                             solved=sum(x["answer"] != "TIMEOUT" for x in part),
                             certified_clauses=sum(x["trace"].get("derived",0) for x in part),
                             nonxor_research_motifs=sum(x["trace"].get("motifs",0) for x in part))
    for case in manifest["cases"]:
        for rep in range(REPS):
            group = [x for x in rows if x["source_sha"] == case["sha256"]
                     and x["repeat"] == rep]
            check({x["mode"] for x in group} == set(MODES), "missing mode")
            answers = {x["answer"] for x in group} - {"TIMEOUT"}
            check(len(answers) <= 1, "SAT/UNSAT disagreement")
    result = dict(protocol=PROTO, cases=len(manifest["cases"]), attempts=len(rows),
                  binary_sha=next(iter(binary_shas)), summary=summary, rows=rows,
                  limitations=["Exploratory paired comparison, same previously tested 8-source cohort, not a fresh holdout",
                   "Only source-subset certified short resolvents; no claim of XOR derivation without complete truth table",
                   "Results use original Kissat binary and original-CNF SAT witness validation",
                   "UNSAT not separately LRAT checked; 30s total cap includes analysis",
                   "Sampling and source bounds may miss beneficial relations",
                   "PAR2 penalties can hide sub-timeout improvements"])
    Path(args.output).write_text(json.dumps(result, indent=2)+"\n")
    lines = ["# R47 certified partial relation transfer — 8 real SATComp26 CNFs",
             "", "Same source SHA, same clean Kissat, 30s total wall cap, 2 repeats, no restart policy changes.",
             "R46 versus R47 causal within-host comparison. All derivations are two-parent resolution",
             "implications with an independent local exhaustive truth-table certificate.",
             "", "| Mode | Solved | Total PAR2, sec | Certified derived clauses (across repeats) |",
             "|---|---:|---:|---:|"]
    for mode in MODES:
        x = summary[mode]
        lines.append(f'| {mode} | {x["solved"]}/16 | {x["par2_s"]:.4f} | {x["certified_clauses"]} |')
    lines += ["", "## Per-original paired times (PAR2=60s for timeout)",
              "| GBD source | Repeat | Clean | R46 | R47 shadow | R47 active | New clauses |",
              "|---|---:|---:|---:|---:|---:|---:|"]
    for case in manifest["cases"]:
        for rep in range(REPS):
            d = {x["mode"]: x for x in rows
                 if x["source_sha"] == case["sha256"] and x["repeat"] == rep}
            lines.append(f'| {case["gbd"]} | {rep} | {d["clean"]["par2_s"]:.4f} | '
                         f'{d["r46_active"]["par2_s"]:.4f} | '
                         f'{d["r47_shadow"]["par2_s"]:.4f} | '
                         f'{d["r47_active"]["par2_s"]:.4f} | '
                         f'{d["r47_active"]["trace"]["derived"]} |')
    lines += ["", "## Interpretation",
              "No claim of world record. Distinguish SAT solved speed from PAR2 totals,",
              "and check active-minus-shadow to isolate proof injection from analysis overhead.",
              "Formulas were seen before by R46; this is exploratory, not blind confirmation."]
    Path(args.report).write_text("\n".join(lines)+"\n")
    print("R47_AUDIT_PASS", len(rows), json.dumps(summary, sort_keys=True), flush=True)

def main():
    parser = argparse.ArgumentParser()
    subs = parser.add_subparsers(dest="cmd", required=True)
    subs.add_parser("selftest")
    m = subs.add_parser("measure")
    for key in ("frozen", "clean", "out"):
        m.add_argument("--"+key, required=True)
    m.add_argument("--shard", type=int, required=True)
    a = subs.add_parser("aggregate")
    for key in ("frozen", "combined", "output", "report"):
        a.add_argument("--"+key, required=True)
    args = parser.parse_args()
    {"selftest": lambda: selftest(),
     "measure": lambda: measure(args),
     "aggregate": lambda: aggregate(args)}[args.cmd]()

if __name__ == "__main__":
    main()
