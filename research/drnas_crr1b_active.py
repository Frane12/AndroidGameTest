#!/usr/bin/env python3
"""CRR1-B: active, budgeted, certificate-replayed CNF <-> GF(2) bridge.

A short XOR consequence is inserted into a COPY of the original formula only
if its source parity blocks are complete, its GF(2) derivation is replayed and
the binary implication graph cannot already establish the new clause.

"New" means missing from the graph's reachability closure, not necessarily
new information to the CDCL solver. In particular, no improvement is claimed
before paired, independently proof-checked results.

SAT: reconstruct and independently check on original CNF.
UNSAT: independently DRAT-check augmented CNF, AND replay original->added
clauses in the parent. The transformation never removes original clauses.
Development W4 source set already seen in CRR1-A; not a blind holdout.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import random
import re
import signal
import subprocess
import sys
import time

import drnas_crr1a_shadow as a

ROOT=Path("crr1b")
PROTO="DRNAS-CRR1B-W4-24x3x3-20s-ACTIVE-CERT-v1"
MODES=("kissat_plain","crr_shadow","crr_active")
CAP=20.0
REPS=3
SHARDS=8
BRIDGE_BUDGET=0.85
MAX_PROPOSALS=256
MAX_ADDED=64
MAX_GROWTH=0.015
MAX_BINARY_SCAN=50000
MAX_BFS_VISITS=20000
SOURCE=a.SOURCE
KISSAT=a.KISSAT
CHECKER=a.CHECKER

def need(ok,msg):
    if not ok:raise RuntimeError("CRR1B_FAIL_CLOSED "+str(msg))

def save(p,data):a.save(p,data)
def sha(p):return a.sha(p)
def parse(p):return a.parse(p)

def derive_exact(clauses,deadline):
    """Only derive XOR rows validated against original complete parity blocks."""
    eqs,covered,cap=a.xor_blocks(clauses,deadline)
    basis={}
    proposed={}
    rank=0
    for i,(vs,rhs,_) in enumerate(eqs):
        if i%16==0 and time.perf_counter()>=deadline:
            raise TimeoutError("GF2 elimination budget")
        row=set(vs); bit=rhs; cert={i}
        while row:
            pivot=min(row)
            if pivot not in basis:break
            old,parity,proof=basis[pivot]
            row.symmetric_difference_update(old)
            bit^=parity
            cert.symmetric_difference_update(proof)
        if not row:
            if bit:
                a.replay(eqs,cert,set(),1,clauses)
                return [],{"eqs":len(eqs),"rank":rank,"covered":covered,
                    "xor_cap":cap,"gf2_unsat":True}
            continue
        basis[min(row)]=(frozenset(row),bit,frozenset(cert))
        rank+=1
        if len(row)<=2 and len(proposed)<MAX_PROPOSALS:
            key=(tuple(sorted(row)),bit)
            if key not in proposed:
                a.replay(eqs,cert,row,bit,clauses)
                proposed[key]=tuple(sorted(cert))
    # A second certified sweep can shorten larger derived rows to <=2.
    for pivot,(vs,rhs,pr) in list(basis.items()):
        if time.perf_counter()>=deadline:break
        row=set(vs);bit=rhs;cert=set(pr)
        for otherpivot in sorted(basis,reverse=True):
            if time.perf_counter()>=deadline:break
            if otherpivot==pivot or otherpivot not in row:continue
            other,parity,proof=basis[otherpivot]
            if len(other)<len(row)+3:
                row.symmetric_difference_update(other)
                bit^=parity
                cert.symmetric_difference_update(proof)
        if row and len(row)<=2 and len(proposed)<MAX_PROPOSALS:
            key=(tuple(sorted(row)),bit)
            if key not in proposed:
                a.replay(eqs,cert,row,bit,clauses)
                proposed[key]=tuple(sorted(cert))
    rows=[{"vars":list(vs),"rhs":bit,"xor_source_indices":list(ids)}
          for (vs,bit),ids in proposed.items()]
    return (eqs,rows),{"eqs":len(eqs),"rank":rank,"covered":covered,
         "xor_cap":cap,"gf2_unsat":False,"derived_short_rows":len(rows)}

def graph_from_original(clauses,deadline):
    graph=collections.defaultdict(list)
    binary_count=0
    for i,c in enumerate(clauses):
        if i%1024==0 and time.perf_counter()>=deadline:
            raise TimeoutError("graph build budget")
        if len(c)!=2 or abs(c[0])==abs(c[1]):continue
        binary_count+=1
        if binary_count>MAX_BINARY_SCAN:
            return None,binary_count
        p,q=c
        graph[-p].append(q)
        graph[-q].append(p)
    return graph,binary_count

def reachable(graph,start,target,deadline):
    if graph is None:return False
    if start==target:return True
    visited={start};queue=collections.deque([start])
    steps=0
    while queue and steps<MAX_BFS_VISITS:
        if steps%512==0 and time.perf_counter()>=deadline:
            raise TimeoutError("reachability budget")
        v=queue.popleft();steps+=1
        for t in graph.get(v,()):
            if t==target:return True
            if t not in visited:
                visited.add(t);queue.append(t)
    return False

def graph_implies(graph,clause,deadline):
    if graph is None or len(clause)!=2:return False
    p,q=clause
    # One binary implication path suffices to entail p OR q.
    return (reachable(graph,-p,q,deadline) or
            reachable(graph,-q,p,deadline))

def make_bridge(n,clauses,budget=BRIDGE_BUDGET):
    """Return the EXACT extra clauses and each one's replayable certificate.

    Fail closed: if analysis has insufficient budget, add nothing.
    """
    started=time.perf_counter()
    deadline=started+budget
    meta={"status":"OK","source_variables":n,"original_clauses":len(clauses),
          "complete_xor_equations":0,"candidate_short_rows":0,
          "candidate_binary_clauses":0,"graph_redundant":0,
          "already_present":0,"attempted_novel_clauses":0,
          "added":0,"added_units":0,"added_binary":0,
          "budget_s":budget,"analysis_s":None,
          "reason":"none","certificate_checks":0}
    if n>30000 or len(clauses)>150000:
        meta.update(status="SKIPPED",reason="source_size",
                    analysis_s=time.perf_counter()-started)
        return [],[],meta
    try:
        d,info=derive_exact(clauses,deadline)
        meta["complete_xor_equations"]=info["eqs"]
        if info["gf2_unsat"]:
            meta.update(status="SKIPPED",reason="xor_contradiction_needs_separate_unsat_certificate")
            return [],[],meta
        equations,rows=d
        meta["candidate_short_rows"]=len(rows)
        graph,binary_count=graph_from_original(clauses,deadline)
        existing={tuple(sorted(c)) for c in clauses if len(c)<=2}
        extra=[];certificates=[]
        seen=set()
        for row in rows:
            if time.perf_counter()>=deadline:
                raise TimeoutError("candidate checking budget")
            vs=tuple(row["vars"]);rhs=row["rhs"]
            if len(vs)==1:
                options=[(vs[0] if rhs else -vs[0],)]
            elif len(vs)==2:
                options=list(a.to_binary(vs,rhs))
            else:continue
            for candidate in options:
                c=tuple(sorted(candidate))
                meta["candidate_binary_clauses"]+=len(c)==2
                if c in existing or c in seen:
                    meta["already_present"]+=1
                    continue
                if graph_implies(graph,c,deadline):
                    meta["graph_redundant"]+=1
                    continue
                meta["attempted_novel_clauses"]+=1
                # Do not accept a clause based on just a claimed GF2 result.
                # Independently reconstruct the exact original CNF XOR premises.
                a.replay(equations,row["xor_source_indices"],set(vs),rhs,clauses)
                meta["certificate_checks"]+=1
                if len(extra)>=MAX_ADDED:break
                seen.add(c)
                extra.append(c)
                certificates.append({"clause":list(c),"vars":list(vs),
                   "rhs":rhs,"xor_source_indices":row["xor_source_indices"]})
            if len(extra)>=MAX_ADDED:break
        if len(extra)>max(1,int(MAX_GROWTH*len(clauses))):
            extra=[];certificates=[]
            meta["reason"]="growth_gate"
        elif extra:
            meta["reason"]="verified_novel_short_GF2"
        else:meta["reason"]="no_novel_short_GF2"
        meta["added"]=len(extra)
        meta["added_units"]=sum(len(c)==1 for c in extra)
        meta["added_binary"]=sum(len(c)==2 for c in extra)
    except TimeoutError as exc:
        extra=[];certificates=[]
        meta.update(status="BUDGET_CUTOFF",reason=str(exc))
    meta["analysis_s"]=round(time.perf_counter()-started,6)
    return extra,certificates,meta

def certify_added(original,certificates):
    """Separate verifier: reconstruct XOR equations from ORIGINAL CNF."""
    eqs,_,_=a.xor_blocks(original,time.perf_counter()+12)
    seen=set()
    for item in certificates:
        vs=tuple(item["vars"]);rhs=item["rhs"]
        clause=tuple(sorted(item["clause"]))
        need(len(vs) in (1,2),"certificate var cardinality")
        if len(vs)==1:
            expected={(vs[0] if rhs else -vs[0],)}
        else:
            expected={tuple(sorted(c)) for c in a.to_binary(vs,rhs)}
        need(clause in expected and clause not in seen,
             "added clause does not follow its parity row")
        seen.add(clause)
        a.replay(eqs,item["xor_source_indices"],set(vs),rhs,original)
    return seen

def selftest():
    a.selftest()
    for rhs in (0,1):
        cnf=a.fixture_xor((1,2),0)+a.fixture_xor((1,2,3),rhs)
        extra,cert,meta=make_bridge(3,cnf,3)
        need(meta["status"]=="OK","small GF2 budget")
        need(len(extra)>0,"expected real algebraic reduction")
        need(certify_added(cnf,cert)==set(extra),"independent certificate replay")
        for mask in range(8):
            model={k:bool((mask>>(k-1))&1) for k in range(1,4)}
            orig=all(any(model[abs(x)]==(x>0) for x in c) for c in cnf)
            reduced=all(any(model[abs(x)]==(x>0) for x in c)
                        for c in list(cnf)+extra)
            need(orig==reduced,"CNF addition changed truth table")
    # Skip an already binary graph-implied clause.
    graph,_=graph_from_original([(1,2),(-2,3)],time.perf_counter()+3)
    need(graph_implies(graph,(1,3),time.perf_counter()+3),
         "implication transitive closure failure")
    print("CRR1B_SELFTEST_PASS",flush=True)

def manifest_cases():
    return a.manifest_cases()

def prepare():
    selftest()
    cases=manifest_cases()
    need(KISSAT.is_file() and CHECKER.is_file(),"missing pinned backend")
    for c in cases:
        need(sha(SOURCE/(c["id"]+".cnf"))==c["sha256"],"original SHA mismatch")
    manifest={"protocol":PROTO,"modes":list(MODES),"source_cohort":"W4 reused SAT2026 originals",
       "source_reuse_not_blind":True,"promotion_allowed":False,"cap_s":CAP,
       "reps":REPS,"shards":SHARDS,"formulas":len(cases),"cases_sha":[c["sha256"] for c in cases],
       "source_manifest_sha":sha("history/w4sources/manifest.json"),
       "analysis_budget_s":BRIDGE_BUDGET,"max_added":MAX_ADDED,
       "max_relative_growth":MAX_GROWTH,"candidate_source":"complete exact CNF XOR blocks only",
       "binary_graph_gate":"skip if original implication graph entails clause",
       "native_proof":"independent DRAT on augmented CNF PLUS original XOR entailment replay",
       "primary":"crr_active vs kissat_plain source-paired PAR2"}
    save(ROOT/"manifest.json",manifest)
    pinfiles=["research/drnas_crr1b_active.py","research/drnas_crr1a_shadow.py",
        ".github/workflows/drnas-crr1b-active.yml","checker/drat-trim",
        "built/bin/kissat_4_0_4","history/w4sources/manifest.json",
        "crr1b/manifest.json"]
    save(ROOT/"pins.json",{p:sha(p) for p in pinfiles})
    verify()
    print("CRR1B_PREPARE_PASS",sha(ROOT/"manifest.json"),flush=True)

def verify():
    cases=manifest_cases()
    m=json.loads((ROOT/"manifest.json").read_text())
    need(m["protocol"]==PROTO and m["modes"]==list(MODES) and
         m["cases_sha"]==[c["sha256"] for c in cases] and
         m["source_manifest_sha"]==sha("history/w4sources/manifest.json"),
         "manifest drift")
    for p,d in json.loads((ROOT/"pins.json").read_text()).items():
        need(sha(p)==d,"code/binary pin drift "+p)
    for c in cases:
        need(sha(SOURCE/(c["id"]+".cnf"))==c["sha256"],"original SHA drift")
    return cases

def worker(source,mode,directory):
    started=time.perf_counter()
    n,original=parse(source)
    active=mode=="crr_active"
    telemetry=None;certs=[];extra=[]
    if active:
        extra,certs,telemetry=make_bridge(n,original)
        need(len(extra)==len(certs),"certificate count mismatch")
        if extra:
            path=Path(directory)/"augmented.cnf"
            # The original formula is preserved in full; only proven clauses appended.
            with path.open("w") as out:
                out.write("p cnf %d %d\n"%(n,len(original)+len(extra)))
                for c in original:
                    out.write(" ".join(map(str,c))+" 0\n")
                for c in extra:
                    out.write(" ".join(map(str,c))+" 0\n")
            need(certify_added(original,certs)==set(extra),
                 "independent original premise replay failed")
            save(Path(directory)/"certificates.json",certs)
        else:path=Path(source)
    else:
        path=Path(source)
        if mode=="crr_shadow":telemetry=a.analyze(n,original)
    print(json.dumps({"event":"bridge","mode":mode,"telemetry":telemetry,
        "source_sha256":sha(source),"added":len(extra),"active":active,
        "prep_s":round(time.perf_counter()-started,6)}),flush=True)
    proof=(Path(directory)/"proof.drat").resolve()
    p=subprocess.run([str(KISSAT.resolve()),str(path.resolve()),str(proof)],
             stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    answers=re.findall(r"(?m)^s (SATISFIABLE|UNSATISFIABLE)\s*$",p.stdout)
    need(len(answers)==1 and p.returncode==(10 if answers[0]=="SATISFIABLE" else 20),
         "invalid native verdict/exit")
    status="SAT" if answers[0]=="SATISFIABLE" else "UNSAT"
    if status=="SAT":
        model={}
        for line in p.stdout.splitlines():
            if not line.startswith("v "):continue
            for token in line[2:].split():
                lit=int(token)
                if lit:
                    need(abs(lit) not in model or model[abs(lit)]==(lit>0),
                         "conflicting SAT witness")
                    model[abs(lit)]=lit>0
        def satisfies(cs):
            return all(any(model.get(abs(v))==(v>0) for v in c) for c in cs)
        need(satisfies(original) and satisfies(extra),"invalid original/augmented SAT model")
        save(Path(directory)/"model.json",model)
    print(json.dumps({"event":"result","verdict":status,"source_sha256":sha(source),
       "solver_cnf_sha256":sha(path),"added":len(extra)}),flush=True)

def trial(c,mode,rep,shard):
    source=SOURCE/(c["id"]+".cnf")
    need(sha(source)==c["sha256"],"source SHA mismatch")
    folder=ROOT/"raw"/str(shard)/(c["id"]+"-"+str(rep)+"-"+mode)
    folder.mkdir(parents=True,exist_ok=True)
    started=time.perf_counter()
    cmd=[sys.executable,__file__,"worker","--source",str(source),
        "--mode",mode,"--directory",str(folder)]
    p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                       text=True,start_new_session=True)
    timedout=False
    try:output,_=p.communicate(timeout=max(.001,CAP-(time.perf_counter()-started)))
    except subprocess.TimeoutExpired:
        timedout=True
        try:os.killpg(p.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        output,_=p.communicate()
    elapsed=min(CAP,time.perf_counter()-started)
    events=[]
    for line in output.splitlines():
        try:
            x=json.loads(line)
            if isinstance(x,dict):events.append(x)
        except ValueError:pass
    prep=[e for e in events if e.get("event")=="bridge"]
    terminal=[e for e in events if e.get("event")=="result"]
    status="TIMEOUT";evidence="WALL_CAP_TIMEOUT"
    reported=None;data=None
    if not timedout and elapsed<CAP:
        need(p.returncode==0 and len(prep)==len(terminal)==1,
             "worker failed "+output[-2500:])
        data=prep[0];end=terminal[0]
        need(data["source_sha256"]==c["sha256"] and
             end["source_sha256"]==c["sha256"],"source provenance invalid")
        reported=end["verdict"]
        extra_path=folder/"augmented.cnf"
        n,original=parse(source)
        if data["active"] and end["added"]:
            need(extra_path.is_file(),"augmented CNF disappeared")
            cert=json.loads((folder/"certificates.json").read_text())
            verified=certify_added(original,cert)
            need(len(verified)==end["added"],"certificate cardinality invalid")
            n_aug,clauses_aug=parse(extra_path)
            need(n_aug==n and len(clauses_aug)==len(original)+len(verified) and
                 clauses_aug[:len(original)]==original and
                 set(clauses_aug[len(original):])==verified,
                 "augmented CNF is not exact proven extension")
        else:
            need(not extra_path.exists() and end["added"]==0,
                 "unexpected solver transformation")
        solver_source=extra_path if end["added"] else source
        need(end["solver_cnf_sha256"]==sha(solver_source),"solver input changed")
        if reported=="SAT":
            model={int(k):v for k,v in json.loads((folder/"model.json").read_text()).items()}
            need(all(any(model.get(abs(l))==(l>0) for l in clause)
                     for clause in original),"SAT model fails original CNF")
            status="SAT";evidence="SAT_ORIGINAL_MODEL_VERIFIED"
        elif reported=="UNSAT":
            proof=folder/"proof.drat"
            if proof.is_file() and proof.stat().st_size:
                try:
                    check=subprocess.run([str(CHECKER.resolve()),
                          str(solver_source.resolve()),str(proof)],
                          stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                          text=True,timeout=180)
                    (folder/"proof_validation.log").write_text(check.stdout[-4500:])
                    if check.returncode==0 and "s VERIFIED" in check.stdout:
                        status="UNSAT";evidence="UNSAT_DRAT_CHECKED_AND_XOR_REPLAYED"
                    else:evidence="UNSAT_CERTIFICATE_INVALID_NOT_SCORED"
                except subprocess.TimeoutExpired:
                    (folder/"proof_validation.log").write_text("DRAT_CHECK_TIMEOUT")
                    evidence="UNSAT_CERTIFICATE_TIMEOUT_NOT_SCORED"
        else:need(False,"unrecognized native verdict")
    for name in ("proof.drat","augmented.cnf","certificates.json","model.json"):
        path=folder/name
        if path.exists():path.unlink()
    row={"protocol":PROTO,"id":c["id"],"sha256":c["sha256"],
         "mode":mode,"rep":rep,"shard":shard,
         "status":status,"reported_status":reported,"proof":evidence,
         "elapsed_s":round(elapsed,6),
         "par2_s":round(elapsed if status!="TIMEOUT" else 2*CAP,6),
         "prep_s":data["prep_s"] if data else None,
         "bridge":data["telemetry"] if data else None,
         "added":data["added"] if data else 0,
         "solver_cnf_sha256":terminal[0]["solver_cnf_sha256"] if data else None}
    print("CRR1B_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    return row

def shard(i):
    cases=verify()
    need(i in range(SHARDS),"shard")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    rows=[]
    for c in cases[i::SHARDS]:
        for rep in range(REPS):
            order=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(order)
            for mode in order:
                rows.append(trial(c,mode,rep,i))
                save(ROOT/("shard-%d.json"%i),rows)
    need(len(rows)==3*REPS*len(MODES),"incomplete shard")
    print("CRR1B_SHARD_PASS",i,len(rows),flush=True)

def audit():
    cases=verify()
    allrows=[];seen=set();valid={c["sha256"]:c for c in cases}
    for i in range(SHARDS):
        rows=json.loads((ROOT/("shard-%d.json"%i)).read_text())
        need(len(rows)==9*3,"incomplete pair shard")
        allowed={c["sha256"] for c in cases[i::SHARDS]}
        for r in rows:
            key=(r["sha256"],r["rep"],r["mode"])
            need(key not in seen and r["sha256"] in allowed and
                 r["id"]==valid[r["sha256"]]["id"] and r["protocol"]==PROTO and
                 r["shard"]==i and r["rep"] in range(REPS) and
                 r["mode"] in MODES,"trial provenance")
            seen.add(key)
            need(0<=r["elapsed_s"]<=CAP and
                 abs(r["par2_s"]-(2*CAP if r["status"]=="TIMEOUT"
                     else r["elapsed_s"]))<.00002,"invalid PAR2")
            need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"invalid verdict")
            need(r["status"]!="SAT" or
                 r["proof"]=="SAT_ORIGINAL_MODEL_VERIFIED","SAT witness not checked")
            need(r["status"]!="UNSAT" or
                 r["proof"]=="UNSAT_DRAT_CHECKED_AND_XOR_REPLAYED",
                 "UNSAT certificate not checked")
            allrows.append(r)
    expected={(c["sha256"],rep,m) for c in cases
              for rep in range(REPS) for m in MODES}
    need(seen==expected and len(allrows)==216,"expected 216 paired")
    for c in cases:
        statuses={r["status"] for r in allrows
                  if r["sha256"]==c["sha256"] and r["status"]!="TIMEOUT"}
        need(len(statuses)<=1,"contradictory SAT/UNSAT verdicts")
    totals={}
    for m in MODES:
        rr=[r for r in allrows if r["mode"]==m]
        totals[m]={"attempts":len(rr),
                   "solved":sum(r["status"]!="TIMEOUT" for r in rr),
                   "sat":sum(r["status"]=="SAT" for r in rr),
                   "unsat_verified":sum(r["status"]=="UNSAT" for r in rr),
                   "par2_s":round(sum(r["par2_s"] for r in rr),6),
                   "sources_with_additions":len({r["sha256"] for r in rr if r["added"]>0}),
                   "added_total_repeated":sum(r["added"] for r in rr)}
    p=totals["kissat_plain"]["par2_s"]
    c=totals["crr_active"]["par2_s"]
    report={"status":"CRR1B_AUDIT_PASS","protocol":PROTO,
            "attempts":216,"source_count":24,
            "not_blind":True,"promotion_allowed":False,
            "all_added_clauses_certified_from_original":True,
            "all_native_UNSAT_requires_DRAT_check":True,
            "totals":totals,
            "primary_ratio":round(p/c,6),
            "primary_gain_PAR2_s":round(p-c,6),
            "active_selected_sources":sorted({r["id"] for r in allrows
                       if r["mode"]=="crr_active" and r["added"]>0})}
    save(ROOT/"report.json",report)
    save(ROOT/"all-trials.json",allrows)
    print("CRR1B_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("selftest","prepare","worker","shard","audit"))
    p.add_argument("--source")
    p.add_argument("--directory")
    p.add_argument("--mode",choices=MODES)
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    if args.action=="worker":worker(args.source,args.mode,args.directory)
    elif args.action=="shard":shard(args.shard)
    else:globals()[args.action]()
