#!/usr/bin/env python3
"""Independently verify 60 LTM9 counting proofs for previously tested families."""
import hashlib
import json
import os
import pathlib
import subprocess
import sys

import drnas_atlas13_generator as G
from drnas_ltm9_independent_cert import (parse_dimacs,certificate_from_stdout,
                                         verify_php_certificate)
from drnas_ltm9_refs_unseen import canonical,witness_ok

ROOT=pathlib.Path("ltm9_certaudit")
EXE="mre_atlas23/bin/drnas_ltm9_certificate"
INDICES=tuple(range(311,321))
SEEDS=(17,29,43)
UNSAT_FAMILIES=("pigeonhole_unsat","graph3color_unsat")

def main():
    if ROOT.exists():raise RuntimeError("clean output directory required")
    ROOT.mkdir()
    rows=[]
    for family in UNSAT_FAMILIES+("pigeonhole_sat","graph3color_sat"):
        for index in INDICES:
            n,clauses,_=G.build(family,index)
            original=canonical(n,clauses)
            sha=hashlib.sha256(original).hexdigest()
            path=ROOT/f"{sha}.cnf"
            path.write_bytes(original)
            src=parse_dimacs(path)
            for seed in (SEEDS if family in UNSAT_FAMILIES else (17,)):
                cmd=[EXE,str(path),"--mode","LTM8_FAST","--time","5",
                     "--seed",str(seed),"--policy","1.0,0.85"]
                p=subprocess.run(cmd,capture_output=True,text=True,timeout=6,
                                 env=dict(os.environ,DRNAS_LTM8_MEMORY=""))
                if p.returncode not in (10,20):raise RuntimeError(
                    f"unexpected return code: {family} {index} {p.returncode} {p.stderr[-300:]}")
                certificate=certificate_from_stdout(p.stdout)
                if family in UNSAT_FAMILIES:
                    if p.returncode!=20:raise RuntimeError("UNSAT candidate did not return UNSAT")
                    checked=verify_php_certificate(src,certificate)
                else:
                    if certificate is not None:
                        raise RuntimeError("false PHP certificate on SAT control")
                    if p.returncode!=10 or not witness_ok(n,clauses,p.stdout):
                        raise RuntimeError("SAT control failed original CNF witness check")
                    checked=None
                row=dict(family=family,index=index,seed=seed,sha256=sha,
                         original_source_checked=True,solver_status=p.returncode,
                         certificate=checked)
                rows.append(row)
                print("LTM9_CERT_AUDIT_TRIAL "+json.dumps(row),flush=True)
    assert len(rows)==80
    certified=sum(r["certificate"] is not None for r in rows)
    assert certified==60
    summary=dict(cases=len({r["sha256"] for r in rows}),
                 trials=len(rows),math_certified_unsat=certified,
                 sat_models_verified=20,invalid_certificates=0,
                 independent_checker=True,original_cnf=True,
                 certificate_kind="counting source clauses, not LRAT",
                 source="ATLAS13 synthetic families, same index cohort as LTM9 WIDE")
    (ROOT/"summary.json").write_text(json.dumps(summary,indent=2))
    (ROOT/"trials.jsonl").write_text(
        "".join(json.dumps(r)+"\n" for r in rows))
    print("LTM9_CERT_AUDIT_FINAL "+json.dumps(summary),flush=True)

if __name__=="__main__":main()
