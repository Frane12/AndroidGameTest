#!/usr/bin/env python3
"""Convert an original-CNF DRNAS structural UNSAT certificate to standard DRAT.

No UNSAT is accepted from structural metadata alone. Verify source SHA and
source clauses first, generate extension/RUP steps, then independently check
the complete original CNF + proof using an external DRAT checker.
"""
import argparse,json,subprocess,sys,time
from pathlib import Path
import hall_er_drat,xor_dp_drat

def convert(cnf,structural,proof,checker,limit):
    data=json.loads(structural.read_text())
    begin=time.perf_counter()
    try:
        if data.get("format")=="pcmax-clause-hall-v1":
            result=hall_er_drat.generate(cnf,data,proof)
            method="PHP_HALL_EXTENDED_RESOLUTION"
        elif data.get("format")=="drnas-math5-eo-xor-unit-v1" and data.get("xor_rows"):
            result=xor_dp_drat.generate(cnf,data,proof,max_s=min(2.0,limit))
            method="XOR_TSEITIN_RUP_ELIMINATION"
        else:
            raise ValueError("unsupported structural certificate; abstaining")
        remaining=limit-(time.perf_counter()-begin)
        if remaining<=0:raise TimeoutError("no remaining proof-check budget")
        p=subprocess.run([str(checker),str(cnf),str(proof)],capture_output=True,
                         text=True,timeout=remaining)
        if p.returncode!=0 or "s VERIFIED" not in p.stdout:
            raise RuntimeError("independent DRAT verification failed")
    except Exception:
        proof.unlink(missing_ok=True)
        raise
    result.update(method=method,verified=True,checker="drat-trim",
                  strict_e2e_s=round(time.perf_counter()-begin,6))
    return result

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("cnf",type=Path)
    ap.add_argument("structural_cert",type=Path)
    ap.add_argument("out_drat",type=Path)
    ap.add_argument("--checker",type=Path,required=True)
    ap.add_argument("--limit-s",type=float,default=5.0)
    a=ap.parse_args()
    try:
        print(json.dumps(convert(a.cnf,a.structural_cert,a.out_drat,
                                 a.checker,a.limit_s),sort_keys=True))
    except Exception as ex:
        print("NOT_VERIFIED "+repr(ex),file=sys.stderr)
        sys.exit(1)
if __name__=="__main__":main()
