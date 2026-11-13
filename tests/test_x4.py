#!/usr/bin/env python3
"""Independent tiny-CNF truth-table oracle, plus no-policy-change trace audit."""
import argparse,itertools,json,random,subprocess,tempfile,time
from pathlib import Path
BIN=Path(__file__).resolve().parents[1]/"build"/"drnas-x4"
def oracle(n,cnf):
    return any(all(any((bit[abs(x)-1]==(x>0)) for x in c) for c in cnf)
               for bit in itertools.product((False,True),repeat=n))
def witness(out,n,cnf):
    v=[]
    for line in out.splitlines():
        if line.startswith("v "):
            v.extend(int(t) for t in line[2:].split() if t!="0")
    if len(v)!=n or {abs(x) for x in v}!=set(range(1,n+1)):return False
    assn={abs(x):x>0 for x in v}
    return all(any(assn[abs(x)]==(x>0) for x in c) for c in cnf)
def check(path,trace_file,n,cnf,counters):
    path.write_text(f"p cnf {n} {len(cnf)}\n"+
                    "".join(" ".join(map(str,c))+" 0\n" for c in cnf))
    expected=oracle(n,cnf)
    rows=[]
    for mode in ("core","trace"):
        cmd=[str(BIN),str(path),"--mode",mode,"--time","2","--stats"]
        if mode=="trace":cmd+=["--transitions",str(trace_file)]
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=4)
        if p.returncode not in (10,20) or (p.returncode==10)!=expected:
            raise AssertionError((mode,n,cnf,p.returncode,p.stderr))
        if p.returncode==10 and not witness(p.stdout,n,cnf):
            raise AssertionError("original CNF SAT witness invalid")
        items=[json.loads(z[len("X4_STATS "):]) for z in p.stderr.splitlines()
               if z.startswith("X4_STATS ")]
        if len(items)!=1:raise AssertionError(("missing stats",p.stderr))
        rows.append((p.stdout,items[0]))
        if mode=="trace":
            tr=[json.loads(line) for line in trace_file.read_text().splitlines()]
            if not tr or tr[0]["type"]!="meta" or tr[0]["observational_only"] is not True:
                raise AssertionError("missing observational metadata")
            if len(tr)-1!=items[0]["trace_samples_retained"]:
                raise AssertionError("trace record count mismatch")
            for entry in tr[1:]:
                a,b=entry["before"],entry["after"]
                assert b["decisions"]==a["decisions"]
                assert b["level"]==a["level"]+1
                assert b["assigned"]>=a["assigned"]+1
                assert b["conflicts"]==a["conflicts"]
                assert entry["remaining_finish_wall_s"] is not None
            counters["records"]+=len(tr)-1
        counters["checks"]+=1
    assert rows[0][0]==rows[1][0],("observer changed SAT witness",cnf)
    for key in ("decisions","conflicts","learnt","propagations","restarts","reduce_removed"):
        assert rows[0][1][key]==rows[1][1][key],("observer changed core",key,cnf)
    counters["sources"]+=1
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--cases",type=int,default=2800)
    a=ap.parse_args()
    rng=random.Random(624261114)
    t=time.monotonic()
    counts=dict(sources=0,checks=0,records=0,seed=624261114)
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)/"case.cnf";tr=Path(tmp)/"trace.jsonl"
        for n in range(12):check(p,tr,n,[],counts)
        for n in range(1,12):
            check(p,tr,n,[[1,-1]],counts)
            check(p,tr,n,[[]],counts)
        for _ in range(a.cases):
            n=rng.randint(0,10);cs=[]
            for _ in range(rng.randrange(0,36)):
                size=rng.randrange(0,7) if n else 0
                cs.append([rng.choice([-1,1])*rng.randint(1,n) for _ in range(size)])
            check(p,tr,n,cs,counts)
        for pigeons in (3,4):
            holes=pigeons-1;cs=[]
            for i in range(pigeons):cs.append([i*holes+h+1 for h in range(holes)])
            for h in range(holes):
                for i in range(pigeons):
                    for j in range(i+1,pigeons):
                        cs.append([-(i*holes+h+1),-(j*holes+h+1)])
            check(p,tr,pigeons*holes,cs,counts)
    counts["elapsed_s"]=round(time.monotonic()-t,3)
    assert counts["records"]>0
    print("X4_DIFFERENTIAL_PASS "+json.dumps(counts,sort_keys=True),flush=True)
if __name__=="__main__":main()
