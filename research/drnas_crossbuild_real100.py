#!/usr/bin/env python3
"""Cross-build REAL100: source-paired original SAT2024, no promotion.
Every trial is serialized on one logical CPU; only independently certified
UNSAT or model-checked SAT counts. Prior CF7 data is not used as timings.
"""
import argparse,collections,hashlib,json,os,pathlib,random,resource,signal,subprocess,sys,tempfile,time
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"research"))
import drnas_clause_cf7_real100 as CF
ARMS=("LTM8_FAST","LTM9_FAST","X5_NO_MIN","R153_NATIVE_DIRECT","R153_CONTEXT_MEMORY","CF7_B2L_32","Kissat")
CAP=8.0
def digest(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def emit(k,v):print(k+" "+json.dumps(v,sort_keys=True),flush=True)
def run_one(arm,source,shard):
    cnf=(ROOT/source["path"]).resolve()
    assert cnf.is_file() and digest(cnf)==source["sha256"],("SOURCE_DRIFT",source["id"])
    start=time.perf_counter();status="UNKNOWN";verified=False;extra={}
    if arm in ("LTM8_FAST","LTM9_FAST"):
        ltm=ROOT/"cross_aux/ltm"
        sys.path.insert(0,str(ltm/"research"))
        import drnas_ltm11_real2 as B
        previous=os.getcwd()
        try:
            os.chdir(ltm)
            row=B.run_solver(arm,dict(source,path=str(cnf),split="eval"),17,CAP-0.25)
        finally:os.chdir(previous)
        status=row["status"]
        verified=bool(row["verified"])
        extra={"math_certified":bool(row.get("php_math_certified"))}
    elif arm.startswith("R153_"):
        ctx=ROOT/"cross_aux/context"
        sys.path.insert(0,str(ctx/"research"))
        from drnas_r28_context_memory import Memory,solve
        binary=str((ROOT/("mre_r28_native/drnas_r28_native" if arm=="R153_NATIVE_DIRECT" else "mre_r28_context/drnas_r28_context")).resolve())
        db=ROOT/"cross_results"/("memory-shard-%02d.sqlite"%shard)
        if not hasattr(run_one,"memory"):
            run_one.memory=Memory(db)
            run_one.memory_digest=run_one.memory.digest()
        row,out=solve(run_one.memory,str(cnf),"eval",CAP,17,arm=="R153_CONTEXT_MEMORY",binary)
        assert run_one.memory.digest()==run_one.memory_digest,"EVAL_MEMORY_MUTATED"
        status=row["status"]
        verified=bool(row["verified"])
        extra={"route":"R28 context/native with R153 real-context protocol","memory_preparation_s":row.get("prepare_s",0)}
    else:
        binary=str((ROOT/("build/drnas-x5" if arm=="X5_NO_MIN" else ("build/drnas-clause-cf6" if arm=="CF7_B2L_32" else "build/kissat"))).resolve())
        with tempfile.TemporaryDirectory() as t:
            proof=pathlib.Path(t)/"proof.drat"
            if arm=="Kissat":cmd=[binary,str(cnf),str(proof)]
            elif arm=="CF7_B2L_32":
                cmd=[binary,str(cnf),"--mode","core","--time",str(CAP),"--x5-no-minimize","--x5-no-retain","--proof",str(proof),"--cf5-policy","B2L_32"]
            else:cmd=[binary,str(cnf),"--mode","core","--time",str(CAP),"--x5-no-minimize","--proof",str(proof)]
            def limit():
                resource.setrlimit(resource.RLIMIT_FSIZE,(512*1024*1024,512*1024*1024))
            proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True,preexec_fn=limit)
            try:out,err=proc.communicate(timeout=CAP+0.2);killed=False
            except subprocess.TimeoutExpired:
                killed=True;os.killpg(proc.pid,signal.SIGKILL);out,err=proc.communicate()
            if not killed and proc.returncode==10:
                verified=CF.DATA.sat_witness_valid(cnf,CF.DATA.nvars(cnf),out)
                if not verified:raise RuntimeError(("INVALID_SAT",source["id"],arm))
                status="SAT_VERIFIED"
            elif not killed and proc.returncode==20:
                status="UNSAT_UNVERIFIED"
                if proof.is_file() and proof.stat().st_size:
                    try:
                        ck=subprocess.run([str(ROOT/"build/drat-trim"),str(cnf),str(proof)],capture_output=True,text=True,timeout=90)
                        verified=ck.returncode==0 and "s VERIFIED" in ck.stdout
                    except subprocess.TimeoutExpired:pass
                if verified:status="UNSAT_CERTIFIED"
            elif not killed and proc.returncode==153:status="PROOF_LIMIT"
            elif not killed and proc.returncode not in (0,124):raise RuntimeError(("SOLVER_EXIT",arm,proc.returncode,err[-500:]))
    elapsed=time.perf_counter()-start
    accepted=verified and elapsed<=CAP
    return dict(id=source["id"],family=source["normalized_name_family"],sha256=source["sha256"],
         arm=arm,status=status,verified=verified,accepted=accepted,elapsed_e2e_s=round(elapsed,6),
         PAR2_verified_s=round(elapsed if accepted else CAP*2,6),**extra)
def shard(index):
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    m=json.loads((ROOT/"cf7/manifest.json").read_text())
    assert len(m["sources"])==100 and m["cap_s"]==CAP
    assert m["protocol"]=="CF7-FIVE-ARM-REAL100-V1"
    sources=[s for s in m["sources"] if s["id"]%10==index]
    assert len(sources)==10
    dest=ROOT/"cross_results"/("shard-%02d"%index);dest.mkdir(parents=True,exist_ok=True)
    rows=[]
    for s in sources:
        order=list(ARMS);random.Random(20261114+s["id"]).shuffle(order)
        for arm in order:
            row=run_one(arm,s,index);rows.append(row)
            emit("CROSS_TRIAL",row)
        verified={r["status"].startswith("SAT") for r in rows[-len(ARMS):] if r["accepted"]}
        assert len(verified)<=1,("CONTRADICTORY_VERIFIED_RESULT",s["id"])
        with (dest/"trials.jsonl").open("w") as f:
            for r in rows:f.write(json.dumps(r,sort_keys=True)+"\n")
    (dest/"meta.json").write_text(json.dumps({"shard":index,"sources":10,"trials":len(rows),"arms":ARMS}))
    emit("CROSS_SHARD_PASS",{"shard":index,"trials":len(rows)})
def report():
    m=json.loads((ROOT/"cf7/manifest.json").read_text())
    records=collections.defaultdict(dict)
    for i in range(10):
        d=ROOT/"cross_downloads"/("cross-shard-"+str(i))
        meta=json.loads((d/"meta.json").read_text())
        assert meta["shard"]==i and meta["trials"]==70
        for s in (d/"trials.jsonl").read_text().splitlines():
            row=json.loads(s);ident=row["id"];arm=row["arm"]
            assert ident%10==i and arm in ARMS and arm not in records[ident]
            assert row["sha256"]==m["sources"][ident]["sha256"]
            records[ident][arm]=row
    assert len(records)==100 and all(set(a)==set(ARMS) for a in records.values())
    summary={}
    for arm in ARMS:
        a=[r[arm] for r in records.values()]
        summary[arm]={"PAR2_verified_s":round(sum(x["PAR2_verified_s"] for x in a),5),
          "verified":sum(x["accepted"] for x in a),
          "SAT":sum(x["accepted"] and x["status"]=="SAT_VERIFIED" for x in a),
          "UNSAT":sum(x["accepted"] and x["status"].startswith("UNSAT_") for x in a)}
    ranked=sorted(summary,key=lambda x:summary[x]["PAR2_verified_s"])
    out={"protocol":"CROSS-REAL100-SAME-SOURCES-V1","cap_s":CAP,
         "original_source_run":43613581688,"one_logical_cpu":True,
         "blind_holdout":False,"no_promotion":True,"arms":summary,
         "ranked":ranked,"trials":700,
         "cases":[{"id":i,"family":m["sources"][i]["normalized_name_family"],
             "sha256":m["sources"][i]["sha256"],"arms":records[i]} for i in sorted(records)]}
    dst=ROOT/"cross_final";dst.mkdir(exist_ok=True)
    (dst/"report.json").write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
    emit("CROSS_FINAL",{"status":"COMPLETE","arms":summary,"ranked":ranked,"trials":700})
if __name__=="__main__":
    a=argparse.ArgumentParser();a.add_argument("mode",choices=["shard","report"]);a.add_argument("--shard",type=int,default=0);v=a.parse_args()
    shard(v.shard) if v.mode=="shard" else report()
