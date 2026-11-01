"""Head-to-head on the two original SC2024 Tseitin grid CNFs."""
import json
import os
import random
import resource
import signal
import statistics
import subprocess
import time
from pathlib import Path

from grid_certificates import make, replay, targets
from proofcheck import dimacs, verify_model
from xor4_benchmark import BIN, CAP, KISSAT, NEW, BASE, OUT, invoke, validate, controls

SOLVER_DIR = Path(os.environ["SATCOMP26_SOLVER_DIR"]).resolve()
RUN_SCRIPT = SOLVER_DIR / "run.sh"
EXPECTED_ARCHIVE_BLOB = os.environ["SATCOMP26_ARCHIVE_GIT_BLOB_SHA"]
CHAMP = "SATComp2026_Overall_Main_Track_Winner"
SOLVERS = [NEW, BASE, KISSAT, CHAMP]

def apply_limits():
    available = os.sched_getaffinity(0)
    os.sched_setaffinity(0, {min(available)})
    resource.setrlimit(resource.RLIMIT_AS, (3 * 1024**3, 3 * 1024**3))

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
        return "TIMEOUT", CAP, {"returncode": 124, "proof_present": False, "stdout": ""}
    elapsed = time.perf_counter() - start
    lines = {line.strip() for line in stdout.splitlines()}
    if "s UNSATISFIABLE" in lines:
        status = "UNSAT"
    elif "s SATISFIABLE" in lines:
        status = "SAT"
    else:
        status = "ERROR"
    proof = outdir / "proof.out"
    answer = {
        "returncode": proc.returncode,
        "proof_present": proof.is_file() and proof.stat().st_size > 0,
        "proof_bytes": proof.stat().st_size if proof.is_file() else 0,
        "stdout_tail": stdout[-1200:],
        "stderr_tail": stderr[-1200:],
    }
    return status, elapsed, answer

def summarize(trials):
    result = {}
    for solver in SOLVERS:
        rows = [t for t in trials if t["solver"] == solver]
        good = [t for t in rows if t["status"] == "UNSAT"]
        result[solver] = {
            "correct_unsat_answers": len(good),
            "attempts": len(rows),
            "timeouts": sum(t["status"] == "TIMEOUT" for t in rows),
            "errors": sum(t["status"] == "ERROR" for t in rows),
            "proof_files_present": sum(bool(t.get("proof_present")) for t in rows),
            "median_seconds_when_solved": statistics.median(t["seconds"] for t in good) if good else None,
        }
    return result

def main():
    OUT.mkdir(exist_ok=True)
    available = os.sched_getaffinity(0)
    os.sched_setaffinity(0, {min(available)})
    resource.setrlimit(resource.RLIMIT_AS, (3 * 1024**3, 3 * 1024**3))
    control_count = controls()
    trials = []
    rng = random.Random(20261101)
    for case, (_, digest) in targets.items():
        cnf = Path(case + ".cnf")
        assert cnf.is_file()
        assert __import__("hashlib").sha256(cnf.read_bytes()).hexdigest() == digest
        nvars, clauses = dimacs(cnf)
        cert = make(clauses)
        replay(clauses, cert)
        for rep in range(3):
            order = SOLVERS.copy()
            rng.shuffle(order)
            for solver in order:
                if solver == CHAMP:
                    status, seconds, answer = invoke_champion(
                        cnf, OUT / "champion-proof" / f"{case}-rep{rep}")
                    trial = {
                        "case": case, "rep": rep, "solver": solver, "status": status,
                        "seconds": seconds, "returncode": answer["returncode"],
                        "proof_present": answer["proof_present"],
                        "proof_bytes": answer["proof_bytes"],
                        "answer_matches_independent_unsat": status == "UNSAT",
                        "stdout_tail": answer["stdout_tail"],
                        "stderr_tail": answer["stderr_tail"],
                    }
                else:
                    status, seconds, answer = invoke(solver, cnf)
                    proof_verified = False
                    if status != "TIMEOUT":
                        assert status == "UNSAT", (case, solver, status, answer)
                        proof = validate(cnf, status, answer)
                        proof_verified = proof is not None
                    trial = {
                        "case": case, "rep": rep, "solver": solver, "status": status,
                        "seconds": seconds, "route": answer.get("path"),
                        "proof_verified": proof_verified,
                        "answer_matches_independent_unsat": status == "UNSAT",
                    }
                trials.append(trial)
                print(json.dumps(trial, sort_keys=True), flush=True)
    protocol = {
        "scope": "two original public SAT Competition 2024 Tseitin grid CNFs",
        "solvers": {
            NEW: "DRNAS V14.2 XOR4, rebuilt from pinned repository source",
            BASE: "DRNAS V14.2 FastGate baseline",
            KISSAT: "pinned Kissat 4.0.4 baseline",
            CHAMP: "official SAT Competition 2026 overall Main Track winner, exact anders.tar.xz package",
        },
        "official_winner_archive_git_blob_sha": EXPECTED_ARCHIVE_BLOB,
        "cap_seconds": CAP, "memory_limit_bytes": 3 * 1024**3,
        "cpu_affinity": sorted(os.sched_getaffinity(0)),
        "repetitions_per_instance": 3, "independent_parity_replay": True,
        "gate_controls_passed": control_count,
    }
    result = {"protocol": protocol, "summary": summarize(trials), "trials": trials}
    OUT.mkdir(exist_ok=True)
    (OUT / "satcomp26_winner_results.json").write_text(json.dumps(result, indent=2))
    lines = [
        "# V14.2 XOR4 vs SAT Competition 2026 Overall Main Track Winner",
        "",
        "Two original SC2024 Tseitin grid CNFs; one CPU core, 3 GiB address-space limit, 8 s cap, three repetitions each.",
        "The official competition used 5000 s and 32 GB per instance, so this is a focused mini-match, not an official ranking.",
        "",
        "| Solver | Correct UNSAT answers / 6 | Timeouts | Proof files | Median seconds when solved |",
        "|---|---:|---:|---:|---:|",
    ]
    for solver, row in result["summary"].items():
        med = row["median_seconds_when_solved"]
        med_text = f"{med:.6f}" if med is not None else "—"
        lines.append(f"| {solver} | {row['correct_unsat_answers']}/6 | {row['timeouts']} | {row['proof_files_present']} | {med_text} |")
    lines += ["", "Each input SHA-256 was matched against the frozen official source IDs. The UNSAT labels were independently replayed from the extracted XOR equations. DRNAS XOR answers were replay-checked; the winner's proof file presence is reported separately."]
    (OUT / "satcomp26_winner_results.md").write_text("\n".join(lines) + "\n")
    print(json.dumps(result["summary"], indent=2), flush=True)

if __name__ == "__main__":
    main()
