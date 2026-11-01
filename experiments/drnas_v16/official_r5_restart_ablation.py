#!/usr/bin/env python3
"""DRNAS R5 diagnostic pilot: original vs monitoring vs restartint 25/50/100.

One previously seen R4-regression instance (#361), 3 paired randomized
repeats, one Linux runner, 75s cap. Not a blind holdout. Never tune on this
case and then report this case as unseen proof of generalization.
"""
from __future__ import annotations
import csv
import hashlib
import json
import os
import platform
import random
import resource
import signal
import statistics
import subprocess
import time
from pathlib import Path
import official_parallel_v180 as common

ROOT = Path("drnas-r5-restart-ablation-results")
INDEX = 361
GBD_HASH = "e305def35c314eec8266087e89a9ab46"
CNF_SHA256 = "fe959fcde799f1dc21eef3a6eaa2d5308175060a01c86f3cc10a2b6d99dc93e4"
ARCHIVE_SHA256 = "9edd7066a583de597f9e3c2f866aa1630032ec03ecd607f4d06a24a5c8ff0015"
EXPECTED = "SAT"
ORIGINAL = "/tmp/kissat-r5-original/build/kissat"
PATCHED = "/tmp/kissat-r5-patched/build/kissat"
CAP_SECONDS = 75
REPEATS = 3
MODES = ("original", "monitor", "restart25", "restart50", "restart100")
MODE_ENV = {
    "monitor": "r5_monitor",
    "restart25": "r5_25",
    "restart50": "r5_50",
    "restart100": "r5_100",
}
COLUMNS = (
    "index", "repeat", "mode", "expected", "status", "wall_s", "cpu_s",
    "par2_s", "sat_witness_verified", "early_conflict", "early_restarts",
    "switch_at", "restart_before", "restart_after", "final_conflicts",
    "final_restarts", "warning",
)

def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def write_csv(path: Path, records: list[dict]) -> None:
    with path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(records)

def obtain_case() -> Path:
    url = (
        f"https://raw.githubusercontent.com/satcompetition/2026/"
        f"{common.PINNED_TRACK}/downloads/track_main_2026.uri"
    )
    raw_uris = common.fetch(url, 100000, timeout=35)
    urls = raw_uris.decode("ascii").strip().splitlines()
    if len(urls) != 400:
        raise RuntimeError("Official 2026 input URI list has changed")
    source_url = urls[INDEX].replace("http://", "https://", 1)
    if source_url.rsplit("/", 1)[-1] != GBD_HASH:
        raise RuntimeError("Official CNF identity mismatch")
    compressed = common.fetch(source_url, 25165824, timeout=50)
    if sha(compressed) != ARCHIVE_SHA256:
        raise RuntimeError("CNF archive SHA256 differs from R4 frozen input")
    common.RAW_LIMIT = 100663296
    raw = common.unpack_limited(compressed)
    if sha(raw) != CNF_SHA256:
        raise RuntimeError("CNF SHA256 differs from R4 frozen input")
    nvars, nclauses = common.dimensions(raw)
    ROOT.mkdir(parents=True, exist_ok=True)
    path = ROOT / f"official_{INDEX}.cnf"
    path.write_bytes(raw)
    meta = {
        "purpose": "diagnostic known R4 regression case; NOT blind holdout",
        "sat_competition_year": 2026,
        "index": INDEX, "gbd_hash": GBD_HASH, "expected": EXPECTED,
        "original_reference_result": "sat-verified",
        "source_url": source_url, "cnf_sha256": CNF_SHA256,
        "archive_sha256": ARCHIVE_SHA256,
        "official_uri_sha256": sha(raw_uris),
        "nvars": nvars, "nclauses": nclauses,
        "source_kissat_commit": "8af8e56f174b778aef3aa45af9f739b2a5f492c2",
        "cap_seconds": CAP_SECONDS, "repeats": REPEATS, "modes": MODES,
        "one_host_all_arms": True,
        "cpu": subprocess.run(["lscpu"], capture_output=True, text=True, check=True).stdout,
        "platform": platform.platform(),
        "runner_name": os.environ.get("RUNNER_NAME", ""),
        "original_binary_sha256": sha(Path(ORIGINAL).read_bytes()),
        "patched_binary_sha256": sha(Path(PATCHED).read_bytes()),
        "not_official_competition_scoring": True,
    }
    (ROOT / "manifest.json").write_text(json.dumps(meta, indent=2))
    print("R5_INPUT", json.dumps({k: meta[k] for k in (
        "index", "cnf_sha256", "nvars", "nclauses", "cap_seconds", "repeats"
    )}), flush=True)
    return path

def extract_tag(output: str, prefix: str) -> dict:
    for line in output.splitlines():
        if line.startswith(prefix):
            return dict(part.split("=", 1) for part in line.split()[2:] if "=" in part)
    return {}

def run_one(cnf: Path, repeat: int, mode: str) -> dict:
    env = os.environ.copy()
    env.pop("DRNAS_V177_MODE", None)
    env.pop("DRNAS_V177_RULE_FILE", None)
    patched = mode != "original"
    if patched:
        env["DRNAS_V177_MODE"] = MODE_ENV[mode]
    binary = PATCHED if patched else ORIGINAL
    start_cpu = resource.getrusage(resource.RUSAGE_CHILDREN)
    start = time.perf_counter()
    process = subprocess.Popen(
        [binary, "-s", str(cnf.resolve())], env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, errors="replace", start_new_session=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=CAP_SECONDS)
        status = {10: "SAT", 20: "UNSAT"}.get(process.returncode, "ERROR")
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        stdout, stderr = process.communicate()
        status = "TIMEOUT"
    wall = time.perf_counter() - start
    end_cpu = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu_s = (end_cpu.ru_utime + end_cpu.ru_stime
             - start_cpu.ru_utime - start_cpu.ru_stime)
    output = stdout + "\n" + stderr
    if status == "ERROR":
        raise RuntimeError(f"Unexpected Kissat exit: {mode} {repeat}: {output[-400:]}")
    if status in ("SAT", "UNSAT") and status != EXPECTED:
        raise RuntimeError(f"R5 correctness contradiction: {mode} {repeat} {status}")
    witness = False
    if status == "SAT":
        witness = common.check_model(cnf, output, None)
        if not witness:
            raise RuntimeError(f"R5 missing/invalid SAT witness: {mode} {repeat}")
    early = extract_tag(output, "c DRNAS_V177_EARLY ")
    switch = extract_tag(output, "c DRNAS_V177_SWITCH ")
    final = extract_tag(output, "c DRNAS_V177_FINAL ")
    warning = []
    if patched and not early:
        warning.append("No early 512-conflict snapshot")
    if mode == "monitor" and switch:
        raise RuntimeError("Monitor mode unexpectedly modified solver")
    expected_interval = {"restart25": 25, "restart50": 50, "restart100": 100}
    if switch:
        if mode not in expected_interval:
            raise RuntimeError("Unauthorized intervention")
        if int(switch.get("at", "0")) < 2048:
            raise RuntimeError("Intervention before conflict 2048")
        if int(switch.get("restart_after", "-1")) != expected_interval[mode]:
            raise RuntimeError("Wrong in-process restart interval")
    elif mode in expected_interval:
        warning.append("Intervention not reached; no treatment")
    row = {
        "index": INDEX, "repeat": repeat, "mode": mode,
        "expected": EXPECTED, "status": status,
        "wall_s": round(wall, 6), "cpu_s": round(cpu_s, 6),
        "par2_s": round(wall if status in ("SAT", "UNSAT") else 2 * CAP_SECONDS, 6),
        "sat_witness_verified": witness,
        "early_conflict": early.get("conflict", ""),
        "early_restarts": early.get("restarts", ""),
        "switch_at": switch.get("at", ""),
        "restart_before": switch.get("restart_before", ""),
        "restart_after": switch.get("restart_after", ""),
        "final_conflicts": final.get("conflicts", ""),
        "final_restarts": final.get("restarts", ""),
        "warning": ";".join(warning),
    }
    print("R5_MEASURE", INDEX, repeat, mode, status,
          f"wall={wall:.5f}s", f"PAR2={row['par2_s']:.5f}",
          f"early_restarts={row['early_restarts']}",
          f"switch={row['switch_at']}",
          f"restart_after={row['restart_after']}", flush=True)
    return row

def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    cnf = obtain_case()
    rows = []
    for repeat in range(REPEATS):
        order = list(MODES)
        random.Random(361050 + repeat).shuffle(order)
        for mode in order:
            rows.append(run_one(cnf, repeat, mode))
            write_csv(ROOT / "measurements.partial.csv", rows)
    write_csv(ROOT / "measurements.csv", rows)
    summaries = []
    base_par2 = sum(r["par2_s"] for r in rows if r["mode"] == "original")
    for mode in MODES:
        subset = [r for r in rows if r["mode"] == mode]
        solved_times = [r["wall_s"] for r in subset if r["status"] == "SAT"]
        total_par2 = sum(r["par2_s"] for r in subset)
        summaries.append({
            "mode": mode,
            "solved": len(solved_times),
            "attempts": len(subset),
            "wall_median_of_solved_s": round(statistics.median(solved_times), 6)
                if solved_times else None,
            "par2_total_s": round(total_par2, 6),
            "par2_improvement_vs_original_pct": round(100 * (1 - total_par2 / base_par2), 4),
            "verified_sat_witnesses": sum(r["sat_witness_verified"] for r in subset),
            "actual_switches": sum(bool(r["switch_at"]) for r in subset),
        })
    result = {
        "experiment": "DRNAS R5 paired in-process restart interval ablation",
        "status": "development pilot on known R4 regression; NOT blind",
        "n_formulas": 1, "repeats": REPEATS,
        "cap_seconds": CAP_SECONDS,
        "claim": "mechanistic diagnostic only; cannot establish general speedup",
        "results": summaries,
    }
    (ROOT / "summary.json").write_text(json.dumps(result, indent=2))
    print("R5_FINAL", json.dumps(result, separators=(",", ":")), flush=True)

if __name__ == "__main__":
    main()
