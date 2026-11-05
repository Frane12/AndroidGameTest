#!/usr/bin/env python3
"""R133c native CaDiCaL paired communication test. Known SATLIB PARITY controls.

This is a development benchmark, NOT blind holdout, not Kissat integration,
not a record claim. The source XOR exporter independently checks original CNF.
R133c pairs certified rows and emits only exact GF(2) consequences.
"""
import argparse
import csv
import hashlib
import itertools
import json
import pathlib
import random
import re
import subprocess
import sys
import time

CAP = 10.0
REPS = 2
MODES = ("clean", "active", "gf2")


def parity_cnf(variables, rhs):
    out = []
    for bits in itertools.product((0, 1), repeat=len(variables)):
        if sum(bits) % 2 != rhs:
            out.append(tuple(-v if b else v for v, b in zip(variables, bits)))
    return out


def fixture(out):
    # Two independent XOR cancellations generate 3^4=0 and 5^6=0;
    # R133c then combines these two certified derived rows into 3^4^5^6=0.
    clauses = (parity_cnf((1, 2, 3), 0) +
               parity_cnf((1, 2, 4), 0) +
               parity_cnf((2, 3, 5), 0) +
               parity_cnf((2, 3, 6), 0) + [(3,)])
    path = out / "fixture.cnf"
    text = "p cnf 6 %d\n" % len(clauses)
    text += "".join(" ".join(map(str, c)) + " 0\n" for c in clauses)
    path.write_text(text)
    return path


def verified_rows(cnf, out, label):
    rows = out / (label + ".tsv")
    proof = out / (label + "-source-proof.json")
    started = time.perf_counter()
    subprocess.run([sys.executable, "research/r93_export_verified_rows.py",
                    "export", "--cnf", str(cnf), "--rows", str(rows),
                    "--evidence", str(proof)],
                   check=True, timeout=40, capture_output=True, text=True)
    prep_s = time.perf_counter() - started
    source = json.loads(proof.read_text())
    assert source["exported"] >= 0
    return rows, proof, source, prep_s


def metric(output, key):
    match = re.search(r"(?:^|\s)" + re.escape(key) + r"=([^\s]+)", output)
    return match.group(1) if match else None


def native_run(binary, mode, cnf, rows, prep_s=0.0):
    cmd = [str(binary), mode, str(cnf), str(rows)]
    started = time.perf_counter()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=max(0.02, CAP-prep_s))
        wall = time.perf_counter() - started
    except subprocess.TimeoutExpired:
        return dict(status="TIMEOUT", solve_wall_s=round(CAP-prep_s,6),
                    prep_s=round(prep_s,6), total_s=CAP, par2_s=2*CAP,
                    result_code=124, disabled=None,
                    source_rows=0, derived_rows=0, emitted=0,
                    assignments=0, backtracks=0, rows_scanned=0)
    if proc.returncode not in (10, 20):
        raise RuntimeError("native bridge error: %s rc=%d\nstdout=%s\nstderr=%s" %
                           (mode, proc.returncode, proc.stdout[-1500:], proc.stderr[-1500:]))
    if "R133C_RESULT" not in proc.stdout or "R99_RESULT" not in proc.stdout:
        raise RuntimeError("missing telemetry: " + proc.stdout[-1500:])
    if metric(proc.stdout, "disabled") != "0":
        raise RuntimeError("native callback/watch invariant failed: " + proc.stdout[-1500:])
    status = "SAT" if proc.returncode == 10 else "UNSAT"
    if status == "SAT" and metric(proc.stdout, "sat_model_checked") != "1":
        raise RuntimeError("SAT source CNF witness unchecked")
    if wall + prep_s > CAP:
        status = "TIMEOUT"
    return dict(status=status, solve_wall_s=round(wall,6),
                prep_s=round(prep_s,6), total_s=round(wall+prep_s,6),
                par2_s=round(2*CAP if status=="TIMEOUT" else wall+prep_s,6),
                result_code=proc.returncode, disabled=0,
                source_rows=int(metric(proc.stdout, "source_rows")),
                derived_rows=int(metric(proc.stdout, "derived_rows")),
                emitted=int(metric(proc.stdout, "clauses_emitted")),
                assignments=int(metric(proc.stdout, "assignments")),
                backtracks=int(metric(proc.stdout, "backtracks")),
                rows_scanned=int(metric(proc.stdout, "rows_scanned")))


def select_controls(root):
    paths = sorted(p for p in root.rglob("*.cnf") if p.stat().st_size < 2_000_000)
    assert len(paths) >= 6, "SATLIB PARITY source has fewer than 6 files"
    chosen = sorted({paths[0], paths[1], paths[len(paths)//2],
                     paths[len(paths)//2+1], paths[-2], paths[-1]})
    assert len(chosen) == 6
    return chosen


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--binary", required=True, type=pathlib.Path)
    ap.add_argument("--satlib", required=True, type=pathlib.Path)
    ap.add_argument("--out", required=True, type=pathlib.Path)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    src = fixture(a.out)
    rows, proof, evidence, prep = verified_rows(src, a.out, "fixture")
    assert evidence["exported"] >= 2, evidence
    fixture_runs = {mode:native_run(a.binary,mode,src,rows,prep if mode!="clean" else 0)
                    for mode in MODES}
    assert all(r["status"]=="SAT" for r in fixture_runs.values()), fixture_runs
    assert fixture_runs["gf2"]["derived_rows"] >= 1, fixture_runs
    (a.out/"fixture-results.json").write_text(json.dumps(fixture_runs,indent=2)+"\n")
    print("R133C_NATIVE_FIXTURE_PASS",json.dumps(fixture_runs,sort_keys=True),flush=True)

    files = select_controls(a.satlib)
    manifest = [dict(file=p.name, sha256=hashlib.sha256(p.read_bytes()).hexdigest())
                for p in files]
    (a.out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    records = []
    for source in files:
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        source_rows, evidence_path, evidence, prep = verified_rows(
            source, a.out, digest[:12])
        for rep in range(REPS):
            order=list(MODES)
            random.Random(digest+str(rep)).shuffle(order)
            for mode in order:
                cost=0 if mode=="clean" else prep
                row=native_run(a.binary,mode,source,source_rows,cost)
                row.update(formula=source.name,sha256=digest,rep=rep,mode=mode,
                           exported_source_rows=evidence["exported"],
                           xor_proof_sha256=hashlib.sha256(evidence_path.read_bytes()).hexdigest())
                records.append(row)
        print("R133C_CASE",source.name,"original_rows",evidence["exported"],
              "prep_s",round(prep,5),flush=True)
    assert len(records)==6*2*len(MODES)==36
    for source in files:
        for rep in range(REPS):
            answers={r["status"] for r in records
                     if r["formula"]==source.name and r["rep"]==rep
                     and r["status"]!="TIMEOUT"}
            assert len(answers)<=1,(source,rep,answers)
    with (a.out/"paired.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    totals={}
    for mode in MODES:
        x=[r for r in records if r["mode"]==mode]
        totals[mode]=dict(par2_s=round(sum(r["par2_s"] for r in x),6),
                          solved=sum(r["status"]!="TIMEOUT" for r in x),
                          emitted=sum(r["emitted"] for r in x),
                          derived_rows=sum(r["derived_rows"] for r in x),
                          assignments=sum(r["assignments"] for r in x),
                          backtracks=sum(r["backtracks"] for r in x),
                          rows_scanned=sum(r["rows_scanned"] for r in x))
    base=totals["clean"]["par2_s"]
    summary=dict(protocol="DRNAS-R133C-NATIVE-PAIRWISE-GF2-CDCL-DEVELOPMENT-20261105",
                 scope="6 REUSED SATLIB PARITY originals, 2 repeats; not unseen; CaDiCaL rel-2.1.0 not Kissat",
                 trials=len(records),formulas=len(files),cap_s=CAP,
                 sat_model_verified=True,source_xor_rows_verified=True,
                 derived_rows_proven_by_exact_pairwise_XOR=True,
                 independent_unsat_proofs=False,
                 preparation_cost_charged_to_active_and_gf2=True,
                 modes=totals,
                 gf2_gain_over_clean_pct=round(100*(base-totals["gf2"]["par2_s"])/base,5),
                 gf2_gain_over_active_pct=round(
                     100*(totals["active"]["par2_s"]-totals["gf2"]["par2_s"])
                     /totals["active"]["par2_s"],5))
    (a.out/"audit.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    print("R133C_NATIVE_AUDIT",json.dumps(summary,sort_keys=True),flush=True)


if __name__=="__main__":
    main()
