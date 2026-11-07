#!/usr/bin/env python3
"""R78: prospective 24-source official SAT2025 input challenge, 4 frozen policies.

The actual source strata are reported, never relabeled or fabricated to
force a desired 8/8/8 composition. Sources are new relative to the documented
R63/R66/R67/R72/R73/R77 selection histories, not a claim of global novelty.
Adaptive policy is frozen before the measurements; observed structural scan
and preprocessing overhead is INCLUDED in every adaptive wall time.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, os, random, signal
import subprocess, tempfile, time
from pathlib import Path
import r73_fresh_quick_unseen_2025 as old
import r32p_real_satcomp26_benchmark as r32p
import r28_exact_gf2_benchmark as r28
import r63_real2026_xor_prevalence_fallback as r63
import r64_mixed_xor_implied as r64
import r65_xor_cnf_feedback as r65
import r71_bcp_15sec_eight_formulas as r71

PROTO="DRNAS-R78-FROZEN-STRUCTURAL-ADAPTIVE-20261104-v1"
SALT="DRNAS-R78-24-ORIGINAL-SAT2025-NO-TIMING-PRESCREEN-20261104"
N, SHARDS, REPS, CAP=24,8,3,30.0
MODES=("clean_kissat","r28_gf2","r65_full","r78_adaptive")
# Predetermined structural gates (no performance tuning on R78).
MIXED_MIN_BLOCKS=4
MIXED_MIN_COVERAGE=0.015
PREP_BUDGET_S=2.0

def check(ok,msg):
    if not ok:raise RuntimeError("R78_FAIL_CLOSED "+str(msg))

def digest(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):
            h.update(b)
    return h.hexdigest()

def freeze(args):
    source_manifests=[]
    for label,folder,proto,num in (
        ("r73",args.r73,"DRNAS-R73-NEVER-SEEN-5TO30S-20261103-v1",8),
        ("r77",args.r77,"DRNAS-R77-UNOFFICIAL-10-FRESH-2025-20261104-v1",10)):
        mp=Path(folder)/("new" if label=="r73" else "world")/"manifest.json"
        check(mp.is_file(),"missing source history "+str(mp))
        data=json.loads(mp.read_text())
        check(data["protocol"]==proto and data["ready"]==num and len(data["cases"])==num,
              label+" incomplete history")
        ids={a["gbd"] for a in data["selection_attempts"]}
        ids|={c["gbd"] for c in data["cases"]}
        hashes={c["sha256"] for c in data["cases"]}
        check(len(ids)>=num and len(hashes)==num,label+" invalid attempts/SHA")
        source_manifests.append((label,data,ids,hashes,digest(mp)))
    original=old.history
    def history_with_disjoint(args_):
        seen,hashed,pinned,registry=original(args_)
        for label,m,ids,hashes,manifest_sha in source_manifests:
            check(not ({c["gbd"] for c in m["cases"]}&seen),
                  label+" historical accepted source collision")
            check(not (hashes&hashed),label+" historical accepted SHA collision")
            seen|=ids; hashed|=hashes
            registry[label+"_attempted_or_selected_count"]=len(ids)
            registry[label+"_accepted_sha_count"]=len(hashes)
            registry[label+"_manifest_sha256"]=manifest_sha
        return seen,hashed,pinned,registry
    old.history=history_with_disjoint
    old.PROTO=PROTO
    old.SALT=SALT
    old.N=N
    old.REPS=REPS
    old.SHARDS=SHARDS
    old.BENCH_CAP=CAP
    old.MAX_2025_ATTEMPTS=64
    try:old.freeze(args)
    finally:old.history=original
    path=Path(args.out)/"manifest.json"
    m=json.loads(path.read_text())
    check(m["ready"]==N and len({c["sha256"] for c in m["cases"]})==N,
          "missing/duplicate selected sources")
    excluded_ids=set().union(*(entry[2] for entry in source_manifests))
    excluded_sha=set().union(*(entry[3] for entry in source_manifests))
    check(not ({c["gbd"] for c in m["cases"]}&excluded_ids),
          "selected an already attempted R73/R77 source")
    check(not ({c["sha256"] for c in m["cases"]}&excluded_sha),
          "selected old R73/R77 SHA")
    m["modes"]=list(MODES)
    m["repeats"]=REPS
    m["shards"]=SHARDS
    m["bench_cap_s"]=CAP
    m["gate_rule"]=dict(
        pure_exact_route="R28 if >=2 complete XOR blocks",
        mixed_exact_route="R65 if >=4 complete blocks AND >=0.015 clause coverage",
        otherwise="original Kissat",
        runtime_pre_scan=True,
        runtime_pre_scan_charged=True,
        r65_max_prep_s=PREP_BUDGET_S)
    counts=dict(collections.Counter(c["group"] for c in m["cases"]))
    m["observed_strata"]=counts
    m["requested_quotas"]=dict(pure_exact=8,mixed_exact=8,no_exact=8)
    m["quotas_achieved"]=all(counts.get(x,0)>=8 for x in
                             ("pure_exact","mixed_exact","no_exact"))
    m["limitations"]+= [
        "Structural 8/8/8 quotas are aspirational. Only observed strata are reported; no false classes.",
        "Twenty-four input originals from 2025 competition catalog, not proof of 24 globally unseen instances.",
        "Same runner class, but separate GitHub-hosted jobs may have different CPUs; log host and core.",
        "Runtime re-scan overhead is measured every R78 attempt, with fail-closed feature agreement.",
        "Adaptive threshold frozen before any R78 performance data, no training on the held-out 24.",
        "SAT assignment checked against original CNF; UNSAT is not independently proof-certified unless R28 GF2 certificate verified.",
        "No official competition placement or world record is implied by these tests."]
    path.write_text(json.dumps(m,indent=2,sort_keys=True)+"\n")
    print("R78_FREEZE_PASS",json.dumps(dict(source_count=N,strata=counts,
        quotas_achieved=m["quotas_achieved"],
        r73_r77_history_excluded=len(excluded_ids))),flush=True)

def decide(features):
    if not features["supported"]:
        return "kissat"
    if features["pure_exact_xor"] and features["complete_blocks"]>=2:
        return "r28"
    if (not features["pure_exact_xor"] and
        features["complete_blocks"]>=MIXED_MIN_BLOCKS and
        features["coverage_fraction"]>=MIXED_MIN_COVERAGE):
        return "r65"
    return "kissat"

def run_solver(argv,original,remaining_s):
    if remaining_s<=0:return "UNKNOWN",0.0,True,"budget_exhausted"
    t0=time.monotonic()
    with subprocess.Popen([str(x) for x in argv],
        stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        text=True,errors="replace",preexec_fn=r63.child) as p:
        try:
            out,err=p.communicate(timeout=remaining_s)
            timeout=False
        except subprocess.TimeoutExpired:
            timeout=True
            p.send_signal(signal.SIGINT)
            try:out,err=p.communicate(timeout=0.35)
            except subprocess.TimeoutExpired:
                p.kill();out,err=p.communicate()
    wall=time.monotonic()-t0
    if timeout:return "UNKNOWN",wall,True,"timeout"
    check(p.returncode in (10,20),
          "unexpected exit "+str(p.returncode)+": "+err[-260:])
    ans="SAT" if p.returncode==10 else "UNSAT"
    if ans=="SAT":
        r32p.verify_sat_witness(original,out)
    route=""
    for line in out.splitlines():
        if line.startswith("c R28_ROUTE "):
            route=line.split()[2]
    if ans=="UNSAT" and route=="certified_xor_contradiction":
        _,clauses=r28.load_clauses(original)
        check(r28.check_gf2_unsat_proof(out,clauses),
              "R28 returned unverified GF2 UNSAT certificate")
    return ans,wall,False,route

def measure(args):
    root=Path(args.sources)
    manifest=json.loads((root/"manifest.json").read_text())
    check(manifest["protocol"]==PROTO and manifest["ready"]==N,
          "frozen source protocol mismatch")
    check(0<=args.shard<SHARDS,"shard outside 0..7")
    check(len({c["sha256"] for c in manifest["cases"]})==N,"duplicate input hashes")
    binaries=Path(args.binaries).resolve()
    verify=subprocess.run(["sha256sum","-c","binary.sha256"],
        cwd=binaries,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
    check(verify.returncode==0,"solver binary hash mismatch: "+verify.stderr)
    kissat=(binaries/"kissat").resolve()
    gf2=(binaries/"r28_gf2").resolve()
    check(digest(kissat)==manifest["registry"]["binary_sha"],
          "Kissat SHA mismatch versus frozen preselection history")
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    r65.MAX_PREP_S=PREP_BUDGET_S
    outdir=Path(args.out)
    outdir.mkdir(parents=True,exist_ok=True)
    results=[]
    for case in manifest["cases"][args.shard::SHARDS]:
        source=root/case["filename"]
        check(source.is_file() and digest(source)==case["sha256"],
              "original source SHA drift")
        for rep in range(REPS):
            order=list(MODES)
            random.Random(int(hashlib.sha256(
                (PROTO+case["sha256"]+str(rep)).encode()).hexdigest(),16)).shuffle(order)
            for mode in order:
                t0=time.monotonic()
                target=source
                argv=[kissat,source]
                action="kissat"
                clauses_added=0
                scan_s=0.0
                with tempfile.TemporaryDirectory(prefix="r78-policy-") as tmp:
                    if mode=="r28_gf2":
                        argv=[gf2,source,kissat]
                        action="r28"
                    elif mode=="r78_adaptive":
                        scan_start=time.monotonic()
                        features=r63.inspect_exact_xor(
                            source,case["variables"],case["clauses"])
                        scan_s=time.monotonic()-scan_start
                        check(features["supported"]==case["supported"] and
                              features["complete_blocks"]==case["complete_blocks"] and
                              features["pure_exact_xor"]==case["pure_exact_xor"],
                              "runtime scan differs from frozen features")
                        action=decide(features)
                        if action=="r28":
                            argv=[gf2,source,kissat]
                    elif mode=="r65_full":
                        action="r65"
                    if action=="r65":
                        _,_,clauses,_,stats=r71.prepare(root,case)
                        clauses_added=len(clauses)
                        if clauses:
                            target=Path(tmp)/"augmented.cnf"
                            r64.augment(source,target,case["variables"],
                                        case["clauses"],clauses)
                        argv=[kissat,target]
                    overhead=time.monotonic()-t0
                    remaining=CAP-overhead
                    answer,solved_wall,timeout,solver_route=run_solver(
                        argv,source,remaining)
                    elapsed=time.monotonic()-t0
                    solved=answer!="UNKNOWN" and not timeout and elapsed<=CAP
                    row=dict(source_id=case["gbd"],source_sha256=case["sha256"],
                        group=case["group"],rep=rep,mode=mode,answer=answer,
                        solved=solved,pre_scan_s=round(scan_s,6),
                        preprocess_and_scan_s=round(overhead,6),
                        solver_wall_s=round(solved_wall,6),
                        end_to_end_s=round(elapsed,6),
                        par2_s=round(elapsed if solved else 2*CAP,6),
                        adaptive_action=action if mode=="r78_adaptive" else None,
                        new_clauses=clauses_added,solver_route=solver_route,
                        runner=os.environ.get("RUNNER_NAME",""),
                        runner_os=os.environ.get("RUNNER_OS",""),
                        commit=os.environ.get("GITHUB_SHA",""),
                        seed=rep,
                        run_id=os.environ.get("GITHUB_RUN_ID",""),
                        solver_sha256=digest(gf2 if action=="r28" else kissat))
                    results.append(row)
                    print("R78_TRIAL",json.dumps({k:row[k] for k in
                        ("source_id","group","rep","mode","answer","adaptive_action",
                         "par2_s","end_to_end_s")}),flush=True)
        matched=[r for r in results if r["source_sha256"]==case["sha256"]]
        for rep in range(REPS):
            vals={r["answer"] for r in matched if r["rep"]==rep and
                  r["answer"]!="UNKNOWN"}
            check(len(vals)<=1,"conflicting solver answers on original CNF")
    expected=len(manifest["cases"][args.shard::SHARDS])*REPS*len(MODES)
    check(len(results)==expected,"incomplete shard")
    report=dict(protocol=PROTO,shard=args.shard,
        source_manifest_sha256=digest(root/"manifest.json"),
        binaries={"kissat":digest(kissat),"r28_gf2":digest(gf2)},
        cpu=Path("/proc/cpuinfo").read_text(errors="replace")[:3500],
        rows=results)
    (outdir/"r78-shard.json").write_text(json.dumps(report,indent=2)+"\n")
    print("R78_SHARD_PASS",args.shard,len(results),flush=True)

def make_scatter(pairs,path):
    dim=480; margin=48; size=dim-2*margin
    # One dot per paired formula and seed: Kissat X vs R78 Y, both PAR-2.
    def fx(x):return margin+size*max(0,min(60,x))/60
    def fy(y):return dim-margin-size*max(0,min(60,y))/60
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{dim}" height="{dim}" viewBox="0 0 {dim} {dim}">',
         '<rect width="100%" height="100%" fill="white"/>',
         f'<line x1="{margin}" y1="{dim-margin}" x2="{dim-margin}" y2="{margin}" stroke="#777" stroke-dasharray="6 4"/>',
         f'<line x1="{margin}" y1="{dim-margin}" x2="{dim-margin}" y2="{dim-margin}" stroke="#222"/>',
         f'<line x1="{margin}" y1="{margin}" x2="{margin}" y2="{dim-margin}" stroke="#222"/>',
         '<text x="250" y="466" text-anchor="middle" font-size="13">Kissat PAR-2 (s)</text>',
         '<text transform="translate(14,250) rotate(-90)" text-anchor="middle" font-size="13">R78 PAR-2 (s)</text>']
    for item in pairs:
        x,y=item["clean_kissat"],item["r78_adaptive"]
        svg.append(f'<circle cx="{fx(x):.1f}" cy="{fy(y):.1f}" r="3.5" fill="#316ad2" fill-opacity=".5"/>')
    svg.append("</svg>")
    path.write_text("\n".join(svg)+"\n")

def audit(args):
    root=Path(args.sources)
    manifest=json.loads((root/"manifest.json").read_text())
    check(manifest["protocol"]==PROTO and manifest["ready"]==N,
          "wrong final manifest")
    check(len({c["sha256"] for c in manifest["cases"]})==N,
          "duplicate source in audit")
    pins=set(); rows=[]; hosts=[]
    for shard in range(SHARDS):
        p=Path(args.combined)/f"r78-shard-{shard}"/"results"/"r78-shard.json"
        check(p.is_file(),"missing shard "+str(shard))
        dat=json.loads(p.read_text())
        check(dat["protocol"]==PROTO and dat["shard"]==shard
              and dat["source_manifest_sha256"]==digest(root/"manifest.json"),
              "wrong shard/source pin")
        pins.add(tuple(sorted(dat["binaries"].items())))
        hosts.append(dict(shard=shard,cpu=dat["cpu"].splitlines()[:10]))
        current=dat["rows"]
        subset=manifest["cases"][shard::SHARDS]
        check(len(current)==len(subset)*REPS*len(MODES),"missing trials")
        for case in subset:
            subsetrows=[r for r in current if r["source_sha256"]==case["sha256"]]
            check(len(subsetrows)==REPS*len(MODES),"incomplete source")
            for rep in range(REPS):
                rr=[r for r in subsetrows if r["rep"]==rep]
                check(len(rr)==len(MODES) and
                      {r["mode"] for r in rr}==set(MODES),"unpaired seed")
                verdicts={r["answer"] for r in rr if r["answer"]!="UNKNOWN"}
                check(len(verdicts)<=1,"SAT UNSAT disagreement")
                check(all(r["source_id"]==case["gbd"] and
                          r["group"]==case["group"] and r["commit"] and
                          r["runner"] for r in rr),"provenance incomplete")
        rows+=current
    check(len(pins)==1 and len(rows)==N*REPS*len(MODES),
          "binary drift or incorrect total trial count")
    totals={}
    group_totals={}
    for grp in ["ALL"]+sorted({c["group"] for c in manifest["cases"]}):
        bymode={}
        for mode in MODES:
            selected=[r for r in rows if r["mode"]==mode and
                      (grp=="ALL" or r["group"]==grp)]
            bymode[mode]=dict(attempts=len(selected),
                solved=sum(r["solved"] for r in selected),
                timeouts=sum(not r["solved"] for r in selected),
                par2_s=round(sum(r["par2_s"] for r in selected),6),
                fastest_s=min((r["end_to_end_s"] for r in selected if r["solved"]),
                              default=None))
        group_totals[grp]=bymode
    totals=group_totals["ALL"]
    reference=totals["clean_kissat"]["par2_s"]
    for mode in MODES[1:]:
        totals[mode]["gain_over_kissat_pct"]=round(
            100*(reference-totals[mode]["par2_s"])/reference,5)
    paired=[]
    for case in manifest["cases"]:
        for rep in range(REPS):
            rr=[r for r in rows if r["source_sha256"]==case["sha256"] and
                r["rep"]==rep]
            item={"sha256":case["sha256"],"gbd":case["gbd"],
                  "group":case["group"],"seed":rep}
            item.update({r["mode"]:r["par2_s"] for r in rr})
            paired.append(item)
    adaptive_actions=dict(collections.Counter(
        r["adaptive_action"] for r in rows if r["mode"]=="r78_adaptive"))
    report=dict(status="PASS_UNOFFICIAL",protocol=PROTO,
        sources=N,trials=len(rows),distinct_source_sha=N,
        repeats=REPS,cap_s=CAP,
        source_manifest_sha256=digest(root/"manifest.json"),
        binary_sha256=dict(next(iter(pins))),
        strata=dict(collections.Counter(c["group"] for c in manifest["cases"])),
        quotas_achieved=manifest["quotas_achieved"],
        adaptive_actions=adaptive_actions,summary=group_totals,
        paired=paired,rows=rows,hosts=hosts,
        limitations=manifest["limitations"])
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    (out/"r78-final.json").write_text(json.dumps(report,indent=2)+"\n")
    import csv
    with (out/"paired.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["gbd","sha256","group","seed"]+list(MODES))
        w.writeheader();w.writerows(paired)
    make_scatter(paired,out/"r78-scatter.svg")
    md=["# R78: Unofficial frozen adaptive XOR vs Kissat / R28 / R65",
        f"24 original SAT2025 inputs; 3 repeats; 30s cap; {len(rows)} total trials.",
        "No runtime prescreen of problems; all original CNFs SHA-256 pinned.",
        f"Observed structure counts: {report['strata']}",
        f"Requested 8/8/8 feasible: {manifest['quotas_achieved']}",
        f"Adaptive actual actions: {adaptive_actions}","",
        "| Solver | Solved / 72 | Timeouts | PAR-2 (s) | Fastest solved (s) |",
        "|---|---:|---:|---:|---:|"]
    for mode,m in totals.items():
        md.append(f"| {mode} | {m['solved']}/72 | {m['timeouts']} | "
                  f"{m['par2_s']:.4f} | {m['fastest_s']} |")
    md+=["","## Important limitations"]+["- "+x for x in manifest["limitations"]]
    (out/"r78-final.md").write_text("\n".join(md)+"\n")
    print("R78_FINAL_AUDIT_PASS",json.dumps(dict(
        sources=N,trials=len(rows),strata=report["strata"],
        adaptive_actions=adaptive_actions,summary=totals)),flush=True)

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="cmd",required=True)
    f=sub.add_parser("freeze")
    for k in ("r63","r66","r67","r67final","r73","r77","kissat","out"):
        f.add_argument("--"+k,required=True)
    m=sub.add_parser("measure")
    for k in ("sources","binaries","out"):
        m.add_argument("--"+k,required=True)
    m.add_argument("--shard",type=int,required=True)
    a=sub.add_parser("audit")
    for k in ("sources","combined","out"):
        a.add_argument("--"+k,required=True)
    args=p.parse_args()
    if args.cmd=="freeze":freeze(args)
    elif args.cmd=="measure":measure(args)
    else:audit(args)

if __name__=="__main__":main()
