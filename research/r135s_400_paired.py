#!/usr/bin/env python3
"""R135 vs R135S on EXACT SAME existing R135 400 original SHA-frozen CNFs.

Retrospective paired replication (the 400 CNFs were already measured by R135).
DO NOT call this a new blind holdout. Each end-to-end 15s trial includes
detection, dispatch and solving, with 2 repeats on 8 native-CPU-pinned shards.
Compare R135S 128KiB/2000-clause C++ gate against original R135 8MiB/120k
Python gate AND clean pinned Kissat, CaDiCaL, R118 in the very same shard.
Never rewrite input, alter solver, tune thresholds or claim UNSAT certification.
"""
import argparse,hashlib,json,os,pathlib,random,sys,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r135_nonxor_portfolio as old
import r135s_run_nonxor as mini

ROOT=pathlib.Path("r135s400")
SOURCE=pathlib.Path("holdout-400")
PROTO="DRNAS-R135S-R135-EXACT-400-SOURCE-PAIRED-REPLICATION-20261105-v1"
OLD_PROTO="DRNAS-R135-FROZEN-NONXOR-BIG-HORN-PORTFOLIO-20261105-v1"
SOURCE_SHA="619665dd5f4ba6680b11200a63ac77ecc706c9897317b5452dbf22a82ef4b787"
CAP=15.0
SHARDS=8
REPS=2
MODES=("kissat","cadical","r118","r135","r135s")
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
CADICAL=pathlib.Path("built/bin/cadical_3_0_1")
R118=ROOT/"r118"
FILTER=ROOT/"r135_selector"

def need(v,reason):
    if not v:raise RuntimeError("R135S400_REFUSED "+str(reason))
def digest(p):
    h=hashlib.sha256()
    with pathlib.Path(p).open("rb") as f:
        for x in iter(lambda:f.read(1048576),b""):h.update(x)
    return h.hexdigest()
def write(path,record):
    path=pathlib.Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(record,sort_keys=True,indent=2)+"\n")
def setup():
    need(old.PROTO==OLD_PROTO,"original large R135 code drift")
    need(old.BINARY_THRESHOLD==0.30 and old.HORN_THRESHOLD==0.55,"R135 frozen gate drift")
    need(mini.CAP==15,"original mini cap drift")
    old.CAP=CAP
    mini.CAP=CAP
    old.KISSAT=mini.KISSAT=KISSAT
    old.CADICAL=mini.CADICAL=CADICAL
    old.R118=mini.R118=R118
    mini.FILTER=FILTER
    # The original R135 parser independently SHA-verifies all 400 source CNFs.
    source_sha,cases=old.read_sources()
    need(source_sha==SOURCE_SHA,"not the original R135 frozen 400 manifest SHA")
    need(len(cases)==400 and len({x["sha256"] for x in cases})==400,"missing/duplicate 400 sources")
    need(all(x["id"].startswith("r135/unpacked/") for x in cases),"original frozen source path drift")
    return source_sha,cases
def run(shard):
    need(0<=shard<SHARDS,"invalid shard")
    source_sha,cases=setup()
    for f in (KISSAT,CADICAL,R118,FILTER):
        need(f.is_file(),"missing pinned binary "+str(f))
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    bins={str(f):digest(f) for f in (KISSAT,CADICAL,R118,FILTER)}
    cpu=next((line for line in pathlib.Path("/proc/cpuinfo").read_text().splitlines()
              if line.startswith("model name")),"unknown")
    rows=[]
    for i,c in enumerate(cases):
        if i%SHARDS!=shard:continue
        src=pathlib.Path(c["id"])
        need(digest(src)==c["sha256"],"original CNF SHA mutated")
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(modes)
            votes=set()
            for mode in modes:
                if mode=="r135s":
                    result=mini.run_portfolio(src,rep)
                    result["mode"]="r135s"
                else:
                    result=old.invoke(src,mode,rep)
                row=dict(protocol=PROTO,source_manifest_sha256=source_sha,
                         shard=shard,id=c["id"],cohort=c["cohort"],
                         sha256=c["sha256"],**result)
                rows.append(row)
                if row["status"]!="TIMEOUT":
                    votes.add(row["status"])
                    need(len(votes)<=1,"SAT/UNSAT disagreement "+c["id"])
                print("R135S400_PAIRED",json.dumps(row,sort_keys=True),flush=True)
                write(ROOT/f"shard-{shard}.json",dict(protocol=PROTO,shard=shard,
                      source_manifest_sha256=source_sha,original_cnf_unchanged=True,
                      pinned_sha256=bins,runner_cpu=cpu,rows=rows))
    need(len(rows)==len(cases[shard::SHARDS])*REPS*len(MODES),"incomplete shard")
    print("R135S400_SHARD_PASS",shard,len(rows),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--shard",type=int,required=True)
    run(p.parse_args().shard)
