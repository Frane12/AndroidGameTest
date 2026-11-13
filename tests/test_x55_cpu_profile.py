#!/usr/bin/env python3
"""X5.5: 216 exact SAT/UNSAT oracle evaluations and proof certificates.

Focusing on invariants: the optional profiler must never change decisions,
conflicts or propagation counts for a completed formula; both modes of the
rotating-watcher algorithm are compared against frozen X5.4 source.
"""
import itertools,json,pathlib,random,subprocess,tempfile

ARMS={
 "X54_CONTROL":("build/drnas-x54",False,False),
 "X54_ROTATE":("build/drnas-x54",True,False),
 "X55_CONTROL_OFF":("build/drnas-x55",False,False),
 "X55_CONTROL_ON":("build/drnas-x55",False,True),
 "X55_ROTATE_ON":("build/drnas-x55",True,True)
}
TRIM="build/drat-trim"
def brute(clauses,n):
    for bits in itertools.product((False,True),repeat=n):
        if all(any(bits[abs(lit)-1]==(lit>0) for lit in c) for c in clauses):return True
    return False

def witness(output,clauses,n):
    assignments={}
    for line in output.splitlines():
        if not line.startswith("v "):continue
        for word in line[2:].split():
            lit=int(word)
            if not lit:continue
            if abs(lit)>n or (abs(lit) in assignments and assignments[abs(lit)]!=(lit>0)):return False
            assignments[abs(lit)]=(lit>0)
    return all(any(assignments.get(abs(lit))==(lit>0) for lit in c) for c in clauses)

def check(cnf,clauses,n,expected,arm,td,seconds=3):
    binary,rotate,profile=ARMS[arm]
    proof=td/(arm+".drat")
    proof.unlink(missing_ok=True)
    cmd=[binary,str(cnf),"--mode","core","--time",str(seconds),"--stats","--proof",str(proof),
         "--x53-policy","baseline","--x52-proof-deletions"]
    if rotate:cmd.append("--x54-rotate-watches")
    if profile:cmd.append("--x55-profile")
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=seconds+3)
    assert p.returncode==(10 if expected else 20),("wrong result or timeout",arm,p.returncode,p.stderr[-1000:])
    if expected:assert witness(p.stdout,clauses,n),("invalid SAT witness",arm)
    else:
        v=subprocess.run([TRIM,str(cnf),str(proof)],capture_output=True,text=True,timeout=10)
        assert v.returncode==0 and "s VERIFIED" in v.stdout,("bad UNSAT proof",arm,v.stderr[-600:],v.stdout[-600:])
    core={};prof={}
    for line in p.stderr.splitlines():
        if line.startswith("X41_STATS "):core=json.loads(line[10:])
        if line.startswith("X55_PROFILE "):prof=json.loads(line[12:])
    assert core,("missing core stats",arm)
    if profile:
        assert prof and prof.get("clock")=="CLOCK_THREAD_CPUTIME_ID"
        assert prof.get("stride_bcp")==1024 and prof.get("stride_phase")==128
        assert prof["bcp_binary_sample_cpu_ns"]>=0
        assert prof["bcp_watch_sample_cpu_ns"]>=0
        assert prof["bcp_trail_samples"]>=0
    else:assert not prof,("profiler ran while disabled",arm)
    return core,prof

def php(h):
    pigeons=h+1
    var=lambda i,j:1+i*h+j
    clauses=[]
    for i in range(pigeons):clauses.append([var(i,j) for j in range(h)])
    for i in range(pigeons):
        for j in range(h):
            for k in range(j+1,h):clauses.append([-var(i,j),-var(i,k)])
    for j in range(h):
        for i in range(pigeons):
            for k in range(i+1,pigeons):clauses.append([-var(i,j),-var(k,j)])
    return pigeons*h,clauses

def main():
    rng=random.Random(551113)
    sat=unsat=0;proofs=0;rotated_samples=0
    with tempfile.TemporaryDirectory() as d:
        td=pathlib.Path(d);p=td/"test.cnf"
        for k in range(54):
            n=5+k%6
            clauses=[]
            for _ in range(5*n+(k%11)):
                width=2+(k%3)
                vs=rng.sample(range(1,n+1),min(width,n))
                clauses.append([v if rng.randrange(2) else -v for v in vs])
            if k%17==0:clauses.extend([[1],[-1]])
            expected=brute(clauses,n)
            sat+=expected;unsat+=not expected
            p.write_text(f"p cnf {n} {len(clauses)}\n"+
                         "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
            results={}
            for arm in ARMS:
                results[arm]=check(p,clauses,n,expected,arm,td)
                if not expected:proofs+=1
            for key in ("decisions","conflicts","propagations","learnt","reduce_removed"):
                assert results["X54_CONTROL"][0][key]==results["X55_CONTROL_OFF"][0][key],(k,key,"control off")
                assert results["X54_CONTROL"][0][key]==results["X55_CONTROL_ON"][0][key],(k,key,"control profile")
                assert results["X54_ROTATE"][0][key]==results["X55_ROTATE_ON"][0][key],(k,key,"rotation profile")
            rotated_samples+=results["X55_ROTATE_ON"][1]["bcp_trail_samples"]
        # Deliberately include a harder, analytically UNSAT PHP without brute-force.
        n,clauses=php(5)
        p.write_text(f"p cnf {n} {len(clauses)}\n"+
                     "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
        results={a:check(p,clauses,n,False,a,td,seconds=5) for a in ARMS}
        proofs+=len(ARMS);unsat+=1
        for key in ("decisions","conflicts","propagations","learnt","reduce_removed"):
            assert results["X54_CONTROL"][0][key]==results["X55_CONTROL_ON"][0][key],("PHP5",key)
            assert results["X54_ROTATE"][0][key]==results["X55_ROTATE_ON"][0][key],("PHP5",key)
        rotated_samples+=results["X55_ROTATE_ON"][1]["bcp_trail_samples"]
    assert sat>0 and unsat>0
    print("X55_SELFTEST_PASS "+json.dumps({
        "sources":55,"executions":55*len(ARMS),"sat":sat,"unsat":unsat,
        "independent_drat_checks":proofs,"profile_counter_equivalence":True,
        "rotating_profile_bcp_samples":rotated_samples
    },sort_keys=True),flush=True)

if __name__=="__main__":main()
