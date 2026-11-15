#!/usr/bin/env python3
"""Frozen-source, single-core, verified SAT-only native structural ablation.
This is RETROSPECTIVE; SOURCE64 was observed in earlier experiments.
"""
import collections,hashlib,json,os,resource,signal,statistics,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"sat_native1_results"
CAP64=5.0
NATIVE=ROOT/"build/drnas-sat-construct"
FUSED=ROOT/"build/drnas-sat-native-x59"
ARMS={
 "NATIVE_DIRECT":lambda cnf:[str(NATIVE),str(cnf),"--max-ms","25","--stats"],
 "X59_OFF":lambda cnf:[str(FUSED),str(cnf),"--mode","core","--time",str(CAP64),"--stats"],
 "X59_ON":lambda cnf:[str(FUSED),str(cnf),"--mode","core","--time",str(CAP64),"--sat-construct-ms","25","--stats"],
 "Kissat":lambda cnf:[str(ROOT/"build/kissat"),str(cnf)],
 "CaDiCaL":lambda cnf:[str(ROOT/"build/cadical"),"-q","--no-binary",str(cnf)]}
SHA64="fc529dff1a6f763c97b0ed1dd33199e0d9dd26c50d210f9032e4fdaab5534c16"
def sha(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        while data:=f.read(1<<20):h.update(data)
    return h.hexdigest()
def source_model_valid(path,stdout):
    values={}
    for row in stdout.splitlines():
        if not row.startswith("v "):continue
        for tok in row[2:].split():
            v=int(tok)
            if v==0:continue
            if abs(v) in values and values[abs(v)]!=(v>0):return False
            values[abs(v)]=(v>0)
    n=m=None;count=0;open_clause=False;satisfied=False
    with open(path) as f:
        for line in f:
            words=line.split()
            if not words or words[0] in ("c","%"):continue
            if words[0]=="p":
                if n is not None or len(words)!=4 or words[1]!="cnf":return False
                n=int(words[2]);m=int(words[3])
                if len(values)!=n:return False
                continue
            if n is None:return False
            for tok in words:
                v=int(tok)
                if v==0:
                    if not satisfied:return False
                    open_clause=False;satisfied=False;count+=1
                else:
                    if abs(v)>n:return False
                    open_clause=True
                    satisfied=satisfied or values.get(abs(v))==(v>0)
    return n is not None and not open_clause and count==m
def one(arm,src,rep,cap):
    path=ROOT/src["path"];assert sha(path)==src["sha256"]
    cmd=ARMS[arm](path)
    if arm.startswith("X59_"):
        k=cmd.index("--time")+1;cmd[k]=str(cap)
    begin=time.perf_counter()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=cap+0.2,check=False)
    except subprocess.TimeoutExpired:p=None
    process_end=time.perf_counter()
    status="TIMEOUT" if p is None else "UNKNOWN"
    meta={}
    if p is not None:
        if p.returncode==10:
            if "s SATISFIABLE" not in p.stdout or not source_model_valid(path,p.stdout):
                raise RuntimeError(f"INVALID ORIGINAL SAT witness id={src['id']} arm={arm}")
            status="SAT_VERIFIED"
        elif p.returncode==20:status="UNSAT_UNVERIFIED"
        elif p.returncode not in (0,10,20,153):
            raise RuntimeError(f"SOLVER_ERROR source={src['id']} arm={arm} rc={p.returncode} {p.stderr[-320:]}")
        for line in p.stderr.splitlines():
            if line.startswith("SAT_NATIVE_STATS ") or line.startswith("SAT_CONSTRUCT_STATS "):
                try:meta.update(json.loads(line.split(" ",1)[1]))
                except ValueError:pass
    # Include independent checking in E2E. Spent time is monotonic wall clock.
    elapsed=time.perf_counter()-begin
    accepted=status=="SAT_VERIFIED" and elapsed<=cap
    if src["id"]==64 and status=="UNSAT_UNVERIFIED":
        raise RuntimeError("UNSAT contradicts known SAT source64")
    return dict(id=src["id"],sha256=src["sha256"],family=src["normalized_name_family"],
        arm=arm,rep=rep,status=status,verified=accepted,
        process_wall_s=round(process_end-begin,6),
        e2e_s=round(elapsed,6),PAR2_sat_s=round(elapsed if accepted else 2*cap,6),
        **meta)
def main():
    OUT.mkdir(parents=True,exist_ok=True)
    aff=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{aff})
    frozen=ROOT/"cf7/manifest.json"
    m=json.loads(frozen.read_text())
    assert m["count"]==100 and len(m["sources"])==100
    assert len({s["sha256"] for s in m["sources"]})==100
    sources=sorted(m["sources"],key=lambda s:s["id"])
    assert set(s["id"] for s in sources)==set(range(100))
    selected=next(s for s in sources if s["id"]==64)
    assert selected["sha256"]==SHA64
    manifest_sha=sha(frozen)
    # Prospectively frozen full 100 SOURCE IDs, but previously seen elsewhere.
    # Native-only source scan is independent of formula outcomes; 150 ms per case.
    screening=[]
    for source in sources:
        screening.append(one("NATIVE_DIRECT",source,0,0.150))
    summary=collections.Counter(x.get("method",x["status"]) if x["verified"] else x["status"]
                               for x in screening)
    (OUT/"original100.json").write_text(json.dumps(screening,indent=2,sort_keys=True)+"\n")
    print("NATIVE100_SUMMARY "+json.dumps(dict(sources=100,
        solved=sum(x["verified"] for x in screening),methods=dict(summary))),flush=True)
    # Exactly matched frozen worker64 case: five paired repetitions, same CPU.
    records=[];arms=list(ARMS)
    for rep in range(5):
        for arm in arms[rep%len(arms):]+arms[:rep%len(arms)]:
            records.append(one(arm,selected,rep,CAP64))
    aggregate={}
    for arm in ARMS:
        rows=[r for r in records if r["arm"]==arm]
        aggregate[arm]=dict(solved=sum(r["verified"] for r in rows),
            median_e2e_s=round(statistics.median(r["e2e_s"] for r in rows),6),
            par2_sum_s=round(sum(r["PAR2_sat_s"] for r in rows),6),
            methods=collections.Counter(r.get("method","N/A") for r in rows))
    (OUT/"worker64.json").write_text(json.dumps(records,indent=2,sort_keys=True)+"\n")
    print("NATIVE64_RESULT "+json.dumps(dict(source_id=64,source_sha256=SHA64,
        cap_s=CAP64,arms=aggregate),sort_keys=True),flush=True)
    # Previously exposed original20 IDs, full native fallback comparison.
    samples=[x for x in sources if x["id"]%5==0]
    assert len(samples)==20
    rows20=[]
    for source in samples:
        for arm in ("X59_OFF","X59_ON"):
            rows20.append(one(arm,source,0,0.70))
    totals={arm:dict(solved=sum(x["verified"] for x in rows20 if x["arm"]==arm),
                     par2_sum_s=round(sum(x["PAR2_sat_s"] for x in rows20
                         if x["arm"]==arm),6)) for arm in ("X59_OFF","X59_ON")}
    (OUT/"real20.json").write_text(json.dumps(rows20,indent=2,sort_keys=True)+"\n")
    print("NATIVE_REAL20_RESULT "+json.dumps(totals,sort_keys=True),flush=True)
    pins={name:sha(p) for name,p in {
        "native":NATIVE,"fused":FUSED,
        "kissat":ROOT/"build/kissat","cadical":ROOT/"build/cadical"}.items()}
    (OUT/"protocol.json").write_text(json.dumps(dict(
        original_manifest_sha256=manifest_sha,source_id64_sha256=SHA64,
        cpu=aff,pins=pins,repeat64=5,cap64_s=CAP64,real20_cap_s=0.7,
        native100_cap_s=0.15,one_logical_core=True,
        independent_original_CNF_model_verification=True,
        unsat_credit=False,frozen_originals_retrospective=True,
        code_sha=os.environ.get("GITHUB_SHA")),indent=2,sort_keys=True)+"\n")

if __name__=="__main__":main()
