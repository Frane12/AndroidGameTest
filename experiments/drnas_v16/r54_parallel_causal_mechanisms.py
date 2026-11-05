#!/usr/bin/env python3
"""R54 exploratory parallel causal SAT mechanism scan on 2026 Main Track originals.

Four independently frozen hypotheses using the SAME mathematically verified
R47 two-parent resolvents and the original R51/R52 clean Kissat binary:
 dose: clause count; pivot: local pivot coherence; order: clause ordering;
 motif: XOR-like local structure and R49 selective abstention.

This is retrospective on eight R52 instances, including R53 positive/negative
controls. It does NOT establish generalization. Every trial includes
preprocessing + DIMACS write + SAT witness check in a 40-second total wall cap.
No search modification, in-process hooking, restart or watchdog.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import random
import resource
import statistics
import subprocess
import tempfile
import time
import r49_pivot_coherence_gate as r49
import r32p_real_satcomp26_benchmark as verify

PROTO="DRNAS-R54-PARALLEL-CAUSAL-2026-20261103-v1"
R52_PROTO="DRNAS-R52-PROSPECTIVE-2026-TOPREFS-20261103-v1"
R52_RUN=41684183452
R53_RUN=41686045650
CAP=40.0
SHARDS=4
ARMS={
  "dose": ("clean","head8","head16","head24","full40"),
  "pivot": ("clean","pivot8","pivot16","pivot40","diverse16"),
  "order": ("clean","full40","reverse40","tail16","shortest16"),
  "motif": ("clean","full40","motif16","generic16","struct_gate40"),
}
# SHA-256 source identities are recorded from R52 FREEZE, not re-selected.
# 2 repeats for high-value positive/negative R53 paired controls, 1 otherwise.
PRECOMMITTED=(
 ("2b35377a7b95f24449a3b607b61fff05",
  "aa490f53e57c5119ac846f54dd2567d200824610ecdc92cae99098c5b0e5c1d4",2,"r53_benefit"),
 ("262a226a47330987f038128579967405",
  "1883d4efd956602fed6397626c9b2f7359609cd54784bf3d7701a1c1a837c7d2",2,"r53_regression"),
 ("09637d3bd641b4d733666a862e8918ea",
  "f10b86d44b3f37c48f8060f9afe2efff32b53ed2f2b0dfc8970b4eff2a20d74b",1,"r52_gate"),
 ("dd5d530ac8bf0019412d023488b075eb",
  "d07776e49cb9a78e50250736b38d6d087269a6894013cd167dfb3b5b484744cf",1,"r52_gate"),
 ("e1292f8d651e022362630d34fef69312",
  "9e956aed24565b49f2eac5be33b1da07a6c27e5df238f04536940a811bad31d5",1,"r52_abstain"),
 ("0c9da400944b002f90fd385d4fdab385",
  "aee38446750ffeeff61dafe272602875a1e7e18a6fd7c284240f7335226bea7a",1,"r52_abstain"),
 ("8d0d8518a438d93428257d9a38863c3c",
  "e3171d818f0d919d9a7ca285d0e43f53570fefbc7a750b076ec83cd1b068133e",1,"r52_timeout"),
 ("958fd8bd1936e5bad8cbccae492edd81",
  "81399a6b850f57fd1b9bfa936a52f7c950b40f8d1281d3f9d7359c9e8fdbc14e",1,"r52_timeout"),
)

def check(ok,msg):
    if not ok: raise RuntimeError("R54_INTEGRITY_FAILURE: "+str(msg))
def sha(x):
    h=hashlib.sha256()
    with open(x,"rb") as f:
        for part in iter(lambda:f.read(1<<20),b""):h.update(part)
    return h.hexdigest()

def select(mode,plan):
    """All returned clauses are original-source proven R47 resolvents."""
    pairs=list(zip(plan["clauses"],plan["proofs"]))
    if mode=="clean":return []
    if mode=="full40":return [c for c,_ in pairs]
    if mode.startswith("head"):return [c for c,_ in pairs[:int(mode[4:])]]
    if mode.startswith("tail"):return [c for c,_ in pairs[-int(mode[4:]):]]
    if mode=="reverse40":return [c for c,_ in reversed(pairs)]
    if mode.startswith("pivot"):
        n=int(mode[5:])
        return [c for c,p in pairs if p["pivot"]==plan["top_pivot"]][:n]
    if mode=="shortest16":
        x=sorted(enumerate(pairs),
                 key=lambda item:(len(item[1][0]),
                           len(item[1][1]["support"]),item[0]))
        return [c for _,(c,p) in x[:16]]
    if mode=="diverse16":
        queues=collections.defaultdict(list)
        for c,p in pairs:queues[p["pivot"]].append(c)
        keys=sorted(queues)
        result=[]
        while keys and len(result)<16:
            for k in keys:
                if queues[k] and len(result)<16:result.append(queues[k].pop(0))
            keys=[k for k in keys if queues[k]]
        return result
    if mode=="motif16":
        return [c for c,p in pairs if p["source"]=="partial_motif"][:16]
    if mode=="generic16":
        return [c for c,p in pairs if p["source"]=="generic"][:16]
    if mode=="struct_gate40":
        return [c for c,_ in pairs] if plan["gate"] else []
    raise RuntimeError("unknown frozen arm mode "+mode)

def audit_clause_selection(plan):
    allset={tuple(c) for c in plan["clauses"]}
    check(len(allset)==len(plan["clauses"]),"duplicate original derivations")
    for arm,modes in ARMS.items():
        check(len(modes)==5 and modes[0]=="clean","protocol modes altered")
        for mode in modes:
            selected=select(mode,plan)
            check(len(selected)<=40 and
                  len({tuple(c) for c in selected})==len(selected)
                  and all(tuple(c) in allset for c in selected),
                  "selection invents or duplicates a clause "+arm+"/"+mode)

def freeze(args):
    root=Path(args.sources)
    official=json.loads((root/"manifest.json").read_text())
    check(official["protocol"]==R52_PROTO and len(official["cases"])==11,
          "expected 11 previously frozen R52 formulas")
    byid={x["gbd"]:x for x in official["cases"]}
    check(len(byid)==11 and len(PRECOMMITTED)==8,"wrong cohort")
    frozen=[]
    for id,source_sha,repeats,cohort in PRECOMMITTED:
        check(id in byid and byid[id]["sha256"]==source_sha,
              "unrecognized prior 2026 original "+id)
        original=root/byid[id]["name"]
        check(sha(original)==source_sha,"original modified")
        plan=r49.compute_plan(original)
        audit_clause_selection(plan)
        selected_counts={arm:{mode:len(select(mode,plan)) for mode in modes}
                         for arm,modes in ARMS.items()}
        row=dict(gbd=id,source_sha256=source_sha,
                 name=byid[id]["name"],expected_status=byid[id]["official_result"],
                 repeats=repeats,cohort=cohort,
                 certificate_sha256=plan["certificate_sha256"],
                 derived=plan["derived"],
                 top_pivot=plan["top_pivot"],
                 dominance=plan["dominance"],
                 gate=plan["gate"],
                 motif_count=sum(p["source"]=="partial_motif"
                                 for p in plan["proofs"]),
                 selected_counts=selected_counts)
        frozen.append(row)
        print("R54_FROZEN_FEATURE",id,cohort,
          "derived",plan["derived"],"dominance",plan["dominance"],
          "gate",plan["gate"],"motifs",row["motif_count"],
          "modes",json.dumps(selected_counts,sort_keys=True),flush=True)
    design=dict(protocol=PROTO,parents=[R52_RUN,R53_RUN],
                original_manifest_sha=sha(root/"manifest.json"),
                cases=frozen,arms={k:list(v) for k,v in ARMS.items()},
                official_2026=True,
                hypothesis_class="exploratory_causes_not_blind_generalization",
                cap_seconds=CAP,par2_timeout_s=CAP*2,
                source_selection="Eight already-measured R52 originals; repeated R53 benefit and regression",
                single_cpu_core=True,trial_memory_gib=3,
                limitations=[
                  "NOT prospective generalization: source selection uses known R52 outcomes",
                  "Zero false claims of SAT competition world rank",
                  "No change to Kissat code, restarts, watcher, or search state",
                  "Exact two-parent resolution proof verified by R47 and R46",
                  "CNF write and proof cost included in fixed 40s total wall budget",
                  "SAT witnesses checked on original unmodified source",
                  "UNSAT lacks separate independent LRAT proof",
                  "Four parallel arms are independent machines; within-arm controls share one runner"])
    path=Path(args.out);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(design,indent=2)+"\n")
    print("R54_DESIGN_SHA",sha(path),"R54_FROZEN_PASS",len(frozen),flush=True)

def childmemory():
    resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))

def trial(original,binary,plan,mode):
    start=time.monotonic()
    status="TIMEOUT";added=0;cost=0.0
    with tempfile.TemporaryDirectory(prefix="drnas-r54-") as folder:
        candidate=original
        if mode!="clean":
            active=r49.compute_plan(original)
            check(active["certificate_sha256"]==plan["certificate_sha256"]
                and active["derived"]==plan["derived"]
                and active["dominance"]==plan["dominance"]
                and active["gate"]==plan["gate"],"proof/structure changed")
            clauses=select(mode,active)
            check(len(clauses)==plan["selected_counts"][CURRENT_ARM][mode],
                  "frozen clause selection changed")
            added=len(clauses)
            if added:
                candidate=Path(folder)/"candidate.cnf"
                rewrite=r49.r48.safe_rewrite(original,candidate,clauses)
                check(rewrite["added"]==added,"DIMACS write audit failed")
        cost=time.monotonic()-start
        if cost<CAP:
            try:
                p=subprocess.run([str(binary),str(candidate)],
                     capture_output=True,text=True,errors="replace",
                     timeout=CAP-cost,preexec_fn=childmemory)
                check(p.returncode in (10,20),
                      "unexpected solver exit code "+str(p.returncode)+": "+p.stderr[-150:])
                status="SAT" if p.returncode==10 else "UNSAT"
                if status=="SAT":
                    verify.verify_sat_witness(original,p.stdout)
            except subprocess.TimeoutExpired:
                status="TIMEOUT"
        elapsed=time.monotonic()-start
    if elapsed>CAP:status="TIMEOUT"
    elapsed=min(elapsed,CAP)
    return dict(answer=status,time_s=round(elapsed,6),
                prep_s=round(cost,6),
                par2_s=round(elapsed if status!="TIMEOUT" else CAP*2,6),
                added=added)

CURRENT_ARM=None
def measure(args):
    global CURRENT_ARM
    CURRENT_ARM=args.arm
    check(args.arm in ARMS and args.shard in range(SHARDS),
          "unsupported arm or shard")
    design=json.loads(Path(args.design).read_text())
    root=Path(args.sources)
    check(design["protocol"]==PROTO
       and design["original_manifest_sha"]==sha(root/"manifest.json"),
          "wrong frozen source or design")
    binary=Path(args.kissat).resolve()
    check(binary.is_file(),"Kissat missing")
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    output=Path(args.out);output.mkdir(parents=True,exist_ok=True)
    metadata=dict(protocol=PROTO,arm=args.arm,shard=args.shard,
          binary_sha=sha(binary),design_sha=sha(args.design),
          manifest_sha=sha(root/"manifest.json"),cap_seconds=CAP,
          source_run=R52_RUN,run_id=os.getenv("GITHUB_RUN_ID","local"),
          cpu_affinity=sorted(os.sched_getaffinity(0)) if hasattr(os,"sched_getaffinity") else [])
    (output/"meta.json").write_text(json.dumps(metadata,indent=2)+"\n")
    rows=[]
    for case in design["cases"][args.shard::SHARDS]:
        original=root/case["name"]
        check(sha(original)==case["source_sha256"],"source SHA drift")
        for rep in range(case["repeats"]):
            modes=list(ARMS[args.arm])
            seed=int(hashlib.sha256(
                  (PROTO+"|"+args.arm+"|"+case["source_sha256"]+"|"+str(rep)).encode()
                  ).hexdigest(),16)
            random.Random(seed).shuffle(modes)
            for mode in modes:
                result=trial(original,binary,case,mode)
                row=dict(arm=args.arm,shard=args.shard,gbd=case["gbd"],
                         source_sha=case["source_sha256"],rep=rep,mode=mode,**result)
                if row["answer"]!="TIMEOUT":
                    check(row["answer"]==case["expected_status"],
                         "verdict inconsistent with official 2026 classification")
                rows.append(row)
                print("R54_TRIAL",args.arm,case["gbd"],"rep",rep,mode,
                      row["answer"],row["time_s"],"PAR2",row["par2_s"],
                      "added",row["added"],flush=True)
                (output/"rows.json").write_text(json.dumps(rows,indent=2)+"\n")
    exp=sum(c["repeats"] for c in design["cases"][args.shard::SHARDS])*5
    check(len(rows)==exp,"incomplete arm shard")

def audit(args):
    design=json.loads(Path(args.design).read_text())
    check(design["protocol"]==PROTO,"bad design")
    rows=[];binary_hashes=set();seen=set()
    for arm,modes in ARMS.items():
        for shard in range(SHARDS):
            root=Path(args.combined)/("r54-"+arm+"-"+str(shard))/"results"
            meta=json.loads((root/"meta.json").read_text())
            check(meta["protocol"]==PROTO and meta["arm"]==arm
                  and meta["shard"]==shard and
                  meta["design_sha"]==sha(args.design)
                  and meta["manifest_sha"]==design["original_manifest_sha"],
                  "mixed GitHub runner artifacts")
            binary_hashes.add(meta["binary_sha"])
            current=json.loads((root/"rows.json").read_text())
            expected=sum(c["repeats"] for c in design["cases"][shard::SHARDS])*len(modes)
            check(len(current)==expected,"missing shard rows")
            for r in current:
                key=(r["arm"],r["gbd"],r["rep"],r["mode"])
                check(key not in seen,"duplicate trial")
                seen.add(key);rows.append(r)
    check(len(binary_hashes)==1,"different binary from prior solver")
    total=sum(c["repeats"] for c in design["cases"])*sum(len(x) for x in ARMS.values())
    check(len(rows)==total==200,"frozen 200 attempted trial mismatch")
    stats={};individual={}
    for arm,modes in ARMS.items():
        base=[r for r in rows if r["arm"]==arm and r["mode"]=="clean"]
        base_total=sum(r["par2_s"] for r in base)
        stats[arm]={}
        for mode in modes:
            arr=[r for r in rows if r["arm"]==arm and r["mode"]==mode]
            check(len(arr)==len(base)==10,"not paired")
            agg=dict(attempts=len(arr),
               solved=sum(r["answer"]!="TIMEOUT" for r in arr),
               timeouts=sum(r["answer"]=="TIMEOUT" for r in arr),
               par2_total_s=round(sum(r["par2_s"] for r in arr),6),
               mean_prep_s=round(statistics.mean(r["prep_s"] for r in arr),6),
               additions=sum(r["added"] for r in arr))
            agg["delta_vs_clean_pct"]=round(
                100*(agg["par2_total_s"]/base_total-1),4)
            stats[arm][mode]=agg
        individual[arm]={}
        for case in design["cases"]:
            x=[r for r in rows if r["arm"]==arm and r["gbd"]==case["gbd"]]
            check(len(x)==case["repeats"]*len(modes),"case missing")
            for rep in range(case["repeats"]):
                p={r["mode"]:r for r in x if r["rep"]==rep}
                check(set(p)==set(modes),"missing matched experiment")
                for mode,r in p.items():
                    check(r["source_sha"]==case["source_sha256"],"wrong official original")
                    check(r["added"]==case["selected_counts"][arm][mode],
                        "clause count drift")
                    check(r["answer"]=="TIMEOUT" or r["answer"]==case["expected_status"],
                        "wrong verdict")
                    check(abs(r["par2_s"]-
                        (80.0 if r["answer"]=="TIMEOUT" else r["time_s"]))<.002,
                        "wrong PAR2")
            individual[arm][case["gbd"]]={
                 mode:dict(solved=sum(r["answer"]!="TIMEOUT"
                    for r in x if r["mode"]==mode),
                     attempts=case["repeats"],
                     par2_sum_s=round(sum(r["par2_s"] for r in x
                       if r["mode"]==mode),6),
                     raw=[round(r["time_s"],3)
                       if r["answer"]!="TIMEOUT" else "TO"
                       for r in sorted((r for r in x if r["mode"]==mode),
                        key=lambda z:z["rep"])])
                 for mode in modes}
    report=dict(protocol=PROTO,source_runs=[R52_RUN,R53_RUN],
      total_attempts=len(rows),pinned_clean_kissat_sha=next(iter(binary_hashes)),
      aggregate=stats,individual=individual,rows=rows,
      frozen_design=design,limitations=design["limitations"])
    Path(args.json).write_text(json.dumps(report,indent=2)+"\n")
    lines=["# R54 — four causal hypothesis directions in parallel",
      "**EXPLORATORY, NOT blind generalization.** Already used R52 official 2026 originals.",
      "Source SHA & R47 two-parent proofs frozen; original SAT witness verified.",
      "40s end-to-end cap per attempt; PAR2 timeout=80s; 3GiB, one pinned Kissat core.",
      "", "## Overall matched 10 attempts per strategy (eight original formulas)"]
    for arm,modes in ARMS.items():
        lines+=["","### "+arm,
          "| Mode | Solved | PAR2 sum s | Change vs arm clean | Added |",
          "|---|---:|---:|---:|---:|"]
        for mode in modes:
            t=stats[arm][mode]
            lines.append(f'| {mode} | {t["solved"]}/10 | {t["par2_total_s"]:.3f} | {t["delta_vs_clean_pct"]:+.2f}% | {t["additions"]} |')
        lines+=["","### "+arm+" / individual formula contrasts",
           "| GBD prefix | "+" | ".join(modes)+" |",
           "|---|"+("|---:|"*len(modes))]
        for case in design["cases"]:
            values=individual[arm][case["gbd"]]
            lines.append("| "+case["gbd"][:12]+" | "+" | ".join(
                f'{values[mode]["par2_sum_s"]:.2f}' for mode in modes)+" |")
    lines+=["","All per-attempt times, zero-clauses abstention and official source SHA are in JSON.",
       "Choose promising methods only after this exploratory pass, then freeze them",
       "and validate on **new SHA-disjoint original 2026 CNFs**.",
       "No global SAT Competition winner or record conclusions from these data."]
    Path(args.md).write_text("\n".join(lines)+"\n")
    print("R54_FINAL_AUDIT_PASS",len(rows),json.dumps(stats,sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="cmd",required=True)
    f=sub.add_parser("freeze")
    f.add_argument("--sources",required=True)
    f.add_argument("--out",required=True)
    m=sub.add_parser("measure")
    for name in ("sources","design","kissat","arm","shard","out"):
        m.add_argument("--"+name,required=True)
    a=sub.add_parser("audit")
    for name in ("design","combined","json","md"):a.add_argument("--"+name,required=True)
    args=p.parse_args()
    if args.cmd=="freeze":freeze(args)
    elif args.cmd=="measure":
        args.shard=int(args.shard)
        measure(args)
    else:audit(args)

if __name__=="__main__":main()
