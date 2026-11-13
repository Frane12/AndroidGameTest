#!/usr/bin/env python3
"""X5.6 static original-binary CSR: exact oracle + proof + same-search controls.

These are correctness tests, not evidence of performance. Verifies the
new CSR path with >=512 *original* binary implication edges and the
unmodified control path on the same DIMACS bytes.
"""
from __future__ import annotations
import itertools,json,pathlib,random,subprocess,tempfile

ARMS={
 "FROZEN":"build/drnas-x55b",
 "X56_OFF":"build/drnas-x56",
 "X56_CSR":"build/drnas-x56",
}
def brute(clauses,n):
    return any(all(any(assignment[abs(l)-1]==(l>0) for l in c)
                   for c in clauses)
               for assignment in itertools.product((False,True),repeat=n))

def witness(stdout,clauses,n):
    assigned={}
    for row in stdout.splitlines():
        if not row.startswith("v "):continue
        for w in row[2:].split():
            lit=int(w)
            if lit==0:continue
            v=abs(lit)
            if v>n or (v in assigned and assigned[v]!=(lit>0)):return False
            assigned[v]=lit>0
    return all(any(assigned.get(abs(lit))==(lit>0) for lit in c) for c in clauses)

def run(path,clauses,n,sat,arm,d,cap=5):
    proof=d/(arm+".drat");proof.unlink(missing_ok=True)
    cmd=[ARMS[arm],str(path),"--mode","core","--time",str(cap),
         "--stats","--proof",str(proof),"--x52-proof-deletions",
         "--x53-policy","baseline"]
    if arm=="X56_CSR":cmd.append("--x56-binary-csr")
    result=subprocess.run(cmd,capture_output=True,text=True,timeout=cap+3)
    assert result.returncode==(10 if sat else 20),(
        path.name,arm,result.returncode,result.stderr[-500:])
    if sat:assert witness(result.stdout,clauses,n),("SAT witness",arm)
    else:
        p=subprocess.run(["build/drat-trim",str(path),str(proof)],
                          capture_output=True,text=True,timeout=6)
        assert p.returncode==0 and "s VERIFIED" in p.stdout,("UNSAT proof",arm,p.stdout[-500:])
    stats={};csr={}
    for line in result.stderr.splitlines():
        if line.startswith("X41_STATS "):stats=json.loads(line[10:])
        if line.startswith("X56_STATS "):csr=json.loads(line[10:])
    assert stats
    if arm!="FROZEN":assert csr
    return stats,csr

def source_file(path,n,clauses):
    path.write_text(f"p cnf {n} {len(clauses)}\n"+
                    "".join(" ".join(map(str,c))+" 0\n" for c in clauses))

def main():
    rng=random.Random(561113)
    ordinary_sat=ordinary_unsat=0
    csr_sat=csr_unsat=0
    csr_visits=0
    with tempfile.TemporaryDirectory() as tmp:
        d=pathlib.Path(tmp);f=d/"case.cnf"
        # Small exact brute-force oracle; deliberately mixed long/binary.
        for k in range(64):
            n=5+k%5
            c=[]
            for j in range(4*n+k%15):
                vars=rng.sample(range(1,n+1),min(n,2+j%3))
                c.append([v if rng.randrange(2) else -v for v in vars])
            if k%11==0:c.extend([[1],[-1]])
            sat=brute(c,n)
            ordinary_sat+=sat;ordinary_unsat+=not sat
            source_file(f,n,c)
            outs={arm:run(f,c,n,sat,arm,d) for arm in ARMS}
            for key in ("decisions","conflicts","propagations","learnt","reduce_removed","binary_propagations"):
                value=outs["FROZEN"][0][key]
                assert all(outs[a][0][key]==value for a in ARMS),(k,key)
            assert not outs["X56_CSR"][1]["csr_enabled"],"small instance unexpectedly activated CSR"
        # Lots of original binary clauses. SAT is planted: positive literal
        # always in each pair; all-TRUE satisfies each clause.
        # More than 512 static directed implication edges.
        for seed in range(6):
            n=90+seed*11
            c=[]
            rng2=random.Random(5800+seed)
            for j in range(840):
                a,b=rng2.sample(range(1,n+1),2)
                c.append([a,b if j%2 else -b])
            if seed%2==1:
                # Force x1 and !x1 indirectly with positive/negative units,
                # making UNSAT with a short independent DRAT proof.
                c.extend([[1],[-1]])
            sat=(seed%2==0)
            csr_sat+=sat;csr_unsat+=not sat
            source_file(f,n,c)
            outs={arm:run(f,c,n,sat,arm,d) for arm in ARMS}
            assert outs["X56_CSR"][1]["csr_enabled"],seed
            assert outs["X56_CSR"][1]["original_binary_edges"]==2*840,seed
            for key in ("decisions","conflicts","propagations","learnt","reduce_removed","binary_propagations"):
                value=outs["FROZEN"][0][key]
                assert all(outs[a][0][key]==value for a in ARMS),(seed,key,value)
            csr_visits+=outs["X56_CSR"][1]["binary_csr_edge_checks"]
            assert outs["X56_CSR"][1]["original_binary_csr_reason_stable"]
    assert ordinary_sat and ordinary_unsat and csr_sat and csr_unsat
    assert csr_visits>0,"CSR was built but never traversed"
    print("X56_SELFTEST_PASS "+json.dumps({
        "small_sources":64,"csr_sources":6,"executions":(64+6)*len(ARMS),
        "SAT_sources":ordinary_sat+csr_sat,"UNSAT_sources":ordinary_unsat+csr_unsat,
        "independent_DRAT_checks":(ordinary_unsat+csr_unsat)*len(ARMS),
        "frozen_search_counters_identical":True,"CSR_edges_visited":csr_visits,
        "original_binary_reason_ids_stable":True,
    },sort_keys=True),flush=True)

if __name__=="__main__":main()
