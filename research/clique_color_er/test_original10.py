#!/usr/bin/env python3
"""20 strict original-source 8-second E2E proof trials (10 CNFs x 2 reps).

Does not feed GBD family, source ID, expected answer or filename to
the proof generator. The source-bytes SHA256 is verified before each trial.
Every accepted UNSAT requires separate external VeriPB 3.0.2 acceptance
within the SAME 8s wall-clock budget. UNKNOWN is a valid outcome;
invalid proof is critical and aborts report after saving its evidence.
"""
import hashlib,json,os,pathlib,resource,signal,subprocess,sys,tempfile,time
ROOT=pathlib.Path(__file__).resolve().parents[2]
INPUT=ROOT/"research/graph_unseen25/inputs"
OUT=ROOT/"results/clique_color_er_original10"
EMITTER=ROOT/"research/clique_color_er/emit_veripb.py"
CHECKER=ROOT/"veripb-tool/bin/veripb"
CAP=8.0

def sha(p):
    h=hashlib.sha256()
    with p.open("rb") as fd:
        for data in iter(lambda:fd.read(1<<20),b""):h.update(data)
    return h.hexdigest()

def execute(args,remaining):
    if remaining<=0:return {"returncode":124,"elapsed_s":0,
                             "stdout":"","stderr":"","expired":True}
    def limits():
        resource.setrlimit(resource.RLIMIT_AS,(4<<30,4<<30))
        resource.setrlimit(resource.RLIMIT_FSIZE,(256<<20,256<<20))
    env=dict(os.environ,PYTHONHASHSEED="0",OMP_NUM_THREADS="1",
             OPENBLAS_NUM_THREADS="1",MKL_NUM_THREADS="1")
    start=time.perf_counter()
    proc=subprocess.Popen(list(map(str,args)),stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,text=True,env=env,
        start_new_session=True,preexec_fn=limits)
    expired=False
    try:stdout,stderr=proc.communicate(timeout=max(0.001,remaining))
    except subprocess.TimeoutExpired:
        expired=True
        try:os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        stdout,stderr=proc.communicate()
    return {"returncode":proc.returncode,"elapsed_s":time.perf_counter()-start,
            "stdout":stdout,"stderr":stderr,"expired":expired}

def run_source(s,rep):
    started=time.perf_counter()
    cnf=ROOT/s["path"]
    assert sha(cnf)==s["sha256"],("SOURCE_SHA_CHANGED",s["id"])
    with tempfile.TemporaryDirectory(prefix="source-cliquestd-") as folder:
        dir=pathlib.Path(folder)
        proof=dir/"proof.pbp";meta=dir/"source_meta.json"
        rem=CAP-(time.perf_counter()-started)
        emit=execute([sys.executable,EMITTER,"--cnf",cnf,"--pbp",proof,
                      "--meta",meta],rem)
        status="UNKNOWN";critical=False;kind=None;reason=None
        emission=emit["elapsed_s"]
        checker_s=0;proof_sha=None;proof_size=0
        if emit["expired"]:
            status="EMITTER_TIMEOUT"
        elif emit["returncode"]==2 and not proof.exists():
            status="UNSUPPORTED_SOURCE"
        elif emit["returncode"]!=0 or not proof.is_file() or not meta.is_file():
            status="INVALID_EMITTER";critical=True
            reason=(emit["stdout"]+emit["stderr"])[-350:]
        else:
            metadata=json.loads(meta.read_text())
            if metadata["source_sha256"]!=s["sha256"]:
                status="INVALID_SOURCE_BINDING";critical=True
            else:
                rem=CAP-(time.perf_counter()-started)
                if rem<=0:
                    status="NO_VERIPB_CHECK_BUDGET"
                else:
                    chk=execute([CHECKER,"--cnf",cnf,proof],rem)
                    checker_s=chk["elapsed_s"]
                    if chk["expired"]:
                        status="VERIPB_CHECK_TIMEOUT"
                    elif chk["returncode"]==0 and (
                        "s VERIFIED UNSATISFIABLE" in chk["stdout"]+chk["stderr"]):
                        status="UNSAT_VERIPB_VERIFIED"
                        kind="VERIPB_EXTENDED_RED_RUP_CP"
                        proof_size=proof.stat().st_size
                        proof_sha=sha(proof)
                    else:
                        status="INVALID_EXTERNAL_VERIPB"
                        critical=True
                        reason=(chk["stdout"]+chk["stderr"])[-350:]
        elapsed=time.perf_counter()-started
        accepted=not critical and status=="UNSAT_VERIPB_VERIFIED" and elapsed<=CAP
        if elapsed>CAP and not critical:
            accepted=False;status="E2E_OVER_CAP"
        return {"id":s["id"],"rep":rep,"source_sha256":s["sha256"],
            "strict_accepted":accepted,"accepted":accepted,
            "status":status,"critical":critical,
            "proof_kind":kind,"proof_bytes":proof_size,
            "proof_sha256":proof_sha,"reason":reason,
            "emitter_s":round(emission,6),
            "checker_s":round(checker_s,6),
            "e2e_s":round(elapsed,6),
            "strict_PAR2_s":round(elapsed if accepted else 2*CAP,6)}

def main():
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
        assert len(os.sched_getaffinity(0))==1
    manifest=json.loads((INPUT/"manifest.json").read_text())
    assert manifest["status"]=="SOURCE_FROZEN_NO_SOLVER_TESTED"
    assert manifest["source_count"]==len(manifest["sources"])==10
    frozen_ids={s["id"] for s in manifest["sources"]}
    assert frozen_ids==set(range(10))
    OUT.mkdir(parents=True,exist_ok=True)
    rows=[]
    for source in manifest["sources"]:
        for rep in (0,1):
            record=run_source(source,rep)
            rows.append(record)
            print("CLIQUE_COLOR_ER_TRIAL "+json.dumps(record,sort_keys=True),
                  flush=True)
            (OUT/"trials.json").write_text(
                json.dumps(rows,indent=2,sort_keys=True)+"\n")
    errors=[r for r in rows if r["critical"]]
    assert len(rows)==20 and {(r["id"],r["rep"]) for r in rows}=={
        (i,rep) for i in range(10) for rep in (0,1)}
    final={"status":"PASS" if not errors else "CRITICAL",
        "originals":10,"attempts":20,
        "strict_verified":sum(r["strict_accepted"] for r in rows),
        "strict_verified_unique_sources":len({r["id"] for r in rows
                                             if r["strict_accepted"]}),
        "strict_PAR2_s":round(sum(r["strict_PAR2_s"] for r in rows),6),
        "critical_count":len(errors),"errors":errors,
        "outcomes":{str(i):[r["status"] for r in rows if r["id"]==i]
                    for i in range(10)},
        "source_manifest_sha256":sha(INPUT/"manifest.json"),
        "emitter_sha256":sha(EMITTER),
        "veripb_sha256":sha(CHECKER),
        "one_logical_cpu":True,"same_wall_cap_includes_external_proof_checker":True,
        "8s_cap":CAP,"retrospective_after_development":True,
        "not_new_blind":True,"no_main_promotion":True}
    (OUT/"final.json").write_text(json.dumps(final,indent=2,sort_keys=True)+"\n")
    print("CLIQUE_COLOR_ER_FINAL "+json.dumps(final,sort_keys=True),flush=True)
    if errors:raise SystemExit(1)
if __name__=="__main__":main()
