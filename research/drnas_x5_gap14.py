#!/usr/bin/env python3
"""Outcome-selected X5 diagnosis: frozen performance and separate CPU profiles."""
import argparse
import collections
import hashlib
import json
import math
import os
from pathlib import Path
import random
import resource
import select
import signal
import subprocess
import tempfile
import time
from types import SimpleNamespace

import drnas_x5_bench as B
from drnas_x5_report import comparison

ROOT = Path(__file__).resolve().parents[1]
SELECTION = "experiments/drnas_x5_gap14/selection.json"
PROTOCOL = ROOT / "gap14_protocol.json"
CAPS, REPS, COUNT, SHARDS = [5.0, 15.0], 2, 14, 4
PROFILE_CAP, PROFILE_CHECK_CAP, PROOF_LIMIT = 15.0, 15.0, 512 * 1024 * 1024
PHASES = {"other", "parse", "bcp", "bcp_empty", "analyze", "minimize", "reduce", "proof", "select"}
ARMS = ["X5_NO_MIN", "X5", "Kissat", "CaDiCaL", "CMS"]
# Tuple fields: minimization enabled, CPU sampler enabled, proof output enabled.
PROFILE_ARMS = {
    "MIN_PROFILE_OFF": (True, False, True), "MIN_PROFILE_ON": (True, True, True),
    "NOMIN_PROFILE_OFF": (False, False, True), "NOMIN_PROFILE_ON": (False, True, True),
    "MIN_NO_PROOF": (True, True, False), "NOMIN_NO_PROOF": (False, True, False),
}
BINARIES = ["drnas-x5", "kissat", "cadical", "cms", "drat-trim", "frat-rs", "timed", "drnas-x5-profile"]
SOURCES = ["src/drnas_x5.cpp", "src/drnas_x5_profile.cpp", SELECTION,
           "research/drnas_x5_gap14.py", "research/drnas_x5_bench.py",
           "research/drnas_x47_long_bench.py", "research/drnas_x5_report.py"]


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def read(path):
    return json.loads(path.read_text())


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def file_sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as fd:
        for block in iter(lambda: fd.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def identities():
    runtime = ROOT / "build/gap14_runtime.txt"
    return {"binary_sha256": {n: file_sha(ROOT / "build" / n) for n in BINARIES},
            "source_sha256": {p: file_sha(ROOT / p) for p in SOURCES},
            "runtime_sha256": file_sha(runtime) if runtime.exists() else None}


def sources(inputs=None):
    selection = read(ROOT / SELECTION)
    require(selection["parent_benchmark_run"] == 43404243647, "Wrong selection parent")
    selected = selection["sources"]
    require(len(selected) == COUNT and len({s["sha256"] for s in selected}) == COUNT,
            "Expected fourteen distinct original CNFs")
    require([s["id"] for s in selected] == sorted({s["id"] for s in selected}), "Unordered or duplicate source IDs")
    require(collections.Counter(s["diagnostic_group"] for s in selected) ==
            {"native_control": 5, "reference_gap": 9}, "Diagnostic groups changed")
    require(all(s["expected_status"] in ("SAT", "UNSAT") for s in selected), "Missing verified original truth")
    if inputs is not None:
        original = read(inputs / "source_manifest.json")["sources"]
        require(len(original) == 100 and len({s["sha256"] for s in original}) == 100, "Invalid original100 manifest")
        by_id = {s["id"]: s for s in original}
        for source in selected:
            require(source["id"] in by_id and all(source[k] == v for k, v in by_id[source["id"]].items()),
                    "Selected metadata disagrees with original source manifest")
            path = (inputs / source["file"]).resolve()
            require(path.parent == inputs.resolve(), "Source path escapes input directory")
            require(path.stat().st_size == source["bytes"] and file_sha(path) == source["sha256"], "Original source bytes changed")
    return selected


def freeze(inputs):
    require(not PROTOCOL.exists(), "Refusing to replace a frozen diagnostic protocol")
    selected = sources(inputs)
    protocol = {"protocol": "X5-GAP14-v1", "sources": selected, "count": COUNT, "shards": SHARDS,
                "arms": ARMS, "caps_s": CAPS, "repeats": REPS, "performance_trials": 280,
                "profile_arms": {k: list(v) for k, v in PROFILE_ARMS.items()}, "profile_trials": 84,
                "profile_cap_s": PROFILE_CAP, "profile_checker_cap_s": PROFILE_CHECK_CAP,
                "profile_proof_limit_bytes": PROOF_LIMIT, "primary": "X5_NO_MIN",
                "parent_benchmark_run": 43404243647, "frozen_binary_run": 43368689724,
                "input_manifest_sha256": file_sha(inputs / "source_manifest.json"),
                "selection_sha256": file_sha(ROOT / SELECTION), "learning": False, "promotion": False,
                "selection": read(ROOT / SELECTION)["selection"],
                "performance_timing": "Frozen binaries; solver plus independent verification share the 5 or 15 second deadline.",
                "profile_timing": "Separate diagnostic clone; 15 second native limit, 15.25 second external stop; independent UNSAT audit may use 15 extra seconds, never competitive credit.",
                "phase_estimates": "SIGPROF sample proportions, exclusive phases; incomplete or fewer than 100 samples are excluded from phase aggregates.",
                **identities()}
    save(PROTOCOL, protocol)
    B.emit("GAP14_FREEZE", {k: v for k, v in protocol.items() if k != "sources"})


def check_protocol(inputs=None, binaries=False):
    p = read(PROTOCOL)
    fixed = {"protocol": "X5-GAP14-v1", "sources": sources(inputs), "count": COUNT, "shards": SHARDS,
             "arms": ARMS, "caps_s": CAPS, "repeats": REPS, "performance_trials": 280,
             "profile_arms": {k: list(v) for k, v in PROFILE_ARMS.items()}, "profile_trials": 84,
             "profile_cap_s": PROFILE_CAP, "profile_checker_cap_s": PROFILE_CHECK_CAP,
             "profile_proof_limit_bytes": PROOF_LIMIT, "primary": "X5_NO_MIN",
             "parent_benchmark_run": 43404243647, "frozen_binary_run": 43368689724,
             "selection_sha256": file_sha(ROOT / SELECTION), "learning": False, "promotion": False,
             "source_sha256": {f: file_sha(ROOT / f) for f in SOURCES}}
    if inputs is not None:
        fixed["input_manifest_sha256"] = file_sha(inputs / "source_manifest.json")
    if binaries:
        fixed.update(identities())
    for key, value in fixed.items():
        require(p[key] == value, "Protocol drift: " + key)
    return p


def selected_shard(selected, index):
    return [s for i, s in enumerate(selected) if i % SHARDS == index]


def execute(cmd, directory, limit, resource_limit=False):
    directory.mkdir(parents=True, exist_ok=True)
    out, err, rss = (directory / n for n in ("stdout.txt", "stderr.txt", "rss.txt"))
    def constrain():
        resource.setrlimit(resource.RLIMIT_FSIZE, (PROOF_LIMIT, PROOF_LIMIT))
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    started = time.monotonic()
    with out.open("w") as stdout, err.open("w") as stderr:
        child = subprocess.Popen([str(ROOT / "build/timed"), str(rss), *cmd], stdout=stdout,
                                 stderr=stderr, start_new_session=True, preexec_fn=constrain if resource_limit else None)
        pidfd = os.pidfd_open(child.pid)
        try:
            ready, _, _ = select.select([pidfd], [], [], max(0, limit - (time.monotonic() - started)))
            expired = not bool(ready)
            if expired:
                try:
                    os.killpg(child.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            child.wait()
        finally:
            os.close(pidfd)
    wall = time.monotonic() - started
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu = (after.ru_utime + after.ru_stime) - (before.ru_utime + before.ru_stime)
    peak = int(rss.read_text().splitlines()[-1]) if rss.exists() else None
    return child.returncode, wall, expired, cpu, peak, out.read_text(errors="replace"), err.read_text(errors="replace")


def profile_run(arm, original, cnf, directory, temporary):
    minimize, enabled, proof_enabled = PROFILE_ARMS[arm]
    proof = temporary / "profile.drat"
    proof.unlink(missing_ok=True)
    cmd = [str(ROOT / "build/drnas-x5-profile"), str(cnf), "--mode", "core", "--stats", "--time", str(PROFILE_CAP)]
    if not minimize: cmd.append("--x5-no-minimize")
    if enabled: cmd.append("--x5-profile")
    if proof_enabled: cmd.extend(["--proof", str(proof)])
    rc, wall, expired, cpu, rss, stdout, stderr = execute(cmd, directory, PROFILE_CAP + .25, True)
    final, progress, native, extra = None, [], {}, {}
    for line in stderr.splitlines():
        for prefix, target in (("X5_PROFILE ", "final"), ("X5_PROFILE_PROGRESS ", "progress"),
                               ("X41_STATS ", "native"), ("X5_STATS ", "extra")):
            if not line.startswith(prefix): continue
            try:
                value = json.loads(line[len(prefix):])
            except json.JSONDecodeError:
                require(expired, "Corrupted completed profile JSON")
                continue
            if target == "final": final = value
            elif target == "progress": progress.append(value)
            elif target == "native": native = value
            else: extra = value
    limited = rc in (-signal.SIGXFSZ, 128 + signal.SIGXFSZ)
    status = "TIMEOUT" if expired else "PROOF_SIZE_LIMIT" if limited else {0: "UNKNOWN", 10: "SAT", 20: "UNSAT"}.get(rc, "PROCESS_ERROR")
    if status in ("SAT", "UNSAT"):
        require(status == original["expected_status"], "Profile reported wrong truth value")
    if not expired and not limited and rc in (0, 10, 20):
        require(final is not None and final.get("complete") is True and final.get("enabled") == enabled,
                "Missing or mismatched final native profile")
        require(final.get("status") == status, "Native profile status disagrees with solver exit status")
    verified, check_s, check_status = False, 0.0, "not_needed"
    if status == "SAT":
        tick = time.monotonic()
        verified = B.B.verify_model_on_original_text(original, stdout)
        check_s = time.monotonic() - tick
        require(verified, "Invalid diagnostic SAT witness")
        check_status = "sat_verified"
    elif status == "UNSAT":
        if not proof_enabled:
            check_status = "proof_disabled_diagnostic_only"
        else:
            qr, check_s, check_timeout, _, _, qo, _ = execute(
                [str(ROOT / "build/drat-trim"), str(cnf), str(proof)], directory / "proof_check", PROFILE_CHECK_CAP)
            verified = not check_timeout and "s VERIFIED" in qo and (qr == 0 or "c trivial UNSAT" in qo)
            require(verified or check_timeout, "Independent diagnostic DRAT proof rejected")
            check_status = "unsat_verified" if verified else "checker_timeout"
    telemetry = final if final is not None else progress[-1] if progress else None
    cpu_complete = not expired and rss is not None
    native_cpu = (telemetry or {}).get("cpu_s", 0)
    cpu_lower_bound = max(cpu, native_cpu) if isinstance(native_cpu, (int, float)) and math.isfinite(native_cpu) else cpu
    result = {"arm": arm, "rep": 0, "cap_s": PROFILE_CAP, "status": status, "returncode": rc,
              "solve_e2e_s": wall, "process_cpu_s": cpu if cpu_complete else cpu_lower_bound,
              "waited_children_cpu_s": cpu, "process_cpu_complete": cpu_complete,
              "cpu_measurement": "exact_waited_children" if cpu_complete else "native_or_waited_children_lower_bound",
              "maxrss_kib": rss, "verified": verified,
              "accepted": False, "diagnostic_only": True, "check_s": check_s, "checker_status": check_status,
              "proof_enabled": proof_enabled, "profiler_enabled": enabled, "minimization_enabled": minimize,
              "external_timeout": expired, "resource_censored": limited, "native_final_available": final is not None,
              "progress_samples": len(progress), "profile": telemetry, "native_stats": native, "x5_stats": extra,
              "proof_bytes": proof.stat().st_size if proof.exists() else 0,
              "proof_sha256": file_sha(proof) if proof.exists() else None,
              "log_directory": str(directory.relative_to(ROOT))}
    proof.unlink(missing_ok=True)
    return result


def write_trial(fd, tag, row):
    fd.write(json.dumps(row, sort_keys=True) + "\n")
    fd.flush()
    B.emit(tag, row)


def shard(inputs, index):
    require(index in range(SHARDS), "Shard out of range")
    p = check_protocol(inputs, True)
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    selected = selected_shard(p["sources"], index)
    out = ROOT / "gap14_shards" / str(index)
    out.mkdir(parents=True, exist_ok=False)
    manifest = {"shard": index, "sources": selected, "logical_cpus": sorted(os.sched_getaffinity(0)),
                "protocol_sha256": file_sha(PROTOCOL), "execution_identity": identities(),
                "measurement_run_id": os.getenv("GITHUB_RUN_ID", "local")}
    save(out / "manifest.json", manifest)
    perf, profiles = [], []
    with tempfile.TemporaryDirectory() as tmp, (out / "trials.jsonl").open("w") as pf, (out / "profiles.jsonl").open("w") as df:
        for number, source in enumerate(selected):
            cnf = (inputs / source["file"]).resolve()
            require(file_sha(cnf) == source["sha256"], "Original changed before trial")
            original = {**source, "content": cnf.read_bytes().decode("ascii"), "cert": "ORIGINAL_PROOF_REQUIRED"}
            identity = {"source_id": source["id"], "sha256": source["sha256"], "family": source["family"],
                        "diagnostic_group": source["diagnostic_group"], "shard": index,
                        "measurement_run_id": manifest["measurement_run_id"]}
            for cap in CAPS:
                args = SimpleNamespace(cap=cap, checker=ROOT / "build/drat-trim", frat=ROOT / "build/frat-rs",
                                       kissat=str(ROOT / "build/kissat"), cadical=str(ROOT / "build/cadical"), cms=str(ROOT / "build/cms"))
                for rep in range(REPS):
                    order = ARMS.copy()
                    random.Random(20261113 + source["id"] * 1009 + int(cap) * 67 + rep * 37).shuffle(order)
                    for arm in order:
                        row = B.run(arm, original, cnf, Path(tmp), args)
                        if row["status"] in ("SAT", "UNSAT"):
                            require(row["status"] == source["expected_status"], "Frozen solver reported wrong truth value")
                        row.update(**identity, cap_s=cap, rep=rep, diagnostic_only=False)
                        perf.append(row); write_trial(pf, "GAP14_TRIAL", row)
            order = list(PROFILE_ARMS)
            random.Random(20261113 + 2017 * source["id"]).shuffle(order)
            for arm in order:
                row = profile_run(arm, original, cnf, out / "profile_logs" / str(source["id"]) / arm, Path(tmp))
                row.update(**identity)
                profiles.append(row); write_trial(df, "GAP14_PROFILE", row)
            B.emit("GAP14_PROGRESS", {"shard": index, "completed": number + 1, "sources": len(selected),
                                       "performance_trials": len(perf), "profile_trials": len(profiles)})
    require(identities() == manifest["execution_identity"], "Execution identity changed during shard")
    completed = {"shard": index, "protocol_sha256": file_sha(PROTOCOL), "performance_trials": len(perf), "profile_trials": len(profiles)}
    save(out / "report.json", completed)
    B.emit("GAP14_SHARD_FINAL", completed)


def profile_quality(row):
    p = row.get("profile") or {}
    reason = "usable"
    if not row["profiler_enabled"]: reason = "profiler_disabled"
    elif not row["native_final_available"] or not p.get("complete"): reason = "partial_native_telemetry"
    elif row["resource_censored"] or row["external_timeout"]: reason = "resource_censored"
    elif p.get("sample_overflow", False): reason = "sample_counter_overflow"
    elif p.get("samples_total", 0) < 100: reason = "fewer_than_100_cpu_samples"
    else:
        samples, estimates = p.get("phase_samples"), p.get("phase_cpu_estimate_s")
        if not isinstance(samples, dict) or not isinstance(estimates, dict): reason = "missing_phase_partition"
        elif set(samples) != PHASES or set(estimates) != PHASES: reason = "unexpected_phase_schema"
        elif any(type(v) is not int or v < 0 for v in samples.values()) or sum(samples.values()) != p["samples_total"]: reason = "invalid_sample_partition"
        elif any(v is None or not math.isfinite(v) or v < 0 for v in estimates.values()): reason = "invalid_phase_estimate"
        elif not isinstance(p.get("profiled_cpu_s"), (float, int)) or not math.isfinite(p["profiled_cpu_s"]) or p["profiled_cpu_s"] < 0: reason = "invalid_profile_cpu_span"
        elif not isinstance(p.get("cpu_s"), (float, int)) or not math.isfinite(p["cpu_s"]) or p["profiled_cpu_s"] > p["cpu_s"] + 1e-6: reason = "profile_span_exceeds_total_cpu"
        elif abs(sum(estimates.values()) - p["profiled_cpu_s"]) > max(1e-6, p["profiled_cpu_s"] * .001): reason = "phase_partition_does_not_cover_profile_span"
        elif sum(estimates.values()) > row["process_cpu_s"] * 1.2 + .05: reason = "phase_estimate_exceeds_process_cpu"
    return {"usable": reason == "usable", "reason": reason}


def profile_summary(rows):
    result = {}
    for arm in PROFILE_ARMS:
        rr = [r for r in rows if r["arm"] == arm]
        require(rr, "Absent diagnostic comparison arm: " + arm)
        usable = [r for r in rr if profile_quality(r)["usable"]]
        phase = collections.defaultdict(float)
        for r in usable:
            for name, value in r["profile"]["phase_cpu_estimate_s"].items(): phase[name] += value
        sample_count = sum(r["profile"]["samples_total"] for r in usable)
        sampled_span = sum(r["profile"]["profiled_cpu_s"] for r in usable)
        result[arm] = {"trials": len(rr), "verified_diagnostic_answers": sum(r["verified"] for r in rr),
                       "process_cpu_s": sum(r["process_cpu_s"] for r in rr if r["process_cpu_complete"]),
                       "incomplete_process_cpu_trials": sum(not r["process_cpu_complete"] for r in rr),
                       "incomplete_process_cpu_lower_bound_s": sum(r["process_cpu_s"] for r in rr if not r["process_cpu_complete"]),
                       "check_s": sum(r["check_s"] for r in rr),
                       "usable_phase_profiles": len(usable), "phase_cpu_estimate_s": dict(phase),
                       "phase_samples_total": sample_count, "profiled_cpu_span_s": sampled_span,
                       "observed_samples_per_cpu_second": sample_count / sampled_span if sampled_span else None,
                       "phase_quality": dict(collections.Counter(profile_quality(r)["reason"] for r in rr)),
                       "proof_bytes": sum(r["proof_bytes"] for r in rr)}
    return result


def paired_profile_details(rows):
    by = {(r["sha256"], r["arm"]): r for r in rows}
    output = []
    for sha in sorted({r["sha256"] for r in rows}):
        for prefix in ("MIN", "NOMIN"):
            off, on, no_proof = [by[(sha, prefix + suffix)] for suffix in ("_PROFILE_OFF", "_PROFILE_ON", "_NO_PROOF")]
            def work(r):
                return (r.get("profile") or {}).get("counters", {}).get("conflicts", r["native_stats"].get("conflicts"))
            left, right, proof_off_work = work(off), work(on), work(no_proof)
            same_status = off["status"] == on["status"]
            complete_pair = off["native_final_available"] and on["native_final_available"] and off["process_cpu_complete"] and on["process_cpu_complete"]
            timeout_pair = same_status and on["status"] == "UNKNOWN" and complete_pair
            ratio = (right / on["process_cpu_s"]) / (left / off["process_cpu_s"]) if timeout_pair and left and right and on["process_cpu_s"] > 0 and off["process_cpu_s"] > 0 else None
            output.append({"sha256": sha, "source_id": on["source_id"], "minimization": prefix,
                           "profiler_off_status": off["status"], "profiler_on_status": on["status"],
                           "profiler_off_conflicts": left, "profiler_on_conflicts": right,
                           "profiler_on_off_conflicts_per_cpu_ratio_for_matched_unknown": ratio,
                           "profiler_on_minus_off_wall_s": on["solve_e2e_s"] - off["solve_e2e_s"],
                           "proof_on_status": on["status"], "proof_off_status": no_proof["status"],
                           "proof_on_conflicts": right, "proof_off_conflicts": proof_off_work,
                           "proof_on_minus_off_wall_s": on["solve_e2e_s"] - no_proof["solve_e2e_s"],
                           "same_status_and_work_for_profiler_timing": complete_pair and same_status and left is not None and left == right,
                           "same_status_and_work_for_proof_timing": on["process_cpu_complete"] and no_proof["process_cpu_complete"] and on["status"] == no_proof["status"] and right is not None and right == proof_off_work,
                           "phase_quality": profile_quality(on)})
    return output


def performance_summary(rows):
    totals = B.summarize(rows, ARMS)
    for arm in ARMS:
        rr = [r for r in rows if r["arm"] == arm]
        known = [r["conflicts"] for r in rr if r["conflicts"] is not None]
        totals[arm].update(conflicts=sum(known) if known else None, conflicts_available_trials=len(known),
                           conflicts_unavailable_trials=len(rr) - len(known))
        if all(r["maxrss_kib"] is None for r in rr): totals[arm]["maxrss_completed_kib"] = None
    return totals


def report(results):
    p = check_protocol()
    manifests = sorted(results.rglob("manifest.json"))
    require(len(manifests) == SHARDS, "Expected exactly four shard manifests")
    perf, profiles, seen, runs = [], [], set(), set()
    for path in manifests:
        m = read(path); index = m["shard"]
        require(index in range(SHARDS) and index not in seen, "Duplicate or invalid shard")
        seen.add(index); runs.add(m["measurement_run_id"])
        selected = selected_shard(p["sources"], index)
        require(m["protocol_sha256"] == file_sha(PROTOCOL) and m["sources"] == selected and len(m["logical_cpus"]) == 1, "Shard protocol/source/CPU mismatch")
        require(m["execution_identity"] == {k: p[k] for k in ("binary_sha256", "source_sha256", "runtime_sha256")}, "Shard execution identity mismatch")
        batches = [[json.loads(line) for line in path.with_name(name).read_text().splitlines()] for name in ("trials.jsonl", "profiles.jsonl")]
        expected = [{(s["sha256"], cap, rep, arm) for s in selected for cap in CAPS for rep in range(REPS) for arm in ARMS},
                    {(s["sha256"], PROFILE_CAP, 0, arm) for s in selected for arm in PROFILE_ARMS}]
        for stage, batch in enumerate(batches):
            require(len(batch) == len(expected[stage]) and {(r["sha256"], r["cap_s"], r["rep"], r["arm"]) for r in batch} == expected[stage], "Missing, duplicate or unknown arm/cap/repetition")
            for r in batch:
                source = next((s for s in selected if s["id"] == r["source_id"]), None)
                require(source is not None and r["sha256"] == source["sha256"] and r["family"] == source["family"] and r["diagnostic_group"] == source["diagnostic_group"], "Trial source mismatch")
                require(r["measurement_run_id"] == m["measurement_run_id"] and r["shard"] == index, "Trial run/shard mismatch")
                if r["status"] in ("SAT", "UNSAT"): require(r["status"] == source["expected_status"], "Contradictory answer")
                if stage == 0:
                    require(r["status"] in ("SAT", "UNSAT", "TIMEOUT", "UNKNOWN") and not r["diagnostic_only"], "Invalid performance trial")
                    require(all(math.isfinite(r[k]) and r[k] >= 0 for k in ("PAR2", "e2e_s", "solve_s", "check_s")), "Invalid performance timing")
                    require(not r["verified"] or r["status"] in ("SAT", "UNSAT"), "Invalid certification flag")
                    require(r["accepted"] == (r["verified"] and r["e2e_s"] <= r["cap_s"]), "Acceptance mismatch")
                    require(abs(r["PAR2"] - (r["e2e_s"] if r["accepted"] else 2 * r["cap_s"])) < 1e-9, "PAR2 mismatch")
                else:
                    require(r["diagnostic_only"] and r["accepted"] is False and "PAR2" not in r, "Diagnostic row received competitive credit")
                    require(r["status"] in ("SAT", "UNSAT", "TIMEOUT", "UNKNOWN", "PROOF_SIZE_LIMIT"), "Diagnostic process error")
                    require([r["minimization_enabled"], r["profiler_enabled"], r["proof_enabled"]] == list(PROFILE_ARMS[r["arm"]]), "Profile configuration mismatch")
                    require(all(math.isfinite(r[k]) and r[k] >= 0 for k in ("solve_e2e_s", "process_cpu_s", "check_s")), "Invalid diagnostic timing")
                    require(r["process_cpu_complete"] == (not r["external_timeout"] and r["maxrss_kib"] is not None), "Process CPU completeness mismatch")
                    require(not r["verified"] or r["status"] == "SAT" or (r["status"] == "UNSAT" and r["proof_enabled"]), "Invalid diagnostic certification")
        done = read(path.with_name("report.json"))
        require(done == {"shard": index, "protocol_sha256": file_sha(PROTOCOL), "performance_trials": len(batches[0]), "profile_trials": len(batches[1])}, "Missing shard completion")
        perf.extend(batches[0]); profiles.extend(batches[1])
    require(len(runs) == 1 and len(perf) == 280 and len(profiles) == 84, "Incomplete or mixed diagnostic campaign")
    performance = {}
    for cap in CAPS:
        rr = [r for r in perf if r["cap_s"] == cap]
        totals = performance_summary(rr)
        for arm in ARMS:
            aa = [r for r in rr if r["arm"] == arm]
            totals[arm].update(solve_s=sum(r["solve_s"] for r in aa), check_s=sum(r["check_s"] for r in aa),
                               distinct_verified=len({r["sha256"] for r in aa if r["accepted"]}))
        performance[str(int(cap))] = {"overall": totals, "comparisons": {native: {ref: comparison(rr, native, ref) for ref in ARMS if ref != native} for native in ("X5_NO_MIN", "X5")},
                                     "by_source": {str(s["id"]): performance_summary([r for r in rr if r["source_id"] == s["id"]]) for s in p["sources"]}}
    final = {"status": "COMPLETE", "protocol": p, "performance_trials": len(perf), "profile_trials": len(profiles),
             "performance": performance, "profile_summary": profile_summary(profiles),
             "paired_profile_details": paired_profile_details(profiles), "promotion": False,
             "limitations": ["Outcome-selected retrospective diagnosis; cannot establish blind generalization.", "Profiler estimates are exclusive CPU-sample proportions, not exact phase timings.", "Phase totals are bounded by construction; this is a numeric consistency check, not proof of sampling accuracy. ITIMER_PROF delivery is kernel-quantized and samples may be correlated; nominal 1 ms is not actual timing precision.", "Diagnostic proof audits occur outside the competitive budget and never earn PAR2 credit.", "Externally killed wrapper process CPU may omit child usage; incomplete observations are flagged and excluded from CPU totals and throughput ratios.", "One diagnostic repetition per configuration; throughput ratios describe matched UNKNOWN attempts only. Proof ON/OFF wall differences require matching status and work before interpreting them as proof cost."]}
    out = ROOT / "gap14_final"
    save(out / "report.json", final)
    for name, rows in (("paired_trials.jsonl", perf), ("profiles.jsonl", profiles)):
        (out / name).write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in sorted(rows, key=lambda r: (r["source_id"], r["cap_s"], r["rep"], r["arm"])) ))
    lines = ["# X5 GAP14 — targeted original-CNF diagnosis", "", "14 originals: nine native coverage gaps and five controls. Retrospective outcome-selected diagnosis; no promotion.",
             "280 frozen-binary performance trials plus 84 separate diagnostic runs. Performance cap includes independent verification."]
    for cap, data in performance.items():
        lines += ["", f"## Shared {cap} s performance budget", "", "| Solver | Verified /28 | Originals /14 | SAT | UNSAT | PAR2 s | Check s |", "|---|---:|---:|---:|---:|---:|---:|"]
        for arm in sorted(ARMS, key=lambda a: data["overall"][a]["PAR2_s"]):
            v = data["overall"][arm]
            lines.append(f"| {arm} | {v['solved']} | {v['distinct_verified']} | {v['SAT']} | {v['UNSAT']} | {v['PAR2_s']:.4f} | {v['check_s']:.4f} |")
    lines += ["", "## CPU profiling quality", "", "Only complete profiles with at least 100 CPU samples and consistent numeric partitions enter phase aggregates. These checks do not prove sampling accuracy; SIGPROF delivery is kernel-quantized and samples may be correlated. Process CPU totals exclude externally killed wrappers whose child usage may be missing.", "", "| Configuration | Profiles | Usable phase profiles | Complete process CPU s | Incomplete CPU observations | Proof MiB |", "|---|---:|---:|---:|---:|---:|"]
    for arm, v in final["profile_summary"].items():
        lines.append(f"| {arm} | {v['trials']} | {v['usable_phase_profiles']} | {v['process_cpu_s']:.3f} | {v['incomplete_process_cpu_trials']} | {v['proof_bytes']/2**20:.2f} |")
    lines += ["", "## Approximate exclusive CPU shares", "", "Sample proportions across usable profiles only. Analysis excludes minimization; add those two shares only when an inclusive analysis share is needed.", "", "| Configuration | CPU samples | Samples / CPU s | BCP % | Analysis % | Minimize % | Reduce % | Proof % |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for arm, v in final["profile_summary"].items():
        if not v["usable_phase_profiles"]: continue
        span = v["profiled_cpu_span_s"]
        shares = [100 * v["phase_cpu_estimate_s"].get(name, 0) / span for name in ("bcp", "analyze", "minimize", "reduce", "proof")]
        lines.append(f"| {arm} | {v['phase_samples_total']} | {v['observed_samples_per_cpu_second']:.1f} | " + " | ".join(f"{value:.2f}" for value in shares) + " |")
    lines += ["", "Per-original performance, phase counters, profiler ON/OFF work comparisons and proof ON/OFF diagnostics are retained in report.json and profiles.jsonl."]
    (out / "summary.md").write_text("\n".join(lines) + "\n")
    B.emit("GAP14_FINAL", {k: final[k] for k in ("status", "performance_trials", "profile_trials", "profile_summary", "promotion")})
    for cap, data in performance.items(): B.emit("GAP14_PERFORMANCE_FINAL", {"cap_s": cap, "overall": data["overall"], "comparisons": data["comparisons"]})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("freeze", "shard", "report"))
    parser.add_argument("--shard", type=int, default=0)
    parser.add_argument("--inputs", type=Path, default=ROOT / "input/x52_original100")
    parser.add_argument("--results", type=Path, default=ROOT / "gap14_downloads")
    args = parser.parse_args()
    if args.mode == "freeze": freeze(args.inputs)
    elif args.mode == "shard": shard(args.inputs, args.shard)
    else: report(args.results)


if __name__ == "__main__":
    main()
