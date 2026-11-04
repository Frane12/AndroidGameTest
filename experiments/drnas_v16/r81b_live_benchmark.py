#!/usr/bin/env python3
"""R80: retrospective SAT Competition 2026 XOR-STRUCTURE-ONLY benchmark.

Only verified parity clause structure and SHA rank select 24 previously
tested real originals from R63, with matched non-XOR/unsupported controls.
NO solver runtime is used for source selection. This is NOT unseen/blind.
All timings include adaptive and preprocessing overhead; originals and
unchanged Kissat/R28 are SHA256 verified. Results are not world rankings.
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
import r81b_gf2_core as r81b

PROTO="DRNAS-R81B-GF2-CERTIFIED-NATIVE-CDCL-20261104-v1"
R80_SOURCE_PROTO="DRNAS-R80-FROZEN-STRUCTURAL-ADAPTIVE-20261104-v1"
SALT="DRNAS-R80-24-ORIGINAL-SAT2025-NO-TIMING-PRESCREEN-20261104"
N, SHARDS, REPS, CAP=24,8,3,30.0
MODES=("clean_kissat","r28_gf2","r65_full","r80_adaptive","r81b_gf2_learn")
# Predetermined structural gates (no performance tuning on R80).
MIXED_MIN_BLOCKS=4
MIXED_MIN_COVERAGE=0.015
PREP_BUDGET_S=2.0

def check(ok,msg):
    if not ok:raise RuntimeError("R80_FAIL_CLOSED "+str(msg))

def digest(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for b in iter(lambda:f.read(1<<20),b""):
            h.update(b)
    return h.hexdigest()

def freeze(args):
    """Select SHA-ranked REAL 2026 originals based solely on complete XOR encodings.

    Reuses the historical R63 SOURCE cohort (retrospective, not fresh).
    No Kissat, R28, or R65 runtime is examined for formula selection.
    """
    from shutil import copyfile
    import r67_xor_structural_diagnostics as r67
    original_root=Path(args.sources)
    old_manifest=original_root/"manifest.json"
    check(old_manifest.is_file(), "missing R63 original-source manifest")
    prior=json.loads(old_manifest.read_text())
    check(prior["protocol"]==r63.PROTO and len(prior["cases"])==32,
          "R63 real SAT2026 source manifest invalid")
    pin=digest(Path(args.kissat))
    check(Path(args.kissat).is_file(), "missing pinned Kissat")
    check(len({c["sha256"] for c in prior["cases"]})==32,
          "historical R63 source SHA duplicates")
    annotated=[]
    for orig in prior["cases"]:
        p=original_root/orig["filename"]
        check(p.is_file() and digest(p)==orig["sha256"],
              "original R63 CNF missing or source SHA changed")
        c=dict(orig)
        c["group"]=r64.group(c)
        check(c["official_status"] in ("SAT","UNSAT"),
              "source lacks external competition status")
        annotated.append(c)
    positives=sorted([c for c in annotated if c["group"] in
        ("pure_exact","mixed_exact")],key=lambda c:c["sha256"])
    negatives=sorted([c for c in annotated if c["group"] not in
        ("pure_exact","mixed_exact")],key=lambda c:c["sha256"])
    check(len(positives)>=8, "insufficient proven real XOR sources")
    positive_selected=positives[:12]
    check(len(negatives)>=N-len(positive_selected),
          "insufficient structural controls")
    chosen=positive_selected+negatives[:N-len(positive_selected)]
    check(len(chosen)==N and len({c["gbd"] for c in chosen})==N,
          "not 24 structurally selected sources")
    out=Path(args.out)
    out.mkdir(parents=True,exist_ok=True)
    cases=[]
    for case in chosen:
        orig=original_root/case["filename"]
        dest=out/case["filename"]
        copyfile(orig,dest)
        check(digest(dest)==case["sha256"],"copy/source SHA drift")
        case["r67_features"]=r67.passive_features(dest,case)
        cases.append(case)
    groups=dict(collections.Counter(c["group"] for c in cases))
    mf=dict(protocol=PROTO,ready=N,cases=cases,
        registry=dict(binary_sha=pin,
                      frozen_original_R63_manifest_sha=digest(old_manifest),
                      source_run_id=41707669490),
        source_sha256_verified=True,
        source_corpus="original SAT Competition 2026 Main CNFs",
        source_reused=True,
        fresh_holdout=False,
        selected_by="verified complete XOR parity support only; SHA-sorted, NOT solver runtimes",
        past_timing_inspected_for_selection=False,
        total_old_r63=32,
        positive_available=len(positives),
        positives_selected=len(positive_selected),
        controls_selected=N-len(positive_selected),
        group_counts=groups,
        repeats=REPS,shards=SHARDS,bench_cap_s=CAP,
        modes=list(MODES),
        gate_rule=dict(
            pure_exact_route="R28 if >=2 complete blocks",
            mixed_exact_route="R65 if >=4 blocks AND >=0.015 coverage",
            otherwise="original Kissat",
            runtime_pre_scan_charged=True,
            r65_max_prep_s=PREP_BUDGET_S),
        quotas_achieved=groups.get("pure_exact",0)>=8 and
                        groups.get("mixed_exact",0)>=8 and
                        groups.get("no_exact",0)>=8,
        limitations=[
          "This is a structural replay on previously seen R63 official SAT2026 original CNFs, NOT an independent blind holdout.",
          "Selection uses only verified complete parity clause encodings and SHA order, never solve seconds.",
          "Source categories are not manufactured. Unscannable does NOT imply no XOR.",
          "Formula selection before this experiment is retrospective and may have unknown historical biases.",
          "Compared on identical original CNF; all R65 preparation and adaptive scanning charged in PAR-2.",
          "Same runner image but GitHub's hosts may have different hardware; CPU logged per shard.",
          "SAT assignments independently checked; UNSAT is checked against imported official 2026 status, not a fresh LRAT proof.",
          "No claim of world ranking, P=NP, or transferable performance on unseen sources."])
    (out/"manifest.json").write_text(json.dumps(mf,indent=2,sort_keys=True)+"\n")
    (out/"source.sha256").write_text("".join(
        c["sha256"]+"  "+c["filename"]+"\n" for c in cases))
    print("R80_FREEZE_PASS",json.dumps(dict(sources=N,positive_available=len(positives),
        selected_xor=len(positive_selected),controls=N-len(positive_selected),
        groups=groups,no_speed_selection=True,source_reused=True)),flush=True)

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
    check(manifest["protocol"]==R80_SOURCE_PROTO and manifest["ready"]==N,
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
                with tempfile.TemporaryDirectory(prefix="r80-policy-") as tmp:
                    if mode=="r28_gf2":
                        argv=[gf2,source,kissat]
                        action="r28"
                    elif mode=="r80_adaptive":
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
                        action="r28" if case["pure_exact_xor"] else "r65"
                        if action=="r28":
                            argv=[gf2,source,kissat]
                    elif mode=="r81b_gf2_learn":
                        action="r81b"
                    proof_meta={}
                    if action=="r65":
                        _,_,clauses,_,stats=r71.prepare(root,case)
                        clauses_added=len(clauses)
                        if clauses:
                            target=Path(tmp)/"augmented.cnf"
                            r64.augment(source,target,case["variables"],
                                        case["clauses"],clauses)
                        argv=[kissat,target]
                    elif action=="r81b":
                        clauses,proof_meta=r81b.derive(source,case,budget_s=1.8)
                        clauses_added=len(clauses)
                        if clauses:
                            target=Path(tmp)/"r81b-certified-augmented.cnf"
                            r64.augment(source,target,case["variables"],
                                        case["clauses"],clauses)
                        argv=[kissat,target]
                    overhead=time.monotonic()-t0
                    remaining=CAP-overhead
                    answer,solved_wall,timeout,solver_route=run_solver(
                        argv,source,remaining)
                    if answer!="UNKNOWN":
                        check(answer==case["official_status"],
                              "solver disagrees with official SAT2026 verdict")
                    elapsed=time.monotonic()-t0
                    solved=answer!="UNKNOWN" and not timeout and elapsed<=CAP
                    row=dict(source_id=case["gbd"],source_sha256=case["sha256"],
                        group=case["group"],rep=rep,mode=mode,answer=answer,
                        solved=solved,pre_scan_s=round(scan_s,6),
                        preprocess_and_scan_s=round(overhead,6),
                        solver_wall_s=round(solved_wall,6),
                        end_to_end_s=round(elapsed,6),
                        par2_s=round(elapsed if solved else 2*CAP,6),
                        adaptive_action=action if mode=="r80_adaptive" else None,
                        new_clauses=clauses_added,solver_route=solver_route,
                        r81b_route=proof_meta.get("route"),
                        r81b_derived_rows=proof_meta.get("derived_rows",0),
                        r81b_proof_sha256=proof_meta.get("proof_sha256"),
                        runner=os.environ.get("RUNNER_NAME",""),
                        runner_os=os.environ.get("RUNNER_OS",""),
                        commit=os.environ.get("GITHUB_SHA",""),
                        seed=rep,
                        run_id=os.environ.get("GITHUB_RUN_ID",""),
                        solver_sha256=digest(gf2 if action=="r28" else kissat))
                    results.append(row)
                    print("R80_TRIAL",json.dumps({k:row[k] for k in
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
    (outdir/"r81b-shard.json").write_text(json.dumps(report,indent=2)+"\n")
    print("R80_SHARD_PASS",args.shard,len(results),flush=True)

def make_scatter(pairs,path):
    dim=480; margin=48; size=dim-2*margin
    # One dot per paired formula and seed: Kissat X vs R80 Y, both PAR-2.
    def fx(x):return margin+size*max(0,min(60,x))/60
    def fy(y):return dim-margin-size*max(0,min(60,y))/60
    svg=[f'<svg xmlns="http://www.w3.org/2000/svg" width="{dim}" height="{dim}" viewBox="0 0 {dim} {dim}">',
         '<rect width="100%" height="100%" fill="white"/>',
         f'<line x1="{margin}" y1="{dim-margin}" x2="{dim-margin}" y2="{margin}" stroke="#777" stroke-dasharray="6 4"/>',
         f'<line x1="{margin}" y1="{dim-margin}" x2="{dim-margin}" y2="{dim-margin}" stroke="#222"/>',
         f'<line x1="{margin}" y1="{margin}" x2="{margin}" y2="{dim-margin}" stroke="#222"/>',
         '<text x="250" y="466" text-anchor="middle" font-size="13">Kissat PAR-2 (s)</text>',
         '<text transform="translate(14,250) rotate(-90)" text-anchor="middle" font-size="13">R80 PAR-2 (s)</text>']
    for item in pairs:
        x,y=item["clean_kissat"],item["r80_adaptive"]
        svg.append(f'<circle cx="{fx(x):.1f}" cy="{fy(y):.1f}" r="3.5" fill="#316ad2" fill-opacity=".5"/>')
    svg.append("</svg>")
    path.write_text("\n".join(svg)+"\n")

def audit(args):
    root=Path(args.sources)
    manifest=json.loads((root/"manifest.json").read_text())
    check(manifest["protocol"]==R80_SOURCE_PROTO and manifest["ready"]==N,
          "wrong final manifest")
    check(len({c["sha256"] for c in manifest["cases"]})==N,
          "duplicate source in audit")
    pins=set(); rows=[]; hosts=[]
    for shard in range(SHARDS):
        p=Path(args.combined)/f"r81b-shard-{shard}"/"results"/"r81b-shard.json"
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
        r["adaptive_action"] for r in rows if r["mode"]=="r80_adaptive"))
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
    (out/"r81b-final.json").write_text(json.dumps(report,indent=2)+"\n")
    import csv
    with (out/"paired.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=["gbd","sha256","group","seed"]+list(MODES))
        w.writeheader();w.writerows(paired)
    make_scatter(paired,out/"r81b-scatter.svg")
    md=["# R81-B: certified GF(2) short-lemma native Kissat BCP experiment",
        f"24 original SAT2026 (historical R63/R80) inputs; 3 repeats; 30s cap; {len(rows)} total trials.",
        "NO blind holdout: reused SHA-pinned R80 source cohort selected from R63 SAT Competition 2026 originals.",
        "No solve-time prescreen of these sources; all original CNFs SHA-256 pinned.",
        "R81B derives proof-traced GF(2) short rows before solve; original native Kissat propagates learned CNF clauses during CDCL. NOT true incremental Gauss-in-search.",
        f"Observed structure counts: {report['strata']}",
        f"Requested 8/8/8 feasible: {manifest['quotas_achieved']}",
        f"Adaptive actual actions: {adaptive_actions}","",
        "| Solver | Solved / 72 | Timeouts | PAR-2 (s) | Fastest solved (s) |",
        "|---|---:|---:|---:|---:|"]
    for mode,m in totals.items():
        md.append(f"| {mode} | {m['solved']}/72 | {m['timeouts']} | "
                  f"{m['par2_s']:.4f} | {m['fastest_s']} |")
    md+=["","## Important limitations"]+["- "+x for x in manifest["limitations"]]
    (out/"r81b-final.md").write_text("\n".join(md)+"\n")
    print("R81B_FINAL_AUDIT_PASS",json.dumps(dict(
        sources=N,trials=len(rows),strata=report["strata"],
        adaptive_actions=adaptive_actions,summary=totals)),flush=True)

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="cmd",required=True)
    f=sub.add_parser("freeze")
    for k in ("sources","kissat","out"):
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
