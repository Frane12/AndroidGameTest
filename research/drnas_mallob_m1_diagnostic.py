#!/usr/bin/env python3
"""Mallob M1 diagnostic: preserved timeout traces, positive SAT and UNSAT controls.

No algorithm change. Reuses the original immutable R193 SHA-locked input bundle
from the completed AlphaMapleSAT/Mallob run. Previously used originals are
DEVELOPMENT ONLY. This is not a performance or global holdout claim.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import signal
import subprocess
import time

import drnas_alpha_mallob_shared as prev

ROOT = Path("mallob_m1")
MALLOB = Path("external/mallob").resolve()
RUN = MALLOB / "build/mallob"
EXPECTED_SHA = prev.EXPECTED_MANIFEST


def require(ok, reason):
    if not ok:
        raise RuntimeError("MALLOB_M1_FAIL_CLOSED " + reason)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def sat_model_valid(cnf, model):
    numvar = nclauses = None
    seen, clause = 0, []
    for line in Path(cnf).read_text().splitlines():
        line = line.strip()
        if not line or line.startswith(("c", "%")):
            continue
        if line.startswith("p "):
            words = line.split()
            require(len(words) == 4 and words[1] == "cnf", "DIMACS header")
            numvar, nclauses = int(words[2]), int(words[3])
            continue
        require(numvar is not None, "missing DIMACS header")
        for word in line.split():
            lit = int(word)
            require(abs(lit) <= numvar, "out-of-range literal")
            if lit:
                clause.append(lit)
            else:
                require(any(abs(k) in model and model[abs(k)] == (k > 0)
                            for k in clause), "SAT witness fails ORIGINAL CNF")
                seen += 1
                clause = []
    require(nclauses == seen and not clause, "DIMACS clause count")


def parse_results(text, solpaths):
    data = text + "\n" + "\n".join(p.read_text(errors="replace") for p in solpaths)
    statuses = set(re.findall(r"^s\s+(SATISFIABLE|UNSATISFIABLE)\s*$", data, re.M))
    result = ("SAT" if statuses == {"SATISFIABLE"} else
              "UNSAT" if statuses == {"UNSATISFIABLE"} else
              "AMBIGUOUS" if statuses else "UNKNOWN")
    model = {}
    for line in data.splitlines():
        if line.startswith("v "):
            for raw in line[2:].split():
                try:
                    lit = int(raw)
                except ValueError:
                    continue
                if lit:
                    require(abs(lit) not in model or model[abs(lit)] == (lit > 0),
                            "SAT witness conflicting")
                    model[abs(lit)] = lit > 0
    return result, model


def diagnose(label, source, cap, cohort, expected=None):
    source = Path(source).resolve()
    require(source.is_file() and RUN.is_file(), "missing source or Mallob binary")
    output = ROOT / label
    output.mkdir(parents=True, exist_ok=True)
    solution = (output / "answer.sol").resolve()
    command = [str(RUN), "-mono=" + str(source),
               "-mono-app=SAT", "-t=2", "-satsolver=k",
               "-s2f=" + str(solution)]
    wall_start = time.perf_counter()
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    process = subprocess.Popen(command, cwd=MALLOB, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, start_new_session=True)
    deadline_hit = False
    try:
        stdout, _ = process.communicate(timeout=cap)
    except subprocess.TimeoutExpired:
        deadline_hit = True
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        stdout, _ = process.communicate()
    elapsed = time.perf_counter() - wall_start
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    raw = stdout.decode("utf-8", "replace")
    (output / "mallob-full.log").write_text(raw)
    files = [p for p in [solution, *output.glob("answer.sol.*")]
             if p.is_file()]
    verdict, model = parse_results(raw, files)
    witness = False
    if verdict == "SAT" and model:
        sat_model_valid(source, model)
        witness = True
    if expected == "SAT":
        require(verdict == "SAT" and witness and not deadline_hit,
                "tiny SAT control did not solve with valid original witness")
    if expected == "UNSAT":
        require(verdict == "UNSAT" and not deadline_hit,
                "tiny UNSAT control did not return UNSAT")
    record = dict(label=label, source_sha256=sha(source),
                  cohort=cohort, development_only=True, cap_s=cap,
                  elapsed_s=round(elapsed, 6), deadline_hit=deadline_hit,
                  returncode=process.returncode, verdict=verdict,
                  SAT_original_model_valid=witness,
                  UNSAT_independently_proven=False,
                  solution_files=[p.name for p in files],
                  mallob_output_bytes=len(stdout),
                  cpu_user_s=round(after.ru_utime - before.ru_utime, 6),
                  cpu_system_s=round(after.ru_stime - before.ru_stime, 6),
                  mallob_log_sha256=sha(output / "mallob-full.log"),
                  output_tail=raw[-700:])
    (output / "diagnostic.json").write_text(json.dumps(record, sort_keys=True,
                                              indent=2) + "\n")
    print("MALLOB_M1_TRIAL", json.dumps(record, sort_keys=True), flush=True)
    return record


def run():
    require(sha(prev.FROZEN / "manifest.json") == EXPECTED_SHA,
            "frozen input manifest mismatch")
    cases = prev.load()
    ROOT.mkdir(parents=True, exist_ok=True)
    simple = ROOT / "tiny"
    simple.mkdir(exist_ok=True)
    sat = simple / "sat.cnf"
    unsat = simple / "unsat.cnf"
    sat.write_text("p cnf 3 2\n1 2 0\n-2 3 0\n")
    unsat.write_text("p cnf 1 2\n1 0\n-1 0\n")
    rows = [diagnose("smoke-sat", sat, 15., "synthetic_positive_control", "SAT"),
            diagnose("smoke-unsat", unsat, 15., "synthetic_negative_control", "UNSAT")]
    # Frozen deterministic first-in-SHA cohort selection; no runtime tuning.
    for cohort in ("new_seed_synthetic", "reused_external_original"):
        selected = sorted((c for c in cases if c["cohort"] == cohort),
                          key=lambda c: c["sha256"])[0]
        cnf = prev.FROZEN / (selected["id"] + ".cnf")
        require(sha(cnf) == selected["sha256"], "R193 source SHA drift")
        rows.append(diagnose(cohort + "-30s", cnf, 30., cohort))
        rows.append(diagnose(cohort + "-90s", cnf, 90., cohort))
    payload = dict(protocol="MALLOB-M1-FROZEN-R193-DIAGNOSTIC-v1",
                   status="DIAGNOSTIC_PASS", upstream_mallob_commit=
                   "486be632791fac57a03dabeb6d50b799c5e06fe9",
                   source_manifest_sha256=EXPECTED_SHA,
                   results=rows, warning="development used originals only; no blind claim; UNSAT lacks independent proof")
    (ROOT / "report.json").write_text(json.dumps(payload, indent=2,
                                                 sort_keys=True) + "\n")
    print("MALLOB_M1_FINAL", json.dumps(dict(status=payload["status"],
                     controls=2, original_source_SHA_count=2, attempts=len(rows),
                     rows=[{"label":x["label"],"verdict":x["verdict"],
                            "elapsed_s":x["elapsed_s"],
                            "deadline_hit":x["deadline_hit"]} for x in rows])),
          flush=True)


if __name__ == "__main__":
    run()
