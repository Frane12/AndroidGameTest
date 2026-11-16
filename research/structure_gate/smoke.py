#!/usr/bin/env python3
"""Fail-closed native smoke test: eligibility != proof, no mistaken SAT/UNSAT."""
import hashlib
import itertools
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"build/drnas-x59-structure-gate1"
CHECK=ROOT/"research/math5/check_math5.py"
EMIT=ROOT/"research/math5/emit_veripb_eo_multiplicity.py"
VERIPB=ROOT/"veripb-tool/bin/veripb"

def execute(cmd,timeout=15):
    r=subprocess.run([str(x) for x in cmd],cwd=ROOT,
        capture_output=True,text=True,timeout=timeout)
    return r

def rows_from_stats(s):
    found={}
    for line in s.splitlines():
        for key in ("STRUCTURE_GATE_STATS","MATH5_UNIFIED_STATS"):
            if line.startswith(key+" "):
                found[key]=json.loads(line[len(key)+1:])
    return found

def fixture():
    groups=[[1,2,3,4],[1,2,5,6],[3,4,5,6]]
    clauses=[]
    for g in groups:
        clauses.append(g)
        clauses.extend([[-a,-b] for a,b in itertools.combinations(g,2)])
    return ("p cnf 6 "+str(len(clauses))+"\n"+
            "".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode()

def main():
    test=ROOT/"build/structure_gate1/structure_gate_unit"
    subprocess.run(["g++","-std=c++20","-O2", "-I"+str(ROOT/"src"),
        str(ROOT/"research/structure_gate/selftest.cpp"),"-o",str(test)],
        cwd=ROOT,check=True)
    local=execute([test])
    assert local.returncode==0 and "STRUCTURE_GATE_UNIT_PASS " in local.stdout,local.stderr
    assert BIN.is_file() and VERIPB.is_file()
    with tempfile.TemporaryDirectory(prefix="drnas-structure-gate-smoke-") as td:
        work=Path(td)
        src=work/"original.cnf";src.write_bytes(fixture())
        # Same binary and mathematical engine ON vs OFF, one process each.
        times={}
        for variant,gate_ms in (("ON",15),("OFF",0)):
            cert=work/(variant+".json");drat=work/(variant+".drat")
            cmd=[BIN,src,"--mode","core","--time","5",
                 "--sat-construct-ms","0","--math5-ms","100",
                 "--structure-gate-ms",str(gate_ms),
                 "--math5-certificate",cert,"--proof",drat,"--stats"]
            proc=execute(cmd,10)
            assert proc.returncode==20 and "s UNSATISFIABLE" in proc.stdout,(
                variant,proc.returncode,proc.stdout,proc.stderr[-1500:])
            stats=rows_from_stats(proc.stderr)
            gate=stats.get("STRUCTURE_GATE_STATS",{})
            math=stats.get("MATH5_UNIFIED_STATS",{})
            assert cert.is_file() and math.get("found") is True,(variant,math)
            if variant=="ON":
                assert gate.get("selected_math5") is True,(variant,gate)
                assert gate.get("reason")=="EXACT_ONE_MULTIGROUP",(variant,gate)
            else:
                assert gate.get("selected_math5") is False,(variant,gate)
            assert not drat.is_file() or drat.stat().st_size==0,(
                "mixed proof path on mathematical UNSAT",drat.stat().st_size)
            checked=execute([sys.executable,CHECK,src,cert])
            assert checked.returncode==0 and "UNSAT_MATH5_CERTIFICATE_VERIFIED" in checked.stdout
            pb=work/(variant+".pbp")
            emitted=execute([sys.executable,EMIT,"--cnf",src,
                "--certificate",cert,"--output",pb],10)
            assert emitted.returncode==0 and pb.is_file(),emitted.stdout+emitted.stderr
            external=execute([VERIPB,"--cnf",src,pb],10)
            assert external.returncode==0 and "s VERIFIED UNSATISFIABLE" in (
                external.stdout+external.stderr),external.stdout+external.stderr
            times[variant]={"gate":gate,"math":math}
        sat=work/"sat.cnf"
        sat.write_text("p cnf 4 3\n1 2 0\n-1 3 0\n2 4 0\n")
        cert=work/"sat.json";drat=work/"sat.drat"
        found=execute([BIN,sat,"--mode","core","--time","5",
                       "--math5-ms","100","--structure-gate-ms","15",
                       "--math5-certificate",cert,"--proof",drat,"--stats"],10)
        assert found.returncode==10 and "s SATISFIABLE" in found.stdout,found.stdout+found.stderr
        logs=rows_from_stats(found.stderr)
        assert logs["STRUCTURE_GATE_STATS"]["selected_math5"] is False
        assert not cert.exists(),"gate invented structural proof on SAT"
        # Fail-closed source tamper: original SHA is bound by independent checker.
        tampered=work/"tampered.cnf"
        tampered.write_bytes(fixture()+b"c changed source bytes\n")
        rejection=execute([sys.executable,CHECK,tampered,work/"ON.json"])
        assert rejection.returncode!=0, "tampered input wrongly certified"
    print("STRUCTURE_GATE_SMOKE_PASS "+json.dumps({
        "strict_veripb_original":True,"independent_source_check":True,
        "original_tampering_rejected":True,"cdcl_sat_fallback":True,
        "math5_on_off_same_binary":True,"gate_on_reason":times["ON"]["gate"]["reason"],
        "unverified_claims":0},sort_keys=True),flush=True)

if __name__=="__main__":main()
