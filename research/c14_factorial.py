#!/usr/bin/env python3
"""C14 development-only BVE/vivify factorial on pinned C13 sources and binaries."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import pathlib
import random
import re
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import c13_ablation as helpers

PROTOCOL = "DRNAS-C14-DEV3-FACTORIAL6-3REPS-30S-v1"
CAP = 30.0
REPS = 3
OUT = pathlib.Path("c14_out")
ARMS = ("matched_default", "skip_bve", "no_vivify", "skip_bve_no_vivify",
        "legacy_noelim", "upstream_default")
# All are development cases; this is a causal diagnostic, not a new holdout.
SOURCES = (
    ("3ed56242f55e3653dbceeb4a70221787", "4a3dde8588b06f42b73b96ba1e610a4b23d8cd239d44d17981c0638911c77aee", "SAT"),
    ("5de866bc7ff4dfde3cd682b5aca75894", "dc3a17e19c6d2c076ed475b7dc342bb1474033bfd4d96f69a217f0e0e282ceac", "SAT"),
    ("bf8c8761003704e761ce36db6665f741", "e90397dabd4bf5e868edb9e8fe070d7d7de350a63ea70f6467e767fdf2f4f607", "UNSAT"),
)
BINARY = pathlib.Path("c8c/bin/instrumented")
UPSTREAM = pathlib.Path("c8c/bin/plain")

def need(ok, message):
    if not ok:
        raise RuntimeError("C14_FAIL_CLOSED " + message)

def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")

def sources():
    manifest = json.loads(pathlib.Path("c13_sources/manifest.json").read_text())
    result = []
    for gbd, sha, status in SOURCES:
        choices = [x for x in manifest["cases"] if x["gbd"] == gbd and x["sha256"] == sha]
        need(len(choices) == 1, "source not present in pinned C13 manifest")
        x = choices[0]
        need(x["status"] == status, "reference status drift")
        path = pathlib.Path("c13_sources") / x["filename"]
        need(helpers.digest(path) == sha, "original SHA mismatch")
        result.append(x)
    return result

def command(arm, path):
    need(arm in ARMS, "unknown arm")
    binary = UPSTREAM if arm == "upstream_default" else BINARY
    options = []
    if arm in ("no_vivify", "skip_bve_no_vivify"):
        options.append("--no-vivify")
    if arm == "legacy_noelim":
        options.append("--no-elim")
    env = os.environ.copy()
    for key in list(env):
        if key.startswith(("DRNAS_C8", "DRNAS_C14")):
            env.pop(key)
    if arm in ("skip_bve", "skip_bve_no_vivify"):
        env["DRNAS_C8C_SKIP_ALL_BVE"] = "1"
    return [str(binary.resolve()), *options, str(path.resolve())], env, binary

def smoke():
    OUT.mkdir(exist_ok=True)
    path = OUT / "smoke.cnf"
    path.write_text("p cnf 2 2\n1 2 0\n-1 2 0\n")
    for arm in ARMS:
        cmd, env, binary = command(arm, path)
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=5)
        need(proc.returncode == 10, "unsupported option or smoke failure: " + arm)
        state, model = helpers.ref.external_parse(proc)
        need(state == "SAT", "smoke status parse failed")
        helpers.cms.verify_model(path, model)
    print("C14_SMOKE_PASS", flush=True)

def stats_lines(text):
    # Native final stats, not a guessed estimate. A killed run may have no final stats.
    keys = re.compile(r"conflicts|decisions|propagations|eliminat|vivif|learn|literal|process time|seconds", re.I)
    lines = [line for line in text.splitlines() if line.startswith("c ") and keys.search(line)]
    return lines[-50:]

def trial(x, arm, rep, position, order_seed):
    path = pathlib.Path("c13_sources") / x["filename"]
    need(helpers.digest(path) == x["sha256"], "source changed before trial")
    cmd, env, binary = command(arm, path)
    started = time.perf_counter()
    killed = False
    try:
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True,
                              errors="replace", timeout=CAP)
        stdout, stderr = proc.stdout, proc.stderr
        elapsed = time.perf_counter() - started
        need(proc.returncode in (10, 20), "unexpected solver exit " + str(proc.returncode))
        state, model = helpers.ref.external_parse(proc)
        need(state in ("SAT", "UNSAT"), "missing solver result")
        need(state == x["status"], "result contradicts published reference")
        verified = False
        if state == "SAT":
            helpers.cms.verify_model(path, model)
            verified = True
        if elapsed > CAP:
            state = "TIMEOUT"
    except subprocess.TimeoutExpired as exc:
        elapsed = time.perf_counter() - started
        def decoded(value):
            return value.decode(errors="replace") if isinstance(value, bytes) else (value or "")
        stdout, stderr = decoded(exc.stdout), decoded(exc.stderr)
        state, verified, killed = "TIMEOUT", False, True
    return dict(protocol=PROTOCOL, development_only=True, global_blind_claim=False,
                source_sha256=x["sha256"], gbd=x["gbd"], reference=x["status"],
                arm=arm, rep=rep, order_position=position, order_seed=order_seed,
                status=state, SAT_original_witness_verified=verified,
                UNSAT_published_agreement=state == "UNSAT", UNSAT_independent_LRAT=False,
                cap_s=CAP, PAR2_s=round(elapsed if state != "TIMEOUT" else 2 * CAP, 6),
                wall_s=round(elapsed, 6), subprocess_killed=killed,
                timing_excludes_model_check=True, no_probe_restart=True,
                solver_seed_changed=False, binary_sha256=helpers.digest(binary),
                native_stats=stats_lines(stdout), stderr_tail=stderr[-1000:],
                commit_sha=os.environ.get("GITHUB_SHA", "local"))

def shard(index):
    cases = sources()
    need(index in range(len(cases)), "bad shard index")
    x = cases[index]
    rows = []
    OUT.mkdir(exist_ok=True)
    for rep in range(REPS):
        order_seed = int(hashlib.sha256((PROTOCOL + x["sha256"] + str(rep)).encode()).hexdigest()[:8], 16)
        order = list(ARMS)
        random.Random(order_seed).shuffle(order)
        for position, arm in enumerate(order):
            row = trial(x, arm, rep, position, order_seed)
            rows.append(row)
            save(OUT / ("shard-%d.json" % index), rows)
            print("C14_TRIAL " + json.dumps(row, sort_keys=True), flush=True)
    need(len(rows) == REPS * len(ARMS), "incomplete shard")
    print("C14_SHARD_PASS %d %d" % (index, len(rows)), flush=True)

def audit():
    cases = sources()
    rows = []
    for i in range(len(cases)):
        part = json.loads((OUT / ("shard-%d.json" % i)).read_text())
        need(len(part) == REPS * len(ARMS), "missing trial")
        need(all(x["source_sha256"] == cases[i]["sha256"] for x in part), "shard source mix")
        rows.extend(part)
    expected = {(x["sha256"], a, rep) for x in cases for a in ARMS for rep in range(REPS)}
    keys = [(r["source_sha256"], r["arm"], r["rep"]) for r in rows]
    need(len(keys) == len(set(keys)) == len(expected) and set(keys) == expected, "paired keys mismatch")
    matched = {r["binary_sha256"] for r in rows if r["arm"] != "upstream_default"}
    need(len(matched) == 1, "factorial arms do not share the exact same binary")
    for r in rows:
        need(r["cap_s"] == CAP and r["protocol"] == PROTOCOL, "protocol drift")
        need(r["status"] in ("TIMEOUT", "SAT", "UNSAT"), "invalid status")
        if r["status"] == "TIMEOUT":
            need(r["PAR2_s"] == 2 * CAP, "bad timeout penalty")
        else:
            need(r["status"] == next(x["status"] for x in cases if x["sha256"] == r["source_sha256"]), "reference mismatch")
            need(r["PAR2_s"] == r["wall_s"], "bad solved score")
            if r["status"] == "SAT":
                need(r["SAT_original_witness_verified"], "missing model verification")
    def scores(group):
        return {a: dict(attempts=len([r for r in group if r["arm"] == a]),
                        solved=sum(r["status"] != "TIMEOUT" for r in group if r["arm"] == a),
                        PAR2_s=round(sum(r["PAR2_s"] for r in group if r["arm"] == a), 6))
                for a in ARMS}
    per_case = {x["gbd"]: scores([r for r in rows if r["gbd"] == x["gbd"]]) for x in cases}
    report = dict(protocol=PROTOCOL, full_trials=len(rows), development_only=True,
                  independent_solver_seeds=False, independent_UNSAT_LRAT=False,
                  matched_binary_sha256=next(iter(matched)), scores=scores(rows),
                  per_case=per_case, adaptive_policy_implemented=False,
                  note="skip-BVE retains the elimination schedule; legacy no-elim also alters other simplification.")
    save(OUT / "report.json", report)
    print("C14_FINAL " + json.dumps(report, sort_keys=True), flush=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("smoke", "shard", "audit"))
    parser.add_argument("--shard", type=int, default=0)
    args = parser.parse_args()
    if args.action == "smoke":
        smoke()
    elif args.action == "shard":
        shard(args.shard)
    else:
        audit()
