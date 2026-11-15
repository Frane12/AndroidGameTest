#!/usr/bin/env python3
"""REAL2025: frozen previously unused-in-this-study original CNF paired audit.
Native ON/OFF + Kissat/CaDiCaL/CMS; SAT models independently checked against
source and UNSAT only with externally checked DRAT/FRAT within same E2E cap.
"""
import argparse,collections,hashlib,json,os,random,resource,signal,statistics,subprocess,tempfile,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
SRC=ROOT/"sat_real2025_inputs"
OUT=ROOT/"sat_real2025_results"
FREEZE_SHA="47cc882a3893b2ecaf543341040d41c417eb13d8eb940198d37143715f65db4e"
CAT_SHA="d02406bb212498ea1d2d9f2e968f9a8f6ad3b6bc479ae1b1368d5b4d638a9120"
CAP=8.0; REP=2; SHARDS=4
ARMS=("X59_OFF","X59_UNIFIED","Kissat","CaDiCaL","CMS")
REF_HASH={
 "build/kissat":"3f95aa678e181b46b248605dad02011b68580c68f230f0e29500ec8a9cb6c60d",
 "build/cadical":"4e453f276393e9689fe1484fa78c2b32a02e7bbd04c02c4b001f960bdebb3f2e",
 "build/cms":"00db7e59c634842acbfc6676bf0f5d30a3fdabbd0ec2fa17b20bb0bf683c7207",
 "build/drat-trim":"92f0aa9575ed519d66a99b8b1b3dde6ece4618ae4c202a3a4b200265dda0aa7a",
 "build/frat-rs":"ba6527c4c64ff35d8905ffc3ccc9dead2160eb117e94c27ee06ed94c7db892c"
}
def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        while data:=f.read(1<<20):h.update(data)
    return h.hexdigest()
def manifest():
    p=SRC/"manifest.json"
    assert sha(p)==FREEZE_SHA,("source manifest drift",sha(p))
    obj=json.loads(p.read_text())
    assert obj["protocol"]=="DRNAS-REAL2025-FROZEN-ORIGINAL-V1"
    assert obj["catalog_sha256"]==CAT_SHA and obj["ready_count"]==19
    assert len(obj["ready_sources"])==19
    assert len({r["sha256"] for r in obj["ready_sources"]})==19
    assert all(row["status"]=="READY" for row in obj["ready_sources"])
    assert all(sha(ROOT/r["path"])==r["sha256"] for r in obj["ready_sources"])
    return obj
def hashes():
    for p,d in REF_HASH.items():
        assert sha(ROOT/p)==d,("reference hash drift",p,sha(ROOT/p))
    return {p:sha(ROOT/p) for p in ("build/drnas-sat-native-x59",*REF_HASH)}
def command(arm,cnf,proof):
    if arm.startswith("X59_"):
        cmd=[str(ROOT/"build/drnas-sat-native-x59"),str(cnf),
             "--mode","core","--time",str(CAP),"--proof",str(proof),"--stats"]
        if arm=="X59_UNIFIED":cmd+=["--sat-construct-ms","100"]
        return cmd
    if arm=="Kissat":return [str(ROOT/"build/kissat"),str(cnf),str(proof)]
    if arm=="CaDiCaL":return [str(ROOT/"build/cadical"),"-q","--no-binary",str(cnf),str(proof)]
    if arm=="CMS":return [str(ROOT/"build/cms"),"--threads=1","--verb=0",
                           "--frat="+str(proof),str(cnf)]
    raise ValueError(arm)
def process(cmd,folder,limit):
    folder.mkdir(parents=True,exist_ok=False)
    def controls():
        resource.setrlimit(resource.RLIMIT_FSIZE,(192*1024**2,)*2)
        resource.setrlimit(resource.RLIMIT_AS,(4*1024**3,)*2)
    env=dict(os.environ,OMP_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1",MKL_NUM_THREADS="1")
    env["LD_LIBRARY_PATH"]=str(ROOT/"build/cms-libs/usr/lib/x86_64-linux-gnu")
    start=time.perf_counter()
    with (folder/"stdout").open("w") as out,(folder/"stderr").open("w") as err:
        p=subprocess.Popen(cmd,stdout=out,stderr=err,env=env,
                           start_new_session=True,preexec_fn=controls)
        timed=False
        try:p.wait(timeout=max(0.001,limit))
        except subprocess.TimeoutExpired:
            timed=True
            try:os.killpg(p.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            p.wait()
    return dict(rc=p.returncode,expired=timed,wall_s=time.perf_counter()-start,
                stdout=folder/"stdout",stderr=folder/"stderr")
def model_valid(cnf,stdout):
    assignments={}
    with stdout.open(errors="replace") as f:
        for line in f:
            if not line.startswith("v "):continue
            for word in line[2:].split():
                try:lit=int(word)
                except ValueError:return False
                if not lit:continue
                v=abs(lit)
                if v in assignments and assignments[v]!=(lit>0):return False
                assignments[v]=lit>0
    n=m=None;count=0;pending=False;satisfied=False
    with cnf.open(errors="replace") as f:
        for line in f:
            vals=line.split()
            if not vals or vals[0] in ("c","%"):continue
            if vals[0]=="p":
                if n is not None or len(vals)!=4 or vals[1]!="cnf":return False
                try:n,m=map(int,vals[2:])
                except ValueError:return False
                if len(assignments)!=n:return False
                continue
            if n is None:return False
            for word in vals:
                try:lit=int(word)
                except ValueError:return False
                if lit:
                    if abs(lit)>n:return False
                    pending=True
                    satisfied=satisfied or assignments.get(abs(lit))==(lit>0)
                else:
                    if not satisfied:return False
                    count+=1;pending=False;satisfied=False
    return n is not None and not pending and count==m
def trial(source,arm,rep):
    cnf=ROOT/source["path"];assert sha(cnf)==source["sha256"]
    with tempfile.TemporaryDirectory(prefix="sat-real2025-") as tmp:
        folder=Path(tmp)
        proof=folder/("proof.frat" if arm=="CMS" else "proof.drat")
        start=time.perf_counter()
        p=process(command(arm,cnf,proof),folder/"solver",CAP)
        status="TIMEOUT" if p["expired"] else "UNKNOWN"
        kind=None;verified=False;proof_bytes=proof.stat().st_size if proof.exists() else 0
        check_s=0.0;checker_rc=None
        err=p["stderr"].read_text(errors="replace")
        if not p["expired"]:
            stdout=p["stdout"].read_text(errors="replace")
            if p["rc"]==10:
                if "s SATISFIABLE" not in stdout:
                    status="INVALID_SAT_CONTRACT"
                elif model_valid(cnf,p["stdout"]):
                    status="SAT_VERIFIED";verified=True;kind="MODEL"
                else:status="INVALID_SAT_MODEL"
            elif p["rc"]==20:
                if "s UNSATISFIABLE" not in stdout:status="INVALID_UNSAT_CONTRACT"
                elif proof_bytes==0:status="UNSAT_UNVERIFIED"
                else:
                    if arm=="CMS":cmd=[str(ROOT/"build/frat-rs"),"elab",str(proof),str(cnf),"-v"]
                    else:cmd=[str(ROOT/"build/drat-trim"),str(cnf),str(proof)]
                    remaining=CAP-(time.perf_counter()-start)
                    if remaining>0:
                        checked=process(cmd,folder/"checker",remaining)
                        checker_rc=checked["rc"];check_s=checked["wall_s"]
                        ctext=checked["stdout"].read_text(errors="replace")
                        if not checked["expired"] and checker_rc==0 and "VERIFIED" in ctext:
                            kind="FRAT" if arm=="CMS" else "DRAT"
                            status="UNSAT_VERIFIED";verified=True
                        else:status="CHECK_TIMEOUT" if checked["expired"] else "UNSAT_PROOF_REJECTED"
                    else:status="CHECK_BUDGET_EXHAUSTED"
            elif p["rc"]==0:status="UNKNOWN"
            elif p["rc"] in (153,-25,-9,-11,137):status="RESOURCE_LIMIT"
            else:status="SOLVER_ERROR"
        elapsed=time.perf_counter()-start
        accepted=verified and elapsed<=CAP
        if status.startswith("INVALID_") or status=="UNSAT_PROOF_REJECTED" or status=="SOLVER_ERROR":
            raise RuntimeError(f"CRITICAL source {source['index']} {arm} {status} rc={p['rc']} stderr={err[-450:]}")
        telemetry={}
        for line in err.splitlines():
            if line.startswith("SAT_CONSTRUCT_STATS "):
                try:telemetry=json.loads(line.partition(" ")[2])
                except ValueError:pass
        row=dict(source_index=source["index"],gbd=source["gbd"],sha256=source["sha256"],
          vars=source["vars"],clauses=source["clauses"],original_bytes=source["bytes"],
          arm=arm,rep=rep,status=status,verified=verified,accepted=accepted,
          certificate_kind=kind,proof_bytes=proof_bytes,solver_rc=p["rc"],
          solver_s=round(p["wall_s"],6),checker_s=round(check_s,6),
          checker_rc=checker_rc,e2e_s=round(elapsed,6),
          PAR2_verified_s=round(elapsed if accepted else 2*CAP,6),
          structural=telemetry)
        return row
def shard(index):
    assert 0<=index<SHARDS
    obj=manifest();pins=hashes()
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    selected=[s for i,s in enumerate(obj["ready_sources"]) if i%SHARDS==index]
    out=OUT/f"shard-{index}";out.mkdir(parents=True,exist_ok=False)
    rows=[];began=time.perf_counter()
    for src in selected:
        for rep in range(REP):
            arms=list(ARMS)
            rot=(src["index"]+rep)%len(arms)
            for arm in arms[rot:]+arms[:rot]:
                rows.append(trial(src,arm,rep))
        recent=rows[-REP*len(ARMS):]
        print("REAL2025_SOURCE_DONE "+json.dumps(dict(gbd=src["gbd"],index=src["index"],
             verified={arm:sum(r["accepted"] for r in recent if r["arm"]==arm) for arm in ARMS},
             elapsed_s=round(time.perf_counter()-began,2))),flush=True)
    assert len(rows)==len(selected)*REP*len(ARMS)
    (out/"trials.jsonl").write_text("".join(json.dumps(r,sort_keys=True)+"\n" for r in rows))
    (out/"meta.json").write_text(json.dumps(dict(shard=index,source_indices=[x["index"] for x in selected],
         source_manifest_sha256=FREEZE_SHA,arms=ARMS,reps=REP,cap_s=CAP,
         logical_cpu=cpu,hashes=pins,git_sha=os.getenv("GITHUB_SHA"),
         independent_verification=True,source_outcome_blind=True),indent=2,sort_keys=True)+"\n")
    counts={arm:dict(solved=sum(x["accepted"] for x in rows if x["arm"]==arm),
               par2_s=round(sum(x["PAR2_verified_s"] for x in rows if x["arm"]==arm),5))
            for arm in ARMS}
    print("REAL2025_SHARD "+json.dumps(dict(index=index,sources=len(selected),
         trials=len(rows),arms=counts),sort_keys=True),flush=True)
def report():
    obj=manifest();all_rows=[]
    for i in range(SHARDS):
        p=OUT/f"shard-{i}"
        meta=json.loads((p/"meta.json").read_text())
        assert meta["source_manifest_sha256"]==FREEZE_SHA
        assert meta["reps"]==REP and meta["cap_s"]==CAP
        all_rows.extend(json.loads(s) for s in (p/"trials.jsonl").read_text().splitlines())
    expected={(s["index"],rep,arm) for s in obj["ready_sources"] for rep in range(REP) for arm in ARMS}
    actual={(r["source_index"],r["rep"],r["arm"]) for r in all_rows}
    assert actual==expected and len(all_rows)==len(expected)
    bysource=collections.defaultdict(dict)
    for row in all_rows:
        if row["verified"]:
            bysource[row["source_index"]][row["arm"]]=row["status"].split("_")[0]
    for idx,outcomes in bysource.items():
        if len(set(outcomes.values()))>1:raise RuntimeError(f"VERIFIED SAT/UNSAT disagreement {idx} {outcomes}")
    summary={}
    for arm in ARMS:
        subset=[r for r in all_rows if r["arm"]==arm]
        summary[arm]=dict(solved=sum(r["accepted"] for r in subset),
          SAT=sum(r["status"]=="SAT_VERIFIED" for r in subset),
          UNSAT=sum(r["status"]=="UNSAT_VERIFIED" for r in subset),
          attempted=len(subset),
          PAR2_sum_s=round(sum(r["PAR2_verified_s"] for r in subset),6),
          median_e2e_s=round(statistics.median(r["e2e_s"] for r in subset),6),
          statuses=dict(collections.Counter(r["status"] for r in subset)),
          math_activation=sum(r.get("structural",{}).get("found",False) is True for r in subset))
    paired=[]
    for source in obj["ready_sources"]:
        idx=source["index"]
        def avg(arm):
            return statistics.mean(r["PAR2_verified_s"] for r in all_rows
                                   if r["source_index"]==idx and r["arm"]==arm)
        paired.append((idx,avg("X59_OFF")-avg("X59_UNIFIED")))
    wins=sum(delta>0.0001 for _,delta in paired)
    losses=sum(delta< -0.0001 for _,delta in paired)
    final=dict(protocol="DRNAS-REAL2025-BLIND-UNIFIED-V1",
       source_manifest_sha256=FREEZE_SHA,source_count=len(obj["ready_sources"]),
       trial_count=len(all_rows),cap_s=CAP,repetitions=REP,arms=ARMS,
       summary=summary,paired=dict(wins=wins,losses=losses,ties=len(paired)-wins-losses,
                                   savings_s=sum(delta for _,delta in paired)),
       limitations=["20xx official originals downloaded before evaluation; size-restricted",
          "Not proof of historical source unexposure beyond explicit SHA audit",
          "Unsat only counts with independent standard proof checker within same cap",
          "Not competition hardware or competition time limits",
          "A 100-ms overhead can regress non-structural cases"])
    OUT.mkdir(exist_ok=True)
    (OUT/"final.json").write_text(json.dumps(final,indent=2,sort_keys=True)+"\n")
    (OUT/"trials.jsonl").write_text("".join(json.dumps(x,sort_keys=True)+"\n" for x in all_rows))
    print("REAL2025_FINAL "+json.dumps(dict(sources=final["source_count"],trials=len(all_rows),
       summary=summary,paired=final["paired"]),sort_keys=True),flush=True)
def main():
    p=argparse.ArgumentParser();p.add_argument("action",choices=["shard","report"])
    p.add_argument("--index",type=int);a=p.parse_args()
    shard(a.index) if a.action=="shard" else report()
if __name__=="__main__":main()
