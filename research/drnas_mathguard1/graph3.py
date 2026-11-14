#!/usr/bin/env python3
"""Single-logical-CPU paired DRNAS MATH-GUARD1 graph 3-colouring experiment.

CNF encoding: each vertex has exactly one of 3 colours; adjacent vertices
cannot share a colour. Outcome labels are known by construction, with exact
independent graph backtracking for small examples and DRAT proof verification
for every solver-reported UNSAT.
"""
import hashlib
import json
import os
from pathlib import Path
import random
import resource
import statistics
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
SOLVER = ROOT / "build/drnas-mathguard1"
PROOFCHECK = ROOT / "external/drat-trim/drat-trim"
OUT = ROOT / "mathguard_graph3c"
CAP = 3.0
REPS = 2

def edges_clean(n, edges):
    e = {tuple(sorted((int(a), int(b)))) for a, b in edges}
    assert all(0 <= a < b < n for a, b in e)
    return sorted(e)

def clique(n): return [(a,b) for a in range(n) for b in range(a+1,n)]
def cycle(n): return [(i, (i+1)%n) for i in range(n)]
def wheel(rim):
    return cycle(rim) + [(rim, i) for i in range(rim)]

def mycielski(n, edges):
    # G with n vertices -> M(G) with 2n+1 vertices, chromatic number +1.
    new = list(edges)
    for a, b in edges:
        new.extend([(a, n+b), (b, n+a)])
    new.extend((n+i, 2*n) for i in range(n))
    return 2*n+1, new

def planted(n, prob, seed):
    rng = random.Random(seed)
    colors = [i % 3 for i in range(n)]
    edges = [(i,j) for i in range(n) for j in range(i+1,n)
             if colors[i] != colors[j] and rng.random() < prob]
    return edges

def fixtures():
    cases = []
    def add(name,n,ed,expected,group):
        e=edges_clean(n,ed)
        cases.append(dict(name=name,n=n,edges=e,expected=expected,group=group))
    add("triangle_K3",3,clique(3),"SAT","small")
    add("tetrahedron_K4",4,clique(4),"UNSAT","small")
    add("complete_K5",5,clique(5),"UNSAT","small")
    add("cycle_C5",5,cycle(5),"SAT","small")
    add("odd_wheel_W6",6,wheel(5),"UNSAT","small")
    add("even_wheel_W7",7,wheel(6),"SAT","small")
    add("odd_wheel_W8",8,wheel(7),"UNSAT","small")
    add("bipartite_K6_6",12,[(i,6+j) for i in range(6) for j in range(6)],"SAT","medium")
    n,ed=mycielski(5,cycle(5))
    add("mycielski_C5_noK4",n,ed,"UNSAT","medium")
    n,ed=mycielski(7,cycle(7))
    add("mycielski_C7_noK4",n,ed,"UNSAT","medium")
    for n,p,seed in [(24,.3,403),(36,.4,713),(48,.4,1231),(72,.35,2027)]:
        ed=planted(n,p,seed)
        add(f"planted_3col_n{n}",n,ed,"SAT","large")
        add(f"planted_plus_K4_n{n}",n,ed+clique(4),"UNSAT","large")
    return cases

def exact_colorable(n, edges):
    adj=[set() for _ in range(n)]
    for a,b in edges:
        adj[a].add(b); adj[b].add(a)
    color=[-1]*n
    def dfs(done):
        if done==n: return True
        pick=max((v for v in range(n) if color[v]<0),
                 key=lambda v:(len({color[w] for w in adj[v] if color[w]>=0}),len(adj[v])))
        forbidden={color[w] for w in adj[pick] if color[w]>=0}
        for c in range(3):
            if c in forbidden: continue
            color[pick]=c
            if dfs(done+1): return True
            color[pick]=-1
        return False
    return dfs(0)

def cnf(n,edges):
    clauses=[]
    for v in range(n):
        ids=[3*v+c+1 for c in range(3)]
        clauses.append(ids)
        clauses.extend([[-ids[0],-ids[1]],[-ids[0],-ids[2]],[-ids[1],-ids[2]]])
    for a,b in edges:
        for c in range(3):
            clauses.append([-(3*a+c+1),-(3*b+c+1)])
    return clauses

def sat_model(out, n, clauses, edges):
    values={}
    for line in out.splitlines():
        if line.startswith("v "):
            for tok in line.split()[1:]:
                lit=int(tok)
                if lit: values[abs(lit)]=lit>0
    if len(values)!=3*n: return False
    if not all(any(values[abs(l)]==(l>0) for l in row) for row in clauses):
        return False
    colors=[]
    for v in range(n):
        active=[c for c in range(3) if values[3*v+c+1]]
        if len(active)!=1:return False
        colors.append(active[0])
    return all(colors[a]!=colors[b] for a,b in edges)

def one_run(case, arm, rep, temp):
    n=case["n"]; ed=case["edges"]; clauses=cnf(n,ed)
    src=temp / "instance.cnf"
    src.write_text(f"p cnf {3*n} {len(clauses)}\n" +
        "".join(" ".join(str(l) for l in row)+" 0\n" for row in clauses))
    sha=hashlib.sha256(src.read_bytes()).hexdigest()
    proof=temp / f"{arm}_{rep}.drat"
    cmd=[str(SOLVER), str(src),"--mode","core","--time",str(CAP-.08),
         "--x5-no-minimize","--stats","--proof",str(proof)]
    if arm=="GUARD_ON":cmd.extend(["--math-guard","--math-guard-budget-ms","4.0"])
    def limit():
        resource.setrlimit(resource.RLIMIT_AS, (2*1024**3, 2*1024**3))
    start=time.perf_counter()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=CAP+.2,
                         preexec_fn=limit)
        rc=p.returncode
        output=p.stdout;err=p.stderr
    except subprocess.TimeoutExpired:
        rc=-9;output="";err=""
    elapsed=time.perf_counter()-start
    if rc==10:
        assert sat_model(output,n,clauses,ed), ("BAD_MODEL",case["name"],arm)
        status="SAT_VERIFIED"
    elif rc==20:
        assert proof.exists() and proof.stat().st_size, ("MISSING_PROOF",case["name"],arm)
        check=subprocess.run([str(PROOFCHECK),str(src),str(proof)],
                             capture_output=True,text=True,timeout=45)
        assert check.returncode==0 and "s VERIFIED" in check.stdout, (
            "BAD_DRAT",case["name"],arm,check.stdout[-500:],check.stderr[-500:])
        status="UNSAT_CERTIFIED"
    elif rc in (0,153,-9):
        status="UNKNOWN"
    else:
        raise AssertionError(("SOLVER_CRASH",case["name"],arm,rc,err[-800:]))
    verified=status in ("SAT_VERIFIED","UNSAT_CERTIFIED") and elapsed<=CAP
    if verified:assert status.split("_")[0]==case["expected"],("WRONG_VERDICT",case["name"],status)
    def stat(tag):
        a=[line.split(" ",1)[1] for line in err.splitlines() if line.startswith(tag+" ")]
        return json.loads(a[0]) if len(a)==1 else {}
    g=stat("MATH_GUARD_STATS")
    s=stat("X41_STATS")
    if arm=="GUARD_ON":assert g.get("enabled") is True
    proof.unlink(missing_ok=True)
    result=dict(name=case["name"],group=case["group"],n=n,edges=len(ed),
        cnf_sha256=sha,arm=arm,rep=rep,status=status,
        e2e_s=round(elapsed,7),PAR2=elapsed if verified else 2*CAP,
        verified=verified,conflicts=s.get("conflicts"),decisions=s.get("decisions"),
        guard_lemmas=g.get("lemmas",0),guard_pairs=g.get("pairs",0),
        guard_ms=g.get("wall_ms",0))
    print("GRAPH3_TRIAL "+json.dumps(result,sort_keys=True),flush=True)
    return result

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    assert SOLVER.is_file() and PROOFCHECK.is_file()
    cases=fixtures()
    for case in cases:
        if case["n"] <= 15:
            assert exact_colorable(case["n"],case["edges"]) == (case["expected"]=="SAT"),case["name"]
        if case["name"].startswith("planted_plus_K4"):
            assert set(clique(4)).issubset(set(case["edges"]))
    results=[]
    with tempfile.TemporaryDirectory() as td:
        for case in cases:
            for rep in range(REPS):
                arms=["GUARD_OFF","GUARD_ON"]
                random.Random(case["n"]*131+rep*17+len(case["edges"])).shuffle(arms)
                for arm in arms:
                    with tempfile.TemporaryDirectory(dir=td) as inner:
                        results.append(one_run(case,arm,rep,Path(inner)))
    OUT.mkdir(exist_ok=True)
    (OUT/"trials.json").write_text(json.dumps(results,indent=2,sort_keys=True)+"\n")
    pairs=[];improvements=[];slowdowns=[]
    for case in cases:
        for rep in range(REPS):
            x=next(r for r in results if r["name"]==case["name"] and r["rep"]==rep and r["arm"]=="GUARD_OFF")
            y=next(r for r in results if r["name"]==case["name"] and r["rep"]==rep and r["arm"]=="GUARD_ON")
            if x["verified"] and y["verified"]:
                ratio=x["e2e_s"]/y["e2e_s"]
                pairs.append(ratio)
                if ratio>1:improvements.append(case["name"])
                else:slowdowns.append(case["name"])
    summary=dict(instances=len(cases),runs=len(results),both_verified_pairs=len(pairs),
        verified_by_arm={a:sum(r["verified"] for r in results if r["arm"]==a) for a in ("GUARD_OFF","GUARD_ON")},
        PAR2_by_arm={a:sum(r["PAR2"] for r in results if r["arm"]==a) for a in ("GUARD_OFF","GUARD_ON")},
        guard_lemmas_total=sum(r["guard_lemmas"] for r in results),
        guard_ms_total=sum(r["guard_ms"] for r in results),
        median_paired_speedup=statistics.median(pairs) if pairs else None,
        improved_pairs=len(improvements),regressed_or_equal_pairs=len(slowdowns),
        one_logical_cpu=True,one_solver_process_at_a_time=True,
        prospective_synthetic=False,guard1_is_short_clause_resolution=True,
        performance_claim=False)
    (OUT/"report.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    print("GRAPH3_FINAL "+json.dumps(summary,sort_keys=True),flush=True)

if __name__=="__main__":
    main()
