#!/usr/bin/env python3
"""Focused post-discovery comparison: original SAT2024 worker source ID64.
Source was discovered by MATCH1: retrospective, NOT a blind or general test.
"""
import hashlib,json,os,resource,statistics,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"sat_match1"))
from model import parse_cnf,verify

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"sat_match64_results"
SOURCE_ID=64
SOURCE_SHA="fc529dff1a6f763c97b0ed1dd33199e0d9dd26c50d210f9032e4fdaab5534c16"
CAP=5.0
ARMS={
 "MATCH1":["python3","research/sat_match64/solve.py"],
 "X59_BASE":["build/drnas-sat-clause1"],
 "X59_SCORE":["build/drnas-sat-clause1"],
 "X59_PROBE":["build/drnas-sat-clause1"],
 "Kissat":["build/kissat"],
 "CaDiCaL":["build/cadical"]
}
def hash_file(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def model_ok(n,clauses,stdout):
    assignment={}
    for line in stdout.splitlines():
        if not line.startswith("v "):continue
        for token in line[2:].split():
            x=int(token)
            if not x:continue
            if abs(x)>n or (abs(x) in assignment and assignment[abs(x)]!=(x>0)):
                return False
            assignment[abs(x)]=x>0
    if len(assignment)!=n:return False
    return verify(n,clauses,[assignment[i] for i in range(1,n+1)])
def command(arm,source):
    if arm=="MATCH1":return ARMS[arm]+[str(source)]
    if arm.startswith("X59_"):
        extra={"X59_BASE":[],"X59_SCORE":["--sat-clause1-score"],
               "X59_PROBE":["--sat-clause1-probe"]}[arm]
        return ARMS[arm]+[str(source),"--mode","core","--time",str(CAP)]+extra
    if arm=="Kissat":return ARMS[arm]+[str(source)]
    if arm=="CaDiCaL":return ARMS[arm]+["-q","--no-binary",str(source)]
    raise ValueError(arm)
def trial(arm,rep,source,n,clauses):
    cmd=command(arm,source)
    start=time.perf_counter()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=CAP+0.2,check=False)
        expired=False
    except subprocess.TimeoutExpired:
        p=None;expired=True
    elapsed=time.perf_counter()-start
    if expired:status="TIMEOUT";verified=False
    elif p.returncode==10:
        verified="s SATISFIABLE" in p.stdout and model_ok(n,clauses,p.stdout)
        status="SAT_VERIFIED" if verified else "INVALID_MODEL"
    elif p.returncode==20:status="CONTRADICTS_KNOWN_SAT";verified=False
    elif p.returncode in (0,153):status="UNKNOWN";verified=False
    else:status="SOLVER_ERROR";verified=False
    if status in ("INVALID_MODEL","CONTRADICTS_KNOWN_SAT","SOLVER_ERROR"):
        raise RuntimeError(f"CRITICAL {arm} {status} stderr={p.stderr[-300:] if p else ''}")
    accepted=verified and elapsed<=CAP
    return dict(arm=arm,rep=rep,status=status,verified=verified,
        e2e_s=round(elapsed,6),PAR2_s=round(elapsed if accepted else 2*CAP,6))
def main():
    OUT.mkdir(exist_ok=True)
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    frozen=json.loads((ROOT/"cf7/manifest.json").read_text())
    src=next(x for x in frozen["sources"] if x["id"]==SOURCE_ID)
    assert src["sha256"]==SOURCE_SHA
    path=ROOT/src["path"];assert hash_file(path)==SOURCE_SHA
    parsed,reason=parse_cnf(path)
    if parsed is None:raise RuntimeError(reason)
    n,clauses=parsed
    bins={arm:hash_file(ROOT/ARMS[arm][0]) for arm in ("X59_BASE","Kissat","CaDiCaL")}
    records=[]
    for rep in range(5):
        arms=list(ARMS);offset=rep%len(arms)
        for arm in arms[offset:]+arms[:offset]:
            records.append(trial(arm,rep,path,n,clauses))
    results={}
    for arm in ARMS:
        subset=[r for r in records if r["arm"]==arm]
        results[arm]=dict(solved=sum(r["verified"] and r["e2e_s"]<=CAP for r in subset),
                          par2_sum=round(sum(x["PAR2_s"] for x in subset),6),
                          median_e2e_s=round(statistics.median(x["e2e_s"] for x in subset),6))
    (OUT/"trials.json").write_text(json.dumps(records,indent=2,sort_keys=True)+"\n")
    (OUT/"protocol.json").write_text(json.dumps(dict(source_id=SOURCE_ID,source_sha256=SOURCE_SHA,
        source_family=src["normalized_name_family"],source_manifest_sha256=hash_file(ROOT/"cf7/manifest.json"),
        cpu=cpu,repetitions=5,cap_s=CAP,post_discovery=True,one_logical_cpu=True,
        binaries_sha256=bins,nvars=n,clauses=len(clauses),git_sha=os.environ.get("GITHUB_SHA")),
        indent=2,sort_keys=True)+"\n")
    print("SAT_MATCH64_RESULT "+json.dumps(dict(source_id=SOURCE_ID,source_sha256=SOURCE_SHA,
        cap_s=CAP,results=results),sort_keys=True),flush=True)
if __name__=="__main__":main()
