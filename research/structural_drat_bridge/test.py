#!/usr/bin/env python3
"""End-to-end DRNAS structural-to-standard-DRAT GitHub smoke on 8 SHA-pinned CNFs.

Every UNSAT is accepted only after drat-trim confirms a generated proof
against the exact original DIMACS. All steps stay on one logical CPU core.
This is retrospective synthetic development, not a blind official leaderboard.
"""
from collections import Counter
from pathlib import Path
import hashlib,json,os,subprocess,tempfile,time,sys
from fixtures import regenerate
from hall_er_drat import generate as hall_drat
from xor_dp_drat import generate as xor_drat

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
B=ROOT/"build"
DRNAS=B/"drnas-unified-core1"
CHECKER=B/"drat-trim"
OUT=ROOT/"bridge8_results"

def command(args,seconds=5):
    cpu=min(os.sched_getaffinity(0))
    def pin():os.sched_setaffinity(0,{cpu})
    return subprocess.run([str(a) for a in args],text=True,capture_output=True,
                          timeout=seconds,preexec_fn=pin)

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    cases=regenerate(OUT/"frozen_cnf")
    results=[]
    for name,cnf,sha in cases:
        dest=OUT/"proofs"/name
        dest.mkdir(parents=True,exist_ok=True)
        cert=dest/"source_structural.json"
        proof=dest/"converted.drat"
        assert not cert.exists() and not proof.exists()
        start=time.perf_counter()
        sol=command((DRNAS,cnf,"--time","5","--certificate",cert),seconds=5)
        assert sol.returncode==20 and "s UNSATISFIABLE" in sol.stdout,(name,sol.returncode,sol.stderr)
        obj=json.loads(cert.read_text())
        assert obj["source_sha256"]==sha
        if obj["format"]=="pcmax-clause-hall-v1":
            detail=hall_drat(cnf,obj,proof);method="HALL_ER"
        elif obj["format"]=="drnas-math5-eo-xor-unit-v1" and obj.get("xor_rows"):
            detail=xor_drat(cnf,obj,proof,max_s=2);method="XOR_DP_RUP"
        else:raise RuntimeError("UNSUPPORTED_CERT "+name)
        verified=command((CHECKER,cnf,proof),seconds=5)
        assert verified.returncode==0 and "s VERIFIED" in verified.stdout,(name,verified.stderr,verified.stdout)
        (dest/"checker.log").write_text(verified.stdout+"\n"+verified.stderr)
        elapsed=time.perf_counter()-start
        result=dict(name=name,source_sha256=sha,method=method,verified=True,
                    e2e_s=round(elapsed,6),proof_sha256=hashlib.sha256(proof.read_bytes()).hexdigest(),**detail)
        results.append(result)
        print("BRIDGE8_VERIFIED",json.dumps(result,sort_keys=True),flush=True)
    # Fail closed on altered source hashes and corrupted source-backed certificates.
    name,cnf,sha=cases[0]
    correct=json.loads((OUT/"proofs"/name/"source_structural.json").read_text())
    evil=dict(correct,source_sha256="0"*64)
    with tempfile.TemporaryDirectory() as tmp:
        try:hall_drat(cnf,evil,Path(tmp)/"invalid.drat")
        except ValueError:pass
        else:raise AssertionError("tampered SHA unexpectedly accepted")
        evil=dict(correct,alo_groups=[[999999]]+correct["alo_groups"][1:])
        try:hall_drat(cnf,evil,Path(tmp)/"invalid2.drat")
        except ValueError:pass
        else:raise AssertionError("altered group unexpectedly accepted")
        partial=Path(tmp)/"invalid-proof.drat"
        proof=(OUT/"proofs"/name/"converted.drat").read_text()
        assert proof.endswith("0\n")
        partial.write_text("\n".join(proof.splitlines()[:4])+"\n")
        check=command((CHECKER,cnf,partial),seconds=5)
        assert check.returncode!=0 or "s VERIFIED" not in check.stdout,"truncated DRAT falsely accepted"
    final=dict(cases=8,verified=len(results),total_e2e_s=round(sum(z["e2e_s"] for z in results),6),
               method_counts=dict(Counter(z["method"] for z in results)),
               checks=["exact source SHA","source CNF structural clauses","external drat-trim",
                       "negative SHA/group/tampered proof"],
               kind="retrospective pre-frozen synthetic development, NOT original official")
    (OUT/"final.json").write_text(json.dumps(final,sort_keys=True,indent=2)+"\n")
    print("BRIDGE8_FINAL",json.dumps(final,sort_keys=True),flush=True)
    assert final["verified"]==8
if __name__=="__main__":main()
