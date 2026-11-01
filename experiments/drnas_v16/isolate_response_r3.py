#!/usr/bin/env python3
"""DRNAS R3: isolate early-state responses on four already-known official CNFs.

DIAGNOSTIC ONLY, NOT BLIND, NOT OFFICIAL COMPETITION SCORING.
Deliberately compare:
 - unmodified upstream Kissat, with restart interval from process start
 - V17.7 in-process forced restart=25 after conflict 2048
 - V18.2 in-process monitor and delayed interventions at conflict 2048
The same frozen CNF, CPU runner, and pairing rules apply to all policies.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,os,platform,random,resource,statistics,subprocess,time
from pathlib import Path
import official_parallel_v180 as common

ROOT=Path("drnas-r3-isolated")
KISSAT="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
TRACK="3e2dee7cf5aa643c77bf946280a3c1c520756ef9"
CAP=60
REPEATS=3
POLICIES=("baseline","cli25","cli50","v177switch","monitor","fixed25",
          "fixed50","gate_no_guard","adaptive_gate","adaptive_force")
CASES=(
  (154,"5de866bc7ff4dfde3cd682b5aca75894","SAT"),
  (212,"8117a2ac08e1acf52f660663efe2a5ca","SAT"),
  (239,"920bbe559da4ea37fd636605316a791c","UNSAT"),
  (324,"c557ad9cb79983b9d429c219e3cecbb8","UNSAT"),
)
FIELDS=("index","gbd_hash","cnf_sha256","repeat","mode","status","expected",
        "wall_s","cpu_s","par2_s","sat_model_valid","switch_at","interval",
        "samples","fallbacks","budget_abort","early_glue","conflicts",
        "restarts","learned","pre2048_samples","warning")
TRACE_FIELDS=("index","repeat","mode","conflict","cpu_ns","restarts",
              "focused_restarts","learned","propagations","decisions",
              "glue","cost_ns","prop_per_conf","bad","stable","interval")
ORIGINAL="/tmp/kissat-r3-original/build/kissat"
V177="/tmp/kissat-r3-v177/build/kissat"
V182="/tmp/kissat-r3-v182/build/kissat"

def sha(data):return hashlib.sha256(data).hexdigest()
def write_csv(path,columns,records):
    with path.open("w",newline="") as stream:
        w=csv.DictWriter(stream,fieldnames=columns,extrasaction="ignore")
        w.writeheader();w.writerows(records)

def obtain(shard,out):
    index,expected_hash,expected=CASES[shard]
    urls=common.fetch(
      f"https://raw.githubusercontent.com/satcompetition/2026/{TRACK}/downloads/track_main_2026.uri",
      100000,timeout=30).decode().strip().splitlines()
    assert len(urls)==400
    url=urls[index].replace("http://","https://",1)
    assert url.rsplit("/",1)[-1]==expected_hash
    compressed=common.fetch(url,24*1024*1024,timeout=45)
    common.RAW_LIMIT=96*1024*1024
    raw=common.unpack_limited(compressed)
    n,m=common.dimensions(raw)
    p=out/f"official_{index}.cnf";p.write_bytes(raw)
    return {"index":index,"gbd_hash":expected_hash,"expected":expected,
            "path":p,"nvars":n,"nclauses":m,"cnf_sha256":sha(raw),
            "archive_sha256":sha(compressed),"archive_size":len(compressed),
            "cnf_bytes":len(raw),"source_url":url}

def tags(output,index,rep,mode):
    result={}
    traces=[]
    for line in output.splitlines():
        if not line.startswith("c V182_"):continue
        x=line.split()
        if len(x)<3:continue
        name=x[1]
        d=dict(token.split("=",1) for token in x[2:] if "=" in token)
        if name=="V182_RESULT":result=d
        elif name=="V182_SAMPLE":
            traces.append(dict(index=index,repeat=rep,mode=mode,**d))
    return result,traces

def invoke(case,mode,rep):
    env=os.environ.copy()
    env.pop("DRNAS_V177_MODE",None)
    env.pop("DRNAS_V177_RULE_FILE",None)
    env.pop("DRNAS_V182_MODE",None)
    binary=ORIGINAL
    flags=[]
    if mode=="cli25":flags=["--restartint=25"]
    elif mode=="cli50":flags=["--restartint=50"]
    elif mode=="v177switch":
        binary=V177;env["DRNAS_V177_MODE"]="switch2048"
    elif mode not in ("baseline","cli25","cli50"):
        binary=V182;env["DRNAS_V182_MODE"]=mode
    command=[binary,*flags,"-s",str(case["path"].resolve())]
    before=resource.getrusage(resource.RUSAGE_CHILDREN)
    start=time.perf_counter()
    try:
        proc=subprocess.run(command,env=env,capture_output=True,
                            text=True,errors="replace",timeout=CAP)
        status={10:"SAT",20:"UNSAT"}.get(proc.returncode,"ERROR")
        output=proc.stdout+"\n"+proc.stderr
    except subprocess.TimeoutExpired as exc:
        status="TIMEOUT"
        def decode(x):
            return x.decode("utf-8","replace") if isinstance(x,bytes) else (x or "")
        output=decode(exc.stdout)+"\n"+decode(exc.stderr)
    wall=time.perf_counter()-start
    after=resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime
    valid=status=="SAT" and common.check_model(case["path"],output,None)
    if status=="SAT" and not valid:
        raise RuntimeError(f"Invalid SAT model: {case['index']} {rep} {mode}")
    if status in ("SAT","UNSAT") and status!=case["expected"]:
        raise RuntimeError(f"Official verified answer mismatch: {case['index']} {rep} {mode} {status}")
    if status=="ERROR":
        raise RuntimeError(f"Unexpected solver exit: {case['index']} {rep} {mode}: {output[-500:]}")
    extra,traces=tags(output,case["index"],rep,mode)
    warn=[]
    if mode in ("monitor","fixed25","fixed50","gate_no_guard","adaptive_gate","adaptive_force"):
        if status!="TIMEOUT" and wall>0.1 and not extra:
            warn.append("NO_V182_RESULT; preprocessing-only or instrumentation mismatch")
    row=dict(index=case["index"],gbd_hash=case["gbd_hash"],cnf_sha256=case["cnf_sha256"],
             repeat=rep,mode=mode,status=status,expected=case["expected"],
             wall_s=round(wall,6),cpu_s=round(cpu,6),
             par2_s=round(wall if status in ("SAT","UNSAT") else 2*CAP,6),
             sat_model_valid=valid,
             switch_at=extra.get("switch_at",""),interval=extra.get("interval",""),
             samples=extra.get("samples",""),fallbacks=extra.get("fallbacks",""),
             budget_abort=extra.get("budget_abort",""),
             early_glue=extra.get("early_glue",""),
             conflicts=extra.get("conflicts",""),restarts=extra.get("restarts",""),
             learned=extra.get("learned",""),
             pre2048_samples=sum(int(t["conflict"])<2048 for t in traces),
             warning="; ".join(warn))
    print("R3_MEASURE",case["index"],rep,mode,status,f"wall={wall:.4f}s",
          f"cpu={cpu:.4f}s",f"switch={row['switch_at']}",
          f"samples={len(traces)}",flush=True)
    return row,traces

def causal_prefix_check(rows,traces):
    group={}
    for t in traces:
        if int(t["conflict"])>=2048:continue
        key=(t["repeat"],t["mode"])
        group.setdefault(key,[]).append(t)
    report=[]
    keys=("conflict","restarts","learned","propagations","decisions","glue","stable")
    for rep in range(REPEATS):
        reference=[tuple(t[k] for k in keys) for t in group.get((rep,"monitor"),[])]
        for mode in ("fixed25","fixed50"):
            other=[tuple(t[k] for k in keys) for t in group.get((rep,mode),[])]
            ok=(reference==other)
            report.append({"repeat":rep,"mode":mode,
                           "prefix_equal":ok,"samples_baseline":len(reference),
                           "samples_treatment":len(other),
                           "explanation":"Identical observable prefix before 2048 conflicts; no full hidden-state equality claim"})
    return report

def main_batch(shard):
    out=ROOT/f"shard_{shard}";out.mkdir(parents=True,exist_ok=True)
    case=obtain(shard,out)
    paths={"original":Path(ORIGINAL),"v177":Path(V177),"v182":Path(V182)}
    assert all(p.is_file() for p in paths.values())
    manifest={k:(str(v) if isinstance(v,Path) else v) for k,v in case.items() if k!="path"}
    manifest.update(kissat_commit=KISSAT,track_commit=TRACK,sha256_binaries={
            k:sha(p.read_bytes()) for k,p in paths.items()},
            policies=POLICIES,repeats=REPEATS,time_cap_s=CAP,
            lscpu=subprocess.run(["lscpu"],text=True,capture_output=True).stdout,
            platform=platform.platform(),source="SAT Competition 2026 Main Track",
            caveat="Diagnostic on previously seen formulas, not blind/official scoring",
            unsat_independent_proof=False)
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2))
    rows=[];traces=[]
    for rep in range(REPEATS):
        order=list(POLICIES)
        random.Random(18031+shard*101+rep).shuffle(order)
        for mode in order:
            r,t=invoke(case,mode,rep)
            rows.append(r);traces.extend(t)
            write_csv(out/"measurements.partial.csv",FIELDS,rows)
            write_csv(out/"traces.partial.csv",TRACE_FIELDS,traces)
    write_csv(out/"measurements.csv",FIELDS,rows)
    write_csv(out/"traces.csv",TRACE_FIELDS,traces)
    prefix=causal_prefix_check(rows,traces)
    baseline=[x["par2_s"] for x in rows if x["mode"]=="baseline"]
    result={}
    for mode in POLICIES:
        sample=sorted([x for x in rows if x["mode"]==mode],key=lambda x:x["repeat"])
        assert len(sample)==REPEATS
        pair=[baseline[i]-sample[i]["par2_s"] for i in range(REPEATS)]
        result[mode]=dict(solved=sum(x["status"] in ("SAT","UNSAT") for x in sample),
             median_wall_s=round(statistics.median(x["wall_s"] for x in sample),6),
             median_par2_s=round(statistics.median(x["par2_s"] for x in sample),6),
             median_improvement_s=round(statistics.median(pair),6),
             mean_cpu_s=round(statistics.mean(x["cpu_s"] for x in sample),6),
             switches=[x["switch_at"] for x in sample],
             budget_abort=[x["budget_abort"] for x in sample],
             samples=[x["samples"] for x in sample])
    m_by_policy={mode:result[mode]["median_par2_s"] for mode in POLICIES}
    r25=m_by_policy["fixed25"];r50=m_by_policy["fixed50"]
    finite_diff=(r50-r25)/25.0
    summary=dict(index=case["index"],status=case["expected"],
       formula_kind="official 2026 already-seen diagnostic",
       measurements=len(rows),repeats=REPEATS,results=result,
       pre_intervention_prefix=prefix,
       observable_prefix_match_all=all(x["prefix_equal"] for x in prefix),
       delayed_restart_response_s_per_interval_unit=round(finite_diff,9),
       caution="Discrete paired action contrast, NOT a mathematical derivative, Jacobian or blind predictive validation",
       validated_sat_witnesses=sum(x["sat_model_valid"] for x in rows),
       independent_unsat_proofs=0,
       invalid_results=sum(x["status"]=="ERROR" for x in rows))
    (out/"summary.json").write_text(json.dumps(summary,indent=2))
    print("R3_FORMULA_FINAL",json.dumps(summary,separators=(",",":")),flush=True)

def main_aggregate():
    shards=[]
    for i in range(4):
        path=ROOT/f"shard_{i}"/"summary.json"
        shards.append(json.loads(path.read_text()))
    assert [x["index"] for x in shards]==[x[0] for x in CASES]
    result=dict(experiment="R3 four-formula causal directional response pilot",
       complete_shards=len(shards),
       measurements=sum(x["measurements"] for x in shards),
       inputs="four previously seen official SAT Competition 2026 formulas",
       runner_model="paired per formula within one GitHub-hosted runner; different physical runners between shards",
       v182_intervention="restartint changed in same Kissat process at conflict 2048 where actually reached",
       v184_jacobian_controller_implemented=False,
       test_is_blind=False,independent_unsat_proofs=0,
       verified_prefix_all=all(x["observable_prefix_match_all"] for x in shards),
       conclusions="No generalization from four outcome-selected formulas. Use independently frozen new official holdout.",
       per_formula=shards)
    (ROOT/"combined.json").write_text(json.dumps(result,indent=2))
    print("R3_ALL_FINAL",json.dumps({k:v for k,v in result.items() if k!="per_formula"},separators=(",",":")),flush=True)
    for x in shards:
        print("R3_COMPACT",x["index"],json.dumps({k:{"median_par2_s":v["median_par2_s"],"switches":v["switches"]} for k,v in x["results"].items()}),flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--shard",type=int)
    ap.add_argument("--aggregate",action="store_true")
    a=ap.parse_args()
    if a.aggregate:main_aggregate()
    elif a.shard in range(4):main_batch(a.shard)
    else:ap.error("Specify --shard 0..3 or --aggregate")
