#!/usr/bin/env python3
"""R170 measured first-used-reason replay on TWO prespecified positive R169 cases.
Development replay only, not blind; original SHA-frozen CNFs are unchanged.
A completed GF2 reason is a real IPASIR-UP reason callback, not necessarily a
saved conflict. Compare 90s end-to-end solve, PAR2, conflicts, and decisions.
Do not claim causal speedup from conflict-count differences at a timeout.
"""
import argparse, collections, hashlib, json, os, pathlib, random, subprocess, sys, time
sys.path.insert(0,str(pathlib.Path("research").resolve()))
import r165_component_benchmark as base

ROOT=pathlib.Path("r170")
base.ROOT=ROOT
base.FROZEN=ROOT/"frozen"
PROTO="DRNAS-R170-FIRST-USED-REASON-90S-PAIRED-20261106-v1"
REPS=2
SHARDS=2
CAP=90.0
MODES=("clean","direct_full","direct_two_way","direct_two_way_newonly","direct_two_way_shadow")
TARGETS=("3e912cd2a499b8f956246b866e2f9f64",
         "99718c1729a8de3347a9946f1836421d")
COUNTERS=("two_way_sweeps","two_way_row_xors","two_way_proposals","two_way_candidates",
          "two_way_multi_source_candidates","two_way_source_duplicate_units",
          "two_way_shadow_candidates","two_way_used_reasons",
          "two_way_abstentions","two_way_ns","direct_proposals",
          "reason_clauses_completed","propagate_ns","assignment_notify_ns",
          "backtrack_notify_ns")
FIRST=("r170_first_proposal_ms","r170_first_used_ms",
       "r170_first_proposal_notifications","r170_first_used_notifications")
def need(condition,reason):
    if not condition:raise RuntimeError("R170_FAIL_CLOSED "+str(reason))
def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def save(p,data):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
def cases():
    all_cases=base.sources()
    selected=[c for c in all_cases if c["id"] in TARGETS]
    need(len(selected)==2 and {c["id"] for c in selected}==set(TARGETS),
         "R169 prespecified cases absent from immutable R155 manifest")
    need(all(c["cohort"]=="mixed_residual" for c in selected),
         "mixed cohort changed")
    return sorted(selected,key=lambda c:TARGETS.index(c["id"]))
def trial(case,mode,rep,prep,binary):
    original=base.FROZEN/(case["id"]+".cnf")
    proof=ROOT/("full-"+case["id"]+".tsv")
    need(sha(original)==case["sha256"],"original CNF SHA drift")
    need(sha(proof)==prep["full_tsv_sha"],"certified XOR TSV drift")
    charged=0.0 if mode=="clean" else prep["preprocessing_s"]
    effective=CAP-charged
    need(effective>=1.0,"preprocessing over budget")
    start=time.perf_counter()
    try:
        proc=subprocess.run([str(binary.resolve()),mode,
              str(original.resolve()),str(proof.resolve()),str(effective)],
              stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=CAP+12.0)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("R170_UNGRACEFUL_NATIVE_TIMEOUT "+case["id"]) from exc
    elapsed=time.perf_counter()-start+charged
    need(proc.returncode in (0,10,20),
         "native exit code "+str(proc.returncode)+" "+proc.stderr[-600:].decode(errors="replace"))
    text,native,stats,source_rows,derived=base.parse_native(proc.stdout,mode)
    status={"SAT":"SAT","UNSAT":"UNSAT","UNKNOWN":"TIMEOUT"}[native["status"]]
    need(proc.returncode=={"SAT":10,"UNSAT":20,"TIMEOUT":0}[status],
         "native exit/status mismatch")
    expected_rows=0 if mode=="clean" else prep["full_rows"]
    need(source_rows==expected_rows,"source row count changed")
    need(abs(float(native["solver_s"])-(elapsed-charged))<0.5,
         "wall versus native solve time mismatch")
    if status=="SAT":
        need(native["source_sat_witness_checked"]=="1","native SAT model not checked")
        base.sat_check(original,text)
    m={key:int(native[key]) for key in COUNTERS+FIRST}
    need(0<=m["two_way_used_reasons"]<=m["two_way_proposals"],
         "consumed reason count invalid")
    need(m["two_way_multi_source_candidates"]<=m["two_way_candidates"],
         "multi-source candidates inconsistent")
    need(m["two_way_shadow_candidates"]<=m["two_way_candidates"],
         "shadow candidates inconsistent")
    need(m["reason_clauses_completed"]>=m["two_way_used_reasons"],
         "GF2 reason callbacks not counted")
    for suffix,count in (("proposal","two_way_proposals"),("used","two_way_used_reasons")):
        ms=m["r170_first_"+suffix+"_ms"]
        nt=m["r170_first_"+suffix+"_notifications"]
        need((ms>=0 and nt>=0)==(m[count]>0),
             "first event marker inconsistent for "+suffix)
        if ms>=0:need(ms<=CAP*1000+1000,"event timestamp outside cap")
    if m["two_way_used_reasons"]:
        need(m["r170_first_used_ms"]>=m["r170_first_proposal_ms"],
             "used GF2 reason before GF2 proposal")
    if mode=="direct_two_way_shadow":
        need(m["two_way_proposals"]==m["two_way_used_reasons"]==0,
             "shadow derived-unit leaked to CDCL")
    if mode in ("clean","direct_full"):
        need(m["two_way_proposals"]==0 and m["two_way_used_reasons"]==0,
             "control mode emitted Gaussian units")
    if mode in ("direct_two_way","direct_two_way_newonly"):
        need(m["two_way_shadow_candidates"]==0,"active GF2 units suppressed")
    need(stats.get("conflicts") is not None and stats.get("decisions") is not None,
         "missing genuine CaDiCaL conflict/decision counters")
    return dict(id=case["id"],sha256=case["sha256"],cohort=case["cohort"],
         mode=mode,repeat=rep,status=status,cap=CAP,elapsed=round(elapsed,6),
         par2=round(2*CAP if status=="TIMEOUT" else min(CAP,elapsed),6),
         charged_preprocess_s=charged,source_rows=source_rows,derived_rows=derived,
         proof="ORIGINAL_SAT_MODEL_INDEPENDENT_CHECK" if status=="SAT"
               else "UNSAT_NATIVE_NOT_LRAT" if status=="UNSAT" else "TIMEOUT",
         native_stats=stats,protocol=PROTO,**m)
def shard(index,binary):
    need(0<=index<SHARDS,"invalid shard")
    need(binary.is_file(),"missing native R170 executable")
    pin=json.loads((ROOT/"build-pin.json").read_text())
    need(pin["binary_sha256"]==sha(binary),"single binary SHA drift")
    need(pin["source_commit"]==os.getenv("GITHUB_SHA",pin["source_commit"]),
         "R170 runner commit drift")
    if hasattr(os,"sched_getaffinity"):
        cores=os.sched_getaffinity(0)
        if cores:os.sched_setaffinity(0,{min(cores)})
    case=cases()[index]
    prep=base.prepare(case)
    rows=[]
    for rep in range(REPS):
        order=list(MODES)
        random.Random(PROTO+case["sha256"]+str(rep)).shuffle(order)
        for mode in order:
            r=trial(case,mode,rep,prep,binary)
            rows.append(r)
            save(ROOT/("shard-"+str(index)+".json"),rows)
            print("R170_TRIAL",json.dumps(dict(
                id=r["id"],mode=mode,rep=rep,status=r["status"],
                par2=r["par2"],conflicts=r["native_stats"]["conflicts"],
                decisions=r["native_stats"]["decisions"],
                derived_emitted=r["two_way_proposals"],
                consumed_reasons=r["two_way_used_reasons"],
                first_GF2_proposal_ms=r["r170_first_proposal_ms"],
                first_GF2_used_ms=r["r170_first_used_ms"]),sort_keys=True),flush=True)
    need(len(rows)==REPS*len(MODES),"incomplete R170 shard")
    print("R170_SHARD_PASS",index,len(rows),flush=True)
def audit():
    selected=cases()
    rows=[]
    for i,case in enumerate(selected):
        p=ROOT/("shard-"+str(i)+".json")
        need(p.is_file(),"missing paired shard")
        piece=json.loads(p.read_text())
        need(len(piece)==REPS*len(MODES),"incomplete paired shard")
        prep=json.loads((ROOT/("prep-"+case["id"]+".json")).read_text())
        cert=json.loads((ROOT/("cert-"+case["id"]+".json")).read_text())
        base.independent_cert(case,cert)
        need(prep["source_sha256"]==case["sha256"]==
             sha(base.FROZEN/(case["id"]+".cnf")),"source checksum drift")
        need(prep["full_tsv_sha"]==sha(ROOT/("full-"+case["id"]+".tsv")),
             "certified XOR equations corrupted")
        for r in piece:
            need(r["sha256"]==case["sha256"] and r["id"]==case["id"],
                 "attempt source drift")
            need(r["protocol"]==PROTO and r["cap"]==CAP,"protocol changed")
            need(abs(r["par2"]-(2*CAP if r["status"]=="TIMEOUT"
                    else min(CAP,r["elapsed"])))<0.0001,"PAR2 miscomputed")
            if r["status"]=="SAT":
                need(r["proof"]=="ORIGINAL_SAT_MODEL_INDEPENDENT_CHECK",
                     "SAT model not rechecked")
        proved={r["status"] for r in piece if r["status"]!="TIMEOUT"}
        need(len(proved)<=1,"contradictory SAT/UNSAT result")
        rows+=piece
    keys={(r["sha256"],r["mode"],r["repeat"]) for r in rows}
    need(len(keys)==len(rows)==len(selected)*len(MODES)*REPS==20,
         "expected 20 unique paired measurements")
    summary={}
    for mode in MODES:
        sub=[r for r in rows if r["mode"]==mode]
        used=[r for r in sub if r["r170_first_used_ms"]>=0]
        summary[mode]=dict(
          trials=len(sub),solved=sum(r["status"]!="TIMEOUT" for r in sub),
          PAR2_s=round(sum(r["par2"] for r in sub),6),
          wall_s=round(sum(r["elapsed"] for r in sub),6),
          cdcl_conflicts=sum(r["native_stats"]["conflicts"] for r in sub),
          cdcl_decisions=sum(r["native_stats"]["decisions"] for r in sub),
          novel_multisource_candidates=sum(r["two_way_multi_source_candidates"] for r in sub),
          emitted_Gaussian_units=sum(r["two_way_proposals"] for r in sub),
          used_Gaussian_reasons=sum(r["two_way_used_reasons"] for r in sub),
          first_used_ms_values=[r["r170_first_used_ms"] for r in used],
          used_in_trials=len(used),
          GF2_processing_ns=sum(r["two_way_ns"] for r in sub))
    report=dict(status="RESEARCH_REPLAY_AUDIT_PASS_NOT_BLIND",
       protocol=PROTO,original_formulas=2,attempts=len(rows),
       prespecified_R169_positive_SHA_cases=TARGETS,
       source_certificates_replayed=True,
       SAT_witnesses_independently_checked=True,
       independent_UNSAT_LRAT_available=False,
       source_run_R169=42153494705,
       source_R155_frozen_run=42112755104,
       one_pinned_native_binary=True,
       cap_s=CAP,results=summary,records=rows,
       conclusions=["Used GF2 reason callbacks are real causal integration events, not solved-time proof.",
          "Conflicts/decisions at equal timeout alone do not prove saved search effort.",
          "These are two pre-exposed development instances, not blind holdout.",
          "No rank or world-record assertions permitted from this test."])
    save(ROOT/"report.json",report)
    with (ROOT/"summary.md").open("w") as f:
        f.write("# DRNAS R170 — two positive R169 mixed instances, 90-second paired replay\n\n")
        f.write("Previously seen CNFs: **not blind**; 20 trials, same original SHA, same compiled solver binary.\n\n")
        f.write("| Mode | Solved | PAR2 (s) | Conflicts | Gaussian units | Actually used reasons | First used (ms) |\n")
        f.write("|---|---:|---:|---:|---:|---:|---|\n")
        for mode in MODES:
            v=summary[mode]
            f.write(f'| {mode} | {v["solved"]}/{v["trials"]} | {v["PAR2_s"]:.2f} | {v["cdcl_conflicts"]} | {v["emitted_Gaussian_units"]} | {v["used_Gaussian_reasons"]} | {v["first_used_ms_values"]} |\n')
        f.write("\nConflict differences at a fixed timeout are not proof of faster solving. External UNSAT proof absent.\n")
    print("R170_FINAL",json.dumps(dict(status=report["status"],
            attempts=report["attempts"],formulas=2,summary=summary),
            sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--binary",default="r170/r170-native")
    args=p.parse_args()
    shard(args.shard,pathlib.Path(args.binary)) if args.action=="shard" else audit()
