#!/usr/bin/env python3
"""Frozen XORBLIND1, paired and independently SAT-witness verified.
No tuning or source selection based on solver outcomes.
"""
import argparse,collections,hashlib,json,os,random,signal,statistics,subprocess,sys,time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
FROZEN=ROOT/"xor_hard2_inputs"
OUTPUT=ROOT/"xor_hard2_results"
CAP=2.0
REPS=2
SHARDS=6
FROZEN_SHA="0d9121da9d63312bd24e24e4cf2754bc0cf6ea6de50ba21b2597324a1d4f8514"
GENERATOR_SHA="f13f2b50d789327f8f186b23192acfde9952e7a16e6a20ba8eb832f8fbdf5658"
ARMS=("X59_OFF","X59_ON_25","X59_ON_100","Kissat","CaDiCaL","CryptoMiniSat")
REFERENCE_SHA={
 "build/kissat":"3f95aa678e181b46b248605dad02011b68580c68f230f0e29500ec8a9cb6c60d",
 "build/cadical":"4e453f276393e9689fe1484fa78c2b32a02e7bbd04c02c4b001f960bdebb3f2e",
 "build/cms":"00db7e59c634842acbfc6676bf0f5d30a3fdabbd0ec2fa17b20bb0bf683c7207",
}
def sha(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        while data:=f.read(1<<20):h.update(data)
    return h.hexdigest()
def manifest():
    m=FROZEN/"manifest.json"
    assert sha(m)==FROZEN_SHA,("unfrozen input manifest",sha(m))
    data=json.loads(m.read_text())
    assert data["generator_sha256"]==GENERATOR_SHA
    assert data["protocol"]=="DRNAS-XORHARD2-FROZEN-V1"
    assert data["source_count"]==60
    assert len(data["sources"])==60
    assert {r["id"] for r in data["sources"]}==set(range(60))
    assert len({r["sha256"] for r in data["sources"]})==100
    assert collections.Counter(r["family"] for r in data["sources"])=={
        f:10 for f in ("pure_xor3","pure_xor4","pure_xor5","pure_xor6",
                      "mixed_xor5","partial_xor3")}
    for r in data["sources"]:
        assert sha(ROOT/r["path"])==r["sha256"],("SOURCE_DRIFT",r["id"])
    return data
def verify_model(source,stdout):
    values={}
    for line in stdout.splitlines():
        if not line.startswith("v "):continue
        for word in line[2:].split():
            try:lit=int(word)
            except ValueError:return False
            if lit==0:continue
            if abs(lit) in values and values[abs(lit)]!=(lit>0):return False
            values[abs(lit)]=(lit>0)
    n=m=None;count=0;open_clause=False;satisfied=False
    with (ROOT/source["path"]).open() as f:
        for line in f:
            tokens=line.split()
            if not tokens or tokens[0] in ("c","%"):continue
            if tokens[0]=="p":
                if n is not None or len(tokens)!=4 or tokens[1]!="cnf":return False
                n,m=map(int,tokens[2:])
                if len(values)!=n:return False
                continue
            if n is None:return False
            for tok in tokens:
                try:lit=int(tok)
                except ValueError:return False
                if lit==0:
                    if not satisfied:return False
                    count+=1;open_clause=False;satisfied=False
                else:
                    if abs(lit)>n:return False
                    open_clause=True
                    satisfied=satisfied or values.get(abs(lit))==(lit>0)
    return n is not None and not open_clause and count==m
def command(arm,src):
    cnf=str(ROOT/src["path"])
    if arm.startswith("X59_"):
        cmd=[str(ROOT/"build/drnas-sat-native-x59"),cnf,
             "--mode","core","--time",str(CAP),"--stats"]
        if arm=="X59_ON_25":cmd+=["--sat-construct-ms","25"]
        if arm=="X59_ON_100":cmd+=["--sat-construct-ms","100"]
        return cmd
    if arm=="Kissat":return [str(ROOT/"build/kissat"),cnf]
    if arm=="CaDiCaL":return [str(ROOT/"build/cadical"),"-q","--no-binary",cnf]
    if arm=="CryptoMiniSat":return [str(ROOT/"build/cms"),"--threads=1","--verb=0",cnf]
    raise ValueError(arm)
def trial(src,arm,rep):
    cmd=command(arm,src)
    env=dict(os.environ,OMP_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1",MKL_NUM_THREADS="1")
    env["LD_LIBRARY_PATH"]=str(ROOT/"build/cms-libs/usr/lib/x86_64-linux-gnu")
    start=time.perf_counter()
    proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
          text=True,start_new_session=True,env=env)
    expired=False
    try:
        stdout,stderr=proc.communicate(timeout=CAP)
    except subprocess.TimeoutExpired:
        expired=True
        try:os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        stdout,stderr=proc.communicate()
    elapsed_proc=time.perf_counter()-start
    status="TIMEOUT" if expired else "UNKNOWN"
    verified=False;meta={}
    if not expired:
        if proc.returncode==10:
            if "s SATISFIABLE" not in stdout or not verify_model(src,stdout):
                raise RuntimeError(f"INVALID_SAT original id={src['id']} {arm}")
            verified=True;status="SAT_VERIFIED"
        elif proc.returncode==20:
            # The generated SAT source has a planted satisfying model.
            # A UNSAT output here is a critical correctness violation.
            raise RuntimeError(f"FALSE_UNSAT on constructed SAT input {src['id']} {arm}")
        elif proc.returncode in (0,153):
            status="UNKNOWN"
        else:
            raise RuntimeError(f"SOLVER_ERROR id={src['id']} {arm} rc={proc.returncode} {stderr[-450:]}")
        for line in stderr.splitlines():
            if line.startswith(("SAT_CONSTRUCT_STATS ","SAT_NATIVE_STATS ")):
                try:meta.update(json.loads(line.split(" ",1)[1]))
                except ValueError:pass
    elapsed=time.perf_counter()-start
    accepted=verified and elapsed<=CAP
    return dict(id=src["id"],family=src["family"],sha256=src["sha256"],
      arm=arm,rep=rep,status=status,accepted=accepted,
      solver_e2e_s=round(elapsed_proc,6),
      e2e_s=round(elapsed,6),PAR2_s=round(elapsed if accepted else 2*CAP,6),
      **meta)
def pinned_binaries():
    for name,expected in REFERENCE_SHA.items():
        assert sha(ROOT/name)==expected,("reference binary changed",name)
    for b in ("build/drnas-sat-native-x59","build/drnas-sat-construct"):
        assert (ROOT/b).is_file()
    return {name:sha(ROOT/name) for name in
        list(REFERENCE_SHA)+["build/drnas-sat-native-x59","build/drnas-sat-construct"]}
def shard(index):
    assert 0<=index<SHARDS
    srcs=manifest()["sources"]
    pins=pinned_binaries()
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    subset=[s for s in srcs if s["id"]%SHARDS==index]
    assert len(subset)==10
    out=OUTPUT/f"shard-{index}"
    out.mkdir(parents=True,exist_ok=False)
    records=[]
    began=time.perf_counter()
    for src in subset:
        for rep in range(REPS):
            arms=list(ARMS)
            rot=(src["id"]+rep)%len(arms)
            for arm in arms[rot:]+arms[:rot]:
                records.append(trial(src,arm,rep))
    assert len(records)==10*REPS*len(ARMS)
    assert len({(r["id"],r["rep"],r["arm"]) for r in records})==len(records)
    (out/"trials.jsonl").write_text("".join(json.dumps(r,sort_keys=True)+"\n" for r in records))
    (out/"meta.json").write_text(json.dumps(dict(protocol="XORHARD2-PINNED-V1",
      source_manifest_sha256=FROZEN_SHA,generator_sha256=GENERATOR_SHA,
      shard=index,source_ids=[x["id"] for x in subset],repetitions=REPS,cap_s=CAP,
      one_logical_cpu=cpu,source_count=len(subset),arms=ARMS,
      binary_hashes=pins,code_git_sha=os.environ.get("GITHUB_SHA"),
      constructed_sat=True,invalid_sat_is_fatal=True,unsat_is_fatal=True,
      checker_counts_in_cap=True),indent=2,sort_keys=True)+"\n")
    totals={arm:dict(solved=sum(r["accepted"] for r in records if r["arm"]==arm),
       par2_s=round(sum(r["PAR2_s"] for r in records if r["arm"]==arm),6))
       for arm in ARMS}
    print("XOR_HARD2_SHARD "+json.dumps(dict(index=index,sources=len(subset),
      trials=len(records),arms=totals,wall_s=round(time.perf_counter()-began,3)),
      sort_keys=True),flush=True)
def report():
    from collections import defaultdict
    srcs=manifest()["sources"]
    by_source={r["id"]:r for r in srcs}
    all_rows=[]
    for index in range(SHARDS):
        folder=OUTPUT/f"shard-{index}"
        meta=json.loads((folder/"meta.json").read_text())
        assert meta["source_manifest_sha256"]==FROZEN_SHA
        assert meta["repetitions"]==REPS and meta["cap_s"]==CAP
        rows=[json.loads(line) for line in (folder/"trials.jsonl").read_text().splitlines()]
        assert len(rows)==10*REPS*len(ARMS)
        all_rows.extend(rows)
    assert len(all_rows)==60*REPS*len(ARMS)
    key={(r["id"],r["rep"],r["arm"]) for r in all_rows}
    assert len(key)==len(all_rows)
    assert key=={(i,j,a) for i in range(60) for j in range(REPS) for a in ARMS}
    assert all(by_source[r["id"]]["sha256"]==r["sha256"] for r in all_rows)
    assert all(r["status"] in ("SAT_VERIFIED","UNKNOWN","TIMEOUT") for r in all_rows)
    summary={}
    for family in sorted({r["family"] for r in srcs})+["ALL"]:
        cohort=[r for r in all_rows if family=="ALL" or r["family"]==family]
        arms={}
        for arm in ARMS:
            rows=[r for r in cohort if r["arm"]==arm]
            arms[arm]=dict(solved=sum(r["accepted"] for r in rows),attempts=len(rows),
                par2_sum_s=round(sum(r["PAR2_s"] for r in rows),6),
                median_e2e_s=round(statistics.median(r["e2e_s"] for r in rows),6),
                recognized=collections.Counter(r.get("method","") for r in rows if r.get("found")))
        summary[family]=arms
    source_pairs=defaultdict(dict)
    for r in all_rows:
        source_pairs[r["id"]].setdefault(r["arm"],[]).append(r["PAR2_s"])
    deltas=[]
    wins=ties=losses=0
    for sid in sorted(source_pairs):
        row=source_pairs[sid]
        off=statistics.mean(row["X59_OFF"])
        on=statistics.mean(row["X59_ON_100"])
        delta=off-on;deltas.append(delta)
        if delta>0.0001:wins+=1
        elif delta< -0.0001:losses+=1
        else:ties+=1
    rng=random.Random(791926)
    bootstrap=[]
    for _ in range(1200):
        bootstrap.append(sum(deltas[rng.randrange(len(deltas))] for k in range(len(deltas))))
    bootstrap.sort()
    paired=dict(wins=wins,losses=losses,ties=ties,
      aggregate_PAR2_saving=sum(deltas),
      per_source_95pct_bootstrap_saving_CI=[bootstrap[30],bootstrap[1170]],
      bootstrap_trials=1200,
      method="resample source, preserving paired repetitions")
    final=dict(protocol="XORBLIND1-PINNED-V1",
       source_manifest_sha256=FROZEN_SHA,total_sources=60,total_trials=len(all_rows),
       reps=REPS,cap_s=CAP,synthetic_source_blind=True,not_original_official=True,
       arms=ARMS,summary=summary,paired=paired)
    OUTPUT.mkdir(exist_ok=True)
    (OUTPUT/"final.json").write_text(json.dumps(final,indent=2,sort_keys=True,default=dict)+"\n")
    (OUTPUT/"trials.jsonl").write_text("".join(json.dumps(r,sort_keys=True)+"\n" for r in all_rows))
    print("XOR_HARD2_FINAL "+json.dumps(dict(sources=60,trials=len(all_rows),
      total=summary["ALL"],paired=paired),sort_keys=True,default=dict),flush=True)
def main():
    p=argparse.ArgumentParser();p.add_argument("action",choices=("shard","report"))
    p.add_argument("--index",type=int)
    a=p.parse_args()
    if a.action=="shard":shard(a.index)
    else:report()
if __name__=="__main__":main()
