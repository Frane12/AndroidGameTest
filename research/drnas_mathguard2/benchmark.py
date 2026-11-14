#!/usr/bin/env python3
"""Independent paired original X59 / GUARD1 / certified GUARD2 graph-3-colour tests.

A diamond chain forces all endpoints to share one colour. Adding an edge
between first and last produces a nontrivial, K4-free UNSAT graph.
Proofs and SAT models are checked independently. Run serially on one CPU.
"""
import hashlib
import json
import os
from pathlib import Path
import random
import resource
import statistics
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research/drnas_mathguard1"))
import graph3 as g1

SOLVER=ROOT/"build/drnas-mathguard2"
PROOF=ROOT/"external/drat-trim/drat-trim"
OUT=ROOT/"mathguard2_graph3"
CAP=2.5
REPS=3

def chain_graph(k,close):
    # Vertices u0...uk (the equality chain), plus two distinct shared-edge
    # anchors a_i,b_i for each step.
    n=3*k+1
    e=[]
    for i in range(k):
        a=k+1+2*i
        b=a+1
        e.extend([(a,b),(a,i),(b,i),(a,i+1),(b,i+1)])
    if close:e.append((0,k))
    return n,g1.edges_clean(n,e)

def fixtures():
    suite=g1.fixtures()
    for k in (3,6,10,20,30):
        for close in (False,True):
            n,ed=chain_graph(k,close)
            suite.append(dict(name=f"diamond_chain_{k}_"+("UNSAT" if close else "SAT"),
                n=n,edges=ed,expected="UNSAT" if close else "SAT",group="diamond_chain"))
    # Any bound below is a mathematical construction invariant; it is
    # not a label inferred from the solver output.
    assert len({x["name"] for x in suite})==len(suite)
    for case in suite:
        if case["n"]<=15:
            expected=g1.exact_colorable(case["n"],case["edges"])
            assert expected==(case["expected"]=="SAT"),case["name"]
    return suite

def run_one(case,arm,rep,folder):
    n=case["n"];edges=case["edges"];clauses=g1.cnf(n,edges)
    cnf=folder/"graph.cnf"
    cnf.write_text(f"p cnf {3*n} {len(clauses)}\n" +
        "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
    sha=hashlib.sha256(cnf.read_bytes()).hexdigest()
    proof=folder/"proof.drat"
    cmd=[str(SOLVER),str(cnf),"--mode","core","--x5-no-minimize",
         "--time",str(CAP-.08),"--proof",str(proof),"--stats"]
    if arm=="GUARD1":cmd+=["--math-guard","--math-guard-budget-ms","4"]
    if arm=="GUARD2":cmd+=["--math-guard2","--math-guard2-budget-ms","8"]
    def limit():
        resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
    start=time.perf_counter()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=CAP+.2,
                         preexec_fn=limit)
        stdout,stderr,rc=p.stdout,p.stderr,p.returncode
    except subprocess.TimeoutExpired:
        stdout=stderr="";rc=-9
    wall=time.perf_counter()-start
    status="UNKNOWN"
    if rc==10:
        if not g1.sat_model(stdout,n,clauses,edges):
            raise RuntimeError(("INVALID_MODEL",case["name"],arm,rep))
        status="SAT_VERIFIED"
    elif rc==20:
        if not proof.exists() or not proof.stat().st_size:
            raise RuntimeError(("MISSING_UNSAT_PROOF",case["name"],arm))
        verify=subprocess.run([str(PROOF),str(cnf),str(proof)],timeout=45,
                              capture_output=True,text=True)
        if verify.returncode!=0 or "s VERIFIED" not in verify.stdout:
            raise RuntimeError(("UNVERIFIED_UNSAT",case["name"],arm,verify.stdout[-500:]))
        status="UNSAT_CERTIFIED"
    elif rc not in (0,153,-9):
        raise RuntimeError(("NATIVE_SOLVER_CRASH",case["name"],arm,rc,stderr[-900:]))
    verified=status in ("SAT_VERIFIED","UNSAT_CERTIFIED") and wall<=CAP
    if verified and not status.startswith(case["expected"]):
        raise RuntimeError(("INVALID_VERDICT",case["name"],arm,status))
    def stats(name):
        rows=[line.split(" ",1)[1] for line in stderr.splitlines()
              if line.startswith(name+" ")]
        return json.loads(rows[0]) if len(rows)==1 else {}
    s=stats("X41_STATS")
    g1s=stats("MATH_GUARD_STATS")
    g2=stats("MATH_GUARD2_STATS")
    if arm=="GUARD2" and not g2.get("enabled"):
        raise RuntimeError(("MISSING_GUARD2_STATS",case["name"]))
    proof.unlink(missing_ok=True)
    row=dict(name=case["name"],group=case["group"],vertices=n,edges=len(edges),
        cnf_sha256=sha,expected=case["expected"],rep=rep,arm=arm,status=status,
        verified=verified,e2e_s=wall,PAR2=wall if verified else 2*CAP,
        conflicts=s.get("conflicts"),decisions=s.get("decisions"),
        guard1_lemmas=g1s.get("lemmas",0),
        guard2_diamonds=g2.get("diamonds",0),guard2_lemmas=g2.get("lemmas",0),
        guard2_binary=g2.get("binary",0),guard2_wall_ms=g2.get("wall_ms",0),
        guard2_budget_hit=g2.get("budget_hit",False))
    print("GRAPH3_G2_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    return row

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    if not SOLVER.is_file() or not PROOF.is_file():raise RuntimeError("MISSING_BINARY")
    suite=fixtures()
    rows=[]
    with tempfile.TemporaryDirectory() as root:
        for case in suite:
            for rep in range(REPS):
                arms=["BASE","GUARD1","GUARD2"]
                random.Random(int(hashlib.sha256(case["name"].encode()).hexdigest()[:12],16)+rep).shuffle(arms)
                for arm in arms:
                    with tempfile.TemporaryDirectory(dir=root) as td:
                        rows.append(run_one(case,arm,rep,Path(td)))
    OUT.mkdir(exist_ok=True)
    (OUT/"trials.json").write_text(json.dumps(rows,indent=2,sort_keys=True)+"\n")
    pair_ratio=[]; improvements=[];regressions=[]
    for case in suite:
        for rep in range(REPS):
            a=next(r for r in rows if r["name"]==case["name"] and r["rep"]==rep and r["arm"]=="BASE")
            b=next(r for r in rows if r["name"]==case["name"] and r["rep"]==rep and r["arm"]=="GUARD2")
            if a["verified"] and b["verified"]:
                if a["status"]!=b["status"]:raise RuntimeError("CONTRADICTORY_VERDICTS")
                ratio=a["e2e_s"]/b["e2e_s"]
                pair_ratio.append(ratio)
                if ratio>1.05:improvements.append((case["name"],rep,ratio))
                if ratio<.95:regressions.append((case["name"],rep,ratio))
    summary=dict(graphs=len(suite),runs=len(rows),both_verified_pairs=len(pair_ratio),
        verified={a:sum(r["verified"] for r in rows if r["arm"]==a)
                  for a in ("BASE","GUARD1","GUARD2")},
        PAR2={a:sum(r["PAR2"] for r in rows if r["arm"]==a)
             for a in ("BASE","GUARD1","GUARD2")},
        median_speedup=statistics.median(pair_ratio) if pair_ratio else None,
        guard2_motifs=sum(r["guard2_diamonds"] for r in rows),
        guard2_lemmas=sum(r["guard2_lemmas"] for r in rows),
        guard2_binary=sum(r["guard2_binary"] for r in rows),
        guard2_ms_total=sum(r["guard2_wall_ms"] for r in rows),
        faster_by_more_than_5pct=len(improvements),
        slower_by_more_than_5pct=len(regressions),
        one_cpu=True,one_solver_process_at_a_time=True,
        retrospective=False,synthetic=True,holdout=False,promotion=False)
    (OUT/"report.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    print("GRAPH3_G2_FINAL "+json.dumps(summary,sort_keys=True),flush=True)

if __name__=="__main__":main()
