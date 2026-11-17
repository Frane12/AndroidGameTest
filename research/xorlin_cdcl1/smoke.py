#!/usr/bin/env python3
"""One-PID hybrid source-only XOR unsat + SAT/nonXOR/CDCL fallbacks.

External proof checker is invoked only AFTER the solver has exited, and
that checking time counts in all benchmark trials.
"""
import hashlib,os,pathlib,subprocess,sys,tempfile
from itertools import product
ROOT=pathlib.Path(__file__).resolve().parents[2]
BINARY=ROOT/"build/drnas-xorlin-cdcl1"
VERIPB=ROOT/"veripb-tool/bin/veripb"
DRAT=ROOT/"build/drat-trim"
sys.path.insert(0,str(ROOT/"research/unified_evidence"))
import benchmark as frozen
def encode(rows):
    cls=[]
    for variables,rhs in rows:
        for bits in product((0,1),repeat=len(variables)):
            if sum(bits)%2!=rhs:
                cls.append(tuple(-v if b else v for v,b in zip(variables,bits)))
    n=max(abs(l) for clause in cls for l in clause)
    return (f"p cnf {n} {len(cls)}\n"+
            "".join(" ".join(map(str,c))+" 0\n" for c in cls)).encode()
def check(cnf,gate,expect,route,external=None):
    with tempfile.TemporaryDirectory(prefix="xorlin-cdcl1-smoke-") as d:
        source=pathlib.Path(d)/"original.cnf";source.write_bytes(cnf)
        proof=pathlib.Path(d)/"proof"
        r=subprocess.run([str(BINARY),str(source),"--mode","core",
                "--gate",gate,"--gate-ms","600","--repo-root",str(ROOT),
                "--time","3","--proof",str(proof)],
                capture_output=True,text=True,timeout=6)
        assert r.returncode==expect,(r.returncode,r.stdout,r.stderr)
        assert f"c XORLIN_CDCL1_ROUTE {route}" in r.stdout,(r.stdout,r.stderr)
        assert ("s SATISFIABLE" if expect==10 else "s UNSATISFIABLE") in r.stdout
        if expect==10:
            assert frozen.model_ok(source,r.stdout)
            assert not proof.exists() or proof.stat().st_size==0,("SAT left nonempty proof file",gate)
        else:
            assert proof.is_file() and proof.stat().st_size
            if external=="VERIPB":
                p=subprocess.run([str(VERIPB),"--cnf",str(source),str(proof)],
                                 capture_output=True,text=True,timeout=12)
                assert p.returncode==0 and "s VERIFIED UNSATISFIABLE" in (
                    p.stdout+p.stderr),(p.stdout,p.stderr)
            elif external=="DRAT":
                p=subprocess.run([str(DRAT),str(source),str(proof)],
                                 capture_output=True,text=True,timeout=12)
                assert p.returncode==0 and "VERIFIED" in (
                    p.stdout+p.stderr),(p.stdout,p.stderr)
        print("XORLIN_CDCL1_SMOKE",{
          "gate":gate,"route":route,"status":"SAT_VERIFIED" if expect==10 else "UNSAT_VERIFIED",
          "proof":external,"source_sha256":hashlib.sha256(cnf).hexdigest(),
          "one_solver_process":True},flush=True)
def run():
    assert BINARY.is_file() and VERIPB.is_file() and DRAT.is_file()
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    core=[((1,2,3),1),((3,4,5),0),((1,2,4,5),0)]
    unsat=encode(core)
    sat=encode([((1,2,3),0)]+core[1:])
    assert frozen.model_ok # proof-only control
    check(unsat,"on",20,"GATE_VERIPB","VERIPB")
    check(unsat,"off",20,"CDCL_DRAT","DRAT")
    check(sat,"on",10,"CDCL_DRAT")
    check(sat,"off",10,"CDCL_DRAT")
    nonxor_sat=b"p cnf 3 2\n1 2 0\n-1 3 0\n"
    check(nonxor_sat,"on",10,"CDCL_DRAT")
    nonxor_unsat=b"p cnf 1 2\n1 0\n-1 0\n"
    check(nonxor_unsat,"on",20,"CDCL_DRAT","DRAT")
    print("XORLIN_CDCL1_SMOKE_PASS 6",flush=True)
if __name__=="__main__":run()
