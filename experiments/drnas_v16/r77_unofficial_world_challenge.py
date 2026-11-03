#!/usr/bin/env python3
"""R77 informal same-runner SAT comparison: original, R65 XOR/CNF, CaDiCaL 3.0.1.

Ten newly selected SAT Competition 2025 ORIGINAL input CNFs, no baseline runtime
prescreen, all documented prior R63/66/67/72/73 IDs and SHA-256 excluded.
This is a recreational, NON-OFFICIAL comparison, not a world-record claim.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import random
import signal
import subprocess
import tempfile
import time

import r73_fresh_quick_unseen_2025 as old
import r71_bcp_15sec_eight_formulas as r71
import r64_mixed_xor_implied as r64
import r32p_real_satcomp26_benchmark as r32p

PROTO="DRNAS-R77-UNOFFICIAL-10-FRESH-2025-20261104-v1"
SALT="DRNAS-R77-UNSCREENED-NONREUSE-20261104-v1"
N=10
REPS=2
CAP=30.0
MODES=("clean_kissat","drnas_r65_full","cadical_301")

def check(ok,msg):
    if not ok:
        raise RuntimeError("R77_FAIL_CLOSED "+str(msg))

def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for block in iter(lambda:f.read(1<<20),b""):
            h.update(block)
    return h.hexdigest()

def frozen(args):
    p=Path(args.r73)/"new"/"manifest.json"
    check(p.exists(),"prior R73 manifest missing")
    m=json.loads(p.read_text())
    check(m["protocol"]=="DRNAS-R73-NEVER-SEEN-5TO30S-20261103-v1" and
          m["ready"]==8 and len(m["cases"])==8,"prior R73 cohort invalid")
    attempted={x["gbd"] for x in m["selection_attempts"]}
    attempted|={x["gbd"] for x in m["cases"]}
    accepted_hashes={x["sha256"] for x in m["cases"]}
    check(len(attempted)>=8 and len(accepted_hashes)==8,
          "prior R73 identities incomplete")
    previous=old.history
    def with_r73_history(namespace):
        seen,shas,binary_sha,registry=previous(namespace)
        check(not (seen & {x["gbd"] for x in m["cases"]}),
              "R73 accepted ID collides with prior registry")
        check(not (shas & accepted_hashes),
              "R73 accepted SHA collides with prior registry")
        registry["r73_previous_manifest_sha256"]=sha(p)
        registry["r73_prior_attempted_ids"]=len(attempted)
        registry["r73_prior_accepted_sha256"]=len(accepted_hashes)
        return seen|attempted,shas|accepted_hashes,binary_sha,registry
    old.history=with_r73_history
    old.N=N
    old.REPS=REPS
    old.SHARDS=N
    old.BENCH_CAP=CAP
    old.PROTO=PROTO
    old.SALT=SALT
    old.MAX_2025_ATTEMPTS=48
    old.freeze(args)
    manifest=Path(args.out)/"manifest.json"
    j=json.loads(manifest.read_text())
    check(j["ready"]==N and len(j["cases"])==N,
          "not all 10 fresh formulas selected")
    check(not {c["gbd"] for c in j["cases"]}&attempted,
          "R73 attempted source repeated")
    check(not {c["sha256"] for c in j["cases"]}&accepted_hashes,
          "R73 source SHA repeated")
    j["modes"]=list(MODES)
    j["bench_cap_s"]=CAP
    j["runner_year"]=2026
    j["source_cohort"]="SAT Competition 2025 input collection; no official ranking"
    j["unofficial_world_challenge"]=True
    j["limitations"]+= [
        "CaDiCaL 3.0.1 is a known reference solver, not a claim to be the top 2026 winner.",
        "The 2025 original benchmark CNFs are not claimed never to have been used by other researchers.",
        "Not all disconnected historical internal experiments can be excluded.",
        "No official scores/hardware equivalence with world-record submissions.",
        "UNSAT verdicts require independent proof/official-label validation for external correctness.",
        "Unscreened 10-source sample, two seeds, 30s cap: cannot establish world ranking."
    ]
    manifest.write_text(json.dumps(j,indent=2,sort_keys=True)+"\n")
    print("R77_FREEZE_PASS",json.dumps(dict(sources=N,
        excluded_R73_attempts=len(attempted),
        excluded_R73_sha=len(accepted_hashes),
        older_excluded=j["prior_gbd_exclusion_count"],
        prescreen=False)),flush=True)

def solve(binary,input_cnf,original):
    started=time.monotonic()
    with subprocess.Popen([str(binary),str(input_cnf)],stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,text=True,errors="replace",preexec_fn=old.r63.child) as p:
        try:
            stdout,stderr=p.communicate(timeout=CAP)
            timeout=False
        except subprocess.TimeoutExpired:
            timeout=True
            p.send_signal(signal.SIGINT)
            try:
                stdout,stderr=p.communicate(timeout=0.35)
            except subprocess.TimeoutExpired:
                p.kill()
                stdout,stderr=p.communicate()
    elapsed=time.monotonic()-started
    answer="UNKNOWN"
    if not timeout:
        check(p.returncode in (10,20),
              "solver unexpected exit "+str(p.returncode)+" "+stderr[-300:])
        answer="SAT" if p.returncode==10 else "UNSAT"
        if answer=="SAT":
            r32p.verify_sat_witness(original,stdout)
    return answer,elapsed,timeout

def measure(args):
    root=Path(args.sources)
    j=json.loads((root/"manifest.json").read_text())
    check(j["protocol"]==PROTO and j["ready"]==N,"manifest protocol/size")
    check(0<=args.shard<N,"shard out of range")
    check(len({c["sha256"] for c in j["cases"]})==N,"duplicate CNF")
    pin=Path(args.binaries)/"binary.sha256"
    check(pin.exists(),"missing executable provenance")
    subprocess.run(["sha256sum","-c",str(pin.resolve())],cwd=args.binaries,check=True,
                   capture_output=True,text=True)
    kissat=(Path(args.binaries)/"kissat").resolve()
    cadical=(Path(args.binaries)/"cadical").resolve()
    check(sha(kissat)==j["registry"]["binary_sha"],"Kissat not exact prior pin")
    check(kissat.is_file() and cadical.is_file(),"missing baselines")
    case=j["cases"][args.shard]
    source=root/case["filename"]
    check(sha(source)==case["sha256"],"source drift")
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    import r65_xor_cnf_feedback as r65
    r65.MAX_PREP_S=2.0
    src,cnf,added,filtered,stats=r71.prepare(root,case)
    with tempfile.TemporaryDirectory(prefix="r77-") as tmp:
        full=Path(tmp)/"xor-augmented.cnf"
        if added:
            r64.augment(source,full,case["variables"],case["clauses"],added)
        else:
            full=source
        inputs={"clean_kissat":(kissat,source,0.0),
                "drnas_r65_full":(kissat,full,float(stats["prep_s"])),
                "cadical_301":(cadical,source,0.0)}
        rows=[]
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(int(hashlib.sha256(
                (PROTO+case["sha256"]+str(rep)).encode()).hexdigest(),16)).shuffle(modes)
            for mode in modes:
                binary,cnf_path,overhead=inputs[mode]
                answer,wall,timed_out=solve(binary,cnf_path,source)
                end=wall+overhead
                solved=answer!="UNKNOWN" and end<=CAP
                row=dict(source_id=case["gbd"],source_sha256=case["sha256"],
                    source_year=2025,rep=rep,mode=mode,answer=answer,
                    timeout=not solved,wall_s=round(wall,6),
                    preprocessing_s=round(overhead,6),
                    end_to_end_s=round(end,6),
                    par2_s=round(end if solved else 2*CAP,6),
                    binary_sha256=sha(binary),runner=os.getenv("RUNNER_NAME",""),
                    commit=os.getenv("GITHUB_SHA",""),
                    actions_run_id=os.getenv("GITHUB_RUN_ID",""))
                rows.append(row)
                print("R77_TRIAL",json.dumps({k:row[k] for k in
                    ("source_id","rep","mode","answer","end_to_end_s","par2_s")}),flush=True)
    check(len(rows)==len(MODES)*REPS,"partial paired run")
    # A SAT/UNSAT contradiction among completed methods is always disqualifying.
    answers={x["answer"] for x in rows if x["answer"]!="UNKNOWN"}
    check(len(answers)<=1,"contradictory solver verdicts")
    out=Path(args.out)
    out.mkdir(parents=True,exist_ok=True)
    packet=dict(protocol=PROTO,shard=args.shard,case=case,
        source_sha256=sha(source),results=rows,
        binaries={k:sha(v) for k,v in [("kissat",kissat),("cadical",cadical)]},
        augmented_clauses=len(added),prep_statistics=stats)
    (out/"r77-shard.json").write_text(json.dumps(packet,indent=2)+"\n")
    print("R77_SHARD_PASS",args.shard,len(rows),flush=True)

def audit(args):
    j=json.loads((Path(args.sources)/"manifest.json").read_text())
    check(j["protocol"]==PROTO and j["ready"]==N,"invalid frozen cohort")
    allrows=[]
    pins=set()
    for i in range(N):
        p=Path(args.combined)/f"r77-shard-{i}"/"results"/"r77-shard.json"
        check(p.is_file(),"missing shard "+str(i))
        v=json.loads(p.read_text())
        c=j["cases"][i]
        check(v["protocol"]==PROTO and v["shard"]==i
              and v["source_sha256"]==c["sha256"],"SHA or shard drift")
        pins.add(tuple(sorted(v["binaries"].items())))
        rows=v["results"]
        check(len(rows)==REPS*len(MODES),"incomplete matched rows")
        for rep in range(REPS):
            group=[r for r in rows if r["rep"]==rep]
            check(len(group)==len(MODES)
                  and {r["mode"] for r in group}==set(MODES),
                  "mode pairing missing")
            answers={r["answer"] for r in group if r["answer"]!="UNKNOWN"}
            check(len(answers)<=1,"contradictory SAT/UNSAT")
        check(all(r["source_sha256"]==c["sha256"]
                  and r["source_id"]==c["gbd"]
                  and r["commit"] for r in rows),"source/commit provenance missing")
        allrows+=rows
    check(len(pins)==1 and len(allrows)==N*REPS*len(MODES),
          "binary SHA drift or trial count")
    summary={}
    for mode in MODES:
        rows=[r for r in allrows if r["mode"]==mode]
        summary[mode]=dict(trials=len(rows),
            solved=sum(not r["timeout"] for r in rows),
            timeouts=sum(r["timeout"] for r in rows),
            par2_s=round(sum(r["par2_s"] for r in rows),6),
            fastest_s=min((r["end_to_end_s"] for r in rows if not r["timeout"]),default=None))
    base=summary["clean_kissat"]["par2_s"]
    for mode in MODES[1:]:
        summary[mode]["par2_gain_vs_kissat_pct"]=round(
            100*(base-summary[mode]["par2_s"])/base,5)
    report=dict(protocol=PROTO,status="PASS_UNOFFICIAL",sources=N,
        attempts=len(allrows),year=2025,repeats=REPS,cap_s=CAP,
        prescreen=False,official_world_record=False,
        source_manifest_sha256=sha(Path(args.sources)/"manifest.json"),
        source_groups=collections.Counter(c["group"] for c in j["cases"]),
        binary_sha256=dict(next(iter(pins))),summary=summary,
        all_rows=allrows,limitations=j["limitations"])
    out=Path(args.out)
    out.mkdir(parents=True,exist_ok=True)
    (out/"r77-final.json").write_text(json.dumps(report,indent=2)+"\n")
    md=["# R77: unofficial SAT 'world challenge' (no world-record claim)",
        "10 unscreened fresh original SAT 2025 formulas, 2 repetitions, 30s cap.",
        "Same runner family and pinned binaries; preprocessing included for R65.",
        "",
        "| Solver | Solved / 20 | Timeouts | PAR-2 seconds | Fastest solved (s) |",
        "|---|---:|---:|---:|---:|"]
    for mode,v in summary.items():
        md.append(f"| {mode} | {v['solved']}/20 | {v['timeouts']} | "
                  f"{v['par2_s']:.3f} | {v['fastest_s']} |")
    md+=["","## Limits"]+["- "+l for l in j["limitations"]]
    (out/"r77-final.md").write_text("\n".join(md)+"\n")
    print("R77_FINAL_AUDIT_PASS",json.dumps(dict(summary=summary,
        sources=N,attempts=len(allrows))),flush=True)

def main():
    parser=argparse.ArgumentParser()
    subs=parser.add_subparsers(dest="cmd",required=True)
    f=subs.add_parser("freeze")
    for x in ("r63","r66","r67","r67final","r73","kissat","out"):
        f.add_argument("--"+x,required=True)
    m=subs.add_parser("measure")
    for x in ("sources","binaries","out"):m.add_argument("--"+x,required=True)
    m.add_argument("--shard",required=True,type=int)
    a=subs.add_parser("audit")
    for x in ("sources","combined","out"):a.add_argument("--"+x,required=True)
    args=parser.parse_args()
    if args.cmd=="freeze":frozen(args)
    elif args.cmd=="measure":measure(args)
    else:audit(args)

if __name__=="__main__":
    main()
