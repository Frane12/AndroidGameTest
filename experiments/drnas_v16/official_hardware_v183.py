#!/usr/bin/env python3
"""DRNAS V18.3 Hardware–Logic Dynamics: conservative telemetry replay.

Real 2026 CNFs ALREADY used in V18.1/V18.2: this is telemetry calibration,
not a new blind holdout and not official competition scoring.

Three levels kept separate:
  1) OS observed resource costs (child CPU user+sys; faults; context switches)
  2) preprocessing-round CPU/logic snapshots even when main search never starts
  3) existing V18.2 256-conflict search snapshots (when actually in search)

CPU time is measurable; CPU *cycles*, instructions, and Joules are NOT
available from getrusage and are explicitly marked unavailable.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,os,random,resource,statistics,subprocess,time
from pathlib import Path
import official_parallel_v180 as common

PIN="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
TRACK="3e2dee7cf5aa643c77bf946280a3c1c520756ef9"
ROOT=Path("drnas-v183-hardware-logic")
CONFIG=Path("experiments/drnas_v16/v183_hardware_calibration_cases.json")
MODES=("baseline","monitor","fixed25","adaptive_gate")
FIELDS=("shard","index","repetition","mode","status","wall_s","cpu_user_s",
       "cpu_system_s","cpu_total_s","minor_faults","major_faults","voluntary_context",
       "involuntary_context","inblock","oublock","search_samples",
       "preprocess_rounds","preprocess_cpu_s","stage","internal_monitor_pct",
       "budget_abort","fallbacks","sat_model_valid","par2","warning")
S_FIELDS=("shard","index","repetition","mode","stream","event","round",
          "conflict","cpu_ns","elapsed_ns","variables_before","variables_after",
          "clauses_before","clauses_after","propagations","restarts",
          "learned","glue","cost_ns","prop_per_conf","interval","bad")
CAP=60
def digest(b):return hashlib.sha256(b).hexdigest()
def csvwrite(path,rows,columns):
    with path.open("w",newline="") as f:
        w=csv.DictWriter(f,columns,extrasaction="ignore");w.writeheader();w.writerows(rows)
def read_tags(txt,shard,index,repetition,mode):
    samples=[];last_result={}
    for line in txt.splitlines():
        if not line.startswith("c V18"):continue
        parts=line.split()
        if len(parts)<3:continue
        tag=parts[1]
        if tag not in ("V183_PREPROCESS_BEGIN","V183_PREPROCESS_ROUND",
                       "V183_PREPROCESS_END","V182_SAMPLE","V182_RESULT"):
            continue
        d={}
        for s in parts[2:]:
            if "=" in s:
                key,val=s.split("=",1);d[key]=val
        if tag=="V182_RESULT":
            last_result=d
            continue
        r=dict(shard=shard,index=index,repetition=repetition,mode=mode,
               stream=("preprocess" if tag.startswith("V183") else "search"),
               event=tag,**d)
        samples.append(r)
    return last_result,samples

def get_case(i,meta,urls,out):
    url=urls[i].replace("http://","https://",1)
    if url.rsplit("/",1)[-1]!=meta["gbd_hash"]:
        raise RuntimeError(f"Official frozen URL mismatch {i}")
    compressed=common.fetch(url,24*1024*1024,timeout=40)
    common.RAW_LIMIT=96*1024*1024
    raw=common.unpack_limited(compressed)
    n,m=common.dimensions(raw)
    path=out/f"formula_{i}.cnf"
    path.write_bytes(raw)
    return dict(meta,path=path,sha256=digest(raw),nvars=n,nclauses=m)

def usage_diff(a,b):
    return dict(cpu_user_s=round(b.ru_utime-a.ru_utime,7),
           cpu_system_s=round(b.ru_stime-a.ru_stime,7),
           cpu_total_s=round(b.ru_utime-a.ru_utime+b.ru_stime-a.ru_stime,7),
           minor_faults=b.ru_minflt-a.ru_minflt,
           major_faults=b.ru_majflt-a.ru_majflt,
           voluntary_context=b.ru_nvcsw-a.ru_nvcsw,
           involuntary_context=b.ru_nivcsw-a.ru_nivcsw,
           inblock=b.ru_inblock-a.ru_inblock,oublock=b.ru_oublock-a.ru_oublock)

def run_case(shard,case,rep,mode):
    env=os.environ.copy()
    env.pop("DRNAS_V182_MODE",None);env.pop("DRNAS_V183_HW",None)
    if mode=="baseline":
        binary="/tmp/kissat-v183-original/build/kissat"
    else:
        binary="/tmp/kissat-v183-hardware/build/kissat"
        env["DRNAS_V182_MODE"]=mode
        env["DRNAS_V183_HW"]="1"
    start=resource.getrusage(resource.RUSAGE_CHILDREN)
    t0=time.perf_counter()
    try:
        p=subprocess.run([binary,"-s",str(case["path"].resolve())],
                 env=env,text=True,capture_output=True,errors="replace",
                 timeout=CAP,check=False)
        wall=time.perf_counter()-t0
        output=p.stdout+"\n"+p.stderr
        state={10:"SAT",20:"UNSAT"}.get(p.returncode,"ERROR")
    except subprocess.TimeoutExpired as e:
        wall=time.perf_counter()-t0
        def decode(x):
            return x.decode("utf-8","replace") if isinstance(x,bytes) else (x or "")
        output=decode(e.stdout)+"\n"+decode(e.stderr)
        state="TIMEOUT"
    end=resource.getrusage(resource.RUSAGE_CHILDREN)
    costs=usage_diff(start,end)
    expected=case["official_kissat"]["result"].upper()
    if state in ("SAT","UNSAT") and state!=expected:
        raise RuntimeError(f"SAT/UNSAT mismatch case {case['official_index']}")
    if state=="ERROR":raise RuntimeError(f"Unexpected return for {mode}: {output[-600:]}")
    witness=state=="SAT" and common.check_model(case["path"],output,None)
    if state=="SAT" and not witness:
        raise RuntimeError(f"Invalid SAT witness {case['official_index']}")
    telemetry,events=read_tags(output,shard,case["official_index"],rep,mode)
    if mode=="baseline" and (events or telemetry):
        raise RuntimeError("Original Kissat emitted patched tags")
    preprocess=[r for r in events if r["event"]=="V183_PREPROCESS_ROUND"]
    ticks=[r for r in events if r["event"]=="V182_SAMPLE"]
    # For real SAT instances taking > 0.1s the patched binary must emit
    # at least one phase marker; all-zero traces mean instrumentation failed.
    # A trivial SAT shortcut can finish before preprocessing/search starts.
    if mode != "baseline" and state in ("SAT", "UNSAT") and wall > 0.1:
        if not telemetry and not any(r["stream"]=="preprocess" for r in events):
            raise RuntimeError(
                f"V183_INSTRUMENTATION_MISSING mode={mode} "
                f"index={case['official_index']} wall={wall:.3f}s "
                "No V182_RESULT or V183_PREPROCESS tags; reject stale binary")
    starts=[r for r in events if r["event"]=="V183_PREPROCESS_BEGIN"]
    ends=[r for r in events if r["event"]=="V183_PREPROCESS_END"]
    stage=("baseline_uninstrumented" if mode=="baseline"
           else "preprocessing_only" if preprocess and not ticks
           else "preprocess_and_search" if preprocess and ticks
           else "search_only" if ticks else "unobserved_phase")
    warnings=[]
    if mode!="baseline" and not ticks:
        warnings.append("no_256_conflict_search_ticks; never replace by zeros")
    if mode!="baseline" and not preprocess:
        warnings.append("no_preprocessing_round_snapshots")
    if mode!="baseline" and state in ("SAT","UNSAT") and len(preprocess)==0 and len(ticks)==0:
        warnings.append("INSUFFICIENT_INNER_TRACE")
    # Explicitly distinguish OS CPU from cycles/instructions/energy.
    row=dict(shard=shard,index=case["official_index"],repetition=rep,mode=mode,
       status=state,wall_s=round(wall,7),**costs,
       search_samples=len(ticks),preprocess_rounds=len(preprocess),
       preprocess_cpu_s=(round((int(ends[-1]["elapsed_ns"])/1e9),7) if ends else ""),
       stage=stage,internal_monitor_pct=telemetry.get("monitor_pct",""),
       budget_abort=telemetry.get("budget_abort",""),
       fallbacks=telemetry.get("fallbacks",""),
       sat_model_valid=bool(witness),par2=round(wall,7) if state in ("SAT","UNSAT") else 120,
       warning="; ".join(warnings))
    print("V183_MEASURE",case["official_index"],rep,mode,state,
          f"wall={wall:.4f}s",f"cpu={costs['cpu_total_s']:.4f}s",
          f"preprocess_rounds={len(preprocess)}",f"search_ticks={len(ticks)}",
          f"fallback={row['fallbacks']}",flush=True)
    return row,events

def third_difference(seq):
    return [seq[i]-3*seq[i-1]+3*seq[i-2]-seq[i-3] for i in range(3,len(seq))]

def analyze(events):
    # Distinguish preprocessing CPU per completed *round* from search CPU
    # per conflict. Samples are not interchangeable, nor normalized as such.
    groups={}
    for e in events:
        key=(e["index"],e["repetition"],e["mode"],e["stream"])
        groups.setdefault(key,[]).append(e)
    out=[]
    for key,samples in groups.items():
        stream=key[3]
        if stream=="preprocess":
            rounds=[x for x in samples if x["event"]=="V183_PREPROCESS_ROUND"]
            values=[int(x["elapsed_ns"]) for x in rounds]
            delta=[values[i]-values[i-1] for i in range(1,len(values))]
            # THIRD difference needs >=4 interval samples or 5 round cumulative
            # timestamps; fewer = unknown, not zero.
            jerks=third_difference(delta)
            total_ns=(int(samples[-1].get("elapsed_ns",0)) if samples else 0)
            out.append(dict(index=key[0],repetition=key[1],mode=key[2],
              stage="preprocess",rounds=len(rounds),samples=len(values),
              cpu_elapsed_ns=total_ns,
              third_diff_available=bool(jerks),
              max_abs_third_diff_ns=max(map(abs,jerks)) if jerks else None,
              note="preprocessing-round spacing is NOT uniform in conflicts"))
        else:
            # Saved V18.2 checkpoints are deliberately sparse after 2048.
            # A third discrete difference is valid only across consecutive
            # 256-conflict ticks. Do not confuse sparse data with uniform data.
            ordered=sorted(samples,key=lambda x:int(x["conflict"]))
            jerks=[]
            for end_idx in range(3,len(ordered)):
                window=ordered[end_idx-3:end_idx+1]
                conflicts=[int(x["conflict"]) for x in window]
                if all(conflicts[k]-conflicts[k-1]==256 for k in range(1,4)):
                    jerks.append(third_difference([
                        float(x["cost_ns"]) for x in window
                    ])[0])
            out.append(dict(index=key[0],repetition=key[1],mode=key[2],
               stage="search",rounds=None,samples=len(ordered),
               cpu_elapsed_ns=None,third_diff_available=bool(jerks),
               max_abs_third_diff_ns=round(max(map(abs,jerks)),5) if jerks else None,
               note="256-conflict samples only before budget-abort; sparse retained checkpoints"))
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--shard",type=int,choices=(0,1),required=True)
    opts=p.parse_args()
    conf=json.loads(CONFIG.read_text())
    assert conf["kissat_sha"]==PIN and conf["track_sha"]==TRACK
    shard=opts.shard
    folder=ROOT/f"shard_{shard}"
    folder.mkdir(parents=True,exist_ok=True)
    official_url=(f"https://raw.githubusercontent.com/satcompetition/2026/"
                  f"{TRACK}/downloads/track_main_2026.uri")
    uri=common.fetch(official_url,100000,timeout=35).decode().splitlines()
    assert len(uri)==400
    selection=conf["shards"][shard]
    cases=[]
    for c in selection:
        case=get_case(c["official_index"],c,uri,folder)
        cases.append(case)
        print("V183_FROZEN_INPUT",case["official_index"],case["sha256"],flush=True)
    data=[];events=[]
    for case in cases:
        for rep in range(conf["repeats"]):
            modes=list(MODES)
            random.Random(183000+case["official_index"]*101+rep).shuffle(modes)
            for mode in modes:
                row,ev=run_case(shard,case,rep,mode)
                data.append(row);events+=ev
            csvwrite(folder/"measurements.partial.csv",data,FIELDS)
    csvwrite(folder/"measurements.csv",data,FIELDS)
    csvwrite(folder/"events.csv",events,S_FIELDS)
    features=analyze(events)
    (folder/"derived_signals.json").write_text(json.dumps(features,indent=2))
    assert len(data)==len(cases)*conf["repeats"]*len(MODES)
    bymode={mode:[x for x in data if x["mode"]==mode] for mode in MODES}
    summary=dict(shard=shard,formula_count=len(cases),measurements=len(data),
       mean_par2={key:round(statistics.mean(float(x["par2"]) for x in value),5)
                   for key,value in bymode.items()},
       observed_preprocess_rounds=sum(int(x["preprocess_rounds"]) for x in data),
       observed_search_snapshots=sum(int(x["search_samples"]) for x in data),
       missing_inner_trace=sum("INSUFFICIENT_INNER_TRACE" in x["warning"] for x in data),
       sat_witness_validations=sum(x["sat_model_valid"] for x in data),
       no_independent_unsat_certificates=True,
       cpu_cycle_counts_available=False,energy_joule_available=False,
       cpu_time_usage="os.getrusage(RUSAGE_CHILDREN) child CPU user+sys delta",
       no_world_record_claim=True,
       no_heldout_claim=True,
       note="Re-analysis of previously used official 2026 CNFs, not fresh blind.")
    (folder/"summary.json").write_text(json.dumps(summary,indent=2))
    (folder/"manifest.json").write_text(json.dumps({**conf,"shard":shard,
       "cases":[{"official_index":x["official_index"],"sha256":x["sha256"]}
                for x in cases]},indent=2))
    print("V183_FINAL",json.dumps(summary,separators=(",",":")),flush=True)

if __name__=="__main__":main()
