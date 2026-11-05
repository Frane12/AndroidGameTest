#!/usr/bin/env python3
"""R32e: hidden-XOR-aware native GF2 selector blind synthetic holdout.
42 fresh baseline plus 28 newly coupled/stressed formulas, frozen SHA identities.
Ten repeats of baseline and three repeats of stress, six matched solver modes:
3024 attempts. Certification on original CNF with signed literal proofs.
Not an official or industrial benchmark, even when statistical wins are found.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,random,re,statistics,subprocess,time
from pathlib import Path
import r31_consistent_gf2_test as r31
import r32b_native_shadow_benchmark as b
import r32d_selective_benchmark as d

PROTO="DRNAS-R32E-FROZEN-HIDDEN-AWARE-SYNTHETIC-20261103-v1"
CAP=8.0
SHARDS=4
REPS=10
STRESS_REPS=3
MODES=("clean","native_off","R32B_native_shadow","R32C_active",
       "R32D_selective","R32E_selective")
d.CAP=CAP

def check(value,detail):
    if not value:raise RuntimeError("R32E_AUDIT_FAILURE "+str(detail))
def sha(value):
    return b.sha(value)
def freeze(dest):
    dest=Path(dest);dest.mkdir(parents=True,exist_ok=True)
    cases=[]
    for family in r31.FAMILIES:
        for idx in range(40,46):
            n,clauses,expected,truth=r31.make_case(family,idx)
            raw=r31.encode(n,clauses)
            name=f"r32e_base_{family}_{idx:02d}.cnf"
            (dest/name).write_bytes(raw)
            cases.append(dict(name=name,family=family,expected=expected,
                              sha256=sha(raw),cohort="new_baseline",repeats=REPS))
    for family in r31.FAMILIES:
        for idx in range(50,54):
            n,clauses,expected,truth=r31.make_case(family,idx)
            rng=random.Random(int(sha((PROTO+"/"+family+"/"+str(idx)).encode()),16))
            extra=200+40*(idx%2)
            extra_vars=list(range(n+1,n+extra+1))
            for v in extra_vars:truth[v]=rng.getrandbits(1)
            n+=extra
            for _ in range(int(extra*4.18)):
                clauses.append(r31.planted_clause(rng,extra_vars,truth))
            if family in ("consistent_visible","consistent_hidden",
                          "consistent_mixed","consistent_conditional"):
                copies=8+4*(idx%2)
                for j in range(210):
                    bridge=4*(j%copies+1)
                    pair=rng.sample(extra_vars,2)
                    cl=[-bridge]+[x if rng.getrandbits(1) else -x for x in pair]
                    if not any((lit>0)==bool(truth[abs(lit)]) for lit in cl):
                        cl[1]*=-1
                    clauses.append(cl)
            rng.shuffle(clauses)
            if expected=="SAT":
                check(all(any((lit>0)==bool(truth[abs(lit)]) for lit in cl)
                          for cl in clauses),"Invalid planted stress witness")
            raw=r31.encode(n,clauses)
            name=f"r32e_stress_{family}_{idx:02d}.cnf"
            (dest/name).write_bytes(raw)
            cases.append(dict(name=name,family=family,expected=expected,
                              sha256=sha(raw),cohort="new_coupled_stress",
                              repeats=STRESS_REPS))
    check(len(cases)==70 and len({c["sha256"] for c in cases})==70,
          "Require 70 unique originals")
    total=sum(c["repeats"]*len(MODES) for c in cases)
    check(total==3024,"Require 3024 trials")
    manifest=dict(protocol=PROTO,cases=cases,modes=MODES,cap=CAP,shards=SHARDS,
                  total_trials=total,base_repeats=REPS,stress_repeats=STRESS_REPS,
                  selector="hidden_resolvent_v1: 8<=extra<=12, 16<=eq<=96, (resolved==0 or resolved>=2*extra)",
                  warnings=[
                   "All 70 formulas are generated SYNTHETIC sources, not unseen real-world SAT competition inputs",
                   "The 28 coupled-stress sources are not proven difficult until run",
                   "Frozen selector was committed before any outcome was measured",
                   "Only complete original-source XOR constraints and BCP permit injection",
                   "SAT verified with full witness on original DIMACS; UNSAT checked with generator label (not LRAT)",
                   "8-second cap, timeout PAR-2=16 seconds",
                   "Small wall-time differences are subject to hardware/process noise",
                   "Neither world-leading SAT performance nor P vs NP progress is established"])
    (dest/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    (dest/"cnf.sha256").write_text("".join(f'{c["sha256"]}  {c["name"]}\n' for c in cases))
    print("R32E_SHA_LOCKED",len(cases),"cases",total,"trials",
          "manifest",sha(dest/"manifest.json"),flush=True)

def one_trial(case,source,mode,bins):
    if mode!="R32E_selective":
        return d.one_trial(case,source,mode,bins)
    env=os.environ.copy();env["R32B_MODE"]="r32e"
    begin=time.monotonic()
    try:
        run=subprocess.run([str(bins["native"]),str(source)],
               stdout=subprocess.PIPE,stderr=subprocess.PIPE,
               text=True,errors="replace",timeout=CAP,env=env)
        elapsed=time.monotonic()-begin
        check(run.returncode in (10,20),
              f"Invalid native exit {run.returncode}: {run.stderr[-300:]}")
        status="SAT" if run.returncode==10 else "UNSAT"
        check(status==case["expected"],"Truth label drift "+case["name"])
        verified=b.sat_check(source,run.stdout) if status=="SAT" else "generator_label_only"
        output=run.stdout
    except subprocess.TimeoutExpired as exc:
        elapsed=time.monotonic()-begin
        status="TIMEOUT";verified="censored"
        output=exc.stdout or b""
        if isinstance(output,bytes):output=output.decode(errors="replace")
    probes,final=b.parse_native(output)
    root=b.get_root(probes)
    proof=b.compare_root(root,source)
    check(proof["status"]=="independent_proof_match",
          "Original-CNF root verification failure "+case["name"])
    if status!="TIMEOUT":
        check(final is not None and final["status"]==(10 if status=="SAT" else 20),
              "Native final result discrepancy")
    matches=re.findall(
       r"^c R32C_ACTIVE signal=([A-Z_]+) injected=(\d+) certified=(\d+)$",
       output,re.MULTILINE)
    check(len(matches)==1,"Missing R32e native injection verdict")
    signal,ninject,ncert=matches[0]
    ninject=int(ninject);ncert=int(ncert)
    expected=int(root.get("extra",0)) if root["signal"]=="CONSISTENT_GAP" else 0
    admissible=0<expected<=12
    choices=re.findall(
       r"^c R32E_SELECT policy=hidden_resolvent_v1 equations=(\d+) resolved=(\d+) extra=(\d+) selected=(\d+)$",
       output,re.MULTILINE)
    check(len(choices)==1,"Missing frozen R32e source gate")
    eq,resolved,extra,selected=map(int,choices[0])
    choose=extra>=8 and 16<=eq<=96 and (resolved==0 or resolved>=2*extra)
    approval=expected if admissible and choose else 0
    check(eq==root["equations"] and resolved==root["resolved"]
          and extra==expected and selected==int(approval>0),
          "R32e gate not frozen to original source structure")
    check(ninject==approval and ncert>=ninject,
          "Native injected units deviate from independent proof count")
    lits=re.findall(
       r"^c R32C_INJECTED_LITS count=(\d+) lits=([0-9,-]+)$",
       output,re.MULTILINE)
    if approval:
        check(signal=="APPLIED" and len(lits)==1,"No positive certified injection evidence")
        n,body=lits[0]
        signed=[int(x) for x in body.split(",")]
        check(int(n)==len(signed)==approval
              and sorted(signed)==sorted(root["sample"]),
              "Unproven sign or value in native injected unit literal")
    else:
        check(signal!="APPLIED" and not lits,"Unsafe injection in abstained case")
    return dict(status=status,seconds=round(elapsed,6),
                par2=round(elapsed,6) if status!="TIMEOUT" else 2*CAP,
                verification=verified,root=root,proof=proof["status"],
                probes=len(probes),final=final,
                active=dict(signal=signal,injected=ninject,certified=ncert,
                            source_gate=bool(selected)))

def measure(a):
    frozen=Path(a.inputs)
    manifest=json.loads((frozen/"manifest.json").read_text())
    check(manifest["protocol"]==PROTO and len(manifest["cases"])==70,
          "Wrong frozen protocol")
    check(0<=a.shard<SHARDS,"Shard out of range")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    bins={k:Path(getattr(a,k)).resolve() for k in ("clean","native")}
    check(all(v.is_file() for v in bins.values()),"Missing pinned Kissat")
    out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    (out/"meta.json").write_text(json.dumps(dict(
         shard=a.shard,manifest=sha(frozen/"manifest.json"),
         binaries={k:sha(v) for k,v in bins.items()}),indent=2))
    rows=[]
    for case in manifest["cases"][a.shard::SHARDS]:
        original=frozen/case["name"]
        check(sha(original)==case["sha256"],"Original SHA drift")
        for rep in range(case["repeats"]):
            order=list(MODES)
            random.Random(int(sha((case["sha256"]+str(rep)+"R32E").encode()),16)).shuffle(order)
            for mode in order:
                result=one_trial(case,original,mode,bins)
                rows.append(dict(case=case["name"],family=case["family"],
                     cohort=case["cohort"],repeat=rep,mode=mode,**result))
                print("R32E_TRIAL",a.shard,case["name"],rep,mode,
                      result["status"],result["seconds"],
                      result["active"]["injected"] if result["active"] else "-",flush=True)
        (out/"rows.json").write_text(json.dumps(rows)+"\n")
    print("R32E_SHARD_PASS",a.shard,len(rows),flush=True)

def aggregate(a):
    root=Path(a.inputs)
    manifest=json.loads((root/"manifest.json").read_text())
    check(manifest["protocol"]==PROTO,"Wrong aggregation manifest")
    rows=[];fingerprints=set()
    for shard in range(SHARDS):
        folder=Path(a.combined)/f"r32e-shard-{shard}"/"results"
        meta=json.loads((folder/"meta.json").read_text())
        check(meta["shard"]==shard and meta["manifest"]==sha(root/"manifest.json"),
              "Frozen SHA mismatch across jobs")
        fingerprints.add(json.dumps(meta["binaries"],sort_keys=True))
        part=json.loads((folder/"rows.json").read_text())
        count=sum(c["repeats"]*len(MODES) for c in manifest["cases"][shard::SHARDS])
        check(len(part)==count,"Incomplete paired trials")
        rows.extend(part)
    check(len(fingerprints)==1 and len(rows)==manifest["total_trials"]==3024,
          "Not all trials used identical native binaries")
    bycase={c["name"]:[x for x in rows if x["case"]==c["name"]]
            for c in manifest["cases"]}
    for case in manifest["cases"]:
        arr=bycase[case["name"]]
        check(len(arr)==case["repeats"]*len(MODES),"Missing matched per-source repeats")
        for repeat in range(case["repeats"]):
            attempts={x["mode"]:x for x in arr if x["repeat"]==repeat}
            check(len(attempts)==len(MODES),"Duplicate or missing arm")
            off=attempts["native_off"];shadow=attempts["R32B_native_shadow"]
            if off["final"] and shadow["final"]:
                check(off["final"]==shadow["final"],
                      "Read-only shadow changed search policy")
            for mode in ("R32C_active","R32D_selective","R32E_selective"):
                active=attempts[mode]
                if (not active["active"]["injected"] and off["final"]
                    and active["final"]):
                    check(off["final"]==active["final"],
                          f"No-op policy drift with {mode}")
            check(len({x["status"] for x in attempts.values()}-{"TIMEOUT"})<=1,
                  "Different solver truth values under paired policies")
    grouped={"ALL":manifest["cases"]}
    grouped.update({cohort:[c for c in manifest["cases"] if c["cohort"]==cohort]
                    for cohort in ("new_baseline","new_coupled_stress")})
    grouped.update({family:[c for c in manifest["cases"] if c["family"]==family]
                    for family in r31.FAMILIES})
    summary={}
    for name,selection in grouped.items():
        source_ids={c["name"] for c in selection}
        out={}
        for mode in MODES:
            trials=[r for r in rows if r["mode"]==mode and r["case"] in source_ids]
            out[mode]=dict(PAR2_sum=round(sum(r["par2"] for r in trials),6),
                           solved_cases=sum(all(r["status"]!="TIMEOUT" for r in trials
                             if r["case"]==c["name"]) for c in selection),
                           timeouts=sum(r["status"]=="TIMEOUT" for r in trials),
                           count=len(trials))
            if mode in ("R32C_active","R32D_selective","R32E_selective"):
                out[mode]["active_cases"]=sum(any(
                  r["active"]["injected"] for r in trials if r["case"]==c["name"])
                  for c in selection)
        native=out["native_off"]["PAR2_sum"]
        for mode in ("R32C_active","R32D_selective","R32E_selective"):
            out[mode]["change_vs_off_pct"]=round(
              100*(out[mode]["PAR2_sum"]-native)/max(0.00001,native),4)
        summary[name]=out
        print("R32E_SUMMARY",name,json.dumps(out,sort_keys=True),flush=True)
    cases=[]
    for case in manifest["cases"]:
        entries=bycase[case["name"]]
        med={mode:round(statistics.median(r["par2"] for r in entries
             if r["mode"]==mode),6) for mode in MODES}
        chosen=next(r for r in entries if r["mode"]=="R32E_selective")
        conf={}
        for mode in ("native_off","R32C_active","R32D_selective","R32E_selective"):
            metrics=[r["final"]["conflicts"] for r in entries
                 if r["mode"]==mode and r["final"] is not None]
            conf[mode]=statistics.median(metrics) if metrics else None
        cases.append(dict(name=case["name"],family=case["family"],
             cohort=case["cohort"],signal=chosen["root"]["signal"],
             selected_lits=chosen["active"]["injected"],medians=med,
             median_conflicts=conf))
    def bootstrap(subset):
        rng=random.Random(3232026)
        samples=[]
        for _ in range(2500):
            drawn=[rng.choice(subset) for _ in subset]
            off=sum(c["medians"]["native_off"] for c in drawn)
            active=sum(c["medians"]["R32E_selective"] for c in drawn)
            samples.append(100*(active-off)/off)
        samples.sort()
        return [round(samples[62],3),round(samples[2437],3)]
    summary["ALL"]["bootstrap_case_median_95_pct"]=bootstrap(cases)
    summary["ALL"]["cases_faster_median"]=sum(
        c["medians"]["R32E_selective"]<c["medians"]["native_off"] for c in cases)
    summary["ALL"]["cases_total"]=len(cases)
    for cohort in ("new_baseline","new_coupled_stress"):
        subs=[c for c in cases if c["cohort"]==cohort]
        summary[cohort]["bootstrap_case_median_95_pct"]=bootstrap(subs)
    output=dict(protocol=PROTO,source_sha256=sha(root/"manifest.json"),
                summary=summary,per_case=cases,rows=rows,warnings=manifest["warnings"])
    Path(a.output).write_text(json.dumps(output,indent=2)+"\n")
    md=["# R32e certified hidden-XOR aware on new synthetic holdout",
        "70 SHA-distinct new sources: 42 baseline with 10 repeats, 28 coupled stress with 3 repeats.",
        "3024 matched trials; cap 8s; PAR2=16s.",
        "All candidate root literals are checked against independent original-CNF proof.",
        "This is NOT a benchmark of unseen official competition formulas.",
        f'95% case bootstrap on ALL paired-source median delta: {summary["ALL"]["bootstrap_case_median_95_pct"]}%.',
        f'R32e faster on {summary["ALL"]["cases_faster_median"]} of 70 individual source medians.',
        "",
        "| Category | Clean s | Native OFF s | R32b s | R32c s | R32d s | R32e s | R32e change | R32e active cases |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name,report in summary.items():
        md.append(f'| {name} | {report["clean"]["PAR2_sum"]:.4f} | {report["native_off"]["PAR2_sum"]:.4f} | {report["R32B_native_shadow"]["PAR2_sum"]:.4f} | {report["R32C_active"]["PAR2_sum"]:.4f} | {report["R32D_selective"]["PAR2_sum"]:.4f} | {report["R32E_selective"]["PAR2_sum"]:.4f} | {report["R32E_selective"]["change_vs_off_pct"]:+.3f}% | {report["R32E_selective"]["active_cases"]} |')
    md+=["","| Original CNF | Cohort | Root signal | Applied root literals | Native OFF median s | R32e median s | Native OFF median conflicts | R32e median conflicts |",
         "|---|---|---|---:|---:|---:|---:|---:|"]
    for c in cases:
        md.append(f'| {c["name"]} | {c["cohort"]} | {c["signal"]} | {c["selected_lits"]} | {c["medians"]["native_off"]:.6f} | {c["medians"]["R32E_selective"]:.6f} | {c["median_conflicts"]["native_off"]} | {c["median_conflicts"]["R32E_selective"]} |')
    Path(a.report).write_text("\n".join(md)+"\n")
    print("R32E_AUDIT_PASS",len(rows),"attempts",len(cases),"unique originals",flush=True)

def main():
    parser=argparse.ArgumentParser()
    subs=parser.add_subparsers(dest="command",required=True)
    p=subs.add_parser("freeze");p.add_argument("--dest",required=True)
    p=subs.add_parser("measure")
    for key in ("inputs","clean","native","outdir"):p.add_argument("--"+key,required=True)
    p.add_argument("--shard",type=int,required=True)
    p=subs.add_parser("aggregate")
    for key in ("inputs","combined","output","report"):p.add_argument("--"+key,required=True)
    args=parser.parse_args()
    if args.command=="freeze":freeze(args.dest)
    elif args.command=="measure":measure(args)
    else:aggregate(args)

if __name__=="__main__":main()
