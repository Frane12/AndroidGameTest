#!/usr/bin/env python3
"""DRNAS SAT v8.2 delayed phase hint selection pilot on verified original CNFs.
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

CAP=60
MODES=("orig_v76","ca_plain","v82_late_guarded","v82_late_durable","v82_late_never")
TEST_CASES={
    "4ae685a11b5cecca76dc3d463481ce92",
    "0c9da400944b002f90fd385d4fdab385",
    "0e06895600b5cd0b6fadb87e17bf8145",
}
FIELDS=("case","sha256","seed","repeat","mode","status","wall_s","cpu_s_last",
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
    stem=case+"_"+str(seed)+"_"+mode
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
    global CAP
    p=argparse.ArgumentParser()
    p.add_argument("--sources",required=True)
    p.add_argument("--binary",required=True)
    p.add_argument("--case-id",required=True)
    p.add_argument("--outdir",required=True)
    p.add_argument("--cap",type=int,required=True,choices=(60,300))
    p.add_argument("--repeats",type=int,required=True,choices=(1,2,3))
    a=p.parse_args()
    CAP=a.cap
    if a.case_id not in TEST_CASES:
        raise RuntimeError("The selected CNF is not in the frozen v8.2 diagnostic manifest")
    items=json.loads(Path(a.sources).read_text())
    chosen=[x for x in items if x["id"]==a.case_id]
    if len(chosen)!=1:
        raise RuntimeError("Expected one original CNF in selected official shard")
    case=chosen[0]
    cnf=Path(case["path"])
    sha=hashlib.sha256(cnf.read_bytes()).hexdigest()
    if sha!=case["sha256"]:
        raise RuntimeError("Original DIMACS checksum mismatch")
    out=Path(a.outdir)
    out.mkdir(parents=True,exist_ok=True)
    print("V82_CONFIG",a.case_id,"cap",CAP,"repeats",a.repeats,flush=True)
    results=[]
    with (out/"v82_raw.csv").open("w",newline="",encoding="utf8") as f:
        writer=csv.DictWriter(f,fieldnames=FIELDS)
        writer.writeheader()
        for rep in range(a.repeats):
            seed=(7707000+rep*527+int(a.case_id[:8],16))%2**32
            order=list(MODES)
            random.Random(82002026+int(a.case_id[:8],16)+rep*733).shuffle(order)
            rep_results=[]
            for mode in order:
                row=execute(Path(a.binary).resolve(),cnf,a.case_id,mode,seed,out)
                row.update(sha256=sha,repeat=rep)
                rep_results.append(row)
                results.append(row)
                writer.writerow({k:row.get(k,"") for k in FIELDS})
                f.flush()
                print("V82_RESULT",a.case_id,"rep",rep,seed,mode,row["status"],
                      f'{row["wall_s"]:.4f}s',"stage",row["last_stage"],
                      "gate",row["gate_reason"],flush=True)
            answers={x["status"] for x in rep_results if x["status"] in ("SAT","UNSAT")}
            if len(answers)>1:
                raise RuntimeError("Contradictory SAT/UNSAT results in same seed")
    if len({x["status"] for x in results if x["status"] in ("SAT","UNSAT")})>1:
        raise RuntimeError("Contradictory answers across all seeds")
    scores={}
    for mode in MODES:
        mode_rows=[r for r in results if r["mode"]==mode]
        if len(mode_rows)!=a.repeats:
            raise RuntimeError("Incomplete mode coverage")
        costs=[r["wall_s"] if r["status"] in ("SAT","UNSAT") else 2*CAP for r in mode_rows]
        scores[mode]={
            "median_par2_s":round(statistics.median(costs),5),
            "solved":sum(r["status"] in ("SAT","UNSAT") for r in mode_rows),
            "timeouts":sum(r["status"]=="TIMEOUT" for r in mode_rows),
            "errors":sum(r["status"]=="ERROR" for r in mode_rows)}
    summary={
        "version":"v8.2-delayed-phase-experimental",
        "source_id":a.case_id,"sha256":sha,"cap_seconds":CAP,
        "repeats":a.repeats,"rows":results,"scores":scores,
        "retrospective":True,"training_on_results":False,
        "limits":[
            "Previously examined official 2026 cases, not a blind holdout.",
            "A 256-conflict plain prefix is NOT identical to unsplit CaDiCaL plain.",
            "Late hints cannot reverse already learned clauses or search decisions.",
            "Learner short-clause offers are not LBD.",
            "A TIMEOUT means unknown; PAR2 penalty is twice the cap.",
            "Model checking verifies SAT solutions, but UNSAT remains an unverified native solver answer.",
            "Original v7.6 and v7.7 source blobs are untouched."
        ]
    }
    (out/"v82_summary.json").write_text(json.dumps(summary,indent=2))
    lines=["# DRNAS SAT v8.2 Delayed Phase Activation","",
           "2026 CNF: "+a.case_id,
           "SHA256: "+sha,
           f"Previously examined; paired {a.repeats} repeats; cap {CAP}s","",
           "| Repeat / mode | Result | Wall (s) | Last stage | Gate | Peak RSS (KiB) |",
           "|---|---|---:|---|---|---:|"]
    for r in sorted(results,key=lambda x:(x["repeat"],MODES.index(x["mode"]))):
        lines.append(f'| {r["repeat"]} / {r["mode"]} | {r["status"]} | {r["wall_s"]:.2f} | {r["last_stage"]} | {r["gate_reason"] or "-"} | {r["peak_rss_kb"] or "-"} |')
    lines+=["","## Mode median PAR-2 (seconds)"]
    for mode in MODES:
        lines.append(f'- {mode}: {scores[mode]["median_par2_s"]:.3f}, solved {scores[mode]["solved"]}/{a.repeats}')
    (out/"v82_report.md").write_text("\n".join(lines)+"\n")
    print("\n".join(lines),flush=True)
    if any(r["status"]=="ERROR" for r in results):
        raise RuntimeError("Solver failure recorded; inspect raw traces")

if __name__=="__main__":
    main()
