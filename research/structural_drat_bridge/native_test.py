#!/usr/bin/env python3
"""Paired one-CPU E2E certified DRAT on eight source-SHA-pinned synthetic CNFs.
Native route: DRNAS CNF -> structural JSON -> C++20 -> DRAT -> drat-trim.
References: pinned Kissat/CaDiCaL -> DRAT -> same drat-trim.
No unsound status accepted. 3 reps, source-paired randomized arm order, 5s
solver+proof+checker cap, PAR2=2*cap on no verified proof.
These are developmental synthetic structures, NOT fresh official blind sources.
"""
import hashlib,json,os,random,resource,statistics,subprocess,sys,time
from collections import defaultdict
from pathlib import Path
from fixtures import regenerate

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"native_bridge8_results"
BIN=ROOT/"build"
NATIVE=BIN/"drnas-structural-drat"
SOURCE=BIN/"drnas-unified-core1"
DRAT=BIN/"drat-trim"
KISSAT=BIN/"kissat"
CADICAL=BIN/"cadical"
CAP=5.0
REPS=3
ARMS=["DRNAS_NATIVE_DRAT","Kissat","CaDiCaL"]

def run_cmd(cmd,seconds):
    def limits():
        resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,)*2)
        resource.setrlimit(resource.RLIMIT_FSIZE,(512*1024**2,)*2)
    try:
        cp=subprocess.run([str(x) for x in cmd],capture_output=True,text=True,
                          timeout=max(.005,seconds),preexec_fn=limits)
        return cp.returncode,cp.stdout,cp.stderr,False
    except subprocess.TimeoutExpired:
        return -99,"","",True

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def check(path,proof,remaining):
    if remaining<=0:return False,"CHECK_TIMEOUT"
    rc,stdout,stderr,expired=run_cmd((DRAT,path,proof),remaining)
    return rc==0 and "s VERIFIED" in stdout,("s VERIFIED" if rc==0 and "s VERIFIED" in stdout else
                                           "CHECK_TIMEOUT" if expired else "CHECK_FAILED")

def trial(name,cnf,source_sha,arm,rep):
    directory=OUT/"proofs"/name/f"rep_{rep}"/arm
    directory.mkdir(parents=True,exist_ok=True)
    cert=directory/"structural.json"
    proof=directory/"result.drat"
    assert sha(cnf)==source_sha
    start=time.perf_counter()
    accepted=False;status="UNKNOWN";method="";proof_sha=None
    if arm=="DRNAS_NATIVE_DRAT":
        rc,stdout,stderr,expired=run_cmd((SOURCE,cnf,"--time",str(CAP),"--certificate",cert),CAP)
        if rc==20 and "s UNSATISFIABLE" in stdout and cert.is_file():
            if json.loads(cert.read_text()).get("source_sha256")!=source_sha:
                raise AssertionError("candidate certificate SHA drift")
            left=CAP-(time.perf_counter()-start)
            if left>0:
                brc,bout,berr,expired=run_cmd(
                    (NATIVE,cnf,cert,proof,"--checker",DRAT,f"{left:.5f}"),left)
                accepted=(brc==0 and "NATIVE_BRIDGE_VERIFIED" in bout and
                          proof.is_file() and "s VERIFIED" in (proof.with_suffix(".drat.checker.log")).read_text()
                          if brc==0 and proof.is_file() and proof.with_suffix(".drat.checker.log").is_file()
                          else False)
                if accepted:
                    method=json.loads(bout.split("NATIVE_BRIDGE_VERIFIED ",1)[1].splitlines()[0])["method"]
                    status="UNSAT_VERIFIED"
                else:status="NATIVE_BRIDGE_TIMEOUT" if expired else "NATIVE_BRIDGE_REJECTED"
            else:status="CANDIDATE_TIME_LIMIT"
        else:status="CANDIDATE_TIMEOUT" if expired else "CANDIDATE_UNKNOWN"
    else:
        cmd=((KISSAT,cnf,proof) if arm=="Kissat" else
             (CADICAL,"-q","--no-binary",cnf,proof))
        rc,stdout,stderr,expired=run_cmd(cmd,CAP)
        if rc==20 and proof.is_file():
            ok,reason=check(cnf,proof,CAP-(time.perf_counter()-start))
            accepted=ok
            status="UNSAT_VERIFIED" if ok else reason
        else:status="TIMEOUT" if expired else ("UNKNOWN" if rc in (0,10) else "ERROR")
    elapsed=time.perf_counter()-start
    # The attempt is not accepted if the proof checker overran E2E cap.
    if elapsed>CAP:accepted=False;status="E2E_TIMEOUT"
    if accepted:proof_sha=sha(proof)
    return dict(name=name,source_sha256=source_sha,arm=arm,rep=rep,
                status=status,accepted=accepted,method=method,
                e2e_s=round(elapsed,6),PAR2_s=round(elapsed if accepted else 2*CAP,6),
                proof_sha256=proof_sha)

def negatives(cases):
    name,cnf,expected=cases[0]
    dest=OUT/"negative_controls"
    dest.mkdir(exist_ok=True)
    cert=OUT/"proofs"/name/"rep_0"/"DRNAS_NATIVE_DRAT"/"structural.json"
    c=json.loads(cert.read_text())
    variants={
      "bad_sha":dict(c,source_sha256="0"*64),
      "non_source_alo":dict(c,alo_groups=[[999999]]+c["alo_groups"][1:]),
    }
    for label,bad in variants.items():
        cj=dest/(label+".json");pd=dest/(label+".drat")
        cj.write_text(json.dumps(bad))
        rc,stdout,stderr,expired=run_cmd((NATIVE,cnf,cj,pd,"--checker",DRAT,"2"),2.5)
        assert rc!=0 and "NATIVE_BRIDGE_VERIFIED" not in stdout and not pd.exists(),label
        print("NATIVE_NEGATIVE_OK",label,flush=True)
    pd=dest/"checker_false.drat"
    rc,stdout,stderr,expired=run_cmd((NATIVE,cnf,cert,pd,"--checker","/bin/false","2"),2.5)
    assert rc!=0 and "NATIVE_BRIDGE_VERIFIED" not in stdout and not pd.exists(),"checker-failure"
    print("NATIVE_NEGATIVE_OK checker_false",flush=True)
    original=OUT/"proofs"/name/"rep_0"/"DRNAS_NATIVE_DRAT"/"result.drat"
    truncated=dest/"truncated.drat"
    truncated.write_text("\n".join(original.read_text().splitlines()[:4])+"\n")
    ok,_=check(cnf,truncated,2)
    assert not ok,"independent checker accepted non-proof"
    print("NATIVE_NEGATIVE_OK incomplete_proof",flush=True)
    # Mutation of an original source must invalidate the structural SHA.
    edited=dest/"tampered.cnf"
    edited.write_bytes(cnf.read_bytes()+b"c deliberate source mutation\n")
    pd=dest/"mutated_source.drat"
    rc,stdout,stderr,expired=run_cmd((NATIVE,edited,cert,pd,"--checker",DRAT,"2"),2.5)
    assert rc!=0 and not pd.exists() and "NATIVE_BRIDGE_VERIFIED" not in stdout
    print("NATIVE_NEGATIVE_OK modified_original",flush=True)

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    assert len(os.sched_getaffinity(0))==1
    OUT.mkdir(exist_ok=True)
    cases=regenerate(OUT/"cnf")
    assert len(cases)==8
    for path in (NATIVE,SOURCE,DRAT,KISSAT,CADICAL):
        assert path.is_file(),path
    print("NATIVE_READY",json.dumps(dict(cases=len(cases),reps=REPS,arms=ARMS,
                                          cap_s=CAP,one_logical_core=True,
                                          source_sha256=[s for _,_,s in cases])),flush=True)
    rng=random.Random(20261115);trials=[]
    for name,cnf,source_sha in cases:
        for rep in range(REPS):
            order=list(ARMS);rng.shuffle(order)
            for arm in order:
                result=trial(name,cnf,source_sha,arm,rep)
                trials.append(result)
                with (OUT/"trials.jsonl").open("a") as f:
                    f.write(json.dumps(result,sort_keys=True)+"\n")
                print("NATIVE_TRIAL",json.dumps(result,sort_keys=True),flush=True)
    negatives(cases)
    byarm=defaultdict(list)
    for r in trials:byarm[r["arm"]].append(r)
    totals={arm:dict(attempts=len(rows),verified=sum(x["accepted"] for x in rows),
                     PAR2_s=round(sum(x["PAR2_s"] for x in rows),6),
                     median_verified_e2e_s=round(statistics.median(x["e2e_s"] for x in rows if x["accepted"]),6)
                     if any(x["accepted"] for x in rows) else None)
            for arm,rows in byarm.items()}
    assert len(trials)==8*REPS*len(ARMS)==72
    assert totals["DRNAS_NATIVE_DRAT"]["verified"]==8*REPS
    final=dict(status="COMPLETE",cases=8,reps=REPS,trials=len(trials),cap_s=CAP,
               sources_frozen_sha=True,dataset="retrospective synthetic development",
               one_logical_cpu=True,strict_requires_standard_drat=True,
               extra_negative_controls=5,totals=totals)
    (OUT/"final.json").write_text(json.dumps(final,indent=2,sort_keys=True)+"\n")
    print("NATIVE_FINAL",json.dumps(final,sort_keys=True),flush=True)

if __name__=="__main__":main()
