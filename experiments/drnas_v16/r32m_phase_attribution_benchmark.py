#!/usr/bin/env python3
"""R32m: phase-resolved single-solver Kissat attribution for certified XOR units.

Measures native CPU microseconds *inside* early lucky, preprocessing, late
lucky, classify, CDCL. Separately measures subprocess wall and original-CNF
SAT correctness. No concurrent SAT solvers, watchdogs, or process portfolios.
Five previously examined diagnostic sources and 60 new synthetic sources.
"""
from __future__ import annotations
import argparse,collections,json,os,random,re,statistics,subprocess,time
from pathlib import Path
import r31_consistent_gf2_test as r31
import r32b_native_shadow_benchmark as b

PROTO="DRNAS-R32M-PHASE-ATTRIBUTION-20261103-v1"
SHARDS=4
CAP=8.0
MODES=("clean","native_off","full","first4","first8","last4")
PHASES=("lucky_early","preprocess","lucky_late","classify","cdcl")
DIAG=("r32e_stress_consistent_visible_51.cnf",
      "r32e_stress_consistent_mixed_53.cnf",
      "r32l_stress_consistent_visible_331.cnf",
      "r32l_stress_consistent_mixed_333.cnf",
      "r32l_fresh_consistent_hidden_303.cnf")

def check(ok,why):
    if not ok:raise RuntimeError("R32M_AUDIT_FAILURE "+str(why))
def sha(x):return b.sha(x)

def freeze(prior,dest):
    out=Path(dest);out.mkdir(parents=True,exist_ok=True)
    old=Path(prior)
    manifest=json.loads((old/"manifest.json").read_text())
    check(manifest["protocol"].startswith("DRNAS-R32L-"),
          "Previously audited R32l original source archive required")
    lookup={c["name"]:c for c in manifest["cases"]}
    cases=[]
    for name in DIAG:
        c=lookup[name];raw=(old/name).read_bytes()
        check(sha(raw)==c["sha256"],"Previously audited diagnostic CNF SHA changed")
        (out/name).write_bytes(raw)
        cases.append(dict(name=name,family=c["family"],expected=c["expected"],
                          cohort="prior_development",sha256=c["sha256"],repeats=10))
    for family in r31.FAMILIES:
        for idx in range(400,406):
            n,clauses,answer,_=r31.make_case(family,idx)
            raw=r31.encode(n,clauses)
            name=f"r32m_base_{family}_{idx:03d}.cnf"
            (out/name).write_bytes(raw)
            cases.append(dict(name=name,family=family,expected=answer,
                              cohort="new_base",sha256=sha(raw),repeats=5))
    for family in ("consistent_visible","consistent_hidden","consistent_mixed"):
        for idx in range(430,436):
            n,clauses,answer,truth=r31.make_case(family,idx)
            rng=random.Random(int(sha((PROTO+"/"+family+"/"+str(idx)).encode()),16))
            extra=200+40*(idx%2)
            bg=list(range(n+1,n+extra+1))
            for v in bg:truth[v]=rng.getrandbits(1)
            n+=extra
            for _ in range(int(extra*4.18)):
                clauses.append(r31.planted_clause(rng,bg,truth))
            copies=8+4*(idx%2)
            for j in range(210):
                bridge=4*(j%copies+1)
                pair=rng.sample(bg,2)
                cl=[-bridge]+[v if rng.getrandbits(1) else -v for v in pair]
                if not any((l>0)==bool(truth[abs(l)]) for l in cl):
                    cl[1]*=-1
                clauses.append(cl)
            rng.shuffle(clauses)
            check(answer=="SAT" and all(any(
                (l>0)==bool(truth[abs(l)]) for l in clause) for clause in clauses),
                "Planted stress SAT witness invalid")
            raw=r31.encode(n,clauses)
            name=f"r32m_stress_{family}_{idx:03d}.cnf"
            (out/name).write_bytes(raw)
            cases.append(dict(name=name,family=family,expected=answer,
                              cohort="new_stress",sha256=sha(raw),repeats=5))
    check(len(cases)==65 and len({c["sha256"] for c in cases})==65,
          "65 original SHA identities required")
    total=sum(c["repeats"]*len(MODES) for c in cases)
    check(total==2100,"Expected exactly 2100 attempts")
    m=dict(protocol=PROTO,cases=cases,shards=SHARDS,modes=MODES,total_trials=total,
           cap_seconds=CAP,phase_clock="process CPU clock in native search.c",
           caveats=[
             "Five previously examined sources are diagnostics, not blind holdouts",
             "All 60 new sources are synthetic generator holdouts, not external SAT",
             "Original Kissat versus native OFF provides process-level overhead control",
             "Native phase CPU excludes input reading, native parse, original GF2 derivation and output",
             "Wall clock includes process launch, parse, native GF2 computation, and search",
             "Phase timings instrumented for ALL native policies (including OFF)",
             "SAT witnessed against original DIMACS; UNSAT uses generator label, not LRAT",
             "Zero-phase no-CDCL resolution can be lucky or preprocessing, not deduced from conflicts",
             "Some millisecond differences can be affected by VM timer/CPU/cache noise",
             "No general SOTA or world record conclusion from synthetic seeds"])
    (out/"manifest.json").write_text(json.dumps(m,indent=2)+"\n")
    (out/"cnf.sha256").write_text("".join(
        f'{c["sha256"]}  {c["name"]}\n' for c in cases))
    print("R32M_FREEZE_PASS",len(cases),"unique CNFs",total,"serial trials",
          "manifest",sha(out/"manifest.json"),flush=True)

def phase_log(output,mode,status,final):
    lines=[line for line in output.splitlines()
           if line.startswith("c R32M_PHASE ")]
    if mode=="clean":
        check(not lines,"Unmodified clean Kissat emitted R32m native phase trace")
        return dict(terminal="not_instrumented",stages={})
    check(len(lines)==5,f"Expected five native phase events, got {len(lines)}")
    stages={}
    fields={"phase","ran","result","cpu_us","conflict_delta",
            "decision_delta","propagation_delta","learned_delta",
            "trail","unassigned"}
    for line in lines:
        parts=dict(re.findall(r"([a-z_]+)=([a-z_0-9.-]+)",line))
        check(set(parts)==fields,"Unrecognized phase telemetry "+line[:140])
        stage=parts.pop("phase")
        check(stage in PHASES and stage not in stages,"Repeated/unknown native phase")
        values={k:int(v) for k,v in parts.items()}
        check(values["ran"] in (0,1) and values["cpu_us"]>=0,
              "Invalid phase timing or skipped flag")
        if not values["ran"]:
            check(values["cpu_us"]==0 and all(values[key]==0 for key in (
                "conflict_delta","decision_delta","propagation_delta",
                "learned_delta")),"Skipped phase incremented counters")
        stages[stage]=values
    check(tuple(stages)==PHASES,"Native phases were reordered")
    if status=="TIMEOUT":terminal="censored"
    else:
        ended=[stage for stage in PHASES
               if stages[stage]["ran"] and stages[stage]["result"] in (10,20)]
        check(len(ended)<=1,"Multiple phases claimed terminal SAT result")
        terminal=ended[0] if ended else "initial_inconsistent"
        if ended:
            check(stages[terminal]["result"]==(10 if status=="SAT" else 20),
                  "Native phase return code disagrees with final SAT status")
        if final:
            for key,source in (("conflict_delta","conflicts"),
                               ("decision_delta","decisions"),
                               ("propagation_delta","propagations"),
                               ("learned_delta","learned")):
                check(stages["cdcl"][key]<=final[source],
                      "CDCL delta exceeds original native solver final counters")
    return dict(terminal=terminal,stages=stages,
                cdcl_entered=bool(stages["cdcl"]["ran"]))

def trial(case,source,mode,binaries):
    env=os.environ.copy()
    env["R32B_MODE"]="off" if mode in ("clean","native_off") else "r32k"
    if mode not in ("clean","native_off"):env["R32K_VARIANT"]=mode
    if mode!="clean":
        env["R32L_TRACE"]="1"
        env["R32M_PHASES"]="1"
    binary=binaries["clean"] if mode=="clean" else binaries["native"]
    begin=time.monotonic()
    try:
        result=subprocess.run([str(binary),str(source)],env=env,
          stdout=subprocess.PIPE,stderr=subprocess.PIPE,
          text=True,errors="replace",timeout=CAP)
        elapsed=time.monotonic()-begin
        check(result.returncode in (10,20),"Kissat exit error "+str(result.returncode))
        status="SAT" if result.returncode==10 else "UNSAT"
        check(status==case["expected"],"Original CNF truth mismatch")
        verification=b.sat_check(source,result.stdout) if status=="SAT" else "generator_label_only"
        output=result.stdout
    except subprocess.TimeoutExpired as exc:
        elapsed=time.monotonic()-begin
        status="TIMEOUT";verification="censored"
        output=exc.stdout or b""
        if isinstance(output,bytes):output=output.decode(errors="replace")
    probes,final=b.parse_native(output)
    proof=None;root=None;units=0
    if mode=="clean":
        check(not probes and final is None,"Clean Kissat instrumented")
    elif mode=="native_off":
        check(not probes,"Native OFF unexpectedly ran GF2 capture")
    else:
        root=b.get_root(probes)
        proof=b.compare_root(root,source)
        check(proof["status"]=="independent_proof_match",
              "Original CNF verified root unit proof mismatch")
        match=re.findall(
          r"^c R32K_ABLATION variant=([a-z0-9]+) available=(\d+) injected=(\d+) equations=(\d+) resolved=(\d+)$",
          output,re.MULTILINE)
        check(len(match)==1,"Missing native GF2 variant trace")
        name,available,count,eq,resolved=match[0]
        check(name==mode and int(eq)==root["equations"] and
              int(resolved)==root["resolved"],"GF2 native instrumented source mismatch")
        count=int(count);available=int(available)
        maximum=root["extra"] if root["signal"]=="CONSISTENT_GAP" else 0
        check(maximum==available,"Independent GF2 proof unit count mismatch")
        expected=maximum if 0<maximum<=12 else 0
        if mode in ("first4","last4"):expected=min(expected,4)
        if mode=="first8":expected=min(expected,8)
        check(count==expected,"Unexpected injected certified GF2 unit count")
        signed=re.findall(
          r"^c R32C_INJECTED_LITS count=(\d+) lits=([0-9,-]+)$",
          output,re.MULTILINE)
        if count:
            check(len(signed)==1 and int(signed[0][0])==count,
                  "Missing native injection signed literal record")
            literals=[int(v) for v in signed[0][1].split(",")]
            expected_lits=(root["sample"][-count:] if mode=="last4" else
                           root["sample"][:count])
            check(literals==expected_lits,
                  "Injected literal signs differ from independently proven sample")
        else:check(not signed,"Unsafe GF2 injection in abstained source")
        units=count
    if status!="TIMEOUT" and mode!="clean":
        check(final is not None and final["status"]==(10 if status=="SAT" else 20),
              "Missing native final solver verdict")
    phase=phase_log(output,mode,status,final)
    return dict(status=status,wall_s=round(elapsed,6),
                par2_s=round(elapsed,6) if status!="TIMEOUT" else 2*CAP,
                model_check=verification,root=root,proof=proof["status"] if proof else None,
                injected_units=units,final=final,phase=phase)

def measure(args):
    inputs=Path(args.inputs)
    m=json.loads((inputs/"manifest.json").read_text())
    check(m["protocol"]==PROTO and len(m["cases"])==65,"Wrong frozen R32m manifest")
    check(0<=args.shard<SHARDS,"Shard range")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    binaries={name:Path(getattr(args,name)).resolve() for name in ("clean","native")}
    check(all(p.is_file() for p in binaries.values()),"Pinned clean/native binary missing")
    out=Path(args.outdir);out.mkdir(parents=True,exist_ok=True)
    (out/"meta.json").write_text(json.dumps(dict(
         shard=args.shard,manifest_sha=sha(inputs/"manifest.json"),
         binary_sha={name:sha(path) for name,path in binaries.items()}),indent=2))
    rows=[]
    for case in m["cases"][args.shard::SHARDS]:
        source=inputs/case["name"]
        check(sha(source)==case["sha256"],"Source SHA drift")
        for repetition in range(case["repeats"]):
            order=list(MODES)
            random.Random(int(sha((case["sha256"]+str(repetition)+PROTO).encode()),16)).shuffle(order)
            for mode in order:
                record=trial(case,source,mode,binaries)
                rows.append(dict(case=case["name"],family=case["family"],
                                 cohort=case["cohort"],repeat=repetition,
                                 mode=mode,**record))
                print("R32M_TRIAL",args.shard,case["name"],repetition,mode,
                      record["status"],record["wall_s"],
                      record["phase"]["terminal"],flush=True)
        (out/"rows.json").write_text(json.dumps(rows)+"\n")
    print("R32M_SHARD_PASS",args.shard,len(rows),flush=True)

def aggregate(args):
    frozen=Path(args.inputs)
    m=json.loads((frozen/"manifest.json").read_text())
    check(m["protocol"]==PROTO,"Wrong source manifest")
    rows=[];sha_binaries=set()
    for shard in range(SHARDS):
        folder=Path(args.combined)/f"r32m-shard-{shard}"/"results"
        meta=json.loads((folder/"meta.json").read_text())
        check(meta["shard"]==shard and meta["manifest_sha"]==sha(frozen/"manifest.json"),
              "Different source SHAs across CI shards")
        sha_binaries.add(json.dumps(meta["binary_sha"],sort_keys=True))
        values=json.loads((folder/"rows.json").read_text())
        check(len(values)==sum(case["repeats"]*len(MODES)
              for case in m["cases"][shard::SHARDS]),"Missing paired trials")
        rows.extend(values)
    check(len(rows)==2100 and len(sha_binaries)==1,
          "Need 2100 source-paired attempts with same binary checksums")
    bycase={c["name"]:[x for x in rows if x["case"]==c["name"]]
            for c in m["cases"]}
    for case in m["cases"]:
        measurements=bycase[case["name"]]
        check(len(measurements)==case["repeats"]*len(MODES),"Missing per-case measurements")
        for rep in range(case["repeats"]):
            samples=[r for r in measurements if r["repeat"]==rep]
            check({r["mode"] for r in samples}==set(MODES),"Missing matched intervention")
            check(len({r["status"] for r in samples}-{"TIMEOUT"})<=1,
                  "Original SAT output label differs across root-unit variants")
    groups={"ALL":m["cases"],
            "prior_development":[c for c in m["cases"] if c["cohort"]=="prior_development"],
            "new_holdout":[c for c in m["cases"] if c["cohort"]!="prior_development"],
            "new_base":[c for c in m["cases"] if c["cohort"]=="new_base"],
            "new_stress":[c for c in m["cases"] if c["cohort"]=="new_stress"]}
    groups.update({family:[c for c in m["cases"] if c["family"]==family]
                    for family in r31.FAMILIES})
    summary={}
    for label,cohort in groups.items():
        selected={c["name"] for c in cohort}
        info={}
        for mode in MODES:
            subset=[r for r in rows if r["case"] in selected and r["mode"]==mode]
            item=dict(wall_PAR2_s=round(sum(x["par2_s"] for x in subset),6),
                      completed=sum(x["status"]!="TIMEOUT" for x in subset),
                      timeouts=sum(x["status"]=="TIMEOUT" for x in subset))
            if mode!="clean":
                item["phase_CPU_us"]={p:sum(x["phase"]["stages"][p]["cpu_us"]
                                        for x in subset) for p in PHASES}
                item["terminal_phase"]=dict(collections.Counter(
                     x["phase"]["terminal"] for x in subset))
                item["CDCL_conflicts"]=sum(x["final"]["conflicts"] for x in subset
                                            if x["final"] is not None)
            info[mode]=item
        native=info["native_off"]["wall_PAR2_s"]
        for mode in MODES[2:]:
            info[mode]["wall_delta_vs_native_off_pct"]=round(
               100*(info[mode]["wall_PAR2_s"]-native)/native,4)
        summary[label]=info
        print("R32M_SUMMARY",label,json.dumps(info,sort_keys=True),flush=True)
    percase=[]
    for c in m["cases"]:
        measurements=bycase[c["name"]]
        policies={}
        for mode in MODES:
            subset=[x for x in measurements if x["mode"]==mode]
            outcome=dict(wall_median_s=statistics.median(x["par2_s"] for x in subset))
            if mode!="clean":
                terminals={x["phase"]["terminal"] for x in subset}
                check(len(terminals)==1,"Nondeterministic terminal phase in frozen policy")
                outcome["terminal"]=next(iter(terminals))
                outcome["median_phase_CPU_us"]={
                    p:statistics.median(x["phase"]["stages"][p]["cpu_us"]
                        for x in subset) for p in PHASES}
                outcome["conflicts"]=statistics.median(
                    x["final"]["conflicts"] for x in subset if x["final"])
            policies[mode]=outcome
        percase.append(dict(name=c["name"],cohort=c["cohort"],family=c["family"],
                            policies=policies))
    data=dict(protocol=PROTO,source_manifest_sha=sha(frozen/"manifest.json"),
              summary=summary,per_case=percase,rows=rows,caveats=m["caveats"])
    Path(args.output).write_text(json.dumps(data,indent=2)+"\n")
    md=["# R32m: native phase attribution of certified XOR interventions",
        "5 known development formulas + 60 fresh synthetic sources.",
        "2100 independent SERIAL single-solver trial attempts (not concurrent).",
        "Native phase clock is *process CPU* inside Kissat search; excludes input parse and root GF2.",
        "Results are synthetic and cannot establish a general SAT speed ranking.",
        "",
        "| Phase (fresh 60) | Native OFF CPU ms | Full certified GF2 CPU ms | Difference ms |",
        "|---|---:|---:|---:|"]
    off=summary["new_holdout"]["native_off"];full=summary["new_holdout"]["full"]
    for phase in PHASES:
        a=off["phase_CPU_us"][phase]/1000
        z=full["phase_CPU_us"][phase]/1000
        md.append(f"| {phase} | {a:.3f} | {z:.3f} | {z-a:+.3f} |")
    md+=["","## Wall-time summary",
        "| Cohort | Native OFF wall s | Full GF2 wall s | Full GF2 change |",
        "|---|---:|---:|---:|"]
    for group,v in summary.items():
        md.append(f'| {group} | {v["native_off"]["wall_PAR2_s"]:.6f} | {v["full"]["wall_PAR2_s"]:.6f} | {v["full"]["wall_delta_vs_native_off_pct"]:+.3f}% |')
    md+=["","## Diagnostic exit phases: observed reasons for large wall differences",
          "| Original formula | Mode | Exit phase | Early lucky CPU ms | Preprocess CPU ms | Late lucky CPU ms | CDCL CPU ms |",
          "|---|---|---|---:|---:|---:|---:|"]
    for c in percase:
        if c["cohort"]!="prior_development":continue
        for mode in ("native_off","full","first4","first8","last4"):
            k=c["policies"][mode];t=k["median_phase_CPU_us"]
            md.append(f'| {c["name"]} | {mode} | {k["terminal"]} | {t["lucky_early"]/1000:.3f} | {t["preprocess"]/1000:.3f} | {t["lucky_late"]/1000:.3f} | {t["cdcl"]/1000:.3f} |')
    md+=["","## Fresh source terminal phase counts (300 trials per mode)"]
    for mode in ("native_off","full","first4","first8","last4"):
        md.append(f'- **{mode}**: {summary["new_holdout"][mode]["terminal_phase"]}')
    Path(args.report).write_text("\n".join(md)+"\n")
    print("R32M_AUDIT_PASS",len(rows),"serial attempts",len(percase),"source CNFs",flush=True)

def main():
    ap=argparse.ArgumentParser()
    subs=ap.add_subparsers(dest="command",required=True)
    p=subs.add_parser("freeze");p.add_argument("--prior",required=True);p.add_argument("--dest",required=True)
    p=subs.add_parser("measure")
    for name in ("inputs","clean","native","outdir"):p.add_argument("--"+name,required=True)
    p.add_argument("--shard",type=int,required=True)
    p=subs.add_parser("aggregate")
    for name in ("inputs","combined","output","report"):p.add_argument("--"+name,required=True)
    a=ap.parse_args()
    if a.command=="freeze":freeze(a.prior,a.dest)
    elif a.command=="measure":measure(a)
    else:aggregate(a)

if __name__=="__main__":main()
