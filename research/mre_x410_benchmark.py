#!/usr/bin/env python3
"""X4 order x MRE10 joint factorial. Known development SHA union, not blind.

All seven arms use one C++ executable and one pinned CMS library, four paired
numeric seeds, one thread, 12s end-to-end INCLUDING parse/order/quotient/witness.
X4 permutations precede joint; joint may erase their duplicate-position effect.
UNSAT is frozen reference agreement only, no independent LRAT.
"""
import argparse
import collections
import hashlib
import itertools
import json
import os
import pathlib
import random
import re
import resource
import subprocess
import tempfile
import time

OUT = pathlib.Path("mre_x410")
BIN = OUT / "bin/native"
EMIT = OUT / "bin/emit"
REF_EMIT = OUT / "bin/mre10_emit"
CAP, REPS, SHARDS = 12.0, 4, 4
ARMS = ("native", "joint", "spread100", "shifted",
        "spread100_joint", "shifted_joint", "ref6f")
PROTO = "DRNAS-MRE-X410-X4xCPPJOINT-UNIONSHA-7ARM-4SEED-12S-E2E-v1"
X4_SHA = (
    "69aa8b6bb96a5952fedf1007994b4255d06f7e32023390bc4c342b1b30a0356a",
    "7f25d0862e92fb60d957ea903ded020ec2b83b2ceec2ba4bf015bdcb1d4c3ac1",
    "eb9a4740b712b149f08d5b430ae5907109eac3f231ce549a281703bc8e0965fb",
    "818eea0ab4e59102c589549d3ca487bf7c8a03e1e51644a126cba75a911e53de",
)

def need(ok, why):
    if not ok:
        raise RuntimeError("MRE_X410_FAIL_CLOSED " + why)

def digest(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def save(path, obj):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, sort_keys=True, indent=2) + "\n")

def parse(path):
    nv = declared = None
    clauses, clause = [], []
    for line in pathlib.Path(path).read_text().splitlines():
        parts = line.split()
        if not parts or parts[0] == "c":
            continue
        if parts[0] == "%":
            break
        if parts[0] == "p":
            need(nv is None and len(parts) == 4 and parts[1] == "cnf", "header")
            nv, declared = map(int, parts[2:])
            continue
        need(nv is not None, "literal before header")
        for token in parts:
            lit = int(token)
            if lit:
                need(abs(lit) <= nv, "literal range")
                clause.append(lit)
            else:
                clauses.append(tuple(clause))
                clause = []
    need(nv is not None and not clause and len(clauses) == declared, "DIMACS count")
    return nv, clauses

def write(path, nv, clauses):
    pathlib.Path(path).write_text("p cnf %d %d\n" % (nv, len(clauses)) +
        "".join(" ".join(map(str, c)) + " 0\n" for c in clauses))

def permutation(clauses, shifted=False):
    # Exact X3 spread100 / X4 spread_shifted, retaining literal order and copies.
    seen, unique, copies = set(), [], []
    for clause in clauses:
        key = tuple(sorted(set(clause)))
        (copies if key in seen else unique).append(clause)
        seen.add(key)
    if not copies:
        return list(clauses)
    offset = max(1, len(unique) // (2 * (len(copies) + 1))) if shifted else 0
    buckets = [[] for _ in range(len(unique) + 1)]
    for i, clause in enumerate(copies):
        gap = min(len(unique), (i + 1) * (len(unique) + 1) // (len(copies) + 1) + offset)
        buckets[gap].append(clause)
    result = []
    for i in range(len(unique) + 1):
        result.extend(buckets[i])
        if i < len(unique):
            result.append(unique[i])
    need(collections.Counter(result) == collections.Counter(clauses), "X4 multiset")
    return result

def backend(arm):
    return "cpp_joint" if arm in ("joint", "spread100_joint", "shifted_joint") else (
        "cpp_ref_6f" if arm == "ref6f" else "cpp_native")

def emitted(binary, src, arm, dst):
    p = subprocess.run([str(pathlib.Path(binary).resolve()), "--emit",
        str(src), arm, str(dst)], capture_output=True, text=True, timeout=30)
    need(p.returncode == 0, "emit failed: " + p.stderr[-500:])
    return parse(dst)

def satisfiable(nv, clauses):
    return any(all(any(bool(bits & (1 << (abs(lit) - 1))) == (lit > 0)
                       for lit in c) for c in clauses) for bits in range(1 << nv))

def parity_source(src, work):
    nv, clauses = parse(src)
    for arm in ARMS:
        ordered = permutation(clauses, arm.startswith("shifted")) if (
            arm.startswith(("spread100", "shifted"))) else clauses
        write(work / "ordered.cnf", nv, ordered)
        expected = emitted(REF_EMIT, work / "ordered.cnf", backend(arm), work / "ref.cnf")
        actual = emitted(EMIT, src, arm, work / "actual.cnf")
        need(actual == expected, "native X4->MRE10 clause parity: " + arm)
        if arm in ("spread100", "shifted"):
            need(collections.Counter(actual[1]) == collections.Counter(clauses), "copies lost")
        if nv <= 6:
            need(satisfiable(nv, clauses) == satisfiable(*actual), "Boolean truth changed")
    return len(ARMS)

def selftest():
    rng = random.Random(20261109410)
    tests = [(4, [(1, -2), (1, -2), (-1, 2), (1, 3), (1, 3), (4,)]),
             (3, [(1,), (-1,), (1,), (-2, 3), (-2, 3)]),
             (4, [(1, 2), (-1, 3), (2, 3), (1, 2), (4, -4)]),
             (3, [(-1, 2), (1, -2), (-2, 3), (2, -3), (1, 3), (1, 3)])]
    for _ in range(40):
        nv = rng.randrange(2, 7)
        clauses = [tuple(rng.choice((-1, 1)) * rng.randrange(1, nv + 1)
                         for _ in range(rng.randrange(1, 5))) for _ in range(12)]
        clauses += clauses[:4]
        tests.append((nv, clauses))
    with tempfile.TemporaryDirectory() as td:
        work = pathlib.Path(td)
        for nv, clauses in tests:
            write(work / "tiny.cnf", nv, clauses)
            parity_source(work / "tiny.cnf", work)
    print("MRE_X410_SELFTEST_PASS", len(tests), len(ARMS), flush=True)

def freeze():
    a = json.loads(pathlib.Path("mre7_easy/manifest.json").read_text())
    b = json.loads(pathlib.Path("mre_x/manifest.json").read_text())
    need(len(a["cases"]) == 16 and len(b["cases"]) == 13, "parent source count drift")
    chosen = {}
    for group, root, arr in (
            ("MRE10", pathlib.Path("mre7_easy"), a["cases"]),
            ("X4", pathlib.Path("mre_x"), [c for c in b["cases"] if c["sha256"] in X4_SHA])):
        need(group != "X4" or len(arr) == 4, "X4 exact four sources missing")
        for case in arr:
            src = root / case["filename"]
            need(digest(src) == case["sha256"], "parent SHA drift")
            status = case.get("reference_screen_status", case.get("reference_status"))
            need(status in ("SAT", "UNSAT"), "unknown parent status")
            if case["sha256"] in chosen:
                item = chosen[case["sha256"]]
                need(item["reference_status"] == status, "parent status contradiction")
                item["cohorts"].append(group)
                continue
            dst = OUT / "sources" / (case["sha256"] + ".cnf")
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())
            chosen[case["sha256"]] = dict(sha256=case["sha256"], gbd=case["gbd"],
                filename=str(dst), reference_status=status, cohorts=[group])
    cases = list(chosen.values())
    with tempfile.TemporaryDirectory() as td:
        for case in cases:
            parity_source(pathlib.Path(case["filename"]), pathlib.Path(td))
    hashes = {str(p): digest(p) for p in (BIN, EMIT, REF_EMIT,
        pathlib.Path("mre5/lib/libcryptominisat5.so.5.11"))}
    save(OUT / "manifest.json", dict(protocol=PROTO, cases=cases, cap_s=CAP,
         reps=REPS, arms=ARMS, binary_sha256=hashes, development_not_blind=True,
         exact_X4_order_and_MRE10_joint_parity_verified=True))
    print("MRE_X410_FREEZE_PASS", len(cases), len(cases) * REPS * len(ARMS), flush=True)

def manifest():
    q = json.loads((OUT / "manifest.json").read_text())
    need(q["protocol"] == PROTO and q["arms"] == list(ARMS) and
         q["cap_s"] == CAP and q["reps"] == REPS, "manifest drift")
    need(len({c["sha256"] for c in q["cases"]}) == len(q["cases"]), "duplicate source")
    for case in q["cases"]:
        need(digest(case["filename"]) == case["sha256"], "original SHA drift")
    for path, expected in q["binary_sha256"].items():
        need(digest(path) == expected, "binary or CMS library drift")
    return q

def seed(case, rep):
    # Match original X4 numeric seeds, even on the union's additional sources.
    raw = "DRNAS-MRE-X-C3-MRE11-13SHA-7ARMS-4SEED-12S-PAR2-v1|SEED|"
    return int(hashlib.sha256((raw + case["sha256"] + "|" + str(rep)).encode()).hexdigest()[:8], 16)

def verify_model(src, stdout):
    values = {}
    for line in stdout.splitlines():
        if line.startswith("v "):
            for token in line.split()[1:]:
                lit = int(token)
                if lit:
                    need(abs(lit) not in values or values[abs(lit)] == (lit > 0),
                         "contradictory witness")
                    values[abs(lit)] = lit > 0
    _, clauses = parse(src)
    need(all(any(abs(lit) in values and values[abs(lit)] == (lit > 0)
                 for lit in clause) for clause in clauses), "SAT witness on original")

MARKER = re.compile(r"^R195_RESULT status=(SAT|UNSAT|UNKNOWN|BUDGET) conflicts=(\d+) decisions=(\d+) propagations=(\d+) source_rows=0 derived_rows=0$", re.M)

def trial(case, rep, arm, position):
    env = {k: v for k, v in os.environ.items() if not k.startswith("DRNAS_")}
    start = time.perf_counter()
    cpu = resource.getrusage(resource.RUSAGE_CHILDREN)
    status, gate, ordering, stats, verified = "TIMEOUT", None, None, None, False
    try:
        p = subprocess.run([str(BIN.resolve()), str(pathlib.Path(case["filename"]).resolve()),
            arm, str(seed(case, rep))], capture_output=True, text=True,
            errors="replace", env=env, timeout=CAP)
    except subprocess.TimeoutExpired:
        p = None
    if p is not None:
        need(p.returncode == 0, "solver crash " + arm + ": " + p.stderr[-600:])
        markers = MARKER.findall(p.stdout)
        need(len(markers) == 1, "missing result")
        status, conflicts, decisions, propagations = markers[0]
        stats = dict(conflicts=int(conflicts), decisions=int(decisions), propagations=int(propagations))
        gates = [json.loads(l.split(" ", 1)[1]) for l in p.stdout.splitlines() if l.startswith("MRE10_GATE ")]
        orders = [json.loads(l.split(" ", 1)[1]) for l in p.stdout.splitlines() if l.startswith("MRE_X410_ORDER ")]
        need(len(gates) == len(orders) == 1 and gates[0]["mode"] == backend(arm)
             and orders[0]["arm"] == arm, "wrong native arm")
        gate, ordering = gates[0], orders[0]
        if status in ("SAT", "UNSAT"):
            need(status == case["reference_status"], "reference disagreement")
        if status == "SAT":
            verify_model(case["filename"], p.stdout)
            verified = True
    elapsed = time.perf_counter() - start
    usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu_s = usage.ru_utime + usage.ru_stime - cpu.ru_utime - cpu.ru_stime
    if status not in ("SAT", "UNSAT") or elapsed > CAP:
        status, verified = "TIMEOUT", False
    return dict(protocol=PROTO, sha256=case["sha256"], gbd=case["gbd"], rep=rep,
        seed=seed(case, rep), arm=arm, position=position, status=status,
        cap_s=CAP, elapsed_s=round(elapsed, 6), child_cpu_s=round(cpu_s, 6),
        PAR2_s=round(elapsed if status != "TIMEOUT" else 2 * CAP, 6),
        SAT_original_verified=verified, UNSAT_independent_LRAT=False,
        gate=gate, ordering=ordering, native=stats, binary_sha256=digest(BIN))

def smoke():
    with tempfile.TemporaryDirectory() as td:
        src = pathlib.Path(td) / "smoke.cnf"
        for status, clauses in (("SAT", [(-1, 2), (1, -2), (1, 3), (1, 3)]),
                                ("UNSAT", [(1,), (-1,), (1,)])):
            write(src, 3, clauses)
            case = dict(filename=str(src), sha256=digest(src), gbd="smoke",
                        reference_status=status)
            for arm in ARMS:
                row = trial(case, 0, arm, 0)
                need(row["status"] == status, "native smoke failed " + arm)
    print("MRE_X410_SMOKE_PASS 14 original-SAT-and-UNSAT", flush=True)

def shard(index):
    need(index in range(SHARDS), "invalid shard")
    cases = manifest()["cases"][index::SHARDS]
    rows = []
    for case in cases:
        for rep in range(REPS):
            order = list(ARMS)
            random.Random(PROTO + case["sha256"] + str(rep)).shuffle(order)
            for position, arm in enumerate(order):
                row = trial(case, rep, arm, position)
                rows.append(row)
                save(OUT / ("shard-%d.json" % index), rows)
                print("MRE_X410_TRIAL", json.dumps(row, sort_keys=True), flush=True)
    need(len(rows) == len(cases) * REPS * len(ARMS), "incomplete shard")
    print("MRE_X410_SHARD_PASS", index, len(rows), flush=True)

def audit():
    q = manifest()
    cases = {c["sha256"]: c for c in q["cases"]}
    rows, by_shard = [], {}
    for i in range(SHARDS):
        part = json.loads((OUT / ("shard-%d.json" % i)).read_text())
        expected_sha = {c["sha256"] for c in q["cases"][i::SHARDS]}
        need(all(r["sha256"] in expected_sha for r in part), "wrong shard")
        rows.extend(part)
        by_shard[str(i)] = part
    expected = set(itertools.product(cases, range(REPS), ARMS))
    actual = [(r["sha256"], r["rep"], r["arm"]) for r in rows]
    need(len(actual) == len(set(actual)) == len(expected) and set(actual) == expected, "paired completeness")
    for r in rows:
        c = cases[r["sha256"]]
        need(r["protocol"] == PROTO and r["seed"] == seed(c, r["rep"]) and
             r["binary_sha256"] == q["binary_sha256"][str(BIN)] and r["cap_s"] == CAP, "provenance")
        need(r["status"] in ("SAT", "UNSAT", "TIMEOUT"), "bad status")
        need(r["status"] == "TIMEOUT" or r["status"] == c["reference_status"], "wrong verdict")
        need(r["status"] != "SAT" or r["SAT_original_verified"], "unchecked SAT")
        need(abs(r["PAR2_s"] - (2 * CAP if r["status"] == "TIMEOUT" else r["elapsed_s"])) < 1e-5, "PAR2")
    def summary(group):
        out = {}
        for arm in ARMS:
            rr = [r for r in group if r["arm"] == arm]
            out[arm] = dict(attempts=len(rr), solved=sum(r["status"] != "TIMEOUT" for r in rr),
                PAR2_s=round(sum(r["PAR2_s"] for r in rr), 6),
                wall_s=round(sum(r["elapsed_s"] for r in rr), 6),
                child_cpu_s=round(sum(r["child_cpu_s"] for r in rr), 6),
                joint_applied=sum(bool((r["gate"] or {}).get("applied")) for r in rr))
        for val in out.values():
            val["speedup_vs_native_x"] = round(out["native"]["PAR2_s"] / val["PAR2_s"], 6)
        return out
    per_source = {c["gbd"]: summary([r for r in rows if r["sha256"] == s]) for s, c in cases.items()}
    report = dict(protocol=PROTO, source_count=len(cases), real_E2E_trials=len(rows),
        repetitions=REPS, cap_s=CAP, development_not_blind=True,
        UNSAT_independent_LRAT=False, no_auto_promotion=True,
        scores=summary(rows), by_shard={i: summary(rr) for i, rr in by_shard.items()},
        by_cohort={cohort: summary([r for r in rows if cohort in cases[r["sha256"]]["cohorts"]])
                   for cohort in ("X4", "MRE10")}, per_source=per_source)
    save(OUT / "report.json", report)
    print("MRE_X410_FINAL", json.dumps({k: v for k, v in report.items() if k != "per_source"}, sort_keys=True), flush=True)
    print("| Arm | PAR2 s | Solved | CPU s | Speedup vs native |")
    print("|---|---:|---:|---:|---:|")
    for arm, score in report["scores"].items():
        print("| %s | %.4f | %d/%d | %.3f | %.4fx |" % (arm, score["PAR2_s"],
              score["solved"], score["attempts"], score["child_cpu_s"], score["speedup_vs_native_x"]))

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("selftest", "smoke", "freeze", "verify", "shard", "audit"))
    parser.add_argument("--shard", type=int, default=0)
    args = parser.parse_args()
    if args.action == "selftest":
        selftest()
    elif args.action == "smoke":
        smoke()
    elif args.action == "freeze":
        freeze()
    elif args.action == "verify":
        print("MRE_X410_VERIFY_PASS", len(manifest()["cases"]), flush=True)
    elif args.action == "shard":
        shard(args.shard)
    else:
        audit()
