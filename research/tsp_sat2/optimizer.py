#!/usr/bin/env python3
"""TSP-SAT2: standalone exact optimality search using SAT+externally checked UNSAT.

The *optimization process* never calls Held-Karp. A verified feasible tour gives
an upper bound; SAT models can improve it. An independently checked proof for
CNF(cost<=B) UNSAT raises the lower bound. Only a surviving original-CNF DRAT,
FRAT or VeriPB proof at B=U-1 plus a checked U-cost tour certifies optimality.

One solver process at a time / one logical CPU, no solver portfolio. All solver
results fail closed; UNKNOWN and resource limits NEVER become bounds.
The TSP->CNF encoder is exhaustively exercised at small n but not formally
verified; this is an experimental conditional optimality certificate.
"""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import random
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research/tsp_sat1"))
import encoding as enc

OUT=ROOT/"results/tsp_sat2"
CAP_QUERY_S=12.0
CAP_CASE_S=105.0
MAX_DECISIONS=18
REPS=2
CASES=(("euclid5_new",5,1021),("euclid6_new",6,1039),
       ("euclid7_new",7,1063),("euclid8_new",8,1097),
       ("euclid9_new",9,1151))
ARMS=("DRNAS_X59","DRNAS_STRUCTURE_GATE","Kissat","CaDiCaL","CryptoMiniSat")
BIN={"DRNAS_X59":"build/drnas-sat-native-x59",
     "DRNAS_STRUCTURE_GATE":"build/drnas-x59-structure-gate1",
     "Kissat":"build/kissat","CaDiCaL":"build/cadical",
     "CryptoMiniSat":"build/cms"}
PIN=tuple(sorted(set(BIN.values())|{"build/drat-trim","build/frat-rs",
    "veripb-tool/bin/veripb",
    "build/cms-libs/usr/lib/x86_64-linux-gnu/libcryptominisat5.so.5.11"}))

def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as fh:
        for chunk in iter(lambda:fh.read(1<<20),b""):h.update(chunk)
    return h.hexdigest()

def save(path,data):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")

def affinity():
    allowed=os.sched_getaffinity(0)
    os.sched_setaffinity(0,{min(allowed)})
    assert len(os.sched_getaffinity(0))==1

def coords_for(n,seed):
    r=random.Random(seed)
    result=[]
    while len(result)<n:
        p=[r.randrange(0,100),r.randrange(0,100)]
        if p not in result:result.append(p)
    return result

def nearest_neighbor(D):
    n=len(D)
    path=[0]
    remaining=set(range(1,n))
    while remaining:
        last=path[-1]
        j=min(remaining,key=lambda x:(D[last][x],x))
        remaining.remove(j)
        path.append(j)
    return tuple(path)

def two_opt(path,D):
    """Deterministic bounded, strictly improving tour refinement."""
    best=list(path)
    changed=True
    while changed:
        changed=False
        for i in range(1,len(best)-1):
            for j in range(i+1,len(best)):
                alt=best[:i]+list(reversed(best[i:j+1]))+best[j+1:]
                if enc.cost(alt,D)<enc.cost(best,D):
                    best=alt;changed=True;break
            if changed:break
    return tuple(best)

def lower_bound(D):
    """Every vertex of a symmetric Hamiltonian cycle has two neighbors."""
    total=0
    n=len(D)
    for i in range(n):
        vals=sorted(D[i][j] for j in range(n) if j!=i)
        total+=vals[0]+vals[1]
    return (total+1)//2

def command(arm,cnf,proof,cert):
    path=ROOT/BIN[arm]
    if arm=="DRNAS_X59":
        return [path,cnf,"--mode","core","--time",str(CAP_QUERY_S),
                "--proof",proof,"--stats"]
    if arm=="DRNAS_STRUCTURE_GATE":
        return [path,cnf,"--mode","core","--time",str(CAP_QUERY_S),
                "--math5-ms","100","--structure-gate-ms","12",
                "--math5-certificate",cert,"--proof",proof,"--stats"]
    if arm=="Kissat":return [path,cnf,proof]
    if arm=="CaDiCaL":return [path,"-q","--no-binary",cnf,proof]
    if arm=="CryptoMiniSat":
        return [path,"--threads=1","--verb=0","--frat="+str(proof),cnf]
    raise ValueError(arm)

def run(argv,limit):
    if limit<=0:return dict(returncode=124,timeout=True,stdout="",stderr="",wall_s=0)
    def restrict():
        resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,)*2)
        resource.setrlimit(resource.RLIMIT_FSIZE,(256*1024**2,)*2)
    env=dict(os.environ,OMP_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1",
        MKL_NUM_THREADS="1",
        LD_LIBRARY_PATH=str(ROOT/"build/cms-libs/usr/lib/x86_64-linux-gnu"))
    t=time.perf_counter()
    p=subprocess.Popen([str(x) for x in argv],stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,text=True,env=env,start_new_session=True,
        preexec_fn=restrict)
    expired=False
    try:out,err=p.communicate(timeout=max(.001,limit))
    except subprocess.TimeoutExpired:
        expired=True
        try:os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        out,err=p.communicate()
    return dict(returncode=p.returncode,timeout=expired,
        stdout=out,stderr=err,wall_s=time.perf_counter()-t)

def checked_unsat(proof,cnf,arm,limit):
    if arm=="CryptoMiniSat":
        cmd=[ROOT/"build/frat-rs","elab",proof,cnf,"-v"]
        kind="FRAT"
    else:
        cmd=[ROOT/"build/drat-trim",cnf,proof]
        kind="DRAT"
    verified=run(cmd,limit)
    success=(not verified["timeout"] and verified["returncode"]==0 and
             "VERIFIED" in verified["stdout"]+verified["stderr"])
    return success,kind,verified

def check_math5(cnf,cert,pbp,remaining):
    stages=[
      [sys.executable,ROOT/"research/math5/check_math5.py",cnf,cert],
      [sys.executable,ROOT/"research/math5/emit_veripb_eo_multiplicity.py",
       "--cnf",cnf,"--certificate",cert,"--output",pbp],
      [ROOT/"veripb-tool/bin/veripb","--cnf",cnf,pbp]]
    words=["UNSAT_MATH5_CERTIFICATE_VERIFIED","MATH5_VERIPB_EMITTED",
           "s VERIFIED UNSATISFIABLE"]
    elapsed=0.0
    for args,expected in zip(stages,words):
        available=remaining-elapsed
        if available<=0:return False,elapsed,"NO_PROOF_BUDGET"
        r=run(args,available)
        elapsed+=r["wall_s"]
        if r["timeout"]:return False,elapsed,"PROOF_CHECK_TIMEOUT"
        if r["returncode"]!=0 or expected not in r["stdout"]+r["stderr"]:
            # Generic MATH5 certificates might not have a standard converter.
            if args==stages[1] and r["returncode"]==2:
                return False,elapsed,"MATH5_EXPORT_UNSUPPORTED"
            return False,elapsed,"INVALID_MATH5_PROOF"
    return True,elapsed,"VERIPB_MATH5"

def solve_bound(coords,B,arm,work,limit,certificate_dir=None):
    """Returns independently verified SAT/UNSAT/UNKNOWN; never trusts exit code."""
    t=time.perf_counter()
    problem,info=enc.encode(coords,B)
    cnf=Path(work)/"decision.cnf"
    problem.output(cnf)
    cnf_hash=sha(cnf)
    proof=Path(work)/("proof.frat" if arm=="CryptoMiniSat" else "proof.drat")
    cert=Path(work)/"math5.json"
    pb=Path(work)/"math5.pbp"
    rem=min(CAP_QUERY_S,limit-(time.perf_counter()-t))
    result=run(command(arm,cnf,proof,cert),rem)
    status="UNKNOWN";kind=None;route=None;route_cost=None
    checked=False;critical=False;details=""
    checker_s=0.0;proof_sha=None
    if result["timeout"]:
        status="TIMEOUT"
    elif result["returncode"] in (10,20):
        expected="s SATISFIABLE" if result["returncode"]==10 else "s UNSATISFIABLE"
        if expected not in result["stdout"].splitlines():
            critical=True;status="INVALID_SOLVER_STATUS_LINE"
        elif result["returncode"]==10:
            try:
                if cert.exists():raise ValueError("unexpected structural proof on SAT")
                witness=enc.verify_sat(result["stdout"],cnf,info)
                route=witness["route"];route_cost=witness["route_cost"]
                if route_cost>B:raise ValueError("SAT route exceeds bound")
                checked=True;kind="MODEL";status="SAT_VERIFIED"
            except (ValueError,AssertionError,TypeError) as exc:
                critical=True;status="INVALID_SAT_MODEL";details=str(exc)[:240]
        elif cert.is_file():
            if proof.is_file() and proof.stat().st_size:
                critical=True;status="INVALID_MIXED_CERTIFICATES"
            else:
                available=min(CAP_QUERY_S,limit)-(time.perf_counter()-t)
                if available>0:
                    checked,checker_s,label=check_math5(cnf,cert,pb,available)
                    status="UNSAT_VERIFIED" if checked else label
                    if checked:kind="VERIPB_MATH5"
                    elif label=="INVALID_MATH5_PROOF":critical=True
                else:status="NO_CHECK_BUDGET"
        elif proof.is_file() and proof.stat().st_size:
            available=min(CAP_QUERY_S,limit)-(time.perf_counter()-t)
            if available>0:
                checked,kind,verifier=checked_unsat(proof,cnf,arm,available)
                checker_s=verifier["wall_s"]
                if checked:status="UNSAT_VERIFIED"
                elif verifier["timeout"]:status="PROOF_CHECK_TIMEOUT"
                else:critical=True;status="INVALID_DRAT_FRAT"
            else:status="NO_CHECK_BUDGET"
        else:status="UNSAT_UNVERIFIED"
    elif result["returncode"] in (137,-9,-11,-25):
        status="RESOURCE_LIMIT"
    elif result["returncode"] not in (0,153,None):
        critical=True;status="SOLVER_ERROR";details=result["stderr"][-240:]

    elapsed=time.perf_counter()-t
    if elapsed>min(CAP_QUERY_S,limit):
        checked=False
        if not critical:status="E2E_OVER_CAP"
    if checked and status=="UNSAT_VERIFIED":
        chosen=pb if kind=="VERIPB_MATH5" else proof
        assert chosen.is_file()
        proof_sha=sha(chosen)
        if certificate_dir is not None:
            # Keep the original CNF and standard proof for EVERY accepted
            # UNSAT bound. Retaining only the last one loses the proof chain.
            certificate_dir=Path(certificate_dir)/f"bound-{B}"
            certificate_dir.mkdir(parents=True,exist_ok=True)
            target=certificate_dir/("refutation.pbp" if kind=="VERIPB_MATH5"
                                   else "refutation.frat" if kind=="FRAT" else "refutation.drat")
            if (certificate_dir/"metadata.json").exists():
                raise RuntimeError("DUPLICATE_UNSAT_BOUND_PROOF")
            shutil.copyfile(cnf,certificate_dir/"decision.cnf")
            shutil.copyfile(chosen,target)
            if kind=="VERIPB_MATH5":
                shutil.copyfile(cert,certificate_dir/"source_cert.json")
            save(certificate_dir/"metadata.json",dict(
                bound=B,kind=kind,source_sha256=cnf_hash,
                proof_sha256=proof_sha,proof_file=target.name))
    return dict(B=B,status=status,kind=kind,accepted=bool(checked),
        critical=critical,reason=details,cnf_sha256=cnf_hash,
        cnf_vars=problem.nvars,cnf_clauses=len(problem.clauses),
        model_route=route,route_cost=route_cost,
        proof_sha256=proof_sha,
        solver_s=round(result["wall_s"],6),
        checker_s=round(checker_s,6),e2e_s=round(elapsed,6))

def optimize(coords,arm,root):
    assert arm in ARMS
    started=time.perf_counter()
    D=enc.euc_distance(coords)
    first=nearest_neighbor(D)
    initial_cost=enc.cost(first,D)
    route=two_opt(first,D)
    U=enc.cost(route,D)
    L=lower_bound(D)
    assert L<=U,(L,U,"bad lower-bound derivation")
    initial_L=L
    log=[]
    proofs=Path(root)/"proof"
    reason="NO_QUERY";critical=False
    tried=set()
    # SAT query at the initial feasible incumbent; this is evidence that the
    # selected solver can actually find an original-CNF-checked route.
    def query(B):
        nonlocal reason,critical
        if B<0:raise ValueError("negative bound")
        available=CAP_CASE_S-(time.perf_counter()-started)
        if available<=0:
            reason="TOTAL_BUDGET_EXHAUSTED";return None
        with tempfile.TemporaryDirectory(prefix="drnas-tsp-sat2-") as td:
            row=solve_bound(coords,B,arm,td,available,proofs)
        log.append(row)
        tried.add(B)
        if row["critical"]:
            critical=True;reason="CRITICAL_"+row["status"]
        elif not row["accepted"]:
            reason=row["status"]
        return row

    probe=query(U)
    if probe and probe["accepted"] and probe["status"]=="SAT_VERIFIED":
        if probe["route_cost"]<U:
            U=probe["route_cost"];route=tuple(probe["model_route"])
    # If SAT initial probe was unknown, the constructive route is still valid.
    while not critical and L<U and len(log)<MAX_DECISIONS:
        B=(L+U-1)//2
        if B in tried:break
        row=query(B)
        if row is None or not row["accepted"]:break
        if row["status"]=="SAT_VERIFIED":
            assert row["route_cost"]<=B<U
            U=row["route_cost"];route=tuple(row["model_route"])
        elif row["status"]=="UNSAT_VERIFIED":
            L=B+1
        else:break
    # If the cheap bound matched the route before any UNSAT query, still
    # require an independently checkable original-CNF proof at U-1.
    target=U-1
    metadata=proofs/f"bound-{target}"/"metadata.json"
    prior=(json.loads(metadata.read_text()) if metadata.exists() else None)
    if (not critical and len(log)<MAX_DECISIONS and U>=1 and
        prior is None):
        row=query(target)
        if row and row["accepted"] and row["status"]=="UNSAT_VERIFIED":
            L=max(L,target+1)
        elif row and row["accepted"] and row["status"]=="SAT_VERIFIED":
            # This is a sound new tour and must never be classified optimal.
            if row["route_cost"]<U:
                U=row["route_cost"];route=tuple(row["model_route"])
            reason="IMPROVEMENT_AT_FINAL_BOUND_REQUIRES_MORE_SEARCH"

    metadata=proofs/f"bound-{U-1}"/"metadata.json"
    prior=(json.loads(metadata.read_text()) if metadata.exists() else None)
    proofdir=metadata.parent
    certificate=bool(prior and prior["bound"]==U-1 and
         (proofdir/prior["proof_file"]).is_file() and
         sha(proofdir/prior["proof_file"])==prior["proof_sha256"] and
         sha(proofdir/"decision.cnf")==prior["source_sha256"])
    proof_found=any(row["status"]=="UNSAT_VERIFIED" and row["accepted"] and
                    row["B"]==U-1 for row in log)
    # A directly checked U-cost Hamiltonian cycle AND verified UNSAT at U-1
    # force the exact optimum, for the supplied integer-distance TSP mapping.
    optimal=(not critical and certificate and proof_found and
             len(route)==len(coords) and len(set(route))==len(coords)
             and route[0]==0 and enc.cost(route,D)==U)
    elapsed=time.perf_counter()-started
    return dict(status=("ERROR" if critical else "OPTIMAL_CERTIFIED" if optimal
                   else "FEASIBLE_NOT_CERTIFIED"),
       arm=arm,initial_route=list(first),initial_cost=initial_cost,
       after_two_opt_cost=enc.cost(two_opt(first,D),D),
       initial_lower_bound=initial_L,final_lower_bound=L,
       best_route=list(route),best_cost=U,proof_at_bound=U-1 if optimal else None,
       certificate=prior if optimal else None,
       queries=len(log),steps=log,reason=reason,
       wall_s=round(elapsed,6),critical=critical,
       cap_case_s=CAP_CASE_S,cap_query_s=CAP_QUERY_S)

def freeze():
    affinity()
    enc.selftest()
    cases=[]
    for name,n,seed in CASES:
        coords=coords_for(n,seed)
        src=OUT/"sources"/(name+".json")
        save(src,dict(name=name,n=n,seed=seed,metric="INTEGER_EUC_2D",
                      coords=coords))
        D=enc.euc_distance(coords)
        heuristic=nearest_neighbor(D)
        cases.append(dict(name=name,n=n,seed=seed,coords=coords,
            source_path=str(src.relative_to(ROOT)),source_sha256=sha(src),
            lower_bound=lower_bound(D),heuristic_cost=enc.cost(heuristic,D)))
    save(OUT/"manifest.json",dict(
        protocol="DRNAS-TSP-SAT2-PROSPECTIVE-SEED-PILOT-V1",
        cases=cases,
        note="New seeded synthetic Euclidean instances, not a TSPLIB or fully historically unseen holdout; no Held-Karp at source selection or during search."))
    p=dict(git_sha=os.environ.get("GITHUB_SHA"),manifest_sha256=sha(OUT/"manifest.json"),
         code_sha256=sha(Path(__file__)),
         encoder_sha256=sha(ROOT/"research/tsp_sat1/encoding.py"),
         pinned={path:sha(ROOT/path) for path in PIN},
         cases=len(cases),arms=ARMS,reps=REPS,cap_query_s=CAP_QUERY_S,
         cap_case_s=CAP_CASE_S,max_decisions=MAX_DECISIONS,
         trials=len(cases)*len(ARMS)*REPS,
         one_logical_cpu=True,no_parallel_portfolio=True,
         final_proof_audited_separately=True,no_main_promotion=True,
         held_karp_excluded_from_search=True)
    save(OUT/"protocol.json",p)
    print("TSP_SAT2_READY "+json.dumps({
        "cases":len(cases),"trials":p["trials"],
        "source_sha":p["manifest_sha256"],
        "heuristic_costs":{c["name"]:c["heuristic_cost"] for c in cases},
        "lower_bounds":{c["name"]:c["lower_bound"] for c in cases}},
        sort_keys=True),flush=True)

def check():
    affinity()
    m=json.loads((OUT/"manifest.json").read_text())
    p=json.loads((OUT/"protocol.json").read_text())
    assert p["git_sha"]==os.environ.get("GITHUB_SHA")
    assert p["code_sha256"]==sha(Path(__file__))
    assert p["encoder_sha256"]==sha(ROOT/"research/tsp_sat1/encoding.py")
    assert p["manifest_sha256"]==sha(OUT/"manifest.json")
    assert p["pinned"]=={path:sha(ROOT/path) for path in PIN}
    assert p["trials"]==len(CASES)*len(ARMS)*REPS
    assert [(x["name"],x["n"],x["seed"]) for x in m["cases"]]==list(CASES)
    for c in m["cases"]:
        assert sha(ROOT/c["source_path"])==c["source_sha256"]
        assert c["coords"]==coords_for(c["n"],c["seed"])
    return m,p

def shard(i):
    assert 0<=i<len(CASES)
    m,p=check()
    case=m["cases"][i]
    folder=OUT/("case-"+str(i))
    folder.mkdir(parents=True,exist_ok=False)
    reports=[]
    for rep in range(REPS):
        order=list(ARMS)
        random.Random(f"{case['source_sha256']}:{rep}:tsp-sat2").shuffle(order)
        for arm in order:
            target=folder/f"{arm}-rep{rep}"
            target.mkdir(parents=True,exist_ok=False)
            output=optimize(case["coords"],arm,target)
            output.update(name=case["name"],n=case["n"],rep=rep,
                          source_sha256=case["source_sha256"])
            # compact progress log; full proof evidence stored in artifacts.
            save(target/"record.json",output)
            with (folder/"trials.jsonl").open("a") as fd:
                fd.write(json.dumps(output,sort_keys=True)+"\n");fd.flush()
            reports.append(output)
            print("TSP_SAT2_TRIAL "+json.dumps(dict(
                name=case["name"],arm=arm,rep=rep,
                status=output["status"],route_cost=output["best_cost"],
                queries=output["queries"],elapsed_s=output["wall_s"],
                proof_at=output["proof_at_bound"],
                statuses=[row["status"] for row in output["steps"]]
            ),sort_keys=True),flush=True)
            if output["critical"]:raise RuntimeError("CRITICAL_POSSIBLY_WRONG_PROOF")
    assert len(reports)==REPS*len(ARMS)
    print("TSP_SAT2_SHARD "+json.dumps(dict(
        name=case["name"],trials=len(reports)),sort_keys=True),flush=True)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("prepare","shard"))
    parser.add_argument("--index",type=int)
    args=parser.parse_args()
    if args.action=="prepare":freeze()
    else:shard(args.index)

if __name__=="__main__":main()
