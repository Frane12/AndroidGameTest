#!/usr/bin/env python3
"""Original-byte precheck fail-closed smoke on generated correctness controls.

No new blind benchmark or performance claims.
"""
import hashlib,sys,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from unified_evidence.precheck import prove
from unified_evidence.check_preproof import check
from ipg1_fixtures import petersen

def raw(n,clauses,tag):
    return (f"c {tag}\np cnf {n} {len(clauses)}\n"
            +"".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode()

def verify_case(name,data,expect):
    cert=prove(data)
    if cert["status"]!=expect:
        raise AssertionError(name+" got "+cert["status"]+" expected "+expect)
    if expect=="UNSAT_UNCHECKED":
        assert check(data,cert)["status"]=="UNION_PRECHECK_VERIFIED"
        changed=dict(cert,source_sha256="0"*64)
        try:check(data,changed)
        except ValueError:pass
        else:raise AssertionError("altered hash was accepted")
        try:check(data+b"c changed original bytes\n",cert)
        except ValueError:pass
        else:raise AssertionError("altered source was accepted")
    return cert["method"]

def run():
    tests=[
       ("simple_binary_units",raw(1,[(1,),(-1,)],"binary unsat"),"UNSAT_UNCHECKED"),
       ("binary_sat",raw(2,[(1,2),(-1,2)],"binary sat"),"UNKNOWN"),
       ("parity_unsat",raw(2,[(1,2),(-1,-2),(-1,2),(1,-2)],"evenxor vs exactlyone"),"UNSAT_UNCHECKED"),
       ("parity_sat",raw(2,[(1,2),(-1,-2)],"exactlyone only"),"UNKNOWN"),
       ("simple_php",raw(6,[(1,2),(3,4),(5,6),(-1,-3),(-1,-5),(-3,-5),(-2,-4),(-2,-6),(-4,-6)],"php"),"UNSAT_UNCHECKED"),
    ]
    allcases=[]
    for name,source,expect in tests:
        method=verify_case(name,source,expect)
        allcases.append((name,method,expect))
    assert hashlib.sha256(petersen().encode()).hexdigest()=="c2fefeffc1f9644ffd6f85728106a21c82dfc01d0d021f32d4d73569cc2bfb70"
    # Intended to confirm the known source-width limit, not assert
    # a new standard or general SAT proof.
    print("GRAND_UNION_PREFLIGHT_PASS "+json.dumps(allcases),flush=True)

if __name__=="__main__":run()
