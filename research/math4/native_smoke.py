#!/usr/bin/env python3
"""Native MATH4 source-first certificate smoke with complete real CNFs.

A successful native result is counted ONLY when the independent checker
accepts every root unit and every XOR half cube from the original file.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"pcmax_capacity"))
from check_xor_units import verify,InvalidMath4Proof
from check_clause_hall import check as hall_check
from check_capacity import check as bdd_check

def call(binary,cnf,mode,proof,with_drat=False):
    args=[str(binary.resolve()),str(cnf.resolve()),"--mode","core","--time","7",
          "--math4" if mode=="MATH4" else "--hall3",
          "--pcmax-budget-ms","750","--pcmax-certificate",str(proof.resolve())]
    if with_drat:
        args+=["--proof",str(proof.parent/"standard.drat")]
    else:
        args+=["--pcmax-only"]
    start=time.perf_counter()
    p=subprocess.run(args,capture_output=True,text=True,timeout=9)
    elapsed=time.perf_counter()-start
    tele=[json.loads(l[len("c PCMAX_CAPACITY "):])
          for l in p.stdout.splitlines() if l.startswith("c PCMAX_CAPACITY ")]
    return p,elapsed,tele[-1] if tele else {}

def certify(cnf,proof):
    cert=json.loads(proof.read_text())
    raw=cnf.read_bytes()
    fmt=cert.get("format")
    if fmt=="drnas-math4-xor-unit-v1":
        c=verify(raw,cert)
        assert c["status"]=="UNSAT_VERIFIED"
    elif fmt=="pcmax-clause-hall-v1":
        c=hall_check(raw,cert)
        assert c["status"]=="UNSAT_CLAUSE_HALL_CERTIFICATE_VERIFIED"
    elif fmt=="pcmax-capacity-v1":
        c=bdd_check(raw,cert)
    else:
        raise AssertionError(("UNSUPPORTED CERTIFICATE",fmt))
    return c,fmt

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--binary",type=Path,required=True)
    a.add_argument("--out",type=Path,required=True)
    args=a.parse_args()
    args.out.mkdir(parents=True,exist_ok=False)
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    manifest=json.loads(Path("research/hall3/manifest.json").read_text())
    cases={x["id"]:x for x in manifest["sources"]}
    results=[]
    for idx in (6,7,10,11,17):
        src=cases[idx]
        cnf=Path(src["path"])
        raw=cnf.read_bytes()
        assert hashlib.sha256(raw).hexdigest()==src["sha256"]
        modes=("MATH4","HALL3") if idx==7 else ("MATH4",)
        for mode in modes:
            cert=args.out/(f"original_{idx}_{mode}.json")
            p,elapsed,tele=call(args.binary,cnf,mode,cert)
            if p.returncode==20:
                assert cert.is_file(),(idx,mode,"missing certificate")
                t=time.perf_counter()
                check,fmt=certify(cnf,cert)
                check_s=time.perf_counter()-t
                assert src["catalog_label"]!="sat",("FALSE UNSAT",idx,mode)
                status="UNSAT_VERIFIED"
            elif p.returncode==0 and "s UNKNOWN" in p.stdout:
                assert not cert.exists()
                check_s=0
                fmt=None
                status="UNKNOWN"
            else:
                raise AssertionError((idx,mode,p.returncode,p.stdout[-600:],p.stderr[-600:]))
            r={"id":idx,"family":src["family"],"mode":mode,
               "status":status,"certificate_format":fmt,
               "native_s":round(elapsed,6),"checker_s":round(check_s,6),
               "reason":tele.get("reason","missing"),"source_sha256":src["sha256"]}
            results.append(r)
            print("MATH4_NATIVE_SMOKE "+json.dumps(r,sort_keys=True),flush=True)
    new=[r for r in results if r["id"]==7 and r["mode"]=="MATH4"][0]
    assert new["status"]=="UNSAT_VERIFIED" and new["certificate_format"]=="drnas-math4-xor-unit-v1",new
    assert not any(r["status"]=="UNSAT_VERIFIED" and r["id"]==6 for r in results)
    # It must be possible to fall back to the unchanged CF7 SAT path with
    # standard DRAT output configured independently of structural certificates.
    sat=args.out/"tiny_sat.cnf"
    sat.write_bytes(b"p cnf 2 1\n1 2 0\n")
    cert=args.out/"tiny_sat_structural.json"
    p,elapsed,tele=call(args.binary,sat,"MATH4",cert,with_drat=True)
    assert p.returncode==10 and "s SATISFIABLE" in p.stdout and not cert.exists(),(p.returncode,p.stdout,p.stderr)
    rows=[int(x) for l in p.stdout.splitlines() if l.startswith("v ") for x in l.split()[1:] if x!="0"]
    assert any(x in (1,2) for x in rows),rows
    summary={"cases":len(results),"cpu":cpu,"certified":sum(r["status"]=="UNSAT_VERIFIED" for r in results),
             "math4_real_lightsout_certified":True,"sat_fallback_pass":True,
             "rows":results}
    (args.out/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print("MATH4_NATIVE_SMOKE_PASS "+json.dumps({k:summary[k] for k in
          ("cases","cpu","certified","math4_real_lightsout_certified","sat_fallback_pass")},sort_keys=True),flush=True)
if __name__=="__main__":main()
