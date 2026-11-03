#!/usr/bin/env python3
"""R32u: source-certified live native XOR-CDCL implications versus passive.

Previously studied 2026 official SAT CNFs, same single pinned Kissat.
Intervention: when all but one variable of an independently original-CNF-
entailed parity equation have values on the native CDCL trail, derive the
missing literal and add a native CNF reason for it *during search*.

No fake speedup from out-of-band scripts or parallel solver process racing.
No watchdog policy or learned-clause heuristics tuning. Fixed 75-second cap
is benchmark resource limit. SAT models checked against original CNF.
"""
from __future__ import annotations
import argparse,hashlib,json,os,pathlib,random,re,shutil,subprocess,time
from pathlib import Path
import r32s_long_mixedxor_benchmark as prior
import r32r_more_real_satcomp26_benchmark as standard
import r32t_certified_short_xor as cert

PROTO="DRNAS-R32U-NATIVE-XOR-TRAIL-REASONS-20261103-v1"
CAP=75.0
MODES=("clean","passive","active")
# Precommitted based on known structural XOR coverage, not runtime response:
# 3 previously established partial-XOR sources, 2 sources with no active
# certified short-XOR cuts. NOT a new blind holdout.
GBD=[
  "12535b3264a9c88bac14522171b497ef",
  "7db30d12cb06f0dc2f30abff80d96d6a",
  "b76b9699c2deb74dd9b4a99a05179acd",
  "e305def35c314eec8266087e89a9ab46",
  "fca71c20202ef404349136c3a00465eb"
]
REPS=1
SHARDS=5
def check(x,m):
    if not x:raise RuntimeError("R32U_BENCH_AUDIT_FAILURE "+str(m))
def digest(path):return standard.sha(path)

def freeze(parent,out):
    parent=Path(parent);out=Path(out)
    old=json.loads((parent/"manifest.json").read_text())
    check(old["protocol"]=="DRNAS-R32S-SAME17-120S-PASSIVE-XOR-CDCL-20261103-v1",
          "R32s original CNF input provenance required")
    cases={v["gbd"]:v for v in old["external_originals"]}
    check(set(GBD)<=set(cases) and len(set(GBD))==SHARDS,
          "Original 2026 official case identity changed")
    out.mkdir(parents=True,exist_ok=True)
    selected=[]
    for gbd in GBD:
        c=cases[gbd];src=parent/c["name"]
        check(digest(src)==c["sha256"],"Previously audited source SHA mismatch")
        shutil.copyfile(src,out/c["name"])
        selected.append(dict(gbd=gbd,name=c["name"],
              sha256=c["sha256"],n=c["vars"],m=c["clauses"],
              bytes=c["bytes"]))
    data=dict(protocol=PROTO,cases=selected,source_parent_sha256=digest(parent/"manifest.json"),
       source_parent_protocol=old["protocol"],modes=MODES,shards=SHARDS,
       repeats=REPS,timeout_s=CAP,
       constraints=[
         "Five previously seen official SAT Competition 2026 original CNFs, NOT blind",
         "Three candidate XOR-structured formulas selected by preexisting source structure",
         "Two known non-active source controls included irrespective of performance",
         "Single native Kissat solver process for each trial, identical source pinned commit",
         "Only active native original-proven XOR conditional CNF reason propagation differs",
         "Pass-through and active XOR extraction source work is identical",
         "SAT model verified independently against the untouched official original CNF",
         "UNSAT model not independently LRAT/DRAT proof certified",
         "R32u uses short source-entailed GF2 RREF rows, width <=5",
         "No new source input preparation, restart policy, process racing, or watchdog",
         "Timeouts censored at 75s, PAR2=150s for unsolved attempts",
         "One trial per mode/source: noisy, NO world ranking or broad performance claims"])
    (out/"manifest.json").write_text(json.dumps(data,indent=2)+"\n")
    (out/"original.sha256").write_text("".join(
        f'{c["sha256"]}  {c["name"]}\n' for c in selected))
    print("R32U_OFFICIAL_5_FROZEN_SHA_PASS",len(selected),flush=True)

SOURCE_ROW=re.compile(r"^c R32U_SOURCE_ROW rhs=(\d+) vars=([\d,]+)$",re.M)
BASIS=re.compile(r"^c R32U_BASIS original_equations=(\d+) rank=(\d+) free=(\d+)"
                 r" candidates=(\d+) selected=(\d+) root_units=(\d+)$",re.M)
MODE_RE=re.compile(r"^c R32U_MODE active=(\d+) prepared=(\d+) max_reasons=(\d+)$",re.M)
EVENT=re.compile(r"^c R32U_ASSIGN equation=(\d+) target_ext=(\d+) sign=(-?\d+) level=(\d+)"
                 r" decisions=(\d+) conflicts=(\d+)$",re.M)
STATS=re.compile(r"^c R32U_STATS active=(\d+) rows=(\d+) scans=(\d+) candidates=(\d+)"
                 r" attached=(\d+) conflict_rows=(\d+) conflicts=(\d+) decisions=(\d+)$",re.M)
def verify_equations_are_original_certified(source,stdout):
    rows=[(tuple(map(int,vs.split(","))),int(rhs)) for rhs,vs in
          SOURCE_ROW.findall(stdout)]
    if not rows:return 0
    info,guard=cert.load_original(source)
    check(guard is None,"R32u row reported on source beyond exact-XOR proof scope")
    axioms=cert.complete_parity_axioms(info)
    derived=cert.certificates(info["n"],axioms)
    cert.reconstruct_and_verify(axioms,derived["chosen"])
    proven={(tuple(v),rhs) for v,rhs,_ in derived["chosen"]}
    check(all(x in proven for x in rows),
          "Native dynamic XOR equation was not independently proven from original complete parity CNF")
    return len(rows)

def preflight(source,binary,out):
    # This is external bounded research preflight, not a parallel solver.
    for active in (0,1):
        env=os.environ.copy()
        env.update(R32B_MODE="r32u",R32U_ACTIVE=str(active),
                   R32S_PASSIVE_TRACE="1",R32L_TRACE="0")
        try:
            p=subprocess.run([str(binary),str(source)],env=env,
               stdout=subprocess.PIPE,stderr=subprocess.PIPE,
               text=True,errors="replace",timeout=3.0)
            stdout=p.stdout
            check(p.returncode in (10,20),
                  "Native proof preflight failed "+str(p.returncode)+" "+p.stderr[-500:])
        except subprocess.TimeoutExpired as exc:
            stdout=exc.stdout or b""
            if isinstance(stdout,bytes):stdout=stdout.decode(errors="replace")
        r=verify_equations_are_original_certified(source,stdout)
        if source.name.startswith("7db30d12"):
            check(r==31,"Flagship 857-equation RREF must expose all 31 proven rows")
        print("R32U_SOURCE_ROWS_INDEPENDENT_PASS",source.name,"active",active,"validated",r,flush=True)

def parse_native(stdout,mode,finished):
    if mode=="clean":
        check(not BASIS.search(stdout) and not EVENT.search(stdout),
              "Clean solver contains custom XOR code")
        return dict(prepared=0,rows_certified=0,attached=0,
                    attached_at_least=0,attached_exact=True,reported_events=0,
                    last_conflicts=None,cdcl_entered=None,
                    rref_rank=None,rref_free=None)
    basis=BASIS.findall(stdout)
    check(len(basis)<=1,"More than one native GF2 source basis")
    mode_rows=MODE_RE.findall(stdout)
    check(len(mode_rows)==1,"Native probe missed exact active/passive mode tag")
    actual_active=int(mode=="active")
    check(int(mode_rows[0][0])==actual_active,"Native XOR mode differs from requested")
    reported=int(mode_rows[0][1])
    rows=[(tuple(map(int,vs.split(","))),int(rhs)) for rhs,vs in
          SOURCE_ROW.findall(stdout)]
    check(len(rows)==reported,"Native original XOR row count and ABI disagree")
    if basis:
        check(int(basis[0][4])==reported,"Bad native GF2 row selection accounting")
    events=EVENT.findall(stdout)
    if mode=="passive":
        check(not events,"Passive baseline illegally assigned XOR reason")
    stats=STATS.findall(stdout)
    if finished:
        check(len(stats)==1,"Completed solver omitted native final XOR stats")
        stat=tuple(map(int,stats[0]))
        check(stat[0]==actual_active and stat[1]==reported,
              "Native final XOR mode or row count mismatch")
        attached=stat[4]
        check(mode=="active" or attached==0,
              "Passive solver internally attached native reason")
    else:
        check(not stats,"Timeout should not report completed solver stats")
        attached=max((int(e[0])+1 for e in []),default=0) if False else 0
        # Every first 16th and every 32nd attach is printed.  For timeout
        # logs, this is only a lower bound, never a complete count.
        if events:
            attached=max(0,(len(events)//1))  # first 16, then sparse; lower bound
    milestones=prior.EVENT_RE.findall(stdout)
    last=milestones[-1] if milestones else None
    return dict(prepared=reported,
        rows_certified=None,attached=attached,
        attached_at_least=attached,attached_exact=finished,
        reported_events=len(events),last_conflicts=int(last[3]) if last else None,
        cdcl_entered=any(e[0]=="cdcl_start" for e in milestones),
        rref_rank=int(basis[0][1]) if basis else None,
        rref_free=int(basis[0][2]) if basis else None)

def run_trial(case,source,mode,compiled):
    env=os.environ.copy()
    env.update(R32B_MODE="r32u",R32U_ACTIVE="1" if mode=="active" else "0",
               R32S_PASSIVE_TRACE="1" if mode!="clean" else "0",
               R32L_TRACE="0",R32M_PHASES="0")
    executable=compiled["clean"] if mode=="clean" else compiled["native"]
    start=time.monotonic()
    try:
        p=subprocess.run([str(executable),str(source)],env=env,
            capture_output=True,text=True,errors="replace",timeout=CAP)
        stdout=p.stdout
        answer={10:"SAT",20:"UNSAT"}.get(p.returncode,"ERROR")
        check(answer!="ERROR","Kissat process failed "+str(p.returncode)+" "+p.stderr[-500:])
        finished=True
    except subprocess.TimeoutExpired as exc:
        stdout=exc.stdout or b""
        if isinstance(stdout,bytes):stdout=stdout.decode(errors="replace")
        answer="TIMEOUT";finished=False
    elapsed=time.monotonic()-start
    if answer=="SAT":standard.verify_sat_witness(source,stdout)
    details=parse_native(stdout,mode,finished)
    count=verify_equations_are_original_certified(source,stdout) if mode!="clean" else 0
    check(details["prepared"]==count,"Native proof mismatch in measured trial")
    details["rows_certified"]=count
    return dict(mode=mode,answer=answer,
                wall_s=round(elapsed,6),
                par2_s=round(elapsed,6) if finished else CAP*2,
                native=details,original_witness_checked=(answer=="SAT"))

def measure(a):
    root=Path(a.inputs);manifest=json.loads((root/"manifest.json").read_text())
    check(manifest["protocol"]==PROTO and len(manifest["cases"])==5,"Wrong source cohort")
    check(0<=a.shard<SHARDS,"Invalid shard")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    binaries={k:Path(getattr(a,k)).resolve() for k in ("clean","native")}
    check(all(x.is_file() for x in binaries.values()),"Missing binaries")
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    info=dict(shard=a.shard,source_manifest_sha=digest(root/"manifest.json"),
              binary_sha={k:digest(v) for k,v in binaries.items()})
    (out/"meta.json").write_text(json.dumps(info,indent=2)+"\n")
    case=manifest["cases"][a.shard]
    source=root/case["name"]
    check(digest(source)==case["sha256"],"Official original mutated during test")
    preflight(source,binaries["native"],out)
    ordered=list(MODES)
    random.Random(int(hashlib.sha256((PROTO+case["sha256"]).encode()).hexdigest(),16)).shuffle(ordered)
    rows=[]
    for mode in ordered:
        result=run_trial(case,source,mode,binaries)
        rows.append(dict(gbd=case["gbd"],n=case["n"],m=case["m"],**result))
        print("R32U_TRIAL",case["gbd"],mode,result["answer"],
              result["wall_s"],"seconds", "PAR2",result["par2_s"],
              "new_root_reason_clauses",result["native"]["attached_at_least"],
              "prepared",result["native"]["prepared"],
              "last_conflicts",result["native"]["last_conflicts"],flush=True)
    (out/"rows.json").write_text(json.dumps(rows,indent=2)+"\n")
    print("R32U_OFFICIAL_SHARD_PASS",a.shard,case["gbd"],flush=True)

def aggregate(a):
    root=Path(a.inputs);m=json.loads((root/"manifest.json").read_text())
    check(m["protocol"]==PROTO,"Wrong source identity")
    rows=[];binsets=set()
    for shard in range(SHARDS):
        folder=Path(a.combined)/f"r32u-shard-{shard}"/"results"
        meta=json.loads((folder/"meta.json").read_text())
        check(meta["source_manifest_sha"]==digest(root/"manifest.json") and meta["shard"]==shard,
              "Stale/incorrect original formulas or shard")
        binsets.add(json.dumps(meta["binary_sha"],sort_keys=True))
        v=json.loads((folder/"rows.json").read_text())
        check(len(v)==3 and {x["mode"] for x in v}==set(MODES),"Unpaired control")
        answers={x["answer"] for x in v if x["answer"]!="TIMEOUT"}
        check(len(answers)<=1,"Original SAT/UNSAT verdict contradiction")
        rows+=v
    check(len(rows)==15 and len(binsets)==1,
          "Benchmark is incomplete or not same pinned binary on all 5 runners")
    cases=[]
    for source in m["cases"]:
        g=source["gbd"]
        v={x["mode"]:x for x in rows if x["gbd"]==g}
        cases.append(dict(gbd=g,n=source["n"],m=source["m"],policies=v))
    summary={}
    for mode in MODES:
        subset=[x for x in rows if x["mode"]==mode]
        summary[mode]=dict(solved=sum(x["answer"]!="TIMEOUT" for x in subset),
            timeouts=sum(x["answer"]=="TIMEOUT" for x in subset),
            PAR2_s=round(sum(x["par2_s"] for x in subset),6),
            cert_verified_rows=sum(x["native"]["rows_certified"] for x in subset),
            native_reason_events=sum(x["native"]["reported_events"] for x in subset))
    data=dict(protocol=PROTO,summary=summary,cases=cases,rows=rows,
       source_manifest_sha=digest(root/"manifest.json"),
       limitations=m["constraints"])
    Path(a.output).write_text(json.dumps(data,indent=2)+"\n")
    md=["# R32u — active certified XOR implications inside native CDCL",
      "Five previously studied official 2026 SAT instances, 75s cap, one repeat.",
      "Identical native Kissat: passive original-CNF GF2 versus live XOR reason propagation.",
      "Every original-CNF derived short row rechecked through independent GF2 source provenance.",
      "One native Kissat process per trial, no parallel watchdog/solver portfolio.",
      "Timeout PAR2 penalty 150s. A timeout has no known completion time.",
      "",
      "| Mode | SAT/UNSAT solved of 5 | Timeout | Sum PAR2 seconds | Source-certified GF2 rows |",
      "|---|---:|---:|---:|---:|"]
    for mode in MODES:
        x=summary[mode]
        md.append(f'| {mode} | {x["solved"]}/5 | {x["timeouts"]} | {x["PAR2_s"]:.4f} | {x["cert_verified_rows"]} |')
    md+=["","## Paired formula-level results",
       "| Original GBD | Var | Clauses | Clean | Passive XOR | Active XOR | Active attached reason clauses (lower bound if timeout) | Verified GF2 rows |",
       "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for c in cases:
        v=c["policies"]
        def formatted(mode):
            x=v[mode]
            return f'{x["wall_s"]:.3f}s' if x["answer"]!="TIMEOUT" else "TIMEOUT ≥75s"
        active_data=v["active"]["native"]
        md.append(f'| {c["gbd"][:12]}… | {c["n"]} | {c["m"]} | {formatted("clean")} | {formatted("passive")} | {formatted("active")} | {active_data["attached_at_least"]} | {active_data["rows_certified"]} |')
    md+=["","## Interpretation",
       "An active assignment is not a new unconditional SAT root unit: it is",
       "conditioned on current native CDCL branch values, with a sound native",
       "CNF clause describing why this literal is forced by a GF2 row.",
       "The same full XOR RREF is computed in passive mode, so differences",
       "isolate native assignment/reason interventions and their costs.",
       "Any faster time in non-active sources is runner noise, not algorithm effect.",
       "Original 2026 CNFs were seen in R32s/R32t, so results are diagnostic, NOT blind.",
       "No claim of official SAT Competition superiority or P=NP."]
    Path(a.report).write_text("\n".join(md)+"\n")
    print("R32U_NATIVE_CDCL_REASON_AUDIT_PASS",
          json.dumps(summary,sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    actions=p.add_subparsers(dest="action",required=True)
    x=actions.add_parser("freeze")
    x.add_argument("--prior",required=True);x.add_argument("--out",required=True)
    x=actions.add_parser("measure")
    for key in ("inputs","clean","native","out"):
        x.add_argument("--"+key,required=True)
    x.add_argument("--shard",required=True,type=int)
    x=actions.add_parser("aggregate")
    for key in ("inputs","combined","output","report"):
        x.add_argument("--"+key,required=True)
    a=p.parse_args()
    if a.action=="freeze":freeze(a.prior,a.out)
    elif a.action=="measure":measure(a)
    else:aggregate(a)
if __name__=="__main__":main()
