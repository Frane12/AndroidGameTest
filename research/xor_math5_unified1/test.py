#!/usr/bin/env python3
"""Adversarial, source-checked proof and model smoke for the one-process hybrid."""
import itertools
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
BINARY=ROOT/"build/drnas-x59-xor-math5-unified1"
CHECKER=ROOT/"research/math5/check_math5.py"

def make_cnf(path, clauses, n):
    path.write_text(f"p cnf {n} {len(clauses)}\n"+
                    "".join(" ".join(map(str,c))+" 0\n" for c in clauses))

def verified_sat(clauses,n,stdout):
    model={}
    for line in stdout.splitlines():
        if not line.startswith("v "):continue
        for x in map(int,line[2:].split()):
            if x:
                if abs(x) in model and model[abs(x)]!=(x>0):
                    return False
                model[abs(x)]=x>0
    return len(model)==n and all(any(model[abs(l)]==(l>0) for l in c) for c in clauses)

def eo(groups):
    clauses=[list(g) for g in groups]
    for g in groups:
        for a,b in itertools.combinations(g,2):
            clauses.append([-a,-b])
    return clauses

def xor(n, parity):
    # Forbid all assignments with parity not equal to the target.
    out=[]
    for bits in itertools.product((0,1),repeat=n):
        if sum(bits)%2!=parity:
            out.append([(-v if bits[v-1] else v) for v in range(1,n+1)])
    return out

def run_one(tmp,name,clauses,n,expect,construct=25,math5=100,require_math5=False):
    cnf=tmp/(name+".cnf");proof=tmp/(name+".json")
    make_cnf(cnf,clauses,n)
    cmd=[str(BINARY),str(cnf),"--mode","core","--time","3",
         "--sat-construct-ms",str(construct),"--stats"]
    if math5:
        cmd+=["--math5-ms",str(math5),"--math5-certificate",str(proof)]
    got=subprocess.run(cmd,capture_output=True,text=True,timeout=8)
    assert got.returncode==expect,(name,got.returncode,got.stdout,got.stderr[-3000:])
    stats=[json.loads(x.split(" ",1)[1]) for x in got.stderr.splitlines()
           if x.startswith("MATH5_UNIFIED_STATS ")]
    assert len(stats)==1,(name,got.stderr[-2000:])
    if expect==10:
        assert verified_sat(clauses,n,got.stdout),(name,got.stdout)
        assert not proof.exists(),(name,"unexpected UNSAT proof")
    if expect==20 and proof.exists():
        check=subprocess.run([sys.executable,str(CHECKER),str(cnf),str(proof)],
                             capture_output=True,text=True,timeout=6)
        assert check.returncode==0,(name,check.stdout,check.stderr)
        assert json.loads(check.stdout)["status"]=="UNSAT_MATH5_CERTIFICATE_VERIFIED"
    if require_math5:assert proof.exists() and stats[0]["found"],(name,stats)
    print("UNIFIED_TEST",json.dumps({"case":name,"returncode":expect,
          "math5_found":stats[0]["found"],"math5_attempted":stats[0]["attempted"]}),
          flush=True)

def main():
    assert BINARY.is_file()
    with tempfile.TemporaryDirectory() as root:
        t=Path(root)
        # Every variable belongs to exactly two of three exact-one groups.
        # Summing the three EO equations yields 2*sum(x)=3, impossible.
        groups=[[1,2,3,4],[1,2,5,6],[3,4,5,6]]
        neg=eo(groups)
        run_one(t,"eo_odd_unsat",neg,6,20,require_math5=True)
        # Removing only a positive ALO constraint makes this case SAT.
        run_one(t,"eo_missing_alo_sat",eo(groups[1:]),6,10)
        # Removing one pairwise mutex also prevents a sound EO derivation.
        gone=neg.index([-1,-3])
        run_one(t,"eo_missing_mutex_sat",neg[:gone]+neg[gone+1:],6,10)
        run_one(t,"xor3_conflict_unsat",xor(3,0)+xor(3,1),3,20,require_math5=True)
        run_one(t,"xor3_sat",xor(3,1),3,10)
        run_one(t,"two_sat_fallback",[[1,2],[-1,3]],3,10)
        run_one(t,"cdcl_contradiction",[[1],[-1]],1,20,math5=0)
        # Excluding a certified MATH5 guard from DRAT mode is essential:
        # otherwise a custom JSON proof could be misrepresented as DRAT.
        cnf=t/"eo_odd_unsat.cnf"
        p=subprocess.run([str(BINARY),str(cnf),"--mode","core",
                          "--math5-ms","100","--math5-certificate",str(t/"x.json"),
                          "--proof",str(t/"x.drat")],
                         capture_output=True,text=True,timeout=5)
        assert p.returncode!=0 and "not DRAT/LRAT" in p.stderr
    print("UNIFIED_MATH5_PREFLIGHT_PASS",flush=True)

if __name__=="__main__":main()
