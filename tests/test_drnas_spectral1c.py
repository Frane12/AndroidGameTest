#!/usr/bin/env python3
"""SPECTRAL1C: same-binary OFF / OBSERVE / ON SAT + independently certified UNSAT."""
import json, os, pathlib, random, subprocess, sys, tempfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/"research"))
import drnas_x55_cpu_real36 as B

BIN=pathlib.Path("build/drnas-spectral1c").resolve()
DRAT=pathlib.Path("build/drat-trim").resolve()
FLAGS={0:[],1:["--spectral1c-observe"],2:["--spectral1c-on"]}

def solve(cnf, mode, *, cap=3):
    proof=cnf.parent/(cnf.stem+"_"+str(mode)+".drat")
    proof.unlink(missing_ok=True)
    cmd=[str(BIN),str(cnf),"--mode","core","--time",str(cap),
         "--stats","--proof",str(proof),*FLAGS[mode]]
    result=subprocess.run(cmd,capture_output=True,text=True,timeout=cap+4)
    assert result.returncode in (0,10,20),(cnf,mode,result.returncode,result.stderr[-400:])
    entries=[json.loads(l.split(" ",1)[1]) for l in result.stderr.splitlines()
             if l.startswith("SPECTRAL1C_STATS ")]
    assert len(entries)==1 and entries[0]["mode"]==mode,(cnf,mode,entries)
    detail=entries[0]
    if result.returncode==10:
        n,clauses=B.parse_cnf(cnf.read_bytes())
        assert B.check_sat(result.stdout,clauses,n),cnf
        return "SAT",detail
    if result.returncode==20:
        check=subprocess.run([str(DRAT),str(cnf),str(proof)],
                             capture_output=True,text=True,timeout=12)
        assert check.returncode==0 and "s VERIFIED" in check.stdout,(
            cnf,mode,check.returncode,check.stdout[-350:],check.stderr[-350:])
        return "UNSAT",detail
    return "UNKNOWN",detail

def php(pigeons,holes):
    n=pigeons*holes
    v=lambda p,h:p*holes+h+1
    c=[]
    for p in range(pigeons):
        c.append(tuple(v(p,h) for h in range(holes)))
    for h in range(holes):
        for a in range(pigeons):
            for b in range(a+1,pigeons):
                c.append((-v(a,h),-v(b,h)))
    return n,c

def main():
    assert BIN.is_file() and os.access(BIN,os.X_OK)
    assert DRAT.is_file() and os.access(DRAT,os.X_OK)
    cases=[
       ("unsat_unit",1,[(1,),(-1,)],"UNSAT"),
       ("unsat_corners",2,[(1,2),(1,-2),(-1,2),(-1,-2)],"UNSAT"),
       ("sat_parity",3,[(-1,2,3),(1,-2,3),(1,2,-3),(-1,-2,-3)],"SAT"),
       ("sat_mixed",5,[(1,2,3),(-1,2),(-2,3),(3,4,5)],"SAT"),
    ]
    for seed in range(12):
        rnd=random.Random(71771+seed)
        n=18; model=[bool(rnd.getrandbits(1)) for _ in range(n)]
        clauses=[]
        for _ in range(60):
            vv=rnd.sample(range(1,n+1),3)
            lit=[v if rnd.getrandbits(1) else -v for v in vv]
            if not any(model[abs(x)-1]==(x>0) for x in lit):
                lit[0]=vv[0] if model[vv[0]-1] else -vv[0]
            clauses.append(tuple(lit))
        cases.append((f"planted-{seed}",n,clauses,"SAT"))
    # A hard pigeonhole control checks whether adaptive measurements are
    # reached at nontrivial search depth, with no unverified UNSAT credit.
    n,clauses=php(7,6)
    cases.append(("php_7_6",n,clauses,"UNSAT"))
    total=0;cert_unsat=0;passes=0;resolutions=set()
    with tempfile.TemporaryDirectory() as directory:
        root=pathlib.Path(directory)
        for label,n,clauses,expected in cases:
            cnf=root/(label+".cnf")
            cnf.write_text(f"p cnf {n} {len(clauses)}\n"+
                           "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
            outcomes=[]
            for mode in (0,1,2):
                status,data=solve(cnf,mode)
                assert status==expected,(label,mode,expected,status)
                outcomes.append(status);total+=1
                cert_unsat+=int(status=="UNSAT")
                passes+=data["passes"]
                if data["resolution4"]:resolutions.add(4)
                if data["resolution6"]:resolutions.add(6)
                if data["resolution8"]:resolutions.add(8)
                if mode==0:
                    assert data["passes"]==0 and data["decision_vars"]==0
                if mode==1:assert data["decision_vars"]==0
            assert len(set(outcomes))==1
    print("SPECTRAL1C_SELFTEST_PASS "+json.dumps({
        "synthetic_sources":len(cases),
        "independently_certified_answers":total,
        "certified_unsat":cert_unsat,
        "adaptive_passes":passes,
        "resolutions_exercised":sorted(resolutions),
        "same_binary":["OFF","OBSERVE","ON"],
        "no_unverified_learned_clauses":True
    },sort_keys=True))

if __name__=="__main__":main()
