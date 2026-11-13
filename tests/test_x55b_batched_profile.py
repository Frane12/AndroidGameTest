#!/usr/bin/env python3
"""X5.5b: coarser entire-propagate CPU sampling, 5-way exact SAT/UNSAT smoke."""
import itertools,json,pathlib,random,subprocess,tempfile

ARMS={
  "X54_CONTROL":("build/drnas-x54",False,False),
  "X54_ROTATE":("build/drnas-x54",True,False),
  "X55B_CONTROL_OFF":("build/drnas-x55b",False,False),
  "X55B_CONTROL_PROFILE":("build/drnas-x55b",False,True),
  "X55B_ROTATE_PROFILE":("build/drnas-x55b",True,True),
}
def brute(clauses,n):
    return any(all(any(x[abs(l)-1]==(l>0) for l in c) for c in clauses)
               for x in itertools.product((False,True),repeat=n))

def sat_model(output,clauses,n):
    assign={}
    for line in output.splitlines():
        if line.startswith("v "):
            for word in line.split()[1:]:
                k=int(word)
                if not k:continue
                if abs(k)>n or (abs(k) in assign and assign[abs(k)]!=(k>0)):return False
                assign[abs(k)]=(k>0)
    return all(any(assign.get(abs(l))==(l>0) for l in c) for c in clauses)

def solve(src,clauses,n,want,arm,temp,cap=3):
    exe,rotate,profile=ARMS[arm]
    proof=temp/(arm+".drat")
    proof.unlink(missing_ok=True)
    cmd=[exe,str(src),"--mode","core","--time",str(cap),"--proof",str(proof),
         "--stats","--x52-proof-deletions","--x53-policy","baseline"]
    if rotate:cmd.append("--x54-rotate-watches")
    if profile:cmd.append("--x55b-profile")
    r=subprocess.run(cmd,capture_output=True,text=True,timeout=cap+3)
    assert r.returncode==(10 if want else 20),(arm,r.returncode,r.stderr[-750:])
    if want:assert sat_model(r.stdout,clauses,n),(arm,"invalid SAT")
    else:
        p=subprocess.run(["build/drat-trim",str(src),str(proof)],capture_output=True,text=True,timeout=6)
        assert p.returncode==0 and "s VERIFIED" in p.stdout,(arm,"invalid DRAT",p.stdout[-500:])
    stats={};profile_obj={}
    for l in r.stderr.splitlines():
        if l.startswith("X41_STATS "):stats=json.loads(l.split(" ",1)[1])
        if l.startswith("X55B_PROFILE "):profile_obj=json.loads(l.split(" ",1)[1])
    assert stats
    if profile:
        assert profile_obj.get("stride_propagate")==64
        assert profile_obj.get("clock")=="CLOCK_THREAD_CPUTIME_ID"
        assert profile_obj.get("propagate_samples",0)>=0
    else:assert not profile_obj
    return stats,profile_obj

def php(h):
    p=h+1
    v=lambda i,j:i*h+j+1
    c=[[v(i,j) for j in range(h)] for i in range(p)]
    for i in range(p):
        for j in range(h):
            for k in range(j+1,h):c.append([-v(i,j),-v(i,k)])
    for j in range(h):
        for i in range(p):
            for k in range(i+1,p):c.append([-v(i,j),-v(k,j)])
    return p*h,c

def main():
    rng=random.Random(551153)
    cnt={"SAT":0,"UNSAT":0};profiles=0
    with tempfile.TemporaryDirectory() as td:
        temp=pathlib.Path(td);src=temp/"case.cnf"
        cases=[]
        for idx in range(40):
            n=5+(idx%5)
            clauses=[]
            for z in range(4*n+(idx%9)):
                k=2+(z%2)
                vs=rng.sample(range(1,n+1),k)
                clauses.append([v if rng.randrange(2) else -v for v in vs])
            if idx%13==0:clauses.extend([[1],[-1]])
            cases.append((n,clauses,brute(clauses,n)))
        n,c=php(5);cases.append((n,c,False))
        for n,c,want in cases:
            cnt["SAT" if want else "UNSAT"]+=1
            src.write_text(f"p cnf {n} {len(c)}\n"+
                           "".join(" ".join(map(str,row))+" 0\n" for row in c))
            runs={a:solve(src,c,n,want,a,temp,cap=5) for a in ARMS}
            for k in ("decisions","conflicts","learnt","propagations","reduce_removed"):
                assert runs["X54_CONTROL"][0][k]==runs["X55B_CONTROL_OFF"][0][k]==runs["X55B_CONTROL_PROFILE"][0][k],(k,"control")
                assert runs["X54_ROTATE"][0][k]==runs["X55B_ROTATE_PROFILE"][0][k],(k,"rotation")
            profiles+=runs["X55B_CONTROL_PROFILE"][1].get("propagate_samples",0)
            profiles+=runs["X55B_ROTATE_PROFILE"][1].get("propagate_samples",0)
    assert profiles>0,(profiles,"no sampling exercised")
    print("X55B_SELFTEST_PASS "+json.dumps({"sources":len(cases),"executions":len(cases)*len(ARMS),
        "SAT_cases":cnt["SAT"],"UNSAT_cases":cnt["UNSAT"],
        "independent_Drat_checks":cnt["UNSAT"]*len(ARMS),
        "profile_propagate_samples":profiles,"control_search_invariants":True},sort_keys=True))

if __name__=="__main__":main()
