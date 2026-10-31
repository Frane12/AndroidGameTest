"""Predefined, paired V9.9 test. All seeds and the routing rule are fixed in source."""
import csv
import hashlib
import itertools
import os
from pathlib import Path
import random
import statistics
import subprocess
import sys
import tempfile
import time

FAMILIES = ("dependencies", "dual-dependencies", "two-choices", "timetable", "random-3sat")
MODES = ("auto", "single96", "single128")
CAP = 3


def fixture(family, index):
    rng = random.Random(99031000 + 100 * FAMILIES.index(family) + index)
    sat = index % 2 == 0
    if family in ("dependencies", "dual-dependencies"):
        n = rng.randint(800, 2200)
        clauses = [[1], [2]] + [[-i, -(i + 1), i + 2] for i in range(1, n - 1)]
        for _ in range(n):
            a, b, c = rng.sample(range(1, n + 1), 3)
            clauses.append([-a, -b, c])
        if not sat:
            clauses.append([-n])
        if family == "dual-dependencies":
            clauses = [[-v for v in clause] for clause in clauses]
    elif family == "two-choices":
        n = rng.randint(800, 2200)
        # Exactly one in each consecutive pair, alternating down a chain.
        clauses = [[1], [n if (sat == bool(n % 2)) else -n]]
        for i in range(1, n):
            clauses.extend([[i, i + 1], [-i, -(i + 1)]])
    elif family == "timetable":
        events = rng.randint(35, 65)
        n = 3 * events
        slots = [rng.randrange(3) for _ in range(events)]
        clauses = []
        for event in range(events):
            choices = [3 * event + k + 1 for k in range(3)]
            clauses.append(choices)
            clauses.extend([[-a, -b] for a, b in itertools.combinations(choices, 2)])
        for a, b in itertools.combinations(range(events), 2):
            if (slots[a] != slots[b] and rng.random() < 0.15) or (not sat and b < 4):
                clauses.extend([[-(3 * a + k + 1), -(3 * b + k + 1)] for k in range(3)])
    else:
        n = rng.randrange(100, 160)
        clauses = [[v if rng.randrange(2) else -v for v in rng.sample(range(1, n + 1), 3)]
                   for _ in range(round(4.25 * n))]
        sat = None
    # Permute both variables and clauses so generated families do not rely on index order.
    perm = list(range(1, n + 1))
    rng.shuffle(perm)
    clauses = [[perm[abs(v) - 1] * (1 if v > 0 else -1) for v in c] for c in clauses]
    rng.shuffle(clauses)
    return n, clauses, sat


def run(exe, path, mode, cap):
    start = time.perf_counter()
    try:
        result = subprocess.run([exe, "--" + mode, str(path)], capture_output=True, timeout=cap)
    except subprocess.TimeoutExpired:
        return "TIMEOUT", 2 * cap, ""
    elapsed = time.perf_counter() - start
    if result.returncode not in (10, 20):
        raise RuntimeError(result.stderr.decode(errors="replace")[:400])
    lines = result.stdout.decode().splitlines()
    route, = [line.split()[2] for line in lines if line.startswith("c route ")]
    status = "SAT" if result.returncode == 10 else "UNSAT"
    if "s " + status + "ISFIABLE" not in lines:
        raise RuntimeError("inconsistent solver output")
    return status, elapsed, route


def main():
    exe = str(Path(sys.argv[1]).resolve())
    out = Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "input.cnf"
        for family in FAMILIES:
            for index in range(20):
                n, clauses, expected = fixture(family, index)
                data = f"p cnf {n} {len(clauses)}\n" + "".join(
                    " ".join(map(str, c)) + " 0\n" for c in clauses)
                path.write_text(data)
                digest = hashlib.sha256(data.encode()).hexdigest()
                labels = set()
                for rep in range(2):
                    order = list(MODES)
                    random.Random(f"99/{family}/{index}/{rep}").shuffle(order)
                    for mode in order:
                        status, cost, route = run(exe, path, mode, CAP)
                        if status != "TIMEOUT":
                            labels.add(status)
                            if expected is not None and (status == "SAT") != expected:
                                raise RuntimeError(f"wrong answer: {family}/{index}/{mode}")
                        rows.append((family, index, digest, rep, mode, route, status, cost))
                if len(labels) > 1:
                    raise RuntimeError(f"disagreement: {family}/{index}")
    assert len(rows) == 600 and len({row[2] for row in rows}) == 100
    with (out / "raw.csv").open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(("family", "case", "cnf_sha", "repeat", "mode", "route", "status", "par2_s"))
        writer.writerows(rows)
    summary = ["| Family | Mode | Solved attempts | Mean PAR2 (s) |",
               "|---|---|---:|---:|"]
    for family in (*FAMILIES, "ALL"):
        for mode in MODES:
            sample = [r for r in rows if (r[0] == family or family == "ALL") and r[4] == mode]
            solved = sum(r[6] != "TIMEOUT" for r in sample)
            summary.append(f"| {family} | {mode} | {solved}/{len(sample)} | "
                           f"{statistics.mean(r[7] for r in sample):.6f} |")
    report = "\n".join(summary)
    print(report)
    (out / "summary.md").write_text(report + "\n")


if __name__ == "__main__":
    main()
