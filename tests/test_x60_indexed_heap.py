#!/usr/bin/env python3
"""X6.0 indexed-heap solver correctness and decision-path A/B, no real sources."""
import json, os, pathlib, random, subprocess, sys, tempfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"research"))
import drnas_x55_cpu_real36 as B
import drnas_x60_indexed_heap_real36 as X

def solve(binary,cnf,flag=False):
    proof=cnf.parent/(cnf.stem+("_on" if flag else "_off")+".drat")
    proof.unlink(missing_ok=True)
    cmd=[str(binary),str(cnf),"--mode","core","--time","3","--stats","--proof",str(proof)]
    cmd.append("--x59-stamp-glue") # identical glue mode in both A/B arms
    if flag:cmd.extend(["--x60-indexed-heap","--x60-heap-audit"])
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=5)
    assert p.returncode in (10,20), (cmd,p.returncode,p.stderr[-1000:])
    stats=[json.loads(x.split(" ",1)[1]) for x in p.stderr.splitlines()
           if x.startswith("X60_STATS ")]
    assert len(stats)==1 and stats[0].get("indexed_heap")==flag,stats
    n,clauses=B.parse_cnf(cnf.read_bytes())
    if p.returncode==10:
        assert B.check_sat(p.stdout,clauses,n),(cnf,flag)
        cert="SAT"
    else:
        check=subprocess.run(["build/drat-trim",str(cnf),str(proof)],
                             capture_output=True,text=True,timeout=10)
        assert check.returncode==0 and "s VERIFIED" in check.stdout,(cnf,check.stdout[-400:])
        cert="UNSAT"
    native=[json.loads(x.split(" ",1)[1]) for x in p.stderr.splitlines()
            if x.startswith("X41_STATS ")]
    assert len(native)==1,(cnf,flag,p.stderr[-500:])
    return cert,stats[0],native[0]

def main():
    binary=pathlib.Path("build/drnas-x60").resolve()
    assert binary.is_file() and os.access(binary,os.X_OK),"X60 candidate not executable"
    with tempfile.TemporaryDirectory() as name:
        path=pathlib.Path(name)
        from itertools import product
        examples=[
          # Forces the other watched literal to be satisfied before processing -1.
          ("blocker_true",3,[(1,2,3),(-1,),(2,)],"SAT"),
          ("unsat_units",1,[(1,),(-1,)],"UNSAT"),
          ("simple_sat",3,[(1,2,3),(-1,2),(-2,3)],"SAT"),
          ("unsat_three",2,[(1,2),(1,-2),(-1,2),(-1,-2)],"UNSAT"),
          ("all_3cnf_unsat",3,[tuple(signs[i]*(i+1) for i in range(3)) for signs in product((1,-1),repeat=3)],"UNSAT"),
        ]
        for k in range(12):
            rng=random.Random(5800+k)
            n=20
            assignment={v:bool(rng.getrandbits(1)) for v in range(1,n+1)}
            clauses=[]
            for _ in range(75):
                vs=rng.sample(range(1,n+1),3)
                literals=[v if rng.getrandbits(1) else -v for v in vs]
                if not any(assignment[abs(l)]==(l>0) for l in literals):
                    v=vs[0];literals[0]=v if assignment[v] else -v
                clauses.append(tuple(literals))
            examples.append((f"planted-{k}",n,clauses,"SAT"))
        total_skipped=0
        for label,n,clauses,expected in examples:
            cnf=path/(label+".cnf")
            cnf.write_text(f"p cnf {n} {len(clauses)}\n"+
                "".join(" ".join(map(str,cl))+" 0\n" for cl in clauses))
            a,off,off_native=solve(binary,cnf,False)
            b,on,on_native=solve(binary,cnf,True)
            assert a==b==expected,(label,a,b)
            assert off["heap_inserts"]==0
            assert on["heap_inserts"]>0
            for key in ("conflicts","decisions","propagations","learnt","restarts"):
                assert off_native[key]==on_native[key],(label,key,off_native[key],on_native[key])
            total_skipped+=on["heap_inserts"]
            if label=="all_3cnf_unsat":
                assert on["heap_removes"]>0,"X60 must remove assigned variables"
        assert total_skipped>0
        print("X60_SELFTEST_PASS "+json.dumps({
            "synthetic_sources":len(examples),
            "independent_certificates":len(examples)*2,
            "candidate_policies":["OFF","ON"],
            "indexed_inserts":total_skipped,
            "no_real_holdout_access":True
        },sort_keys=True))
if __name__=="__main__":main()
