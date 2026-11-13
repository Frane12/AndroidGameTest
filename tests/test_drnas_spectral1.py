#!/usr/bin/env python3
"""Safety oracle: SPECTRAL1 OFF/ON same binary; SAT model and DRAT UNSAT checks."""
import itertools
import json
import os
import pathlib
import random
import subprocess
import sys
import tempfile

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"research"))
import drnas_x55_cpu_real36 as baseline

BIN=pathlib.Path("build/drnas-spectral1").resolve()
DRAT=pathlib.Path("build/drat-trim").resolve()

def solve(cnf, enabled):
    name="on" if enabled else "off"
    proof=cnf.parent/(cnf.stem+"_"+name+".drat")
    proof.unlink(missing_ok=True)
    cmd=[str(BIN),str(cnf),"--mode","core","--time","3","--stats","--proof",str(proof)]
    if enabled:cmd+=["--spectral1"]
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=6)
    assert p.returncode in (10,20),(cnf,p.returncode,p.stderr[-1000:])
    stats=[json.loads(l.split(" ",1)[1]) for l in p.stderr.splitlines()
           if l.startswith("SPECTRAL1_STATS ")]
    assert len(stats)==1 and stats[0].get("enabled") == enabled,stats
    n,clauses=baseline.parse_cnf(cnf.read_bytes())
    if p.returncode==10:
        assert baseline.check_sat(p.stdout,clauses,n),(cnf,p.stdout[-500:])
        result="SAT"
    else:
        checked=subprocess.run([str(DRAT),str(cnf),str(proof)],
                               capture_output=True,text=True,timeout=10)
        assert checked.returncode==0 and "s VERIFIED" in checked.stdout,(cnf,checked.stderr[-500:])
        result="UNSAT"
    return result,stats[0]

def main():
    assert BIN.is_file() and os.access(BIN,os.X_OK),"spectral solver not executable"
    assert DRAT.is_file() and os.access(DRAT,os.X_OK),"DRAT checker not executable"
    cases=[
      ("parity",3,[(-1,2,3),(1,-2,3),(1,2,-3),(-1,-2,-3)],"SAT"),
      ("unit_unsat",1,[(1,),(-1,)],"UNSAT"),
      ("unsat_three",2,[(1,2),(1,-2),(-1,2),(-1,-2)],"UNSAT"),
      ("all_three_unsat",3,[tuple(-i if (mask>>(i-1))&1 else i
                        for i in range(1,4)) for mask in range(8)],"UNSAT"),
      ("mixed_sat",5,[(1,2,3),(-1,2),(-2,3),(3,4,5)],"SAT"),
    ]
    # Random planted CNFs: known SAT witness is independent of solver.
    for i in range(12):
        rng=random.Random(271800+i)
        n=16
        witness=[bool(rng.randrange(2)) for _ in range(n)]
        clauses=[]
        for j in range(75):
            variables=rng.sample(range(1,n+1),3)
            lits=[v if rng.randrange(2) else -v for v in variables]
            if not any(witness[abs(l)-1] == (l>0) for l in lits):
                v=variables[0]
                lits[0]=v if witness[v-1] else -v
            clauses.append(tuple(lits))
        cases.append((f"planted_{i}",n,clauses,"SAT"))
    report={"formulas":len(cases),"checked_outputs":0,
            "verified_unsat":0,"spectral_windows_active":0,
            "rank_reduced":0,"biased_variables":0}
    with tempfile.TemporaryDirectory() as temp:
        path=pathlib.Path(temp)
        for label,n,clauses,expected in cases:
            p=path/(label+".cnf")
            p.write_text(f"p cnf {n} {len(clauses)}\n"+
                "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
            off,t_off=solve(p,False)
            on,t_on=solve(p,True)
            assert off==on==expected,(label,off,on)
            assert t_off["windows_analyzed"]==0
            report["checked_outputs"]+=2
            report["verified_unsat"]+=2*int(expected=="UNSAT")
            report["spectral_windows_active"]+=t_on["windows_active"]
            report["rank_reduced"]+=t_on["rank_reduced_windows"]
            report["biased_variables"]+=t_on["variables_biased"]
            if label=="parity":
                assert t_on["windows_active"]>0 and t_on["rank_reduced_windows"]>0,t_on
                assert t_on["variables_biased"]>=3,t_on
    assert report["spectral_windows_active"]>0
    report["same_binary_ab"]=True
    report["no_unverified_learned_clauses"]=True
    print("SPECTRAL1_SELFTEST_PASS "+json.dumps(report,sort_keys=True))

if __name__=="__main__":main()
