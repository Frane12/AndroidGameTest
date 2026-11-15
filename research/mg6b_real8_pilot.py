#!/usr/bin/env python3
"""Short, transparent retrospective benchmark of eight authentic original PCMAX CNFs.

Two sequential independent pipelines per original on one logical CPU:
MG6: generic clause-clique capacity -> VeriPB;
BDD: native PCMAX BDD guard -> independent structural checker ->
     weighted cutting-planes proof -> pinned external VeriPB.
Never label unverified output UNSAT. This is NOT a blind or PAR2 benchmark.
"""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "research/pcmax_capacity"))
from benchmark import materialize
from check_capacity import check as check_structural

MANIFEST = json.loads((ROOT / "research/pcmax_capacity/sources20.json").read_text())["entries"]
INDICES = [0, 2, 5, 10, 1, 6, 11, 12] # 4 UNSAT/author claim; 4 catalog SAT
OUT = ROOT / "results/mg6b_real8"
VERIPB = ROOT / "veripb-tool/bin/veripb"
MG6 = ROOT / "research/mg6_general_capacity.py"
EMITTER = ROOT / "research/pcmax_capacity/emit_veripb_capacity_weighted2.py"
NATIVE = ROOT / "build/drnas-pcmax"

def run(args, seconds):
    st = time.monotonic()
    try:
        p = subprocess.run([str(a) for a in args], capture_output=True, text=True, timeout=seconds)
        return p.returncode, round(time.monotonic()-st, 6), p.stdout + "\n" + p.stderr
    except subprocess.TimeoutExpired:
        return 124, round(time.monotonic()-st, 6), "TIMEOUT"

def main():
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    OUT.mkdir(parents=True, exist_ok=True)
    originals = OUT / "originals"
    originals.mkdir(exist_ok=True)
    rows = []
    failures = []
    for idx in INDICES:
        entry = MANIFEST[idx]
        case = OUT / f"{idx:02d}"
        case.mkdir(exist_ok=True)
        row = {"index": idx, "name": entry["name"], "expected_status": entry["expected_status"],
               "sha256": entry["sha256"], "mg6": "UNKNOWN", "bdd": "UNKNOWN"}
        try:
            cnf = materialize(entry, originals, True)
            raw = cnf.read_bytes()
            if hashlib.sha256(raw).hexdigest() != entry["sha256"]:
                raise RuntimeError("original SHA-256 mismatch")
            # Source-bound generic method.
            proof = case / "mg6.pbp"
            report = case / "mg6.json"
            rc, sec, msg = run([sys.executable, MG6, "--cnf", cnf,
                                 "--proof", proof, "--report", report], 30)
            row["mg6_generator_s"] = sec
            if rc != 0:
                raise RuntimeError("MG6 producer failure: " + msg[-250:])
            data = json.loads(report.read_text())
            if data["status"] == "PROOF_EMITTED_UNCHECKED":
                rc, vsec, verify = run([VERIPB, "--cnf", cnf, proof], 60)
                (case / "mg6_verifier.log").write_text(verify)
                row["mg6_verifier_s"] = vsec
                if rc == 0 and "s VERIFIED UNSATISFIABLE" in verify:
                    row["mg6"] = "VERIPB_UNSAT_VERIFIED"
                else:
                    raise RuntimeError("MG6 emitted proof not accepted by VeriPB")
            elif data["status"] != "UNKNOWN":
                raise RuntimeError("invalid MG6 state")

            # Existing BDD capacity detector as sequential standalone arm.
            capfile = (case / "capacity.json").resolve()
            rc, sec, msg = run([NATIVE, cnf.resolve(), "--mode", "core", "--time", "7",
                                "--pcmax-only", "--pcmax-capacity",
                                "--pcmax-budget-ms", "5000",
                                "--pcmax-certificate", capfile], 12)
            row["bdd_native_s"] = sec
            (case / "native.log").write_text(msg[-10000:])
            if rc == 20 and capfile.exists():
                structural = check_structural(raw, json.loads(capfile.read_text()))
                if structural.get("status") != "UNSAT_STRUCTURAL_CERTIFICATE_VERIFIED":
                    raise RuntimeError("BDD structural certificate rejected")
                row["demand"] = structural["required"]
                row["capacity"] = structural["capacity_sum"]
                pb = case / "weighted.pbp"
                rc, sec, msg = run([sys.executable, EMITTER, "--cnf", cnf,
                                    "--certificate", capfile, "--output", pb], 45)
                row["bdd_producer_s"] = sec
                (case / "producer.log").write_text(msg[-6000:])
                if rc != 0 or not pb.is_file():
                    raise RuntimeError("BDD proof producer failed")
                rc, sec, log = run([VERIPB, "--cnf", cnf, pb], 120)
                row["bdd_verifier_s"] = sec
                (case / "bdd_verifier.log").write_text(log)
                if rc == 0 and "s VERIFIED UNSATISFIABLE" in log:
                    row["bdd"] = "VERIPB_UNSAT_VERIFIED"
                else:
                    raise RuntimeError("BDD proof rejected by VeriPB")
            elif rc == 0 and "s UNKNOWN" in msg and not capfile.exists():
                pass
            else:
                raise RuntimeError(f"unexpected BDD return {rc}")
            if entry["expected_status"] == "SAT" and (
                row["mg6"] == "VERIPB_UNSAT_VERIFIED" or
                row["bdd"] == "VERIPB_UNSAT_VERIFIED"):
                raise RuntimeError("SAT control conflict")
        except Exception as e:
            row["error"] = str(e)[:320]
            failures.append(entry["name"] + ": " + str(e)[:120])
        rows.append(row)
        print("MG6B_REAL8_CASE " + json.dumps(row, sort_keys=True), flush=True)
        (OUT / "rows.json").write_text(json.dumps(rows, indent=2) + "\n")

    totals = {
        "cases": len(rows), "original_sha_verified": len(rows)-len([r for r in rows if "error" in r]),
        "mg6_veripb_unsat": sum(r["mg6"] == "VERIPB_UNSAT_VERIFIED" for r in rows),
        "bdd_veripb_unsat": sum(r["bdd"] == "VERIPB_UNSAT_VERIFIED" for r in rows),
        "both_unknown": sum(r["mg6"] == "UNKNOWN" and r["bdd"] == "UNKNOWN" for r in rows),
        "sat_controls": sum(r["expected_status"] == "SAT" for r in rows),
        "failures": failures,
        "note": "Retrospective known PCMAX family; not blind or PAR2. Independent VeriPB only."
    }
    (OUT / "summary.json").write_text(json.dumps(totals, indent=2) + "\n")
    print("MG6B_REAL8_TOTAL " + json.dumps(totals, sort_keys=True), flush=True)
    return 1 if failures else 0

if __name__ == "__main__":
    sys.exit(main())
