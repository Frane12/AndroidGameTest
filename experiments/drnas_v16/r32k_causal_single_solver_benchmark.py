#!/usr/bin/env python3
"""R32k causal GF2 root-unit ablation within ONE pinned Kissat execution.

Experimental unit sets: full, first4, last4, first8. These are subsets of
the SAME independently certified original-CNF GF(2) root units. Same pinned
Kissat binary and CDCL policy; no parallel solvers, watchdog, in-process
restart intervention, communication, pretrained rule or oracle selection.
Two R32e known diagnostic cases + 60 SHA-distinct newly seeded synthetics.
Measure total wall time, conflicts, decisions, propagations and learned.
Ablation tests mechanistic hypothesis; statistical validation on NEW sources
cannot automatically establish performance on official SAT instances.
"""
from __future__ import annotations
import argparse,collections,hashlib,json,os,random,re,statistics,subprocess,time
from pathlib import Path
import r31_consistent_gf2_test as r31
import r32b_native_shadow_benchmark as b

PROTO="DRNAS-R32K-SINGLE-SOLVER-CAUSE-20261103-v1"
PIN="8af8e56f174b778aef3aa45af9f739b2a5f492c2"
VARIANTS=("clean","native_off","full","first4","first8","last4")
SHARDS=4
CAP=8.0
BASE_INDICES=range(240,246)
STRESS_INDICES=range(260,266)
NEW_REPS=5
DEV_REPS=10
KNOWN=("r32e_stress_consistent_visible_51.cnf",
       "r32e_stress_consistent_mixed_53.cnf")

def check(ok,reason):
    if not ok:raise RuntimeError("R32K_PROOF_AUDIT_FAILURE "+str(reason))
def sha(data):return b.sha(data)

def freeze(prior,dest):
    out=Path(dest);out.mkdir(parents=True,exist_ok=True)
    previous=Path(prior)
    old=json.loads((previous/"manifest.json").read_text())
    check(old["protocol"].startswith("DRNAS-R32E-"),"Wrong development source")
    index={c["name"]:c for c in old["cases"]}
    cases=[]
    for name in KNOWN:
        case=index[name]
        raw=(previous/name).read_bytes()
        check(sha(raw)==case["sha256"],"Known diagnosis SHA changed")
        (out/name).write_bytes(raw)
        cases.append(dict(name=name,family=case["family"],expected=case["expected"],
                          sha256=case["sha256"],cohort="prior_development",
                          repeats=DEV_REPS))
    for family in r31.FAMILIES:
        for idx in BASE_INDICES:
            n,clauses,expected,truth=r31.make_case(family,idx)
            raw=r31.encode(n,clauses)
            name=f"r32k_fresh_{family}_{idx:03d}.cnf"
            (out/name).write_bytes(raw)
            cases.append(dict(name=name,family=family,expected=expected,
                              sha256=sha(raw),cohort="new_base",
                              repeats=NEW_REPS))
    for family in ("consistent_visible","consistent_hidden","consistent_mixed"):
        for idx in STRESS_INDICES:
            n,clauses,expected,truth=r31.make_case(family,idx)
            rng=random.Random(int(sha((PROTO+"/"+family+"/"+str(idx)).encode()),16))
            extra=200+40*(idx%2)
            vars_extra=list(range(n+1,n+extra+1))
            for v in vars_extra:truth[v]=rng.getrandbits(1)
            n+=extra
            for _ in range(int(extra*4.18)):
                clauses.append(r31.planted_clause(rng,vars_extra,truth))
            copies=8+4*(idx%2)
            for j in range(210):
                bridge=4*(j%copies+1)
                pair=rng.sample(vars_extra,2)
                clause=[-bridge]+[v if rng.getrandbits(1) else -v for v in pair]
                if not any((x>0)==bool(truth[abs(x)]) for x in clause):
                    clause[1]*=-1
                clauses.append(clause)
            rng.shuffle(clauses)
            check(expected=="SAT" and all(
                 any((x>0)==bool(truth[abs(x)]) for x in clause)
                 for clause in clauses),"Stress construction broke SAT model")
            raw=r31.encode(n,clauses)
            name=f"r32k_stress_{family}_{idx:03d}.cnf"
            (out/name).write_bytes(raw)
            cases.append(dict(name=name,family=family,expected=expected,
                              sha256=sha(raw),cohort="new_stress",
                              repeats=NEW_REPS))
    total=sum(c["repeats"]*len(VARIANTS) for c in cases)
    check(len(cases)==62 and len({c["sha256"] for c in cases})==62
          and total==1920,"Expected 62 SHA-distinct source formulas and 1920 attempts")
    manifest=dict(protocol=PROTO,pin=PIN,cases=cases,modes=VARIANTS,
        cap=CAP,shards=SHARDS,total_trials=total,
        dev_names=list(KNOWN),fresh_base_seeds=list(BASE_INDICES),
        fresh_stress_seeds=list(STRESS_INDICES),
        warnings=[
          "Two previously seen R32e formulas are development diagnostics, NOT blind.",
          "Sixty new CNFs are synthetically generated holdouts, NOT official SAT Competition.",
          "Labels visible vs mixed come from generator family seed; same template can yield opposite CDCL effects.",
          "One native Kissat runs per attempt, no concurrent worker, watchdog or communication.",
          "Same original CNF and original-source GF2 proof across all intervention variants.",
          "Unit-set variants are fixed beforehand; no fit or tuning on new-case results.",
          "SAT witness checked against original source; UNSAT by generator expected label, not LRAT.",
          "Tiny single-process wall time differences can reflect process startup and runner noise.",
          "8s timeout, PAR2=16s, no implication for general NP/P=NP, world rankings"])
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    (out/"cnf.sha256").write_text("".join(
      f'{c["sha256"]}  {c["name"]}\n' for c in cases))
    print("R32K_FROZEN",len(cases),"sources",total,
          "single-solver attempts",sha(out/"manifest.json"),flush=True)

def one(case,path,mode,bins):
    binary=bins["clean"] if mode=="clean" else bins["native"]
    env=os.environ.copy()
    env["R32B_MODE"]="off" if mode in ("clean","native_off") else "r32k"
    if mode not in ("clean","native_off"):env["R32K_VARIANT"]=mode
    started=time.monotonic()
    try:
        p=subprocess.run([str(binary),str(path)],
            env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            text=True,errors="replace",timeout=CAP)
        elapsed=time.monotonic()-started
        check(p.returncode in (10,20),
              f"Native solver exit code invalid: {p.returncode} stderr={p.stderr[-250:]}")
        status="SAT" if p.returncode==10 else "UNSAT"
        check(status==case["expected"],"Wrong original formula status")
        validation=b.sat_check(path,p.stdout) if status=="SAT" else "generator_label_only"
        text=p.stdout
    except subprocess.TimeoutExpired as exc:
        elapsed=time.monotonic()-started
        status="TIMEOUT";validation="censored"
        text=exc.stdout or b""
        if isinstance(text,bytes):text=text.decode(errors="replace")
    probes,final=b.parse_native(text)
    root=None;ablation=None;proof=None
    if mode=="clean":check(not probes and final is None,"Clean Kissat instrumented")
    elif mode=="native_off":check(not probes,"Native OFF ran probes")
    else:
        root=b.get_root(probes)
        proof=b.compare_root(root,path)
        check(proof["status"]=="independent_proof_match",
              "Certified GF2 proof mismatch for injected source")
        match=re.findall(
          r"^c R32K_ABLATION variant=([a-z0-9]+) available=(\d+) injected=(\d+) equations=(\d+) resolved=(\d+)$",
          text,re.MULTILINE)
        check(len(match)==1,"Missing causal ablation configuration log")
        name,available,count,eq,resolved=match[0]
        available=int(available);count=int(count)
        check(name==mode,"Wrong configured unit subset")
        correct=int(root["extra"]) if root["signal"]=="CONSISTENT_GAP" else 0
        check(available==correct and int(eq)==root["equations"]
              and int(resolved)==root["resolved"],"Source feature telemetry mismatch")
        intended=correct if correct<=12 else 0
        if not (root["signal"]=="CONSISTENT_GAP" and 0<correct<=12):intended=0
        elif mode in ("first4","last4"):intended=min(4,correct)
        elif mode=="first8":intended=min(8,correct)
        check(intended==count,"Unexpected root intervention amount")
        claims=re.findall(
          r"^c R32C_ACTIVE signal=([A-Z_]+) injected=(\d+) certified=(\d+)$",
          text,re.MULTILINE)
        check(len(claims)==1,"No native intervention claim")
        signal,native_count,certified=claims[0]
        check(int(native_count)==intended
              and int(certified)>=intended,"Native certificate count mismatch")
        literals=re.findall(
          r"^c R32C_INJECTED_LITS count=(\d+) lits=([0-9,-]+)$",
          text,re.MULTILINE)
        if intended:
            check(len(literals)==1 and signal=="APPLIED",
                  "Missing injected signed literals")
            n,shown=literals[0]
            actual=[int(x) for x in shown.split(",")]
            basis=root["sample"]
            expected=(basis[-intended:] if mode=="last4" else basis[:intended])
            check(int(n)==intended and actual==expected,
                  "Injected subset not identical to individually certified units")
        else:
            check(not literals and signal!="APPLIED",
                  "Abstention was violated")
        ablation=dict(variant=name,available=available,injected=count,
                      root_signal=root["signal"],equations=int(eq),
                      resolved=int(resolved))
    if status!="TIMEOUT" and mode!="clean":
        check(final is not None and final["status"]==(10 if status=="SAT" else 20),
              "Missing original native final telemetry")
    return dict(status=status,seconds=round(elapsed,6),
                par2=round(elapsed,6) if status!="TIMEOUT" else CAP*2,
                verification=validation,root=root,ablation=ablation,
                proof=proof["status"] if proof else None,final=final)

def measure(a):
    sources=Path(a.inputs);manifest=json.loads((sources/"manifest.json").read_text())
    check(manifest["protocol"]==PROTO and len(manifest["cases"])==62,
          "Invalid protocol or case count")
    check(0<=a.shard<SHARDS,"Shard out of range")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    binaries={k:Path(getattr(a,k)).resolve() for k in ("clean","native")}
    check(all(x.is_file() for x in binaries.values()),"Pinned binaries absent")
    dest=Path(a.outdir);dest.mkdir(parents=True,exist_ok=True)
    (dest/"meta.json").write_text(json.dumps(dict(shard=a.shard,
        source_sha=sha(sources/"manifest.json"),
        binaries={k:sha(v) for k,v in binaries.items()}),indent=2))
    rows=[]
    for case in manifest["cases"][a.shard::SHARDS]:
        original=sources/case["name"]
        check(sha(original)==case["sha256"],"Original SHA changed")
        for repeat in range(case["repeats"]):
            order=list(VARIANTS)
            random.Random(int(sha((case["sha256"]+str(repeat)+PROTO).encode()),16)).shuffle(order)
            for mode in order:
                result=one(case,original,mode,binaries)
                rows.append(dict(case=case["name"],family=case["family"],
                                 cohort=case["cohort"],repeat=repeat,mode=mode,**result))
                print("R32K_TRIAL",a.shard,case["name"],repeat,mode,
                    result["status"],result["seconds"],
                    result["final"]["conflicts"] if result["final"] else "-",
                    "units",result["ablation"]["injected"] if result["ablation"] else "-",flush=True)
        (dest/"rows.json").write_text(json.dumps(rows)+"\n")
    print("R32K_SHARD_PASS",a.shard,len(rows),flush=True)

def aggregate(a):
    frozen=Path(a.inputs);m=json.loads((frozen/"manifest.json").read_text())
    check(m["protocol"]==PROTO,"Invalid manifest")
    rows=[];fingerprints=set()
    for shard in range(SHARDS):
        folder=Path(a.combined)/f"r32k-shard-{shard}"/"results"
        meta=json.loads((folder/"meta.json").read_text())
        check(meta["shard"]==shard and
              meta["source_sha"]==sha(frozen/"manifest.json"),
              "Case SHA drift across experiments")
        fingerprints.add(json.dumps(meta["binaries"],sort_keys=True))
        chunk=json.loads((folder/"rows.json").read_text())
        check(len(chunk)==sum(c["repeats"]*len(VARIANTS)
                   for c in m["cases"][shard::SHARDS]),
              "Shard does not have every paired mode")
        rows.extend(chunk)
    check(len(rows)==1920 and len(fingerprints)==1,
          "Need all 1920 attempts on same pinned binary pair")
    bycase={c["name"]:[r for r in rows if r["case"]==c["name"]]
            for c in m["cases"]}
    for case in m["cases"]:
        measurements=bycase[case["name"]]
        check(len(measurements)==case["repeats"]*len(VARIANTS),"Unpaired attempts")
        for rep in range(case["repeats"]):
            selected=[r for r in measurements if r["repeat"]==rep]
            check({r["mode"] for r in selected}==set(VARIANTS),
                  "Missing paired arm")
            check(len({r["status"] for r in selected}-{"TIMEOUT"})<=1,
                  "Different truth values from certified root-unit subsets")
    groups={"ALL":m["cases"],
            "prior_development":[c for c in m["cases"] if c["cohort"]=="prior_development"],
            "new_holdout":[c for c in m["cases"] if c["cohort"]!="prior_development"],
            "new_base":[c for c in m["cases"] if c["cohort"]=="new_base"],
            "new_stress":[c for c in m["cases"] if c["cohort"]=="new_stress"]}
    groups.update({f:[c for c in m["cases"] if c["family"]==f] for f in r31.FAMILIES})
    summaries={}
    for name,cc in groups.items():
        members={c["name"] for c in cc};data={}
        for mode in VARIANTS:
            r=[x for x in rows if x["mode"]==mode and x["case"] in members]
            data[mode]=dict(PAR2_sum=round(sum(x["par2"] for x in r),6),
                           solved=sum(x["status"]!="TIMEOUT" for x in r),
                           timeouts=sum(x["status"]=="TIMEOUT" for x in r),
                           conflicts=sum(x["final"]["conflicts"] for x in r if x["final"]),
                           decisions=sum(x["final"]["decisions"] for x in r if x["final"]))
        base=data["native_off"]["PAR2_sum"]
        for mode in VARIANTS[2:]:
            data[mode]["delta_vs_off_pct"]=round(
                100*(data[mode]["PAR2_sum"]-base)/max(1e-9,base),4)
        summaries[name]=data
        print("R32K_SUMMARY",name,json.dumps(data,sort_keys=True),flush=True)
    cases=[]
    for case in m["cases"]:
        r=bycase[case["name"]]
        med={key:{metric:statistics.median(
            x["final"][metric] for x in r if x["mode"]==key and x["final"])
            if key!="clean" and any(x["mode"]==key and x["final"] for x in r) else None
            for metric in ("conflicts","decisions","propagations","learned")}
            for key in VARIANTS}
        med_time={key:statistics.median(x["par2"] for x in r if x["mode"]==key)
                  for key in VARIANTS}
        example=next(x["ablation"] for x in r if x["mode"]=="full")
        cases.append(dict(name=case["name"],family=case["family"],
           cohort=case["cohort"],source_sha=case["sha256"],
           proven_units=example["available"],root_signal=example["root_signal"],
           median_time=med_time,median_cdcl=med))
    rng=random.Random(32026)
    held=[c for c in cases if c["cohort"]!="prior_development"]
    intervals={}
    for mode in VARIANTS[2:]:
        drawn=[]
        for _ in range(2200):
            sample=[rng.choice(held) for _ in held]
            off=sum(x["median_time"]["native_off"] for x in sample)
            trial=sum(x["median_time"][mode] for x in sample)
            drawn.append(100*(trial-off)/off)
        drawn.sort()
        intervals[mode]=[round(drawn[54],3),round(drawn[2144],3)]
    changes={}
    for mode in VARIANTS[2:]:
        diffs=[c["median_cdcl"][mode]["conflicts"]-
               c["median_cdcl"]["native_off"]["conflicts"] for c in held]
        changes[mode]=dict(fewer=sum(x<0 for x in diffs),
                           equal=sum(x==0 for x in diffs),
                           more=sum(x>0 for x in diffs),
                           bootstrap_case_time_ci95_pct=intervals[mode])
    out=dict(protocol=PROTO,summary=summaries,conflict_directions=changes,
             by_case=cases,rows=rows,source_sha=sha(frozen/"manifest.json"),
             caveats=m["warnings"])
    Path(a.output).write_text(json.dumps(out,indent=2)+"\n")
    report=["# DRNAS R32k: certified XOR root-unit causal ablation inside one Kissat",
       "62 SHA-original CNFs: two known R32e diagnostics and 60 new synthetic holdouts.",
       "6 modes, 1920 paired attempts, cap 8s, no concurrent SAT processes.",
       "Unit variants full, first4, first8, last4 retain original CNF certification.",
       "Root contradictions and incomplete patterns never inject units.",
       "Benchmark distinguishes CDCL conflict counts from wall-clock noise.",
       "No unseen external industrial or SAT Competition cases tested here.",
       "","| Cohort | Native OFF s | Full GF2 s | First4 s | First8 s | Last4 s |",
       "|---|---:|---:|---:|---:|---:|"]
    for label,item in summaries.items():
        report.append(f'| {label} | {item["native_off"]["PAR2_sum"]:.5f} | {item["full"]["PAR2_sum"]:.5f} | {item["first4"]["PAR2_sum"]:.5f} | {item["first8"]["PAR2_sum"]:.5f} | {item["last4"]["PAR2_sum"]:.5f} |')
    report+=["","## Unseen-synthetic holdout: changes in conflict counts"]
    for mode,item in changes.items():
        report.append(f'- **{mode}**: fewer/equal/more conflicts = {item["fewer"]}/{item["equal"]}/{item["more"]}; paired-case time CI95 = {item["bootstrap_case_time_ci95_pct"]}%.')
    report+=["","## Per-formula causal ablation (medians)",
             "| Original | Cohort | Root units | OFF conflicts | Full conflicts | First4 conflicts | First8 conflicts | Last4 conflicts | OFF s | Full s |",
             "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for c in cases:
        q=c["median_cdcl"];t=c["median_time"]
        report.append(f'| {c["name"]} | {c["cohort"]} | {c["proven_units"]} | {q["native_off"]["conflicts"]} | {q["full"]["conflicts"]} | {q["first4"]["conflicts"]} | {q["first8"]["conflicts"]} | {q["last4"]["conflicts"]} | {t["native_off"]:.6f} | {t["full"]:.6f} |')
    Path(a.report).write_text("\n".join(report)+"\n")
    print("R32K_AUDIT_PASS",len(rows),"single-solver attempts",len(cases),"sources",flush=True)

def main():
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest="command",required=True)
    p=sub.add_parser("freeze");p.add_argument("--prior",required=True);p.add_argument("--dest",required=True)
    p=sub.add_parser("measure")
    for key in ("inputs","clean","native","outdir"):p.add_argument("--"+key,required=True)
    p.add_argument("--shard",type=int,required=True)
    p=sub.add_parser("aggregate")
    for key in ("inputs","combined","output","report"):p.add_argument("--"+key,required=True)
    a=parser.parse_args()
    if a.command=="freeze":freeze(a.prior,a.dest)
    elif a.command=="measure":measure(a)
    else:aggregate(a)

if __name__=="__main__":main()
