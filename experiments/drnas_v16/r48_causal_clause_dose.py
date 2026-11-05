#!/usr/bin/env python3
"""R48: causal ablation of R47 sound short resolvents on two official 2026 CNFs.

This is an EXPLORATORY known-case diagnosis, NOT an external blind holdout.
No trained selector and no claims about SOTA. Separate clean, analysis-only,
rewrite-zero, graded prefix/suffix and order-only controls. Both the proof
extraction and source rewrite count toward the hard wall time per trial.
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
import re
import statistics
import subprocess
import tempfile
import time

import r47_partial_links as r47
import r46_local_certified_links as r46
import r32p_real_satcomp26_benchmark as verify

PROTOCOL = "DRNAS-R48-CAUSAL-DOSE-20261103-v1"
TARGETS = {
    "benefit": "ba14be209c2fc064726025f017cef17a",
    "regress": "2b7e863462991fd008f9898eca63ebf4",
}
MODES = ("clean", "shadow", "rewrite0", "head4", "head8", "head16",
         "head32", "head40", "tail4", "tail16", "reverse40")
CAP = 30.0
REPEATS = 2


def check(v, message):
    if not v:
        raise RuntimeError("R48_INTEGRITY_FAIL " + str(message))


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canon_clauses(clauses):
    return hashlib.sha256(
        json.dumps([list(c) for c in clauses],
                   separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def source_case(root, name):
    manifest = json.loads((root / "manifest.json").read_text())
    check(manifest["protocol"].startswith("DRNAS-R32P-REAL-SATCOMP2026"),
          "unknown official source protocol")
    check(len(manifest["cases"]) == 8, "changed frozen original cohort")
    ids = [x for x in manifest["cases"] if x["gbd"] == TARGETS[name]]
    check(len(ids) == 1, "wrong or missing precommitted target")
    case = ids[0]
    path = root / case["name"]
    check(sha(path) == case["sha256"], "original CNF fingerprint changed")
    return case, path


def select(mode, clauses):
    check(len(clauses) == 40, "R47 frozen clause count no longer 40")
    if mode in ("clean", "shadow", "rewrite0"):
        return []
    if mode.startswith("head"):
        return clauses[:int(mode[4:])]
    if mode.startswith("tail"):
        return clauses[-int(mode[4:]):]
    if mode == "reverse40":
        return list(reversed(clauses))
    raise ValueError("unknown mode " + mode)


def safe_rewrite(source, output, added):
    # R47 previously placed new clauses AFTER a possible percent end marker.
    # We do NOT assume Kissat parses any text after '%'; add before it.
    check(len(added) <= 40, "dose cap")
    before = 0
    reached_end = False
    emitted = False
    def inject(stream):
        for c in added:
            stream.write(" ".join(str(x) for x in c) + " 0\n")
    with open(source, encoding="ascii", errors="strict") as reader, \
         open(output, "w", encoding="ascii") as writer:
        for line in reader:
            stripped = line.lstrip()
            if stripped.startswith("p "):
                fields = stripped.split()
                check(len(fields) == 4 and fields[1] == "cnf" and before == 0,
                      "source DIMACS header mismatch")
                before += 1
                writer.write(f"p cnf {fields[2]} {int(fields[3])+len(added)}\n")
            elif stripped.startswith("%"):
                if not emitted:
                    check(before == 1, "no CNF header")
                    inject(writer)
                    emitted = True
                reached_end = True
                writer.write(line)
            else:
                # Original clause data and comments preserved byte-for-byte.
                writer.write(line)
        check(before == 1, "one source header required")
        if not emitted:
            if not reached_end:
                writer.write("\n")
            inject(writer)
    # The file, not just the mathematical certificate, must contain the
    # announced additional clauses BEFORE any terminating % marker.
    expected = len(added)
    header_seen, count, terminator = False, 0, False
    queue = []
    with open(output, encoding="ascii", errors="strict") as stream:
        for line in stream:
            line = line.strip()
            if not line or line.startswith("c"):
                continue
            if line.startswith("%"):
                terminator = True
                continue
            check(not terminator, "data after percent terminator")
            if line.startswith("p "):
                fields = line.split()
                check(not header_seen and len(fields) == 4 and fields[1] == "cnf",
                      "rewritten CNF invalid header")
                target_count = int(fields[3])
                header_seen = True
                continue
            for token in line.split():
                lit = int(token)
                if lit:
                    queue.append(lit)
                else:
                    count += 1
                    queue.clear()
    check(header_seen and not queue and count == target_count,
          "added clauses not visible to DIMACS parser")
    return dict(actual_clauses=count, added=expected, percent_terminator=terminator)


def certify(original, additions, proofs):
    check(len(additions) == 40 and len(proofs) == 40,
          "changed R47 ordered list")
    n, original_snippets, _ = r47.sample_original(original)
    check(n is not None, "source outside R47 proof guard")
    for entry, proof in zip(additions, proofs):
        check(tuple(proof["clause"]) == tuple(entry), "proof mismatched result")
        parents = [original_snippets[i] for i in proof["parent_ids"]]
        check(r46.certifies(parents, entry, proof["support"]),
              "derived clause not independently entailed")
    return canon_clauses(additions)


def selftest():
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        cnf = root / "source.cnf"
        cnf.write_text("c R48 percent handling\np cnf 3 2\n1 2 0\n-1 3 0\n%\n")
        out = root / "rewritten.cnf"
        summary = safe_rewrite(cnf, out, [(2, 3)])
        check(summary["actual_clauses"] == 3, "physical clause missing")
        raw = out.read_text()
        check(raw.index("2 3 0") < raw.index("%"), "clause appended after terminator")
        for truth in itertools.product((False, True), repeat=3):
            assign = {i + 1: val for i, val in enumerate(truth)}
            original_ok = r46.clause_true((1, 2), assign) and \
                          r46.clause_true((-1, 3), assign)
            added_ok = original_ok and r46.clause_true((2, 3), assign)
            check(original_ok == added_ok, "replacement changed satisfiability")
        z = root / "zero.cnf"
        empty = safe_rewrite(cnf, z, [])
        check(empty["actual_clauses"] == 2, "zero-clauses control not valid")
    print("R48_SAFE_REWRITE_AND_PROOF_SELFTEST_PASS", flush=True)


def freeze(args):
    root = Path(args.frozen)
    record = dict(protocol=PROTOCOL, target_prefixes=TARGETS, doses=MODES,
                  reps=REPEATS, cap_s=CAP, cases={}, limitations=[
                    "Known outcomes from R47; exploratory causal ablation, never blind",
                    "No dynamic route selection or hindsight optimization",
                    "Reuses exact original 2026 source hashes and pinned clean Kissat",
                    "R47 method is ordinary binary resolution, not demonstrated partial XOR",
                    "Repeated same-hardware wall runs can vary due to CPU noise",
                    "UNSAT not LRAT-certified; SAT witnessed against original source"])
    for name in TARGETS:
        case, path = source_case(root, name)
        additions, proofs, trace = r47.derive_partial(path)
        certificate_hash = certify(path, additions, proofs)
        check(len(additions) == 40 and trace["derived"] == 40,
              "not same 40 clauses from R47")
        record["cases"][name] = dict(source_sha=case["sha256"],
           gbd=case["gbd"], n=case["vars"], m=case["clauses"],
           derived_sha=certificate_hash, clauses=[list(x) for x in additions],
           proofs=proofs, trace=trace)
        print("R48_FROZEN_SOURCE_AND_40_PROOFS_PASS", name,
              case["gbd"], certificate_hash, trace, flush=True)
    Path(args.output).write_text(json.dumps(record, indent=2)+"\n")


def measure(args):
    check(args.target in TARGETS and 0 <= args.rep < REPEATS,
          "non-precommitted arm")
    original_root = Path(args.frozen)
    frozen = json.loads(Path(args.design).read_text())
    check(frozen["protocol"] == PROTOCOL and frozen["doses"] == list(MODES),
          "design protocol drift")
    case, original = source_case(original_root, args.target)
    frozen_arm = frozen["cases"][args.target]
    check(case["sha256"] == frozen_arm["source_sha"], "target SHA mismatch")
    clean = Path(args.clean).resolve()
    check(clean.is_file(), "pinned clean Kissat missing")
    if hasattr(os, "sched_getaffinity"):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    dest = Path(args.out)
    dest.mkdir(parents=True, exist_ok=True)
    meta = dict(protocol=PROTOCOL, target=args.target, rep=args.rep,
        frozen_design_sha=sha(args.design), source_sha=case["sha256"],
        binary_sha=sha(clean), modes=MODES, wall_cap_s=CAP)
    (dest/"meta.json").write_text(json.dumps(meta, indent=2)+"\n")
    modes = list(MODES)
    random.Random(int(hashlib.sha256((case["sha256"]+str(args.rep)+PROTOCOL)
                 .encode()).hexdigest(),16)).shuffle(modes)
    rows = []
    for mode in modes:
        start = time.monotonic()
        prepared = original
        trace = dict(prep_s=0.0, derived=0, added=0, proof_sha=None, rewrite=None)
        with tempfile.TemporaryDirectory(prefix="drnas_r48_") as scratch:
            if mode != "clean":
                new, proofs, metrics = r47.derive_partial(original)
                proofhash = certify(original, new, proofs)
                check(proofhash == frozen_arm["derived_sha"],
                      "R47 proof list changed after freezing")
                dose = select(mode, new)
                trace.update(derived=len(new), added=len(dose),
                             proof_sha=proofhash, metrics=metrics)
                if mode not in ("shadow",):
                    prepared = Path(scratch) / "source_plus_entailed.cnf"
                    trace["rewrite"] = safe_rewrite(original, prepared, dose)
            trace["prep_s"] = round(time.monotonic() - start, 6)
            remain = CAP - (time.monotonic() - start)
            if remain <= 0:
                result = dict(answer="TIMEOUT", time_s=round(time.monotonic()-start,6),
                              par2_s=2*CAP, trace=trace)
            else:
                try:
                    p = subprocess.run([str(clean), str(prepared)],
                          capture_output=True,text=True,errors="replace",
                          timeout=remain)
                    check(p.returncode in (10, 20),
                          "pinned Kissat exit "+str(p.returncode)+" "+p.stderr[-500:])
                    answer = "SAT" if p.returncode == 10 else "UNSAT"
                    if answer == "SAT":
                        verify.verify_sat_witness(original, p.stdout)
                    result = dict(answer=answer, time_s=round(time.monotonic()-start, 6),
                                  par2_s=round(time.monotonic()-start, 6), trace=trace)
                except subprocess.TimeoutExpired:
                    result = dict(answer="TIMEOUT", time_s=round(time.monotonic()-start,6),
                                  par2_s=2*CAP, trace=trace)
        rows.append(dict(target=args.target, rep=args.rep, mode=mode,
                         gbd=case["gbd"], **result))
        print("R48_TRIAL", args.target, args.rep, mode, result, flush=True)
        (dest/"rows.json").write_text(json.dumps(rows, indent=2)+"\n")
    print("R48_ARM_COMPLETE", args.target, args.rep, len(rows), flush=True)


def aggregate(args):
    frozen = json.loads(Path(args.design).read_text())
    check(frozen["protocol"] == PROTOCOL, "bad design")
    rows, binaries = [], set()
    for target in TARGETS:
        for rep in range(REPEATS):
            arm = Path(args.combined)/f"r48-{target}-{rep}"/"results"
            meta = json.loads((arm/"meta.json").read_text())
            check(meta["protocol"] == PROTOCOL and meta["target"] == target
                  and meta["rep"] == rep
                  and meta["frozen_design_sha"] == sha(args.design),
                  "wrong paired arm")
            binaries.add(meta["binary_sha"])
            group = json.loads((arm/"rows.json").read_text())
            check(len(group) == len(MODES) and {r["mode"] for r in group} == set(MODES),
                  "incomplete dose trial")
            check(all(r["target"]==target and r["rep"]==rep for r in group),
                  "crossed arm results")
            results = {r["answer"] for r in group} - {"TIMEOUT"}
            check(len(results)<=1, "contradictory solver SAT status")
            rows.extend(group)
    check(len(binaries) == 1, "different solver binaries")
    # CRITICAL: never infer average speed from PAR2 without solved counts.
    summary = {}
    for target in TARGETS:
        per = [r for r in rows if r["target"] == target]
        summary[target] = {}
        for mode in MODES:
            x = [r for r in per if r["mode"] == mode]
            summary[target][mode] = dict(
                solved=sum(r["answer"] != "TIMEOUT" for r in x),
                mean_par2_s=round(statistics.mean(r["par2_s"] for r in x), 6),
                raw_times_s=[r["time_s"] for r in sorted(x,key=lambda a:a["rep"])],
                added=x[0]["trace"]["added"])
    data = dict(protocol=PROTOCOL, frozen_design=frozen, binary_sha=next(iter(binaries)),
                trials=len(rows), summary=summary, rows=rows)
    Path(args.output).write_text(json.dumps(data, indent=2)+"\n")
    lines=["# DRNAS R48 — causal dose response on two known 2026 SAT CNFs", "",
      "These two sources were chosen BECAUSE R47 had a win and a regression.",
      "This is an in-sample diagnostic, never a generalization or blind holdout.",
      "30s total wall cap; 2 repetitions; unchanged pinned Kissat.",
      "Each new clause carries an original-clause resolution certificate.",
      "Rewrite-zero and shadow control separate CNF I/O and analysis cost.",
      "Percent-terminated CNFs insert all added clauses BEFORE the terminator.",
      "", "| Target | Dose | Solved | Mean PAR-2 s | Repeat 1 wall s | Repeat 2 wall s | New clauses |",
      "|---|---|---:|---:|---:|---:|---:|"]
    for target in TARGETS:
        for mode in MODES:
            x=summary[target][mode]
            times=x["raw_times_s"]
            lines.append(f'| {target} | {mode} | {x["solved"]}/2 | '
                         f'{x["mean_par2_s"]:.4f} | {times[0]:.4f} | '
                         f'{times[1]:.4f} | {x["added"]} |')
    lines += ["", "Do NOT train a selector from the same two cases and call it validated.",
              "Next step: locate high-impact clauses with replicated independent seeds,",
              "freeze a structural gate, then use completely SHA-disjoint CNFs."]
    Path(args.report).write_text("\n".join(lines)+"\n")
    print("R48_AUDIT_PASS", len(rows), json.dumps(summary,sort_keys=True), flush=True)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("selftest")
    f = sub.add_parser("freeze")
    f.add_argument("--frozen", required=True)
    f.add_argument("--output", required=True)
    m = sub.add_parser("measure")
    for field in ("frozen", "design", "clean", "target", "out"):
        m.add_argument("--"+field, required=True)
    m.add_argument("--rep", type=int, required=True)
    a = sub.add_parser("aggregate")
    for field in ("design", "combined", "output", "report"):
        a.add_argument("--"+field, required=True)
    args = parser.parse_args()
    {"selftest":lambda:selftest(),
     "freeze":lambda:freeze(args),
     "measure":lambda:measure(args),
     "aggregate":lambda:aggregate(args)}[args.cmd]()


if __name__ == "__main__":
    main()
