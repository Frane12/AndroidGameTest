#!/usr/bin/env python3
"""R51: same exact eight SHA-pinned official SATComp26 CNFs, four matched methods.

These are previously seen formulas from R47/R49, not blind and not a claim
against the official 5000s contest. Single pinned clean Kissat executable.
All source preprocessing overhead is included in the same 30s cap.
R49 resolvents are checked from two-clause proofs; GF2 short parity cuts
have an independently verified original-CNF certificate.
"""
import argparse
import hashlib
import json
import os
import random
import subprocess
import tempfile
import time
from pathlib import Path
import r49_pivot_coherence_gate as r49
import r32t_certified_short_xor as gf2

CAP=30.0
SHARDS=4
MODES=("clean","r49_gate","r49_pivot16","r32t_certified_xor")
PROTO="DRNAS-R51-SAME8-REAL2026-FOUR-METHOD-20261103-v1"

def chk(ok,msg):
    if not ok: raise RuntimeError("R51_AUDIT_FAIL "+str(msg))

def digest(p):
    return r49.sha(p)

def freeze(a):
    src=Path(a.sources)
    mm=r49.cases(src)
    out=Path(a.out)
    out.mkdir(parents=True,exist_ok=True)
    (out/"aug").mkdir(exist_ok=True)
    (out/"cert").mkdir(exist_ok=True)
    entries=[]
    for c in mm["cases"]:
        original=src/c["name"]
        plan=r49.compute_plan(original)
        augmented=out/"aug"/c["name"]
        cert=out/"cert"/(c["gbd"]+".json")
        t0=time.monotonic()
        result=gf2.build(original,augmented,cert)
        prep=time.monotonic()-t0
        gf2.audit(original,augmented,cert)
        chk(result["sha256_original"]==c["sha256"],"original altered")
        entries.append(dict(name=c["name"],gbd=c["gbd"],sha256=c["sha256"],
             rank=result["rank"],xor_axioms=result["axioms"],
             xor_added=result["added_clauses"],xor_chosen=result["chosen_short_equations"],
             xor_augmented_sha=result["sha256_augmented"],
             xor_prep_s=round(prep,6),r49_gate=plan["gate"],
             r49_derived=plan["derived"],r49_dominance=plan["dominance"],
             r49_certificate_sha=plan["certificate_sha256"]))
        print("R51_FREEZE",c["gbd"],"r49_gate",plan["gate"],
              "gf2_added",result["added_clauses"],"gf2_prep_s",round(prep,4),
              flush=True)
    chk(len(entries)==8,"expected eight identical real SATComp26 source instances")
    info=dict(protocol=PROTO,src_manifest_sha=digest(src/"manifest.json"),
              base_source_run=41669951007,source_r49_run=41676249421,
              gf2_source_commit="b29f106f12a6cfca1bd2c9f298466ce243f05271",
              cap_s=CAP,modes=MODES,shards=SHARDS,
              nonblind=True,contest_equivalence=False,
              cases=entries)
    (out/"r51-manifest.json").write_text(json.dumps(info,indent=2)+"\n")

def run(a):
    src=Path(a.sources)
    mm=r49.cases(src)
    root=Path(a.frozen)
    info=json.loads((root/"r51-manifest.json").read_text())
    chk(info["protocol"]==PROTO and info["src_manifest_sha"]==digest(src/"manifest.json"),
        "sources changed")
    chk(0<=a.shard<SHARDS,"invalid shard")
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    b=Path(a.binary).resolve()
    chk(b.is_file(),"clean Kissat binary absent")
    out=Path(a.out)
    out.mkdir(parents=True,exist_ok=True)
    (out/"meta.json").write_text(json.dumps(dict(shard=a.shard,
          binary_sha=digest(b),source_sha=info["src_manifest_sha"],
          protocol=PROTO),indent=2)+"\n")
    rows=[]
    entries=info["cases"]
    original_names={c["name"] for c in mm["cases"]}
    chk({c["name"] for c in entries}==original_names,"case identity mismatch")
    for case in entries[a.shard::SHARDS]:
        original=src/case["name"]
        augmented=root/"aug"/case["name"]
        cert=root/"cert"/(case["gbd"]+".json")
        chk(digest(original)==case["sha256"] and
            digest(augmented)==case["xor_augmented_sha"],"frozen data SHA drift")
        gf2.audit(original,augmented,cert)
        methods=list(MODES)
        random.Random(int(hashlib.sha256((PROTO+case["sha256"]).encode()).hexdigest(),16)).shuffle(methods)
        for mode in methods:
            t0=time.monotonic()
            candidate=original
            added=0
            with tempfile.TemporaryDirectory(prefix="drnas-r51-") as tmp:
                if mode=="r32t_certified_xor":
                    candidate=augmented
                    added=case["xor_added"]
                    prep=case["xor_prep_s"]
                elif mode.startswith("r49_"):
                    plan=r49.compute_plan(original)
                    chk(plan["certificate_sha256"]==case["r49_certificate_sha"] and
                        plan["gate"]==case["r49_gate"],"R49 frozen rule drift")
                    rule="gate" if mode=="r49_gate" else "pivot16"
                    derived=r49.selection(rule,plan)
                    added=len(derived)
                    if derived:
                        candidate=Path(tmp)/"candidate.cnf"
                        rw=r49.r48.safe_rewrite(original,candidate,derived)
                        chk(rw["added"]==added,"R49 incorrect clause rewrite")
                    prep=time.monotonic()-t0
                else:
                    prep=0.
                remain=CAP-prep
                answer="TIMEOUT"
                solve_elapsed=0.
                if remain>0:
                    s0=time.monotonic()
                    try:
                        p=subprocess.run([str(b),str(candidate)],
                          capture_output=True,text=True,errors="replace",
                          timeout=remain)
                        chk(p.returncode in (10,20),"Kissat failure "+str(p.returncode))
                        answer="SAT" if p.returncode==10 else "UNSAT"
                        if answer=="SAT":
                            r49.verify.verify_sat_witness(original,p.stdout)
                    except subprocess.TimeoutExpired:
                        answer="TIMEOUT"
                    solve_elapsed=time.monotonic()-s0
            elapsed=round(prep+solve_elapsed,6)
            if answer=="TIMEOUT":elapsed=min(max(elapsed,CAP),CAP)
            row=dict(gbd=case["gbd"],source_sha=case["sha256"],
                 mode=mode,answer=answer,time_s=elapsed,
                 prep_s=round(prep,6),solving_s=round(solve_elapsed,6),
                 par2_s=round(elapsed if answer!="TIMEOUT" else 2*CAP,6),
                 added=added,gate=case["r49_gate"])
            rows.append(row)
            print("R51_REAL2026_TRIAL",case["gbd"],mode,answer,
                  row["time_s"],"PAR2",row["par2_s"],"added",added,flush=True)
            (out/"rows.json").write_text(json.dumps(rows,indent=2)+"\n")
    chk(len(rows)==len(entries[a.shard::SHARDS])*len(MODES),"shard incomplete")

def audit(a):
    root=Path(a.frozen)
    info=json.loads((root/"r51-manifest.json").read_text())
    chk(info["protocol"]==PROTO,"wrong source")
    rows=[]
    hashes=set()
    for shard in range(SHARDS):
        folder=Path(a.combined)/("r51-shard-"+str(shard))/"results"
        meta=json.loads((folder/"meta.json").read_text())
        chk(meta["shard"]==shard and meta["source_sha"]==info["src_manifest_sha"],
            "incorrect shard source")
        hashes.add(meta["binary_sha"])
        entries=json.loads((folder/"rows.json").read_text())
        chk(len(entries)==2*len(MODES),"missing trials")
        rows.extend(entries)
    chk(len(hashes)==1 and len(rows)==8*len(MODES),"missing modes or mismatched Kissat")
    cases={c["gbd"]:c for c in info["cases"]}
    for gbd,case in cases.items():
        trial=[x for x in rows if x["gbd"]==gbd]
        chk(len(trial)==len(MODES) and {x["mode"] for x in trial}==set(MODES),
            "not matched per original")
        chk(all(x["source_sha"]==case["sha256"] for x in trial),"original mismatch")
        chk(len({x["answer"] for x in trial if x["answer"]!="TIMEOUT"})<=1,
            "inconsistent SAT verdicts")
    summary={}
    for mode in MODES:
        rr=[x for x in rows if x["mode"]==mode]
        summary[mode]=dict(solved=sum(x["answer"]!="TIMEOUT" for x in rr),
             timeout=sum(x["answer"]=="TIMEOUT" for x in rr),
             par2_sum_s=round(sum(x["par2_s"] for x in rr),6),
             added=sum(x["added"] for x in rr))
    base=summary["clean"]["par2_sum_s"]
    for v in summary.values():
        v["difference_vs_clean_pct"]=round(100*(v["par2_sum_s"]/base-1),4)
    report=dict(protocol=PROTO,summary=summary,rows=rows,cases=cases,
         binary_sha256=next(iter(hashes)),
         caveats=["Previously seen eight SATComp26 originals, not blind",
           "Same one-core GitHub runner and pinned clean Kissat, 30s total cap",
           "Proof audited derived CNF; SAT witnesses verified, UNSAT proof not externally checked",
           "Not a head-to-head against 2026 winners or official 5000s hardware",
           "Only R49 gate and pivot clauses, GF2 certified clauses; no native CDCL change"])
    Path(a.out).write_text(json.dumps(report,indent=2)+"\n")
    lines=["# R51 — SAME 8 REAL 2026 CNFs, FOUR METHODS (NOT BLIND)",
      "Single pinned clean Kissat, one core, 30s including preprocessing, PAR2 timeout=60s.",
      "| Solver policy | Solved / 8 | PAR2 sum seconds | Difference vs clean |",
      "|---|---:|---:|---:|"]
    for mode in MODES:
        v=summary[mode]
        lines.append(f'| {mode} | {v["solved"]}/8 | {v["par2_sum_s"]:.3f} | {v["difference_vs_clean_pct"]:+.2f}% |')
    lines.extend(["","## Per-instance wall time (seconds, TIMEOUT=30s) ",
       "| Official GBD prefix | "+" | ".join(MODES)+" |",
       "|---|"+("|---:|"*len(MODES))])
    for c in info["cases"]:
        rr={x["mode"]:x for x in rows if x["gbd"]==c["gbd"]}
        lines.append("| "+c["gbd"][:12]+" | "+" | ".join(
            f'{rr[k]["time_s"]:.3f}' if rr[k]["answer"]!="TIMEOUT" else "TIMEOUT (30)"
            for k in MODES)+" |")
    lines+=["","No official SATComp26 leaderboard rank is inferred from this pilot."]
    Path(a.markdown).write_text("\n".join(lines)+"\n")
    print("R51_AUDIT_PASS",json.dumps(summary),flush=True)

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="cmd",required=True)
    x=sub.add_parser("freeze");x.add_argument("--sources",required=True);x.add_argument("--out",required=True)
    x=sub.add_parser("measure")
    for key in ("sources","frozen","binary","shard","out"):x.add_argument("--"+key,required=True)
    x=sub.add_parser("audit")
    for key in ("frozen","combined","out","markdown"):x.add_argument("--"+key,required=True)
    a=p.parse_args()
    if a.cmd=="freeze":freeze(a)
    elif a.cmd=="measure":a.shard=int(a.shard);run(a)
    else:audit(a)

if __name__=="__main__":main()
