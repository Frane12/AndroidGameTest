#!/usr/bin/env python3
"""DRNAS SOLVER-TIME60 — 2 previously frozen original MIXAB3 SHA,
four arms, two paired repetitions, 60s hard E2E cap, one logical CPU.
Report actual observed subprocess wall time and native CDCL solver_s,
never treat a timeout as completed solve time.
"""
import argparse, hashlib, json, os, pathlib, random, re, resource, subprocess, tempfile, time
import drnas_gf_cdcl_novel2d_medium as base
import drnas_xorabc3_live_trail as abc3
import drnas_equiv9_prospective_seed_holdout as e9
import r158x_causal_benchmark as telemetry

ROOT=pathlib.Path("mre_gf_cdcl_solver_time60")
CAP=60.0
REPS=2
ARMS=("clean","direct","novel2b","cms_plain")
MODES={"clean":"clean","direct":"direct_boundary","novel2b":"novel2b"}
PROTO="GFCDCL-SOLVER-TIME60-TWO-MIXAB3-SOURCE-SHA-4ARMS-2REPS-ONECPU-v1"
def need(ok,msg):
    if not ok:raise RuntimeError("SOLVER_TIME60_FAIL_CLOSED "+str(msg))
def digest(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def load(p):return json.loads(pathlib.Path(p).read_text())
def save(p,obj):
    path=pathlib.Path(p);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def preregister():
    # Exact two SHA already selected and frozen before any 60s candidate run.
    base_m=base.verify()
    selected=[c["sha256"] for c in base_m["cases"]]
    need(len(selected)==2 and len(set(selected))==2,"invalid source frozen count")
    info=dict(protocol=PROTO,source_sha=selected,arms=list(ARMS),reps=REPS,
              e2e_hard_cap_s=CAP,attempts=len(selected)*len(ARMS)*REPS,
              pinned_native_binary_sha256=digest(base.BIN),
              original_source_manifest_sha256=digest(base.ROOT/"manifest.json"),
              script_sha256=digest(__file__),single_logical_CPU=True,
              sources_previously_seen=True,not_blind=True,
              raw_UNSAT_separate_from_independently_proven=True)
    if (ROOT/"manifest.json").exists():
        need(load(ROOT/"manifest.json")==info,"solver-time preregistration drift")
    else:save(ROOT/"manifest.json",info)
    print("SOLVER_TIME60_FROZEN "+json.dumps(info,sort_keys=True),flush=True)
    return base_m
def benchmark(c,rep,arm):
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    wall_start=time.perf_counter()
    cpu_parent_start=time.process_time()
    path=base.source(c)
    n,original=e9.x22.read_cnf(path)
    need(n>0 and digest(path)==c["sha256"],"original source SHA drift")
    backend="UNKNOWN";status="TIMEOUT";sat_verified=False
    solver_wall=None;solver_cpu=None;native_solver_seconds=None
    cdl_stats={};external_time_limit=False
    with tempfile.TemporaryDirectory(dir=ROOT) as td:
        tsv=pathlib.Path(td)/"source-certified.tsv"
        row_info=None
        if arm not in ("clean","cms_plain"):
            row_info,_=abc3.export_native(path,tsv)
            need(row_info["verified"],"original-CNF source XOR rows unverified")
        prep_seconds=time.perf_counter()-wall_start
        left=CAP-prep_seconds
        need(left>1.25,"preparation exhausted nominal E2E cap")
        if arm=="cms_plain":
            command=[str(abc3.abc2.prev.CMS.resolve()),"--verb","0","-t","1",
                     str(path.resolve())]
        else:
            command=[str(base.BIN.resolve()),MODES[arm],str(path.resolve()),
                     str(tsv.resolve()),str(max(1.0,left-.50))]
        env=os.environ.copy()
        env["LD_LIBRARY_PATH"]=str(pathlib.Path("mre_equiv12/lib").resolve())+":" + str(pathlib.Path("mre5/lib").resolve())+":"+env.get("LD_LIBRARY_PATH","")
        child_start=time.perf_counter()
        usage_before=resource.getrusage(resource.RUSAGE_CHILDREN)
        try:
            r=subprocess.run(command,capture_output=True,text=True,env=env,
                             timeout=max(.1,left-.02),check=False)
        except subprocess.TimeoutExpired:
            r=None;external_time_limit=True
        child_elapsed=time.perf_counter()-child_start
        usage_after=resource.getrusage(resource.RUSAGE_CHILDREN)
        solver_wall=round(child_elapsed,6)
        solver_cpu=round((usage_after.ru_utime+usage_after.ru_stime)-
                         (usage_before.ru_utime+usage_before.ru_stime),6)
        if r is not None:
            need(r.returncode in (0,10,20),
                 "solver subprocess invalid exit "+str(r.returncode)+" "+r.stderr[-700:])
            if arm=="cms_plain":
                backend,sat_verified=e9.x22.solver_result("cms",r.returncode,
                                  r.stdout+"\n"+r.stderr,original,{})
                if backend=="SAT":need(sat_verified,"CMS model fails original CNF")
            else:
                output,tele,s,certified_source,derived_count=telemetry.parse_native(
                                 r.stdout.encode(),MODES[arm])
                backend=tele["status"]
                if backend=="SAT":
                    model=abc3.get_model(output)
                    need(model and e9.x22.holds(original,model),
                         "native model fails original CNF")
                    sat_verified=True
                if row_info is not None:
                    need(row_info["rows"]==certified_source,
                         "certified source row count drift")
                last=re.search(r"^R158X_RESULT .*?$",r.stdout,re.M)
                need(last is not None,"missing timed native result")
                kv={}
                for field in last.group().split():
                    if "=" in field:
                        key,value=field.split("=",1);kv[key]=value
                native_solver_seconds=float(kv["solver_s"])
                cdl_stats={k:int(kv[k]) for k in
                  ("derived_direct_proposals","source_direct_proposals",
                   "reason_clauses_completed","direct_proposals","source_rows")
                   if k in kv}
                cdl_stats.update({k:s.get(k) for k in
                                  ("conflicts","decisions","propagations")})
                cdl_stats["derived_rows"]=derived_count
            status="SAT" if backend=="SAT" else ("UNSAT_UNVERIFIED" if backend=="UNSAT" else "TIMEOUT")
    e2e=time.perf_counter()-wall_start
    need(e2e<=CAP+.25,"60s E2E hard cap exceeded")
    if e2e>=CAP:status="TIMEOUT";sat_verified=False
    need(status!="SAT" or sat_verified,"SAT cannot be unverified")
    need(digest(path)==c["sha256"],"source changed after benchmark")
    # Completed solve times exist only for SAT (model checked) or raw UNSAT;
    # UNSAT is explicitly NOT independently certified here.
    completed= status in ("SAT","UNSAT_UNVERIFIED")
    return dict(protocol=PROTO,sha256=c["sha256"],arm=arm,rep=rep,
        cpu=cpu,one_logical_cpu=True,cap_s=CAP,status=status,
        backend_status=backend,solver_completed=completed,
        solver_wall_s=solver_wall,solver_CPU_s=solver_cpu,
        native_internal_solver_s=native_solver_seconds,
        preparation_E2E_s=round(prep_seconds,6),
        wall_E2E_s=round(e2e,6),
        parent_CPU_s=round(time.process_time()-cpu_parent_start,6),
        external_timeout=external_time_limit,stats=cdl_stats,
        SAT_original_verified=sat_verified,
        UNSAT_independent_LRAT=False,
        original_sha_verified=True)
def shard(index):
    m=preregister()
    need(index in (0,1),"wrong index")
    case=m["cases"][index]
    records=[]
    for rep in range(REPS):
        order=list(ARMS)
        random.Random(case["sha256"]+"|SOLVER_TIME60|"+str(rep)).shuffle(order)
        for arm in order:
            a=benchmark(case,rep,arm)
            records.append(a)
            save(ROOT/f"shard-{index}.json",records)
            print("SOLVER_TIME60_TRIAL "+json.dumps(a,sort_keys=True),flush=True)
    need(len(records)==8,"incomplete time60 shard")
    print("SOLVER_TIME60_SHARD_PASS "+str(index)+" 8",flush=True)
def audit():
    m=preregister()
    rr=[]
    for i in range(2):
        a=load(ROOT/f"shard-{i}.json")
        need(len(a)==8,"incomplete shard "+str(i))
        rr+=a
    expected={(c["sha256"],r,arm) for c in m["cases"]
              for r in range(REPS) for arm in ARMS}
    actual=[(a["sha256"],a["rep"],a["arm"]) for a in rr]
    need(len(actual)==len(expected) and set(actual)==expected,"missing paired trials")
    table={}
    for c in m["cases"]:
        key=c["sha256"]
        table[key]={}
        for arm in ARMS:
            z=sorted([x for x in rr if x["sha256"]==key and x["arm"]==arm],
                     key=lambda x:x["rep"])
            need(len(z)==REPS,"invalid pair")
            table[key][arm]=dict(
                solver_status=[x["status"] for x in z],
                solver_wall_s=[x["solver_wall_s"] for x in z],
                solver_internal_s=[x["native_internal_solver_s"] for x in z],
                solver_CPU_s=[x["solver_CPU_s"] for x in z],
                E2E_s=[x["wall_E2E_s"] for x in z],
                completed_count=sum(x["solver_completed"] for x in z),
                verified_SAT=sum(x["SAT_original_verified"] for x in z),
                raw_UNSAT_without_independent_proof=sum(x["backend_status"]=="UNSAT" for x in z),
                strict_PAR2_s=round(sum(x["wall_E2E_s"] if x["SAT_original_verified"]
                   else 2*CAP for x in z),6),
                GF2_proposals=sum(x["stats"].get("derived_direct_proposals",0) for x in z),
                GF2_reasons=sum(x["stats"].get("reason_clauses_completed",0) for x in z))
    outcome=dict(protocol=PROTO,trials=len(rr),source_frozen_previously_seen=True,
                 comparison="per_SHA two identical arm repetitions one logical CPU",
                 cap_E2E_s=CAP,
                 timeout_is_censored_not_solved=True,
                 independent_UNSAT_proof_present=False,
                 per_original_SHA_solver_times=table)
    save(ROOT/"report.json",outcome)
    print("SOLVER_TIME60_FINAL "+json.dumps(outcome,sort_keys=True),flush=True)
def main():
    p=argparse.ArgumentParser()
    p.add_argument("cmd",choices=("shard","audit"))
    p.add_argument("--shard",type=int)
    q=p.parse_args()
    if q.cmd=="shard":shard(q.shard)
    else:audit()
if __name__=="__main__":main()
