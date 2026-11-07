"""Short, sequential diagnostic on two previously measured SAT Competition 2026 CNFs."""
import csv
import hashlib
import json
import os
import random
import re
import signal
import select
import math
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path.cwd().resolve()
OUT = ROOT / "short15-results"
CAP = 15
CASES = {
    "4ae685a11b5cecca76dc3d463481ce92": ("SAT", "16b09f959320357facb6345950ba5e6528299fc488c07e99f084446148755158"),
    "43d40ced32b5be08814ef24f97379654": ("UNSAT", "099b4f771e50460cd451b97d8d64a6a1d91ba709d1a514652df4aab2d7dbcd39"),
}
NATIVE = {"DRNAS-v7.6": "orig_v76", "DRNAS-v8.0": "hybrid_gate_with_observer",
          "CaDiCaL-3.0.1": "ca_plain"}
COMP = {"satsuma-iter+kissat": "anders", "Kissat-MAB-DA": "liang"}

def fetch():
    sys.path.insert(0, str(ROOT / "research/drnas-sat-v7-7"))
    from official26_v77_fetch import download, unpack
    for case, (_, digest) in CASES.items():
        data, _ = download("https://benchmark-database.de/file/" + case)
        cnf = unpack(data)
        if hashlib.sha256(cnf).hexdigest() != digest:
            raise ValueError("Wrong original CNF " + case)
        (ROOT / (case + ".cnf")).write_bytes(cnf)

def prepare():
    launches = {}
    for name, author in COMP.items():
        slug = name.lower().replace("+", "-")
        dirs = [p for p in (ROOT / author).rglob("*") if p.is_dir()
                and p.name.lower().replace("_", "-").replace("+", "-") == slug]
        if len(dirs) != 1:
            raise RuntimeError(f"Expected one {slug} directory, got {dirs}")
        paths = list(dirs[0].rglob("run-parsl.sh")) or list(dirs[0].rglob("run.sh"))
        if len(paths) != 1:
            raise RuntimeError(f"Expected one submitted launcher in {dirs[0]}, got {paths}")
        run = paths[0].resolve()
        print(name, "launcher", run, run.read_text(), flush=True)
        builds = list(dirs[0].rglob("build.sh"))
        build = run.parent / "build.sh"
        if not build.exists() and len(builds) == 1:
            build = builds[0]
        if build.is_file():
            print(name, "build", build, build.read_text(), flush=True)
            subprocess.run(["bash", str(build)], cwd=build.parent, check=True)
        launches[name] = str(run)
    (OUT / "launchers.json").write_text(json.dumps(launches, indent=2))

def execute(cmd, cwd, log):
    with log.open("wb") as output:
        start = time.monotonic()
        p = subprocess.Popen(cmd, cwd=cwd, stdout=output, stderr=subprocess.STDOUT,
                             start_new_session=True)
        pidfd = os.pidfd_open(p.pid)
        try:
            poll = select.poll()
            poll.register(pidfd, select.POLLIN)
            remaining_ms = max(0, math.ceil(1000 * (CAP - (time.monotonic() - start))))
            if not poll.poll(remaining_ms):
                os.killpg(p.pid, signal.SIGKILL)
                p.wait()
                return None, float(CAP)
            elapsed = time.monotonic() - start
            return p.wait(), elapsed
        finally:
            os.close(pidfd)

def measure(name, case, rep, launch):
    cnf = ROOT / (case + ".cnf")
    expected = CASES[case][0]
    log = OUT / f"{case[:8]}-{rep}-{name}.log"
    with tempfile.TemporaryDirectory() as tmp:
        if name in NATIVE:
            seed = (7707000 + rep * 527 + int(case[:8], 16)) % 2**32
            cmd = [str(ROOT / "v80_hybrid_probe"), NATIVE[name], str(cnf), str(seed)]
            cwd = ROOT
        else:
            runner = Path(launch[name])
            cmd = ["bash", str(runner), str(cnf), str(Path(tmp) / "proof.out")]
            cwd = runner.parent
        rc, elapsed = execute(cmd, cwd, log)
    if rc is None:
        return "TIMEOUT", elapsed, ""
    output = log.read_text(errors="replace")
    if name in NATIVE:
        matches = re.findall(r"^DRNAS_CAUSAL\tmode=(\S+)\tanswer=(SAT|UNSAT)\t", output, re.M)
        if len(matches) == 1 and matches[0] == (NATIVE[name], expected) and rc == 0:
            return expected, elapsed, "native witness" if expected == "SAT" else "matches official label"
    else:
        answers = set(re.findall(r"^s (SATISFIABLE|UNSATISFIABLE)\s*$", output, re.M))
        if answers == {expected + "ISFIABLE"} and rc in (0, 10 if expected == "SAT" else 20):
            if expected == "UNSAT":
                return expected, elapsed, "matches official label"
            from official26_v77_run import check_witness
            if check_witness(cnf, output):
                return "SAT", elapsed, "model checked on original CNF"
    return "ERROR", elapsed, f"exit {rc}: missing/incorrect answer or witness"

def benchmark():
    sys.path.insert(0, str(ROOT / "research/drnas-sat-v7-7"))
    cpu = min(os.sched_getaffinity(0))
    os.sched_setaffinity(0, {cpu})
    launch = json.loads((OUT / "launchers.json").read_text())
    methods = [*NATIVE, *COMP]
    rows = []
    with (OUT / "raw.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(("case","sha256","solver","repeat","status","wall_s","cap_s","check"))
        for case, (_, digest) in CASES.items():
            if hashlib.sha256((ROOT / (case + ".cnf")).read_bytes()).hexdigest() != digest:
                raise ValueError("CNF changed before measurement")
            order = methods.copy()
            random.Random(int(case[:8], 16)).shuffle(order)
            for rep in range(2):
                for name in (order if rep == 0 else reversed(order)):
                    try:
                        status, elapsed, detail = measure(name, case, rep, launch)
                    except (OSError, ValueError, RuntimeError) as exc:
                        status, elapsed, detail = "ERROR", 0.0, str(exc)
                    row = (case, digest, name, rep+1, status, round(elapsed, 4), CAP, detail)
                    rows.append(row)
                    w.writerow(row)
                    f.flush()
                    print("SHORT15", case[:8], name, rep+1, status, round(elapsed,4), detail, flush=True)
    lines = ["# Short15 on one CPU", "", "15 s wall per run. Two repeats. Known SAT models checked, UNSAT compared with the official label. Submitted external launchers receive a proof path; DRNAS uses its original decision driver.", "", "| GBD | Solver | Repeat 1 | Repeat 2 |", "|---|---|---|---|"]
    for case in CASES:
        for name in methods:
            block = [r for r in rows if r[0] == case and r[2] == name]
            labels = [f"{r[4]} ({r[5]:.3f} s)" for r in block]
            lines.append(f"| {case[:8]} | {name} | {' | '.join(labels)} |")
    summary = "\n".join(lines)+"\n"
    (OUT / "summary.md").write_text(summary)
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as f:
        f.write(summary)
    if len(rows) != 20 or any(r[4]=="ERROR" for r in rows):
        raise RuntimeError("Invalid short benchmark, inspect raw.csv and logs")

if __name__ == "__main__":
    OUT.mkdir(exist_ok=True)
    {"fetch": fetch, "build": prepare, "run": benchmark}[sys.argv[1]]()
