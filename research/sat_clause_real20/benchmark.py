#!/usr/bin/env python3
"""SAT-CLAUSE1 retrospective REAL20 (SAT-only model verification).
Preselected IDs 0,5,...95 from original frozen CF7 SAT2024 REAL100.
Unsat without a checked proof is never accepted. Single CPU, paired arms.
"""
import argparse,hashlib,json,os,resource,signal,subprocess,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BINARY=ROOT/"build/drnas-sat-clause1"
SOURCES=ROOT/"cf7/manifest.json"
CAP=3.0
ARMS={"OFF":[],"SCORE":["--sat-clause1-score"],"PROBE":["--sat-clause1-probe"]}

def sha(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        while (data:=f.read(1<<20)):h.update(data)
    return h.hexdigest()

def independent_check(path,output):
    assignments={};n=None;m=None;count=0;clause=[];good=True
    for line in output.splitlines():
        if line.startswith("v "):
            for word in line[2:].split():
                l=int(word)
                if not l:continue
                if abs(l) in assignments and assignments[abs(l)]!=(l>0):return False
                assignments[abs(l)]=l>0
    with open(path) as f:
        for line in f:
            line=line.strip()
            if not line or line[0] in "c%":continue
            if line.startswith("p "):
                fields=line.split()
                if len(fields)!=4 or fields[1]!="cnf" or n is not None:return False
                n,m=int(fields[2]),int(fields[3])
                if len(assignments)!=n:return False
                continue
            if n is None:return False
            for token in line.split():
                l=int(token)
                if l==0:
                    if not clause or not any(assignments.get(abs(x))==(x>0) for x in clause):
                        return False
                    clause=[];count+=1
                else:
                    if abs(l)>n:return False
                    clause.append(l)
    return n is not None and not clause and count==m

def run_one(source,arm,rep,aff):
    path=ROOT/source["path"];assert sha(path)==source["sha256"]
    cmd=[str(BINARY),str(path),"--mode","core","--time",str(CAP),"--stats"]+ARMS[arm]
    def limits():
        if aff is not None:os.sched_setaffinity(0,{aff})
        resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,)*2)
        resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024**2,)*2)
    start=time.perf_counter();expired=False
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=CAP+0.20,
                         preexec_fn=limits,check=False)
    except subprocess.TimeoutExpired:
        expired=True;p=None
    elapsed=time.perf_counter()-start
    status="TIMEOUT" if expired else "UNKNOWN";stats={}
    if p is not None:
        if p.returncode==10:
            if "s SATISFIABLE" not in p.stdout or not independent_check(path,p.stdout):
                raise RuntimeError(f"INVALID SAT on original CNF {source['id']} {arm}")
            status="SAT_VERIFIED"
        elif p.returncode==20:status="UNSAT_UNVERIFIED"
        elif p.returncode not in (0,10,20,153):
            raise RuntimeError(f"SOLVER ERROR {source['id']} {arm} {p.returncode} {p.stderr[-250:]}")
        for line in p.stderr.splitlines():
            if line.startswith("X41_STATS "):
                try:
                    obj=json.loads(line.split(" ",1)[1])
                    stats.update(conflicts=obj.get("conflicts"),decisions=obj.get("decisions"))
                except ValueError:pass
            if line.startswith("SAT_CLAUSE1_STATS "):
                try:stats.update(json.loads(line.split(" ",1)[1]))
                except ValueError:pass
    accepted=(status=="SAT_VERIFIED" and elapsed<=CAP)
    return dict(id=source["id"],family=source["normalized_name_family"],
                sha256=source["sha256"],arm=arm,rep=rep,status=status,
                accepted=accepted,elapsed_s=elapsed,
                PAR2_sat_s=elapsed if accepted else 2*CAP,**stats)

def main():
    p=argparse.ArgumentParser();p.add_argument("--shard",type=int,required=True)
    args=p.parse_args();assert 0<=args.shard<4
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    manifest=json.loads(SOURCES.read_text())
    assert manifest["count"]==100
    assert len({s["sha256"] for s in manifest["sources"]})==100
    group=sorted((s for s in manifest["sources"] if s["id"]%5==0 and
                  (s["id"]//5)%4==args.shard),key=lambda x:x["id"])
    assert len(group)==5
    out=ROOT/"sat_clause_real20_results"/str(args.shard);out.mkdir(parents=True,exist_ok=False)
    results=[];start=time.perf_counter()
    for source in group:
        assert sha(ROOT/source["path"])==source["sha256"]
        for rep in range(2):
            arms=list(ARMS)
            offset=(source["id"]//5+rep)%3
            for arm in arms[offset:]+arms[:offset]:
                row=run_one(source,arm,rep,cpu)
                results.append(row)
                # Only one compact progress line per original; full rows in artifact.
        small=results[-6:]
        print("SAT_REAL20_SOURCE "+json.dumps(dict(id=source["id"],sha256=source["sha256"],
            counts={a:sum(r["accepted"] for r in small if r["arm"]==a) for a in ARMS})),flush=True)
    (out/"results.json").write_text(json.dumps(results,indent=2,sort_keys=True)+"\n")
    (out/"metadata.json").write_text(json.dumps(dict(cap_s=CAP,shard=args.shard,
        repetitions=2,one_cpu=cpu,source_ids=[s["id"] for s in group],
        frozen_manifest_sha256=sha(SOURCES),git_sha=os.environ.get("GITHUB_SHA"),
        scope="SAT MODEL only: unverified UNSAT penalized; retrospective previously exposed sources"),
        indent=2,sort_keys=True)+"\n")
    totals={arm:dict(solved=sum(r["accepted"] for r in results if r["arm"]==arm),
                     par2_s=round(sum(r["PAR2_sat_s"] for r in results if r["arm"]==arm),6),
                     flips=sum(r.get("phase_flips",0) for r in results if r["arm"]==arm),
                     failed_literals=sum(r.get("failed_literals",0) for r in results if r["arm"]==arm))
            for arm in ARMS}
    print("SAT_REAL20_SHARD "+json.dumps(dict(shard=args.shard,sources=5,trials=len(results),
        arms=totals,elapsed_s=round(time.perf_counter()-start,3))),flush=True)

if __name__=="__main__":main()
