#!/usr/bin/env python3
"""SAT/UNSAT and distractor selftest for native subset PHP detector.
Uses exact original CNF logical subformula, not a family-name assertion.
"""
import pathlib,subprocess,tempfile,sys
sys.path.insert(0,"research")
from drnas_atlas34_php_verify import prove_php_subset

def php(p,h):
    vs=lambda pigeon,hole: 1+pigeon*h+hole
    clauses=[[vs(i,j) for j in range(h)] for i in range(p)]
    for j in range(h):
        for i in range(p):
            for k in range(i+1,p):
                clauses.append([-vs(i,j),-vs(k,j)])
    return p*h,clauses

def exercise(tag,n,cls,expect):
    assert (prove_php_subset(cls) is not None)==expect,(tag,"independent")
    with tempfile.TemporaryDirectory() as d:
        p=pathlib.Path(d)/"test.cnf"
        p.write_text("p cnf %d %d\n"%(n,len(cls))+
            "".join(" ".join(map(str,c))+" 0\n" for c in cls))
        r=subprocess.run(["mre_atlas25/bin/drnas_php_native34",str(p),
                          "/bin/true"],capture_output=True,text=True,timeout=3)
        assert (r.returncode==20)==expect,(tag,r.returncode,r.stdout,r.stderr)
        if expect:
            assert "ATLAS34_PHP_THEOREM" in r.stdout
        else:assert "ATLAS34_PHP_THEOREM" not in r.stdout
    print("ATLAS34_SELFTEST_CASE",tag,"PASS",flush=True)

n,a=php(3,2)
exercise("exact_unsat",n,a,True)
exercise("unrelated_positive_distractor",n+3,a+[[n+1,n+2,n+3]],True)
n2,b=php(3,2)
encoded=[]
for c in b:
    if len(c)>1 and all(x>0 for x in c):
        n2+=1
        encoded.extend([[n2],[-n2]+c])
    else:encoded.append(c)
exercise("unit_encoded_php_with_distractor",n2+3,encoded+[[n2+1,n2+2,n2+3]],True)
n3,c=php(2,2)
exercise("satisfiable_two_pigeons",n3+3,c+[[n3+1,n3+2,n3+3]],False)
exercise("non_php_random",6,[[1,2,3],[-1,4],[-2,-5],[-3,6]],False)
print("ATLAS34_SELFTEST_PASS original_clause_theorem=true distractor_tolerant=true no_false_unsat=true")
