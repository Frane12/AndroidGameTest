"""Pinned V9.9 Auto vs six 2026 submissions. 9 CNFs x 7 solvers x 2 repeats."""
import csv
import hashlib
import json
import os
from pathlib import Path
import random
import signal
import statistics
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "drnas-sat-v7-8"))
from official_shortlong_select import download_and_features

CAP = 15
REPLAY = ("ee44c3f464238366729bf2cb16eb412a", "2b35377a7b95f24449a3b607b61fff05",
          "0be1e12a8e7282d1a4e389bb90f6dbc7")
KNOWN7 = (*REPLAY, "2b8cac8e1f5cad04696004e7fbf5cf2e", "8d0d8518a438d93428257d9a38863c3c",
          "3ed56242f55e3653dbceeb4a70221787", "4f09ef861ee74e50dc101765e1ce27fb")
MODES = ("drnas-v99", "satsuma-iter-kissat", "cadical3", "mergesat", "mergesat-l",
         "kissat-mab-eae2", "kissat-lr-ds")


def freeze():
    pool = {}
    for filename in ("old/official_v94_manifest.json", "new/official_v96_manifest.json"):
        for entry in json.loads(Path(filename).read_text())["cases"]:
            pool[entry["id"]] = entry
    assert len(pool) == 24
    with Path("scores.csv").open() as f:
        for r in csv.DictReader(f):
            if r["instanceid"] not in pool or r["status"] not in ("sat-verified", "unsat-verified"):
                continue
            c = pool[r["instanceid"]]
            value = float(r["runtime"])
            assert r["status"].split("-")[0].upper() == c["official_label"]
            if "best_time" not in c or value < c["best_time"]:
                c["best_time"], c["best_solver"] = value, r["solverid"]
    def row(c, group):
        return dict(id=c["id"], sha256=c["sha256"], label=c["official_label"], group=group,
                    best_s=c["best_time"], best_solver=c["best_solver"])
    chosen = [row(pool[key], "V99-replay") for key in REPLAY]
    used = set(KNOWN7)
    # Fixed public-time bands. No DRNAS result or per-case route enters the selection.
    for target in (3, 10, 25):
        for label in ("SAT", "UNSAT"):
            candidates = [c for c in pool.values() if c["id"] not in used and c["official_label"] == label]
            c = min(candidates, key=lambda c: (abs(c["best_time"] - target), c["id"]))
            chosen.append(row(c, "new-to-V99"))
            used.add(c["id"])
    assert len({c["id"] for c in chosen}) == 9
    Path("plan.json").write_text(json.dumps(chosen, indent=2) + "\n")
    print(Path("plan.json").read_text())


def load_clauses(path):
    clauses, clause = [], []
    for line in path.read_bytes().splitlines():
        line = line.strip()
        if not line or line[:1] in (b"c", b"p", b"%"):
            continue
        for lit in map(int, line.split()):
            if lit:
                clause.append(lit)
            else:
                clauses.append(clause)
                clause = []
    assert not clause
    return clauses


def check_result(stdout, rc, case, clauses):
    labels = {line.split()[1] for line in stdout.splitlines() if line.startswith("s ") and len(line.split()) > 1}
    expected = case["label"]
    if rc not in (0, 10, 20) or labels - {"SATISFIABLE", "UNSATISFIABLE"} or len(labels) > 1:
        raise ValueError(f"unexpected exit/status: {rc}, {labels}, {stdout[-240:]}")
    label = {"SATISFIABLE": "SAT", "UNSATISFIABLE": "UNSAT"}.get(next(iter(labels), ""))
    code_label = {10: "SAT", 20: "UNSAT"}.get(rc)
    if (code_label and label and code_label != label) or (label or code_label) != expected:
        raise ValueError(f"answer mismatch {rc}, {label}, expected {expected}")
    if expected == "UNSAT":
        return "official-label"
    model = {int(v) for line in stdout.splitlines() if line.startswith("v ") for v in line.split()[1:] if v != "0"}
    if not model:
        return "official-label-only"
    if any(-v in model for v in model) or not all(any(v in model for v in c) for c in clauses):
        raise ValueError("invalid SAT witness")
    return "SAT-model-verified"


def launch(cmd, cwd):
    start = time.perf_counter()
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=cwd, start_new_session=True)
    try:
        stdout, stderr = p.communicate(timeout=max(0, CAP - (time.perf_counter() - start)))
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        p.communicate()
        return None, CAP, "", ""
    return p.returncode, time.perf_counter() - start, stdout.decode(errors="replace"), stderr.decode(errors="replace")


def trial(index):
    case = json.loads(Path("plan.json").read_text())[index]
    root = Path.cwd()
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    cpus = [s.split(":", 1)[1].strip() for s in Path("/proc/cpuinfo").read_text().splitlines()
            if s.startswith("model name")]
    with tempfile.TemporaryDirectory() as tmp:
        cnf = Path(tmp) / "case.cnf"
        found = download_and_features(case["id"], cnf)
        assert found["sha256"] == case["sha256"]
        clauses = load_clauses(cnf)
        rows = []
        for repeat in (1, 2):
            order = list(MODES)
            random.Random(f"v99-2026/{case['id']}/{repeat}").shuffle(order)
            for mode in order:
                with tempfile.TemporaryDirectory(dir=tmp) as scratch:
                    cwd = scratch
                    if mode == "drnas-v99":
                        cmd = [str(root / "drnas/drnas-sat"), str(cnf)]
                    elif mode == "satsuma-iter-kissat":
                        cmd = [str(root / "winner-launch"), str(cnf), scratch]
                    else:
                        cmd = [str(root / "official/bins" / mode), str(cnf)]
                    rc, elapsed, output, err = launch(cmd, cwd)
                    status = "timeout" if rc is None else "solved"
                    check = ""
                    if rc is not None:
                        try:
                            check = check_result(output, rc, case, clauses)
                        except ValueError as exc:
                            status, check = "error", f"{exc}; stderr={err[-200:]}"
                    r = dict(case=case["id"], group=case["group"], label=case["label"], mode=mode,
                             repeat=repeat, status=status, wall_s=round(elapsed, 6),
                             validation=check, cpu=cpus[0], core=next(iter(os.sched_getaffinity(0))))
                    rows.append(r)
                    print(case["id"][:12], mode, repeat, status, r["wall_s"], check, flush=True)
        Path(f"trial-{index}.json").write_text(json.dumps(rows, indent=2))
        if any(r["status"] == "error" for r in rows):
            raise RuntimeError("invalid solver execution; see per-trial rows")


def audit():
    plan = json.loads(Path("plan.json").read_text())
    rows = [r for p in sorted(Path("trials").glob("trial-*.json")) for r in json.loads(p.read_text())]
    keys = [(r["case"], r["mode"], r["repeat"]) for r in rows]
    assert len(keys) == 126 and set(keys) == {(c["id"], m, n) for c in plan for m in MODES for n in (1, 2)}
    assert all(r["status"] in ("timeout", "solved") for r in rows)
    cost = lambda r: r["wall_s"] if r["status"] == "solved" else 2 * CAP
    with Path("results.csv").open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    lines = ["| Solver | Solved runs /18 | New /12 | Replay /6 | Mean PAR-2 s |",
             "|---|---:|---:|---:|---:|"]
    for m in sorted(MODES, key=lambda m: sum(cost(r) for r in rows if r["mode"] == m)):
        sample = [r for r in rows if r["mode"] == m]
        good = [r for r in sample if r["status"] == "solved"]
        new = sum(r["group"] == "new-to-V99" for r in good)
        lines.append(f"| {m} | {len(good)} | {new} | {len(good)-new} | {statistics.mean(map(cost,sample)):.3f} |")
    lines += ["", "| CNF / group | " + " | ".join(MODES) + " |", "|---|" + "---:|" * len(MODES)]
    for c in plan:
        cells = []
        for m in MODES:
            times = [r["wall_s"] for r in rows if r["case"] == c["id"] and r["mode"] == m and r["status"] == "solved"]
            cells.append(">15" if not times else f"{statistics.mean(times):.3f}" + (" (1/2)" if len(times) == 1 else ""))
        lines.append("| " + c["id"][:12] + " " + c["group"] + " | " + " | ".join(cells) + " |")
    lines += ["", "Published times are in the fixed plan; this is a single-core, capped wall-clock decision benchmark.",
              "SAT witnesses are checked when emitted. UNSAT agrees with verified official labels; local UNSAT proofs are not certified."]
    report = "\n".join(lines)
    Path("summary.md").write_text(report + "\n")
    print(report)


if __name__ == "__main__":
    if sys.argv[1] == "freeze":
        freeze()
    elif sys.argv[1] == "trial":
        trial(int(sys.argv[2]))
    elif sys.argv[1] == "audit":
        audit()
