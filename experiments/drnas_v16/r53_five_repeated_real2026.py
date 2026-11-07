#!/usr/bin/env python3
"""R53: five matched randomized repeats of R52's target breakthrough and regression.

Use same R52 SHA-locked original SATComp2026 CNFs and fixed pinned solver
binaries. The positive and negative cases are POST-HOC selected based on R52
outcomes. These repeats assess stability, NOT generalization or world rank.
40s total wall budget includes R49 preprocessing and SAT witness verification.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import random
import statistics
import subprocess
import tempfile
import time
import resource
import r49_pivot_coherence_gate as r49
import r32p_real_satcomp26_benchmark as proof

PROTO="DRNAS-R53-FIVE-REPEATS-POSTHOC-20261103-v1"
PARENT="DRNAS-R52-PROSPECTIVE-2026-TOPREFS-20261103-v1"
SOURCE_RUN=41684183452
CAP=40.0
REPS=5
MODES=("kissat_original","drnas_r49_gate","cadical_3_0_1")
CASES=(
  ("2b35377a7b95f24449a3b607b61fff05",
   "aa490f53e57c5119ac846f54dd2567d200824610ecdc92cae99098c5b0e5c1d4",
   "breakthrough_R52"),
  ("262a226a47330987f038128579967405",
   "1883d4efd956602fed6397626c9b2f7359609cd54784bf3d7701a1c1a837c7d2",
   "regression_R52"),
)
CHECKED_SHA={x[0]:x[1] for x in CASES}

def check(condition,msg):
    if not condition: raise RuntimeError("R53_AUDIT_FAIL: "+str(msg))

def digest(p):
    return r49.sha(p)

def freeze(args):
    src=Path(args.sources)
    manifest=json.loads((src/"manifest.json").read_text())
    check(manifest["protocol"]==PARENT,"R52 manifest not pinned")
    originals={x["gbd"]:x for x in manifest["cases"]}
    check(len(originals)==11 and len(set(x["sha256"] for x in originals.values()))==11,
          "Expected exact eleven source hashes from R52")
    selected=[]
    for g,expected,cohort in CASES:
        check(g in originals and originals[g]["sha256"]==expected,
             "selected R52 source differs from precommitted SHA")
        original=src/originals[g]["name"]
        check(digest(original)==expected,"source modified")
        plan=r49.compute_plan(original)
        check(plan["gate"],"Selected cases must actually activate R49 gate")
        check(len(plan["clauses"])==40,"Expected 40 audited derived clauses")
        selected.append(dict(gbd=g,sha256=expected,cohort=cohort,
            name=originals[g]["name"],gate=plan["gate"],
            derived=len(plan["clauses"]),pivot_dominance=plan["dominance"],
            cert_sha=plan["certificate_sha256"]))
    output=Path(args.output)
    output.parent.mkdir(parents=True,exist_ok=True)
    data=dict(protocol=PROTO,parent_run=SOURCE_RUN,
         original_manifest_sha=digest(src/"manifest.json"),
         selected_for_R52_outcome=True,blind=False,
         cap_s=CAP,repetitions=REPS,modes=list(MODES),cases=selected,
         limitations=["Post-hoc selected positive and regression cases",
           "SAT witness verification checked against unchanged source",
           "UNSAT without independent LRAT, compare verdicts",
           "Single GitHub runner core per case, same pinned binaries and memory cap",
           "Not a competition leaderboard or population wide evaluation"])
    output.write_text(json.dumps(data,indent=2)+"\n")
    print("R53_FROZEN_PASS",len(selected),"exact archived sources",flush=True)

def memcap():
    resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))

def one(original,mode,binaries,plan):
    t0=time.monotonic()
    answer="TIMEOUT";added=0
    with tempfile.TemporaryDirectory(prefix="drnas-r53-") as directory:
        source=original
        if mode=="drnas_r49_gate":
            actual=r49.compute_plan(original)
            check(actual["gate"] and actual["certificate_sha256"]==plan["cert_sha"],
                  "precommitted R49 mathematical proof drift")
            derived=r49.selection("gate",actual)
            check(len(derived)==40,"R49 policy not activated")
            source=Path(directory)/"augmented.cnf"
            audit=r49.r48.safe_rewrite(original,source,derived)
            check(audit["added"]==len(derived),"incorrect rewrite")
            added=len(derived)
        prep_s=time.monotonic()-t0
        if prep_s<CAP:
            try:
                binary=binaries["cadical"] if mode=="cadical_3_0_1" else binaries["kissat"]
                p=subprocess.run([str(binary),str(source)],
                        capture_output=True,text=True,errors="replace",
                        timeout=CAP-prep_s,preexec_fn=memcap)
                check(p.returncode in (10,20),
                      "wrong solver exit "+str(p.returncode)+": "+p.stderr[-200:])
                answer="SAT" if p.returncode==10 else "UNSAT"
                if answer=="SAT":
                    proof.verify_sat_witness(original,p.stdout)
            except subprocess.TimeoutExpired:
                answer="TIMEOUT"
        elapsed=time.monotonic()-t0
    if elapsed>CAP:answer="TIMEOUT"
    wall=min(elapsed,CAP)
    return dict(answer=answer,wall_s=round(wall,6),
      prep_s=round(prep_s,6),par2_s=round(wall if answer!="TIMEOUT" else 2*CAP,6),
      added=added)

def run(args):
    src=Path(args.sources);pre=Path(args.design)
    design=json.loads(pre.read_text())
    check(design["protocol"]==PROTO
      and design["original_manifest_sha"]==digest(src/"manifest.json"),
      "frozen design mismatch")
    check(args.case_index in (0,1),"case index invalid")
    plan=design["cases"][args.case_index]
    g,sha,_=CASES[args.case_index]
    check(g==plan["gbd"] and sha==plan["sha256"],"wrong chosen case")
    original=src/plan["name"]
    check(digest(original)==sha,"unmodified R52 original SHA mismatch")
    bins={k:Path(getattr(args,k)).resolve() for k in ("kissat","cadical")}
    check(all(x.is_file() for x in bins.values()),"binary missing")
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    out=Path(args.out)
    out.mkdir(parents=True,exist_ok=True)
    metadata=dict(protocol=PROTO,case_index=args.case_index,
      case_gbd=g,source_sha=sha,
      design_sha=digest(pre),
      binaries_sha={k:digest(v) for k,v in bins.items()},
      cpu_affinity=list(os.sched_getaffinity(0)),
      runner=os.getenv("RUNNER_NAME","local"),
      repeats=REPS,cap_s=CAP)
    (out/"meta.json").write_text(json.dumps(metadata,indent=2)+"\n")
    rows=[]
    for rep in range(REPS):
        order=list(MODES)
        rnd=int(hashlib.sha256((PROTO+sha+":"+str(rep)).encode()).hexdigest(),16)
        random.Random(rnd).shuffle(order)
        for mode in order:
            r=one(original,mode,bins,plan)
            rows.append(dict(gbd=g,cohort=plan["cohort"],rep=rep,
                    mode=mode,source_sha=sha,**r))
            print("R53_TRIAL",plan["cohort"],"rep",rep,mode,r["answer"],
                  r["wall_s"],"PAR2",r["par2_s"],"added",r["added"],flush=True)
            (out/"rows.json").write_text(json.dumps(rows,indent=2)+"\n")
    check(len(rows)==REPS*len(MODES),"not all repeats")

def audit(args):
    design=json.loads(Path(args.design).read_text())
    check(design["protocol"]==PROTO,"wrong design")
    sha=digest(args.design)
    rows=[];solver_shas=set()
    for idx in (0,1):
        folder=Path(args.combined)/("r53-case-"+str(idx))/"results"
        meta=json.loads((folder/"meta.json").read_text())
        check(meta["protocol"]==PROTO and meta["case_index"]==idx
          and meta["design_sha"]==sha and
          meta["source_sha"]==design["cases"][idx]["sha256"],
          "source or design drift")
        solver_shas.add(json.dumps(meta["binaries_sha"],sort_keys=True))
        records=json.loads((folder/"rows.json").read_text())
        check(len(records)==REPS*len(MODES),"incomplete repeated case")
        rows.extend(records)
    check(len(solver_shas)==1 and len(rows)==2*REPS*len(MODES),
          "missing trial or inconsistent binaries")
    results={}
    for case in design["cases"]:
        rr=[r for r in rows if r["gbd"]==case["gbd"]]
        check(len(rr)==REPS*len(MODES),"missing case")
        index={}
        for rep in range(REPS):
            trial={r["mode"]:r for r in rr if r["rep"]==rep}
            check(set(trial)==set(MODES),"incomplete paring")
            check(all(r["source_sha"]==case["sha256"] for r in trial.values()),
                  "sha mismatch")
            check(len({r["answer"] for r in trial.values()
                       if r["answer"]!="TIMEOUT"})<=1,"inconsistent SAT result")
            index[rep]=trial
        bymode={}
        for mode in MODES:
            z=[index[rep][mode] for rep in range(REPS)]
            bymode[mode]=dict(solved=sum(r["answer"]!="TIMEOUT" for r in z),
                timeouts=sum(r["answer"]=="TIMEOUT" for r in z),
                par2_sum_s=round(sum(r["par2_s"] for r in z),6),
                median_wall_s=round(statistics.median(r["wall_s"] for r in z),6),
                min_wall_s=round(min(r["wall_s"] for r in z),6),
                max_wall_s=round(max(r["wall_s"] for r in z),6))
        base=bymode["kissat_original"]["par2_sum_s"]
        for d in bymode.values():
            d["delta_vs_kissat_pct"]=round(100*(d["par2_sum_s"]/base-1),4)
        results[case["cohort"]]=dict(gbd=case["gbd"],summary=bymode)
    report=dict(protocol=PROTO,source_run=SOURCE_RUN,
       cases=results,rows=rows,
       all_binaries_sha=json.loads(next(iter(solver_shas))),
       protocol_notes=design["limitations"])
    Path(args.json).write_text(json.dumps(report,indent=2)+"\n")
    lines=["# R53 — Five paired repeats of two R52 outcome-selected formulas",
         "Two original SATComp2026 CNFs, same source SHA and pinned binaries.",
         "Each paired attempt has 40s total cap including R49 40-clause preprocessing;",
         "PAR2 gives 80s to a timeout. No claim of new blind generalization.",""]
    for key,data in results.items():
        lines.extend(["## "+key+" — "+data["gbd"],
           "| Method | Solved | Median wall s | PAR2 sum s | Delta vs pinned Kissat |",
           "|---|---:|---:|---:|---:|"])
        for mode in MODES:
            q=data["summary"][mode]
            lines.append(f'| {mode} | {q["solved"]}/{REPS} | {q["median_wall_s"]:.3f} | {q["par2_sum_s"]:.3f} | {q["delta_vs_kissat_pct"]:+.2f}% |')
        lines+=["","| Rep | Kissat s | R49 gate s | CaDiCaL s |",
                 "|---:|---:|---:|---:|"]
        for rep in range(REPS):
            sub={r["mode"]:r for r in rows
                 if r["gbd"]==data["gbd"] and r["rep"]==rep}
            value=lambda mode: ("TIMEOUT (40)" if sub[mode]["answer"]=="TIMEOUT"
                                else f'{sub[mode]["wall_s"]:.3f}')
            lines.append(f'| {rep+1} | {value("kissat_original")} | {value("drnas_r49_gate")} | {value("cadical_3_0_1")} |')
        lines.append("")
    Path(args.md).write_text("\n".join(lines)+"\n")
    print("R53_FINAL_AUDIT_PASS",json.dumps(results),flush=True)

def main():
    p=argparse.ArgumentParser()
    subs=p.add_subparsers(dest="cmd",required=True)
    f=subs.add_parser("freeze")
    f.add_argument("--sources",required=True)
    f.add_argument("--output",required=True)
    m=subs.add_parser("measure")
    for name in ("sources","design","kissat","cadical","out"):
        m.add_argument("--"+name,required=True)
    m.add_argument("--case-index",required=True,type=int)
    a=subs.add_parser("audit")
    for name in ("design","combined","json","md"):
        a.add_argument("--"+name,required=True)
    args=p.parse_args()
    if args.cmd=="freeze":freeze(args)
    elif args.cmd=="measure":run(args)
    else:audit(args)

if __name__=="__main__":main()
