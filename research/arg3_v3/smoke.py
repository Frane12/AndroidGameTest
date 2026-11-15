#!/usr/bin/env python3
"""ARG3-V3 sound SAT regression: original known graph, omitted source
one-hot group with source-fixed units, and SHA-pinned four development originals.
No incorrect SAT accepted; failed construction remains UNKNOWN/CDCL fallback.
"""
import hashlib,json,os,random,subprocess,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BIN=ROOT/"build/drnas-sat-native-x59"
INPUTS=ROOT/"arg3_realarg_inputs"
KNOWN=ROOT/"sat_real2025_inputs/manifest.json"
def verify(n,clauses,out):
    vals={}
    for line in out.splitlines():
        if not line.startswith("v "):continue
        for w in line[2:].split():
            l=int(w)
            if not l:continue
            v=abs(l)
            if v in vals and vals[v]!=(l>0):return False
            vals[v]=l>0
    return len(vals)==n and all(any(vals[abs(l)]==(l>0) for l in c) for c in clauses)
def clauses_file(path):
    n=m=None;cs=[];cur=[]
    for line in path.open():
        a=line.split()
        if not a or a[0] in ("c","%"):continue
        if a[0]=="p":
            n,m=map(int,a[2:]);continue
        for w in a:
            l=int(w)
            if l:cur.append(l)
            else:cs.append(cur);cur=[]
    assert n and m==len(cs) and not cur
    return n,cs
def run(path,n,clauses,budget,timeout=1.0):
    begin=time.perf_counter()
    p=subprocess.run([str(BIN),str(path),"--mode","core","--time",str(timeout),
        "--arg3-v3-ms",str(budget),"--stats"],
        capture_output=True,text=True,timeout=timeout+1.0)
    stats=next(json.loads(l.split(" ",1)[1]) for l in p.stderr.splitlines()
               if l.startswith("SAT_ARG3V3_STATS "))
    if p.returncode==10 and not verify(n,clauses,p.stdout):
        raise RuntimeError("FALSE SAT / model invalid on "+str(path))
    if p.returncode not in (0,10,20):
        raise RuntimeError(f"SOLVER ERROR rc={p.returncode} {p.stderr[-400:]}")
    return dict(status={0:"UNKNOWN",10:"SAT",20:"UNSAT"}[p.returncode],
        verified_SAT=p.returncode==10,stats=stats,
        wall_s=round(time.perf_counter()-begin,5))
def write(path,n,clauses):
    path.write_text(f"p cnf {n} {len(clauses)}\n"+
      "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
def generated():
    import sys
    sys.path.insert(0,str(ROOT/"research/cdcl299"))
    from test_arg3 import generate
    n,clauses=generate(0x10292025+5)
    k=n//3
    # Canonical planted IN node 0 is sound under this generator.
    targets={tuple(sorted(c)) for c in (
        [1,k+1,2*k+1],[-1,-k-1],[-1,-2*k-1],[-k-1,-2*k-1])}
    removed=[c for c in clauses if tuple(sorted(c)) in targets]
    # A positive, and two negative source-backed units carry its state.
    keep=[c for c in clauses if c not in removed]
    keep.extend([[1],[-(k+1)],[-(2*k+1)]])
    return n,keep,len(removed)
def main():
    assert BIN.exists()
    rows=[]
    with tempfile.TemporaryDirectory() as tmp:
        n,cs,removed=generated()
        path=Path(tmp)/"repair.cnf";write(path,n,cs)
        rr=run(path,n,cs,100)
        if not rr["stats"]["recognized"] or rr["stats"]["repaired_groups"]<1:
            raise RuntimeError("repair controls not recognized "+str(rr))
        if not rr["verified_SAT"]:
            raise RuntimeError("repair synthetic known-SAT source not solved "+str(rr))
        rows.append(dict(case="constructed_repair",source_unit_triples=3,
                         source_clauses_removed=removed,**rr))
        rng=random.Random(20261115)
        nn=105;bad=[]
        for _ in range(200):
            v=rng.sample(range(1,nn+1),3)
            bad.append([rng.choice((-1,1))*x for x in v])
        path=Path(tmp)/"unrelated.cnf";write(path,nn,bad)
        rr=run(path,nn,bad,60,0.1)
        if rr["stats"]["recognized"] or rr["stats"]["found"]:
            raise RuntimeError("false graph recognition on negative control")
        rows.append(dict(case="unrelated",**rr))
    m=json.loads((INPUTS/"manifest.json").read_text())
    assert m["ready_count"]==11
    prefixes=("00d5a43a","9754fc1a","aa558557","c0074020")
    for src in m["ready_sources"]:
        if not any(src["gbd"].startswith(x) for x in prefixes):continue
        path=ROOT/src["path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest()==src["sha256"]
        n,cs=clauses_file(path)
        rr=run(path,n,cs,150,0.9)
        rows.append(dict(case=src["gbd"],sha256=src["sha256"],**rr))
    original=json.loads(KNOWN.read_text())
    dev=next(s for s in original["ready_sources"]
             if s["gbd"]=="b9ed6fd14f4fc969ec966a4b54c36872")
    p=ROOT/dev["path"]
    assert hashlib.sha256(p.read_bytes()).hexdigest()==dev["sha256"]
    n,cs=clauses_file(p)
    rr=run(p,n,cs,150,0.9)
    rows.append(dict(case="known_ARG3_299",**rr))
    print("ARG3_V3_SOURCE_SMOKE "+json.dumps(dict(
        total=len(rows),recognized=sum(r["stats"]["recognized"] for r in rows),
        verified_SAT=sum(r["verified_SAT"] for r in rows),
        wrong_SAT=0,rows=rows),sort_keys=True),flush=True)
if __name__=="__main__":main()
