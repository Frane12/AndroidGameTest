#!/usr/bin/env python3
"""DRNAS 2SAT-REALBENCH1: full genuine 2-CNF, SAT+UNSAT and source verification.
Public external cases: TIOJ 3718 samples (https://ntuj.csie.org/contests/7/problems/3718).
Scalable cases: reproducible STANDARD RANDOM 2-SAT, not external industrial CNFs.
All synthetic CNFs generated before any solver runs. All statuses checked
against independent MiniSat and, if available, CaDiCaL.
"""
import collections
import hashlib
import json
import math
import os
import pathlib
import random
import statistics
import subprocess
import sys
import tempfile
import time

BIN = pathlib.Path(sys.argv[1]).resolve()
MINISAT = sys.argv[2] if len(sys.argv)>2 else "minisat"
CADICAL = sys.argv[3] if len(sys.argv)>3 else ""
CAP=12.0

def source_cnf(n,clauses):
    return (f"p cnf {n} {len(clauses)}\n"+
            "".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode()

def make_random(n,alpha,seed):
    rng=random.Random((seed<<32) ^ (n*65537) ^ round(alpha*100000))
    clauses=[]
    for _ in range(round(n*alpha)):
        a=rng.randrange(n)+1
        b=rng.randrange(n-1)+1
        if b>=a:b+=1
        a=a if rng.randrange(2) else -a
        b=b if rng.randrange(2) else -b
        clauses.append((a,b))
    return clauses

def make_chain(n,contradiction):
    # Independent structured implication path, not a random distribution.
    c=[(-i,i+1) for i in range(1,n)]
    c.extend([(1,),(-n,) if contradiction else (n,)])
    return c

def parse_status(proc):
    if proc.returncode==10:return "SAT"
    if proc.returncode==20:return "UNSAT"
    if proc.returncode==0:return "UNKNOWN"
    raise AssertionError(("unexpected_exit",proc.returncode,proc.stdout[-500:],proc.stderr[-500:]))

def model_check(n,clauses,out):
    model={}
    for line in out.splitlines():
        if line.startswith("v "):
            for token in line.split()[1:]:
                lit=int(token)
                if not lit:continue
                v=abs(lit)
                assert 1<=v<=n
                assert v not in model,("duplicated_assignment",v)
                model[v]=lit>0
    assert len(model)==n,("incomplete_model",len(model),n)
    for c in clauses:
        assert any(model[abs(x)]==(x>0) for x in c),("invalid_sat_witness",c)

def check_rup(n,clauses,proof):
    # Independent RUP verifier for pure 2-CNF.
    # Unlike a full DRAT checker this handles additions (not deletions) and
    # accepts only unit/binary clauses, which is sufficient for this test.
    work=[tuple(dict.fromkeys(c)) for c in clauses]
    text=proof.strip()
    assert text, "missing_UNSAT_proof"
    for row in text.splitlines():
        vals=[int(v) for v in row.split()]
        assert vals[-1]==0
        candidate=tuple(vals[:-1])
        assert len(candidate)<=2
        graph=[[] for _ in range(n*2)]
        units=[]
        empty=False
        def vertex(l):return (abs(l)-1)*2+(l<0)
        for c in work:
            if not c:empty=True;break
            assert len(c)<=2
            if len(c)==1:
                units.append(c[0]);graph[vertex(-c[0])].append(c[0])
            else:
                a,b=c
                graph[vertex(-a)].append(b)
                graph[vertex(-b)].append(a)
        values=bytearray(n)
        queue=collections.deque(units+[-v for v in candidate])
        failed=empty
        while queue and not failed:
            lit=queue.popleft()
            value=1 if lit>0 else 2
            index=abs(lit)-1
            if values[index]:
                if values[index]!=value:failed=True
                continue
            values[index]=value
            queue.extend(graph[vertex(lit)])
        assert failed,("RUP_FAILED",candidate)
        work.append(candidate)
    assert work[-1]==tuple()

def run_one(cmd,timeout):
    t=time.perf_counter()
    try:
        p=subprocess.run(cmd,text=True,capture_output=True,timeout=timeout)
        return p,time.perf_counter()-t
    except subprocess.TimeoutExpired:
        raise AssertionError(("unexpected_timeout",cmd))

def run_case(name,n,clauses,tmp):
    assert n>=1 and all(0<len(c)<=2 for c in clauses)
    assert all(0<abs(l)<=n for c in clauses for l in c)
    inp=tmp/(name+".cnf")
    proof=tmp/(name+".drat")
    miniout=tmp/(name+".minisat.txt")
    data=source_cnf(n,clauses)
    inp.write_bytes(data)
    h=hashlib.sha256(data).hexdigest()
    p,td=run_one([str(BIN),str(inp),"--proof",str(proof),"--time",str(CAP)], CAP+4)
    ds=parse_status(p)
    assert ds in ("SAT","UNSAT"),("not_complete_2sat",name,p.stdout[-500:],p.stderr[-300:])
    if ds=="SAT":
        assert not proof.exists()
        model_check(n,clauses,p.stdout)
    else:
        assert proof.exists()
        check_rup(n,clauses,proof.read_text())
    q,tm=run_one([MINISAT,"-verb=0",str(inp),str(miniout)], CAP+4)
    ms=parse_status(q)
    assert ms in ("SAT","UNSAT")
    assert miniout.exists()
    status=miniout.read_text().split()[0]
    assert status==ms
    if ms=="SAT":
        v=[int(x) for x in miniout.read_text().splitlines()[1].split() if int(x)]
        assert len(v)==n and all(any(v[abs(x)-1]==x for x in c) for c in clauses)
    assert ds==ms,("MISMATCH_MINISAT",name,ds,ms)
    tc=None
    if CADICAL:
        z,tc=run_one([CADICAL,str(inp)], CAP+4)
        cs=parse_status(z)
        assert cs==ds,("MISMATCH_CADICAL",name,ds,cs,z.stdout[-500:])
        if cs=="SAT":
            model_check(n,clauses,z.stdout)
    inp.unlink(missing_ok=True)
    proof.unlink(missing_ok=True)
    miniout.unlink(missing_ok=True)
    return {"name":name,"n":n,"m":len(clauses),"status":ds,"sha256":h,
            "drnas_s":round(td,6),"minisat_s":round(tm,6),
            "cadical_s":round(tc,6) if tc is not None else None,"verified":True}

def main():
    result=[]
    with tempfile.TemporaryDirectory() as folder:
        tmp=pathlib.Path(folder)
        pub=[
            ("TIOJ3718_SAT",5,[(1,2),(-3,-1),(-4,-3),(2,-5),(5,-2),(1,4)]),
            ("TIOJ3718_UNSAT",2,[(1,2),(1,-2),(-1,2),(-1,-2)]),
        ]
        for name,n,c in pub:result.append(run_case(name,n,c,tmp))
        for n in (250,2000,10000,50000,100000):
            for alpha in (0.75,0.95,1.05,1.25):
                for seed in (17,29):
                    tag=f"uniform_n{n}_a{alpha}_seed{seed}"
                    result.append(run_case(tag,n,make_random(n,alpha,seed),tmp))
        for n in (1000,10000,50000):
            for unsat in (False,True):
                result.append(run_case(f"implication_chain_n{n}_{'UNSAT' if unsat else 'SAT'}",
                    n,make_chain(n,unsat),tmp))
    by={}
    for r in result:
        key="external_public" if r["name"].startswith("TIOJ") else (
            "structured" if r["name"].startswith("implication") else "random")
        by.setdefault(key,[]).append(r)
    for category,rows in by.items():
        for n in sorted({r["n"] for r in rows}):
            group=[r for r in rows if r["n"]==n]
            def med(f):return round(statistics.median(r[f] for r in group),6)
            print("GROUP",json.dumps({"family":category,"n":n,"count":len(group),
                "SAT":sum(r["status"]=="SAT" for r in group),
                "UNSAT":sum(r["status"]=="UNSAT" for r in group),
                "DRNAS_median_s":med("drnas_s"),"MiniSat_median_s":med("minisat_s"),
                "CaDiCaL_median_s":(med("cadical_s") if CADICAL else None)},
                separators=(",",":")),flush=True)
    kinds=collections.Counter(r["status"] for r in result)
    print("EXACT_2SAT_PAIRED_PASS",json.dumps({"cases":len(result),
        "SAT":kinds["SAT"],"UNSAT":kinds["UNSAT"],
        "external":len(by.get("external_public",[])),
        "standard_random":len(by.get("random",[])),
        "structured":len(by.get("structured",[])),
        "false_results":0,"sat_models_verified":kinds["SAT"],
        "unsat_RUP_verified":kinds["UNSAT"],
        "reference":["MiniSat"]+(["CaDiCaL"] if CADICAL else [])},
        separators=(",",":")),flush=True)
    pathlib.Path("drnas_2sat_realbench1.json").write_text(json.dumps(
        {"protocol":"random2sat_standard_2026-11-16_v1",
         "timing":"per subprocess wall_s, input prewritten, single runner",
         "results":result},indent=2)+"\n")
if __name__=="__main__":
    main()
