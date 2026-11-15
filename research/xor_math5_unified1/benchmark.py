#!/usr/bin/env python3
"""Unseen, SHA-frozen XORHARD2 SAT regression for experimental MATH5 integration.
Reuses frozen XORHARD2 sources, no source reselection and no tuning.
This does not measure MATH5 UNSAT benefit; the proof test does that separately.
"""
import argparse
import collections
import hashlib
import json
import os
import random
import signal
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"research/xor_hard2"))
import benchmark as base
RESULTS=ROOT/"xor_math5_unified1_results"
ARMS=("X59_OFF","X59_ON_25","X59_ON_25_MATH5_100",
      "Kissat","CaDiCaL","CryptoMiniSat")
REPS=2
CAP=2.0
SHARDS=6
FROZEN_SHA=base.FROZEN_SHA

def trial(src,arm,rep):
    if arm=="X59_ON_25_MATH5_100":
        with tempfile.TemporaryDirectory(prefix="math5-unified-") as tmp:
            proof=Path(tmp)/"math5.json"
            cmd=[str(ROOT/"build/drnas-x59-xor-math5-unified1"),
                 str(ROOT/src["path"]),"--mode","core","--time",str(CAP),
                 "--sat-construct-ms","25","--math5-ms","100",
                 "--math5-certificate",str(proof),"--stats"]
            return invoke(src,arm,rep,cmd,proof)
    return invoke(src,arm,rep,base.command(arm,src),None)

def invoke(src,arm,rep,cmd,custom):
    env=dict(os.environ,OMP_NUM_THREADS="1",OPENBLAS_NUM_THREADS="1",MKL_NUM_THREADS="1")
    env["LD_LIBRARY_PATH"]=str(ROOT/"build/cms-libs/usr/lib/x86_64-linux-gnu")
    started=time.perf_counter()
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
    solver_e2e=time.perf_counter()-started
    status="TIMEOUT" if expired else "UNKNOWN"
    accepted=False
    meta={}
    if not expired:
        if proc.returncode==10:
            if "s SATISFIABLE" not in stdout or not base.verify_model(src,stdout):
                raise RuntimeError(f"INVALID_SAT {src['id']} {arm}")
            status="SAT_VERIFIED"
            accepted=True
        elif proc.returncode==20:
            raise RuntimeError(f"FALSE_UNSAT on planted SAT source {src['id']} {arm}")
        elif proc.returncode not in (0,153):
            raise RuntimeError(f"SOLVER_ERROR {src['id']} {arm} rc={proc.returncode} {stderr[-900:]}")
        if custom is not None and custom.exists():
            raise RuntimeError(f"Unexpected custom UNSAT proof on SAT source {src['id']}")
        for line in stderr.splitlines():
            if line.startswith(("SAT_CONSTRUCT_STATS ","MATH5_UNIFIED_STATS ")):
                try:meta[line.split(" ",1)[0]]=json.loads(line.split(" ",1)[1])
                except ValueError:raise RuntimeError("BAD_STATS_JSON")
    elapsed=time.perf_counter()-started
    accepted=accepted and elapsed<=CAP
    return dict(id=src["id"],family=src["family"],sha256=src["sha256"],
        arm=arm,rep=rep,status=status,accepted=accepted,
        solver_e2e_s=round(solver_e2e,6),e2e_s=round(elapsed,6),
        PAR2_s=round(elapsed if accepted else 2*CAP,6),meta=meta)

def freeze():
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    srcs=base.manifest()["sources"]
    pins=base.pinned_binaries()
    h=hashlib.sha256((ROOT/"build/drnas-x59-xor-math5-unified1").read_bytes()).hexdigest()
    return srcs,dict(source_manifest_sha256=FROZEN_SHA,
       source_count=len(srcs),repetitions=REPS,cap_s=CAP,
       arms=ARMS,one_logical_cpu=cpu,
       code_git_sha=os.environ.get("GITHUB_SHA"),
       baseline_hashes=pins,combined_binary_sha256=h,
       data_class="frozen synthetic SAT XOR only; no UNSAT claim",
       no_tuning=True)

def shard(idx):
    assert 0<=idx<SHARDS
    srcs,proto=freeze()
    rows=[]
    subset=[s for s in srcs if s["id"]%SHARDS==idx]
    assert len(subset)==10
    out=RESULTS/f"shard-{idx}"
    out.mkdir(parents=True,exist_ok=False)
    for s in subset:
        for rep in range(REPS):
            ordered=list(ARMS)
            k=(s["id"]+rep)%len(ARMS)
            for arm in ordered[k:]+ordered[:k]:
                rows.append(trial(s,arm,rep))
    assert len(rows)==120
    (out/"trials.jsonl").write_text("".join(json.dumps(r,sort_keys=True)+"\n" for r in rows))
    (out/"meta.json").write_text(json.dumps(dict(proto,shard=idx),sort_keys=True,indent=2)+"\n")
    print("XOR_MATH5_UNIFIED_SHARD "+json.dumps(dict(index=idx,source_count=len(subset),
       attempts=len(rows),summary={arm:dict(solved=sum(r["accepted"] for r in rows if r["arm"]==arm),
        par2_sum_s=round(sum(r["PAR2_s"] for r in rows if r["arm"]==arm),6))
       for arm in ARMS}),sort_keys=True),flush=True)

def report():
    srcs=base.manifest()["sources"]
    rows=[]
    for idx in range(SHARDS):
        out=RESULTS/f"shard-{idx}"
        meta=json.loads((out/"meta.json").read_text())
        assert meta["source_manifest_sha256"]==FROZEN_SHA
        assert meta["cap_s"]==CAP and meta["repetitions"]==REPS
        rows.extend(json.loads(x) for x in (out/"trials.jsonl").read_text().splitlines())
    assert len(rows)==60*REPS*len(ARMS)
    assert len({(r["id"],r["rep"],r["arm"]) for r in rows})==len(rows)
    assert {(r["id"],r["rep"],r["arm"]) for r in rows}=={
        (i,j,a) for i in range(60) for j in range(REPS) for a in ARMS}
    lookup={r["id"]:r for r in srcs}
    assert all(r["sha256"]==lookup[r["id"]]["sha256"] for r in rows)
    summary={}
    for family in sorted({s["family"] for s in srcs})+["ALL"]:
        f=[r for r in rows if family=="ALL" or r["family"]==family]
        summary[family]={arm:dict(solved=sum(r["accepted"] for r in f if r["arm"]==arm),
            attempts=len([r for r in f if r["arm"]==arm]),
            par2_sum_s=round(sum(r["PAR2_s"] for r in f if r["arm"]==arm),6))
            for arm in ARMS}
    pair=[]
    for sid in range(60):
        a=statistics.mean(r["PAR2_s"] for r in rows
                          if r["id"]==sid and r["arm"]=="X59_ON_25")
        b=statistics.mean(r["PAR2_s"] for r in rows
                          if r["id"]==sid and r["arm"]=="X59_ON_25_MATH5_100")
        pair.append(a-b)
    rng=random.Random(20261115)
    boots=sorted(sum(pair[rng.randrange(60)] for _ in range(60)) for _ in range(1200))
    stats=dict(wins=sum(x>0.0001 for x in pair),
               losses=sum(x<-0.0001 for x in pair),
               ties=sum(abs(x)<=0.0001 for x in pair),
               par2_delta_s=sum(pair),source_resampled_CI95_s=[boots[30],boots[1170]])
    final=dict(total_trials=len(rows),source_count=60,source_manifest_sha256=FROZEN_SHA,
       synthetic_sat_only=True,not_official_original=True,summary=summary,paired=stats)
    RESULTS.mkdir(exist_ok=True)
    (RESULTS/"final.json").write_text(json.dumps(final,indent=2,sort_keys=True)+"\n")
    (RESULTS/"trials.jsonl").write_text("".join(json.dumps(r,sort_keys=True)+"\n" for r in rows))
    print("XOR_MATH5_UNIFIED_FINAL "+json.dumps(dict(trials=len(rows),
          total=summary["ALL"],paired=stats),sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("action",choices=("shard","report"))
    p.add_argument("--index",type=int);a=p.parse_args()
    if a.action=="shard":shard(a.index)
    else:report()
