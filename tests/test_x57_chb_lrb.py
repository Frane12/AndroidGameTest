#!/usr/bin/env python3
"""DRNAS X5.7 CHB/LRB small exact oracle + DRAT and frozen VSIDS equivalence.

This is only the correctness gate. No speedup claims from these tests.
"""
from __future__ import annotations
import itertools,json,pathlib,random,subprocess,tempfile

BIN={"FROZEN":"build/drnas-x55b","VSIDS":"build/drnas-x57",
     "CHB":"build/drnas-x57","LRB":"build/drnas-x57"}
POLICY={"VSIDS":"vsids","CHB":"chb","LRB":"lrb"}

def oracle(cnf,n):
    for trial in itertools.product((False,True),repeat=n):
        if all(any(trial[abs(l)-1]==(l>0) for l in clause) for clause in cnf):
            return True
    return False

def sat_assignment(out,cnf,n):
    vals={}
    for line in out.splitlines():
        if not line.startswith("v "):continue
        for token in line[2:].split():
            lit=int(token)
            if not lit:continue
            v=abs(lit)
            if v>n or (v in vals and vals[v]!=(lit>0)):return False
            vals[v]=(lit>0)
    return all(any(vals.get(abs(l))==(l>0) for l in c) for c in cnf)

def pigeonhole(holes):
    birds=holes+1
    var=lambda i,j:1+i*holes+j
    clauses=[[var(i,j) for j in range(holes)] for i in range(birds)]
    for i in range(birds):
        for j in range(holes):
            for k in range(j+1,holes):clauses.append([-var(i,j),-var(i,k)])
    for j in range(holes):
        for i in range(birds):
            for k in range(i+1,birds):clauses.append([-var(i,j),-var(k,j)])
    return birds*holes,clauses

def run(path,clauses,n,sat,arm,tmp,cap=6):
    proof=tmp/(arm+".drat")
    proof.unlink(missing_ok=True)
    cmd=[BIN[arm],str(path),"--mode","core","--time",str(cap),
         "--stats","--proof",str(proof),"--x52-proof-deletions",
         "--x53-policy","baseline"]
    if arm in POLICY:cmd+=["--x57-branch",POLICY[arm]]
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=cap+3)
    assert p.returncode==(10 if sat else 20),(arm,p.returncode,path.name,p.stderr[-600:])
    if sat:
        assert sat_assignment(p.stdout,clauses,n),("bad SAT",arm,path)
    else:
        q=subprocess.run(["build/drat-trim",str(path),str(proof)],
                         capture_output=True,text=True,timeout=10)
        assert q.returncode==0 and "s VERIFIED" in q.stdout,(arm,"bad UNSAT proof",q.stdout[-500:],q.stderr[-500:])
    native={};x57={}
    for line in p.stderr.splitlines():
        if line.startswith("X41_STATS "):native=json.loads(line.split(" ",1)[1])
        if line.startswith("X57_STATS "):x57=json.loads(line.split(" ",1)[1])
    assert native,("missing base statistics",arm)
    if arm in POLICY:
        assert x57.get("requested")==arm
        assert x57.get("effective")==arm and not x57.get("fallback"),(arm,x57)
        assert x57.get("score_updates",0)>=0 and x57.get("learned_clause_hits",0)>=0
    return native,x57

def main():
    randomgen=random.Random(571113)
    sources=[]
    for ix in range(58):
        n=5+(ix%6)
        clauses=[]
        for j in range(3*n+(ix%19)):
            width=min(n,2+(ix+j)%3)
            var=randomgen.sample(range(1,n+1),width)
            clauses.append([v if randomgen.getrandbits(1) else -v for v in var])
        if ix%17==0:clauses.extend([[1],[-1]])
        sources.append((n,clauses,oracle(clauses,n),"bruteforce"))
    for h in (3,4,5):
        n,c=pigeonhole(h)
        sources.append((n,c,False,f"pigeonhole{h}"))
    assert any(s[2] for s in sources) and any(not s[2] for s in sources)
    cases=0;unsat=0;updates={"CHB":0,"LRB":0};picks={"CHB":0,"LRB":0}
    changed={"CHB":0,"LRB":0}
    with tempfile.TemporaryDirectory() as d:
        temp=pathlib.Path(d);file=temp/"test.cnf"
        for n,c,sat,label in sources:
            file.write_text(f"p cnf {n} {len(c)}\n"+
                            "".join(" ".join(map(str,row))+" 0\n" for row in c))
            results={arm:run(file,c,n,sat,arm,temp) for arm in BIN}
            cases+=1;unsat+=not sat
            for key in ("decisions","conflicts","propagations","learnt","reduce_removed","binary_propagations"):
                assert results["FROZEN"][0][key]==results["VSIDS"][0][key],(label,key,results["FROZEN"][0][key],results["VSIDS"][0][key])
            for arm in ("CHB","LRB"):
                a=results[arm][1]
                updates[arm]+=a["score_updates"]
                picks[arm]+=a["selected"]
                changed[arm]+=int(results[arm][0]["decisions"]!=results["VSIDS"][0]["decisions"] or
                                  results[arm][0]["conflicts"]!=results["VSIDS"][0]["conflicts"])
        assert all(updates[k]>0 and picks[k]>0 and changed[k]>0 for k in updates),(updates,picks,changed)
    print("X57_SELFTEST_PASS "+json.dumps({
        "sources":cases,"executions":cases*len(BIN),
        "SAT_sources":cases-unsat,"UNSAT_sources":unsat,
        "independent_DRAT_checks":unsat*len(BIN),
        "frozen_vsids_search_counters_identical":True,
        "CHB_updates":updates["CHB"],"LRB_updates":updates["LRB"],
        "CHB_changed_searches":changed["CHB"],"LRB_changed_searches":changed["LRB"]
    },sort_keys=True),flush=True)

if __name__=="__main__":main()
