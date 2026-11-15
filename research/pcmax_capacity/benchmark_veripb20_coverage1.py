#!/usr/bin/env python3
"""Retrospective coverage audit: existing PCMAX20 originals, optional VeriPB3 proof.

The solver and the proof producer see only frozen original DIMACS bytes.
Labels are read after the result is determined, for adversarial SAT controls.
This is not a blind dataset and never upgrades UNKNOWN to UNSAT without VeriPB.
One logical CPU, sequential cases, bounded processes and proof sizes.
"""
import hashlib
import json
import os
import resource
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "research/pcmax_capacity"))
from benchmark import materialize
from check_capacity import check

BASE = ROOT / "results/veripb20"
ORIGINALS = ROOT / "originals/veripb20"
MANIFEST = ROOT / "research/pcmax_capacity/sources20.json"
BIN = ROOT / "build/drnas-pcmax"
PRODUCER = ROOT / "research/pcmax_capacity/emit_veripb_capacity1.py"
CHECKER = ROOT / "veripb-tool/bin/veripb"
LIMIT = 35 * 1024 * 1024

def limit_file_size():
    resource.setrlimit(resource.RLIMIT_FSIZE, (LIMIT, LIMIT))

def execute(argv, timeout, proof_limit=False):
    begin = time.perf_counter()
    try:
        p = subprocess.run([str(x) for x in argv], capture_output=True, text=True,
                           timeout=timeout, preexec_fn=limit_file_size if proof_limit else None)
        return {"rc":p.returncode, "elapsed_s":round(time.perf_counter()-begin,6),
                "output": (p.stdout or "")+"\n"+(p.stderr or ""), "timeout":False}
    except subprocess.TimeoutExpired as e:
        return {"rc":None,"elapsed_s":round(time.perf_counter()-begin,6),
                "output": "timeout (bound exceeded)", "timeout":True}

def main():
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    BASE.mkdir(parents=True,exist_ok=True)
    ORIGINALS.mkdir(parents=True,exist_ok=True)
    entries=json.loads(MANIFEST.read_text())["entries"]
    assert len(entries)==20 and len({e["sha256"] for e in entries})==20
    rows=[]
    failures=[]
    for idx,e in enumerate(entries):
        key=e["sha256"][:12]
        case=BASE/f"{idx:02d}_{key}"
        case.mkdir(exist_ok=False)
        row={"index":idx,"name":e["name"],"original_sha256":e["sha256"],
             "catalog_label":e["expected_status"],"phase":"source","outcome":"UNKNOWN",
             "veripb_accepted":False}
        start=time.perf_counter()
        try:
            source=materialize(e,ORIGINALS,True)
            raw=source.read_bytes()
            assert hashlib.sha256(raw).hexdigest()==e["sha256"]
            row["source_bytes"]=len(raw)
            cert=case/"capacity.json"
            native=execute([BIN,source.resolve(),"--mode","core","--time","7",
                            "--pcmax-only","--pcmax-capacity","--pcmax-budget-ms","5000",
                            "--pcmax-certificate",cert.resolve()],12)
            row["native_rc"]=native["rc"]
            row["native_s"]=native["elapsed_s"]
            row["native_timeout"]=native["timeout"]
            (case/"native.log").write_text(native["output"][-20000:])
            if native["rc"]==0 and "s UNKNOWN" in native["output"]:
                assert not cert.exists(), "UNKNOWN left certificate"
                row["phase"]="native_unknown"
                row["outcome"]="NATIVE_UNKNOWN"
            elif native["rc"]==20 and "s UNSATISFIABLE" in native["output"]:
                assert cert.is_file(),"UNSAT lacks certificate"
                structural=check(raw,json.loads(cert.read_text()))
                assert structural["status"]=="UNSAT_STRUCTURAL_CERTIFICATE_VERIFIED"
                row["demand"]=structural["required"]
                row["capacity"]=structural["capacity_sum"]
                row["phase"]="structurally_verified"
                if e["expected_status"]=="SAT":
                    failures.append(e["name"]+": native UNSAT on SAT-labelled input")
                    row["outcome"]="SAT_CONTROL_CONFLICT"
                else:
                    proof=case/"proof.pbp"
                    emitted=execute([sys.executable,PRODUCER,"--cnf",source,
                                     "--certificate",cert,"--output",proof],30,True)
                    row["producer_s"]=emitted["elapsed_s"]
                    row["producer_rc"]=emitted["rc"]
                    (case/"producer.log").write_text(emitted["output"][-5000:])
                    if emitted["rc"]!=0 or not proof.exists() or not proof.stat().st_size:
                        row["outcome"]="PROOF_NOT_EMITTED"
                        proof.unlink(missing_ok=True)
                    else:
                        row["proof_bytes"]=proof.stat().st_size
                        row["proof_sha256"]=hashlib.sha256(proof.read_bytes()).hexdigest()
                        chk=execute([CHECKER,"--cnf",source,proof],60)
                        row["veripb_rc"]=chk["rc"]
                        row["veripb_s"]=chk["elapsed_s"]
                        (case/"veripb.log").write_text(chk["output"][-5000:])
                        accepted=(chk["rc"]==0 and "s VERIFIED UNSATISFIABLE" in chk["output"])
                        row["veripb_accepted"]=accepted
                        if accepted:
                            row["phase"]="veripb_verified"
                            row["outcome"]="VERIPB_UNSAT_VERIFIED"
                        else:
                            row["outcome"]="VERIPB_REJECTED_OR_TIMEOUT"
                            failures.append(e["name"]+": generated proof not independently accepted")
                        if not accepted:
                            proof.unlink(missing_ok=True)
            else:
                row["phase"]="native_error"
                row["outcome"]="NATIVE_ERROR"
                failures.append(e["name"]+": native nonstandard result "+str(native["rc"]))
        except Exception as exc:
            row["outcome"]="AUDIT_ERROR"
            row["error"]=str(exc)[:500]
            failures.append(e["name"]+": "+str(exc)[:500])
        row["end_to_end_s_excluding_download"]=round(
            sum(row.get(k,0) for k in ("native_s","producer_s","veripb_s")),6)
        row["total_wall_s_including_download"]=round(time.perf_counter()-start,6)
        rows.append(row)
        (BASE/"summary.json").write_text(json.dumps({
            "experiment":"retrospective PCMAX20 VeriPB3 coverage",
            "single_logical_cpu":cpu, "not_blind":True,
            "source_count":len(entries),"completed":len(rows),
            "verified_veripb_count":sum(r["veripb_accepted"] for r in rows),
            "structural_certified_count":sum(r.get("phase") in ("structurally_verified","veripb_verified") or r["outcome"] in
                 ("PROOF_NOT_EMITTED","VERIPB_REJECTED_OR_TIMEOUT") for r in rows),
            "false_unsat_on_sat_controls":sum(r["outcome"]=="SAT_CONTROL_CONFLICT" for r in rows),
            "errors":failures,"rows":rows},indent=2,sort_keys=True)+"\n")
        print("VERIPB20_CASE "+json.dumps(row,sort_keys=True),flush=True)
    print("VERIPB20_SUMMARY "+json.dumps({
        "total":len(rows), "veripb_verified":sum(r["veripb_accepted"] for r in rows),
        "native_unknown":sum(r["outcome"]=="NATIVE_UNKNOWN" for r in rows),
        "proof_not_emitted":sum(r["outcome"]=="PROOF_NOT_EMITTED" for r in rows),
        "failures":len(failures),"sat_control_conflicts":sum(r["outcome"]=="SAT_CONTROL_CONFLICT" for r in rows)
        },sort_keys=True),flush=True)
    return 2 if failures else 0

if __name__=="__main__":
    sys.exit(main())
