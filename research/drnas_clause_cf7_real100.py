#!/usr/bin/env python3
"""CF7: source-paired original SAT2024 100-case five-arm experiment.
No training, no claim of a novel blind holdout, no promotion.
Each subprocess pinned to the caller's one logical CPU; no concurrent arms.
Verified SAT models and independently DRAT-certified UNSAT only score.
"""
import argparse, collections, hashlib, json, os, pathlib, random, resource, signal, subprocess, sys, tarfile, tempfile, time
ROOT=pathlib.Path("cf7")
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import drnas_ltm10_real1 as DATA
import drnas_x55_cpu_real36 as REAL
ARMS=("CF7_B2L_32","CF6_BASE","CF5_BASE","CaDiCaL","Kissat")
CAP=8.0
SHARDS=10
BINS={"CF7_B2L_32":"build/drnas-clause-cf6",
      "CF6_BASE":"build/drnas-clause-cf6",
      "CF5_BASE":"build/drnas-clause-cf5",
      "CaDiCaL":"build/cadical","Kissat":"build/kissat"}
CHECKER="build/drat-trim"
def sha(b):return hashlib.sha256(b).hexdigest()
def emit(tag,obj):print(tag+" "+json.dumps(obj,sort_keys=True),flush=True)
def write(path,obj):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def cpu_pin():
    allowed=os.sched_getaffinity(0);os.sched_setaffinity(0,{min(allowed)})
    assert len(os.sched_getaffinity(0))==1
def collect():
    cpu_pin()
    assert all(pathlib.Path(p).is_file() for p in list(BINS.values())+[CHECKER])
    # Reuse previously declared LTM10 name-family/size-only frozen selection,
    # not timing- or answer-driven instance selection.
    DATA.ROOT=ROOT/"selection"
    src=DATA.collect()
    assert len(src)==100 and len({r["sha256"] for r in src})==100
    assert len({r["normalized_name_family"] for r in src})==100
    bins={arm:sha(pathlib.Path(p).read_bytes()) for arm,p in BINS.items()}
    manifest={"protocol":"CF7-FIVE-ARM-REAL100-V1",
       "archive":DATA.ARCHIVE,"sources":src,"count":100,
       "source_selection":"LTM10 fixed size/name-only 100 family heuristic",
       "arms":ARMS,"cap_s":CAP,"shards":SHARDS,
       "solver_sha256":bins,"checker_sha256":sha(pathlib.Path(CHECKER).read_bytes()),
       "one_logical_cpu_per_trial":True,"original_cnfs_unchanged":True,
       "blind_holdout":False,"prior_source_exposure_possible":True,
       "no_training_or_promotion":True,
       "unsat_requires_independent_drat_trim":True}
    write(ROOT/"manifest.json",manifest)
    with tarfile.open("cf7_inputs.tgz","w:gz") as t:
        t.add(ROOT/"selection",arcname="cf7/selection")
        t.add(ROOT/"manifest.json",arcname="cf7/manifest.json")
    emit("CF7_FROZEN",{"count":100,"families":100,"arms":list(ARMS),"cap_s":CAP})
def checked_manifest():
    obj=json.loads((ROOT/"manifest.json").read_text())
    assert obj["count"]==100 and obj["cap_s"]==CAP and tuple(obj["arms"])==ARMS
    assert obj["checker_sha256"]==sha(pathlib.Path(CHECKER).read_bytes())
    for arm,p in BINS.items():assert obj["solver_sha256"][arm]==sha(pathlib.Path(p).read_bytes())
    return obj
def command(arm,cnf,proof):
    if arm.startswith("CF"):
        mode="B2L_32" if arm=="CF7_B2L_32" else "BASE"
        return [BINS[arm],str(cnf),"--mode","core","--time",str(CAP),
                "--x5-no-minimize","--x5-no-retain","--proof",str(proof),
                "--cf5-policy",mode]
    if arm=="Kissat":return [BINS[arm],str(cnf),str(proof)]
    if arm=="CaDiCaL":return [BINS[arm],"-q","--no-binary",str(cnf),str(proof)]
    raise ValueError(arm)
def trial(source,arm):
    cnf=pathlib.Path(source["path"])
    assert cnf.is_file() and sha(cnf.read_bytes())==source["sha256"],("SOURCE_DRIFT",source["id"])
    with tempfile.TemporaryDirectory() as tmp:
        proof=pathlib.Path(tmp)/"p.drat"
        cmd=command(arm,cnf,proof)
        start=time.perf_counter()
        p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           text=True,start_new_session=True,
                           preexec_fn=lambda:resource.setrlimit(resource.RLIMIT_FSIZE,(512*1024*1024,512*1024*1024)))
        killed=False
        try:out,err=p.communicate(timeout=CAP+0.25)
        except subprocess.TimeoutExpired:
            killed=True
            os.killpg(p.pid,signal.SIGKILL);out,err=p.communicate()
        elapsed=time.perf_counter()-start
        code=p.returncode
        if not killed and code not in (0,10,20,153):
            raise RuntimeError(("SOLVER_EXIT",source["id"],arm,code,err[-400:]))
        status="UNKNOWN";verified=False
        if not killed and code==10:
            verified=DATA.sat_witness_valid(cnf,DATA.nvars(cnf),out)
            if not verified:raise RuntimeError(("INVALID_SAT",source["id"],arm))
            status="SAT_VERIFIED"
        elif not killed and code==20:
            if proof.is_file() and proof.stat().st_size:
                try:
                    ck=subprocess.run([CHECKER,str(cnf),str(proof)],
                         capture_output=True,text=True,timeout=90)
                    verified=ck.returncode==0 and "s VERIFIED" in ck.stdout
                except subprocess.TimeoutExpired:pass
            status="UNSAT_CERTIFIED" if verified else "UNSAT_UNVERIFIED"
        elif code==153: status="PROOF_LIMIT"
        accepted=verified and elapsed<=CAP
        row={"id":source["id"],"family":source["normalized_name_family"],
             "sha256":source["sha256"],"arm":arm,
             "status":status,"verified":verified,"accepted":accepted,
             "elapsed_e2e_s":round(elapsed,6),
             "PAR2_verified_s":round(elapsed if accepted else 2*CAP,6),
             "proof_size":proof.stat().st_size if proof.is_file() else 0}
        emit("CF7_TRIAL",row)
        return row
def shard(index):
    cpu_pin()
    manifest=checked_manifest()
    assert 0<=index<SHARDS
    sources=[s for s in manifest["sources"] if s["id"]%SHARDS==index]
    assert len(sources)==10
    results=[]
    for src in sources:
        shuffled=list(ARMS)
        random.Random(7700+src["id"]).shuffle(shuffled)
        for arm in shuffled:results.append(trial(src,arm))
        confirmed={r["status"] for r in results[-len(ARMS):] if r["verified"]}
        assert len(confirmed)<=1,("CONTRADICTORY_CERTIFIED_RESULT",src["id"])
    dest=ROOT/"shards"/str(index)
    dest.mkdir(parents=True,exist_ok=True)
    with (dest/"trials.jsonl").open("w") as f:
        for r in results:f.write(json.dumps(r,sort_keys=True)+"\n")
    write(dest/"meta.json",{"index":index,"source_ids":[s["id"] for s in sources],
                             "trials":len(results),"cap_s":CAP})
    emit("CF7_SHARD_PASS",{"index":index,"sources":len(sources),"trials":len(results)})
def final():
    obj=json.loads((ROOT/"manifest.json").read_text())
    rows=[]
    for i in range(SHARDS):
        folder=ROOT/"downloads"/("cf7-shard-"+str(i))
        meta=json.loads((folder/"meta.json").read_text())
        assert meta["index"]==i and meta["trials"]==50
        rows.extend(json.loads(x) for x in (folder/"trials.jsonl").read_text().splitlines())
    assert len(rows)==500
    by=collections.defaultdict(dict)
    for r in rows:
        assert r["arm"] not in by[r["id"]]
        by[r["id"]][r["arm"]]=r
    assert len(by)==100 and all(set(v)==set(ARMS) for v in by.values())
    assert all(len({r["sha256"] for r in v.values()})==1 for v in by.values())
    summary={}
    for arm in ARMS:
        chosen=[v[arm] for v in by.values()]
        summary[arm]={"verified":sum(x["accepted"] for x in chosen),
           "SAT_verified":sum(x["accepted"] and x["status"]=="SAT_VERIFIED" for x in chosen),
           "UNSAT_certified":sum(x["accepted"] and x["status"]=="UNSAT_CERTIFIED" for x in chosen),
           "PAR2_verified_s":round(sum(x["PAR2_verified_s"] for x in chosen),5),
           "unverified_unsat":sum(x["status"]=="UNSAT_UNVERIFIED" for x in chosen),
           "proof_limited":sum(x["status"]=="PROOF_LIMIT" for x in chosen)}
    assert all(len({v["status"] for v in trials.values() if v["verified"]})<=1 for trials in by.values())
    result={"status":"COMPLETE","samples":100,"attempts":500,"cap_s":CAP,
            "blind_holdout":False,"no_promotion":True,"arms":summary}
    write(ROOT/"final/report.json",result)
    emit("CF7_FINAL",result)
def main():
    p=argparse.ArgumentParser();p.add_argument("action",choices=("collect","shard","final"))
    p.add_argument("--shard",type=int,default=0);a=p.parse_args()
    if a.action=="collect":collect()
    elif a.action=="shard":shard(a.shard)
    else:final()
if __name__=="__main__":main()
