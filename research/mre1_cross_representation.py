#!/usr/bin/env python3
"""MRE1 / Cross-Representation Reduction: CNF -> certified XOR -> GF2
-> short CNF lemmas -> binary resolution -> GF2 again.
Proofs are replayed from the ORIGINAL clauses. No original clause is removed.
This is a bounded experimental *pre-solve* loop, not a new CMS trail callback.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import os
import pathlib
import random
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import r164_pure_exact_gf2 as exact
import r195_native_cms_benchmark as r195

PROTO = "DRNAS-MRE1-CRR-32SHA-4ARM-2REP-20261108-v1"
MODES = ("cms_native", "source_xor", "crr_shadow", "crr_active")
CAP, REPS, SHARDS = 30.0, 2, 8
ROOT = pathlib.Path("mre1")
MAX_SOURCE_ROWS = 150
MAX_DERIVED = 96
MAX_BINARY_POOL = 180
MAX_CHECKS = 4000
PREP_BUDGET = 2.0


def need(condition, why):
    if not condition:
        raise RuntimeError("MRE1_FAIL_CLOSED: " + str(why))


def normalize(clause):
    s = set(clause)
    if any(-x in s for x in s):
        return None
    return tuple(sorted(s, key=lambda x: (abs(x), x)))


def mask(vs):
    out = 0
    for v in vs:
        need(v > 0 and not (out & (1 << (v-1))), "bad GF2 variables")
        out |= 1 << (v-1)
    return out


def vars_of(m):
    out = []
    while m:
        bit = m & -m
        out.append(bit.bit_length())
        m ^= bit
    return tuple(out)


def clauses_for(m, rhs):
    v = vars_of(m)
    need(rhs in (0, 1) and len(v) <= 2, "unsupported GF2 CNF projection")
    if not v:
        return [()] if rhs else []
    if len(v) == 1:
        return [(v[0] if rhs else -v[0],)]
    a, b = v
    if rhs:
        return [normalize((a, b)), normalize((-a, -b))]
    return [normalize((-a, b)), normalize((a, -b))]


def replay_source_xors(source, rows):
    original = {normalize(c) for c in source}
    for vs, rhs in rows:
        need(2 <= len(vs) <= 6 and tuple(sorted(set(vs))) == vs,
             "source XOR invalid")
        for bits in range(1 << len(vs)):
            if (bits.bit_count() & 1) == rhs:
                continue
            forbidden = normalize(
                [-v if bits & (1 << k) else v for k, v in enumerate(vs)])
            need(forbidden in original, "source XOR is not CNF-implied")


def reduce_gf2(inputs):
    pivot = {}
    for idx, (m0, b0, _) in enumerate(inputs):
        m, b, evidence = m0, b0, 1 << idx
        while m:
            lead = m & -m
            if lead not in pivot:
                pivot[lead] = (m, b, evidence)
                break
            pm, pb, pe = pivot[lead]
            m ^= pm
            b ^= pb
            evidence ^= pe
        else:
            if b:
                return [(0, 1, evidence)]
    for lead in sorted(pivot, reverse=True):
        for small in sorted(pivot):
            if small >= lead:
                break
            m, b, e = pivot[small]
            if m & lead:
                pm, pb, pe = pivot[lead]
                pivot[small] = (m ^ pm, b ^ pb, e ^ pe)
    return list(pivot.values())


def resolution(left, right, pivot):
    need(pivot in left and -pivot in right, "resolution pivot absent")
    return normalize([x for x in left if x != pivot] +
                     [x for x in right if x != -pivot])


def verify_proofs(original, source_rows, proofs):
    """Separate deterministic replay over only ORIGINAL CNF + proven lemmas."""
    replay_source_xors(original, source_rows)
    seen = {normalize(c) for c in original if normalize(c) is not None}
    src = set(source_rows)
    for record in proofs:
        target = tuple(record["clause"])
        need(target == normalize(target) and target not in seen,
             "bad/duplicate derived lemma")
        if record["kind"] == "gf2":
            lhs = rhs = 0
            for entry in record["origins"]:
                if entry[0] == "source":
                    _, variables, parity = entry
                    variables = tuple(variables)
                    need((variables, parity) in src, "GF2 used unproven source")
                    lhs ^= mask(variables)
                    rhs ^= parity
                else:
                    need(entry[0] == "unit" and len(entry) == 2,
                         "unexpected GF2 input")
                    lit = entry[1]
                    need((lit,) in seen, "GF2 unit was not yet proven")
                    lhs ^= mask((abs(lit),))
                    rhs ^= int(lit > 0)
            need(lhs == record["mask"] and rhs == record["rhs"],
                 "incorrect GF2 combination")
            need(target in clauses_for(lhs, rhs), "invalid GF2 projection")
        elif record["kind"] == "resolution":
            left, right = tuple(record["left"]), tuple(record["right"])
            need(left in seen and right in seen, "missing resolution parent")
            need(resolution(left, right, record["pivot"]) == target,
                 "invalid resolution step")
        else:
            need(False, "unknown proof method")
        seen.add(target)
    return True


def derive(original, max_s=PREP_BUDGET):
    began = time.perf_counter()
    need(len(original) <= 150000, "excessive source clause count")
    source = r195.certified_source_rows(original)[:MAX_SOURCE_ROWS]
    replay_source_xors(original, source)
    known = {normalize(c) for c in original if normalize(c) is not None}
    proofs = []
    stats = dict(source_rows=len(source), gf2_lemmas=0,
                 resolution_lemmas=0, rounds=0, proof_replayed=False,
                 budget_exhausted=False)

    def add(record):
        target = tuple(record["clause"])
        if target in known or len(proofs) >= MAX_DERIVED:
            return False
        need(target == normalize(target), "invalid lemma")
        proofs.append(record)
        known.add(target)
        stats[("gf2" if record["kind"] == "gf2" else "resolution") +
              "_lemmas"] += 1
        return True

    for round_no in range(2):
        if time.perf_counter() - began > max_s:
            stats["budget_exhausted"] = True
            break
        stats["rounds"] += 1
        inputs = [(mask(vs), rhs, ("source", vs, rhs))
                  for vs, rhs in source]
        units = sorted((c[0] for c in known if c is not None and len(c) == 1),
                       key=lambda x: (abs(x), x))
        for lit in units[:128]:
            inputs.append((mask((abs(lit),)), int(lit > 0), ("unit", lit)))
        for m, rhs, trace in reduce_gf2(inputs):
            if m.bit_count() > 2:
                continue
            origins = [inputs[i][2] for i in range(len(inputs))
                       if trace & (1 << i)]
            check_m = check_rhs = 0
            for i in range(len(inputs)):
                if trace & (1 << i):
                    check_m ^= inputs[i][0]
                    check_rhs ^= inputs[i][1]
            need((check_m, check_rhs) == (m, rhs),
                 "GF2 trace mismatch")
            for c in clauses_for(m, rhs):
                add(dict(kind="gf2", clause=c, mask=m, rhs=rhs,
                         origins=origins))
        # Bounded implication/resolution bridge: short CNF -> new GF2 units.
        small = sorted((c for c in known if c is not None and len(c) <= 2),
                       key=lambda c: (len(c), c))
        small = small[:MAX_BINARY_POOL]
        by_literal = collections.defaultdict(list)
        for c in small:
            for lit in c:
                by_literal[lit].append(c)
        checked = 0
        for left in small:
            for lit in left:
                for right in by_literal.get(-lit, ()):
                    if checked >= MAX_CHECKS or len(proofs) >= MAX_DERIVED:
                        break
                    checked += 1
                    c = resolution(left, right, lit)
                    if c is not None and len(c) <= 2:
                        add(dict(kind="resolution", clause=c,
                                 left=left, right=right, pivot=lit))
                if checked >= MAX_CHECKS:
                    break
            if checked >= MAX_CHECKS:
                break
    # Fail closed: do not import any CRR lemma without full independent replay.
    verify_proofs(original, source, proofs)
    stats["proof_replayed"] = True
    stats["derived_clauses"] = len(proofs)
    stats["prep_s"] = round(time.perf_counter()-began, 6)
    return source, proofs, stats


def write_cnf(path, n, original, proofs):
    all_clauses = list(original) + [p["clause"] for p in proofs]
    with open(path, "w", encoding="utf8") as f:
        f.write("p cnf %d %d\n" % (n, len(all_clauses)))
        for clause in all_clauses:
            f.write(" ".join(map(str, clause)) + " 0\n")


def write_xors(path, rows):
    with open(path, "w", encoding="utf8") as f:
        for vs, rhs in rows:
            f.write("%d %d %s\n" % (len(vs), rhs,
                                    " ".join(map(str, vs))))


def trial(case, rep, mode, binary):
    source_file = r195.FROZEN / case["name"]
    need(r195.digest(source_file) == case["sha256"], "SHA mismatch")
    started = time.perf_counter()
    n, original = exact.parse_dimacs(source_file)
    stats = dict(source_rows=0, derived_clauses=0, proof_replayed=True,
                 rounds=0, prep_s=0)
    rows, proofs = [], []
    if mode != "cms_native":
        prep_started = time.perf_counter()
        if mode == "source_xor":
            rows = r195.certified_source_rows(original)[:MAX_SOURCE_ROWS]
            replay_source_xors(original, rows)
            stats["source_rows"] = len(rows)
        else:
            rows, proofs, stats = derive(original)
        stats["prep_s"] = round(time.perf_counter()-prep_started, 6)
    seed = int(hashlib.sha256((PROTO+case["sha256"]+str(rep))
                               .encode()).hexdigest()[:8], 16)
    result, model, native = "TIMEOUT", {}, {}
    with tempfile.TemporaryDirectory(prefix="drnas-mre1-") as d:
        d = pathlib.Path(d)
        cnf, rowfile, empty = d/"input.cnf", d/"source.tsv", d/"empty.tsv"
        write_cnf(cnf, n, original,
                  proofs if mode == "crr_active" else [])
        write_xors(rowfile, rows)
        empty.write_text("")
        cms_mode = "cms_native" if mode == "cms_native" else "source_xor_import"
        remaining = CAP-(time.perf_counter()-started)
        if remaining >= 0.1:
            try:
                p = subprocess.run([str(pathlib.Path(binary).resolve()),
                                    str(cnf), str(rowfile), str(empty),
                                    cms_mode, str(seed)],
                                   capture_output=True, text=True,
                                   timeout=remaining, check=False)
            except subprocess.TimeoutExpired:
                p = None
            if p is not None:
                need(p.returncode == 0,
                     "CMS bridge failure: " + p.stderr[-1200:])
                result, model, native = r195.parsed_native(p.stdout)
                if result == "SAT":
                    r195.verify_model(source_file, model)
    elapsed = time.perf_counter()-started
    if elapsed >= CAP:
        result = "TIMEOUT"
    if result != "TIMEOUT":
        need(result == case["expected"], "verdict differs from expected")
    return dict(protocol=PROTO, source_sha256=case["sha256"],
                id=case["name"], cohort=case["cohort"],
                mode=mode, rep=rep, status=result,
                elapsed_s=round(elapsed, 6),
                par2_s=round(2*CAP if result == "TIMEOUT" else elapsed, 6),
                prep_s=stats["prep_s"], source_rows=len(rows),
                derived_clauses=stats.get("derived_clauses", 0),
                rounds=stats.get("rounds", 0),
                proof="ORIGINAL_CNF_SAT_MODEL_CHECKED" if result == "SAT"
                      else "UNSAT_NOT_INDEPENDENT_LRAT" if result == "UNSAT"
                      else "CAP_TIMEOUT",
                cms_conflicts=native.get("conflicts"),
                cms_decisions=native.get("decisions"),
                github_sha=os.environ.get("GITHUB_SHA", "local"))


def selftest():
    a = r195.xor_cnf((1, 2, 3), 0)
    b = r195.xor_cnf((2, 3), 1)
    original = a+b+[(4, 5), (-4, 6), (-6, 5)]
    src, proof, stats = derive(original, max_s=5)
    need(((1, 2, 3), 0) in src and ((2, 3), 1) in src,
         "failed to recover source XOR")
    need((1,) in [tuple(p["clause"]) for p in proof],
         "GF2 did not discover implied x=1")
    verify_proofs(original, src, proof)
    need(stats["proof_replayed"], "proof replay missing")
    print("MRE1_SELFTEST_PASS", json.dumps(stats, sort_keys=True), flush=True)


def shard(shard_id, binary):
    need(0 <= shard_id < SHARDS, "invalid shard")
    cases = r195.cases()
    results = []
    ROOT.mkdir(parents=True, exist_ok=True)
    for c in cases[shard_id::SHARDS]:
        for rep in range(REPS):
            modes = list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(modes)
            for mode in modes:
                record = trial(c, rep, mode, binary)
                results.append(record)
                print("MRE1_TRIAL", json.dumps(record, sort_keys=True),
                      flush=True)
    need(len(results) == len(cases[shard_id::SHARDS])*REPS*len(MODES),
         "shard incomplete")
    (ROOT/("shard-%d.json" % shard_id)).write_text(
        json.dumps(results, sort_keys=True)+"\n")
    print("MRE1_SHARD_PASS", shard_id, len(results), flush=True)


def audit():
    cases = r195.cases()
    rows = []
    for i in range(SHARDS):
        rows += json.loads((ROOT/("shard-%d.json" % i)).read_text())
    need(len(rows) == len(cases)*REPS*len(MODES) == 256,
         "incomplete 256 paired measurements")
    groups = collections.defaultdict(dict)
    for row in rows:
        key = (row["source_sha256"], row["rep"])
        need(row["mode"] not in groups[key], "duplicate arm")
        groups[key][row["mode"]] = row
        need(row["proof"] == "ORIGINAL_CNF_SAT_MODEL_CHECKED"
             if row["status"] == "SAT" else True,
             "unverified SAT model")
    for item in groups.values():
        need(set(item) == set(MODES), "missing mode")
        need(len({x["status"] for x in item.values()
                  if x["status"] != "TIMEOUT"}) <= 1,
             "solver verdict disagreement")
    totals = {}
    for name in ("all", "reused_official_2026",
                 "reused_synthetic_controls", "new_mixed_xor_cnf"):
        cohort = [r for r in rows if name == "all" or r["cohort"] == name]
        totals[name] = {}
        for mode in MODES:
            subset = [r for r in cohort if r["mode"] == mode]
            totals[name][mode] = dict(
                attempts=len(subset),
                solved=sum(r["status"] != "TIMEOUT" for r in subset),
                par2_s=round(sum(r["par2_s"] for r in subset), 6),
                prep_s=round(sum(r["prep_s"] for r in subset), 6),
                derived_clauses=sum(r["derived_clauses"] for r in subset))
    report = dict(protocol=PROTO, cohort="development NOT blind",
                  source_count=len(cases), measurements=len(rows),
                  independent_UNSAT_LRAT=False,
                  original_SAT_model_verified=True,
                  full_wall_includes_preprocessing=True, totals=totals)
    (ROOT/"report.json").write_text(json.dumps(report, indent=2,
                                               sort_keys=True)+"\n")
    print("MRE1_FINAL", json.dumps(report, sort_keys=True), flush=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=("selftest", "shard", "audit"))
    ap.add_argument("--shard", type=int, default=0)
    ap.add_argument("--binary", default="mre1/native")
    options = ap.parse_args()
    if options.action == "selftest":
        selftest()
    elif options.action == "shard":
        shard(options.shard, options.binary)
    else:
        audit()
