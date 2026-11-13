#!/usr/bin/env python3
"""X5.8 proof-on versus explicitly SAT-only decision trace correctness.

SAT-only must independently validate SAT witnesses and must NEVER credit UNSAT.
For fixed policy, all final search counters must remain the same across modes
on these complete, bounded, small instances.
"""
from __future__ import annotations
import itertools,json,pathlib,random,subprocess,tempfile

POLICIES=("vsids","chb","lrb")
COUNTERS=("decisions","conflicts","propagations","learnt","reduce_removed","binary_propagations")

def oracle(cnf,n):
    for a in itertools.product((-1,1),repeat=n):
        if all(any(a[abs(l)-1]==(1 if l>0 else -1) for l in c) for c in cnf):
            return True
    return False

def sat_model(out,cnf,n):
    a={}
    try:
        for line in out.splitlines():
            if not line.startswith("v "):continue
            for w in line[2:].split():
                lit=int(w)
                if lit==0:continue
                v=abs(lit)
                if v>n or (v in a and a[v]!=(lit>0)):return False
                a[v]=(lit>0)
        return all(any(a.get(abs(l))==(l>0) for l in c) for c in cnf)
    except ValueError:return False

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
    return h*p,c

def one(formula,cnf,n,truth,policy,mode,temp):
    proof=temp/"proof.drat"
    trace=temp/"trace.jsonl"
    proof.unlink(missing_ok=True);trace.unlink(missing_ok=True)
    binary="build/drnas-x57" if mode=="frozen-proof" else "build/drnas-x58"
    cmd=[binary,str(formula),"--mode","core","--time","10","--stats",
         "--x52-proof-deletions","--x53-policy","baseline",
         "--x57-branch",policy]
    if mode in ("frozen-proof","new-proof"):
        cmd+=["--proof",str(proof)]
    else:
        cmd+=["--x58-sat-only"]
        if mode=="sat-trace":
            cmd+=["--x57-decision-trace",str(trace)]
    run=subprocess.run(cmd,capture_output=True,text=True,timeout=12)
    if mode in ("frozen-proof","new-proof"):
        assert run.returncode==(10 if truth else 20),("proof mode",policy,mode,run.returncode,run.stderr[-250:])
        if truth:assert sat_model(run.stdout,cnf,n)
        else:
            q=subprocess.run(["build/drat-trim",str(formula),str(proof)],
                             capture_output=True,text=True,timeout=10)
            assert q.returncode==0 and "s VERIFIED" in q.stdout,(policy,mode,q.stdout[-200:])
    else:
        assert run.returncode==(10 if truth else 0),(policy,mode,run.returncode,run.stderr[-300:])
        assert not proof.exists()
        if truth:assert sat_model(run.stdout,cnf,n)
        else:assert "s UNKNOWN" in run.stdout and "s UNSATISFIABLE" not in run.stdout
        status=[l for l in run.stderr.splitlines() if l.startswith("X58_SAT_ONLY ")]
        assert len(status)==1,(policy,mode,run.stderr[-300:])
        meta=json.loads(status[0].split(" ",1)[1])
        assert meta["enabled"] and meta["proof_disabled"]
        assert meta["UNSAT_without_proof_credited"] is False
        assert meta["policy"]==policy.upper()
        assert meta["internal_status"]==("SAT" if truth else "UNSAT")
        assert meta["reported_status"]==("SAT" if truth else "UNKNOWN")
    counts={}
    for line in run.stderr.splitlines():
        if line.startswith("X41_STATS "):
            counts=json.loads(line.split(" ",1)[1])
    assert counts,("missing statistics",policy,mode)
    nrows=0
    if mode=="sat-trace":
        assert trace.exists() and trace.stat().st_size>0
        rows=[json.loads(line) for line in trace.read_text().splitlines()]
        assert rows[0]["schema"]=="x57-decision-trace-v1"
        assert rows[0]["policy"]==policy.upper()
        assert rows[0]["rows_retained"]==len(rows)-1
        assert rows[0]["observational_only"]
        for rr in rows[1:]:
            assert rr["type"]=="decision" and not rr["is_causal_effect_known"]
        nrows=len(rows)-1
    return counts,nrows

def main():
    rng=random.Random(581113)
    samples=[]
    for k in range(42):
        n=5+(k%5)
        c=[]
        for j in range(2*n+(k%15)):
            vars=rng.sample(range(1,n+1),min(n,2+(j+k)%3))
            c.append([v if rng.getrandbits(1) else -v for v in vars])
        if k%11==0:c.extend([[1],[-1]])
        samples.append((n,c,oracle(c,n)))
    for h in (3,4,5):
        n,c=php(h);samples.append((n,c,False))
    assert any(x[2] for x in samples) and any(not x[2] for x in samples)
    totals={"SAT_sources":0,"UNSAT_sources":0,"trace_rows":0,"decisions_changed_by_trace":0}
    with tempfile.TemporaryDirectory() as td:
        tmp=pathlib.Path(td)
        f=tmp/"case.cnf"
        for n,cnf,truth in samples:
            totals["SAT_sources" if truth else "UNSAT_sources"]+=1
            f.write_text(f"p cnf {n} {len(cnf)}\n"+
                         "".join(" ".join(map(str,c))+" 0\n" for c in cnf))
            for policy in POLICIES:
                results=[one(f,cnf,n,truth,policy,mode,tmp) for mode in
                         ("frozen-proof","new-proof","sat-no-trace","sat-trace")]
                for key in COUNTERS:
                    vals={x[0][key] for x in results}
                    assert len(vals)==1,("trace or proof changed search",policy,key,vals)
                totals["trace_rows"]+=results[-1][1]
    assert totals["trace_rows"]>0
    p=subprocess.run(["build/drnas-x58","--help"],capture_output=True,text=True)
    assert p.returncode==0 and "--x58-sat-only" in p.stdout
    print("X58_SAT_ONLY_SELFTEST_PASS "+
          json.dumps({**totals,
          "source_count":len(samples),"executions":len(samples)*len(POLICIES)*4,
          "independent_DRAT_checks":totals["UNSAT_sources"]*len(POLICIES)*2,
          "counter_exact":True,"unverified_UNSAT_downgraded_to_UNKNOWN":True
          },sort_keys=True),flush=True)

if __name__=="__main__":main()
