#!/usr/bin/env python3
"""R135 original-CNF paired 15s benchmark; detector and dispatch wall included."""
import argparse,hashlib,json,os,pathlib,random,re,subprocess,time
import r132_wide_xor_benchmark as r132
import r128_xor_threshold_benchmark as base
ROOT=pathlib.Path("r135")
SOURCES=ROOT/"frozen"
FILTER=ROOT/"r135_selector"
R118=ROOT/"r118"
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
CADICAL=pathlib.Path("built/bin/cadical_3_0_1")
PROTO="DRNAS-R135-FROZEN-NONXOR-PORTFOLIO-20261105-v1"
MODES=("kissat","cadical","r118","r135")
CAP=15
REPS=2
SHARDS=8
def need(v,msg):
    if not v:raise RuntimeError("R135_BENCH_REFUSED "+str(msg))
def sha(p):
    h=hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda:f.read(1048576),b""):h.update(block)
    return h.hexdigest()
def selected():
    r132.ROOT=ROOT
    r132.SOURCES=SOURCES
    r132.PROTO=PROTO
    return r132.cases()
def probe(src):
    st=time.perf_counter()
    p=subprocess.run([str(FILTER.resolve()),str(src)],text=True,capture_output=True,timeout=2)
    need(p.returncode==0,"R135 selector failure "+p.stderr[-300:])
    line=next((v for v in p.stdout.splitlines() if v.startswith("c R135_SELECTOR ")),None)
    need(line is not None,"missing R135 selector telemetry")
    fields=dict(re.findall(r"([a-z_]+)=([^\s]+)",line))
    need(fields.get("route") in ("CADICAL","KISSAT"),"invalid selector route")
    return dict(route=fields["route"],reason=fields["reason"],
        binary_fraction=float(fields["binary_fraction"]),
        horn_fraction=float(fields["horn_fraction"]),
        observed_clauses=int(fields["observed"]),
        prefix_limited=bool(int(fields["prefix"])),
        probe_s=round(time.perf_counter()-st,6))
def run_portfolio(src,rep):
    start=time.perf_counter()
    p=probe(src)
    status="TIMEOUT";proof="timeout";elapsed=time.perf_counter()-start
    if elapsed<CAP:
        binary=CADICAL if p["route"]=="CADICAL" else KISSAT
        try:
            solver=subprocess.run([str(binary.resolve()),str(src)],
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=CAP-elapsed)
            elapsed=time.perf_counter()-start
            need(solver.returncode in (10,20),"selected solver failed "+
                 str(solver.returncode)+" "+solver.stderr[-300:].decode(errors="replace"))
            if elapsed<CAP:
                status="SAT" if solver.returncode==10 else "UNSAT"
                if status=="SAT":
                    r132.witness.check_original_sat(solver.stdout,src)
                    proof="source_SAT_witness_verified"
                else:proof="UNSAT_without_independent_LRAT_proof"
        except subprocess.TimeoutExpired:elapsed=CAP
    elapsed=min(CAP,elapsed)
    return dict(mode="r135",repeat=rep,status=status,seconds=round(elapsed,6),
        par2=30.0 if status=="TIMEOUT" else round(elapsed,6),
        proof=proof,route=p["route"],selected_R118=False,GF2_solved=False,
        detector_s=p["probe_s"],binary_fraction=p["binary_fraction"],
        horn_fraction=p["horn_fraction"],detector_reason=p["reason"],
        observed_clauses=p["observed_clauses"],prefix_limited=p["prefix_limited"])
def execute(shard):
    need(0<=shard<SHARDS,"invalid shard")
    cases=selected()
    for f in (FILTER,R118,KISSAT,CADICAL):need(f.is_file(),"missing binary "+str(f))
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    base.R118=R118.resolve()
    base.KISSAT=KISSAT.resolve()
    base.CAP=CAP
    r132.CADICAL=CADICAL.resolve()
    r132.CAP=CAP
    ROOT.mkdir(exist_ok=True)
    rows=[];probes=[]
    for i,c in enumerate(cases):
        if i%SHARDS!=shard:continue
        src=SOURCES/c["id"]
        probes.append(dict(id=c["id"],cohort=c["cohort"],sha256=c["sha256"],**probe(src)))
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(modes)
            votes=set()
            for mode in modes:
                if mode=="r135":x=run_portfolio(src,rep)
                elif mode=="cadical":x=r132.run_cadical(src,rep)
                else:x=base.run_one(src,mode,rep,"holdout")
                row=dict(protocol=PROTO,shard=shard,id=c["id"],cohort=c["cohort"],sha256=c["sha256"],**x)
                rows.append(row)
                if row["status"]!="TIMEOUT":
                    votes.add(row["status"])
                    need(len(votes)<=1,"SAT/UNSAT disagreement "+c["id"])
                print("R135_PAIRED_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==len(cases[shard::SHARDS])*REPS*len(MODES),"missing shard trials")
    cpu=next((x for x in pathlib.Path("/proc/cpuinfo").read_text().splitlines() if x.startswith("model name")),"unknown")
    pins={str(f):sha(f) for f in (FILTER,R118,KISSAT,CADICAL)}
    data=dict(protocol=PROTO,shard=shard,source_manifest_sha256=sha(SOURCES/"manifest.json"),
        binary_sha256=pins,runner_cpu=cpu,rows=rows,probes=probes)
    (ROOT/f"shard-{shard}.json").write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
    print("R135_SHARD_COMPLETE",shard,len(rows),len(probes),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--shard",type=int,required=True)
    execute(p.parse_args().shard)
