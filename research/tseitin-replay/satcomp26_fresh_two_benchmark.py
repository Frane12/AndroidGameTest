"""Three-repeat head-to-head on two fresh official SC2024 Tseitin inputs."""
import csv
import hashlib
import io
import itertools
import json
import os
import random
import resource
import signal
import statistics
import subprocess
import time
import urllib.request
import zipfile
from collections import defaultdict
from pathlib import Path

from official_shortlong_select import download_and_features
from proofcheck import dimacs, verify_model
from xor4_benchmark import BIN, CAP, NEW, BASE, KISSAT, invoke, validate, controls

SOLVER_DIR = Path(os.environ["SATCOMP26_SOLVER_DIR"]).resolve()
RUN_SCRIPT = SOLVER_DIR / "run.sh"
EXPECTED_ARCHIVE_BLOB = os.environ["SATCOMP26_ARCHIVE_GIT_BLOB_SHA"]
OUT = Path("fresh-tseitin-results")
META_URL = "https://raw.githubusercontent.com/satcompetition/2024/fa06f42b914ec155b2120aef936ce9305a3e4128/downloads/meta.csv"
META_SHA256 = "c8703ab84f28b4369c96bbdfd3d6cc0f00b0b5212bc58cd2d5d7eca48cafc0ce"
RESULTS_URL = "https://raw.githubusercontent.com/satcompetition/2024/fa06f42b914ec155b2120aef936ce9305a3e4128/downloads/detailed_results.zip"
RESULTS_SHA256 = "dfdf1d515fc95e95d3b76f907a2ce67932af1f8905f90c3dd7f743ea6c2b751a"
# Both SC2024 IDs were absent from the 326+ prior case manifest audit.
CASES = [
    ("0fa8623240b5c14c1308f863a6dc88ab", "urqh1c5x5.shuffled-as.sat03-1468.cnf.mis-103.debugged.cnf.xz"),
    ("aa39c6d885d283a085d033ab7b89f8c8", "urq45.cnf.xz"),
]
CHAMP = "SATComp2026_Overall_Main_Track_Winner"
SOLVERS = [NEW, BASE, KISSAT, CHAMP]
CAP = 8

def pinned(url, expected):
    data = urllib.request.urlopen(url, timeout=90).read()
    actual = hashlib.sha256(data).hexdigest()
    assert actual == expected, (url, actual, expected)
    return data

def apply_limits():
    affinity = os.sched_getaffinity(0)
    os.sched_setaffinity(0, {min(affinity)})
    resource.setrlimit(resource.RLIMIT_AS, (3 * 1024**3, 3 * 1024**3))

def exact_xor_equations(clauses):
    groups = defaultdict(list)
    for index, clause in enumerate(clauses):
        support = tuple(sorted(abs(lit) for lit in clause))
        if len(set(support)) != len(support) or not support or len(support) > 6:
            return None
        groups[support].append((index, clause))
    equations = []
    for support, rows in sorted(groups.items()):
        allowed = set()
        for bits in itertools.product((0, 1), repeat=len(support)):
            env = dict(zip(support, bits))
            if all(any(bool(env[abs(lit)]) == (lit > 0) for lit in clause) for _, clause in rows):
                allowed.add(bits)
        even = {bits for bits in itertools.product((0, 1), repeat=len(support)) if sum(bits) % 2 == 0}
        odd = {bits for bits in itertools.product((0, 1), repeat=len(support)) if sum(bits) % 2 == 1}
        if allowed == even:
            rhs = 0
        elif allowed == odd:
            rhs = 1
        else:
            return None
        equations.append({"variables": list(support), "rhs": rhs, "clause_indices": [i for i, _ in rows]})
    return equations

def gf2_contradiction(equations):
    pivots = {}
    for index, equation in enumerate(equations):
        bits = sum(1 << (v - 1) for v in equation["variables"])
        rhs = equation["rhs"]
        combo = 1 << index
        while bits:
            pivot = (bits & -bits).bit_length() - 1
            if pivot not in pivots:
                pivots[pivot] = (bits, rhs, combo)
                break
            other_bits, other_rhs, other_combo = pivots[pivot]
            bits ^= other_bits
            rhs ^= other_rhs
            combo ^= other_combo
        if not bits and rhs:
            selected = [i for i in range(len(equations)) if (combo >> i) & 1]
            return selected
    return None

def verify_gf2_witness(equations, selected):
    variables = set()
    rhs = 0
    for index in selected:
        row = equations[index]
        variables.symmetric_difference_update(row["variables"])
        rhs ^= row["rhs"]
    assert variables == set() and rhs == 1

def invoke_champion(cnf, outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    command = [str(RUN_SCRIPT), str(cnf.resolve()), str(outdir.resolve())]
    start = time.perf_counter()
    proc = subprocess.Popen(command, cwd=str(SOLVER_DIR), stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True, start_new_session=True,
                            preexec_fn=apply_limits)
    try:
        stdout, stderr = proc.communicate(timeout=CAP)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        return "TIMEOUT", CAP, {"returncode": 124, "proof_present": False, "model": []}
    elapsed = time.perf_counter() - start
    lines = {line.strip() for line in stdout.splitlines()}
    if "s UNSATISFIABLE" in lines:
        status = "UNSAT"
    elif "s SATISFIABLE" in lines:
        status = "SAT"
    else:
        status = "ERROR"
    proof = outdir / "proof.out"
    model = [int(lit) for line in stdout.splitlines() if line.startswith("v ")
             for lit in line.split()[1:] if lit != "0"]
    return status, elapsed, {
        "returncode": proc.returncode,
        "proof_present": proof.is_file() and proof.stat().st_size > 0,
        "proof_bytes": proof.stat().st_size if proof.is_file() else 0,
        "model": model,
        "stdout_tail": stdout[-1200:],
        "stderr_tail": stderr[-1200:],
    }

def official_labels():
    meta = pinned(META_URL, META_SHA256)
    rows = list(csv.DictReader(io.StringIO(meta.decode("utf-8"))))
    by_id = {row["hash"]: row for row in rows}
    for ident, filename in CASES:
        assert ident in by_id, ident
        assert by_id[ident]["family"] == "tseitin", by_id[ident]
        assert by_id[ident]["filename"] == filename, by_id[ident]
    archive = pinned(RESULTS_URL, RESULTS_SHA256)
    table = csv.DictReader(io.StringIO(zipfile.ZipFile(io.BytesIO(archive)).read("detailed_main.csv").decode("utf-8")))
    labels = {row["hash"]: row["vresult"].upper() for row in table}
    return by_id, labels

def main():
    OUT.mkdir(exist_ok=True)
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_AS, (3 * 1024**3, 3 * 1024**3))
    gate_controls = controls()
    meta, labels = official_labels()
    cases = []
    for ident, filename in CASES:
        path = OUT / (ident + ".cnf")
        info = download_and_features(ident, path)
        nvars, clauses = dimacs(path)
        equations = exact_xor_equations(clauses)
        witness = gf2_contradiction(equations) if equations is not None else None
        if witness is not None:
            verify_gf2_witness(equations, witness)
        cases.append({
            "id": ident, "filename": filename, "family": meta[ident]["family"],
            "official_label": labels.get(ident, "UNKNOWN"), "sha256": info["sha256"],
            "variables": nvars, "clauses": len(clauses),
            "exact_xor_equations": len(equations) if equations is not None else None,
            "gf2_unsat_witness_rows": witness,
            "path": path, "clauses_data": clauses,
        })
    available = os.sched_getaffinity(0)
    protocol = {
        "scope": "two previously unused original SAT Competition 2024 Tseitin-family formulas",
        "case_ids": [c["id"] for c in cases],
        "input_sha256": {c["id"]: c["sha256"] for c in cases},
        "official_labels": {c["id"]: c["official_label"] for c in cases},
        "history_audit": "IDs absent from the prior 326+ case-manifest snapshot and prior formula run artifacts",
        "solvers": {
            NEW: "DRNAS V14.2 XOR4 rebuilt from pinned repository source",
            BASE: "DRNAS V14.2 FastGate pinned baseline",
            KISSAT: "pinned Kissat 4.0.4 baseline",
            CHAMP: "exact official SAT Competition 2026 overall Main Track winner package",
        },
        "official_winner_archive_git_blob_sha": EXPECTED_ARCHIVE_BLOB,
        "cpu_affinity": sorted(available), "memory_limit_bytes": 3 * 1024**3,
        "cap_seconds": CAP, "repetitions_per_formula": 3,
        "independent_xor_certificate": "Every reported GF(2) witness is formed from clauses grouped by exact support; each block is exhaustively checked against its parity equation before Gaussian elimination.",
        "gate_controls_passed": gate_controls,
    }
    trials = []
    rng = random.Random(20261101)
    for case in cases:
        for rep in range(3):
            order = SOLVERS.copy()
            rng.shuffle(order)
            for solver in order:
                if solver == CHAMP:
                    status, seconds, answer = invoke_champion(case["path"], OUT / "champion-proof" / f'{case["id"]}-rep{rep}')
                else:
                    status, seconds, answer = invoke(solver, case["path"])
                verified = False
                if status == "SAT":
                    if solver == CHAMP:
                        verify_model(case["variables"], case["clauses_data"], answer["model"])
                    else:
                        validate(case["path"], status, answer)
                    verified = True
                elif status == "UNSAT":
                    if solver != CHAMP:
                        validate(case["path"], status, answer)
                    if case["gf2_unsat_witness_rows"] is not None:
                        verify_gf2_witness(case["equations"], case["gf2_unsat_witness_rows"])
                        verified = True
                official = case["official_label"]
                label_match = official in ("UNKNOWN", status)
                trial = {
                    "case": case["id"], "filename": case["filename"], "rep": rep,
                    "solver": solver, "status": status, "seconds": seconds,
                    "official_label": official, "matches_official_label": label_match,
                    "independently_checked": verified,
                    "proof_file_present": answer.get("proof_present", False),
                    "route": answer.get("path"),
                }
                trials.append(trial)
                print(json.dumps(trial, sort_keys=True), flush=True)
    summary = {}
    for solver in SOLVERS:
        rows = [t for t in trials if t["solver"] == solver]
        solved = [t for t in rows if t["status"] in ("SAT", "UNSAT")]
        summary[solver] = {
            "attempts": len(rows),
            "official_label_matches": sum(t["matches_official_label"] for t in rows),
            "independently_checked_answers": sum(t["independently_checked"] for t in rows),
            "timeouts": sum(t["status"] == "TIMEOUT" for t in rows),
            "errors": sum(t["status"] == "ERROR" for t in rows),
            "median_seconds_when_solved": statistics.median(t["seconds"] for t in solved) if solved else None,
        }
    result = {"protocol": protocol, "cases": [{k:v for k,v in c.items() if k not in ("path","clauses_data","equations")} for c in cases], "summary": summary, "trials": trials}
    (OUT / "results.json").write_text(json.dumps(result, indent=2))
    lines = [
        "# DRNAS V14.2 XOR4 vs SATComp 2026 Main Track Winner — fresh SC2024 inputs",
        "",
        "Two official SC2024 Tseitin-family formulas absent from the prior case manifests. Three repeats per formula; one core, 3 GiB, 8 s cap.",
        "",
        "| Solver | Correct official labels / 6 | Timeouts | Independently checked answers | Median seconds when solved |",
        "|---|---:|---:|---:|---:|",
    ]
    for solver, row in summary.items():
        median = row["median_seconds_when_solved"]
        median_text = f"{median:.6f}" if median is not None else "—"
        lines.append(f"| {solver} | {row['official_label_matches']}/6 | {row['timeouts']} | {row['independently_checked_answers']}/6 | {median_text} |")
    lines += ["", "Formula IDs, SHA-256 digests, official labels, and GF(2) contradiction witnesses are recorded in results.json. A solver answer is counted against the official label; independently checked SAT models and parity UNSAT witnesses are reported separately."]
    (OUT / "results.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(summary, indent=2), flush=True)

if __name__ == "__main__":
    main()
