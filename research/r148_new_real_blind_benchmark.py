#!/usr/bin/env python3
"""R148 prospective blinded evaluation over frozen previously unmeasured real CNFs.

Identical fixed 15s wall-clock budget per solver, two paired repeats per CNF.
R148 original gate and reference solvers unchanged, SAT witnesses on original CNF.
No tuning or formula selection based on runtime.
"""
import argparse,hashlib,json,os,pathlib,random,statistics,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r148_exact_fast_benchmark as r
ROOT=pathlib.Path("r148blind")
SOURCE=ROOT/"frozen"
PROTO="DRNAS-R148-NEW-REAL-BLIND-FIVEWAY-20261105-v1"
FREEZE_PROTO="DRNAS-R148-REAL-50-PROSPECTIVE-SHA-URL-EXCLUDED-20261105-v1"
CAP=15.0;REPS=2;SHARDS=8
MODES=("kissat","cadical","r118","r135","r148")
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
CADICAL=pathlib.Path("built/bin/cadical_3_0_1")
R118=ROOT/"r118"
FILTER=ROOT/"r148_selector"
def need(x,why):
    if not x:raise RuntimeError("R148_NEW_BLIND_REFUSED "+str(why))
def sha(p):
    h=hashlib.sha256()
    with pathlib.Path(p).open("rb") as f:
        for b in iter(lambda:f.read(1048576),b""):h.update(b)
    return h.hexdigest()
def write(path,x):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(x,indent=2,sort_keys=True)+"\n")
def setup():
    mpath=SOURCE/"manifest.json"
    need(mpath.is_file(),"immutable holdout manifest missing")
    m=json.loads(mpath.read_text())
    need(m["protocol"]==FREEZE_PROTO and m["phase"]=="FROZEN_BEFORE_FIRST_SOLVER_TIMING","wrong source protocol")
    cs=m["cases"]
    need(m["no_speed_or_solve_outcome_selection"] and m["pilot_and_original_400_not_reused"],
         "source provenance not independently frozen")
    need(36<=len(cs)<=50 and len({c["sha256"] for c in cs})==len(cs),"wrong unique CNF count")
    r.FILTER=FILTER;r.KISSAT=KISSAT;r.CADICAL=CADICAL;r.CAP=CAP
    r.old.KISSAT=KISSAT;r.old.CADICAL=CADICAL;r.old.R118=R118;r.old.CAP=CAP
    need(r.old.BINARY_THRESHOLD==0.30 and r.old.HORN_THRESHOLD==0.55,"R135 rule drift")
    for c in cs:
        src=SOURCE/c["id"]
        need(src.is_file() and sha(src)==c["sha256"],"frozen original CNF SHA mismatch")
        need(c["bytes"]==src.stat().st_size,"original CNF size drift")
    return sha(mpath),cs,m
def run(shard):
    need(0<=shard<SHARDS,"invalid shard")
    manifest_sha,cs,m=setup()
    for f in (FILTER,KISSAT,CADICAL,R118):
        need(f.is_file(),"missing pinned R148 or solver binary "+str(f))
    if hasattr(os,"sched_getaffinity"):
        cpu_set=os.sched_getaffinity(0);os.sched_setaffinity(0,{min(cpu_set)})
    cpu=next((x for x in pathlib.Path("/proc/cpuinfo").read_text().splitlines()
              if x.startswith("model name")),"unknown")
    pins={str(f):sha(f) for f in (FILTER,KISSAT,CADICAL,R118)}
    rows=[]
    for i,c in enumerate(cs):
        if i%SHARDS!=shard:continue
        src=SOURCE/c["id"]
        # Required invariant: R148 native route == independently computed frozen R135 policy.
        old_target,*_=r.old.choose(src)
        new_route,_=r.native(src)
        need(new_route["route"]==old_target.upper(),"native R148 is NOT equivalent on unseen source "+c["sha256"])
        for rep in range(REPS):
            order=list(MODES)
            random.Random(PROTO+"|"+c["sha256"]+"|"+str(rep)).shuffle(order)
            votes=set()
            for mode in order:
                result=r.run_one(src,mode,rep)
                row=dict(protocol=PROTO,source_manifest_sha256=manifest_sha,
                         id=c["id"],cohort=c["cohort"],sha256=c["sha256"],
                         shard=shard,**result)
                rows.append(row)
                if row["status"]!="TIMEOUT":
                    votes.add(row["status"])
                    need(len(votes)<=1,"SAT/UNSAT contradiction on original "+c["sha256"])
                print("R148_BLIND_PAIRED",json.dumps(row,sort_keys=True),flush=True)
                write(ROOT/f"shard-{shard}.json",dict(protocol=PROTO,shard=shard,
                    manifest_sha256=manifest_sha,pinned_sha256=pins,runner_cpu=cpu,rows=rows))
    need(len(rows)==len(cs[shard::SHARDS])*REPS*len(MODES),"incomplete shard")
    print("R148_BLIND_SHARD_PASS",shard,len(rows),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--shard",type=int,required=True)
    run(p.parse_args().shard)
