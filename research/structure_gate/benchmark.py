#!/usr/bin/env python3
"""STRUCTURE-GATE1 retrospective strict E2E paired comparison on frozen SAT25/26.
One logical CPU per solver, SHA-pinned original sources and reference binaries.
Gate hints NEVER count as proof; independent SAT models / DRAT / FRAT / VeriPB only.
No source selection from results; not a prospective blind holdout or main promotion.
"""
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import random
import resource
import signal
import statistics
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"results/structure_gate1"
YEAR25=ROOT/"sat_real2025_inputs/manifest.json"
YEAR26=ROOT/"unified_realblind100_inputs/manifest.json"
FREEZE_SHA25="47cc882a3893b2ecaf543341040d41c417eb13d8eb940198d37143715f65db4e"
CAP=12.0
REPS=2
SHARDS=10
ARMS=("SG_ON","SG_OFF","X59_OFF","Kissat","CaDiCaL","CryptoMiniSat")
REFERENCES=("Kissat","CaDiCaL","CryptoMiniSat")
CANDIDATE=ROOT/"build/drnas-x59-structure-gate1"
MATH_SOURCE_CHECKER=ROOT/"research/math5/check_math5.py"
EMITTER=ROOT/"research/math5/emit_veripb_eo_multiplicity.py"
VERIPB=ROOT/"veripb-tool/bin/veripb"
BIN={
 "SG_ON":CANDIDATE,"SG_OFF":CANDIDATE,
 "X59_OFF":ROOT/"build/drnas-sat-native-x59",
 "Kissat":ROOT/"build/kissat","CaDiCaL":ROOT/"build/cadical",
 "CryptoMiniSat":ROOT/"build/cms",
}
REQUIRED=tuple(sorted(set(str(x.relative_to(ROOT)) for x in BIN.values()) | {
 "build/drat-trim","build/frat-rs",
 "build/cms-libs/usr/lib/x86_64-linux-gnu/libcryptominisat5.so.5.11",
 "veripb-tool/bin/veripb"}))

def sha(p):
    hasher=hashlib.sha256()
    with Path(p).open("rb") as fd:
        for part in iter(lambda:fd.read(1<<20),b""):
            hasher.update(part)
    return hasher.hexdigest()

def put(path, data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")

def affinity():
    mask=os.sched_getaffinity(0)
    os.sched_setaffinity(0,{min(mask)})
    assert len(os.sched_getaffinity(0))==1

def sources():
    assert sha(YEAR25)==FREEZE_SHA25,"SAT2025 manifest has drifted"
    manifest25=json.loads(YEAR25.read_text())
    manifest26=json.loads(YEAR26.read_text())
    assert manifest25["ready_count"]==19
    assert manifest26["selected"]==67
    seq=[]
    for i,s in enumerate(manifest25["ready_sources"]):
        assert s["status"]=="READY" and sha(ROOT/s["path"])==s["sha256"]
        seq.append(dict(era="SAT2025",id=i,path=s["path"],sha256=s["sha256"],
                        family="SAT2025_ORIGINALS",label=s["gbd"]))
    for s in manifest26["sources"]:
        assert sha(ROOT/s["path"])==s["sha256"]
        seq.append(dict(era="SAT2026",id=s["id"],path=s["path"],
                        sha256=s["sha256"],family=s["family"],label=s["file_id"]))
    assert len(seq)==86
    assert len({s["sha256"] for s in seq})==86
    return seq

def pinned():
    return {p:sha(ROOT/p) for p in REQUIRED}

def preflight():
    affinity()
    manifest=sources()
    binary_shas=pinned()
    doc=dict(protocol="DRNAS-STRUCTURE-GATE1-RETROSPECTIVE-STRICT-V1",
        git_sha=os.environ.get("GITHUB_SHA"),
        source_manifest_sha2025=sha(YEAR25),
        source_manifest_sha2026=sha(YEAR26),
        code_sha=sha(Path(__file__)),
        gate_header_sha=sha(ROOT/"src/drnas_structure_gate.hpp"),
        binary_sha256=binary_shas,
        sources=len(manifest),trials=len(manifest)*REPS*len(ARMS),
        arms=ARMS,cap_s=CAP,shards=SHARDS,repetitions=REPS,
        one_logical_cpu=True,same_process_no_portfolio=True,
        fixed_math5_budget_ms=100,fixed_sat_constructor_budget_ms=25,
        gate_budget_ms={"SG_ON":12,"SG_OFF":0},
        independent_standard_proof_only=True,
        source_disjoint_prospective=False,
        source_family_disjoint_holdout=False,
        no_main_promotion=True,strict_e2e_includes_proof_check=True)
    put(OUT/"protocol.json",doc)
    print("SGATE_READY "+json.dumps(dict(
        sources=86,trials=doc["trials"],sha25=doc["source_manifest_sha2025"],
        sha26=doc["source_manifest_sha2026"],candidate_sha=binary_shas[
            "build/drnas-x59-structure-gate1"]),sort_keys=True),flush=True)

def restore():
    affinity()
    data=sources()
    p=json.loads((OUT/"protocol.json").read_text())
    assert p["git_sha"]==os.environ.get("GITHUB_SHA")
    assert p["code_sha"]==sha(Path(__file__))
    assert p["gate_header_sha"]==sha(ROOT/"src/drnas_structure_gate.hpp")
    assert p["source_manifest_sha2025"]==sha(YEAR25)
    assert p["source_manifest_sha2026"]==sha(YEAR26)
    assert p["binary_sha256"]==pinned()
    assert p["arms"]==list(ARMS) and p["trials"]==len(data)*REPS*len(ARMS)
    return data,p

def run(args,timeout):
    def limit():
        resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,)*2)
        resource.setrlimit(resource.RLIMIT_FSIZE,(256*1024**2,)*2)
    env=dict(os.environ,OMP_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1",MKL_NUM_THREADS="1",
             LD_LIBRARY_PATH=str(ROOT/"build/cms-libs/usr/lib/x86_64-linux-gnu"))
    t=time.perf_counter()
    proc=subprocess.Popen([str(x) for x in args],text=True,stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE,env=env,preexec_fn=limit,
                          start_new_session=True)
    timed_out=False
    try:
        stdout,stderr=proc.communicate(timeout=max(0.001,timeout))
    except subprocess.TimeoutExpired:
        timed_out=True
        try:os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        stdout,stderr=proc.communicate()
    return dict(rc=proc.returncode,stdout=stdout,stderr=stderr,
                timed_out=timed_out,elapsed=time.perf_counter()-t)

def model_ok(path,output):
    assigned={}
    for line in output.splitlines():
        if not line.startswith("v "):continue
        for value in line[2:].split():
            try:literal=int(value)
            except ValueError:return False
            if not literal:continue
            if abs(literal) in assigned and assigned[abs(literal)]!=(literal>0):return False
            assigned[abs(literal)]=literal>0
    if not assigned:return False
    num=None
    expected=None
    counted=0
    clause=[]
    with Path(path).open(errors="strict") as inp:
        for line in inp:
            tokens=line.split()
            if not tokens or tokens[0] in ("c","%"):continue
            if tokens[0]=="p":
                if num is not None or len(tokens)!=4 or tokens[1]!="cnf":return False
                num,expected=map(int,tokens[2:])
                if any(v>num for v in assigned):return False
                continue
            if num is None:return False
            for token in tokens:
                lit=int(token)
                if abs(lit)>num:return False
                if lit:clause.append(lit)
                else:
                    counted+=1
                    if not any(assigned.get(abs(l))==(l>0) for l in clause):
                        return False
                    clause=[]
    return num is not None and not clause and counted==expected

def cmd(arm,src,proof,certificate):
    c=ROOT/src["path"]
    if arm in ("SG_ON","SG_OFF"):
        return [BIN[arm],c,"--mode","core","--time",str(CAP),
                "--sat-construct-ms","25","--math5-ms","100",
                "--structure-gate-ms","12" if arm=="SG_ON" else "0",
                "--math5-certificate",certificate,"--proof",proof,"--stats"]
    if arm=="X59_OFF":
        return [BIN[arm],c,"--mode","core","--time",str(CAP),"--proof",proof,"--stats"]
    if arm=="Kissat":return [BIN[arm],c,proof]
    if arm=="CaDiCaL":return [BIN[arm],"-q","--no-binary",c,proof]
    if arm=="CryptoMiniSat":
        return [BIN[arm],"--threads=1","--verb=0","--frat="+str(proof),c]
    raise ValueError(arm)

def telemetry(stderr):
    for line in stderr.splitlines():
        if line.startswith("STRUCTURE_GATE_STATS "):
            try:return json.loads(line.partition(" ")[2])
            except json.JSONDecodeError:return {"bad_json":True}
    return {}

def attempt(src,arm,rep):
    start=time.perf_counter()
    cnf=ROOT/src["path"]
    assert sha(cnf)==src["sha256"],("SOURCE_CHANGED",src)
    with tempfile.TemporaryDirectory(prefix="sgate-e2e-") as td:
        work=Path(td)
        proof=work/("proof.frat" if arm=="CryptoMiniSat" else "proof.drat")
        cert=work/"math5.json"
        pb=work/"math5.pbp"
        proof_size=0
        certificate_kind=None
        status="UNKNOWN"
        strict=False
        critical=False
        reason=None
        check_s=0
        checker_details={}
        solver=run(cmd(arm,src,proof,cert),CAP)
        status="TIMEOUT" if solver["timed_out"] else "UNKNOWN"
        observed_rc=solver["rc"]
        gate=telemetry(solver["stderr"])
        if not solver["timed_out"]:
            if observed_rc in (10,20):
                expected="s SATISFIABLE" if observed_rc==10 else "s UNSATISFIABLE"
                if expected not in solver["stdout"].splitlines():
                    status="INVALID_STATUS";critical=True
                elif observed_rc==10:
                    certificate_kind="MODEL"
                    if cert.exists() or not model_ok(cnf,solver["stdout"]):
                        status="INVALID_SAT_MODEL_OR_STRAY_CERT";critical=True
                    else:
                        strict=True;status="SAT_VERIFIED"
                else:
                    if cert.exists():
                        certificate_kind="VERIPB_MATH5"
                        if proof.exists() and proof.stat().st_size:
                            critical=True;status="INVALID_MIXED_MATH5_AND_DRAT"
                        else:
                            remaining=CAP-(time.perf_counter()-start)
                            if remaining>0:
                                chk=run([sys.executable,MATH_SOURCE_CHECKER,cnf,cert],remaining)
                                check_s+=chk["elapsed"]
                                checker_details["source"]=chk["rc"]
                                if chk["timed_out"]:status="MATH_SOURCE_CHECK_TIMEOUT"
                                elif chk["rc"]!=0 or "UNSAT_MATH5_CERTIFICATE_VERIFIED" not in chk["stdout"]:
                                    critical=True;status="INVALID_MATH5_SOURCE_PROOF"
                                else:
                                    remaining=CAP-(time.perf_counter()-start)
                                    if remaining>0:
                                        emitted=run([sys.executable,EMITTER,"--cnf",cnf,
                                            "--certificate",cert,"--output",pb],remaining)
                                        check_s+=emitted["elapsed"]
                                        checker_details["emitter"]=emitted["rc"]
                                        if emitted["timed_out"]:status="MATH_EMIT_TIMEOUT"
                                        elif emitted["rc"]==2:
                                            status="MATH5_NO_STANDARD_PROOF"
                                        elif emitted["rc"]!=0 or not pb.is_file():
                                            status="INVALID_MATH_EMITTER";critical=True
                                        else:
                                            remaining=CAP-(time.perf_counter()-start)
                                            if remaining>0:
                                                proof_check=run([VERIPB,"--cnf",cnf,pb],remaining)
                                                check_s+=proof_check["elapsed"]
                                                checker_details["veripb"]=proof_check["rc"]
                                                if proof_check["timed_out"]:
                                                    status="VERIPB_CHECK_TIMEOUT"
                                                elif proof_check["rc"]==0 and (
                                                     "s VERIFIED UNSATISFIABLE" in proof_check["stdout"]+
                                                     proof_check["stderr"]):
                                                    strict=True;status="UNSAT_VERIFIED"
                                                    proof_size=pb.stat().st_size
                                                else:
                                                    status="INVALID_EXTERNAL_VERIPB";critical=True
                                            else:status="NO_VERIPB_BUDGET"
                                    else:status="NO_EMIT_BUDGET"
                            else:status="NO_SOURCE_CHECK_BUDGET"
                    elif proof.is_file() and proof.stat().st_size:
                        certificate_kind="FRAT" if arm=="CryptoMiniSat" else "DRAT"
                        remaining=CAP-(time.perf_counter()-start)
                        if remaining>0:
                            check=([ROOT/"build/frat-rs","elab",proof,cnf,"-v"] if
                                   arm=="CryptoMiniSat" else
                                   [ROOT/"build/drat-trim",cnf,proof])
                            verified=run(check,remaining)
                            check_s+=verified["elapsed"]
                            checker_details["ref"]=verified["rc"]
                            if verified["timed_out"]:status="REFERENCE_PROOF_TIMEOUT"
                            elif verified["rc"]==0 and "VERIFIED" in (
                                    verified["stdout"]+verified["stderr"]):
                                strict=True;status="UNSAT_VERIFIED"
                                proof_size=proof.stat().st_size
                            else:status="INVALID_DRAT_OR_FRAT";critical=True
                        else:status="NO_PROOF_CHECK_BUDGET"
                    else:status="UNSAT_UNVERIFIED"
            elif observed_rc in (137,-9,-25,-11):status="RESOURCE_LIMIT"
            elif observed_rc in (0,153,None):status="UNKNOWN"
            else:
                status="SOLVER_ERROR";critical=True
                reason=solver["stderr"][-400:]
        elapsed=time.perf_counter()-start
        if elapsed>CAP:
            strict=False
            if not critical:status="E2E_OVER_CAP"
        return dict(era=src["era"],id=src["id"],family=src["family"],
            source_sha256=src["sha256"],arm=arm,rep=rep,status=status,
            strict_accepted=bool(strict and not critical and elapsed<=CAP),
            critical=critical,reason=reason,
            certificate_kind=certificate_kind,proof_bytes=proof_size,
            rc=observed_rc,solver_s=round(solver["elapsed"],6),
            checker_s=round(check_s,6),e2e_s=round(elapsed,6),
            PAR2_strict_s=round(elapsed if strict and not critical and elapsed<=CAP else 2*CAP,6),
            gate=gate,checker=checker_details)

def shard(index):
    assert 0<=index<SHARDS
    data,_=restore()
    sub=[s for s in data if s["id"]%SHARDS==index]
    out=OUT/f"shard-{index}"
    out.mkdir(parents=True,exist_ok=False)
    count=0
    with (out/"trials.jsonl").open("w") as log:
        for src in sub:
            for rep in range(REPS):
                order=list(ARMS)
                random.Random(f"{src['sha256']}:{rep}:sgate1").shuffle(order)
                state={}
                for arm in order:
                    result=attempt(src,arm,rep)
                    log.write(json.dumps(result,sort_keys=True)+"\n")
                    log.flush()
                    count+=1
                    state[arm]=[result["status"],round(result["PAR2_strict_s"],3),
                                result["gate"].get("reason","")]
                print("SGATE_SOURCE "+json.dumps(dict(era=src["era"],id=src["id"],
                    rep=rep,results=state),sort_keys=True),flush=True)
    assert count==len(sub)*REPS*len(ARMS)
    print("SGATE_SHARD "+json.dumps(dict(index=index,sources=len(sub),
        trials=count),sort_keys=True),flush=True)

def aggregate():
    data,p=restore()
    rows=[]
    for i in range(SHARDS):
        path=OUT/f"shard-{i}"/"trials.jsonl"
        if not path.exists():raise RuntimeError("MISSING_SHARD "+str(i))
        rows.extend(json.loads(x) for x in path.read_text().splitlines())
    expected={(s["era"],s["id"],rep,arm) for s in data
              for rep in range(REPS) for arm in ARMS}
    observed={(r["era"],r["id"],r["rep"],r["arm"]) for r in rows}
    assert len(rows)==len(expected)==p["trials"] and observed==expected,"INCOMPLETE_TRIALS"
    identity={(s["era"],s["id"]):s for s in data}
    failures=[]
    for r in rows:
        if r["critical"]:failures.append({k:r[k] for k in ("era","id","arm","status","reason")})
        if r["source_sha256"]!=identity[r["era"],r["id"]]["sha256"]:
            failures.append(("SOURCE_HASH_MISMATCH",r["era"],r["id"]))
        if r["strict_accepted"] and r["certificate_kind"] not in (
                "MODEL","DRAT","FRAT","VERIPB_MATH5"):
            failures.append(("INVALID_STRICT_CREDIT",r["era"],r["id"],r["arm"]))
    for s in data:
        verdicts={r["status"].split("_")[0] for r in rows if
           r["era"]==s["era"] and r["id"]==s["id"] and r["strict_accepted"]}
        if len(verdicts)>1:failures.append(("CONTRADICTORY_VERIFIED",s["era"],s["id"]))
    totals={}
    def summed(rr):
        return {arm:dict(
            trials=len([r for r in rr if r["arm"]==arm]),
            strict_verified=sum(r["strict_accepted"] for r in rr if r["arm"]==arm),
            strict_PAR2_s=round(sum(r["PAR2_strict_s"] for r in rr if r["arm"]==arm),6),
            sat=sum(r["status"]=="SAT_VERIFIED" and r["strict_accepted"]
                    for r in rr if r["arm"]==arm),
            unsat=sum(r["status"]=="UNSAT_VERIFIED" and r["strict_accepted"]
                    for r in rr if r["arm"]==arm),
            gate_selected=sum(bool(r["gate"].get("selected_math5"))
                              for r in rr if r["arm"]==arm),
            gate_reasons=dict(collections.Counter(
                r["gate"].get("reason","NOT_REPORTED") for r in rr if r["arm"]==arm)),
            statuses=dict(collections.Counter(
                r["status"] for r in rr if r["arm"]==arm)))
            for arm in ARMS}
    for era in ("SAT2025","SAT2026","COMBINED"):
        rr=rows if era=="COMBINED" else [r for r in rows if r["era"]==era]
        summary=summed(rr)
        best=min(REFERENCES,key=lambda a:summary[a]["strict_PAR2_s"])
        baseline=summary["SG_OFF"]["strict_PAR2_s"]
        chosen=summary["SG_ON"]["strict_PAR2_s"]
        totals[era]=dict(sources=len(rr)//(len(ARMS)*REPS),
            arms=summary,best_reference=best,
            gate_vs_off_percent=round(100*(1-chosen/baseline),6),
            gate_vs_best_ref_percent=round(100*(
                1-chosen/summary[best]["strict_PAR2_s"]),6))
    output=dict(status="FAIL" if failures else "COMPLETE",
        results=totals,critical=failures,trials=len(rows),protocol=p,
        retrospective_not_blind=True,no_main_promotion=True,
        note="Gate never proves UNSAT; original-source external VeriPB/DRAT/FRAT only.")
    put(OUT/"final.json",output)
    compact={e:dict(
        best_reference=v["best_reference"],
        gain_vs_off_percent=v["gate_vs_off_percent"],
        gain_vs_ref_percent=v["gate_vs_best_ref_percent"],
        arms={a:dict(strict_PAR2_s=z["strict_PAR2_s"],
                      strict_verified=z["strict_verified"],
                      gate_selected=z["gate_selected"])
             for a,z in v["arms"].items()})
             for e,v in totals.items()}
    print("SGATE_FINAL "+json.dumps(dict(status=output["status"],
        sources=86,trials=len(rows),critical_count=len(failures),
        eras=compact),sort_keys=True),flush=True)
    if failures:raise SystemExit(1)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("action",choices=["prepare","shard","report"])
    ap.add_argument("--index",type=int)
    args=ap.parse_args()
    if args.action=="prepare":preflight()
    elif args.action=="shard":shard(args.index)
    else:aggregate()
