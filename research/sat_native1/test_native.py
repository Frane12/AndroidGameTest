#!/usr/bin/env python3
"""Source-exact C++ SAT witness controls, independent checker and UNSAT negatives."""
import itertools,json,random,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research/sat_match1"))
from model import verify as independent_verify
from benchmark import generate as matching_fixture
BIN=ROOT/"build/drnas-sat-construct"
FUSED=ROOT/"build/drnas-sat-native-x59"

def dimacs(n,cs):
    return f"p cnf {n} {len(cs)}\n"+"".join(
        " ".join(map(str,c))+" 0\n" for c in cs)

def run(binary,path,more=()):
    p=subprocess.run([str(binary),str(path),*more],capture_output=True,text=True,timeout=3)
    vals={}
    for line in p.stdout.splitlines():
        if line.startswith("v "):
            for w in line.split()[1:]:
                x=int(w)
                if not x:continue
                if abs(x) in vals and vals[abs(x)]!=(x>0):
                    raise AssertionError("contradictory model literal")
                vals[abs(x)]=(x>0)
    return p,vals

def one(n,clauses,expected=None,method=None):
    with tempfile.TemporaryDirectory() as td:
        path=Path(td)/"x.cnf";path.write_text(dimacs(n,clauses))
        native,vals=run(BIN,path,("--stats",))
        if native.returncode not in (0,10):
            raise RuntimeError(("NATIVE_CRASH",native.stderr,n,clauses))
        if native.returncode==10:
            assert "s SATISFIABLE" in native.stdout
            assert len(vals)==n and independent_verify(n,clauses,
                      [vals[i] for i in range(1,n+1)]),"BAD_NATIVE_MODEL"
        if native.returncode==0:assert "s UNKNOWN" in native.stdout
        if expected is not None:assert native.returncode==expected,("unexpected",native.stdout,native.stderr)
        if method is not None:
            data=next(json.loads(line.split(" ",1)[1]) for line in native.stderr.splitlines()
                if line.startswith("SAT_NATIVE_STATS "))
            assert data["method"]==method,(method,data)
        # Fused CDCL must work both with and without the optional module.
        for opts in ((),("--sat-construct-ms","25",)):
            fused,assigned=run(FUSED,path,("--mode","core","--time","1",*opts))
            if fused.returncode==10:
                assert len(assigned)==n and independent_verify(n,clauses,
                     [assigned[i] for i in range(1,n+1)]),"BAD_FUSED_MODEL"
            elif fused.returncode not in (0,20):
                raise RuntimeError(("FUSED_CRASH",fused.returncode,fused.stderr))
        return native.returncode

def xoreqs(n,witness):
    clauses=[]
    # All distinct triples -> enough independent equations for unique solution.
    for vars in itertools.combinations(range(1,n+1),3):
        expected=sum(witness[v-1] for v in vars)&1
        for bits in itertools.product((0,1),repeat=3):
            if sum(bits)&1==expected:continue
            clauses.append([v if b==0 else -v for v,b in zip(vars,bits)])
    return clauses

def sat_exhaustive(n,clauses):
    for bits in itertools.product((False,True),repeat=n):
        if independent_verify(n,clauses,bits):return True
    return False

def main():
    assert BIN.is_file() and FUSED.is_file()
    start=time.perf_counter();counts={}
    cases=[
        ("HORN",4,[[1],[-1,2],[-2,3],[-3,-4]],10,"HORN"),
        ("2SAT",2,[[1,2],[-1,2],[1,-2]],10,"2SAT"),
        ("GF2",5,xoreqs(5,[True,False,True,False,True]),10,"GF2"),
        ("UNKNOWN",1,[[1],[-1]],0,None),
        ("2SAT_NEGATIVE",2,[[1,2],[-1,2],[1,-2],[-1,-2]],0,None),
    ]
    n,cs=matching_fixture(17,8,6)
    cases.append(("MATCH",n,cs,10,"MATCH"))
    for label,n,cs,expected,method in cases:
        one(n,cs,expected,method)
        counts[label]=counts.get(label,0)+1
    # Source-disjoint matching SAT positives and Hall negatives.
    for i in range(35):
        n,cs=matching_fixture(27000+i,resources=7+(i%6),jobs=4+(i%5))
        assert one(n,cs,10)==10
        counts["MATCH_SAT"] = counts.get("MATCH_SAT",0)+1
    for i in range(25):
        resources=2+i%4
        # Every job has every resource, but there are more jobs than resources.
        n,cs=matching_fixture(19000+i,resources=resources+1,jobs=resources)
        cs.extend([[1],[-1]]) # explicitly contradictory control
        assert not sat_exhaustive(1,[[1],[-1]])
        one(n,cs,0)
        counts["UNSAT_CONTROLS"]=counts.get("UNSAT_CONTROLS",0)+1
    rng=random.Random(20261115)
    for i in range(65):
        n=7;witness=[bool(rng.randrange(2)) for _ in range(n)]
        clauses=[]
        for _ in range(22):
            vs=rng.sample(range(1,n+1),3)
            while True:
                c=[v if rng.randrange(2) else -v for v in vs]
                if any((l>0)==witness[abs(l)-1] for l in c):break
            clauses.append(c)
        assert sat_exhaustive(n,clauses)
        one(n,clauses)
        counts["RANDOM_KNOWN_SAT"]=counts.get("RANDOM_KNOWN_SAT",0)+1
    for i in range(45):
        n=6;clauses=[]
        for _ in range(25):
            vs=rng.sample(range(1,n+1),3)
            clauses.append([v if rng.randrange(2) else -v for v in vs])
        if sat_exhaustive(n,clauses):continue
        assert one(n,clauses,0)==0
        counts["BRUTE_UNSAT"]=counts.get("BRUTE_UNSAT",0)+1
    print("NATIVE_SAT_CONTROLS "+json.dumps(dict(counts=counts,
         elapsed_s=round(time.perf_counter()-start,3),violations=0)),flush=True)

if __name__=="__main__":main()
