#!/usr/bin/env python3
"""DRNAS R46: bounded, certificate-checked local CNF/XOR implications.

Research-only DIMACS preprocessor. Every added clause is entailed by a
small explicitly listed subset of ORIGINAL clauses, checked exhaustively.
The original CDCL solver, restarts and settings remain untouched.
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
import statistics
import subprocess
import tempfile
import time

PROTO = "DRNAS-R46-LOCAL-CERTIFIED-20261103-v1"
CAP = 30.0
REPS = 2
SHARDS = 4
MODES = ("clean", "shadow", "active")
MAX_BYTES = 24 * 1024 * 1024
MAX_CLAUSES = 250000
MAX_LITERALS = 1400000
MAX_XOR_SEEDS = 120
MAX_EXTRAS_PER_SEED = 4
MAX_DERIVED = 32
MAX_LOCAL_CLAUSES = 80
MAX_SUPPORT = 5


def require(ok, message):
    if not ok:
        raise RuntimeError("R46_AUDIT_FAIL " + str(message))


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        for b in iter(lambda: stream.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def read_cnf(path):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        return None, None, "file_size_guard"
    clauses, current = [], []
    header = None
    nlit = 0
    with path.open("rt", encoding="ascii") as stream:
        for line in stream:
            line = line.strip()
            if not line or line.startswith(("c", "%")):
                continue
            if line.startswith("p "):
                fields = line.split()
                require(header is None and len(fields) == 4 and fields[:2] == ["p", "cnf"],
                        "malformed DIMACS")
                header = (int(fields[2]), int(fields[3]))
                continue
            require(header is not None, "DIMACS missing header")
            for token in line.split():
                lit = int(token)
                if lit:
                    require(0 < abs(lit) <= header[0], "literal outside variable range")
                    current.append(lit)
                    nlit += 1
                    if nlit > MAX_LITERALS:
                        return None, None, "literal_count_guard"
                else:
                    clauses.append(tuple(current))
                    current = []
                    if len(clauses) > MAX_CLAUSES:
                        return None, None, "clause_count_guard"
    require(header and not current and header[1] == len(clauses), "DIMACS count mismatch")
    return header[0], clauses, None


def complete_xor_seeds(clauses):
    # An XOR equation is recognized only when EVERY assignment of the
    # opposite parity is excluded by an original full-width clause.
    groups = collections.defaultdict(set)
    occurrences = collections.defaultdict(list)
    existing = set()
    for ci, clause in enumerate(clauses):
        if 1 <= len(clause) <= 4:
            key = tuple(sorted(set(map(abs, clause))))
            if len(key) == len(clause):
                existing.add(frozenset(clause))
        if 2 <= len(clause) <= 4:
            key = tuple(sorted(map(abs, clause)))
            if len(set(key)) != len(key):
                continue
            signs = {abs(x): x < 0 for x in clause}
            mask = sum((1 << i) for i, x in enumerate(key) if signs[x])
            groups[key].add(mask)
        if 1 <= len(clause) <= 4 and len({abs(x) for x in clause}) == len(clause):
            for v in set(map(abs, clause)):
                occurrences[v].append(ci)
    seeds = []
    for vars_, masks in groups.items():
        k = len(vars_)
        for rhs in (0, 1):
            # The falsifying assignment sets each negative literal's
            # variable to true and positive literal's variable to false.
            # Therefore its truth mask equals the negative-literal mask.
            required = {mask for mask in range(1 << k)
                        if (mask.bit_count() & 1) != rhs}
            if required <= masks:
                seeds.append((vars_, rhs))
    return sorted(set(seeds)), occurrences, existing


def clause_true(clause, assignment):
    return any(assignment[abs(x)] == (x > 0) for x in clause)


def certifies(local, derived, variables):
    # Deterministic exhaustive implication proof over <=5 variables.
    # Each local clause MUST be an unchanged original clause.
    for mask in range(1 << len(variables)):
        assignment = {v: bool(mask & (1 << j)) for j, v in enumerate(variables)}
        if all(clause_true(c, assignment) for c in local):
            if not clause_true(derived, assignment):
                return False
    return True


def derive_local(clauses):
    seeds, occur, existing = complete_xor_seeds(clauses)
    metrics = dict(seeds=len(seeds), inspected=0, derived=0,
                   units=0, binaries=0, reason="no_complete_xor")
    proofs, additions = [], []
    if not seeds:
        return additions, proofs, metrics
    added = set()
    for core, parity in seeds[:MAX_XOR_SEEDS]:
        if len(additions) >= MAX_DERIVED:
            break
        # Candidate bridge variables occur in a short clause touching
        # one of the confirmed XOR variables.
        candidate_ids = set()
        for v in core:
            candidate_ids.update(occur[v])
        bridges = collections.Counter()
        for ci in candidate_ids:
            vs = set(map(abs, clauses[ci]))
            if vs.intersection(core) and len(vs - set(core)) == 1:
                bridges[next(iter(vs - set(core)))] += 1
        extras = [None] + [x for x, _ in
                              sorted(bridges.items(), key=lambda p: (-p[1], p[0]))
                              [:MAX_EXTRAS_PER_SEED]]
        for extra in extras:
            support = tuple(sorted(set(core) | ({extra} if extra is not None else set())))
            if len(support) > MAX_SUPPORT:
                continue
            allow = set(support)
            ids = sorted(ci for ci in candidate_ids
                         if set(map(abs, clauses[ci])) <= allow)
            if extra is not None:
                ids = sorted(set(ids) | {
                    ci for ci in occur[extra]
                    if set(map(abs, clauses[ci])) <= allow})
            if len(ids) > MAX_LOCAL_CLAUSES or len(ids) < (1 << (len(core) - 1)):
                continue
            local = [clauses[i] for i in ids]
            metrics["inspected"] += 1
            vals = []
            for mask in range(1 << len(support)):
                assignment = {v: bool(mask & (1 << j)) for j, v in enumerate(support)}
                if all(clause_true(c, assignment) for c in local):
                    vals.append(assignment)
            if not vals:
                # Local contradiction is a consequence, but R46 only
                # injects short clauses and never self-certifies UNSAT.
                continue
            literals = [v if sign else -v for v in support for sign in (False, True)]
            proposed = [(lit,) for lit in literals]
            proposed += [(a, b) for a, b in itertools.combinations(literals, 2)
                         if abs(a) != abs(b)]
            for item in proposed:
                tag = frozenset(item)
                if tag in existing or tag in added:
                    continue
                # Fast filter, followed by independent exhaustive certificate.
                if any(clause_true(item, v) is False for v in vals):
                    continue
                require(certifies(local, item, support),
                        "local implication validation disagrees")
                additions.append(item)
                proofs.append(dict(clause=list(item), originals=ids,
                                   variables=list(support), parity=parity,
                                   seed=list(core)))
                added.add(tag)
                if len(additions) >= MAX_DERIVED:
                    break
            if len(additions) >= MAX_DERIVED:
                break
    metrics["derived"] = len(additions)
    metrics["units"] = sum(len(c) == 1 for c in additions)
    metrics["binaries"] = sum(len(c) == 2 for c in additions)
    metrics["reason"] = "certified_new_implications" if additions else "no_new_short_implication"
    return additions, proofs, metrics


def independently_audit(clauses, new, proofs):
    require(len(new) == len(proofs), "certificate row mismatch")
    for clause, proof in zip(new, proofs):
        support = tuple(proof["variables"])
        original = [clauses[i] for i in proof["originals"]]
        require(all(set(map(abs, c)) <= set(support) for c in original),
                "certificate incomplete support")
        require(tuple(clause) == tuple(proof["clause"]), "certificate wrong clause")
        require(certifies(original, clause, support), "certificate incorrect")


def write_augmented(path, n, clauses, new):
    with open(path, "wt", encoding="ascii") as dst:
        dst.write(f"p cnf {n} {len(clauses)+len(new)}\n")
        for clause in itertools.chain(clauses, new):
            dst.write(" ".join(map(str, clause)) + " 0\n")


def run_one(source, binary, mode):
    # Both preprocessing and solver count against the same measured wall cap.
    began = time.monotonic()
    telemetry = dict(seeds=0, inspected=0, derived=0, units=0,
                     binaries=0, reason="unprocessed")
    proposed, proofs, n, clauses = [], [], None, None
    candidate = source
    with tempfile.TemporaryDirectory(prefix="drnas_r46_") as tmp:
        if mode != "clean":
            n, clauses, guard = read_cnf(source)
            if guard:
                telemetry["reason"] = guard
            else:
                proposed, proofs, telemetry = derive_local(clauses)
                independently_audit(clauses, proposed, proofs)
                if mode == "active" and proposed:
                    candidate = Path(tmp) / "strengthened.cnf"
                    write_augmented(candidate, n, clauses, proposed)
        elapsed = time.monotonic() - began
        remaining = CAP - elapsed
        if remaining <= 0:
            return dict(answer="TIMEOUT", time_s=round(elapsed, 6),
                        par2_s=2*CAP, trace=telemetry)
        try:
            p = subprocess.run([str(binary), str(candidate)], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, errors="replace",
                               timeout=remaining)
            elapsed = time.monotonic() - began
            require(p.returncode in (10, 20),
                    "solver failed " + str(p.returncode) + ": " + p.stderr[-400:])
            answer = "SAT" if p.returncode == 10 else "UNSAT"
            if answer == "SAT":
                import r32p_real_satcomp26_benchmark as baseline
                baseline.verify_sat_witness(source, p.stdout)
            return dict(answer=answer, time_s=round(elapsed, 6),
                        par2_s=round(elapsed, 6), trace=telemetry)
        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - began
            return dict(answer="TIMEOUT", time_s=round(elapsed, 6),
                        par2_s=2*CAP, trace=telemetry)


def selftest():
    # x1 xor x2 xor x3 = 0, with x1=1 and x2=1 => x3=0.
    cnf = [
        (1, 2, -3), (1, -2, 3), (-1, 2, 3), (-1, -2, -3),
        (1,), (2,)
    ]
    new, proofs, trace = derive_local(cnf)
    independently_audit(cnf, new, proofs)
    require((-3,) in new, "failed cross-clause XOR/unit reasoning")
    # Independently enumerate the original and augmented formulas.
    for bits in itertools.product((False, True), repeat=3):
        a = {i+1: x for i, x in enumerate(bits)}
        lhs = all(clause_true(c, a) for c in cnf)
        rhs = all(clause_true(c, a) for c in cnf+new)
        require(lhs == rhs, "non-equivalent CNF extension")
    print("R46_CERTIFIED_SELFTEST_PASS", trace, flush=True)


def measure(args):
    manifest = json.loads((Path(args.frozen) / "manifest.json").read_text())
    require(manifest["protocol"].startswith("DRNAS-R32P-REAL-SATCOMP2026"),
            "wrong original frozen source")
    cases = manifest["cases"]
    require(len(cases) >= 3 and args.shard in range(SHARDS), "case or shard guard")
    binary = Path(args.clean).resolve()
    require(binary.is_file(), "pinned clean Kissat missing")
    if hasattr(os, "sched_getaffinity"):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    meta = dict(protocol=PROTO, shard=args.shard, manifest_sha=digest(Path(args.frozen)/"manifest.json"),
                binary_sha=digest(binary), cap=CAP, reps=REPS, modes=MODES)
    (out / "meta.json").write_text(json.dumps(meta, indent=2)+"\n")
    rows = []
    for case in cases[args.shard::SHARDS]:
        path = Path(args.frozen) / case["name"]
        require(digest(path) == case["sha256"], "official source SHA mismatch")
        for rep in range(REPS):
            ordered = list(MODES)
            seed = int(hashlib.sha256((case["sha256"]+str(rep)+PROTO).encode()).hexdigest(), 16)
            random.Random(seed).shuffle(ordered)
            for mode in ordered:
                result = run_one(path, binary, mode)
                rows.append(dict(sha256=case["sha256"], gbd=case["gbd"],
                                 rep=rep, mode=mode, **result))
                print("R46_TRIAL", case["gbd"], rep, mode, result, flush=True)
            (out/"rows.json").write_text(json.dumps(rows, indent=2)+"\n")
    print("R46_SHARD_PASS", args.shard, len(rows), flush=True)


def aggregate(args):
    root = Path(args.frozen)
    manifest = json.loads((root/"manifest.json").read_text())
    rows, shas = [], set()
    for shard in range(SHARDS):
        folder = Path(args.combined) / f"r46-shard-{shard}" / "results"
        meta = json.loads((folder/"meta.json").read_text())
        require(meta["protocol"] == PROTO and meta["shard"] == shard
                and meta["manifest_sha"] == digest(root/"manifest.json"),
                "shard protocol mismatch")
        shas.add(meta["binary_sha"])
        part = json.loads((folder/"rows.json").read_text())
        require(len(part) == len(manifest["cases"][shard::SHARDS])*REPS*len(MODES),
                "missing shard measurements")
        rows += part
    require(len(shas) == 1, "solver SHA differs across shards")
    stats = {}
    for mode in MODES:
        sub = [r for r in rows if r["mode"] == mode]
        stats[mode] = dict(par2_sum_s=round(sum(r["par2_s"] for r in sub), 6),
                           solved=sum(r["answer"] != "TIMEOUT" for r in sub),
                           timeouts=sum(r["answer"] == "TIMEOUT" for r in sub),
                           certified_injections=sum(r["trace"]["derived"] > 0 for r in sub),
                           derived_total=sum(r["trace"]["derived"] for r in sub))
    for case in manifest["cases"]:
        for rep in range(REPS):
            part = [r for r in rows if r["sha256"] == case["sha256"] and r["rep"] == rep]
            require({r["mode"] for r in part} == set(MODES), "unpaired experiment")
            verdicts = {r["answer"] for r in part} - {"TIMEOUT"}
            require(len(verdicts) <= 1, "inconsistent SAT/UNSAT verdict")
    report = dict(protocol=PROTO, source="SHA-pinned SATComp 2026 R32p original CNFs",
                  cases=len(manifest["cases"]), attempts=len(rows),
                  baseline_binary_sha=next(iter(shas)),
                  metrics=stats, rows=rows,
                  limitations=["Research-only preprocessing, not a native Kissat patch.",
                   "Original source CNF is only strengthened with exhaustively proven local implicates.",
                   "Source size and local-support guards may abstain; every abstention is reported.",
                   "Same pinned Kissat binary, same runner, fixed 30s overall cap including preprocessing.",
                   "SAT witnesses validated on unchanged original formulas, no independent UNSAT LRAT proof.",
                   "A restricted SATComp26 sample; no claim about official ranking."])
    Path(args.output).write_text(json.dumps(report, indent=2)+"\n")
    lines = ["# DRNAS SAT R46 — certified local links on official SATComp26 original CNFs",
             "",
             f'{len(manifest["cases"])} original SHA-pinned inputs, {len(rows)} trials,'
             " 30s total per trial, PAR-2=60s; 2 repeats; same pinned Kissat.",
             "Clean vs shadow (measures preprocessing cost) vs active (adds only certified clauses).",
             "", "| Mode | Solved attempts | PAR-2 sum, s | Trials with verified derived clauses |",
             "|---|---:|---:|---:|"]
    for mode in MODES:
        v = stats[mode]
        lines.append(f'| {mode} | {v["solved"]}/{len(manifest["cases"])*REPS} | {v["par2_sum_s"]:.4f} | {v["certified_injections"]} |')
    lines += ["", "## Each original source and repeat",
              "| Source GBD | Rep | Clean s | Shadow s | Active s | Added clauses | Reason |",
              "|---|---:|---:|---:|---:|---:|---|"]
    for case in manifest["cases"]:
        for rep in range(REPS):
            s = {r["mode"]: r for r in rows if r["sha256"] == case["sha256"] and r["rep"] == rep}
            lines.append(f'| {case["gbd"]} | {rep} | {s["clean"]["par2_s"]:.3f} | '
                         f'{s["shadow"]["par2_s"]:.3f} | {s["active"]["par2_s"]:.3f} | '
                         f'{s["active"]["trace"]["derived"]} | {s["active"]["trace"]["reason"]} |')
    lines += ["", "All derived clauses are certified against subsets of original CNF.",
              "Zero added clauses means no demonstrated local XOR transfer on that formula.",
              "PAR-2 totals include timeout penalties; no world-record claim."]
    Path(args.report).write_text("\n".join(lines)+"\n")
    print("R46_OFFICIAL_AUDIT_PASS", len(rows), json.dumps(stats, sort_keys=True), flush=True)


def main():
    p = argparse.ArgumentParser()
    q = p.add_subparsers(dest="command", required=True)
    q.add_parser("selftest")
    m = q.add_parser("measure")
    for field in ("frozen", "clean", "out"):
        m.add_argument("--"+field, required=True)
    m.add_argument("--shard", type=int, required=True)
    a = q.add_parser("aggregate")
    for field in ("frozen", "combined", "output", "report"):
        a.add_argument("--"+field, required=True)
    args = p.parse_args()
    if args.command == "selftest":
        selftest()
    elif args.command == "measure":
        measure(args)
    else:
        aggregate(args)


if __name__ == "__main__":
    main()
