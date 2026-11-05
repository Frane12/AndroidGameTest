#!/usr/bin/env python3
"""R49: precommitted pivot-coherence guard for certified short resolvents.

R48 calibration uses TWO previously seen SATComp26 inputs, not a discovery
claim. Six further SATComp26 originals from R47 are also previously tested:
evaluation is prospective for the frozen R49 gate, NOT a new blind dataset.
Never changes V15.3.1 or pinned clean Kissat. Preprocessing, proof checks,
DIMACS rewrite and solving all consume the SAME 30s wall budget.
"""
from __future__ import annotations
import argparse, collections, hashlib, json, os, random, statistics
import subprocess, tempfile, time
from pathlib import Path
import r48_causal_clause_dose as r48
import r47_partial_links as r47
import r46_local_certified_links as r46
import r32p_real_satcomp26_benchmark as verify

PROTO="DRNAS-R49-FROZEN-PIVOT-COHERENCE-20261103-v1"
MODES=("clean","shadow","rewrite0","all","pivot16","gate")
CAP=30.0
REPS=2
SHARDS=4
CALIBRATION=set(r48.TARGETS.values())
# These values are frozen BEFORE inspecting any R49 timing results.
GATE_MIN_DERIVED=24
GATE_MIN_DOMINANCE=.80
PIVOT_CAP=16

def check(cond,detail):
    if not cond: raise RuntimeError("R49_PROVENANCE_OR_PROOF_FAIL: "+str(detail))

def sha(path):
    return r48.sha(path)

def cases(root):
    root=Path(root)
    manifest=json.loads((root/"manifest.json").read_text())
    check(manifest["protocol"].startswith("DRNAS-R32P-REAL-SATCOMP2026")
          and len(manifest["cases"])==8,"expected exact eight R47 sources")
    source_names=set()
    for c in manifest["cases"]:
        source=root/c["name"]
        check(source.is_file() and sha(source)==c["sha256"],
              "original CNF modified "+c["name"])
        check(c["sha256"] not in source_names,"duplicate source SHA")
        source_names.add(c["sha256"])
    return manifest

def compute_plan(original):
    derived, proofs, trace=r47.derive_partial(original)
    check(len(derived)==len(proofs) and len(derived)<=40,
          "unbounded or unpaired local resolvents")
    for clause,proof in zip(derived,proofs):
        check(tuple(proof["clause"])==tuple(clause) and
              len(proof["parent_ids"])==2 and len(proof["support"])<=5,
              "invalid 2-parent proof shape")
    pivots=collections.Counter(p["pivot"] for p in proofs)
    top_pivot,top_count=(pivots.most_common(1)[0] if pivots else (None,0))
    dominance=top_count/len(derived) if derived else 0.
    # On R48: the benefit case has 40/40 at one pivot; regression
    # 15/40 at the leading pivot. No use of any timing in this function.
    gate=len(derived)>=GATE_MIN_DERIVED and dominance>=GATE_MIN_DOMINANCE
    single=[list(c) for c,p in zip(derived,proofs) if p["pivot"]==top_pivot][:PIVOT_CAP]
    return dict(derived=len(derived),pivots=dict(sorted(pivots.items())),
        top_pivot=top_pivot,top_count=top_count,
        dominance=round(dominance,8),gate=gate,
        clauses=[list(c) for c in derived],single_pivot_16=single,
        proofs=proofs,trace=trace,
        certificate_sha256=r48.canon_clauses(derived))

def selftest():
    r48.selftest()
    with tempfile.TemporaryDirectory() as d:
        original=Path(d)/"three.cnf"
        original.write_text("p cnf 3 2\n1 2 0\n-1 3 0\n")
        plan=compute_plan(original)
        check(plan["derived"]>=1 and plan["gate"] is False,
              "small-support gate failed safe abstention")
        check([2,3] in plan["clauses"],"sound resolvent missed")
    print("R49_SELFTEST_CERTIFIED_REWRITE_GATE_PASS")

def freeze(a):
    root=Path(a.frozen)
    m=cases(root)
    result=dict(protocol=PROTO,
         manifest_sha256=sha(root/"manifest.json"),
         target_binary_source_run=41669951007,
         source_runner="R47 SHA-frozen SATComp2026 originals",
         cap_s=CAP,modes=list(MODES),repeats=REPS,
         preregistered_rule=dict(min_derived=GATE_MIN_DERIVED,
                                min_pivot_dominance=GATE_MIN_DOMINANCE,
                                top_pivot_clause_limit=PIVOT_CAP),
         limitations=[
            "Two R48 calibration cases were selected based on known divergent outcomes",
            "Other six original CNFs were already used for R47, not fresh official holdout",
            "Ordinary entailed resolvents, NOT proven XOR equations",
            "UNSAT without independent LRAT certificate",
            "No solver binary, heuristic or historical SQL changes"],
         cases={})
    for c in m["cases"]:
        p=compute_plan(root/c["name"])
        p.update(name=c["name"],source_sha256=c["sha256"],
                 gbd=c["gbd"],variables=c["vars"],original_clauses=c["clauses"],
                 cohort=("calibration_R48" if c["gbd"] in CALIBRATION
                         else "previously_seen_R47_validation"))
        result["cases"][c["name"]]=p
        print("R49_PRECOMMITTED_STRUCTURE",c["gbd"],
              "clauses",p["derived"],"top",p["top_count"],
              "dominance",p["dominance"],"gate",p["gate"],flush=True)
    Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    print("R49_FROZEN_DESIGN",sha(a.output),flush=True)

def selection(mode,plan):
    if mode in ("clean","shadow","rewrite0"): return []
    if mode=="all": return plan["clauses"]
    if mode=="pivot16": return plan["single_pivot_16"]
    if mode=="gate": return plan["clauses"] if plan["gate"] else []
    raise RuntimeError("unsupported mode")

def measure(a):
    root=Path(a.frozen)
    m=cases(root)
    design=json.loads(Path(a.design).read_text())
    check(design["protocol"]==PROTO and
          design["manifest_sha256"]==sha(root/"manifest.json"),
          "frozen design mismatch")
    check(a.shard in range(SHARDS),"shard")
    binary=Path(a.clean).resolve()
    check(binary.is_file(),"clean Kissat missing")
    cores=sorted(os.sched_getaffinity(0))
    check(cores,"no allocated core")
    os.sched_setaffinity(0,{cores[0]})
    out=Path(a.out)
    out.mkdir(parents=True,exist_ok=True)
    metadata=dict(protocol=PROTO,shard=a.shard,
        original_manifest_sha256=sha(root/"manifest.json"),
        frozen_design_sha256=sha(a.design),
        binary_sha256=sha(binary),
        run_sha=os.getenv("GITHUB_SHA","local"),
        run_id=os.getenv("GITHUB_RUN_ID","local"),
        runner=os.getenv("RUNNER_NAME","local"),cpu_core=cores[0],
        modes=MODES,repeats=REPS,timeout_s=CAP)
    (out/"meta.json").write_text(json.dumps(metadata,indent=2)+"\n")
    rows=[]
    for case in m["cases"][a.shard::SHARDS]:
        original=root/case["name"]
        plan=design["cases"][case["name"]]
        check(plan["source_sha256"]==case["sha256"],"source changed")
        for rep in range(REPS):
            seed=int(hashlib.sha256(
                 (case["sha256"]+":"+str(rep)+":"+PROTO).encode()
                 ).hexdigest(),16)
            order=list(MODES)
            random.Random(seed).shuffle(order)
            for mode in order:
                start=time.monotonic()
                added=[]
                with tempfile.TemporaryDirectory(prefix="drnas-r49-") as tmp:
                    candidate=original
                    if mode!="clean":
                        observed=compute_plan(original)
                        check(observed["certificate_sha256"]==plan["certificate_sha256"]
                              and observed["proofs"]==plan["proofs"]
                              and observed["gate"]==plan["gate"],
                              "frozen proof and structural gate drift")
                        added=selection(mode,plan)
                        if mode not in ("shadow",) and (added or mode=="rewrite0"):
                            candidate=Path(tmp)/"candidate.cnf"
                            rw=r48.safe_rewrite(original,candidate,added)
                            check(rw["added"]==len(added),
                                  "DIMACS parser did not see clauses")
                    prep_s=round(time.monotonic()-start,6)
                    remaining=CAP-(time.monotonic()-start)
                    if remaining<=0:
                        answer="TIMEOUT"
                    else:
                        try:
                            p=subprocess.run([str(binary),str(candidate)],
                                capture_output=True,text=True,errors="replace",
                                timeout=remaining)
                            check(p.returncode in (10,20),
                                  "unexpected Kissat exit "+str(p.returncode))
                            answer="SAT" if p.returncode==10 else "UNSAT"
                            if answer=="SAT":
                                verify.verify_sat_witness(original,p.stdout)
                        except subprocess.TimeoutExpired:
                            answer="TIMEOUT"
                    time_s=round(time.monotonic()-start,6)
                row=dict(source_sha256=case["sha256"],gbd=case["gbd"],
                   cohort=plan["cohort"],rep=rep,mode=mode,
                   order_seed=str(seed),answer=answer,time_s=time_s,
                   par2_s=time_s if answer!="TIMEOUT" else 2*CAP,
                   prep_s=prep_s,added=len(added),
                   derived=plan["derived"],pivot_dominance=plan["dominance"],
                   gate=plan["gate"],cert_sha=plan["certificate_sha256"])
                rows.append(row)
                print("R49_TRIAL",case["gbd"],rep,mode,answer,
                      time_s,"added",len(added),flush=True)
                (out/"rows.json").write_text(json.dumps(rows)+"\n")
    check(len(rows)==len(m["cases"][a.shard::SHARDS])*REPS*len(MODES),
          "incomplete shard")

def aggregate(a):
    design=json.loads(Path(a.design).read_text())
    check(design["protocol"]==PROTO,"design protocol drift")
    rows=[];binsha=set();seen=set()
    for shard in range(SHARDS):
        folder=Path(a.combined)/("r49-shard-"+str(shard))/"results"
        meta=json.loads((folder/"meta.json").read_text())
        check(meta["protocol"]==PROTO and meta["shard"]==shard
              and meta["frozen_design_sha256"]==sha(a.design)
              and meta["original_manifest_sha256"]==design["manifest_sha256"],
              "shard meta mismatch")
        binsha.add(meta["binary_sha256"])
        part=json.loads((folder/"rows.json").read_text())
        check(len(part)==2*REPS*len(MODES),"incomplete shard")
        rows+=part
    check(len(binsha)==1 and len(rows)==8*REPS*len(MODES),
          "missing real measurements")
    by=collections.defaultdict(dict)
    for r in rows:
        key=(r["source_sha256"],r["rep"],r["mode"])
        check(key not in seen,"duplicate attempt")
        seen.add(key)
        plan=next((p for p in design["cases"].values()
                  if p["source_sha256"]==r["source_sha256"]),None)
        check(plan is not None and r["cert_sha"]==plan["certificate_sha256"]
              and r["gate"]==plan["gate"] and
              r["added"]==len(selection(r["mode"],plan)),
              "frozen source, proof or gate changed")
        check(r["answer"] in ("SAT","UNSAT","TIMEOUT"),"bad status")
        check(abs(r["par2_s"]-(2*CAP if r["answer"]=="TIMEOUT"
              else r["time_s"]))<.001,"PAR2 mismatch")
        by[(r["source_sha256"],r["rep"])][r["mode"]]=r
    check(len(by)==8*REPS and all(set(p)==set(MODES) for p in by.values()),
          "mismatched paired comparison")
    for values in by.values():
        check(len({r["answer"] for r in values.values()
                   if r["answer"]!="TIMEOUT"})<=1,
              "SAT/UNSAT correctness disagreement")
    summary={}
    for cohort in ("all","calibration_R48","previously_seen_R47_validation"):
        cohort_rows=[r for r in rows if cohort=="all" or r["cohort"]==cohort]
        tmp={}
        for mode in MODES:
            sel=[r for r in cohort_rows if r["mode"]==mode]
            tmp[mode]=dict(n=len(sel),solved=sum(x["answer"]!="TIMEOUT" for x in sel),
                timeout=sum(x["answer"]=="TIMEOUT" for x in sel),
                par2_sum_s=round(sum(x["par2_s"] for x in sel),6),
                prep_sum_s=round(sum(x["prep_s"] for x in sel),6),
                injected_clauses=sum(x["added"] for x in sel))
        baseline=tmp["clean"]["par2_sum_s"]
        for mode in MODES:
            tmp[mode]["change_vs_clean_pct"]=(
                round(100*(tmp[mode]["par2_sum_s"]-baseline)/baseline,4)
                if baseline else None)
        summary[cohort]=tmp
    report=dict(protocol=PROTO,design_sha256=sha(a.design),
        formula_count=8,new_formula_count=0,attempts=len(rows),
        binary_sha256=next(iter(binsha)),summary=summary,rows=rows,
        provenance=design["limitations"],
        caveat="Known SATComp26 source identities; not fresh blind test")
    Path(a.output).write_text(json.dumps(report,indent=2)+"\n")
    lines=["# R49 pivot-coherence gate — 8 previously benchmarked SATComp26 originals",
       "A calibrated hypothesis, not an independently confirmed breakthrough.",
       "Two R48 selected calibration cases, six previously seen R47 evaluation cases.",
       "Positive percentage denotes slower than clean Kissat; all preprocessing counted.",
       ""]
    for cohort,info in summary.items():
        lines += ["## "+cohort,
          "| Mode | Solved | Total PAR2 s | Change from clean | Added clauses |",
          "|---|---:|---:|---:|---:|"]
        for mode in MODES:
            v=info[mode]
            lines.append("| "+mode+" | "+str(v["solved"])+"/"+str(v["n"])+
               " | "+str(v["par2_sum_s"])+" | "+str(v["change_vs_clean_pct"])+
               "% | "+str(v["injected_clauses"])+" |")
        lines.append("")
    lines += ["## Precommitted gate decisions",
       "| Source GBD | Cohort | Derived | Leading pivot fraction | Gate |",
       "|---|---|---:|---:|---|"]
    for p in design["cases"].values():
        lines.append("| "+p["gbd"]+" | "+p["cohort"]+" | "+str(p["derived"])+
           " | "+str(p["dominance"])+" | "+str(p["gate"])+" |")
    lines += ["","SAT witnesses checked against original CNF; no LRAT UNSAT proof.",
       "All clause additions are independently certified two-parent resolvents.",
       "Reusing the same 8 originals is NOT an official blind holdout."]
    Path(a.report).write_text("\n".join(lines)+"\n")
    print("R49_AUDIT_PASS",len(rows),json.dumps(summary,sort_keys=True))

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="task",required=True)
    sub.add_parser("selftest")
    z=sub.add_parser("freeze")
    for x in ("frozen","output"):z.add_argument("--"+x,required=True)
    z=sub.add_parser("measure")
    for x in ("frozen","design","clean","out"):z.add_argument("--"+x,required=True)
    z.add_argument("--shard",type=int,required=True)
    z=sub.add_parser("aggregate")
    for x in ("design","combined","output","report"):z.add_argument("--"+x,required=True)
    a=p.parse_args()
    {"selftest":lambda:selftest(),"freeze":lambda:freeze(a),
     "measure":lambda:measure(a),"aggregate":lambda:aggregate(a)}[a.task]()
if __name__=="__main__":
    main()
