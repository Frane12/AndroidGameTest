#!/usr/bin/env python3
"""DRNAS SAT V7.7 — frozen prospective original SATLIB CNFs, paired controls.
No instance selection by solver runtime. SAT/UNSAT label mismatch aborts.
PAR-2 retains all 12s process timeouts. Model verified inside C++.
"""
import argparse,csv,hashlib,json,random,statistics,subprocess,time
from collections import Counter,defaultdict
from pathlib import Path

METHODS=("plain","majority","split1024","guided1024","v76_guided",
         "observe_plain1024","quality_plain","quality_guided","quality_random")
FIELDS=("case","family","known_answer","method","repeat","answer","wall_s","native_s",
        "phases","first_budget","stage1","second_budget","stage2",
        "extended","resumed","observed","short3","short5","short8",
        "sum_len","short_fraction","probe_us","extension_us","resume_us",
        "variables","clauses","cutoff_s","error")

def execute(binary,method,path,seed,cutoff):
    start=time.perf_counter()
    try:
        run=subprocess.run([str(binary),method,str(path),str(seed)],
                           capture_output=True,text=True,check=False,timeout=cutoff)
    except subprocess.TimeoutExpired:
        return dict(answer="TIMEOUT",wall_s=cutoff,native_s=None,error="")
    wall=time.perf_counter()-start
    if run.returncode!=0:
        raise RuntimeError("C++ exited abnormally "+method+" / "+str(path)+": "+
                           run.stderr[-1200:])
    hits=[s for s in run.stdout.splitlines() if s.startswith("DRNAS_RESULT\t")]
    if len(hits)!=1:
        raise RuntimeError("Missing or duplicated machine-readable result")
    a=hits[0].split("\t")
    if len(a)!=22 or a[1]!=method or a[2] not in ("SAT","UNSAT"):
        raise RuntimeError("Malformed machine result: "+hits[0][:400])
    try:
        return dict(answer=a[2],wall_s=wall,native_s=float(a[3])/1e6,
           phases=int(a[4]),first_budget=int(a[5]),stage1=int(a[6]),
           second_budget=int(a[7]),stage2=int(a[8]),
           extended=int(a[9]),resumed=int(a[10]),
           observed=int(a[11]),short3=int(a[12]),short5=int(a[13]),
           short8=int(a[14]),sum_len=int(a[15]),short_fraction=float(a[16]),
           probe_us=float(a[17]),extension_us=float(a[18]),
           resume_us=float(a[19]),variables=int(a[20]),
           clauses=int(a[21]),error="")
    except (ValueError,IndexError) as exc:
        raise RuntimeError("Cannot parse C++ result: "+hits[0]) from exc

def report(rows,reps,cutoff):
    by=defaultdict(lambda:defaultdict(list))
    fam={}
    classes={}
    for r in rows:
        by[r["case"]][r["method"]].append(r)
        fam[r["case"]]=r["family"]
        classes[r["case"]]=r["known_answer"]
    ids=sorted(by)
    if not ids:raise RuntimeError("Benchmark has no valid instances")
    for name in ids:
        if set(by[name])!=set(METHODS):
            raise RuntimeError("Missing method: "+name)
        for method in METHODS:
            trials=by[name][method]
            if len(trials)!=reps:
                raise RuntimeError("Missing repetition: "+name+"/"+method)
            if any(r["answer"] not in ("TIMEOUT",classes[name]) for r in trials):
                raise RuntimeError("Wrong answer: "+name+"/"+method)

    def cost(name,method):
        values=[2*cutoff if r["answer"]=="TIMEOUT" else r["wall_s"]
                for r in by[name][method]]
        return statistics.median(values)

    def subset(names,method):
        if not names:return None
        total=sum(cost(k,method) for k in names)
        plain=sum(cost(k,"plain") for k in names)
        obs=[r["observed"] for k in names for r in by[k][method]
             if r["observed"] is not None and r["stage1"]==0]
        short=[r["short_fraction"] for k in names for r in by[k][method]
               if r["short_fraction"] is not None and r["stage1"]==0]
        return {
            "n":len(names),
            "PAR2_sum_case_medians_s":round(total,6),
            "ratio_plain_over_method":round(plain/max(total,1e-12),6),
            "solved_runs":sum(r["answer"]!="TIMEOUT" for k in names for r in by[k][method]),
            "total_runs":len(names)*reps,
            "faster_cases_than_plain":sum(cost(k,method)<cost(k,"plain") for k in names),
            "slower_cases_than_plain":sum(cost(k,method)>cost(k,"plain") for k in names),
            "extended_cases":sum(any(r["extended"] for r in by[k][method]) for k in names),
            "extended_runs":sum(r["extended"] for k in names for r in by[k][method]
                                if r["extended"] is not None),
            "checkpoint_unknown_runs":sum(r["stage1"]==0 for k in names
                                           for r in by[k][method]),
            "median_export_offers_at_checkpoint":(round(statistics.median(obs),3)
                                                    if obs else None),
            "median_short5_fraction_at_checkpoint":(round(statistics.median(short),6)
                                                      if short else None)
        }
    modes={m:subset(ids,m) for m in METHODS}
    family=defaultdict(list)
    for name in ids:family[fam[name]].append(name)
    family_scores={f:{m:subset(names,m) for m in METHODS}
                   for f,names in sorted(family.items())}
    classes_scores={cl:{m:subset([k for k in ids if classes[k]==cl],m)
                        for m in METHODS} for cl in ("SAT","UNSAT")}
    rng=random.Random(77072026)
    contrasts={}
    comparisons=(("quality_guided","quality_plain"),
                 ("quality_guided","quality_random"),
                 ("quality_guided","observe_plain1024"),
                 ("quality_guided","guided1024"),
                 ("quality_guided","v76_guided"),
                 ("quality_guided","plain"))
    for proposed,control in comparisons:
        proposed_score=sum(cost(k,proposed) for k in ids)
        control_score=sum(cost(k,control) for k in ids)
        boot=[]
        for _ in range(1200):
            draw=[rng.choice(ids) for _ in ids]
            boot.append(sum(cost(k,control) for k in draw)/
                        max(sum(cost(k,proposed) for k in draw),1e-12))
        boot.sort()
        contrasts[f"{proposed}_vs_{control}"]={
            "ratio_control_over_proposed":round(control_score/max(proposed_score,1e-12),6),
            "paired_bootstrap_95pct":[round(boot[29],6),round(boot[1170],6)],
            "faster_instances":sum(cost(k,proposed)<cost(k,control) for k in ids),
            "slower_instances":sum(cost(k,proposed)>cost(k,control) for k in ids)
        }
    return {
        "n_instances":len(ids),"repetitions":reps,"cutoff_s":cutoff,
        "source":"Original SHA256-pinned external SATLIB archive members",
        "solver":"unmodified official CaDiCaL rel-3.0.1",
        "modes":modes,"families":family_scores,"SAT_UNSAT":classes_scores,
        "contrasts":contrasts,
        "caveats":[
            "CaDiCaL Learner callback observes clause sizes offered for external export, not an LBD metric nor necessarily all internal learned clauses.",
            "Matched quality_plain uses the same callback and decision threshold without phase hints; each method can therefore observe a different clause distribution.",
            "Every timeout retained as PAR2 2x cutoff; times include process startup and solver but not original DIMACS reading in native measurement.",
            "One solver instance is maintained across all phases, so learned clauses are not discarded.",
            "SAT models checked by native solver against original formula; UNSAT compared with pinned original answer labels, not externally proof-certified.",
            "Pilot excluded from final results. All holdout formulas frozen before probing pilot.",
            "Paired bootstrap resamples CNF instances; confidence intervals including one do not establish a speedup."
        ]
    }

def main(args):
    verify=json.loads(Path(args.verification).read_text())
    cases=verify[args.group]
    root=Path(args.outdir)
    root.mkdir(parents=True,exist_ok=True)
    rows=[]
    with (root/"raw.csv").open("w",newline="",encoding="utf8") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader()
        for idx,entry in enumerate(cases):
            path=Path(entry["path"])
            if hashlib.sha256(path.read_bytes()).hexdigest()!=entry["expected_sha256"]:
                raise RuntimeError("Source SHA256 mismatch: "+entry["name"])
            if entry["status"] not in ("SAT","UNSAT"):
                raise RuntimeError("Missing external known truth class")
            for rep in range(args.repeats):
                methods=list(METHODS)
                random.Random(7707000+idx*271+rep*293).shuffle(methods)
                for method in methods:
                    result=execute(args.binary,method,path,7707+idx*113+rep*7,args.timeout)
                    row={col:result.get(col) for col in FIELDS}
                    row.update(case=entry["name"],family=entry["family"],
                               known_answer=entry["status"],method=method,
                               repeat=rep,cutoff_s=args.timeout)
                    rows.append(row)
                    w.writerow(row);f.flush()
                    if result["answer"] not in ("TIMEOUT",entry["status"]):
                        raise RuntimeError(f"WRONG SAT/UNSAT {entry['name']} "
                                           f"{method}: {result['answer']}")
            print(f"{args.group} {idx+1}/{len(cases)} {entry['name']}: "+
                  str(dict(Counter(r["answer"] for r in rows
                                   if r["case"]==entry["name"]))),flush=True)
    summary=report(rows,args.repeats,args.timeout)
    (root/"summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf8")
    print("SUMMARY",json.dumps({k:summary[k] for k in
                  ("n_instances","modes","contrasts")},indent=2),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--binary",required=True)
    p.add_argument("--verification",required=True)
    p.add_argument("--group",choices=("pilot","holdout"),required=True)
    p.add_argument("--outdir",required=True)
    p.add_argument("--timeout",type=float,default=12)
    p.add_argument("--repeats",type=int,default=2)
    main(p.parse_args())
