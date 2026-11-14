#!/usr/bin/env python3
"""Fresh frozen-seed synthetic graph 3-colouring A/B/C GUARD3 audit.

Every arm is the IDENTICAL native executable on ONE pinned logical CPU.
SAT models are checked on the original CNF; UNSAT DRAT proofs independently
checked with pinned drat-trim. Prospective seeds are disjoint from prior G2.
Graph labels follow mathematical construction, not solver outcomes.
"""
from pathlib import Path
import hashlib
import json
import os
import random
import resource
import statistics
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research/drnas_mathguard1"))
sys.path.insert(0,str(ROOT/"research/drnas_mathguard2"))
import graph3 as graph
from benchmark import chain_graph

SOLVER=ROOT/"build/drnas-mathguard3"
PROOFCHECK=ROOT/"external/drat-trim/drat-trim"
OUT=ROOT/"mathguard3_graph3"
CAP=3.0
REPS=5
ARMS=("BASE","GUARD2","GUARD3")

def permuted(n,ed,seed):
    order=list(range(n))
    random.Random(seed).shuffle(order)
    return graph.edges_clean(n,[(order[a],order[b]) for a,b in ed])

def fixtures():
    cases=[]
    def add(name,n,ed,expected,group):
        edges=graph.edges_clean(n,ed)
        cases.append(dict(name=name,n=n,edges=edges,expected=expected,group=group))
    # Never-used chain lengths and fresh vertex permutations, not G2's 3/6/10/20/30.
    for k in (5,8,13,17,23,29):
        for repseed in (811,1907):
            n,edges=chain_graph(k,False)
            add(f"chain_k{k}_seed{repseed}_sat",n,
                permuted(n,edges,repseed+100*k),"SAT","equality_chain_sat")
            n,edges=chain_graph(k,True)
            add(f"chain_k{k}_seed{repseed}_unsat",n,
                permuted(n,edges,repseed+100*k),"UNSAT","equality_chain_unsat")
    # New seeds and vertex permutations on satisfiable planted families, plus
    # obvious non-3-colourable K4 controls. Structure labels construction-proof.
    for n,seed,p in ((28,43011,.35),(45,43013,.32),(63,43017,.31),
                     (81,43019,.31),(90,43021,.29)):
        e=graph.planted(n,p,seed)
        add(f"planted_{n}_{seed}",n,permuted(n,e,seed+27),"SAT","planted_sat")
        add(f"plantedK4_{n}_{seed}",n,
            permuted(n,e+graph.clique(4),seed+27),"UNSAT","planted_k4_unsat")
    # K4-free 4-chromatic family does not expose the GUARD3 diamond-chain gate.
    for n in (5,7,9):
        size,ed=graph.mycielski(n,graph.cycle(n))
        add(f"mycielski_cycle_{n}",size,permuted(size,ed,n*971),
            "UNSAT","non_diamond_unsat")
    for rim in (5,7,9):
        n=rim+1
        add(f"odd_wheel_{n}",n,permuted(n,graph.wheel(rim),n*37),
            "UNSAT","non_diamond_unsat")
    assert len({x["name"] for x in cases})==len(cases)
    assert len(cases)==40
    for case in cases:
        if case["n"]<=15:
            assert graph.exact_colorable(case["n"],case["edges"]) == (case["expected"]=="SAT"),case["name"]
    return cases

def parse_stats(stderr,tag):
    x=[line.split(" ",1)[1] for line in stderr.splitlines()
       if line.startswith(tag+" ")]
    if len(x)!=1:raise RuntimeError(("MISSING_TELEMETRY",tag,len(x)))
    return json.loads(x[0])

def trial(case,arm,rep,temp):
    n=case["n"];ed=case["edges"];clauses=graph.cnf(n,ed)
    source=temp/"source.cnf"
    source.write_text(f"p cnf {3*n} {len(clauses)}\n"+
        "".join(" ".join(map(str,c))+" 0\n" for c in clauses))
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    proof=temp/"solve.drat"
    cmd=[str(SOLVER),str(source),"--mode","core","--x5-no-minimize",
         "--time",str(CAP-.1),"--stats","--proof",str(proof)]
    if arm=="GUARD2":cmd+=["--math-guard2","--math-guard2-budget-ms","8"]
    if arm=="GUARD3":cmd+=["--math-guard3","--math-guard2-budget-ms","8"]
    def limits():
        resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
    u0=resource.getrusage(resource.RUSAGE_CHILDREN)
    start=time.perf_counter()
    try:
        proc=subprocess.run(cmd,capture_output=True,text=True,timeout=CAP+.2,
                            preexec_fn=limits)
        rc=proc.returncode
        out=proc.stdout
        err=proc.stderr
    except subprocess.TimeoutExpired:
        rc=-9;out=err=""
    wall=time.perf_counter()-start
    u1=resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu=(u1.ru_utime+u1.ru_stime)-(u0.ru_utime+u0.ru_stime)
    status="UNKNOWN"
    if rc==10:
        if not graph.sat_model(out,n,clauses,ed):
            raise RuntimeError(("BAD_SAT_MODEL",case["name"],arm,rep))
        status="SAT_VERIFIED"
    elif rc==20:
        if not proof.exists() or not proof.stat().st_size:
            raise RuntimeError(("NO_PROOF",case["name"],arm))
        check=subprocess.run([str(PROOFCHECK),str(source),str(proof)],
                             timeout=45,text=True,capture_output=True)
        if check.returncode!=0 or "s VERIFIED" not in check.stdout:
            raise RuntimeError(("INVALID_DRAT",case["name"],arm,check.stdout[-400:]))
        status="UNSAT_CERTIFIED"
    elif rc not in (0,153,-9):
        raise RuntimeError(("SOLVER_CRASH",case["name"],arm,rc,err[-800:]))
    verified=status in ("SAT_VERIFIED","UNSAT_CERTIFIED") and wall<=CAP
    if verified and not status.startswith(case["expected"]):
        raise RuntimeError(("WRONG_VERDICT",case["name"],arm,status))
    g3=parse_stats(err,"MATH_GUARD3_STATS") if rc!=-9 else {}
    g2=parse_stats(err,"MATH_GUARD2_STATS") if rc!=-9 else {}
    s=parse_stats(err,"X41_STATS") if rc!=-9 else {}
    if arm=="GUARD3" and not g3.get("enabled"):
        raise RuntimeError(("MISSING_GUARD3_ENABLED",case["name"]))
    if arm=="GUARD3" and g3.get("triggered") and g3.get("selected_path",0)<3:
        raise RuntimeError(("BAD_GUARD3_TRIGGER",case["name"],g3))
    if arm=="GUARD3" and not g3.get("triggered") and g2.get("lemmas",0):
        raise RuntimeError(("UNTRIGGERED_GUARD3_EMITTED_LEMMAS",case["name"],g2))
    proof.unlink(missing_ok=True)
    row=dict(name=case["name"],group=case["group"],rep=rep,arm=arm,
        n=n,edges=len(ed),sha256=digest,status=status,verified=verified,
        wall_s=wall,cpu_s=cpu,PAR2=wall if verified else 2*CAP,
        conflicts=s.get("conflicts"),decisions=s.get("decisions"),
        g3_triggered=g3.get("triggered",False),
        g3_equalities=g3.get("equalities",0),
        g3_candidate_edges=g3.get("candidate_edges",0),
        g3_path=g3.get("selected_path",0),
        guard_lemmas=g2.get("lemmas",0),guard_ms=g2.get("wall_ms",0))
    print("GUARD3_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    return row

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    assert SOLVER.is_file() and PROOFCHECK.is_file()
    cases=fixtures()
    OUT.mkdir(exist_ok=True)
    manifest=[dict(name=c["name"],group=c["group"],vertices=c["n"],
                   edges=len(c["edges"]),expected=c["expected"],
                   graph_sha256=hashlib.sha256(json.dumps(c["edges"]).encode()).hexdigest())
              for c in cases]
    (OUT/"frozen_manifest.json").write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
    rows=[]
    with tempfile.TemporaryDirectory() as temp:
        for case in cases:
            for rep in range(REPS):
                arms=list(ARMS)
                random.Random(int(hashlib.sha256(case["name"].encode()).hexdigest()[:16],16)+rep*61).shuffle(arms)
                for arm in arms:
                    with tempfile.TemporaryDirectory(dir=temp) as folder:
                        rows.append(trial(case,arm,rep,Path(folder)))
    (OUT/"trials.json").write_text(json.dumps(rows,sort_keys=True,indent=2)+"\n")
    pairs=[]
    for case in cases:
        for rep in range(REPS):
            a=next(x for x in rows if x["name"]==case["name"] and x["rep"]==rep and x["arm"]=="BASE")
            b=next(x for x in rows if x["name"]==case["name"] and x["rep"]==rep and x["arm"]=="GUARD3")
            if a["verified"] and b["verified"]:
                assert a["status"]==b["status"]
                pairs.append(a["wall_s"]/b["wall_s"])
    aggregate={}
    for arm in ARMS:
        group= [x for x in rows if x["arm"]==arm]
        aggregate[arm]=dict(verified=sum(x["verified"] for x in group),
            PAR2_s=sum(x["PAR2"] for x in group),wall_s=sum(x["wall_s"] for x in group),
            cpu_s=sum(x["cpu_s"] for x in group),
            conflicts=sum(x["conflicts"] or 0 for x in group),
            decisions=sum(x["decisions"] or 0 for x in group),
            guard_lemmas=sum(x["guard_lemmas"] for x in group),
            triggered=sum(x["g3_triggered"] for x in group))
    families={}
    for family in sorted({c["group"] for c in cases}):
        families[family]={}
        for arm in ARMS:
            vals=[x for x in rows if x["arm"]==arm and x["group"]==family]
            families[family][arm]=dict(PAR2_s=sum(x["PAR2"] for x in vals),
                conflicts=sum(x["conflicts"] or 0 for x in vals),
                verified=sum(x["verified"] for x in vals),n=len(vals))
    summary=dict(instances=len(cases),runs=len(rows),repeats=REPS,
        verified_pairs=len(pairs),median_speedup=statistics.median(pairs) if pairs else None,
        aggregate=aggregate,families=families,
        one_logical_cpu=True,one_solver_process_at_a_time=True,
        source_selection="new predeclared deterministic generation seeds, no outcome-based filtering",
        artificial_graphs=True,independent_proof_verification=True,
        holdout_trained=False,promotion=False)
    (OUT/"report.json").write_text(json.dumps(summary,sort_keys=True,indent=2)+"\n")
    print("GUARD3_FINAL "+json.dumps(summary,sort_keys=True),flush=True)

if __name__=="__main__":main()
