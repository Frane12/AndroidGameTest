#!/usr/bin/env python3
"""Reduced-budget, unofficial SAT2026 comparison. Never an official ranking.

The TA3 decision and R28 implementation are unchanged. All 24 sources from the
already frozen TA3-2026 cohort are used, without consulting its trial outcomes.
Generic UNSAT is consistency-checked, not independently certificate-checked.
The official entrant uses its submitted wrapper, including its proof policy;
that policy is recorded rather than silently claiming identical proof settings.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import random
import re
import signal
import statistics
import subprocess
import sys
import tempfile
import time

ROOT = Path("worldsim_w1")
SOURCE = Path("ta3_2026/sources")
PROTO = "DRNAS-WORLDSIM-W1-SAT2026-24x6x3-60s-v1"
CAP = 60.0
REPS = 3
SHARDS = 8
MODES = ("ta3_portfolio", "r28_kissat", "kissat_404", "cms_51115",
         "cadical_301", "satsuma_iter_kissat_2026")
THREAD_ENV = {k: "1" for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                              "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS")}

def need(ok, msg):
    if not ok:
        raise RuntimeError("W1_FAIL_CLOSED " + str(msg))

def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")

def parse_answer(raw, rc):
    answers = set(re.findall(r"^s\s+(SATISFIABLE|UNSATISFIABLE)\s*$", raw, re.M))
    need(len(answers) == 1, "missing/contradictory result line")
    answer = answers.pop()
    status = "SAT" if answer == "SATISFIABLE" else "UNSAT"
    need(rc in (0, 10 if status == "SAT" else 20), "exit/result mismatch")
    model = {}
    for line in raw.splitlines():
        if line.startswith("v "):
            for value in map(int, line.split()[1:]):
                if value:
                    need(abs(value) not in model or model[abs(value)] == (value > 0),
                         "contradictory SAT assignment")
                    model[abs(value)] = value > 0
    return status, model

def verify_model(path, model):
    clause = []
    declared = seen = variables = None
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith(("c", "%")):
            continue
        if line.startswith("p "):
            _, kind, variables, declared = line.split()
            need(kind == "cnf", "not CNF")
            variables, declared, seen = int(variables), int(declared), 0
            continue
        need(declared is not None, "missing DIMACS header")
        for value in map(int, line.split()):
            if value:
                need(abs(value) <= variables, "literal outside DIMACS range")
                clause.append(value)
            else:
                need(any(abs(v) in model and model[abs(v)] == (v > 0) for v in clause),
                     "SAT witness fails original CNF")
                seen += 1
                clause = []
    need(declared is not None and seen == declared and not clause,
         "DIMACS clause count mismatch")

def timed_process(command, started, *, cwd=None, env=None, cap=CAP):
    remaining = cap - (time.perf_counter() - started)
    if remaining <= 0:
        return None, "", True
    process = subprocess.Popen([str(x) for x in command], cwd=cwd,
        env={**os.environ, **THREAD_ENV, **(env or {})},
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        stdout, _ = process.communicate(timeout=remaining)
        return process.returncode, stdout.decode("utf-8", errors="replace"), False
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        stdout, _ = process.communicate()
        return process.returncode, stdout.decode("utf-8", errors="replace"), True

def selector():
    import drnas_ta3_adaptive_selector as ta3
    return ta3

def command_for(mode, source, proofdir):
    source = source.resolve()
    if mode == "kissat_404":
        return [Path("built/bin/kissat_4_0_4").resolve(), source], None
    if mode == "cadical_301":
        return [Path("worldsim_w1/reference/bin/cadical_3_0_1").resolve(), source], None
    if mode == "cms_51115":
        return ["/usr/bin/cryptominisat5", "--threads=1", source], None
    if mode == "satsuma_iter_kissat_2026":
        meta = json.loads((ROOT / "official.json").read_text())
        script = Path(meta["run_script"]).resolve()
        return ["bash", script, source, proofdir.resolve()], script.parent
    if mode == "r28_kissat":
        return selector().command("kissat_r28", source), None
    raise ValueError(mode)

def trial(case, mode, rep, shard, *, cap=CAP, emit=True):
    source = SOURCE / (case["id"] + ".cnf")
    need(digest(source) == case["sha256"], "source changed before trial")
    proofdir = ROOT / "raw" / str(shard) / case["id"] / str(rep) / mode
    proofdir.mkdir(parents=True, exist_ok=True)
    selected, reason, profile_s = mode, "fixed", 0.0
    started = time.perf_counter()
    if mode == "ta3_portfolio":
        ta3 = selector()
        features = ta3.fast_features(source)
        selected, reason = ta3.decision(features, "ta2_portfolio")
        profile_s = time.perf_counter() - started
        command, cwd = ta3.command(selected, source), None
    else:
        command, cwd = command_for(mode, source, proofdir)
    rc, raw, timeout = timed_process(command, started, cwd=cwd, cap=cap)
    elapsed = min(cap, time.perf_counter() - started)
    status, evidence = "TIMEOUT", "CAP_TIMEOUT"
    if not timeout and elapsed < cap:
        status, model = parse_answer(raw, rc)
        if status == "SAT":
            verify_model(source, model)
            evidence = "SAT_MODEL_ORIGINAL_CNF_VERIFIED"
        else:
            evidence = "UNSAT_REPORTED_NO_INDEPENDENT_CERTIFICATE"
        if case.get("expected", "UNKNOWN") != "UNKNOWN":
            need(status == case["expected"], "known verdict mismatch")
    (proofdir / "stdout.log").write_text(raw)
    proof_bytes = sum(p.stat().st_size for p in proofdir.rglob("*")
                      if p.is_file() and p.name != "stdout.log")
    row = dict(protocol=PROTO, id=case["id"], sha256=case["sha256"],
        mode=mode, selected=selected, routing_reason=reason, rep=rep, shard=shard,
        status=status, elapsed_s=round(elapsed, 6),
        par2_s=round(2 * cap if status == "TIMEOUT" else elapsed, 6),
        profile_s=round(profile_s, 6), evidence=evidence,
        submitted_wrapper_proof_bytes=proof_bytes,
        stdout_sha256=hashlib.sha256(raw.encode()).hexdigest(),
        command=[str(x) for x in command])
    if emit:
        print("W1_TRIAL", json.dumps(row, sort_keys=True), flush=True)
    return row

def freeze():
    import ast
    # Enforce exactly the source-only TA3 method already selected on SAT2025.
    old = ast.parse(Path("research/drnas_ta3_adaptive_selector.py").read_text())
    new = ast.parse(Path("research/drnas_ta3_2026_portfolio.py").read_text())
    for name in ("fast_features", "decision", "command"):
        a = next(n for n in old.body if isinstance(n, ast.FunctionDef) and n.name == name)
        b = next(n for n in new.body if isinstance(n, ast.FunctionDef) and n.name == name)
        need(ast.dump(a) == ast.dump(b), "TA3 method changed " + name)
    original = json.loads(Path("ta3_2026/manifest.json").read_text())
    cases = original["cases"]
    need(len(cases) == len({c["sha256"] for c in cases}) == 24, "not 24 originals")
    for filename, expected in json.loads(Path("ta3_2026/pins.json").read_text()).items():
        need(digest(filename) == expected, "TA326 original pin drift " + filename)
    for case in cases:
        need(digest(SOURCE / (case["id"] + ".cnf")) == case["sha256"], "source drift")
    save(ROOT / "manifest.json", dict(protocol=PROTO,
        cases=sorted(cases, key=lambda c: c["sha256"]), modes=MODES,
        repetitions=REPS, cap_s=CAP, shards=SHARDS, expected_trials=432,
        source_manifest_sha256=digest("ta3_2026/manifest.json"),
        source_run=42396350093, method_selection_run=42393279231,
        source_selection="all 24 already frozen official SAT2026 cohort; no trial filtering",
        new_global_blind_holdout=False,
        tuning_on_TA326_outcomes=False, official_competition_ranking=False,
        verification_off_timing_for_all_modes=True,
        proof_policy="controls use default no-proof commands; official entrant uses submitted wrapper; report proof bytes and do not equate proof policies",
        independent_generic_UNSAT_certificate=False))
    paths = set(Path("research").glob("*.py"))
    paths.update(Path("experiments/drnas_v16").glob("*.py"))
    paths.update(Path("worldsim_w1/official").rglob("*"))
    paths.update(map(Path, ["r190_cms_mixed/r28", "built/bin/kissat_4_0_4",
        "r192/cms_single.sh", "r192/cms_gauss_forced.sh", "/usr/bin/cryptominisat5",
        "worldsim_w1/reference/bin/cadical_3_0_1", "worldsim_w1/official.json",
        "worldsim_w1/manifest.json", ".github/workflows/drnas-worldsim-w1.yml"]))
    save(ROOT / "pins.json", {str(p): digest(p) for p in sorted(paths) if p.is_file()})
    # Import before timed runs so one-time Python import is equal across arms.
    selector()
    for expected, cnf in [("SAT", "p cnf 3 2\n1 2 0\n-2 3 0\n"),
                          ("UNSAT", "p cnf 1 2\n1 0\n-1 0\n")]:
        source = SOURCE / "w1-smoke.cnf"
        source.write_text(cnf)
        case = dict(id="w1-smoke", sha256=digest(source), expected=expected)
        for mode in MODES:
            row = trial(case, mode, 0, -1, cap=15, emit=False)
            need(row["status"] == expected, "smoke failed " + mode)
    (SOURCE / "w1-smoke.cnf").unlink()
    print("W1_FREEZE_SMOKE_PASS", json.dumps({"sources":24,"trials":432,
        "manifest_sha256":digest(ROOT / "manifest.json")}), flush=True)

def verify_pins():
    for filename, expected in json.loads((ROOT / "pins.json").read_text()).items():
        need(digest(filename) == expected, "pin drift " + filename)
    manifest = json.loads((ROOT / "manifest.json").read_text())
    need(manifest["protocol"] == PROTO and len(manifest["cases"]) == 24, "manifest drift")
    for case in manifest["cases"]:
        need(digest(SOURCE / (case["id"] + ".cnf")) == case["sha256"], "source pin drift")
    return manifest

def shard(index):
    need(0 <= index < SHARDS, "invalid shard")
    manifest = verify_pins()
    affinity = sorted(os.sched_getaffinity(0))
    os.sched_setaffinity(0, {affinity[0]})
    selector()
    rows = []
    hardware = dict(cpu=Path("/proc/cpuinfo").read_text().split("model name",1)[-1].split("\n",1)[0],
                    affinity=sorted(os.sched_getaffinity(0)), python=sys.version)
    for case in manifest["cases"][index::SHARDS]:
        for rep in range(REPS):
            order = list(MODES)
            random.Random(PROTO + case["sha256"] + str(rep)).shuffle(order)
            for mode in order:
                rows.append(trial(case, mode, rep, index))
                save(ROOT / f"shard-{index}.json", dict(protocol=PROTO, rows=rows,
                    manifest_sha256=digest(ROOT / "manifest.json"), hardware=hardware))
    need(len(rows) == 54, "incomplete shard")
    print("W1_SHARD_PASS", index, len(rows), flush=True)

def audit():
    manifest = verify_pins()
    cases = {c["sha256"]: c for c in manifest["cases"]}
    rows, keys, hardware = [], set(), []
    for index in range(SHARDS):
        data = json.loads((ROOT / f"shard-{index}.json").read_text())
        need(data["protocol"] == PROTO and data["manifest_sha256"] == digest(ROOT / "manifest.json"), "shard provenance")
        need(len(data["rows"]) == 54 and len(data["hardware"]["affinity"]) == 1, "shard count/affinity")
        allowed = {c["sha256"] for c in manifest["cases"][index::SHARDS]}
        hardware.append(data["hardware"])
        for row in data["rows"]:
            key = row["sha256"], row["rep"], row["mode"]
            need(key not in keys and row["sha256"] in allowed, "duplicate/wrong source")
            need(row["shard"] == index and row["id"] == cases[row["sha256"]]["id"], "shard/ID drift")
            need(row["mode"] in MODES and 0 <= row["rep"] < REPS, "bad arm/rep")
            need(row["status"] in ("SAT", "UNSAT", "TIMEOUT"), "invalid status")
            need(0 <= row["elapsed_s"] <= CAP, "invalid elapsed time")
            need(row["status"] != "SAT" or row["evidence"] == "SAT_MODEL_ORIGINAL_CNF_VERIFIED", "unverified SAT")
            expected = 2*CAP if row["status"] == "TIMEOUT" else row["elapsed_s"]
            need(abs(expected-row["par2_s"]) < 0.00001, "bad PAR2")
            keys.add(key); rows.append(row)
    expected_keys = {(sha, rep, mode) for sha in cases for rep in range(REPS) for mode in MODES}
    need(keys == expected_keys and len(rows) == 432, "missing complete pairs")
    for sha in cases:
        need(len({r["status"] for r in rows if r["sha256"] == sha and r["status"] != "TIMEOUT"}) <= 1,
             "SAT/UNSAT disagreement across repetitions or solvers")
    totals = {}
    for mode in MODES:
        rr = [r for r in rows if r["mode"] == mode]
        totals[mode] = dict(attempts=len(rr), solved=sum(r["status"] != "TIMEOUT" for r in rr),
            solved_distinct_formulas=len({r["sha256"] for r in rr if r["status"] != "TIMEOUT"}),
            SAT=sum(r["status"] == "SAT" for r in rr), UNSAT=sum(r["status"] == "UNSAT" for r in rr),
            elapsed_s=round(sum(r["elapsed_s"] for r in rr),6),
            PAR2_s=round(sum(r["par2_s"] for r in rr),6),
            submitted_wrapper_proof_bytes=sum(r["submitted_wrapper_proof_bytes"] for r in rr))
    candidate = totals["ta3_portfolio"]["PAR2_s"]
    comparisons = {}
    ordered_sha = sorted(cases)
    for base in MODES[1:]:
        candidate_scores = [statistics.mean(r["par2_s"] for r in rows if r["sha256"] == sha and r["mode"] == "ta3_portfolio") for sha in ordered_sha]
        baseline_scores = [statistics.mean(r["par2_s"] for r in rows if r["sha256"] == sha and r["mode"] == base) for sha in ordered_sha]
        rng = random.Random(PROTO + base)
        samples = []
        for _ in range(10000):
            indices = rng.choices(range(24), k=24)
            samples.append(sum(baseline_scores[i] for i in indices) / sum(candidate_scores[i] for i in indices))
        samples.sort()
        comparisons[base] = dict(PAR2_ratio_vs_TA3=totals[base]["PAR2_s"]/candidate,
            source_cluster_bootstrap_95=[samples[249], samples[9749]])
    result = dict(status="W1_AUDIT_PASS", protocol=PROTO, trials=432, totals=totals,
        comparisons=comparisons, hardware=hardware, manifest=manifest,
        official_entrant=json.loads((ROOT / "official.json").read_text()),
        limitations=["24 resource-bounded sources, 60s cap; official sequential competition uses 5000s",
            "Repeated frozen evaluation cohort, not a new globally blind holdout",
            "Generic UNSAT consistency only; independent submitted proof verification absent",
            "Official entrant uses submitted wrapper/proof policy; inspect proof bytes before treating its ratio as proof-normalized",
            "No official rank, world record, or general SAT speedup claim"])
    save(ROOT / "report.json", result)
    save(ROOT / "all_trials.json", rows)
    lines = ["# DRNAS WorldSim W1 — unofficial reduced-budget SAT2026 comparison", "",
        "24 official original CNFs × 6 arms × 3 repetitions; 60s per attempt. One CPU per shard; sequential randomized paired arms.", "",
        "| Solver | Solved attempts / 72 | Distinct formulas / 24 | PAR-2 seconds | Baseline PAR-2 / TA3 PAR-2 |", "|---|---:|---:|---:|---:|"]
    for mode in sorted(MODES, key=lambda m:totals[m]["PAR2_s"]):
        t = totals[mode]
        lines.append(f"| {mode} | {t['solved']}/72 | {t['solved_distinct_formulas']}/24 | {t['PAR2_s']:.6f} | {t['PAR2_s']/candidate:.4f}× |")
    lines += ["", *["- " + s for s in result["limitations"]], ""]
    (ROOT / "report.md").write_text("\n".join(lines))
    print("W1_FINAL", json.dumps(dict(status=result["status"], trials=432, totals=totals,
        comparisons=comparisons), sort_keys=True), flush=True)

def selftest():
    status, model = parse_answer("s SATISFIABLE\nv 1 -2 0\nv 3 0\n", 10)
    need(status == "SAT" and model == {1:True, 2:False, 3:True}, "SAT parser")
    for raw, rc in [("s SATISFIABLE\ns UNSATISFIABLE\n", 0),
                    ("s SATISFIABLE\nv 1 -1 0\n", 10),
                    ("s SATISFIABLE\nv 1 0\n", 20)]:
        try:
            parse_answer(raw, rc)
        except RuntimeError:
            pass
        else:
            raise RuntimeError("accepted invalid solver answer")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "model.cnf"
        path.write_text("p cnf 3 2\n1\n2 0 -2 3 0\n")
        verify_model(path, {1:True, 2:False, 3:True})
        try:
            verify_model(path, {1:False, 2:False, 3:False})
        except RuntimeError:
            pass
        else:
            raise RuntimeError("accepted false SAT model")
    rc, raw, timeout = timed_process([sys.executable, "-c", "print('s UNSATISFIABLE');raise SystemExit(20)"], time.perf_counter(), cap=2)
    need(not timeout and parse_answer(raw, rc)[0] == "UNSAT", "process result")
    _, _, timeout = timed_process([sys.executable, "-c", "import time; time.sleep(10)"], time.perf_counter(), cap=.1)
    need(timeout, "process deadline")
    print("W1_SELFTEST_PASS", flush=True)

if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("action", choices=("freeze", "shard", "audit", "selftest"))
    cli.add_argument("--shard", type=int, default=0)
    args = cli.parse_args()
    if args.action == "shard":
        shard(args.shard)
    else:
        globals()[args.action]()
