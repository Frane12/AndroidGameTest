#!/usr/bin/env python3
"""DRNAS SAT v8.1 diagnostic: 300s pilot on six previously examined hard 2026 CNFs.
Retrospective, predeclared instances and no tuning. Never count timeout as solved.
The original frozen v7.6 and v7.7 implementations run unmodified.
"""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import random
import signal
import statistics
import subprocess
import time

CAP=300
MODES=("orig_v76","orig_v77","hybrid_gate_with_observer","ca_plain")
HARD_CASES={
    "0e06895600b5cd0b6fadb87e17bf8145",
    "43d40ced32b5be08814ef24f97379654",
    "44b7d2c8d08574002ac959e6d1ef30ae",
    "53d23b2b464a5c041114eb1f00cc4b81",
    "93983a1211a506a87907c7e2ffa4e818",
    "a08d0fcc98fe0ce9c53b2fd0c69ccc4b",
}
FIELDS=("case","sha256","seed","mode","status","wall_s","cpu_s_last",
        "peak_rss_kb","sample_count","last_stage","stages","extended",
        "gate_reason","timeout_cap_s","error","trace_path","samples_path")

def cpu_and_rss(pid):
    cpu_s=None
    rss_kb=None
    try:
        raw=Path(f"/proc/{pid}/stat").read_text()
        tail=raw[raw.rfind(")")+2:].split()
        cpu_s=(int(tail[11])+int(tail[12]))/os.sysconf("SC_CLK_TCK")
    except (OSError,ValueError,IndexError):
        pass
    try:
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                rss_kb=int(line.split()[1])
                break
    except (OSError,ValueError,IndexError):
        pass
    return cpu_s,rss_kb

def parse_tokens(line):
    fields=line.strip().split("\t")
    output={}
    for entry in fields[1:]:
        if "=" not in entry:
            raise ValueError("Invalid diagnostic token: "+entry[:70])
        k,v=entry.split("=",1)
        if k in output:
            raise ValueError("Duplicate key: "+k)
        output[k]=v
    return output

def execute(binary,cnf,case,mode,seed,out):
    stem=case+"_"+mode
    trace_path=out/(stem+".trace.log")
    samples_path=out/(stem+".samples.jsonl")
    start=time.perf_counter()
    peak=0
    last_cpu=None
    sample_count=0
    timed_out=False
    with trace_path.open("w",encoding="utf8") as logfile, samples_path.open("w",encoding="utf8") as sampler:
        proc=subprocess.Popen([str(binary),mode,str(cnf),str(seed)],
            stdout=logfile,stderr=subprocess.STDOUT,start_new_session=True)
        while True:
            elapsed=time.perf_counter()-start
            if elapsed>=CAP:
                timed_out=proc.poll() is None
                if timed_out:
                    os.killpg(proc.pid,signal.SIGKILL)
                proc.wait()
                break
            try:
                proc.wait(timeout=min(10.0,CAP-elapsed))
                break
            except subprocess.TimeoutExpired:
                cpu,rss=cpu_and_rss(proc.pid)
                last_cpu=cpu if cpu is not None else last_cpu
                peak=max(peak,rss or 0)
                sample_count+=1
                snap={"elapsed_s":round(time.perf_counter()-start,3),
                      "cpu_s":cpu,"rss_kb":rss}
                sampler.write(json.dumps(snap)+"\n")
                sampler.flush()
                if sample_count%3==0:
                    print("V81_HEARTBEAT",case[:8],mode,snap,flush=True)
    wall=time.perf_counter()-start
    lines=trace_path.read_text(errors="replace").splitlines()
    stage_rows=[parse_tokens(x) for x in lines if x.startswith("DRNAS_STAGE\t")]
    final_rows=[parse_tokens(x) for x in lines if x.startswith("DRNAS_CAUSAL\t")]
    if timed_out:
        status="TIMEOUT"
        err=""
    elif proc.returncode!=0:
        status="ERROR"
        err="Process exit code "+str(proc.returncode)+"; "+str(lines[-3:])[:350]
    elif len(final_rows)!=1 or final_rows[0].get("mode")!=mode:
        status="ERROR"
        err="Expected exactly one matching final diagnostic row"
    elif final_rows[0].get("answer") not in ("SAT","UNSAT"):
        status="ERROR"
        err="Invalid solver final answer"
    else:
        status=final_rows[0]["answer"]
        err=""
    gate=next((x for x in reversed(stage_rows) if x.get("stage")=="gate"),{})
    return dict(case=case,sha256="",seed=seed,mode=mode,status=status,
        wall_s=round(min(wall,CAP) if timed_out else wall,4),
        cpu_s_last=last_cpu,peak_rss_kb=peak or None,
        sample_count=sample_count,
        last_stage=stage_rows[-1].get("stage","") if stage_rows else "unavailable",
        stages=">".join(x.get("stage","") for x in stage_rows),
        extended=final_rows[0].get("extended","") if status in ("SAT","UNSAT") else gate.get("extend",""),
        gate_reason=final_rows[0].get("gate_reason","") if status in ("SAT","UNSAT") else gate.get("reason",""),
        timeout_cap_s=CAP,error=err,trace_path=str(trace_path),
        samples_path=str(samples_path))

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--sources",required=True)
    p.add_argument("--binary",required=True)
    p.add_argument("--case-id",required=True)
    p.add_argument("--outdir",required=True)
    a=p.parse_args()
    if a.case_id not in HARD_CASES:
        raise RuntimeError("Instance is not in the predeclared hard SAT set")
    out=Path(a.outdir)
    out.mkdir(parents=True,exist_ok=True)
    choices=json.loads(Path(a.sources).read_text())
    selected=[x for x in choices if x["id"]==a.case_id]
    if len(selected)!=1:
        raise RuntimeError("Selected hard CNF missing from official manifest")
    item=selected[0]
    cnf=Path(item["path"])
    sha=hashlib.sha256(cnf.read_bytes()).hexdigest()
    if sha!=item["sha256"]:
        raise RuntimeError("CNF SHA256 does not match pinned previous run")
    seed=(7707000+int(a.case_id[:8],16))%2**32
    order=list(MODES)
    random.Random(81002026+int(a.case_id[:8],16)).shuffle(order)
    rows=[]
    with (out/"v81_raw.csv").open("w",encoding="utf8",newline="") as csvfile:
        writer=csv.DictWriter(csvfile,fieldnames=FIELDS)
        writer.writeheader()
        for mode in order:
            row=execute(Path(a.binary).resolve(),cnf,a.case_id,mode,seed,out)
            row["sha256"]=sha
            rows.append(row)
            writer.writerow(row)
            csvfile.flush()
            print("V81",a.case_id,seed,mode,row["status"],
                  f'{row["wall_s"]:.3f}s',
                  "last_stage",row["last_stage"],
                  "gate",row["gate_reason"],
                  "max_rss_kb",row["peak_rss_kb"],flush=True)
    solved={r["status"] for r in rows if r["status"] in ("SAT","UNSAT")}
    if len(solved)>1:
        raise RuntimeError("CONTRADICTORY SOLVER ANSWERS; see saved raw traces")
    scores={r["mode"]:(r["wall_s"] if r["status"] in ("SAT","UNSAT") else 2*CAP) for r in rows}
    summary={
       "experiment":"v8.1-hard300-diagnostic-pilot",
       "retrospective":True,
       "instance":a.case_id,"official_sha256":sha,
       "seed":seed,"wall_cap_seconds":CAP,
       "modes":list(MODES),"rows":rows,
       "par2_seconds":scores,
       "limitations":[
          "Six previously examined official 2026 CNFs are not a blind holdout.",
          "One fixed paired seed per case is a diagnostic pilot, not a performance distribution.",
          "The first-stage conflict checkpoint is 256, extension budget is 768; no internal conflict rate is inferred from CPU sampling.",
          "Process CPU and memory are external Linux /proc samples and may miss peaks.",
          "Frozen v7.6/v7.7 and CaDiCaL plain do not emit intermediate checkpoints.",
          "Timeouts are unknown, not SAT or UNSAT; PAR2 penalty is 600s per timeout.",
          "SAT responses validated by the existing native model checker; UNSAT results are not independently proof certified.",
          "No claims about asymptotic complexity or general solver superiority."
       ]
    }
    (out/"v81_summary.json").write_text(json.dumps(summary,indent=2))
    lines=["# DRNAS v8.1 — 300-second hard-instance diagnostic",
           "Original 2026 GBD ID: "+a.case_id,"Verified DIMACS SHA256: "+sha,
           "Previously examined instance; one paired seed, no holdout claim.",
           "","| Mode | Result | Wall (s) | Last checkpoint | Gate reason | Peak RSS KiB |",
           "|---|---|---:|---|---|---:|"]
    for row in sorted(rows,key=lambda x:MODES.index(x["mode"])):
        lines.append(f'| {row["mode"]} | {row["status"]} | {row["wall_s"]:.2f} | {row["last_stage"]} | {row["gate_reason"] or "-"} | {row["peak_rss_kb"] or "-"} |')
    (out/"v81_report.md").write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)
    if any(r["status"]=="ERROR" for r in rows):
        raise RuntimeError("One or more solvers failed; see trace files")

if __name__=="__main__":
    main()
