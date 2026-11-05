#!/usr/bin/env python3
"""R129 exploratory, NON-BLIND pilot on already-seen R128 holdout sources.

Do not promote from this dataset: R128 outcomes were already inspected.
Runs original pinned Kissat, CaDiCaL 3.0.1, R118 and two non-frozen
bounded XOR scanner thresholds in paired order. Original CNF stays immutable.
"""
import argparse, collections, csv, hashlib, json, os, pathlib, random, re, statistics, subprocess, sys, time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r128_xor_threshold_benchmark as base
import r127_early_xor_benchmark as witness

ROOT=pathlib.Path("r129")
SOURCES=pathlib.Path("r128/holdout")
MODES=("kissat","cadical","r118","q2_25","q1_0")
FILTER=ROOT/"r129_filter"
R118=ROOT/"r118"
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
CADICAL=pathlib.Path("built/bin/cadical_3_0_1")
CAP=15
SHARDS=4
REPS=2
PROTO="DRNAS-R129-BOUNDED-XOR-EXPLORATORY-REUSED-R128-20261105"

def need(v,msg):
    if not v:raise RuntimeError("R129_AUDIT_REFUSED "+str(msg))
def digest(p):
    h=hashlib.sha256()
    with pathlib.Path(p).open("rb") as f:
        for block in iter(lambda:f.read(1048576),b""):h.update(block)
    return h.hexdigest()
def write(p,x):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,indent=2,sort_keys=True)+"\n")
def cases():
    m=json.loads((SOURCES/"manifest.json").read_text())
    need(m["protocol"]==base.PROTO,"unexpected frozen R128 manifest protocol")
    cs=base.verify_source(m,SOURCES)
    need(len(cs)==26,"expected all 26 R128 original formulas")
    need(len({x["sha256"] for x in cs})==len(cs),"duplicate SHA")
    return cs

def probe(src,policy):
    st=time.perf_counter()
    p=subprocess.run([str(FILTER.resolve()),str(src),str(R118),str(KISSAT),policy,"--probe-only"],
        text=True,capture_output=True,timeout=6)
    need(p.returncode==0,"probe failed "+str(p.stderr)[:400])
    line=next((v for v in p.stdout.splitlines() if v.startswith("c R128_PREFILTER policy=")),None)
    need(line is not None,"missing R129 prefilter telemetry")
    fields=dict(re.findall(r"([a-z_]+)=([^\s]+)",line))
    need(fields.get("policy")==policy,"unexpected policy telemetry")
    return dict(policy=policy,route=fields.get("route"),reason=fields.get("reason"),
        bytes=int(fields["bytes"]),clauses=int(fields["clauses"]),
        xor_equations=int(fields["xor_equations"]),covered_clauses=int(fields["covered_clauses"]),
        parsed=int(fields["parsed"]),probe_s=round(time.perf_counter()-st,6))

def run_cadical(src,rep):
    start=time.perf_counter()
    try:
        p=subprocess.run([str(CADICAL.resolve()),str(src)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=CAP)
        elapsed=time.perf_counter()-start
        need(p.returncode in (10,20),"CaDiCaL failure "+str(p.returncode)+" "+p.stderr[-200:].decode(errors="replace"))
        status="SAT" if p.returncode==10 else "UNSAT"
        if elapsed>=CAP: status="TIMEOUT"
        proof="timeout"
        if status=="SAT":
            witness.check_original_sat(p.stdout,src)
            proof="source_SAT_witness_verified"
        elif status=="UNSAT":proof="UNSAT_without_independent_LRAT_proof"
    except subprocess.TimeoutExpired:
        elapsed=CAP;status="TIMEOUT";proof="timeout"
    return dict(mode="cadical",repeat=rep,status=status,
                seconds=round(min(elapsed,CAP),6),par2=30.0 if status=="TIMEOUT" else round(elapsed,6),
                proof=proof,route="CaDiCaL_direct",selected_R118=False,GF2_solved=False)

def execute(shard):
    need(0<=shard<SHARDS,"invalid shard")
    selected=cases()
    for x in (FILTER,R118,KISSAT,CADICAL):
        need(x.is_file(),"missing pinned solver "+str(x))
    (ROOT).mkdir(parents=True,exist_ok=True)
    affinity=sorted(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{affinity[0]})
    rows=[];probes=[]
    base.FILTER=FILTER.resolve();base.R118=R118.resolve();base.KISSAT=KISSAT.resolve()
    for i,c in enumerate(selected):
        if i%SHARDS!=shard:continue
        src=SOURCES/c["id"]
        for policy in ("q2_25","q1_0"):
            probes.append(dict(id=c["id"],sha256=c["sha256"],cohort=c["cohort"],**probe(src,policy)))
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(modes)
            votes=set()
            for mode in modes:
                if mode=="cadical":x=run_cadical(src,rep)
                else:x=base.run_one(src,mode,rep,"holdout")
                row=dict(protocol=PROTO,shard=shard,id=c["id"],sha256=c["sha256"],
                         cohort=c["cohort"],**x)
                rows.append(row)
                if row["status"]!="TIMEOUT":
                    votes.add(row["status"])
                    need(len(votes)<=1,"SAT/UNSAT disagreement on "+c["id"])
                print("R129_PAIRED_TRIAL",json.dumps(row,sort_keys=True),flush=True)
    need(len(rows)==len(selected[shard::SHARDS])*REPS*len(MODES),"incomplete rows")
    cpu=next((s for s in pathlib.Path("/proc/cpuinfo").read_text().splitlines() if s.startswith("model name")),"unknown")
    pins={str(x):digest(x) for x in (FILTER,R118,KISSAT,CADICAL)}
    write(ROOT/f"shard-{shard}.json",dict(protocol=PROTO,shard=shard,
          source_manifest_sha256=digest(SOURCES/"manifest.json"),rows=rows,probes=probes,
          binary_sha256=pins,runner_cpu=cpu))
    print("R129_SHARD_COMPLETE",shard,len(rows),len(probes),flush=True)

def audit():
    selected=cases()
    source_sha=digest(SOURCES/"manifest.json")
    shards=[json.loads((ROOT/f"shard-{i}.json").read_text()) for i in range(SHARDS)]
    need(all(x["protocol"]==PROTO and x["source_manifest_sha256"]==source_sha for x in shards),"source drift")
    need(len({json.dumps(x["binary_sha256"],sort_keys=True) for x in shards})==1,"binary drift")
    rows=[y for sh in shards for y in sh["rows"]]
    probes=[y for sh in shards for y in sh["probes"]]
    need(len(rows)==len(selected)*REPS*len(MODES),"missing trials")
    cases_by_sha={c["sha256"]:c for c in selected}
    idx={}
    for x in rows:
        need(x["sha256"] in cases_by_sha and cases_by_sha[x["sha256"]]["id"]==x["id"],"formula identity drift")
        need(x["mode"] in MODES and x["repeat"] in range(REPS),"mode or repetition")
        need(x["status"] in ("SAT","UNSAT","TIMEOUT"),"solver status")
        if x["status"]=="SAT":need(x["proof"]=="source_SAT_witness_verified","missing SAT witness")
        if x["status"]=="UNSAT":need(x["proof"]=="UNSAT_without_independent_LRAT_proof","unfounded UNSAT proof claim")
        need(abs(x["par2"]-(30 if x["status"]=="TIMEOUT" else x["seconds"]))<1e-5,"incorrect PAR2")
        key=(x["sha256"],x["repeat"],x["mode"])
        need(key not in idx,"duplicate trial")
        idx[key]=x
    need(len(idx)==len(rows),"trial duplicates")
    for sha in cases_by_sha:
        for rep in range(REPS):
            tests=[idx[(sha,rep,m)] for m in MODES]
            need(len({x["status"] for x in tests if x["status"]!="TIMEOUT"})<=1,"SAT/UNSAT disagreement")
    summary={}
    for m in MODES:
        x=[r for r in rows if r["mode"]==m]
        solved=[r["seconds"] for r in x if r["status"]!="TIMEOUT"]
        summary[m]=dict(trials=len(x),solved=len(solved),SAT=sum(r["status"]=="SAT" for r in x),
             UNSAT=sum(r["status"]=="UNSAT" for r in x),timeout=sum(r["status"]=="TIMEOUT" for r in x),
             PAR2_total_s=round(sum(r["par2"] for r in x),6),
             PAR2_mean_s=round(statistics.mean(r["par2"] for r in x),6),
             median_solved_wall_s=round(statistics.median(solved),6) if solved else None,
             gate_activations=sum(r["selected_R118"] for r in x),
             GF2_solved=sum(r["GF2_solved"] for r in x))
    base_par2=summary["kissat"]["PAR2_total_s"]
    comparisons={}
    for m in MODES:
        if m=="kissat":continue
        diffs=[sum(idx[(sha,rep,m)]["par2"]-idx[(sha,rep,"kissat")]["par2"] for rep in range(REPS)) for sha in cases_by_sha]
        comparisons[m]=dict(gain_vs_kissat_pct=round(100*(base_par2/summary[m]["PAR2_total_s"]-1),5),
            faster_formula_pairs=sum(d<-1e-5 for d in diffs),
            slower_formula_pairs=sum(d>1e-5 for d in diffs),
            wins_2x=sum(sum(idx[(sha,rep,"kissat")]["par2"] for rep in range(REPS))>=2*sum(idx[(sha,rep,m)]["par2"] for rep in range(REPS)) for sha in cases_by_sha),
            regressions_2x=sum(sum(idx[(sha,rep,m)]["par2"] for rep in range(REPS))>=2*sum(idx[(sha,rep,"kissat")]["par2"] for rep in range(REPS)) for sha in cases_by_sha))
    reasons=collections.Counter((p["policy"],p["reason"]) for p in probes)
    report=dict(protocol=PROTO,phase="REUSED_R128_DEVELOPMENT_PILOT_NOT_NEW_BLIND",
        source_run_id=42033905606,formulas=len(selected),measurements=len(rows),CAP_s=CAP,repeats=REPS,
        original_manifest_sha256=source_sha,source_sha_verified=True,
        summary=summary,comparisons=comparisons,
        probes=dict(by_reason={f"{p}|{reason}":n for (p,reason),n in sorted(reasons.items())},
            triggered={m:sum(p["policy"]==m and p["route"]=="GF2" for p in probes) for m in ("q2_25","q1_0")},
            median_probe_seconds={m:round(statistics.median(p["probe_s"] for p in probes if p["policy"]==m),6) for m in ("q2_25","q1_0")}),
        all_runs_hardware=[x["runner_cpu"] for x in shards],strict_no_promotion=True,
        no_independent_UNSAT_LRAT=True,
        nonblind_note="R128 holdout was already seen and is used ONLY to diagnose R129; a new SHA-disjoint holdout would be required to claim improvement.")
    write(ROOT/"report.json",report)
    with (ROOT/"paired.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    with (ROOT/"probes.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(probes[0]));w.writeheader();w.writerows(probes)
    print("R129_PILOT_FINAL",json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("command",choices=("run","audit"))
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    {"run":lambda:execute(a.shard),"audit":audit}[a.command]()
