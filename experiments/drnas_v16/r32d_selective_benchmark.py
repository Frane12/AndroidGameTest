#!/usr/bin/env python3
"""DRNAS R32d frozen selective GF2 root-unit research test.
42 unseen SHA-distinct synthetic seeds, 20 repeats, five matched policies;
4200 trials, soundness checks for each actually injected signed literal.
The selector was frozen before the holdout. No official SAT instances here.
"""
from __future__ import annotations
import argparse,collections,functools,json,os,random,re,statistics,subprocess,time
from pathlib import Path
import r31_consistent_gf2_test as r31
import r32b_native_shadow_benchmark as b
import r32c_active_unit_benchmark as c

PROTO="DRNAS-R32D-FROZEN-GF2-SELECTOR-HOLDOUT-20261103-v1"
REPS=20
SHARDS=4
CAP=4.0
MODES=("clean","native_off","R32B_native_shadow","R32C_active","R32D_selective")
INDICES=range(30,36)
c.PROTO=PROTO
c.REPS=REPS
c.SHARDS=SHARDS
c.CAP=CAP
c.MODES=MODES
r31.structure=functools.lru_cache(maxsize=128)(r31.structure)
b.r30.parse_dimacs=functools.lru_cache(maxsize=128)(b.r30.parse_dimacs)

def check(valid,msg):
    if not valid:raise RuntimeError("R32D_AUDIT_FAILURE "+str(msg))
def sha(x):return b.sha(x)

def freeze(dest):
    out=Path(dest);out.mkdir(parents=True,exist_ok=True)
    cases=[]
    for family in r31.FAMILIES:
        for idx in INDICES:
            n,clauses,expected,truth=r31.make_case(family,idx)
            raw=r31.encode(n,clauses)
            name=f"r32d_holdout_{family}_{idx:02d}.cnf"
            (out/name).write_bytes(raw)
            cases.append(dict(name=name,family=family,expected=expected,
                              sha256=sha(raw),cohort="fresh_synthetic_holdout"))
    check(len(cases)==42 and len({x["sha256"] for x in cases})==42,
          "Expected 42 distinct SHA-frozen cases")
    manifest=dict(protocol=PROTO,cases=cases,modes=MODES,repeats=REPS,
        cap_seconds=CAP,shards=SHARDS,holdout_seed_indices=list(INDICES),
        selector="direct_gap_v1: resolved==0 and equations>=16 and extra>=8; 1<=extra<=12; consistent",
        warnings=["Synthetic seed holdout, not external competition benchmark",
                  "Frozen selector chosen on earlier development data",
                  "SAT model reverified against original DIMACS",
                  "UNSAT correctness relies on generator label; no DRAT/LRAT proof",
                  "Many solve times are milliseconds, so paired noise is material",
                  "A 4-second timeout is censored; PAR2=8 seconds",
                  "Benchmark cannot establish a universal SAT improvement"])
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    (out/"cnf.sha256").write_text("".join(
        f'{x["sha256"]}  {x["name"]}\n' for x in cases))
    print("R32D_SHA_FROZEN",len(cases),"holdout SHA",sha(out/"manifest.json"),flush=True)

def one_trial(case,path,mode,bins):
    env=os.environ.copy()
    env["R32B_MODE"]={"clean":"off","native_off":"off",
        "R32B_native_shadow":"shadow","R32C_active":"active",
        "R32D_selective":"selective"}[mode]
    binary=bins["clean"] if mode=="clean" else bins["native"]
    started=time.monotonic()
    try:
        p=subprocess.run([str(binary),str(path)],env=env,
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            text=True,errors="replace",timeout=CAP)
        elapsed=time.monotonic()-started
        check(p.returncode in (10,20),f"Invalid Kissat exit {p.returncode} {p.stderr[-250:]}")
        status="SAT" if p.returncode==10 else "UNSAT"
        check(status==case["expected"],"Truth label drift "+case["name"]+" mode "+mode)
        verified=b.sat_check(path,p.stdout) if status=="SAT" else "generator_label_only"
        output=p.stdout
    except subprocess.TimeoutExpired as exc:
        elapsed=time.monotonic()-started
        status="TIMEOUT";verified="censored"
        output=exc.stdout or b""
        if isinstance(output,bytes):output=output.decode(errors="replace")
    probes,final=b.parse_native(output)
    if mode=="clean":check(not probes and final is None,"Clean solver instrumented")
    if mode=="native_off":check(not probes,"Native OFF invoked probe")
    if status!="TIMEOUT" and mode!="clean":
        check(final is not None and final["status"]==(10 if status=="SAT" else 20),
              "Missing/incorrect native final counters")
    root=None;proof=None;active=None
    if mode in ("R32B_native_shadow","R32C_active","R32D_selective"):
        root=b.get_root(probes)
        proof=b.compare_root(root,path)
        check(proof["status"]=="independent_proof_match",
              "Independent original-CNF proof failed "+case["name"])
    if mode in ("R32C_active","R32D_selective"):
        hits=re.findall(
            r"^c R32C_ACTIVE signal=([A-Z_]+) injected=(\d+) certified=(\d+)$",
            output,re.MULTILINE)
        check(len(hits)==1,"Missing one active verdict")
        signal,count,cert=hits[0]
        count=int(count);cert=int(cert)
        expected=int(root.get("extra",0)) if root["signal"]=="CONSISTENT_GAP" else 0
        admissible=(0<expected<=12)
        selected=True
        if mode=="R32D_selective":
            policy=re.findall(
              r"^c R32D_SELECT policy=direct_gap_v1 equations=(\d+) resolved=(\d+) extra=(\d+) selected=(\d+)$",
              output,re.MULTILINE)
            check(len(policy)==1,"Missing frozen selective gate telemetry")
            eq,derived,extra,applied=map(int,policy[0])
            selected=(derived==0 and eq>=16 and extra>=8)
            check(eq==root["equations"] and derived==root["resolved"]
                  and extra==expected and applied==int(admissible and selected),
                  "R32d selector differs from frozen structural rule")
        approved=expected if admissible and selected else 0
        check(count==approved and cert>=count,
              "Native intervention does not match independently audited count")
        literal_hits=re.findall(
            r"^c R32C_INJECTED_LITS count=(\d+) lits=([0-9,-]+)$",
            output,re.MULTILINE)
        if approved:
            check(signal=="APPLIED" and len(literal_hits)==1,
                  "Applied root unit literals not logged")
            length,body=literal_hits[0]
            signed=[int(x) for x in body.split(",")]
            check(int(length)==len(signed)==approved
                  and sorted(signed)==sorted(root["sample"]),
                  "Injected signed literals are not independently verified")
        else:
            check(signal!="APPLIED" and not literal_hits,
                  "Selected units on abstained/unsound source")
        active=dict(signal=signal,injected=count,certified=cert)
    return dict(status=status,seconds=round(elapsed,6),
                par2=round(elapsed,6) if status!="TIMEOUT" else CAP*2,
                verification=verified,root=root,
                proof=proof["status"] if proof else None,
                probes=len(probes),final=final,active=active)

def measure(a):
    frozen=Path(a.inputs)
    manifest=json.loads((frozen/"manifest.json").read_text())
    check(manifest["protocol"]==PROTO and len(manifest["cases"])==42,
          "Wrong holdout")
    check(0<=a.shard<SHARDS,"Shard range")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    bins={key:Path(getattr(a,key)).resolve() for key in ("clean","native")}
    check(all(x.is_file() for x in bins.values()),"Missing native baseline")
    out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    (out/"meta.json").write_text(json.dumps(dict(
        shard=a.shard,manifest=sha(frozen/"manifest.json"),
        binary_sha256={k:sha(v) for k,v in bins.items()}),indent=2))
    rows=[]
    for case in manifest["cases"][a.shard::SHARDS]:
        source=frozen/case["name"]
        check(sha(source)==case["sha256"],"Original CNF hash changed")
        for rep in range(REPS):
            order=list(MODES)
            random.Random(int(sha((case["sha256"]+":"+str(rep)+":R32D").encode()),16)).shuffle(order)
            for mode in order:
                result=one_trial(case,source,mode,bins)
                rows.append(dict(case=case["name"],family=case["family"],
                                 repeat=rep,mode=mode,**result))
                print("R32D_TRIAL",a.shard,case["name"],rep,mode,
                      result["status"],result["seconds"],
                      result["active"]["injected"] if result["active"] else "-",flush=True)
        (out/"rows.json").write_text(json.dumps(rows)+"\n")
    print("R32D_SHARD_PASS",a.shard,len(rows),flush=True)

def aggregate(a):
    inputs=Path(a.inputs)
    manifest=json.loads((inputs/"manifest.json").read_text())
    check(manifest["protocol"]==PROTO,"Original protocol drift")
    rows=[];binsha=set()
    for shard in range(SHARDS):
        directory=Path(a.combined)/f"r32d-shard-{shard}"/"results"
        meta=json.loads((directory/"meta.json").read_text())
        check(meta["shard"]==shard and meta["manifest"]==sha(inputs/"manifest.json"),
              "Source SHA mismatch between shards")
        binsha.add(json.dumps(meta["binary_sha256"],sort_keys=True))
        portion=json.loads((directory/"rows.json").read_text())
        check(len(portion)==len(manifest["cases"][shard::SHARDS])*REPS*len(MODES),
              "Missing frozen paired attempts")
        rows.extend(portion)
    check(len(binsha)==1 and len(rows)==42*20*5,
          "Expected 4200 attempts with same binary SHAs")
    cases={c["name"]:[x for x in rows if x["case"]==c["name"]] for c in manifest["cases"]}
    for name,arr in cases.items():
        check(len(arr)==REPS*len(MODES),"Missing per-case pairing")
        for rep in range(REPS):
            trial={x["mode"]:x for x in arr if x["repeat"]==rep}
            check(len(trial)==len(MODES),"Repeated/missing mode")
            off=trial["native_off"];shadow=trial["R32B_native_shadow"]
            if off["final"] and shadow["final"]:
                check(off["final"]==shadow["final"],"R32b passive policy drift")
            for mode in ("R32C_active","R32D_selective"):
                selected=trial[mode]
                if not selected["active"]["injected"] and off["final"] and selected["final"]:
                    check(selected["final"]==off["final"],"Policy drift despite no injection")
            statuses={x["status"] for x in trial.values()}-{"TIMEOUT"}
            check(len(statuses)<=1,"Contradictory solver result")
    grouped={"ALL":manifest["cases"]}
    grouped.update({f:[x for x in manifest["cases"] if x["family"]==f] for f in r31.FAMILIES})
    summary={}
    for group,cc in grouped.items():
        names={x["name"] for x in cc}
        d={}
        for mode in MODES:
            subset=[x for x in rows if x["case"] in names and x["mode"]==mode]
            d[mode]=dict(PAR2_sum=round(sum(x["par2"] for x in subset),6),
                         solved_cases=sum(all(x["status"]!="TIMEOUT" for x in subset
                           if x["case"]==c["name"]) for c in cc),
                         timeouts=sum(x["status"]=="TIMEOUT" for x in subset))
        for mode in ("R32C_active","R32D_selective"):
            applied=[x for x in rows if x["mode"]==mode and x["case"] in names]
            d[mode]["injected_total"]=sum(x["active"]["injected"] for x in applied)
            d[mode]["applied_cases"]=sum(any(x["active"]["injected"] for x in applied
                if x["case"]==c["name"]) for c in cc)
        baseline=d["native_off"]["PAR2_sum"]
        for mode in ("R32C_active","R32D_selective"):
            d[mode]["delta_vs_off_pct"]=round(100*(d[mode]["PAR2_sum"]-baseline)/baseline,4)
        summary[group]=d
        print("R32D_SUMMARY",group,json.dumps(d,sort_keys=True),flush=True)
    percase=[]
    for case in manifest["cases"]:
        part=cases[case["name"]]
        median={mode:round(statistics.median(x["par2"] for x in part if x["mode"]==mode),6)
                for mode in MODES}
        r=next(x for x in part if x["mode"]=="R32D_selective")
        percase.append(dict(name=case["name"],family=case["family"],
              medians=median,root=r["root"]["signal"],
              selected_literals=r["active"]["injected"],
              difference_vs_off_pct=round(100*(median["R32D_selective"]-
                  median["native_off"])/median["native_off"],4)))
    seed=random.Random(20261103)
    samples=[]
    for i in range(3000):
        picked=[seed.choice(percase) for _ in percase]
        a1=sum(p["medians"]["native_off"] for p in picked)
        b1=sum(p["medians"]["R32D_selective"] for p in picked)
        samples.append(100*(b1-a1)/a1)
    samples.sort()
    summary["ALL"]["bootstrap_case_median_delta95_pct"]=[
      round(samples[75],3),round(samples[2924],3)]
    summary["ALL"]["median_cases_improved"]=sum(
      p["medians"]["R32D_selective"]<p["medians"]["native_off"] for p in percase)
    summary["ALL"]["median_cases_total"]=len(percase)
    result=dict(protocol=PROTO,summary=summary,by_case=percase,
                rows=rows,source_sha=sha(inputs/"manifest.json"),
                cautions=manifest["warnings"])
    Path(a.output).write_text(json.dumps(result,indent=2)+"\n")
    md=["# R32d frozen structural GF2 selector: 4200-trial synthetic holdout",
        "42 SHA-distinct previously untested generator seeds; 20 repeats; 5 modes",
        "No official SAT instances or SOTA ranking; timeout 4s, PAR2=8s.",
        "Root-unit interventions independently audited against original CNF.",
        f'95% case-bootstrap interval on paired-case medians: {summary["ALL"]["bootstrap_case_median_delta95_pct"]}% (negative is faster).',
        f'Cases with lower median selective time: {summary["ALL"]["median_cases_improved"]}/42.',
        "","| Family | Clean PAR2 s | Native OFF PAR2 s | R32b passive s | R32c active s | R32d selective s | R32d vs OFF | Selected formulas |",
        "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for family,d in summary.items():
        md.append(f'| {family} | {d["clean"]["PAR2_sum"]:.4f} | {d["native_off"]["PAR2_sum"]:.4f} | {d["R32B_native_shadow"]["PAR2_sum"]:.4f} | {d["R32C_active"]["PAR2_sum"]:.4f} | {d["R32D_selective"]["PAR2_sum"]:.4f} | {d["R32D_selective"]["delta_vs_off_pct"]:+.3f}% | {d["R32D_selective"]["applied_cases"]} |')
    md+=["","| Source | Type | Selected literals | Native OFF median s | R32c median s | R32d median s |",
          "|---|---|---:|---:|---:|---:|"]
    for p in percase:
        m=p["medians"]
        md.append(f'| {p["name"]} | {p["root"]} | {p["selected_literals"]} | {m["native_off"]:.6f} | {m["R32C_active"]:.6f} | {m["R32D_selective"]:.6f} |')
    Path(a.report).write_text("\n".join(md)+"\n")
    print("R32D_AUDIT_PASS",len(rows),"trials",len(percase),"formulas",flush=True)

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="mode",required=True)
    x=sub.add_parser("freeze");x.add_argument("--dest",required=True)
    x=sub.add_parser("measure")
    for k in ("inputs","clean","native","outdir"):x.add_argument("--"+k,required=True)
    x.add_argument("--shard",type=int,required=True)
    x=sub.add_parser("aggregate")
    for k in ("inputs","combined","output","report"):x.add_argument("--"+k,required=True)
    args=p.parse_args()
    if args.mode=="freeze":freeze(args.dest)
    elif args.mode=="measure":measure(args)
    else:aggregate(args)

if __name__=="__main__":main()
