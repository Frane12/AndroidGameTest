#!/usr/bin/env python3
"""R32t real-world mixed-XOR test: certified short XOR cuts vs identical Kissat.

The 17 exact 2026 SHA-originals from R32s are NOT new blind instances.
This test is a structural mechanism check of a *frozen* short-GF2 policy
(width <=5, <=64 new XOR rows and <=1024 original-CNF-entailment clauses).

Two native mode inputs are SAT-equivalent by independent GF2 proof.
Both use the SAME R32s read-only Kissat binary, OFF GF2 injection, phase
and conflict progress enabled. Unmodified clean Kissat provides a reference.
One process per trial, no portfolio and no search policy/watchdog changes.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,random,shutil,statistics,subprocess,time
from pathlib import Path
import r32t_certified_short_xor as cuts
import r32s_long_mixedxor_benchmark as r32s
import r32r_more_real_satcomp26_benchmark as r32r

PROTO="DRNAS-R32T-REAL2026-CERTIFIED-SHORT-XOR-CUTS-20261103-v1"
PARENT_PROTO="DRNAS-R32S-SAME17-120S-PASSIVE-XOR-CDCL-20261103-v1"
SHARDS=8
REPS=1
CAP=120.0
MODES=("clean_original","native_original","native_xor_cuts")

def check(b,msg):
    if not b:raise RuntimeError("R32T_BENCH_AUDIT_FAILURE "+str(msg))
def sha(p):return r32r.sha(p)

def freeze(prior,out):
    prior=Path(prior);out=Path(out)
    parent=json.loads((prior/"manifest.json").read_text())
    check(parent["protocol"]==PARENT_PROTO and len(parent["external_originals"])==17,
          "Only original source-frozen R32s 17 official 2026 inputs allowed")
    originals=out/"original";augmented=out/"augmented";proofs=out/"certificates"
    for folder in (originals,augmented,proofs):folder.mkdir(parents=True,exist_ok=True)
    rows=[]
    for c in parent["external_originals"]:
        name=c["name"];src=prior/name
        check(sha(src)==c["sha256"],"Original SHA differs from prior certified 2026 source")
        shutil.copyfile(src,originals/name)
        target=augmented/name
        cert=proofs/(c["gbd"]+".json")
        result=cuts.build(src,target,cert)
        cuts.audit(src,target,cert)
        check(result["sha256_original"]==c["sha256"],
              "Certificate did not preserve exact original DIMACS")
        rows.append(dict(gbd=c["gbd"],name=name,
             original_sha256=c["sha256"],
             augmented_sha256=result["sha256_augmented"],
             parity_axioms=result["axioms"],rank=result["rank"],
             free=result["free"],short_candidates=result["new_short_candidates"],
             chosen=result["chosen_short_equations"],added=result["added_clauses"],
             skip_reason=result["derivation_guard"],
             certificate_file=c["gbd"]+".json",n=c["vars"],m=c["clauses"]))
    n_active=sum(q["chosen"]>0 for q in rows)
    check(any(x["gbd"].startswith("7db30d12") and x["chosen"]>0 for x in rows),
          "Known 857-equation source must have at least one certified new short relation")
    check(n_active>=2,"No real-world GF2 candidate cohort; test invalid")
    info=dict(protocol=PROTO,parent_protocol=PARENT_PROTO,
         parent_manifest_sha256=sha(prior/"manifest.json"),
         sources=rows,source_count=17,modes=MODES,shards=SHARDS,
         repeats=REPS,timeout_seconds=CAP,
         cases_with_active_cuts=n_active,
         rules=dict(max_xor_width=cuts.MAX_NEW_WIDTH,
                    max_equations=cuts.MAX_NEW_EQUATIONS,
                    max_new_clauses=cuts.MAX_NEW_CLAUSES,
                    max_input_vars=cuts.CAP_VARIABLES,
                    max_input_bytes=cuts.CAP_BYTES),
         limitations=[
           "This is *not* a fresh unseen holdout: original 17 formulas already used in R32r/R32s",
           "Existing parity Gauss elimination is known mathematics; no complexity breakthrough claim",
           "Adding entailed CNF clauses is source-level preprocessing, NOT native XOR-CDCL integration",
           "Candidate rows chosen only by lexicographic short support, NEVER runtime feedback",
           "Original/augmented formulas are equivalent because every cut has a GF2 combination proof",
           "UNSAT outputs lack external LRAT/DRAT verification; SAT models checked against original",
           "Potential performance effect comes from redundant clause guiding and processing overhead",
           "Single trial per case and policy, 120s right censoring, PAR2=240s",
           "Original clean/native control to account for tracer overhead",
           "Sources under guard are byte-identical; claimed speedup requires an actually altered source",
           "No adaptation of solver policies, no communications between solvers, no watcher",
           "Not official competition hardware, time limit or leaderboard"])
    (out/"manifest.json").write_text(json.dumps(info,indent=2)+"\n")
    (out/"original.sha256").write_text("".join(f'{x["original_sha256"]}  original/{x["name"]}\n' for x in rows))
    (out/"augmented.sha256").write_text("".join(f'{x["augmented_sha256"]}  augmented/{x["name"]}\n' for x in rows))
    print("R32T_FROZEN_AND_CERTIFIED_PASS",len(rows),"originals",
          n_active,"cases with new short XOR cuts",
          sum(c["added"] for c in rows),"total entailed source clauses",flush=True)

def run_one(case,orig,aug,mode,binaries):
    env=os.environ.copy()
    env["R32B_MODE"]="off"
    env["R32S_PASSIVE_TRACE"]="1" if mode!="clean_original" else "0"
    env["R32L_TRACE"]="0"
    env["R32M_PHASES"]="0"
    binary=binaries["clean"] if mode=="clean_original" else binaries["native"]
    input_file=aug if mode=="native_xor_cuts" else orig
    start=time.monotonic();timeout=False
    try:
        p=subprocess.run([str(binary),str(input_file)],
             stdout=subprocess.PIPE,stderr=subprocess.PIPE,
             text=True,errors="replace",env=env,timeout=CAP)
        result="SAT" if p.returncode==10 else "UNSAT" if p.returncode==20 else "ERROR"
        check(result!="ERROR","Native solver fault "+str(p.returncode)+" "+p.stderr[-300:])
        output=p.stdout
    except subprocess.TimeoutExpired as err:
        timeout=True;result="TIMEOUT"
        output=err.stdout or b""
        if isinstance(output,bytes):output=output.decode(errors="replace")
    elapsed=time.monotonic()-start
    if result=="SAT":r32r.verify_sat_witness(orig,output)
    control="clean" if mode=="clean_original" else "native_off"
    progress=r32s.trace_log(output,control,not timeout)
    telemetry=r32r.native_telemetry(output,control,orig)
    check(telemetry["injected"]==0,"Unexpected native GF2 injection during CNF-cut test")
    return dict(answer=result,wall_s=round(elapsed,6),
        par2_s=round(elapsed,6) if result!="TIMEOUT" else CAP*2,
        original_sat_model_verified=(result=="SAT"),
        output_input_sha256=case["augmented_sha256"] if mode=="native_xor_cuts" else case["original_sha256"],
        new_entailed_cnf_clauses=case["added"] if mode=="native_xor_cuts" else 0,
        trace=progress,telemetry=telemetry)

def measure(a):
    root=Path(a.inputs);m=json.loads((root/"manifest.json").read_text())
    check(m["protocol"]==PROTO and len(m["sources"])==17,
          "Wrong exact source cohort")
    check(0<=a.shard<SHARDS,"Wrong shard")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    binpaths={k:Path(getattr(a,k)).resolve() for k in ("clean","native")}
    check(all(x.is_file() for x in binpaths.values()),"Missing pinned binaries")
    folder=Path(a.out);folder.mkdir(parents=True,exist_ok=True)
    meta=dict(shard=a.shard,source_manifest_sha=sha(root/"manifest.json"),
              binary_sha256={k:sha(v) for k,v in binpaths.items()})
    (folder/"meta.json").write_text(json.dumps(meta,indent=2)+"\n")
    rows=[]
    for case in m["sources"][a.shard::SHARDS]:
        o=root/"original"/case["name"];d=root/"augmented"/case["name"]
        proof=root/"certificates"/case["certificate_file"]
        check(sha(o)==case["original_sha256"] and
              sha(d)==case["augmented_sha256"],"Changed original/derived source SHA")
        cuts.audit(o,d,proof)
        for rep in range(REPS):
            order=list(MODES)
            rnd=int(hashlib.sha256((PROTO+case["original_sha256"]+str(rep)).encode()).hexdigest(),16)
            random.Random(rnd).shuffle(order)
            for mode in order:
                row=run_one(case,o,d,mode,binpaths)
                rows.append(dict(gbd=case["gbd"],n=case["n"],m=case["m"],
                    chosen_cuts=case["chosen"],added_clauses=case["added"],
                    repetition=rep,mode=mode,**row))
                print("R32T_TRIAL",case["gbd"],mode,row["answer"],
                      row["wall_s"],"PAR2",row["par2_s"],
                      "certified_added",row["new_entailed_cnf_clauses"],
                      "conflicts_at_checkpoint",row["trace"]["last_conflicts"],
                      "cdcl",row["trace"]["entered_cdcl"],flush=True)
        (folder/"rows.json").write_text(json.dumps(rows)+"\n")
    print("R32T_SHARD_PASS",a.shard,len(rows),"single solver attempts",flush=True)

def aggregate(a):
    root=Path(a.inputs);m=json.loads((root/"manifest.json").read_text())
    check(m["protocol"]==PROTO,"Unknown source manifest")
    rows=[];pair_binaries=set()
    for shard in range(SHARDS):
        folder=Path(a.combined)/f"r32t-shard-{shard}"/"results"
        meta=json.loads((folder/"meta.json").read_text())
        check(meta["shard"]==shard and
              meta["source_manifest_sha"]==sha(root/"manifest.json"),
              "Different original SHA between jobs")
        pair_binaries.add(json.dumps(meta["binary_sha256"],sort_keys=True))
        sub=json.loads((folder/"rows.json").read_text())
        check(len(sub)==len(m["sources"][shard::SHARDS])*REPS*len(MODES),
              "Missing serial tests from shard")
        rows.extend(sub)
    check(len(rows)==17*REPS*len(MODES) and len(pair_binaries)==1,
          "Missing 51 trials or different pinned solvers")
    original={c["gbd"]:c for c in m["sources"]}
    percase=[]
    for gbd,case in original.items():
        trials=[x for x in rows if x["gbd"]==gbd]
        check(len(trials)==3 and {x["mode"] for x in trials}==set(MODES),
              "Missing case/mode pair")
        verdict={x["answer"] for x in trials}-{"TIMEOUT"}
        check(len(verdict)<=1,"Wrong SAT decision after entailed CNF cuts")
        time_by={x["mode"]:dict(answer=x["answer"],wall_s=x["wall_s"],
                  par2_s=x["par2_s"],last_conflicts=x["trace"]["last_conflicts"],
                  cdcl_entered=x["trace"]["entered_cdcl"]) for x in trials}
        percase.append(dict(gbd=gbd,n=case["n"],m=case["m"],
              parity_axioms=case["parity_axioms"],rank=case["rank"],
              chosen=case["chosen"],added=case["added"],
              cut_generation_guard=case["skip_reason"],
              times=time_by))
    summary={}
    for mode in MODES:
        sub=[x for x in rows if x["mode"]==mode]
        active=[x for x in sub if original[x["gbd"]]["added"]>0]
        summary[mode]=dict(solved=sum(x["answer"]!="TIMEOUT" for x in sub),
           timed_out=sum(x["answer"]=="TIMEOUT" for x in sub),
           PAR2_sum_s=round(sum(x["par2_s"] for x in sub),6),
           active_sources=len(active),
           active_subset_PAR2_s=round(sum(x["par2_s"] for x in active),6))
    data=dict(protocol=PROTO,summary=summary,
              active_formula_count=m["cases_with_active_cuts"],
              candidates=m["sources"],cases=percase,rows=rows,
              limitations=m["limitations"])
    Path(a.output).write_text(json.dumps(data,indent=2)+"\n")
    md=["# R32t — 120s real SATComp2026 original versus certified short parity cuts",
        "**Same 17 previously seen original CNFs**, 51 serial single-Kissat tries; source-only mathematically entailed clauses.",
        "R32t does NOT add arbitrary root values: 857 eq on flagship 7db CNF have rank 857 but no singleton root consequence.",
        "Every augmented clause is certified by an independently verified XOR combination of complete original parity clause sets.",
        "Exactly identical native Kissat on both original and augmented inputs; only source CNF differs.",
        "One run per mode, 120s cap; 240s PAR2 for timeouts; SAT witness validated against original.",
        "Existing XOR Gaussian elimination, **not** novel universal SAT algorithm.",
        "",
        "| Mode | Solved of 17 | Timeouts | Total PAR2 s | Active-cut-source PAR2 s |",
        "|---|---:|---:|---:|---:|"]
    for mode in MODES:
        v=summary[mode]
        md.append(f'| {mode} | {v["solved"]}/17 | {v["timed_out"]} | {v["PAR2_sum_s"]:.5f} | {v["active_subset_PAR2_s"]:.5f} |')
    md+=["","## Original and entailed-CNF wall times (seconds)",
         "| 2026 official GBD prefix | Original CNF clauses | Recognized XOR axioms | New certified XOR equations | Clauses appended | Clean orig | Native orig | Native + XOR cuts |",
         "|---|---:|---:|---:|---:|---:|---:|---:|"]
    def t(entry):
        return f'{entry["wall_s"]:.3f}' if entry["answer"]!="TIMEOUT" else "TIMEOUT ≥120"
    for x in percase:
        p=x["times"]
        md.append(f'| {x["gbd"][:12]}… | {x["m"]} | {x["parity_axioms"]} | {x["chosen"]} | {x["added"]} | {t(p["clean_original"])} | {t(p["native_original"])} | {t(p["native_xor_cuts"])} |')
    md+=["","## Interpretation",
      "Where added clauses are zero, original and augmented CNFs are byte-identical,",
      "so differences are scheduler/runner noise and cannot be claimed as an XOR effect.",
      "Where cuts are present, any improvement or regression is a causal source-level",
      "redundant-clause intervention; it is not yet native XOR-aware CDCL reasoning.",
      "Sparse read-only CDCL conflict/phase logs are included in the machine-readable artifact.",
      "This is a known-source mechanism test, NOT a new blind official SAT validation.",
      "A frozen prospective holdout with new originals is needed for generalization."]
    Path(a.report).write_text("\n".join(md)+"\n")
    print("R32T_CERTIFIED_51_REAL_SAT_AUDIT_PASS",
        "active",m["cases_with_active_cuts"],
        json.dumps(summary,sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    subs=p.add_subparsers(dest="cmd",required=True)
    x=subs.add_parser("freeze")
    x.add_argument("--prior",required=True);x.add_argument("--out",required=True)
    x=subs.add_parser("measure")
    for f in ("inputs","clean","native","out"):x.add_argument("--"+f,required=True)
    x.add_argument("--shard",required=True,type=int)
    x=subs.add_parser("aggregate")
    for f in ("inputs","combined","output","report"):x.add_argument("--"+f,required=True)
    a=p.parse_args()
    if a.cmd=="freeze":freeze(a.prior,a.out)
    elif a.cmd=="measure":measure(a)
    else:aggregate(a)

if __name__=="__main__":main()
