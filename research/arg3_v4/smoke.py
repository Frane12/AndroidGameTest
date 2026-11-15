#!/usr/bin/env python3
"""ARG3-V4 three-valued IN/OUT/UNDEC SAT source verification controls.
No UNSAT is inferred from heuristic failure; all SAT models checked against
UNCHANGED generated or frozen original CNF, never a transformed solver output.
"""
import json,hashlib,itertools,random,subprocess,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"build/drnas-sat-native-x59"
def make_graph(n,edges,force_undec=None):
    incoming=[set() for _ in range(n)]
    for a,b in edges:incoming[b].add(a)
    clauses=[]
    for i in range(n):
        inside=i+1;outside=n+i+1;unknown=2*n+i+1
        clauses.extend([[inside,outside,unknown],
                        [-inside,-outside],[-inside,-unknown],[-outside,-unknown]])
    for a,b in edges:
        clauses.extend([[-a-1,n+b+1],[-b-1,n+a+1]])
    for i in range(n):
        clauses.append([-n-i-1]+[a+1 for a in sorted(incoming[i])])
        clauses.append([i+1]+[-n-a-1 for a in sorted(incoming[i])])
    if force_undec is not None:
        i=force_undec
        forbidden={tuple(sorted(c)) for c in (
            [i+1,n+i+1,2*n+i+1],
            [-i-1,-n-i-1],[-i-1,-2*n-i-1],[-n-i-1,-2*n-i-1]
        )}
        removed=sum(tuple(sorted(c)) in forbidden for c in clauses)
        assert removed==4,removed
        clauses=[c for c in clauses if tuple(sorted(c)) not in forbidden]
        clauses.extend([[-i-1],[-n-i-1],[2*n+i+1]])
    return clauses
def parse_original(path):
    n=m=None;cs=[];partial=[]
    with path.open() as f:
        for line in f:
            words=line.split()
            if not words or words[0] in ("c","%"):continue
            if words[0]=="p":
                n,m=map(int,words[2:]);continue
            for word in words:
                lit=int(word)
                if lit:partial.append(lit)
                else:cs.append(partial);partial=[]
    assert n and len(cs)==m and not partial
    return n,cs
def write(path,n,cs):
    path.write_text(f"p cnf {n} {len(cs)}\n"+
                    "".join(" ".join(map(str,c))+" 0\n" for c in cs))
def verify(n,clauses,out):
    truth={}
    for row in out.splitlines():
        if not row.startswith("v "):continue
        for w in row[2:].split():
            lit=int(w)
            if not lit:continue
            v=abs(lit)
            if v in truth and truth[v]!=(lit>0):return False
            truth[v]=lit>0
    return len(truth)==n and all(any(
        truth[abs(l)]==(l>0) for l in c) for c in clauses)
def run(path,n,cs,ms=120,timeout=1.0):
    begin=time.perf_counter()
    p=subprocess.run([str(BIN),str(path),"--mode","core","--time",str(timeout),
                      "--arg3-v4-ms",str(ms),"--stats"],
                     capture_output=True,text=True,timeout=timeout+1.0)
    stats=next(json.loads(line.split(" ",1)[1])
               for line in p.stderr.splitlines()
               if line.startswith("SAT_ARG3V4_STATS "))
    if p.returncode not in (0,10,20):
        raise RuntimeError(f"solver failed rc={p.returncode}: {p.stderr[-350:]}")
    if p.returncode==10 and not verify(n,cs,p.stdout):
        raise RuntimeError("INVALID SAT witness on original")
    return dict(status={0:"UNKNOWN",10:"SAT",20:"UNSAT"}[p.returncode],
        model_verified=(p.returncode==10),stats=stats,
        wall_s=round(time.perf_counter()-begin,6))
def main():
    assert BIN.exists()
    tests=[];rng=random.Random(20261115)
    with tempfile.TemporaryDirectory() as td:
        # 15-node disjoint directed odd cycles: no stable IN/OUT model exists,
        # but the all-UNDEC complete labeling is source-verifiable SAT.
        n=15
        edges={(3*k+i,3*k+(i+1)%3) for k in range(5) for i in range(3)}
        for name,root in (("undec_odd_cycles",None),
                          ("unit_repaired_undec_odd_cycles",0)):
            cs=make_graph(n,edges,root)
            p=Path(td)/"g.cnf";write(p,3*n,cs)
            r=run(p,3*n,cs,200,1.0)
            if not r["model_verified"] or not r["stats"]["found"]:
                raise RuntimeError(f"V4 failed required 3-valued control {name} {r}")
            if root is not None and r["stats"]["repaired_triples"]<1:
                raise RuntimeError("V4 failed repaired UNDEC one-hot group")
            tests.append(dict(case=name,**r))
        # Acyclic segment + odd cycles: both IN/OUT and UNDEC required.
        graph=set(edges)|{(15,16),(16,17)}
        cs=make_graph(18,graph)
        p=Path(td)/"mix.cnf";write(p,54,cs)
        r=run(p,54,cs,200,1.0)
        if not r["model_verified"]:
            raise RuntimeError(f"V4 failed mixed IN/OUT/UNDEC source {r}")
        tests.append(dict(case="mixed_three_labels",**r))
        # Fast negative guard: arbitrary CNFs must NOT be misrecognized as
        # one-hot argument encodings. The fallback CDCL may still solve them.
        for i in range(12):
            n=99;cs=[]
            for _ in range(140):
                vs=rng.sample(range(1,n+1),3)
                cs.append([v if rng.getrandbits(1) else -v for v in vs])
            p=Path(td)/"not-arg.cnf";write(p,n,cs)
            r=run(p,n,cs,80,0.2)
            if r["stats"]["recognized"] or r["stats"]["found"]:
                raise RuntimeError("nonargumentation CNF was falsely recognized")
            tests.append(dict(case="negative_random",**r))
    # Previously inspected REALARG1 sources, not future blind holdout.
    f=json.loads((ROOT/"arg3_realarg_inputs/manifest.json").read_text())
    assert f["ready_count"]==11
    selected=("00d5a43a","9754fc1a","aa558557","c0074020")
    for src in f["ready_sources"]:
        if not any(src["gbd"].startswith(x) for x in selected):continue
        path=ROOT/src["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest()==src["sha256"]
        n,cs=parse_original(path)
        r=run(path,n,cs,200,0.7)
        tests.append(dict(case=src["gbd"],sha256=src["sha256"],**r))
    # Also protect prior original #299 from unintended source-model regression.
    dev=json.loads((ROOT/"sat_real2025_inputs/manifest.json").read_text())
    source=next(x for x in dev["ready_sources"] if
                x["gbd"]=="b9ed6fd14f4fc969ec966a4b54c36872")
    path=ROOT/source["path"]
    assert hashlib.sha256(path.read_bytes()).hexdigest()==source["sha256"]
    n,cs=parse_original(path)
    r=run(path,n,cs,100,0.7)
    tests.append(dict(case="known_299",**r))
    print("ARG3_V4_CONTROLS "+json.dumps(dict(
        total=len(tests),positive_source_verified=sum(x["model_verified"] for x in tests),
        four_real_sources_recognized=sum(x["stats"]["recognized"] for x in tests
            if x["case"].startswith(selected)),
        wrong_SAT=0,rows=tests),sort_keys=True),flush=True)
if __name__=="__main__":main()
