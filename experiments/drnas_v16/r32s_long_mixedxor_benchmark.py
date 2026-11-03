#!/usr/bin/env python3
"""R32s: 120s single-solver, real SATComp26 mixed-XOR / CDCL progress study.

Frozen EXACT R32r SHA originals, 17 CNFs. No new cherry-picked instances.
3 policies: clean Kissat; same native with R32n GF2 off and read-only tracing;
same native with R32n mathematically-certified GF2 root units plus tracing.
A side-car R28 classify-only pass is *separate* from measured solves:
it describes sound explicit parity blocks and fallback/guard state, but does
not itself claim to improve Kissat or discover hidden parity generally.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,random,re,statistics,subprocess,time
from pathlib import Path
import r32r_more_real_satcomp26_benchmark as old

PROTO="DRNAS-R32S-SAME17-120S-PASSIVE-XOR-CDCL-20261103-v1"
CAP=120.0
REPS=1
SHARDS=8
MODES=("clean","native_off","full")
BASE_PROTOCOL="DRNAS-R32R-PROSPECTIVE-REAL2026-EXACT-GF2-20261103-v1"

def assert_ok(test,msg):
    if not test:raise RuntimeError("R32S_AUDIT_FAILURE "+str(msg))
def sha(p):return old.sha(p)

def freeze_from_r32r(source,out):
    source=Path(source);out=Path(out)
    data=json.loads((source/"manifest.json").read_text())
    assert_ok(data["protocol"]==BASE_PROTOCOL,"Requires original R32r SHA manifest")
    assert_ok(len(data["cases"])==17,"Exactly the previous 17 2026 originals")
    assert_ok(len({x["sha256"] for x in data["cases"]})==17,"Source identity duplication")
    for case in data["cases"]:
        path=source/case["name"]
        assert_ok(sha(path)==case["sha256"],"Original DIMACS SHA drift")
    out.mkdir(parents=True,exist_ok=True)
    frozen=dict(protocol=PROTO,
        inherited_original_manifest_sha256=sha(source/"manifest.json"),
        inherited_original_protocol=data["protocol"],
        external_originals=data["cases"],
        selected_source_ids=[c["gbd"] for c in data["cases"]],
        rejected_precommitted_candidates=[x for x in data["complete_download_log"] if x["status"]!="READY"],
        modes=MODES,shards=SHARDS,repeats=REPS,timeout_seconds=CAP,
        notes=[
          "The 17 official sources are inherited SHA-exactly from completed R32r 30s study",
          "Previously observed sources: this is follow-on 120s study, not a new blind holdout",
          "One solver per attempt, no concurrent solver portfolios or search watchdog",
          "Hard 120s test cap is external benchmark resource limit, not CDCL intervention",
          "Original upstream source commit pinned, original CNF SAT witnesses verified",
          "Native OFF and Full use identical read-only CDCL/phase trace for fair comparison",
          "GF2 source proof independently checked only if a unit is actually injected",
          "R28 classify-only parity recovery is descriptive, not a solver speedup",
          "R28 source guard does not prove absence of XOR parity on a guarded formula",
          "Sparse conflict milestones are progress only, not full CDCL internal states",
          "Unsatisfiable status compared across modes; no independently verified LRAT",
          "120s timeout is right censored, PAR2=240 seconds for unsolved runs",
          "One repeat per formula and mode: performance noise and runner bias remain",
          "Not the official competition hardware and cutoff, not representative overall standings"])
    (out/"manifest.json").write_text(json.dumps(frozen,indent=2)+"\n")
    (out/"source.sha256").write_text("".join(
        f'{c["sha256"]}  {c["name"]}\n' for c in data["cases"]))
    print("R32S_FROZEN_17_OFFICIAL_SHA_PASS",len(data["cases"]),
          sha(out/"manifest.json"),flush=True)

def route_report(text):
    rows=[line for line in text.splitlines() if line.startswith("c R28_ROUTE ")]
    assert_ok(len(rows)==1,"R28 classifier must report one route")
    line=rows[0]
    if line.startswith("c R28_ROUTE fallback "):
        props=dict(re.findall(r"(\w+)=([^\s]+)",line))
        for key in ("clauses","covered","equations"):
            assert_ok(key in props,"Missing classifier counter: "+key)
        return dict(route="fallback",reason=props.get("reason","unreported"),
                    examined_clause_count=int(props["clauses"]),
                    complete_parity_covered_clauses=int(props["covered"]),
                    equations=int(props["equations"]),
                    coverage_known=props.get("reason") not in
                       ("invalid_or_over_limit","equation_limit"))
    if line.startswith("c R28_ROUTE certified_pure_xor_sat "):
        props=dict(re.findall(r"(\w+)=([^\s]+)",line))
        return dict(route="certified_pure_xor_sat",reason=None,
                    equations=int(props["equations"]),
                    rank=int(props["rank"]),
                    complete_parity_covered_clauses=int(props["covered"]),
                    examined_clause_count=int(props["clauses"]),
                    coverage_known=True)
    if line.startswith("c R28_ROUTE certified_xor_contradiction "):
        props=dict(re.findall(r"(\w+)=([^\s]+)",line))
        return dict(route="certified_xor_contradiction",reason=None,
                    equations=int(props["equations"]),rank=int(props["rank"]),
                    complete_parity_covered_clauses=int(props["covered"]),
                    examined_clause_count=int(props["clauses"]),
                    coverage_known=True)
    raise RuntimeError("R32S_AUDIT_FAILURE unknown exact parity route")

def classify_source(source,r28,clean,timeout=18):
    t=time.monotonic()
    try:
        proc=subprocess.run([str(r28),str(source),str(clean),"--classify-only"],
            capture_output=True,text=True,errors="replace",timeout=timeout)
        assert_ok(proc.returncode==0,
                  "R28 classify-only error code "+str(proc.returncode)+" "+proc.stderr[-180:])
        d=route_report(proc.stdout)
        d["classification_elapsed_s"]=round(time.monotonic()-t,5)
        return d
    except subprocess.TimeoutExpired:
        return dict(route="classification_timeout",reason="bounded_18s",
                    coverage_known=False,equations=None,
                    complete_parity_covered_clauses=None,
                    classification_elapsed_s=round(time.monotonic()-t,5))

EVENT_RE=re.compile(r"^c R32S_TRACE event=([a-z_]+) mark=(\d+) cpu_ms=([0-9.]+)"
  r" conflicts=(\d+) decisions=(\d+) propagations=(\d+)"
  r" restarts=(\d+) learned=(\d+) trail=(\d+)$",re.MULTILINE)
EVENT_TYPES={"entry","lucky_early_start","lucky_early_end",
    "preprocess_start","preprocess_end","lucky_late_start","lucky_late_end",
    "cdcl_start","conflict_milestone","finished"}

def trace_log(text,mode,completed):
    hits=list(EVENT_RE.finditer(text))
    if mode=="clean":
        assert_ok(not hits,"Clean Kissat unexpectedly contains native progress trace")
        return dict(checkpoints=[],start_seen=False,entered_cdcl=None,
                    last_phase="not_instrumented",last_conflicts=None)
    events=[]
    for m in hits:
        kind,mark,cpu,conf,dec,prop,restart,learned,trail=m.groups()
        assert_ok(kind in EVENT_TYPES,"Unknown read-only CDCL checkpoint")
        events.append(dict(event=kind,mark=int(mark),cpu_ms=float(cpu),
             conflicts=int(conf),decisions=int(dec),propagations=int(prop),
             restarts=int(restart),learned=int(learned),trail=int(trail)))
    if events:
        assert_ok(events[0]["event"]=="entry","Native progress started after solver entry")
        for x,y in zip(events,events[1:]):
            assert_ok(y["cpu_ms"]>=x["cpu_ms"]-0.002,
                      "Native CPU clock jumped backwards")
            for field in ("conflicts","decisions","propagations",
                          "restarts","learned"):
                assert_ok(y[field]>=x[field],"Native CDCL counters not monotonic")
        milestones=[x["mark"] for x in events if x["event"]=="conflict_milestone"]
        assert_ok(milestones==sorted(set(milestones)),
                  "Unordered/repeated conflict milestones")
        if completed:
            assert_ok(events[-1]["event"]=="finished",
                      "Native SAT verdict ended without terminal checkpoint")
    return dict(checkpoints=events,
      start_seen=bool(events),entered_cdcl=any(x["event"]=="cdcl_start" for x in events),
      last_phase=next((x["event"] for x in reversed(events)),"source_parse_or_guard"),
      last_conflicts=events[-1]["conflicts"] if events else None,
      last_cpu_ms=events[-1]["cpu_ms"] if events else None)

def one(case,source,mode,binaries):
    env=os.environ.copy()
    env["R32B_MODE"]="r32k" if mode=="full" else "off"
    env["R32K_VARIANT"]="full"
    env["R32S_PASSIVE_TRACE"]="1" if mode!="clean" else "0"
    env["R32L_TRACE"]="0"
    env["R32M_PHASES"]="0"
    binary=binaries["clean"] if mode=="clean" else binaries["native"]
    started=time.monotonic()
    timeout=False
    try:
        proc=subprocess.run([str(binary),str(source)],env=env,
             stdout=subprocess.PIPE,stderr=subprocess.PIPE,
             text=True,errors="replace",timeout=CAP)
        answer="SAT" if proc.returncode==10 else "UNSAT" if proc.returncode==20 else "ERROR"
        assert_ok(answer!="ERROR","Kissat crashed "+str(proc.returncode)+" "+proc.stderr[-220:])
        output=proc.stdout
    except subprocess.TimeoutExpired as ex:
        timeout=True
        answer="TIMEOUT"
        output=ex.stdout or b""
        if isinstance(output,bytes):output=output.decode(errors="replace")
    elapsed=time.monotonic()-started
    if answer=="SAT":
        old.verify_sat_witness(source,output)
    detail=trace_log(output,mode,not timeout)
    telemetry=old.native_telemetry(output,mode,source)
    assert_ok(telemetry["injected"]==0 or mode=="full",
              "Native OFF or clean injected an algebraic clause")
    return dict(answer=answer,wall_s=round(elapsed,6),
      par2_s=round(elapsed,6) if not timeout else 2*CAP,
      telemetry=telemetry,progress=detail)

def measure(args):
    root=Path(args.inputs)
    m=json.loads((root/"manifest.json").read_text())
    assert_ok(m["protocol"]==PROTO and len(m["external_originals"])==17,
             "Wrong frozen original 2026 archive")
    assert_ok(0<=args.shard<SHARDS,"Shard ID")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    binaries={v:Path(getattr(args,v)).resolve() for v in ("clean","native","r28")}
    assert_ok(all(v.is_file() for v in binaries.values()),"Missing pinned binaries")
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    (out/"meta.json").write_text(json.dumps(dict(
       shard=args.shard,manifest_sha=sha(root/"manifest.json"),
       binaries={k:sha(v) for k,v in binaries.items()},
       parser_protocol=PROTO),indent=2))
    rows=[];profiles=[]
    cases=m["external_originals"][args.shard::SHARDS]
    for case in cases:
        original=root/case["name"]
        assert_ok(sha(original)==case["sha256"],"Original 2026 DIMACS SHA changed")
        classification=classify_source(original,binaries["r28"],binaries["clean"])
        classification.update(dict(gbd=case["gbd"],vars=case["vars"],
                                   clauses=case["clauses"],source_sha256=case["sha256"]))
        profiles.append(classification)
        print("R32S_XOR_STRUCTURE",json.dumps(classification,sort_keys=True),flush=True)
        for repetition in range(REPS):
            order=list(MODES)
            random.Random(int(hashlib.sha256((PROTO+case["sha256"]+str(repetition)).encode()).hexdigest(),16)).shuffle(order)
            for mode in order:
                row=one(case,original,mode,binaries)
                rows.append(dict(gbd=case["gbd"],n=case["vars"],
                    m=case["clauses"],repeat=repetition,mode=mode,**row))
                print("R32S_TRIAL",case["gbd"],mode,row["answer"],
                    row["wall_s"],"PAR2",row["par2_s"],
                    "injected",row["telemetry"]["injected"],
                    "CDCL",row["progress"]["entered_cdcl"],
                    "last_conflicts",row["progress"]["last_conflicts"],flush=True)
        (out/"rows.json").write_text(json.dumps(rows)+"\n")
        (out/"profiles.json").write_text(json.dumps(profiles)+"\n")
    print("R32S_SHARD_PASS",args.shard,len(cases),"official",
          len(rows),"serial solving attempts",flush=True)

def aggregate(args):
    root=Path(args.inputs)
    m=json.loads((root/"manifest.json").read_text())
    assert_ok(m["protocol"]==PROTO,"Wrong R32s frozen source file")
    rows=[];profiles=[];binary_set=set()
    for shard in range(SHARDS):
        folder=Path(args.combined)/f"r32s-shard-{shard}"/"results"
        meta=json.loads((folder/"meta.json").read_text())
        assert_ok(meta["shard"]==shard and meta["manifest_sha"]==sha(root/"manifest.json"),
                  "Source manifest SHA inconsistent across runners")
        binary_set.add(json.dumps(meta["binaries"],sort_keys=True))
        shard_rows=json.loads((folder/"rows.json").read_text())
        p=json.loads((folder/"profiles.json").read_text())
        assert_ok(len(shard_rows)==len(m["external_originals"][shard::SHARDS])*len(MODES)*REPS,
                  "Unpaired 120s solver sample")
        rows.extend(shard_rows);profiles.extend(p)
    assert_ok(len(binary_set)==1 and len(rows)==17*len(MODES)*REPS,
              "Incomplete or mismatched 120s original trials")
    assert_ok(len(profiles)==17 and len({x["gbd"] for x in profiles})==17,
              "Incorrect or duplicate parity structure classification")
    byid={c["gbd"]:[r for r in rows if r["gbd"]==c["gbd"]] for c in m["external_originals"]}
    pc={c["gbd"]:c for c in profiles}
    table=[]
    for case in m["external_originals"]:
        data=byid[case["gbd"]]
        assert_ok({x["mode"] for x in data}==set(MODES),
                  "Original formula missing one intervention arm")
        verdicts={x["answer"] for x in data if x["answer"]!="TIMEOUT"}
        assert_ok(len(verdicts)<=1,"Different original SAT/UNSAT verdicts")
        pol={}
        for mode in MODES:
            rec=next(x for x in data if x["mode"]==mode)
            pol[mode]=dict(answer=rec["answer"],wall_s=rec["wall_s"],
                           par2_s=rec["par2_s"],injected=rec["telemetry"]["injected"],
                           last_conflicts=rec["progress"]["last_conflicts"],
                           cdcl_entered=rec["progress"]["entered_cdcl"],
                           last_phase=rec["progress"]["last_phase"])
        structure=pc[case["gbd"]]
        cov=structure.get("complete_parity_covered_clauses")
        frac=100*cov/case["clauses"] if structure.get("coverage_known") and cov is not None else None
        table.append(dict(gbd=case["gbd"],n=case["vars"],m=case["clauses"],
            structure=dict(route=structure["route"],equations=structure["equations"],
                  covered_clauses=cov,covered_pct=round(frac,3) if frac is not None else None,
                  limitation=structure.get("reason")),
            policies=pol))
    summary={}
    for mode in MODES:
        sample=[x for x in rows if x["mode"]==mode]
        summary[mode]=dict(solved=sum(x["answer"] in ("SAT","UNSAT") for x in sample),
          timeouts=sum(x["answer"]=="TIMEOUT" for x in sample),
          sum_PAR2_s=round(sum(x["par2_s"] for x in sample),6),
          XOR_active=sum(x["telemetry"]["injected"]>0 for x in sample),
          cdcl_confirmed=sum(x["progress"]["entered_cdcl"] is True for x in sample),
          progress_traces=sum(x["progress"]["start_seen"] for x in sample))
    report=dict(protocol=PROTO,source_manifest_sha=sha(root/"manifest.json"),
      summary=summary,originals=table,parity_profiles=profiles,rows=rows,
      source_limitations=m["notes"])
    Path(args.output).write_text(json.dumps(report,indent=2)+"\n")
    md=["# R32s — 120-second real SAT Competition 2026 mixed XOR/CDCL test",
        "SAME 17 exact SHA-audited sources from R32r. Already seen in 30s test.",
        "One CPU-pinned solver per trial; one repetition, three modes, 120s cap (PAR2=240s).",
        "Read-only milestones in *native* binary record conflict counts and preprocess/CDCL entry",
        "even when no solver finishes. R28 classify-only describes original exact-XOR blocks;",
        "these do not imply the partial XOR equations were used in CDCL.",
        "No process racing, watchdog heuristic or inter-solver communication.",
        "Timeouts right-censored, not solved in 120s. Not official machine/leaderboard.",
        "",
        "| Policy | Solved / 17 | 120s timeout | PAR2 sum s | Active certified unit insertions |",
        "|---|---:|---:|---:|---:|"]
    for mode in MODES:
        k=summary[mode]
        md.append(f'| {mode} | {k["solved"]}/17 | {k["timeouts"]} | {k["sum_PAR2_s"]:.4f} | {k["XOR_active"]} |')
    md+=["","## Each official formula: wall time, XOR coverage, CDCL progress",
         "| GBD ID | Var | Clauses | Complete XOR equations | XOR clause coverage | Clean wall s | OFF wall s | GF2 wall s | Injected | Native OFF conflicts at last checkpoint | GF2 conflicts at last checkpoint |",
         "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for c in table:
        a=c["policies"];p=c["structure"]
        coverage=f'{p["covered_pct"]:.2f}%' if p["covered_pct"] is not None else "not measured (guard)"
        def tim(k):
            x=a[k]
            return f'{x["wall_s"]:.3f}' if x["answer"]!="TIMEOUT" else "TIMEOUT ≥120s"
        md.append(f'| {c["gbd"][:12]}… | {c["n"]} | {c["m"]} | {p["equations"] if p["equations"] is not None else "guard"} | {coverage} | {tim("clean")} | {tim("native_off")} | {tim("full")} | {a["full"]["injected"]} | {a["native_off"]["last_conflicts"]} | {a["full"]["last_conflicts"]} |')
    md+=["","## Scientific interpretation",
         "If native Full injects no original-source-certified units, any difference from OFF",
         "is measurement/instrumentation noise, not a proven causal XOR speedup.",
         "Exact parity equations can cover only part of a mixed CNF; direct R28 elimination",
         "cannot automatically solve the remaining clauses. Classification is read-only.",
         "CDCL checkpoint counts are partial evidence of progress; they do not measure",
         "learnt clause quality or prove causal effect of parity constraints.",
         "Compare phase labels and unresolved original problems with a stronger parity-aware",
         "baseline in a later prospective benchmark before trying safe native integration."]
    Path(args.report).write_text("\n".join(md)+"\n")
    print("R32S_120S_ORIGINAL_AUDIT_PASS",len(rows),
          json.dumps(summary,sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    subs=p.add_subparsers(dest="action",required=True)
    q=subs.add_parser("freeze")
    q.add_argument("--prior",required=True);q.add_argument("--out",required=True)
    q=subs.add_parser("measure")
    for key in ("inputs","clean","native","r28","out"):q.add_argument("--"+key,required=True)
    q.add_argument("--shard",type=int,required=True)
    q=subs.add_parser("aggregate")
    for key in ("inputs","combined","output","report"):q.add_argument("--"+key,required=True)
    a=p.parse_args()
    if a.action=="freeze":freeze_from_r32r(a.prior,a.out)
    elif a.action=="measure":measure(a)
    else:aggregate(a)

if __name__=="__main__":main()
