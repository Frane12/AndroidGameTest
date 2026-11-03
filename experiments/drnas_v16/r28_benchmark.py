#!/usr/bin/env python3
"""R28 matched native AND↔XOR phase experiment: raw trials, paired analysis.

Frozen before executing: 10 earlier R26 GBD polynomial dev, 4 additional
GBD original holdouts, 4 XOR controls; 4 intervention modes + 2 baselines.
All repeated attempts in each case share CPU affinity and frozen input SHA.
"""
import argparse,hashlib,json,os,random,statistics,subprocess,time
from collections import Counter,defaultdict
from pathlib import Path
from r28_freeze import PROTOCOL,MODES,CAP,REPEATS,SHARDS

FIELDS=("exact_xor3_blocks","and3_gates","joined_and_xor_outputs","chosen",
        "hints","max_xor_degree","first_status","learned_redundant","active_initial",
        "active_256","extract_us","first_us","resume_us","solver_us")
def digest(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for c in iter(lambda:f.read(1<<20),b""):h.update(c)
    return h.hexdigest()

def execute(exe,case,mode,seed,cap):
    src=case["realpath"]
    if mode.startswith("gate_"):
        args=[str(exe/"r28_and_xor"),mode,str(src),str(seed)]
    elif mode=="CaDiCaL301":
        args=[str(exe/"cadical_solver"),str(src)]
    else:
        args=[str(exe/"kissat_solver"),str(src)]
    start=time.perf_counter()
    try:
        p=subprocess.run(args,text=True,errors="replace",capture_output=True,
                         timeout=cap,check=False)
    except subprocess.TimeoutExpired:
        return dict(status="TIMEOUT",wall_s=cap,correct=False,
                    route="timeout",exit=-1,telemetry={},error="")
    elapsed=time.perf_counter()-start
    status=None; telemetry={};route="direct_baseline"
    if mode.startswith("gate_"):
        lines=[x for x in p.stdout.splitlines() if x.startswith("DRNAS_R28_RESULT\t")]
        if len(lines)!=1:
            raise RuntimeError(f"R28 machine summary missing {mode}: "
                               +p.stderr[-650:])
        items=lines[0].split("\t")
        if len(items)!=17 or items[1]!=mode or items[2] not in ("SAT","UNSAT"):
            raise RuntimeError("Malformed R28 output: "+repr(items))
        status=items[2]
        for key,value in zip(FIELDS,items[3:]):
            telemetry[key]=float(value) if key.endswith("_us") else int(value)
        route="and_xor_phase" if telemetry["hints"] else "and_xor_no_hint"
        if telemetry["hints"]>512 or telemetry["joined_and_xor_outputs"]<telemetry["hints"]:
            raise RuntimeError("Invalid phase telemetry")
        if telemetry["first_status"] not in (0,10,20):
            raise RuntimeError("Invalid early checkpoint code")
    else:
        for line in p.stdout.splitlines():
            if line.startswith("s UNSATISFIABLE"):
                status="UNSAT"
            if line.startswith("s SATISFIABLE"):
                status="SAT"
        if status is None and p.returncode in (10,20):
            status="SAT" if p.returncode==10 else "UNSAT"
    if p.returncode not in (0,10,20) or status not in ("SAT","UNSAT"):
        raise RuntimeError(f"Native error mode={mode}, exit={p.returncode}: "
                           +p.stderr[-500:])
    if status!=case["expected"]:
        raise RuntimeError("WRONG SAT/UNSAT: "+case["id"]+" "+mode+" "+status)
    return dict(status=status,wall_s=round(elapsed,6),correct=True,
                route=route,exit=p.returncode,telemetry=telemetry,error="")

def run(a):
    src=Path(a.inputs).resolve()
    spec=json.loads((src/"manifest.json").read_text())
    if (spec["protocol"]!=PROTOCOL or spec["modes"]!=list(MODES) or
        spec["cutoff_s"]!=CAP or spec["repetitions"]!=REPEATS or
        spec["shards"]!=SHARDS):raise RuntimeError("Frozen protocol changed")
    if not 0<=a.shard<SHARDS:raise RuntimeError("Invalid shard")
    cores=os.sched_getaffinity(0)
    if len(cores)>0:os.sched_setaffinity(0,{min(cores)})
    binary=Path(a.bin).resolve()
    out=Path(a.out)
    out.mkdir(parents=True,exist_ok=True)
    hashes={name:digest(binary/name) for name in
            ("r28_and_xor","kissat_solver","cadical_solver")}
    cpu=next((line.split(":",1)[1].strip() for line in
             Path("/proc/cpuinfo").read_text().splitlines()
             if line.startswith("model name")),"unknown")
    manifest_sha=digest(src/"manifest.json")
    (out/"metadata.json").write_text(json.dumps(dict(
        shard=a.shard,cpu=cpu,affinity=sorted(os.sched_getaffinity(0)),
        source_manifest_sha256=manifest_sha,protocol=PROTOCOL,
        cutoff_s=a.timeout,repetitions=a.repeats,
        binary_sha256=hashes),indent=2))
    results=[]
    for case in spec["cases"][a.shard::SHARDS]:
        case=dict(case)
        case["realpath"]=src/case["path"]
        if digest(case["realpath"])!=case["sha256"]:
            raise RuntimeError("Original input SHA drift")
        measurements=[]
        for repeat in range(a.repeats):
            seed=28031103+int(case["sha256"][:7],16)+repeat*5197
            modes=list(MODES)
            random.Random(seed).shuffle(modes)
            for mode in modes:
                v=execute(binary,case,mode,seed,a.timeout)
                measurements.append(dict(mode=mode,repeat=repeat,seed=seed,**v))
                info=v["telemetry"]
                print("R28_TRIAL",case["id"],case["role"],mode,repeat,
                      v["status"],v["wall_s"],v["route"],
                      "hint_count="+str(info.get("hints",-1)),
                      "xor="+str(info.get("exact_xor3_blocks",-1)),
                      "gates="+str(info.get("and3_gates",-1)),
                      "joined="+str(info.get("joined_and_xor_outputs",-1)),
                      "early="+str(info.get("first_status",-1)),
                      "learnt="+str(info.get("learned_redundant",-1)),
                      flush=True)
        case.pop("realpath")
        results.append(dict(case=case,trials=measurements))
        (out/"rows.json").write_text(json.dumps(results,indent=2,sort_keys=True)+"\n")
    print("R28_SHARD_SUCCESS",a.shard,len(results),flush=True)

def aggregate(a):
    src=Path(a.inputs).resolve()
    spec=json.loads((src/"manifest.json").read_text())
    allrows=[]
    binaries=set();hardware=set()
    for shard in range(SHARDS):
        folder=Path(a.combined)/f"r28-shard-{shard}"
        if not (folder/"rows.json").exists():folder=folder/"results"
        m=json.loads((folder/"metadata.json").read_text())
        assert m["protocol"]==PROTOCOL and m["source_manifest_sha256"]==digest(src/"manifest.json")
        assert m["shard"]==shard and m["cutoff_s"]==CAP and m["repetitions"]==REPEATS
        binaries.add(json.dumps(m["binary_sha256"],sort_keys=True))
        hardware.add(m["cpu"])
        rows=json.loads((folder/"rows.json").read_text())
        assert [r["case"]["sha256"] for r in rows]==[
            z["sha256"] for z in spec["cases"][shard::SHARDS]]
        allrows+=rows
    assert len(allrows)==18 and len(binaries)==1,(len(allrows),len(binaries))
    summary={}
    roles=("ALL","previously_measured_development","r28_additional_original_holdout",
           "xor_structure_control")
    for role in roles:
        subset=[r for r in allrows if role=="ALL" or r["case"]["role"]==role]
        summary[role]={}
        for mode in MODES:
            med=[];solved=0;timeouts=0;selected=0;stage=Counter()
            for r in subset:
                v=[x for x in r["trials"] if x["mode"]==mode]
                assert len(v)==REPEATS and all(x["status"]=="TIMEOUT" or x["correct"] for x in v)
                costs=[2*CAP if x["status"]=="TIMEOUT" else x["wall_s"] for x in v]
                med.append(statistics.median(costs))
                solved+=int(all(x["correct"] for x in v))
                timeouts+=sum(x["status"]=="TIMEOUT" for x in v)
                selected+=int(any(x["telemetry"].get("hints",0)>0 for x in v))
                stage.update(x["telemetry"].get("first_status",-1) for x in v)
            summary[role][mode]=dict(solved=solved,total=len(subset),
                        sum_case_median_PAR2_s=round(sum(med),6),
                        timeouts_attempts=timeouts,with_nonzero_phase_hints=selected,
                        first_status_hist=dict(stage))
        for target in ("gate_zero","gate_one","gate_random","gate_shadow"):
            score=summary[role][target]["sum_case_median_PAR2_s"]
            for compare in ("gate_shadow","CaDiCaL301","Kissat404"):
                ref=summary[role][compare]["sum_case_median_PAR2_s"]
                summary[role][target]["ratios_"+compare+"_over_target"]=round(ref/max(score,1e-9),6)
    percase=[]
    for row in allrows:
        x=dict(id=row["case"]["id"],role=row["case"]["role"],family=row["case"]["family"])
        for mode in MODES:
            v=[t for t in row["trials"] if t["mode"]==mode]
            x[mode+"_PAR2_s"]=round(statistics.median(
                2*CAP if t["status"]=="TIMEOUT" else t["wall_s"] for t in v),6)
            if mode.startswith("gate_"):
                x[mode+"_telemetry"]=v[0]["telemetry"]
        x["gate_zero_vs_shadow_ratio"]=round(
            x["gate_shadow_PAR2_s"]/max(x["gate_zero_PAR2_s"],1e-9),5)
        percase.append(x)
    report=dict(protocol=PROTOCOL,
        sha256_original_manifest=digest(src/"manifest.json"),
        original_binary_sha256=json.loads(next(iter(binaries))),
        paired_runner_cpu_models=sorted(hardware),
        caveats=[
          "This is a local SAT competition-style simulation, NOT world ranking",
          "R28 uses a phase heuristic only; no clause-level XOR/AND propagation is implemented",
          "gate_shadow does the exact structural extraction/checkpoint with zero phase hints",
          "Previously measured development and four additional original GBD holdouts must be assessed separately",
          "Every solved SAT outcome by experimental arms was checked against original CNF internally",
          "No independent UNSAT certificates supplied; original source labels checked",
          "PAR2 timeout penalty=12s per 6-second cap, not actual solver duration",
          "Identical SHA and same runner for per-case randomized paired methods",
          "Hardware may differ across GitHub shards, so comparisons are paired within cases"],summary=summary,
        per_case=percase,raw_rows=allrows)
    Path(a.out_json).write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    text=["# DRNAS SAT R28 AND↔XOR native phase A/B","Original SHA-pinned 18 CNFs, six methods, two paired repeats each, six-second cap, PAR2 timeout penalty twelve seconds.",
          "**This is an experiment, not an official competition ranking.**",""]
    for role in roles:
        d=summary[role]
        text += [f"## {role} — {len([x for x in allrows if role=='ALL' or x['case']['role']==role])} formulas",
            "| Solver mode | Solved | Sum PAR2 median s | Timeout attempts | Gated cases |",
            "|---|---:|---:|---:|---:|"]
        for mode in MODES:
            x=d[mode]
            text.append(f'| {mode} | {x["solved"]}/{x["total"]} | '
                        f'{x["sum_case_median_PAR2_s"]:.6f} | {x["timeouts_attempts"]} | '
                        f'{x["with_nonzero_phase_hints"]} |')
        text += [f'**gate_zero vs matched gate_shadow: {d["gate_zero"]["ratios_gate_shadow_over_target"]:.4f}x**',
                 f'**gate_zero vs unmodified CaDiCaL: {d["gate_zero"]["ratios_CaDiCaL301_over_target"]:.4f}x**',""]

    text += ["## Instance-level results and regressions",
             "| Formula | Role | gate_zero | gate_shadow | CaDiCaL | Kissat | Phase speedup |",
             "|---|---|---:|---:|---:|---:|---:|"]
    for x in percase:
        text.append(f'| {x["id"]} | {x["role"]} | {x["gate_zero_PAR2_s"]:.3f} | '
                    f'{x["gate_shadow_PAR2_s"]:.3f} | {x["CaDiCaL301_PAR2_s"]:.3f} | '
                    f'{x["Kissat404_PAR2_s"]:.3f} | {x["gate_zero_vs_shadow_ratio"]:.2f}x |')
    text += ["","## Scientific interpretation",
             "Phase hints alter solver search preference, not logical satisfiability or original CNF constraints.",
             "A favorable paired result is not a proof of general SAT gains or P=NP.",
             "Any selection rule derived from these results must be revalidated on a new untouched formula set."]
    Path(a.out_md).write_text("\n".join(text)+"\n")
    print("\n".join(text),flush=True)

def main():
    p=argparse.ArgumentParser()
    s=p.add_subparsers(dest="command",required=True)
    run=s.add_parser("run")
    for x in ("inputs","bin","out"):run.add_argument("--"+x,required=True)
    run.add_argument("--shard",type=int,required=True)
    run.add_argument("--timeout",type=float,default=CAP)
    run.add_argument("--repeats",type=int,default=REPEATS)
    agg=s.add_parser("aggregate")
    for x in ("inputs","combined","out-json","out-md"):
        agg.add_argument("--"+x,required=True)
    a=p.parse_args()
    if a.command=="run":globals()["run"](a)
    else:aggregate(a)
if __name__=="__main__":main()
