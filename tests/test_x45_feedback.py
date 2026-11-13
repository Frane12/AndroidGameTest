#!/usr/bin/env python3
"""X4.5 native smoke, strict SAT witness/UNSAT small oracle, study invariants."""
from __future__ import annotations
import itertools
import pathlib
import random
import subprocess
import sys
import tempfile

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"research"))
import drnas_x45_trial as T
import drnas_x44_ood as G45
import drnas_x42_1000 as G


def brute_sat(clauses,n):
    for bits in itertools.product((-1,1),repeat=n):
        if all(any(bits[abs(x)-1]==(1 if x>0 else -1) for x in c) for c in clauses):
            return True
    return False


def check_small():
    rng=random.Random(45)
    with tempfile.TemporaryDirectory() as directory:
        root=pathlib.Path(directory)
        for i in range(60):
            n=5
            clauses=[]
            for _ in range(15+i%10):
                width=2+(i%2)
                variables=rng.sample(range(1,n+1),width)
                clauses.append([x if rng.getrandbits(1) else -x for x in variables])
            path=root/f"small_{i}.cnf"
            path.write_text(f"p cnf {n} {len(clauses)}\n"+
                            "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
            true_sat=brute_sat(clauses,n)
            for mode in ("core","x45_sham","x45_fixed","x45_online"):
                cmd=["build/drnas-x45",str(path),"--mode",mode,"--time","0.5","--stats"]
                run=subprocess.run(cmd,capture_output=True,text=True,timeout=2.0)
                if run.returncode not in (10,20):
                    raise AssertionError((i,mode,run.returncode,run.stderr[-500:]))
                if (run.returncode==10)!=true_sat:
                    raise AssertionError((i,mode,"incorrect SAT/UNSAT"))
                if run.returncode==10 and not G.verify_sat(path,run.stdout,n):
                    raise AssertionError((i,mode,"invalid witness"))


def check_medium():
    with tempfile.TemporaryDirectory() as directory:
        root=pathlib.Path(directory)
        G45.SEED_NAMESPACE=T.SEED_NAMESPACE
        for family in ("planted_uniform","novel_xor_duplicate"):
            src=G45.new_source(family,7,root)
            for key in T.BUILD:
                result=T.one(src,key)
                assert result["status"] in ("SAT_VERIFIED","UNKNOWN")
                if key in ("SHAM","FIXED","ONLINE"):
                    assert result["counterfactuals"]>=0
                    assert result["probe_rounds"]>=0
                    if key=="ONLINE":
                        assert result["updates"]==result["feedback"]
                    else:
                        assert result["updates"]==0


def check_math():
    assert T.exact_binomial_test(0,0)==1
    assert T.exact_binomial_test(1,0)==1
    assert T.exact_binomial_test(10,0)<.01
    d=T.bootstrap_difference([1.,2.,3.],[2.,3.,4.],300)
    assert d["observed_sum_s"]==-3
    assert d["bootstrap95_sum_s"]==[-3,-3]
    assert len(T.BUILD)==5


if __name__=="__main__":
    for binary,_,_ in T.BUILD.values():
        assert pathlib.Path(binary).is_file(),binary
    check_math()
    check_small()
    check_medium()
    print("X45_TEST_PASS exact_oracle=60 mode_checks=240 planted_families=2 arms=5")
