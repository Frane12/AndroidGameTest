#!/usr/bin/env python3
"""DRNAS 2SAT UP-CLOSURE1: differential against original binary guard,
exhaustive oracle for small CNFs, and independent clause-by-clause RUP replay.
Includes polarity changes, permutations, wide-clause disguises, and random CNFs.
"""
import itertools
import pathlib
import random
import runpy
import subprocess
import sys
import tempfile

old_exe=pathlib.Path(sys.argv[1]).resolve()
new_exe=pathlib.Path(sys.argv[2]).resolve()
lib=runpy.run_path("tests/test_drnas_2sat_guard.py")
sat=lib["sat"]
rup_check=lib["rup_check"]
permute=lib["permute"]
check=lib["check"]
rng=random.Random(20261115)

def execute(exe,n,clauses,tmp,key):
    f=tmp/(key+".cnf")
    proof=tmp/(key+".drat")
    f.write_text(f'p cnf {n} {len(clauses)}\n'+
        ''.join(' '.join(map(str,row))+' 0\n' for row in clauses))
    r=subprocess.run([str(exe),str(f),"--proof",str(proof),"--time","10"],
         capture_output=True,text=True,timeout=15)
    assert r.returncode in (0,20),(key,r.stdout,r.stderr)
    if r.returncode==20:
        try:
            rup_check(clauses,proof.read_text())
        except AssertionError:
            print(f"RUP_DIAGNOSTIC key={key} n={n} clauses={clauses} proof={proof.read_text()!r} trueSAT={sat(n,clauses)}",flush=True)
            raise
    else:
        assert not proof.exists(),key
    return r.returncode==20

def shuffle_and_sign(clauses,n):
    mapping=list(range(1,n+1));rng.shuffle(mapping)
    signs=[bool(rng.getrandbits(1)) for _ in range(n)]
    out=permute(clauses,mapping,signs)
    for row in out:rng.shuffle(row)
    rng.shuffle(out)
    return out

def hidden_example(chain=False):
    base=[[1,2],[-1,2],[1,-2],[-1,-2]]
    # All four contradictory binary clauses are disguised as width-4 CNF.
    clauses=[row+[3,4] for row in base]
    if chain:
        # Only binary implications derive -3 and -4 from positive units.
        clauses.extend([[5],[-5,-3],[6],[-6,-4]])
    else:
        clauses.extend([[-3],[-4]])
    clauses.append([3,4,1,-1]) # irrelevant tautology; safe to ignore
    return 6,clauses

def main():
    with tempfile.TemporaryDirectory() as d:
        tmp=pathlib.Path(d)
        # Regression test: all original 681 test cases, for the new solver.
        lib["exe"]=new_exe  # run_path functions use their original globals;
        # update the globals actually used by check()
        check.__globals__["exe"]=new_exe
        lib["main"]()
        total=0; old_hit=0; new_hit=0; hidden_hits=0; sat_cases=0
        for chain in (False,True):
            for _ in range(140):
                n,c=hidden_example(chain)
                c=shuffle_and_sign(c,n)
                old=execute(old_exe,n,c,tmp,f"hidden_old_{total}")
                new=execute(new_exe,n,c,tmp,f"hidden_new_{total}")
                assert not old, "old unexpectedly recognizes disguised 2SAT"
                assert new, "new failed to recognize provable hidden 2SAT"
                assert not sat(n,c)
                total+=1;old_hit+=old;new_hit+=new;hidden_hits+=new
        for _ in range(100):
            n=rng.randint(2,8)
            model=[bool(rng.getrandbits(1)) for __ in range(n)]
            clauses=[]
            for __ in range(rng.randint(0,25)):
                while True:
                    c=[rng.choice((-1,1))*rng.randint(1,n) 
                       for ___ in range(rng.choice([1,2,3,4]))]
                    if any(model[abs(l)-1]==(l>0) for l in c):break
                clauses.append(c)
            assert sat(n,clauses)
            new=execute(new_exe,n,clauses,tmp,f"sat_new_{total}")
            assert not new, "false UNSAT on satisfiable CNF"
            total+=1;sat_cases+=1
        for _ in range(320):
            n=rng.randint(1,8)
            clauses=[[rng.choice((-1,1))*rng.randint(1,n)
                      for ___ in range(rng.randint(1,5))]
                     for __ in range(rng.randint(0,30))]
            truth=sat(n,clauses)
            old=execute(old_exe,n,clauses,tmp,f"random_old_{total}")
            new=execute(new_exe,n,clauses,tmp,f"random_new_{total}")
            assert not new or not truth
            assert not old or not truth
            assert not old or new, "unit closure lost baseline UNSAT detection"
            total+=1;old_hit+=old;new_hit+=new
        print(f"UP_CLOSURE_PASS tests={total} hidden_unsat={hidden_hits}/280 sat_verified={sat_cases}"
              f" binary_baseline_hits={old_hit} upclosure_hits={new_hit} wrong_unsat=0"
              f" proof_checker=independent_RUP permutations=280")
if __name__=="__main__":
    main()
