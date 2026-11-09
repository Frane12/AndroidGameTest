#!/usr/bin/env python3
"""DRNAS CRR-S2 native proof-first pilot: frozen original SHA, 1 logical CPU,
RUP-only additions, full preprocessing wall time inside cap, strict E2E audit.
Diagnostic pilot on three PREVIOUSLY SEEN original 2021-23 formulas.
No UNSAT is certified here by LRAT; original-backend agreement only.
"""
import argparse
import hashlib
import json
import os
import pathlib
import resource
import subprocess
import tempfile
import time
import sys
import drnas_crr1_gf2_scc_rup as core

PROTO="DRNAS-CRRS3-NATIVE-WATCHED-RUP-3SEEN-ONECPU-8S-v1"
PREFIXES=("7f25d086","a43d096e","404763ef")
ARMS=("kissat_raw","kissat_s2_all","kissat_s3_shadow","kissat_s3_gate","cadical_raw")
CAP=8.0
PREP_MS=350
REPS=2
def check(ok,msg):
    if not ok: raise RuntimeError("CRRS3_FAIL_CLOSED "+msg)
def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for b in iter(lambda:f.read(1048576),b""):h.update(b)
    return h.hexdigest()
def cases(path):
    manifest=json.loads(pathlib.Path(path).read_text())
    check(len(manifest.get("cases",[]))==24,"frozen original count")
    found=[]
    for prefix in PREFIXES:
        a=[c for c in manifest["cases"] if c["sha256"].startswith(prefix)]
        check(len(a)==1,"missing or multiple SHA prefix "+prefix)
        found.append(a[0])
    check(len({c["sha256"] for c in found})==len(PREFIXES),"duplicate source")
    return found
def usage():
    a=resource.getrusage(resource.RUSAGE_CHILDREN)
    return a.ru_utime+a.ru_stime
def native_probe(binary,source,output,mode):
    start=time.perf_counter()
    c0=usage()
    stats=dict(added=0,rup_checked=0,candidate_count=0,gate_probed=0,
               gate_rejected=0,gate_positive=0,gate_score_sum=0,xor_rows=0,
               xor4=0,scc_equiv=0,emitted_lemmas=[],
               native_status="NOT_STARTED",prep_wall_s=0.,prep_cpu_s=0.)
    try:
        p=subprocess.run([str(binary),str(source),str(output),str(PREP_MS),mode],
                         capture_output=True,text=True,errors="replace",timeout=0.75)
        a=[s.split(" ",1)[1] for s in p.stdout.splitlines()
           if s.startswith("CRRS3_NATIVE ")]
        if p.returncode==0 and len(a)==1 and pathlib.Path(output).is_file():
            obj=json.loads(a[0])
            check(len(obj.get("emitted_lemmas",[]))==obj.get("added",-1),
                  "native metadata mismatch")
            stats.update(obj)
            stats["native_status"]="OK_TIMED" if obj.get("timed_out") else "OK"
        else:
            stats["native_status"]="ABSTAIN_RETURN_"+str(p.returncode)
    except subprocess.TimeoutExpired:
        stats["native_status"]="ABSTAIN_PROCESS_TIMEOUT"
    finally:
        stats["prep_wall_s"]=round(time.perf_counter()-start,6)
        stats["prep_cpu_s"]=round(max(0,usage()-c0),6)
    # No half-written native output can be consumed. We require fully parsed output.
    if not stats["native_status"].startswith("OK"):
        stats["added"]=0
        stats["emitted_lemmas"]=[]
    return stats
def run_solver(binary,cnf,remaining):
    if remaining<=0.001:
        return dict(status="TIMEOUT",solve_wall_s=0.,child_cpu_s=0.,stdout="")
    start=time.perf_counter()
    c0=usage()
    try:
        p=subprocess.run([str(binary),str(cnf)],capture_output=True,text=True,
                         errors="replace",timeout=max(0.001,remaining))
        data=p.stdout+"\n"+p.stderr
        if p.returncode==10 and "SATISFIABLE" in data and "UNSATISFIABLE" not in data:
            status="SAT"
        elif p.returncode==20 and "UNSATISFIABLE" in data: status="UNSAT"
        else: status="UNKNOWN"
    except subprocess.TimeoutExpired:
        status="TIMEOUT"
        data=""
    return dict(status=status,solve_wall_s=round(time.perf_counter()-start,6),
                child_cpu_s=round(max(0,usage()-c0),6),
                stdout=data if status=="SAT" else "")
def verify_model(output,clauses,n):
    vals={}
    for line in output.splitlines():
        if not line.startswith("v "):continue
        for word in line[2:].split():
            try:lit=int(word)
            except ValueError:continue
            if 0<abs(lit)<=n:vals[abs(lit)]=lit>0
    return all(any(vals.get(abs(lit))==(lit>0) for lit in c) for c in clauses)
def bench(a):
    cpus=os.sched_getaffinity(0)
    check(bool(cpus),"no available CPU")
    cpu=min(cpus)
    os.sched_setaffinity(0,{cpu})
    selected=cases(a.manifest)
    consensus=set(json.loads(pathlib.Path(a.consensus).read_text())["historical_consensus"])
    rows=[]
    out=pathlib.Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    for idx,c in enumerate(selected):
        if idx%2!=a.shard:continue
        source=pathlib.Path(a.root)/c["filename"]
        check(source.is_file() and sha(source)==c["sha256"],"source SHA mismatch")
        n,original=core.parse(source)
        for rep in range(REPS):
            for arm in ARMS:
                with tempfile.TemporaryDirectory() as td:
                    stats=dict(added=0,rup_checked=0,candidate_count=0,
                               gate_probed=0,gate_rejected=0,gate_positive=0,
                               gate_score_sum=0,prep_wall_s=0.,prep_cpu_s=0.,native_status="SKIP",
                               emitted_lemmas=[])
                    runfile=source
                    if arm in ("kissat_s2_all","kissat_s3_shadow","kissat_s3_gate"):
                        modified=pathlib.Path(td)/"modified.cnf"
                        mode="all" if arm=="kissat_s2_all" else "gate"
                        stats=native_probe(a.native,source,modified,mode)
                        if (arm in ("kissat_s2_all","kissat_s3_gate")
                            and stats["native_status"].startswith("OK") and stats["added"]):
                            runfile=modified
                    remaining=max(0.,CAP-stats["prep_wall_s"])
                    binary=a.cadical if arm=="cadical_raw" else a.kissat
                    solved=run_solver(binary,runfile,remaining)
                    status=solved.pop("status")
                    model=solved.pop("stdout")
                    witness=verify_model(model,original,n) if status=="SAT" else False
                    unsat=(status=="UNSAT" and c["sha256"] in consensus)
                    accepted=witness or unsat
                    label=("SAT_VERIFIED" if witness else
                           "UNSAT_CONSENSUS_NO_LRAT" if unsat else
                           "SAT_INVALID" if status=="SAT" else
                           "UNSAT_UNCONFIRMED" if status=="UNSAT" else status)
                    wall=round(stats["prep_wall_s"]+solved["solve_wall_s"],6)
                    child_cpu=round(stats["prep_cpu_s"]+solved["child_cpu_s"],6)
                    row=dict(protocol=PROTO,original_sha256=c["sha256"],gbd=c["gbd"],
                             arm=arm,rep=rep,cap_s=CAP,
                             allocated_logical_cpus=1,cpu_affinity=[cpu],
                             raw_status=status,status=label,accepted=accepted,
                             SAT_original_witness_verified=witness,
                             UNSAT_historical_consensus_no_LRAT=unsat,
                             independent_UNSAT_LRAT=False,
                             original_sha_verified=sha(source)==c["sha256"],
                             E2E_s=wall,CPU_s=child_cpu,
                             PAR2_s=wall if accepted else 2*CAP,
                             CPU_PAR2_s=child_cpu if accepted else 2*CAP,
                             prep=stats,solve=solved)
                    check(row["original_sha_verified"],"source drift")
                    check(wall<=CAP+0.1,"E2E budget exceeded")
                    rows.append(row)
                    out.write_text(json.dumps(rows,indent=2)+"\n")
                    print("CRRS3_TRIAL "+json.dumps({k:row[k] for k in
                      ("original_sha256","arm","rep","status","accepted",
                       "E2E_s","CPU_s","PAR2_s")}|
                      {"added":stats["added"],"rup_checked":stats["rup_checked"],
                       "prep_s":stats["prep_wall_s"],
                       "native_status":stats["native_status"]},sort_keys=True),flush=True)
    check(len(rows)==(2 if a.shard==0 else 1)*REPS*len(ARMS),
          "incomplete shard")
    print("CRRS3_SHARD_PASS",a.shard,len(rows),flush=True)
def audit(a):
    allrows=[]
    for i in (0,1):
        allrows+=json.loads((pathlib.Path(a.folder)/f"shard-{i}.json").read_text())
    selected=cases(a.manifest)
    expected={(c["sha256"],arm,rep) for c in selected
              for arm in ARMS for rep in range(REPS)}
    actual={(r["original_sha256"],r["arm"],r["rep"]) for r in allrows}
    check(len(allrows)==30 and actual==expected,"original SHA pairing mismatch")
    check(all(r["original_sha_verified"] and r["allocated_logical_cpus"]==1 and
              not r["independent_UNSAT_LRAT"] and r["protocol"]==PROTO
              and 0<=r["E2E_s"]<=CAP+0.1 for r in allrows),
          "metadata/CPU/cap mismatch")
    # Fully independent RUP proof replay on ORIGINAL CNF, in accepted lemma order.
    replayed=0
    replay_cache={}
    for r in allrows:
        if r["arm"] not in ("kissat_s2_all","kissat_s3_shadow","kissat_s3_gate"):continue
        s=next(c for c in selected if c["sha256"]==r["original_sha256"])
        original=pathlib.Path(a.root)/s["filename"]
        check(sha(original)==s["sha256"],"audited SHA drift")
        lemmas=[tuple(c) for c in r["prep"].get("emitted_lemmas",[])]
        check(len(lemmas)==r["prep"]["added"],"emitted lemma count drift")
        if lemmas:
            key=(s["sha256"],tuple(lemmas))
            if key not in replay_cache:
                _,cnf=core.parse(original)
                extended=[]
                for clause in lemmas:
                    check(0<len(clause)<=2 and
                          core.rup(cnf+extended,clause),
                          "independent Python RUP FAILED")
                    extended.append(clause)
                replay_cache[key]=True
            replayed+=len(lemmas)
    result=dict(protocol=PROTO,source_count=len(selected),trials=30,
                seen_not_blind=True,cap_s=CAP,reps=REPS,one_logical_cpu=True,
                new_CDCL_trials=30,original_SHA_verified=True,
                independent_UNSAT_LRAT=False,
                independent_python_RUP_lemma_replays=replayed,
                scores={})
    for arm in ARMS:
        subset=[r for r in allrows if r["arm"]==arm]
        result["scores"][arm]=dict(
          PAR2_s=round(sum(r["PAR2_s"] for r in subset),6),
          CPU_PAR2_s=round(sum(r["CPU_PAR2_s"] for r in subset),6),
          solved=sum(r["accepted"] for r in subset),
          SAT_verified=sum(r["SAT_original_witness_verified"] for r in subset),
          UNSAT_consensus_no_LRAT=sum(r["UNSAT_historical_consensus_no_LRAT"] for r in subset),
          RUP_lemmas_added=sum(r["prep"]["added"] for r in subset),
          gate_probed=sum(r["prep"].get("gate_probed",0) for r in subset),
          gate_rejected=sum(r["prep"].get("gate_rejected",0) for r in subset),
          gate_positive=sum(r["prep"].get("gate_positive",0) for r in subset),
          gate_score_sum=sum(r["prep"].get("gate_score_sum",0) for r in subset),
          prep_wall_s=round(sum(r["prep"]["prep_wall_s"] for r in subset),6),
          attempts=len(subset))
    f=pathlib.Path(a.folder)
    (f/"report.json").write_text(json.dumps(result,indent=2)+"\n")
    print("CRRS3_FINAL "+json.dumps(result,sort_keys=True),flush=True)
def selftest(a):
    with tempfile.TemporaryDirectory() as td:
        # Native smoke includes watched propagation and exact XOR/SCC extraction.
        out=subprocess.run([str(a.native),"selftest"],
                           capture_output=True,text=True,timeout=5)
        check(out.returncode==0 and "CRRS3_SELFTEST_PASS" in out.stdout,
              "C++ smoke selftest failed: "+out.stderr[-200:])
        check(not verify_model("v 1 2 3 0",[(1,),(-1,)],3),
              "partial SAT verifier unsound")
        print("CRRS3_PY_SELFTEST_PASS",flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    sp=p.add_subparsers(dest="cmd",required=True)
    s=sp.add_parser("selftest");s.add_argument("--native",required=True)
    b=sp.add_parser("bench")
    for n in ("manifest","root","kissat","cadical","native","consensus","out"):
        b.add_argument("--"+n,required=True)
    b.add_argument("--shard",type=int,choices=(0,1),required=True)
    a=sp.add_parser("audit")
    for n in ("folder","manifest","root"):a.add_argument("--"+n,required=True)
    args=p.parse_args()
    {"selftest":selftest,"bench":bench,"audit":audit}[args.cmd](args)
