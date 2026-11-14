#!/usr/bin/env python3
"""Source-pinned, diagnostic-only experiment on SAT2024 REAL100 ids 44 and 64.

No training, no solver modifications, no new heuristics, and no promotion.
Original source sha256 is checked before EVERY trial. Each solver gets one
logical CPU and runs serially. Accepted SAT needs its full original witness;
accepted UNSAT needs independent DRAT verification.
"""
import collections
import hashlib
import json
import os
import pathlib
import random
import resource
import signal
import statistics
import subprocess
import sys
import tempfile
import time

ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"research"))
import drnas_clause_cf7_real100 as CF

DEST=ROOT/"diagnostic_44_64"
ARMS=("X5_NO_MIN","CF5_BASE","CF7_B2L_32","Kissat","CaDiCaL")
BINS={"X5_NO_MIN":"build/drnas-x5","CF5_BASE":"build/drnas-clause-cf5",
      "CF7_B2L_32":"build/drnas-clause-cf6",
      "Kissat":"build/kissat","CaDiCaL":"build/cadical"}
FOCUS={44:"pcmax-scheduling",64:"worker"}
EXPECTED={
  44:"c55ab8fe2c9e10f0579f806802bc32d04913f12cd6ce28e6662b8d59d114c174",
  64:"fc529dff1a6f763c97b0ed1dd33199e0d9dd26c50d210f9032e4fdaab5534c16"}
CHECKER=ROOT/"build/drat-trim"

def emit(k,obj):
    print(k+" "+json.dumps(obj,sort_keys=True),flush=True)

def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for block in iter(lambda:f.read(1<<20),b""):h.update(block)
    return h.hexdigest()

def pick_sources():
    manifest=json.loads((ROOT/"cf7/manifest.json").read_text())
    assert manifest["protocol"]=="CF7-FIVE-ARM-REAL100-V1"
    assert manifest["cap_s"]==8.0 and manifest["count"]==100
    indexed={x["id"]:x for x in manifest["sources"]}
    assert len(indexed)==100
    for ident,tag in FOCUS.items():
        src=indexed[ident]
        assert tag in src["normalized_name_family"].lower(),(ident,src["normalized_name_family"])
        assert src["sha256"]==EXPECTED[ident],("PINNED_SOURCE_MISMATCH",ident)
        path=ROOT/src["path"]
        assert path.is_file() and sha(path)==EXPECTED[ident],("SOURCE_BYTES_CHANGED",ident)
    return indexed

def structure(src):
    path=ROOT/src["path"]
    assert sha(path)==src["sha256"]
    header=None
    degrees_pos=collections.Counter()
    degrees_neg=collections.Counter()
    lengths=collections.Counter()
    literal_count=clauses=horn=unit=0
    current=[]
    for raw in path.open("r",encoding="ascii",errors="replace"):
        line=raw.strip()
        if not line or line.startswith("c") or line.startswith("%"):continue
        if line.startswith("p "):
            parts=line.split()
            assert len(parts)>=4 and parts[1]=="cnf"
            header=(int(parts[2]),int(parts[3]))
            continue
        for tok in line.split():
            v=int(tok)
            if v==0:
                clen=len(current)
                clauses+=1
                lengths[clen]+=1
                literal_count+=clen
                horn+=sum(x>0 for x in current)<=1
                unit+=clen==1
                for x in current:
                    if x>0:degrees_pos[x]+=1
                    else:degrees_neg[-x]+=1
                current=[]
            else:current.append(v)
    assert header and not current and clauses==header[1],("DIMACS_COUNT",src["id"],clauses,header)
    all_vars=set(degrees_pos)|set(degrees_neg)
    deg=sorted((degrees_pos[v]+degrees_neg[v] for v in all_vars))
    q=lambda frac:deg[min(len(deg)-1,int(frac*(len(deg)-1)))] if deg else 0
    return {"id":src["id"],"family":src["normalized_name_family"],
            "sha256":src["sha256"],"vars_declared":header[0],"vars_used":len(all_vars),
            "clauses":clauses,"literals":literal_count,"units":unit,
            "binary":lengths[2],"ternary":lengths[3],"length_4plus":sum(v for k,v in lengths.items() if k>=4),
            "max_clause_length":max(lengths,default=0),
            "mean_clause_length":round(literal_count/max(1,clauses),3),
            "horn_fraction":round(horn/max(1,clauses),5),
            "pure_variables":sum((degrees_pos[v]==0) != (degrees_neg[v]==0) for v in all_vars),
            "degree_p50":q(.5),"degree_p90":q(.9),"degree_p99":q(.99),"max_degree":q(1),
            "size_bytes":path.stat().st_size}

def command(arm,cnf,proof,cap):
    exe=str(ROOT/BINS[arm])
    if arm=="Kissat":return [exe,str(cnf),str(proof)]
    if arm=="CaDiCaL":return [exe,"-q","--no-binary",str(cnf),str(proof)]
    out=[exe,str(cnf),"--mode","core","--time",str(max(.1,cap-.12)),
         "--x5-no-minimize","--proof",str(proof),"--stats"]
    if arm in ("CF5_BASE","CF7_B2L_32"):
        out+=["--x5-no-retain","--cf5-policy","B2L_32" if arm=="CF7_B2L_32" else "BASE"]
    return out

def parse_stats(text):
    result={}
    for label in ("X41_STATS","X5_STATS","CLCF5_STATS","CLCF6_STATS"):
        for line in text.splitlines():
            if line.startswith(label+" "):
                try:result[label]=json.loads(line[len(label)+1:])
                except json.JSONDecodeError:raise RuntimeError(("INVALID_TELEMETRY",label,line[:200]))
                break
    return result

def trial(src,arm,cap,rep):
    assert sha(ROOT/src["path"])==src["sha256"]
    with tempfile.TemporaryDirectory(prefix="drnas-44-64-") as t:
        proof=pathlib.Path(t)/"proof.drat"
        cnf=(ROOT/src["path"]).resolve()
        cmd=command(arm,cnf,proof,cap)
        def limit():
            resource.setrlimit(resource.RLIMIT_FSIZE,(512*1024*1024,512*1024*1024))
        started=time.perf_counter()
        p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           text=True,start_new_session=True,preexec_fn=limit)
        killed=False
        try:stdout,stderr=p.communicate(timeout=cap+.3)
        except subprocess.TimeoutExpired:
            killed=True
            os.killpg(p.pid,signal.SIGKILL)
            stdout,stderr=p.communicate()
        elapsed=time.perf_counter()-started
        code=p.returncode
        if not killed and code not in (0,10,20,124,153):
            raise RuntimeError(("SOLVER_ERROR",arm,src["id"],code,stderr[-600:]))
        stats=parse_stats(stderr)
        status="UNKNOWN"
        verified=False
        if not killed and code==10:
            verified=CF.DATA.sat_witness_valid(cnf,CF.DATA.nvars(cnf),stdout)
            if not verified:raise RuntimeError(("INVALID_SAT_WITNESS",src["id"],arm))
            status="SAT_VERIFIED"
        elif not killed and code==20:
            status="UNSAT_UNVERIFIED"
            if proof.is_file() and proof.stat().st_size:
                try:
                    chk=subprocess.run([str(CHECKER),str(cnf),str(proof)],
                                       capture_output=True,text=True,timeout=120)
                    verified=chk.returncode==0 and "s VERIFIED" in chk.stdout
                except subprocess.TimeoutExpired:pass
            if verified:status="UNSAT_CERTIFIED"
        elif killed:status="TIMEOUT"
        elif code==153:status="PROOF_LIMIT"
        accepted=verified and elapsed<=cap
        row={"id":src["id"],"family":src["normalized_name_family"],
            "sha256":src["sha256"],"arm":arm,"cap_s":cap,"rep":rep,
            "status":status,"accepted":accepted,
            "elapsed_e2e_s":round(elapsed,6),
            "PAR2_verified_s":round(elapsed if accepted else 2*cap,6),
            "proof_bytes":proof.stat().st_size if proof.is_file() else 0,
            "telemetry":stats}
        emit("FOCUS_TRIAL",{k:v for k,v in row.items() if k!="telemetry"}|
             {"stats":stats.get("X41_STATS"),"cf5":stats.get("CLCF5_STATS"),
              "cf6":stats.get("CLCF6_STATS")})
        return row

def run():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    assert len(os.sched_getaffinity(0))==1
    DEST.mkdir(exist_ok=True)
    sources=pick_sources()
    for p in list(BINS.values())+["build/drat-trim"]:
        assert (ROOT/p).is_file(),("MISSING_BINARY",p)
    identities={arm:sha(ROOT/p) for arm,p in BINS.items()}
    profiles={str(i):structure(sources[i]) for i in sorted(FOCUS)}
    (DEST/"source_profiles.json").write_text(json.dumps(profiles,indent=2,sort_keys=True)+"\n")
    emit("FOCUS_SOURCE_PROFILES",profiles)
    rows=[]
    with (DEST/"trials.jsonl").open("w") as f:
        # Many short repetitions expose OS/process-start noise on worker #64.
        for rep in range(25):
            order=list(ARMS)
            random.Random(64000+rep).shuffle(order)
            for arm in order:
                row=trial(sources[64],arm,2.,rep)
                rows.append(row);f.write(json.dumps(row,sort_keys=True)+"\n");f.flush()
        # Progress profiles on hard UNSAT #44. No success expected or assumed.
        for cap in (0.5,2.,8.):
            order=list(ARMS)
            random.Random(44000+int(cap*10)).shuffle(order)
            for arm in order:
                row=trial(sources[44],arm,cap,0)
                rows.append(row);f.write(json.dumps(row,sort_keys=True)+"\n");f.flush()
        # A single longer diagnostic on the most informative engines.
        for arm in ("X5_NO_MIN","CF7_B2L_32","Kissat"):
            row=trial(sources[44],arm,20.,1)
            rows.append(row);f.write(json.dumps(row,sort_keys=True)+"\n");f.flush()
    assert len(rows)==143,(len(rows))
    report={"protocol":"FOCUS44-64-DIAGNOSTIC-V1",
       "source_sha256":EXPECTED,"original_manifest_run":43613581688,
       "one_logical_cpu":True,"blind_holdout":False,"no_promotion":True,
       "build_sha256":identities,"profiles":profiles,
       "worker_64":{},"pcmax_44":[],"trials":len(rows)}
    for arm in ARMS:
        a=[r for r in rows if r["id"]==64 and r["arm"]==arm]
        assert len(a)==25
        accepted=[r["elapsed_e2e_s"] for r in a if r["accepted"]]
        reduce=[r["telemetry"].get("CLCF5_STATS",{}) for r in a]
        cf6=[r["telemetry"].get("CLCF6_STATS",{}) for r in a]
        report["worker_64"][arm]={
           "verified":len(accepted),"median_verified_s":round(statistics.median(accepted),7) if accepted else None,
           "min_s":round(min(accepted),7) if accepted else None,
           "max_s":round(max(accepted),7) if accepted else None,
           "first_reduction_triggered":sum(bool(x.get("first_effective_reduce")) for x in reduce),
           "cf7_total_actual_swaps":sum(x.get("actual_swaps",0) for x in cf6),
           "median_conflicts":statistics.median([r["telemetry"].get("X41_STATS",{}).get("conflicts",0) for r in a]) if arm not in ("Kissat","CaDiCaL") else None}
    for row in rows:
        if row["id"]!=44:continue
        stats=row["telemetry"].get("X41_STATS",{})
        red=row["telemetry"].get("CLCF5_STATS",{})
        swap=row["telemetry"].get("CLCF6_STATS",{})
        report["pcmax_44"].append({
           "arm":row["arm"],"cap_s":row["cap_s"],
           "status":row["status"],"accepted":row["accepted"],
           "elapsed_e2e_s":row["elapsed_e2e_s"],
           "proof_bytes":row["proof_bytes"],"conflicts":stats.get("conflicts"),
           "decisions":stats.get("decisions"),"propagations":stats.get("propagations"),
           "restarts":stats.get("restarts"),"reduce_removed":stats.get("reduce_removed"),
           "first_reduction_triggered":red.get("first_effective_reduce"),
           "first_reduce_conflicts":red.get("first_reduce_conflicts"),
           "actual_swaps":swap.get("actual_swaps")})
    (DEST/"report.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    emit("FOCUS_FINAL",{"status":"COMPLETE","trials":len(rows),"worker":report["worker_64"],
                       "pcmax":report["pcmax_44"]})
if __name__=="__main__":
    run()
