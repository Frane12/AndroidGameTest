#!/usr/bin/env python3
"""DRNAS X13B: certified CNF clause surgery, causal original-SHA paired E2E test.

Preserves the original 32 X11 CNF files, source SHAs and pinned solver backends.
Unlike clause-order-only X11, this tests proof-safe *logical* deletion:
duplicate clauses, tautological clauses, and clauses subsumed by a unit/binary
clause. No unrestricted resolution, no learned clauses, no hint files.
All SAT answers replay on the unmodified source. UNSAT scores need agreement
between CMS and an independent reference solver; no LRAT is claimed.
This is reuse of X11 historical formulas, NOT a prospective blind holdout.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import itertools
import json
import math
import os
import pathlib
import random
import subprocess
import tempfile
import time

import mre_x11_placebo_causal as x11

PROTO = "DRNAS-X13B-CLAUSE-SURGERY-32SHA-8ARM-2REP-15S-20261109-v1"
ROOT = pathlib.Path("mre_x13b")
CAP = 15.0
REPS = 2
SHARDS = 8
ARMS = (
    "original", "sample_noop", "sample_front", "sample_reduce",
    "front100", "gate_reduce", "kissat", "cadical"
)
EXPECTED = 32 * REPS * len(ARMS)

def need(ok, why):
    if not ok:
        raise RuntimeError("X13B_FAIL_CLOSED " + why)

def save(path, obj):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")

def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def dedup(clauses):
    seen = set()
    result = []
    for c in clauses:
        key = frozenset(c)
        if key not in seen:
            result.append(c)
            seen.add(key)
    return result

def certified_reduce(clauses):
    # Exactly equivalent CNF: every deleted clause is a tautology, identical
    # to another clause, or is subsumed by a unit/binary clause still present.
    seen = set()
    unique = []
    removed = collections.Counter()
    for c in clauses:
        key = frozenset(c)
        if any(-v in key for v in key):
            removed["tautologies"] += 1
            continue
        if key in seen:
            removed["duplicates"] += 1
            continue
        seen.add(key)
        unique.append(c)
    units = {c[0] for c in unique if len(set(c)) == 1 and len(c) == 1}
    binaries = {frozenset(c) for c in unique if len(set(c)) == 2}
    result = []
    for c in unique:
        s = set(c)
        if len(s) > 1 and any(v in units for v in s):
            removed["unit_subsumed"] += 1
            continue
        # For safety and cost, do not probe wider clauses for binary subsumption.
        if 2 < len(s) <= 16 and any(frozenset(pair) in binaries
                          for pair in itertools.combinations(s, 2)):
            removed["binary_subsumed"] += 1
            continue
        result.append(c)
    need(len(result) + sum(removed.values()) == len(clauses),
         "certified reducer accounting")
    return result, dict(removed)

def freeze():
    prior = x11.verify()
    ROOT.mkdir(exist_ok=True)
    cases = prior["cases"]
    need(len(cases) == 32 and len({c["sha256"] for c in cases}) == 32,
         "wrong X11 original SHAs")
    structure = json.loads((x11.ROOT / "structure.json").read_text())
    feats = {r["sha256"]: r for r in structure["sources"]}
    need(set(feats) == {c["sha256"] for c in cases}, "structure manifest mismatch")
    save(ROOT / "manifest.json", dict(
        protocol=PROTO, predecessor_x11_run=42563452186,
        predecessor_x11_manifest_sha256=sha(x11.ROOT / "manifest.json"),
        cases=cases, original_source_count=len(cases),
        duplicate_positive=sum(feats[c["sha256"]]["duplicate_count"] > 0
                               for c in cases),
        historical_prepared_not_blind=True, source_sha_locked=True,
        solver_binaries_identical_to_x11=True,
        arms=ARMS, cap_s=CAP, repetitions=REPS, shards=SHARDS,
        expected_trials=EXPECTED, no_auto_promotion=True,
        independent_unsat_lrat=False,
        gate_rule="sample first+last 128KiB; skip any rewrite unless >=2 "
                  "exact repeated original DIMACS lines in sample; "
                  "then front100 or certified reduction; "
                  "old full gate retained as controlled baseline",
        safety="equivalent CNF, original-source SAT witness replay, "
               "UNSAT cross-solver agreement for scored solutions"))
    print("X13B_FROZEN", len(cases), EXPECTED, flush=True)

def manifest():
    x11.verify()
    m = json.loads((ROOT / "manifest.json").read_text())
    need(m["protocol"] == PROTO and m["expected_trials"] == EXPECTED and
         tuple(m["arms"]) == ARMS and len(m["cases"]) == 32,
         "protocol/arm drift")
    need(sha(x11.ROOT / "manifest.json") ==
         m["predecessor_x11_manifest_sha256"], "predecessor manifest changed")
    return m

def transform(clauses, arm):
    stats = {"input_clauses": len(clauses), "removed": {},
             "selected": arm}
    if arm == "rewrite_identity":
        out = list(clauses)
    elif arm == "front100":
        out = x11.transform(clauses, "front100")
        need(collections.Counter(map(tuple, out)) ==
             collections.Counter(map(tuple, clauses)),
             "clause-order-only control changed CNF multiset")
    elif arm == "dedup":
        out = dedup(clauses)
    elif arm == "reduce":
        out, stats["removed"] = certified_reduce(clauses)
    elif arm == "front_reduce":
        front = x11.transform(clauses, "front100")
        out, stats["removed"] = certified_reduce(front)
    elif arm == "gate_reduce":
        reduced, removed = certified_reduce(clauses)
        removed_n = len(clauses) - len(reduced)
        duplicates = len(x11.x9.x6.x3.duplicates(clauses))
        if duplicates >= 2 and removed_n >= 2:
            front = x11.transform(clauses, "front100")
            out, stats["removed"] = certified_reduce(front)
            stats["selected"] = "front_reduce"
        elif removed_n >= max(64, math.ceil(.01 * len(clauses))):
            out, stats["removed"] = reduced, removed
            stats["selected"] = "reduce"
        else:
            out = clauses
            stats["selected"] = "original"
        stats["duplicate_signals"] = duplicates
    else:
        need(False, "unexpected transform arm: " + arm)
    stats["output_clauses"] = len(out)
    stats["deleted"] = len(clauses) - len(out)
    return out, stats

def cheap_duplicate_signal(source):
    """Read at most 256 KiB, never rewrite based on a speculative inference.
    An incomplete or wrapped DIMACS line can cause only a false negative:
    the exact CNF is parsed and proof-safe transformed if selected.
    """
    p = pathlib.Path(source)
    size = p.stat().st_size
    with p.open("rb") as f:
        if size <= 262144:
            regions = [f.read(262144)]
        else:
            regions = [f.read(131072)]
            f.seek(-131072, os.SEEK_END)
            regions.append(f.read(131072))
    seen = set()
    duplicates = 0
    sample_lines = 0
    for ix, region in enumerate(regions):
        lines = region.splitlines()
        if size > 262144 and ix > 0:
            lines = lines[1:]
        if size > 262144 and ix == 0:
            lines = lines[:-1]
        for raw in lines:
            line = raw.strip()
            if not line or line[:1] in (b"c", b"p"):
                continue
            sample_lines += 1
            if line in seen:
                duplicates += 1
            else:
                seen.add(line)
    return dict(duplicates=duplicates, lines=sample_lines,
                sampled_bytes=sum(len(x) for x in regions),
                size_bytes=size)

def trial(c, rep, arm):
    need(arm in ARMS and rep in range(REPS), "invalid benchmark arm")
    src = x11.ROOT / c["filename"]
    need(sha(src) == c["sha256"], "source SHA mismatch")
    seed = x11.seed(c, rep)
    start = time.perf_counter()
    env = os.environ.copy()
    env.pop("DRNAS_MAX_CONFLICTS", None)
    status = "TIMEOUT"
    verified = False
    reduction = {"selected": arm, "deleted": 0}
    proc = None
    with tempfile.TemporaryDirectory(dir=ROOT) as temp:
        target = src
        if arm in ("sample_noop", "sample_front", "sample_reduce"):
            signal = cheap_duplicate_signal(src)
            reduction = {"selected": "original", "deleted": 0, "sample": signal}
            if arm != "sample_noop" and signal["duplicates"] >= 2:
                nvars, clauses = x11.x9.x2.parse(src)
                selected = "front100" if arm == "sample_front" else "reduce"
                rewritten, actual = transform(clauses, selected)
                reduction.update(actual)
                reduction["sample"] = signal
                target = pathlib.Path(temp) / "transformed.cnf"
                x11.x9.x2.write(target, nvars, rewritten)
        elif arm not in ("original", "kissat", "cadical"):
            nvars, clauses = x11.x9.x2.parse(src)
            rewritten, reduction = transform(clauses, arm)
            if not (arm == "gate_reduce" and reduction["selected"] == "original"):
                target = pathlib.Path(temp) / "transformed.cnf"
                x11.x9.x2.write(target, nvars, rewritten)
        prep = time.perf_counter() - start
        if arm == "kissat":
            binary = pathlib.Path("built/bin/kissat_4_0_4")
            cmd = [str(binary.resolve()), "--seed=" + str(seed),
                   str(target.resolve())]
        elif arm == "cadical":
            binary = pathlib.Path("/usr/bin/cadical")
            cmd = [str(binary.resolve()), str(target.resolve())]
        else:
            binary = pathlib.Path("mre_x4/bin/native")
            cmd = [str(binary.resolve()), str(target.resolve()),
                   "x_native", str(seed)]
        remain = CAP - (time.perf_counter() - start)
        if remain > 0:
            try:
                proc = subprocess.run(cmd, env=env, capture_output=True,
                   text=True, errors="replace", timeout=remain, check=False)
            except subprocess.TimeoutExpired:
                pass
        elapsed = time.perf_counter() - start
        if proc is not None:
            if arm in ("kissat", "cadical"):
                need(proc.returncode in (10, 20),
                     "reference process error: " + (proc.stderr or "")[-300:])
                status = "SAT" if proc.returncode == 10 else "UNSAT"
                need(("s SATISFIABLE" if status == "SAT"
                      else "s UNSATISFIABLE") in proc.stdout,
                     "missing reference verdict")
                model = {}
                for line in proc.stdout.splitlines():
                    if line.startswith("v "):
                        for literal in map(int, line[2:].split()):
                            if literal:
                                need(abs(literal) not in model or
                                     model[abs(literal)] == (literal > 0),
                                     "conflicting SAT model literals")
                                model[abs(literal)] = literal > 0
            else:
                need(proc.returncode == 0,
                     "CMS crashed " + (proc.stderr or "")[-300:])
                gate = x11.x9.x6.x4.base.parse_gate(proc.stdout, "x_native")
                need(not gate["applied"],
                     "native backend applied unexpected additional rewriting")
                status, model, _ = x11.x9.x6.x4.base.cms.parsed_native(proc.stdout)
            if status == "SAT" and elapsed <= CAP:
                x11.x9.x6.x4.base.cms.verify_model(src, model)
                verified = True
    if status not in ("SAT", "UNSAT") or elapsed > CAP:
        status = "TIMEOUT"
        verified = False
    return dict(protocol=PROTO, original_sha256=c["sha256"], gbd=c["gbd"],
        cohort=c["cohort"], arm=arm, rep=rep, seed=seed,
        status=status, elapsed_s=round(elapsed, 6),
        preprocess_s=round(prep, 6), cap_s=CAP,
        PAR2_s=round(elapsed if status != "TIMEOUT" else 2 * CAP, 6),
        SAT_original_witness_verified=verified,
        UNSAT_independent_LRAT=False,
        binary_sha256=sha(binary), reduction=reduction)

def shard(index):
    m = manifest()
    need(index in range(SHARDS), "invalid shard")
    selection = [c for i, c in enumerate(m["cases"]) if i % SHARDS == index]
    need(len(selection) == 4, "shard has wrong source count")
    rows = []
    for c in selection:
        for rep in range(REPS):
            order = list(ARMS)
            random.Random(x11.seed(c, rep)).shuffle(order)
            for arm in order:
                result = trial(c, rep, arm)
                rows.append(result)
                save(ROOT / ("shard-%d.json" % index), rows)
                print("X13B_TRIAL", json.dumps(result, sort_keys=True), flush=True)
    need(len(rows) == 4 * REPS * len(ARMS), "short shard")
    print("X13B_SHARD_PASS", index, len(rows), flush=True)

def audit():
    m = manifest()
    cases = {c["sha256"]: c for c in m["cases"]}
    rows = []
    for i in range(SHARDS):
        rows.extend(json.loads((ROOT / ("shard-%d.json" % i)).read_text()))
    expected = {(c, rep, arm) for c in cases
                for rep in range(REPS) for arm in ARMS}
    actual = {(r["original_sha256"], r["rep"], r["arm"]) for r in rows}
    need(len(rows) == len(actual) == EXPECTED and actual == expected,
         "incomplete or duplicated source-seed paired trials")
    per_source = []
    for c_sha, c in cases.items():
        rs = [r for r in rows if r["original_sha256"] == c_sha]
        verdicts = {r["status"] for r in rs if r["status"] != "TIMEOUT"}
        need(len(verdicts) <= 1, "SAT/UNSAT cross-solver contradiction")
        cms_unsat = any(r["status"] == "UNSAT" and
                        r["arm"] not in ("kissat", "cadical") for r in rs)
        ref_unsat = any(r["status"] == "UNSAT" and
                        r["arm"] in ("kissat", "cadical") for r in rs)
        for r in rs:
            need(r["protocol"] == PROTO and r["gbd"] == c["gbd"] and
                 r["seed"] == x11.seed(c, r["rep"]) and r["cap_s"] == CAP,
                 "protocol/source/seed mismatch")
            need(r["status"] != "SAT" or r["SAT_original_witness_verified"],
                 "SAT solution without replayed original model")
            need(r["status"] != "TIMEOUT" or r["PAR2_s"] == 2 * CAP,
                 "timeout penalty mismatch")
            need(r["status"] == "TIMEOUT" or
                 r["elapsed_s"] <= CAP and r["PAR2_s"] == r["elapsed_s"],
                 "solved PAR2 not E2E")
            r["accepted"] = (r["status"] == "SAT" or
               r["status"] == "UNSAT" and cms_unsat and ref_unsat)
            r["audited_PAR2_s"] = (r["PAR2_s"] if r["accepted"] else 2 * CAP)
        by_arm = {arm: round(sum(r["audited_PAR2_s"] for r in rs
                        if r["arm"] == arm), 6) for arm in ARMS}
        per_source.append(dict(gbd=c["gbd"], sha256=c_sha,
            cohort=c["cohort"], PAR2_s=by_arm,
            front_gain_s=round(by_arm["original"] - by_arm["front100"], 6),
            gated_gain_s=round(by_arm["original"] - by_arm["gate_reduce"], 6),
        sampled_front_gain_s=round(by_arm["original"] - by_arm["sample_front"], 6),
        sampled_reduce_gain_s=round(by_arm["original"] - by_arm["sample_reduce"], 6)))
    score = {}
    for arm in ARMS:
        rs = [r for r in rows if r["arm"] == arm]
        score[arm] = dict(n=len(rs),
            solved=sum(r["accepted"] for r in rs),
            timeouts=sum(r["status"] == "TIMEOUT" for r in rs),
            PAR2_s=round(sum(r["audited_PAR2_s"] for r in rs), 6),
            prep_s=round(sum(r["preprocess_s"] for r in rs), 6))
    for arm, v in score.items():
        for baseline in ("original", "kissat", "cadical"):
            baseline_s = score[baseline]["PAR2_s"]
            v["pct_less_PAR2_vs_" + baseline] = round(
                100.0 * (1 - v["PAR2_s"] / baseline_s), 4)
            v["speedup_vs_" + baseline] = round(
                baseline_s / v["PAR2_s"], 5)
    gates = collections.Counter(r["reduction"]["selected"] for r in rows
                                 if r["arm"] == "gate_reduce")
    sample_decisions = {arm: dict(collections.Counter(r["reduction"]["selected"]
                  for r in rows if r["arm"] == arm))
                  for arm in ("sample_noop", "sample_front", "sample_reduce")}
    results = dict(protocol=PROTO, trials=len(rows), original_sources=32,
       sample_decisions=sample_decisions,
       cap_s=CAP, score=score, gated_selected=dict(gates),
       source_reused_not_blind=True, certified_reduction_not_LRAT=True,
       UNSAT_independent_LRAT=False, no_auto_promotion=True,
       rows=rows, per_source=per_source)
    save(ROOT / "report.json", results)
    print("X13B_FINAL", json.dumps({k: v for k, v in results.items()
      if k not in ("rows", "per_source")}, sort_keys=True), flush=True)

def selftest():
    randomizer = random.Random(1309)
    for _ in range(400):
        n = randomizer.randrange(1, 6)
        formula = [tuple(randomizer.choice(
            (-1, 1)) * randomizer.randrange(1, n + 1)
            for _ in range(randomizer.randrange(0, 5)))
            for _ in range(randomizer.randrange(0, 13))]
        for arm in ("rewrite_identity", "front100", "dedup", "reduce",
                    "front_reduce", "gate_reduce"):
            result, _ = transform(formula, arm)
            for bits in itertools.product((False, True), repeat=n):
                def ev(cnf):
                    return all(any((lit > 0) == bits[abs(lit) - 1]
                               for lit in clause) for clause in cnf)
                need(ev(formula) == ev(result),
                     "truth-table equivalence failed: " + arm)
    with tempfile.TemporaryDirectory() as temp:
        sample = pathlib.Path(temp) / "probe.cnf"
        sample.write_text("p cnf 3 4\\n1 2 0\\n-1 3 0\\n1 2 0\\n1 2 0\\n".replace("\\n", "\n"))
        need(cheap_duplicate_signal(sample)["duplicates"] == 2,
             "cheap scan must detect repeated DIMACS lines")
        sample.write_text("p cnf 1 1\\n1 0\\n".replace("\\n", "\n"))
        need(cheap_duplicate_signal(sample)["duplicates"] == 0,
             "cheap scan must reject distinct clause")
    print("X13B_SELFTEST_PASS 400 exhaustive truth tables and cheap probes", flush=True)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=(
        "selftest", "freeze", "verify", "shard", "audit"))
    parser.add_argument("--shard", type=int, default=0)
    args = parser.parse_args()
    if args.action == "selftest":
        selftest()
    elif args.action == "freeze":
        freeze()
    elif args.action == "verify":
        manifest()
        print("X13B_VERIFY_PASS", flush=True)
    elif args.action == "shard":
        shard(args.shard)
    elif args.action == "audit":
        audit()

if __name__ == "__main__":
    main()
