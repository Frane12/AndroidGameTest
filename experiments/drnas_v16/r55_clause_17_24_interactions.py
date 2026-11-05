#!/usr/bin/env python3
"""R55: isolate which of R47 derived clauses 17..24 enable R54's ~13 s solve.

EXPLORATORY / in-sample single already-seen SATComp26 CNF, NOT generalization.
Run 44 counterfactual subsets + four within-runner controls, two repetitions,
across 16 independent GitHub runners. Original order of retained R47 clauses
is frozen, and only certified two-parent resolvents from original CNF are added.
All source analysis, CNF rewriting and original-source SAT witness verification
count against a 40-second wall clock (PAR2 timeout 80 seconds).
"""
from __future__ import annotations
import argparse, hashlib, json, os, random, resource, statistics, subprocess, tempfile, time
from pathlib import Path
import r49_pivot_coherence_gate as r49
import r32p_real_satcomp26_benchmark as witness

PROTO="DRNAS-R55-8CLAUSE-CAUSAL-INTERACTION-20261103-v1"
SOURCE_RUN=41684183452
TARGET_GBD="2b35377a7b95f24449a3b607b61fff05"
TARGET_SHA="aa490f53e57c5119ac846f54dd2567d200824610ecdc92cae99098c5b0e5c1d4"
R52_PROTO="DRNAS-R52-PROSPECTIVE-2026-TOPREFS-20261103-v1"
CAP=40.0
SHARDS=16
REPS=2
CONTROLS=("clean","head16","head24","full40")
PROBES=tuple(
    [f"add_{i}" for i in range(17,25)]
    +[f"drop_{i}" for i in range(17,25)]
    +[f"pair_{i}_{j}" for i in range(17,25) for j in range(i+1,25)]
)
assert len(PROBES)==44

def chk(ok,msg):
    if not ok:raise RuntimeError("R55_FAIL_CLOSED "+str(msg))
def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for c in iter(lambda:f.read(1<<20),b""):h.update(c)
    return h.hexdigest()
def clause_indices(mode):
    if mode=="clean":return []
    if mode=="head16":return list(range(16))
    if mode=="head24":return list(range(24))
    if mode=="full40":return list(range(40))
    if mode.startswith("add_"):
        i=int(mode.split("_")[1]);chk(17<=i<=24,"bad index")
        return list(range(16))+[i-1]
    if mode.startswith("drop_"):
        i=int(mode.split("_")[1]);chk(17<=i<=24,"bad index")
        return [x for x in range(24) if x!=i-1]
    if mode.startswith("pair_"):
        _,a,b=mode.split("_");i,j=int(a),int(b)
        chk(17<=i<j<=24,"bad pair")
        return list(range(16))+[i-1,j-1]
    raise RuntimeError("unsupported frozen dose "+mode)

def freeze(args):
    root=Path(args.sources)
    m=json.loads((root/"manifest.json").read_text())
    chk(m["protocol"]==R52_PROTO and len(m["cases"])==11,
        "wrong official source cohort")
    original_case=next((c for c in m["cases"] if c["gbd"]==TARGET_GBD),None)
    chk(original_case is not None and original_case["sha256"]==TARGET_SHA,
        "target original SHA mismatch")
    original=root/original_case["name"]
    chk(sha(original)==TARGET_SHA,"source drift")
    plan=r49.compute_plan(original)
    chk(plan["derived"]==40 and plan["gate"] and
        len(plan["clauses"])==40 and len(plan["proofs"])==40,
        "not certified 40-clause R54 target")
    chk(plan["dominance"]==1.0,"source pivot structure drift")
    per_clause=[]
    for i,(c,p) in enumerate(zip(plan["clauses"],plan["proofs"]),1):
        chk(tuple(c)==tuple(p["clause"]) and len(p["parent_ids"])==2,
            "invalid independent proof")
        per_clause.append(dict(index=i,clause=c,proof=p,
             clause_sha256=hashlib.sha256(json.dumps(c).encode()).hexdigest()))
    design=dict(protocol=PROTO,origin_run=SOURCE_RUN,
         blind=False,seen_case=True,
         target=dict(gbd=TARGET_GBD,sha256=TARGET_SHA,
                    filename=original_case["name"],status=original_case["official_result"],
                    certificate_sha256=plan["certificate_sha256"],
                    clause_manifest=per_clause),
         parent_manifest_sha=sha(root/"manifest.json"),
         cap_seconds=CAP,par2_timeout_s=80.0,
         hypotheses=[
           "Necessary: delete each clause 17..24 individually from head24",
           "Sufficient: add each clause 17..24 individually to head16",
           "Pairwise synergy: add each unique pair from clauses 17..24 to head16",
           "Check clean, head16, head24, full40 on every runner and both reps",
           "Preserve original derivation order, count preprocessing and SAT witness time"],
         controls=list(CONTROLS),probes=list(PROBES),shards=SHARDS,reps=REPS,
         expected_trials=(SHARDS*len(CONTROLS)+len(PROBES))*REPS,
         limitations=[
           "Retrospective diagnosis of one selected case, not independent success evidence",
           "Benchmark uses separate Github runners; probe comparisons use same-runner controls",
           "Two repeats per probe cannot establish statistical significance",
           "New valid clauses may perturb CDCL beyond their propositional content",
           "UNSAT independently unproved; SAT models checked on original source"
         ])
    out=Path(args.out)
    out.write_text(json.dumps(design,indent=2)+"\n")
    print("R55_FREEZE_PASS",len(PROBES),"probe subsets",len(CONTROLS),
          "within-run controls",design["expected_trials"],"planned trials",flush=True)
    for c in per_clause[16:24]:
        print("R55_CLAUSE_WINDOW",c["index"],json.dumps(c["clause"]),
            c["clause_sha256"],"pivot",c["proof"]["pivot"],flush=True)

def mem():
    resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))

def trial(original,binary,design,mode):
    t0=time.monotonic()
    source=original
    status="TIMEOUT";prep=0.;added=0
    with tempfile.TemporaryDirectory(prefix="r55-causal-") as directory:
        if mode!="clean":
            plan=r49.compute_plan(original)
            chk(plan["certificate_sha256"]==design["target"]["certificate_sha256"]
                and plan["clauses"]==[c["clause"] for c in design["target"]["clause_manifest"]],
                "certified clause list drift")
            index=clause_indices(mode)
            chk(index==sorted(set(index)) and len(index)<=40,"order changed")
            selected=[plan["clauses"][i] for i in index]
            added=len(selected)
            if selected:
                source=Path(directory)/"candidate.cnf"
                rw=r49.r48.safe_rewrite(original,source,selected)
                chk(rw["added"]==added,"DIMACS rewrite/counter mismatch")
        prep=time.monotonic()-t0
        remaining=CAP-prep
        if remaining>0:
            try:
                p=subprocess.run([str(binary),str(source)],
                   capture_output=True,text=True,errors="replace",
                   timeout=remaining,preexec_fn=mem)
                chk(p.returncode in (10,20),
                    "solver process error "+str(p.returncode)+" "+p.stderr[-250:])
                status="SAT" if p.returncode==10 else "UNSAT"
                if status=="SAT":
                    witness.verify_sat_witness(original,p.stdout)
            except subprocess.TimeoutExpired:
                status="TIMEOUT"
        elapsed=time.monotonic()-t0
    if elapsed>CAP:status="TIMEOUT"
    wall=round(min(elapsed,CAP),6)
    return dict(answer=status,wall_s=wall,prep_s=round(prep,6),
         par2_s=round(wall if status!="TIMEOUT" else CAP*2,6),added=added)

def measure(args):
    chk(args.shard in range(SHARDS),"unknown shard")
    root=Path(args.sources)
    design=json.loads(Path(args.design).read_text())
    chk(design["protocol"]==PROTO and design["parent_manifest_sha"]==sha(root/"manifest.json"),
        "not frozen 2026 original")
    original=root/design["target"]["filename"]
    chk(sha(original)==TARGET_SHA,"changed CNF")
    binary=Path(args.kissat).resolve()
    chk(binary.is_file(),"missing pinned Kissat binary")
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    modes=list(CONTROLS)+list(PROBES[args.shard::SHARDS])
    meta=dict(protocol=PROTO,shard=args.shard,origin_sha=TARGET_SHA,
        design_sha=sha(args.design),solver_sha=sha(binary),
        modes=modes,reps=REPS,cpu_affinity=list(os.sched_getaffinity(0)))
    (out/"meta.json").write_text(json.dumps(meta,indent=2)+"\n")
    rows=[]
    for rep in range(REPS):
        ordered=modes.copy()
        seed=int(hashlib.sha256((PROTO+":"+str(args.shard)+":"+str(rep)).encode()).hexdigest(),16)
        random.Random(seed).shuffle(ordered)
        for mode in ordered:
            r=trial(original,binary,design,mode)
            chk(r["answer"]=="TIMEOUT" or r["answer"]==design["target"]["status"],
                "SAT answer contradicts official SATComp2026")
            row=dict(shard=args.shard,rep=rep,mode=mode,**r)
            rows.append(row)
            print("R55_TRIAL",args.shard,"rep",rep,mode,r["answer"],
                  r["wall_s"],"PAR2",r["par2_s"],"added",r["added"],flush=True)
            (out/"rows.json").write_text(json.dumps(rows,indent=2)+"\n")
    chk(len(rows)==len(modes)*REPS,"missing probe trial")

def audit(args):
    design=json.loads(Path(args.design).read_text())
    chk(design["protocol"]==PROTO,"wrong protocol")
    rows=[];bs=set();unique=set()
    for shard in range(SHARDS):
        folder=Path(args.combined)/f"r55-shard-{shard}"/"results"
        meta=json.loads((folder/"meta.json").read_text())
        chk(meta["protocol"]==PROTO and meta["shard"]==shard and
            meta["origin_sha"]==TARGET_SHA and
            meta["design_sha"]==sha(args.design),"runner original/protocol differs")
        bs.add(meta["solver_sha"])
        modes=list(CONTROLS)+list(PROBES[shard::SHARDS])
        chk(meta["modes"]==modes,"not precommitted mode set")
        rr=json.loads((folder/"rows.json").read_text())
        chk(len(rr)==len(modes)*REPS,"missing rows")
        for r in rr:
            key=(r["shard"],r["rep"],r["mode"])
            chk(key not in unique,"duplicated row");unique.add(key)
            chk(r["added"]==len(clause_indices(r["mode"])) and
                r["answer"] in ("SAT","UNSAT","TIMEOUT"),"wrong dose or verdict")
            chk(r["answer"]=="TIMEOUT" or r["answer"]==design["target"]["status"],
                "source status conflict")
            rows.append(r)
    chk(len(bs)==1 and len(rows)==design["expected_trials"]==216,
        "missing trials or binary mismatch")
    stats={}
    for mode in list(CONTROLS)+list(PROBES):
        rr=[r for r in rows if r["mode"]==mode]
        expected=SHARDS*REPS if mode in CONTROLS else REPS
        chk(len(rr)==expected,"wrong control/probe count")
        stats[mode]=dict(attempts=expected,solved=sum(r["answer"]!="TIMEOUT" for r in rr),
            median_s=round(statistics.median(r["wall_s"] for r in rr),6),
            par2_total_s=round(sum(r["par2_s"] for r in rr),6),
            raw=[r["wall_s"] if r["answer"]!="TIMEOUT" else "TO" for r in rr],
            added=len(clause_indices(mode)))
    # Difference to head24 and head16 matched controls on same runner+rep.
    for mode in PROBES:
        rr=[r for r in rows if r["mode"]==mode]
        controls=[next(r for r in rows if r["mode"]=="head24"
                     and r["shard"]==q["shard"] and r["rep"]==q["rep"])
                 for q in rr]
        sum_base=sum(q["par2_s"] for q in controls)
        stats[mode]["delta_vs_same_runner_head24_pct"]=round(
               (stats[mode]["par2_total_s"]/sum_base-1)*100,4)
        h16=[next(r for r in rows if r["mode"]=="head16"
                     and r["shard"]==q["shard"] and r["rep"]==q["rep"])
                 for q in rr]
        sum16=sum(q["par2_s"] for q in h16)
        stats[mode]["delta_vs_same_runner_head16_pct"]=round(
               (stats[mode]["par2_total_s"]/sum16-1)*100,4)
    rank=sorted(PROBES,key=lambda m:(stats[m]["par2_total_s"],m))
    report=dict(protocol=PROTO,parent=design,solver_sha=next(iter(bs)),
       trials=len(rows),stats=stats,ranked_probe_modes=rank,rows=rows)
    Path(args.json).write_text(json.dumps(report,indent=2)+"\n")
    lines=["# R55 — causal identification of R47 clauses 17–24",
       "**Known 2026 CNF, exploratory diagnostic only.**",
       f"Target {TARGET_GBD}, 40s overall cap, 80s PAR2 timeout, 216 paired attempts.",
       "All 16 runners include clean, head16, head24 and full40 controls (two repeats).",
       "Only mathematically certified R47 two-parent resolvents were added.",
       "","## Controls across 16 runners",
       "| Control | Solved | Median wall s | PAR2 total s |",
       "|---|---:|---:|---:|"]
    for m in CONTROLS:
        z=stats[m]
        lines.append(f'| {m} | {z["solved"]}/{z["attempts"]} | {z["median_s"]:.3f} | {z["par2_total_s"]:.3f} |')
    for group in ("add_","drop_","pair_"):
        names=[m for m in rank if m.startswith(group)]
        lines+=["",f"## {group.rstrip('_')} experiments sorted by PAR2",
           "| Probe | Solved | Trial times | PAR2 total s | vs same runner head24 | vs head16 |",
           "|---|---:|---|---:|---:|---:|"]
        for m in names:
            z=stats[m]
            lines.append(f'| {m} | {z["solved"]}/2 | {z["raw"]} | {z["par2_total_s"]:.3f} | {z["delta_vs_same_runner_head24_pct"]:+.2f}% | {z["delta_vs_same_runner_head16_pct"]:+.2f}% |')
    lines+=["","Best observed selections remain post-hoc/one-source hypotheses.",
       "Freeze a single rule **before** evaluating SHA-disjoint 2026 holdout sources.",
       "Do not call rankings on this known formula a world record."]
    Path(args.md).write_text("\n".join(lines)+"\n")
    print("R55_FINAL_AUDIT_PASS",len(rows),
         "best_probes",json.dumps([{m:stats[m]} for m in rank[:8]]),flush=True)

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="action",required=True)
    a=sub.add_parser("freeze")
    a.add_argument("--sources",required=True);a.add_argument("--out",required=True)
    a=sub.add_parser("measure")
    for k in ("sources","design","kissat","shard","out"):
        a.add_argument("--"+k,required=True)
    a=sub.add_parser("audit")
    for k in ("design","combined","json","md"):a.add_argument("--"+k,required=True)
    args=p.parse_args()
    if args.action=="freeze":freeze(args)
    elif args.action=="measure":
        args.shard=int(args.shard);measure(args)
    else:audit(args)
if __name__=="__main__":main()
