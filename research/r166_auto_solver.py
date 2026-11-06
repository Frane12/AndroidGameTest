#!/usr/bin/env python3
"""DRNAS R166 certified EXACT XOR auto-dispatch + fail-closed CDCL fallback.

Real executable interface (not a post-hoc benchmark selector):
    python3 research/r166_auto_solver.py SOURCE.cnf --native r166/r164-native --cap 5

SAT/UNSAT fast-path is permitted ONLY when every original CNF clause is
covered by source-complete parity blocks (width 2..6) or original units.
Mixed, unsupported or partial XOR CNFs always fall back to pinned clean CDCL.
Input is neither modified nor pre-simplified. Optional --proof-out records
source rows and a replayable parity contradiction/fully checked SAT model.
NOTE: fallback is CaDiCaL clean, NOT R164 direct_incremental. R166 is an
external dispatcher, not yet a fused C++/CaDiCaL GF2 engine.
"""
import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import r164_pure_exact_gf2 as pure
import r164_component_benchmark as native_api

def require(condition, reason):
    if not condition:
        raise RuntimeError("R166_FAIL_CLOSED " + reason)

def digest(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def parity_certificate(rows, answer, source_sha, n, clauses):
    certificate = {
        "source_sha256": source_sha, "status": answer["status"],
        "source_vars": n, "source_clauses": len(clauses),
        "rows": [[list(vs), rhs] for vs, rhs in rows],
        "gauss_rank": answer["rank"]
    }
    if answer["status"] == "SAT":
        model = answer["model"]
        require(pure.verify_sat(clauses, model),
                "original-CNF SAT witness failed verification")
        certificate["model_true_vars"] = [
            v for v in range(1, n + 1) if (model >> (v - 1)) & 1
        ]
        certificate["model_sha256"] = hashlib.sha256(
            "".join(str((model >> i) & 1) for i in range(n)).encode()
        ).hexdigest()
    else:
        ids = answer["conflict_row_ids"]
        lhs = 0
        rhs = 0
        for j in ids:
            require(0 <= j < len(rows), "invalid XOR contradiction index")
            vars_, bit = rows[j]
            for v in vars_:
                lhs ^= 1 << (v - 1)
            rhs ^= bit
        require(lhs == 0 and rhs == 1, "contradiction certificate did not replay")
        certificate["conflict_row_ids"] = ids
    return certificate

def get_native_result(source, binary, time_left, started, cap):
    with tempfile.TemporaryDirectory(prefix="r166-") as directory:
        empty = pathlib.Path(directory) / "no-gf2-rows.tsv"
        empty.write_text("")
        proc = subprocess.run(
            [str(binary.resolve()), "clean", str(source.resolve()),
             str(empty.resolve()), str(time_left)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=time_left + 12)
    require(proc.returncode in (0, 10, 20),
            "native error " + proc.stderr.decode(errors="replace")[-1000:])
    txt, fields, stats, source_rows, derived = native_api.parse_native(
        proc.stdout, "clean")
    require(source_rows == 0 and derived == 0, "clean fallback carried GF2 data")
    status = {"SAT":"SAT","UNSAT":"UNSAT","UNKNOWN":"TIMEOUT"}[fields["status"]]
    require(proc.returncode == {"SAT":10,"UNSAT":20,"TIMEOUT":0}[status],
            "native status and return code differ")
    if status == "SAT":
        require(fields.get("source_sat_witness_checked") == "1",
                "native SAT witness not checked")
        native_api.sat_check(source, txt)
    return {
        "method": "CLEAN_CDCL_FALLBACK", "status": status,
        "native_mode": "clean", "source_rows": source_rows,
        "gf2_proposals": int(fields["direct_proposals"]),
        "native_stats": stats, "source_sat_witness_checked": status == "SAT",
        "native_stdout": txt
    }

def solve(source, binary, cap, proof_out=None):
    source = pathlib.Path(source)
    binary = pathlib.Path(binary)
    require(source.is_file() and binary.is_file(), "missing CNF or native executable")
    require(0.1 <= cap <= 3600, "invalid cap")
    begin = time.perf_counter()
    source_sha = digest(source)
    n, clauses = pure.parse_dimacs(source)
    exact, rows, covered = pure.detect_exact(clauses)
    record = {
        "source_sha256": source_sha, "variables": n,
        "clauses": len(clauses), "pure_exact": exact,
        "covered_clauses": covered, "xor_rows": len(rows),
        "cap_s": cap, "status": "TIMEOUT",
        "method": "NOT_STARTED", "native_mode": None,
        "source_sat_witness_checked": False,
        "certification": None, "model_sha256": None,
    }
    proof = None
    native_stdout = ""
    if exact and time.perf_counter() - begin < cap:
        answer = pure.gaussian(rows)
        proof = parity_certificate(rows, answer, source_sha, n, clauses)
        elapsed = time.perf_counter() - begin
        if elapsed <= cap:
            record.update(
                status=answer["status"], method="EXACT_GF2_FASTPATH",
                certification=("CNF_EQUIVALENCE_AND_SOURCE_MODEL" if answer["status"] == "SAT"
                               else "CNF_EQUIVALENCE_AND_PARITY_CONTRADICTION_NO_LRAT"),
                source_sat_witness_checked=answer["status"] == "SAT",
                model_sha256=proof.get("model_sha256"),
                certificate_rows=len(proof.get("conflict_row_ids", [])),
                gauss_rank=answer["rank"],
            )
        else:
            record.update(method="EXACT_GF2_CAP_EXCEEDED", status="TIMEOUT")
    elif exact:
        record.update(method="DETECTION_CAP_EXCEEDED", status="TIMEOUT")
    else:
        remaining = cap - (time.perf_counter() - begin)
        if remaining > 0.10:
            native = get_native_result(source, binary, remaining, begin, cap)
            native_stdout = native.pop("native_stdout")
            record.update(native)
            record["certification"] = ("NATIVE_ORIGINAL_MODEL_CHECKED" if
                record["status"] == "SAT" else
                "NATIVE_UNSAT_NO_INDEPENDENT_PROOF" if record["status"] == "UNSAT"
                else "NO_CONCLUSION")
        else:
            record.update(method="DETECTION_CAP_EXCEEDED", status="TIMEOUT")
    elapsed = time.perf_counter() - begin
    if elapsed > cap and record["status"] in ("SAT", "UNSAT"):
        # Never count an over-cap solver answer as a within-cap benchmark solve.
        record["over_cap_native_status"] = record["status"]
        record["status"] = "TIMEOUT"
        record["method"] += "_OVER_CAP"
    record["wall_s"] = round(elapsed, 6)
    record["par2_s"] = round(2 * cap if record["status"] == "TIMEOUT"
                             else min(cap, elapsed), 6)
    if proof_out is not None and proof is not None:
        pathlib.Path(proof_out).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(proof_out).write_text(json.dumps(proof, sort_keys=True))
    print("R166_RESULT", json.dumps(record, sort_keys=True), flush=True)
    if record["status"] == "SAT":
        print("s SATISFIABLE")
        if proof is not None:
            tvars = set(proof["model_true_vars"])
            for first in range(1, n + 1, 80):
                print("v " + " ".join(str(i if i in tvars else -i)
                                     for i in range(first, min(n+1, first+80))) + " 0")
        else:
            # Preserve independently checked native model.
            for line in native_stdout.splitlines():
                if line.startswith("v "):
                    print(line)
    elif record["status"] == "UNSAT":
        print("s UNSATISFIABLE")
    else:
        print("s UNKNOWN")
    return {"SAT":10, "UNSAT":20, "TIMEOUT":0}[record["status"]]

def selftest():
    with tempfile.TemporaryDirectory() as folder:
        samples = {
          "pure-sat": ("p cnf 2 2\n1 2 0\n-1 -2 0\n", True, "SAT"),
          "pure-unsat": ("p cnf 2 4\n1 2 0\n-1 -2 0\n1 -2 0\n-1 2 0\n", True, "UNSAT"),
          "xor-unit": ("p cnf 2 3\n1 2 0\n-1 -2 0\n1 0\n", True, "SAT"),
          "contradictory-units": ("p cnf 1 2\n1 0\n-1 0\n", True, "UNSAT"),
          "empty": ("p cnf 1 1\n0\n", False, "NOT_PURE"),
          "no-clauses": ("p cnf 2 0\n", True, "SAT"),
          "mixed-or": ("p cnf 3 3\n1 2 0\n-1 -2 0\n2 3 0\n", False, "NOT_PURE"),
          "partial-block": ("p cnf 3 3\n1 2 3 0\n-1 -2 3 0\n1 -2 -3 0\n", False, "NOT_PURE"),
        }
        for key, (formula, expected_pure, expected) in samples.items():
            path = pathlib.Path(folder) / (key + ".cnf")
            path.write_text(formula)
            n, clauses = pure.parse_dimacs(path)
            exact, rows, covered = pure.detect_exact(clauses)
            require(exact == expected_pure, "selftest gate " + key)
            if exact:
                answer = pure.gaussian(rows)
                require(answer["status"] == expected, "selftest result " + key)
                cert = parity_certificate(rows, answer, digest(path), n, clauses)
                require(cert["source_sha256"] == digest(path), "selftest cert " + key)
            print("R166_SELFTEST", key, expected, flush=True)
    print("R166_SELFTEST_PASS", len(samples), flush=True)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("source", nargs="?")
    ap.add_argument("--native", default="r166/r164-native")
    ap.add_argument("--cap", type=float, default=5.0)
    ap.add_argument("--proof-out")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        selftest()
    else:
        require(args.source, "missing source DIMACS")
        sys.exit(solve(args.source, args.native, args.cap, args.proof_out))
