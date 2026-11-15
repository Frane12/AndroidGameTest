#!/usr/bin/env python3
"""R32Q frozen SATComp2026 real original: prospective code, known formula.
SAT model check always on original sha; UNSAT not credited. Same one logical CPU.
"""
import hashlib,json,os,statistics,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"sat_native_r32q_results"
GBD="75429ff7acb5acb597abe01aa745c2a6"
SOURCE_SHA="243e5d0079606862166a4619691cbbb8ffc9c8c14eb16250138b16d724c6bc83"
CAP=5.0
ARMS=("NATIVE_DIRECT","X59_OFF","X59_ON","R28_GF2","Kissat")
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read_source(path):
    n=m=None;clauses=[];cur=[]
    for line in path.read_text().splitlines():
        ts=line.split()
        if not ts or ts[0] in ("c","%"):continue
        if ts[0]=="p":
            assert n is None and ts[1]=="cnf"
            n,m=map(int,ts[2:])
            continue
        for t in ts:
            v=int(t)
            if not v:clauses.append(cur);cur=[]
            else:cur.append(v)
    assert not cur and (n,m)==(250,1000) and len(clauses)==1000
    return n,clauses
def verify(n,clauses,output):
    d={}
    for l in output.splitlines():
        if not l.startswith("v "):continue
        for word in l[2:].split():
            v=int(word)
            if not v:continue
            if abs(v)>n or (abs(v) in d and d[abs(v)]!=(v>0)):
                return False
            d[abs(v)]=(v>0)
    if len(d)!=n:return False
    return all(any(d[abs(l)]==(l>0) for l in c) for c in clauses)
def command(arm,cnf):
    if arm=="NATIVE_DIRECT":
        return [str(ROOT/"build/drnas-sat-construct"),str(cnf),"--max-ms","25","--stats"]
    if arm.startswith("X59_"):
        cmd=[str(ROOT/"build/drnas-sat-native-x59"),str(cnf),"--mode","core",
             "--time",str(CAP),"--stats"]
        if arm=="X59_ON":cmd+=["--sat-construct-ms","25"]
        return cmd
    if arm=="R28_GF2":
        return [str(ROOT/"compiled/r28_gf2"),str(cnf),str(ROOT/"compiled/kissat")]
    if arm=="Kissat":return [str(ROOT/"compiled/kissat"),str(cnf)]
    raise ValueError(arm)
def run():
    OUT.mkdir(parents=True,exist_ok=True)
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    frozen=ROOT/"frozen"
    m=json.loads((frozen/"manifest.json").read_text())
    record=next(x for x in m["cases"] if x["gbd"]==GBD)
    source=frozen/record["name"]
    assert record["sha256"]==SOURCE_SHA and digest(source)==SOURCE_SHA
    n,clauses=read_source(source)
    rows=[]
    for rep in range(3):
        order=list(ARMS)
        order=order[rep%len(order):]+order[:rep%len(order)]
        for arm in order:
            start=time.perf_counter()
            try:
                proc=subprocess.run(command(arm,source),capture_output=True,
                    text=True,timeout=CAP+0.15,check=False)
                expired=False
            except subprocess.TimeoutExpired:proc=None;expired=True
            status="TIMEOUT" if expired else "UNKNOWN"
            meta={}
            if proc is not None:
                if proc.returncode==10:
                    if "s SATISFIABLE" not in proc.stdout or not verify(n,clauses,proc.stdout):
                        raise RuntimeError("INVALID ORIGINAL SAT MODEL "+arm)
                    status="SAT_VERIFIED"
                elif proc.returncode==20:raise RuntimeError("FALSE UNSAT on known SAT "+arm)
                elif proc.returncode not in (0,153):
                    raise RuntimeError("solver failed "+arm+" "+proc.stderr[-300:])
                for line in proc.stderr.splitlines():
                    if line.startswith("SAT_NATIVE_STATS ") or line.startswith("SAT_CONSTRUCT_STATS "):
                        try:meta.update(json.loads(line.split(" ",1)[1]))
                        except ValueError:pass
            elapsed=time.perf_counter()-start
            verified=status=="SAT_VERIFIED" and elapsed<=CAP
            rows.append(dict(rep=rep,arm=arm,status=status,verified=verified,
                e2e_s=round(elapsed,6),par2_s=round(elapsed if verified else 2*CAP,6),
                **meta))
    (OUT/"trials.json").write_text(json.dumps(rows,indent=2,sort_keys=True)+"\n")
    res={}
    for arm in ARMS:
        rr=[x for x in rows if x["arm"]==arm]
        res[arm]=dict(solved=sum(x["verified"] for x in rr),
              median_e2e_s=round(statistics.median(x["e2e_s"] for x in rr),6),
              par2_sum_s=round(sum(x["par2_s"] for x in rr),6),
              methods=sorted(set(x.get("method","") for x in rr)))
    (OUT/"protocol.json").write_text(json.dumps(dict(cpu=cpu,source_sha256=SOURCE_SHA,
        gbd=GBD,nvars=n,clauses=len(clauses),repetitions=3,cap_s=CAP,
        frozen_manifest_sha256=digest(frozen/"manifest.json"),
        binary_sha256={b:digest(ROOT/p) for b,p in {
           "native":"build/drnas-sat-construct","fused":"build/drnas-sat-native-x59",
           "r28":"compiled/r28_gf2","kissat":"compiled/kissat"}.items()},
        exact_source=True,one_logical_cpu=True,original_CNF_model_verification=True,
        source_previously_exposed=True,not_blind=True,unsat_not_accepted=True,
        git_sha=os.environ.get("GITHUB_SHA")),indent=2,sort_keys=True)+"\n")
    print("NATIVE_R32Q_RESULT "+json.dumps(dict(source_sha256=SOURCE_SHA,results=res),
          sort_keys=True),flush=True)
if __name__=="__main__":run()
