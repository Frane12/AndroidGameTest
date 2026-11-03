#!/usr/bin/env python3
"""R25 XOR/algebra starting-line cup: SHA-locked, paired, timeout-correct.

XOR: 24 newly salted mathematical GF(2) instances (12 SAT, 12 UNSAT).
Polynomial: 6 predeclared original Global Benchmark Database CNFs, previously
published/benchmarked (not an unseen holdout). Controls: 2 original 2025
competition CNFs. This is a competition-style SIMULATION, never a ranking.
"""
import argparse
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import random
import re
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict

PROTO = "DRNAS-R25-XOR-ALGEBRA-FROZEN-CUP-20261103-v1"
SOURCE_COMMIT = "3cd6525817f5019516b0addb94b4db5f57c7e9b1"
SALT = "DRNAS-R25-NEW-XOR-SALT-20261103-COMMITTED-BEFORE-MEASUREMENT"
POLY_INDICES = (1, 2, 3, 13, 14, 15)  # 3 SAT + 3 UNSAT, fixed before R25 timings
OFFICIAL_2025 = ("7a044c99-sum-of-3-cubes.cnf", "d9320e4d-modcircuits.cnf")
MODES = ("R25_adaptive", "DRNAS_V1531", "DRNAS_V78_guided", "CaDiCaL301", "Kissat404")
CAP, REPS, SHARDS = 15.0, 2, 4

def check(ok, message):
    if not ok:
        raise RuntimeError(message)

def digest(data):
    if isinstance(data, Path):
        data = data.read_bytes()
    return hashlib.sha256(data).hexdigest()

def save(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")

def module(name, file):
    spec = importlib.util.spec_from_file_location(name, str(file))
    item = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(item)
    return item

def xor_formula(i, prior):
    rng = random.Random(int(digest((SALT + "/" + str(i)).encode()), 16))
    vertices = (48, 54, 60, 66, 72, 78)[i % 6]
    edges = prior.graph(vertices, rng)
    incidents = [[] for _ in range(vertices)]
    for j, (u, v) in enumerate(edges, 1):
        incidents[u].append(j)
        incidents[v].append(j)
    check(all(len(x) == 3 for x in incidents), "Graph not cubic")
    witness = {j: bool(rng.getrandbits(1)) for j in range(1, len(edges)+1)}
    rhs = [sum(witness[j] for j in row) % 2 for row in incidents]
    unsat = i % 2 == 0
    if unsat:
        rhs[0] ^= 1
        check(sum(rhs) % 2 == 1 and len(edges)*2 == 3*vertices,
              "Invalid parity cancellation certificate")
    clauses = []
    for inc, parity in zip(incidents, rhs):
        for mask in range(8):
            values = [bool(mask >> j & 1) for j in range(3)]
            if sum(values) % 2 == parity:
                continue
            clauses.append(tuple(-v if val else v for v, val in zip(inc, values)))
    if not unsat:
        check(prior.valid(clauses, witness), "Planted SAT witness invalid")
    return prior.dimacs(len(edges), clauses), "UNSAT" if unsat else "SAT", vertices

def prepare(a):
    root = Path(a.outdir)
    root.mkdir(parents=True, exist_ok=True)
    pinned = Path(a.pinned)
    family = json.loads((pinned/"frozen_verified_gbd_family.json").read_text())
    competition = json.loads((pinned/"frozen_competition_v78.json").read_text())
    check(family["source"] == "Global Benchmark Database / benchmark-database.de",
          "Wrong archived source")
    check(family["samples"][11]["name"] == "mp1-Nb7T46.cnf.xz",
          "Historical source manifest changed")
    sys.path.insert(0, str(Path("research/drnas-sat-v7-8").resolve()))
    import v134_constructive as prior
    preflight = module("r25_gbd_preflight", pinned/"preflight.py")
    rows = []
    for i in range(24):
        raw, label, vertices = xor_formula(i, prior)
        filename = f"xor_{i:02d}.cnf"
        (root/filename).write_bytes(raw)
        rows.append(dict(id=filename, path=filename, family="xor_gf2_new",
                         status=label, sha256=digest(raw), source="R25 frozen synthetic",
                         vertices=vertices, bytes=len(raw), previously_measured=False))
    for i in POLY_INDICES:
        entry = family["samples"][i]
        check(entry["group"] == "holdout" and
              entry["source_validation"]["validation"] == "sha256_verified",
              "Invalid polynomial source selection")
        raw, _ = preflight.download(entry, family)
        freeze = entry["source_validation"]
        check(digest(raw) == freeze["sha256"] and len(raw) == freeze["bytes"],
              "Original GBD SHA mismatch " + entry["name"])
        filename = f"poly_{i:02d}.cnf"
        (root/filename).write_bytes(raw)
        rows.append(dict(id=entry["name"], path=filename,
                         family="polynomial_gbd_original", status=entry["status"],
                         sha256=digest(raw), source=entry["url"], bytes=len(raw),
                         previously_measured=True))
    all_originals = competition["pilot"] + competition["holdout"]
    for name in OFFICIAL_2025:
        entry = next((x for x in all_originals if x["name"] == name), None)
        check(entry is not None, "Missing 2025 original " + name)
        row = dict(hash=name.split("-")[0], name=name, group="competition_control",
                   author="SATCompetition2025", status=entry["status"],
                   url=entry["url"])
        raw, _ = preflight.download(row, dict(max_compressed_bytes=25000000,
                                               max_plain_bytes=100000000))
        check(digest(raw) == entry["sha256"] and len(raw) == entry["bytes"],
              "Original 2025 SHA mismatch " + name)
        filename = f"control_{name}"
        (root/filename).write_bytes(raw)
        rows.append(dict(id=name, path=filename, family="official_2025_algebra_control",
                         status=entry["status"], sha256=digest(raw),
                         source=entry["url"], bytes=len(raw),
                         previously_measured=True))
    check(len(rows) == 32 and len({x["sha256"] for x in rows}) == 32,
          "Expected 32 distinct source inputs")
    manifest = dict(protocol=PROTO, prior_source_commit=SOURCE_COMMIT,
                    xor_salt=SALT, polynomial_indices=list(POLY_INDICES),
                    official_2025_names=list(OFFICIAL_2025),
                    cutoff_s=CAP, repeats=REPS, shards=SHARDS,
                    modes=MODES, notes=[
                        "24 new synthetic GF(2) cases, with independent SAT witness / parity proof",
                        "6 original GBD polynomial CNFs previously known; not blind",
                        "2 original 2025 competition control CNFs; not blind",
                        "R25 selector uses only formula bytes, not metadata/labels/filenames",
                        "Same hardware per paired case, process-level time including startup",
                        "This is a 15s local competition-style benchmark, not official SAT Competition scoring",
                    ], cases=rows)
    save(root/"manifest.json", manifest)
    print("R25_FROZEN_MANIFEST", len(rows), digest(root/"manifest.json"), flush=True)
    for x in rows:
        print("R25_FROZEN_CASE", x["family"], x["id"], x["status"],
              x["sha256"], flush=True)

def parse(text, exitcode):
    route = "unreported"
    payload = None
    status = "UNKNOWN"
    for line in text.splitlines():
        if line.startswith("DRNAS_R25_ROUTE\t"):
            route = line.split("\t")[1]
        elif line.startswith("DRNAS_HYBRID_RESULT\t"):
            payload = json.loads(line.split("\t", 1)[1])
            status = payload.get("status", "UNKNOWN")
            route = route if route != "unreported" else payload.get("path", "v1531")
        elif line.startswith("DRNAS_RESULT\t"):
            v = line.split("\t")
            status = v[2]
            if route == "unreported":
                route = "cadical_v78_" + v[1]
        elif line.startswith("s SATISFIABLE"):
            status = "SAT"
        elif line.startswith("s UNSATISFIABLE"):
            status = "UNSAT"
    if status == "UNKNOWN" and exitcode in (10, 20):
        status = "SAT" if exitcode == 10 else "UNSAT"
    return status, route, payload

def clauses_for_proof(path):
    clauses = []
    buf = []
    with open(path, "r", errors="replace") as f:
        for line in f:
            if not line.strip() or line.lstrip().startswith(("c", "p", "%")):
                continue
            for t in line.split():
                v = int(t)
                if not v:
                    clauses.append(tuple(buf))
                    buf = []
                else:
                    buf.append(v)
    check(not buf, "Nonterminated DIMACS")
    return clauses

def attempt(mode, case, a, seed, cap):
    src = Path(a.inputs).resolve()/case["path"]
    binary = Path(a.bin).resolve()
    if mode == "R25_adaptive":
        cmd = [sys.executable, str(Path(__file__).parent/"r25_xor_algebra_selector.py"),
               str(src), "--kissat", str(binary/"kissat_solver"),
               "--v1531", str(binary/"v1531_nohang"),
               "--v78", str(binary/"v78_single"), "--seed", str(seed)]
    elif mode == "DRNAS_V1531":
        cmd = [str(binary/"v1531_nohang"), str(src),
               str(binary/"kissat_solver"), str(seed)]
    elif mode == "DRNAS_V78_guided":
        cmd = [str(binary/"v78_single"), "quality_guided", str(src), str(seed)]
    elif mode == "CaDiCaL301":
        cmd = [str(binary/"cadical_solver"), str(src)]
    else:
        cmd = [str(binary/"kissat_solver"), str(src)]
    started = time.monotonic()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                errors="replace", timeout=cap, check=False)
        seconds = time.monotonic() - started
        status, route, payload = parse(result.stdout, result.returncode)
        verified = status == case["status"]
        proof = None
        if payload and status == "UNSAT":
            # Independent proof checker on original formula, not native flag.
            sys.path.insert(0, str(Path("research/tseitin-replay").resolve()))
            from v153_proof_checker import verify_certificate
            proof = bool(verify_certificate(payload, clauses_for_proof(src)))
            verified = verified and proof
        elif payload and status == "SAT" and isinstance(payload.get("model"), list):
            model = {abs(v): v > 0 for v in payload["model"]}
            proof = all(any(model.get(abs(v)) == (v > 0) for v in cl)
                        for cl in clauses_for_proof(src))
            verified = verified and proof
        if status not in ("SAT", "UNSAT") or not verified:
            print("R25_INVALID_OR_ERROR", case["id"], mode, status,
                  result.returncode, result.stderr[-250:], flush=True)
        return dict(status=status, seconds=round(seconds, 6), route=route,
                    correct=verified, proof_valid=proof, exit=result.returncode,
                    stderr=result.stderr[-250:])
    except subprocess.TimeoutExpired:
        return dict(status="TIMEOUT", seconds=cap, route="timeout",
                    correct=False, proof_valid=None, exit=-1, stderr="")

def benchmark(a):
    inputs = Path(a.inputs).resolve()
    data = json.loads((inputs/"manifest.json").read_text())
    check(data["protocol"] == PROTO and data["modes"] == list(MODES)
          and data["cutoff_s"] == CAP and data["repeats"] == REPS,
          "Frozen protocol mismatch")
    check(0 <= a.shard < SHARDS, "Bad shard")
    allowed = os.sched_getaffinity(0)
    os.sched_setaffinity(0, {min(allowed)})
    chosen = data["cases"][a.shard::SHARDS]
    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)
    save(out/"metadata.json", dict(shard=a.shard, manifest_sha256=digest(inputs/"manifest.json"),
                                  protocol=PROTO, modes=MODES, cap=a.timeout,
                                  repetitions=a.repeats,
                                  cpu_model=next((l.split(":",1)[1].strip()
                                    for l in Path("/proc/cpuinfo").read_text().splitlines()
                                    if l.startswith("model name")), "unknown"),
                                  binaries={x:digest(Path(a.bin)/x) for x in
                                  ("v1531_nohang","v78_single","kissat_solver","cadical_solver")}))
    rows = []
    for case in chosen:
        check(digest(inputs/case["path"]) == case["sha256"],
              "Input SHA changed: "+case["id"])
        trials = []
        for rep in range(a.repeats):
            seed = 25031103 + int(case["sha256"][:7], 16) + rep*4099
            modes = list(MODES)
            random.Random(seed).shuffle(modes)
            for mode in modes:
                v = attempt(mode, case, a, seed, a.timeout)
                trials.append(dict(mode=mode, repeat=rep, **v))
                print("R25_TRIAL", case["id"], mode, rep, v["status"],
                      v["seconds"], v["route"], flush=True)
                check(v["status"] == "TIMEOUT" or v["correct"],
                      "Wrong SAT/UNSAT or invalid proof " + repr(v))
        rows.append(dict(case=case, trials=trials))
        save(out/"rows.json", rows)
    print("R25_SHARD_DONE", a.shard, len(rows), flush=True)

def aggregate(a):
    inputs = Path(a.inputs)
    spec = json.loads((inputs/"manifest.json").read_text())
    all_rows = []
    for shard in range(SHARDS):
        folder = Path(a.combined)/f"r25-shard-{shard}"
        meta = json.loads((folder/"metadata.json").read_text())
        check(meta["shard"] == shard and
              meta["manifest_sha256"] == digest(inputs/"manifest.json"),
              "Wrong shard provenance")
        part = json.loads((folder/"rows.json").read_text())
        check([r["case"]["sha256"] for r in part] ==
              [r["sha256"] for r in spec["cases"][shard::SHARDS]],
              "Incomplete or shifted shard")
        all_rows.extend(part)
    check(len(all_rows) == 32, "Incomplete benchmark")
    report = {}
    for family in ["ALL", "xor_gf2_new", "polynomial_gbd_original",
                   "official_2025_algebra_control"]:
        group = [r for r in all_rows if family == "ALL" or r["case"]["family"] == family]
        stats = {}
        for mode in MODES:
            par2, solved, medians = [], 0, []
            for r in group:
                trials = [x for x in r["trials"] if x["mode"] == mode]
                check(len(trials) == REPS, "Missing repeated trial")
                vals = [x["seconds"] if x["status"] != "TIMEOUT" else 2*CAP
                        for x in trials]
                medians.append(statistics.median(vals))
                par2.extend(vals)
                solved += int(all(x["correct"] for x in trials))
            stats[mode] = dict(solved_cases=solved, n_cases=len(group),
                               sum_median_PAR2_s=round(sum(medians), 6),
                               median_case_PAR2_s=round(statistics.median(medians), 6),
                               mean_attempt_PAR2_s=round(statistics.mean(par2), 6),
                               timed_out_attempts=sum(x["status"]=="TIMEOUT"
                                   for r in group for x in r["trials"] if x["mode"]==mode))
        stats["ratio_Kissat_over_R25"] = round(
            stats["Kissat404"]["sum_median_PAR2_s"] /
            max(stats["R25_adaptive"]["sum_median_PAR2_s"], 1e-9), 4)
        report[family] = stats
    output = dict(protocol=PROTO, original_manifest_sha256=digest(inputs/"manifest.json"),
                  subsets=report, rows=all_rows,
                  limitations=["Competition-style local 15 s cutoff, NOT world ranking",
                               "XOR family is new salt but structure known to developers",
                               "GBD polynomial formulas are previous public inputs, NOT blind",
                               "Timeouts PAR2 = 30 s, retained in all sums"])
    save(a.out, output)
    md = ["# DRNAS SAT R25 — XOR / polynomial starting-line cup",
          "Frozen SHA-256; two paired attempts per input; 15s cap, PAR2=30s.",
          "New-salt XOR, previously known GBD polynomial, real 2025 controls.",
          "**Simulation, not official SAT Competition scoring or blind benchmark.**", ""]
    for family, stat in report.items():
        md.extend([f"## {family}",
                   "| Solver | Solved cases | Sum PAR2 of medians (s) | Timeouts (attempts) |",
                   "|---|---:|---:|---:|"])
        for mode in MODES:
            x=stat[mode]
            md.append(f"| {mode} | {x['solved_cases']}/{x['n_cases']} | {x['sum_median_PAR2_s']:.6f} | {x['timed_out_attempts']} |")
        md.extend([f"**Kissat / R25 = {stat['ratio_Kissat_over_R25']}×**", ""])
    Path(a.md).write_text("\n".join(md)+"\n")
    print("\n".join(md), flush=True)

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="command",required=True)
    v=sub.add_parser("prepare")
    v.add_argument("--pinned",required=True)
    v.add_argument("--outdir",required=True)
    v=sub.add_parser("run")
    for opt in ("inputs","outdir","bin"):
        v.add_argument("--"+opt,required=True)
    v.add_argument("--shard",type=int,required=True)
    v.add_argument("--timeout",type=float,default=CAP)
    v.add_argument("--repeats",type=int,default=REPS)
    v=sub.add_parser("aggregate")
    for opt in ("inputs","combined","out","md"):
        v.add_argument("--"+opt,required=True)
    a=p.parse_args()
    if a.command=="prepare":prepare(a)
    elif a.command=="run":benchmark(a)
    else:aggregate(a)
if __name__=="__main__":
    main()
