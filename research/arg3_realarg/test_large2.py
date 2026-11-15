#!/usr/bin/env python3
"""ARG3-LARGE2 capacity safety checks at 600 and 900 graph arguments.
Known constructed SAT assignment, no source result labels fed to solver.
"""
import json,random,subprocess,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"build/drnas-sat-native-x59"
def generate(n,seed):
    rng=random.Random(seed)
    planted=set(range(0,n,31))
    attacks=set()
    for target in range(n):
        if target not in planted:
            attacks.add((rng.choice(sorted(planted)),target))
        while len([a for a,b in attacks if b==target])<3:
            a=rng.randrange(n)
            if a==target or (a in planted and target in planted):continue
            attacks.add((a,target))
    attackers=[[] for _ in range(n)]
    for a,b in sorted(attacks):attackers[b].append(a)
    clauses=[]
    for i in range(n):
        a=i+1;b=n+i+1;c=2*n+i+1
        clauses.extend([[a,b,c],[-a,-b],[-a,-c],[-b,-c]])
        incoming=attackers[i]
        clauses.append([a]+[-n-j-1 for j in incoming])
        clauses.append([-b]+[j+1 for j in incoming])
    for a,b in sorted(attacks):
        clauses.append([-a-1,n+b+1])
        clauses.append([-b-1,n+a+1])
    clauses.append([i+1 for i in range(n)])
    model=[-1]*(3*n)
    for i in range(n):
        if i in planted:model[i]=1
        else:model[n+i]=1
    assert all(any(model[abs(l)-1]==(1 if l>0 else -1) for l in c) for c in clauses)
    return clauses
def model_valid(n,clauses,stdout):
    values={}
    for line in stdout.splitlines():
        if not line.startswith("v "):continue
        for word in line.split()[1:]:
            lit=int(word)
            if not lit:continue
            if abs(lit) in values and values[abs(lit)]!=(lit>0):return False
            values[abs(lit)]=lit>0
    return len(values)==3*n and all(any(values[abs(l)]==(l>0) for l in c) for c in clauses)
def main():
    assert BIN.is_file()
    results=[]
    with tempfile.TemporaryDirectory() as tmp:
        for n in (600,900):
            clauses=generate(n,31000+n)
            p=Path(tmp)/"graph.cnf"
            p.write_text(f"p cnf {3*n} {len(clauses)}\n"+
                "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
            started=time.perf_counter()
            r=subprocess.run([str(BIN),str(p),"--mode","core","--time","1",
                  "--arg3-ms","75","--stats"],capture_output=True,text=True,timeout=2)
            if r.returncode not in (0,10):raise RuntimeError(f"unsafe status {r.returncode}: {r.stderr[-500:]}")
            detail=next(json.loads(l.split(" ",1)[1]) for l in r.stderr.splitlines()
                if l.startswith("SAT_ARG3_STATS "))
            if not detail["recognized"]:raise RuntimeError("failed argument graph structural recognition")
            if r.returncode==10 and not model_valid(n,clauses,r.stdout):
                raise RuntimeError("invalid complete SAT model")
            results.append(dict(arguments=n,variables=3*n,clauses=len(clauses),
                                recognized=detail["recognized"],
                                found=detail["found"],
                                SAT_verified=r.returncode==10,
                                elapsed_s=time.perf_counter()-started))
    print("ARG3_LARGE2_SAFETY "+json.dumps(dict(cases=results,wrong_SAT=0),
          sort_keys=True),flush=True)
if __name__=="__main__":main()
