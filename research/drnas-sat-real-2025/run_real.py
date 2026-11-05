#!/usr/bin/env python3
"""Run unchanged DRNAS v7.2.1 and CaDiCaL 3.0.1 on PINNED real 2025 CNFs.
- Native timed region uses exact original v7.2.1 code, excluding file I/O.
- External process limit is identical across methods.
- Every timeout remains in statistics as PAR-2 (2 * per-method cutoff).
- All unexpected SAT/UNSAT answers are fatal and never silently skipped.
- All inputs are SHA-256 verified by fetch_benchmarks.py, unchanged bytes.
"""
import argparse
import csv
import json
import random
import statistics
import subprocess
import time
from collections import Counter, defaultdict
from pathlib import Path

METHODS=("plain","majority","selective","confidence","confidence_random")
COLUMNS=("case","family","known_answer","method","repeat","result","expected",
         "wall_s","native_ms","selected","hint_count","analysis_us","pair_reuse",
         "variables","clauses","timeout_s","error")

def run_process(binpath, method, path, seed, timeout):
    start=time.perf_counter()
    try:
        p=subprocess.run([str(binpath),method,str(path),str(seed)],
                         capture_output=True,text=True,timeout=timeout,check=False)
        wall=time.perf_counter()-start
    except subprocess.TimeoutExpired:
        return {"result":"TIMEOUT","wall_s":timeout,"native_ms":None,"error":""}
    if p.returncode:
        return {"result":"ERROR","wall_s":wall,"native_ms":None,
                "error":(p.stderr or p.stdout)[-1000:].replace("\n"," ")}
    hits=[line for line in p.stdout.splitlines() if line.startswith("DRNAS_RESULT\t")]
    if len(hits)!=1:
        return {"result":"ERROR","wall_s":wall,"native_ms":None,
                "error":"Missing or multiple machine result markers"}
    parts=hits[0].split("\t")
    if len(parts)!=10 or parts[1]!=method or parts[2] not in ("SAT","UNSAT"):
        return {"result":"ERROR","wall_s":wall,"native_ms":None,
                "error":"Invalid machine result markers"}
    try:
        return {"result":parts[2],"wall_s":wall,"native_ms":float(parts[3])/1000,
                "selected":int(parts[4]),"hint_count":int(parts[5]),
                "analysis_us":float(parts[6]),"pair_reuse":float(parts[7]),
                "variables":int(parts[8]),"clauses":int(parts[9]),"error":""}
    except ValueError as exc:
        return {"result":"ERROR","wall_s":wall,"native_ms":None,"error":str(exc)}

def inspect_features(binary,path,seed,timeout):
    p=subprocess.run([str(binary),"features",str(path),str(seed)],
                     capture_output=True,text=True,timeout=timeout)
    if p.returncode:raise RuntimeError("Feature probe failed: "+p.stderr[-900:])
    hits=[l for l in p.stdout.splitlines() if l.startswith("DRNAS_FEATURES\t")]
    if len(hits)!=1:raise RuntimeError("Unexpected feature probe response")
    p=hits[0].split("\t")
    if len(p)!=7:raise RuntimeError(f"Malformed feature response, len {len(p)}")
    return dict(old_selected=int(p[1]),confidence_selected=int(p[2]),
                confidence_gate_us=float(p[3]),pair_reuse=float(p[4]),
                variables=int(p[5]),clauses=int(p[6]))

def compute_report(rows,features,timeout_s,repeats):
    by=defaultdict(lambda:defaultdict(list))
    answers={}
    families={}
    for row in rows:
        by[row["case"]][row["method"]].append(row)
        answers[row["case"]]=row["expected"]
        families[row["case"]]=row["family"]
    ids=sorted(by)
    penalty=2*timeout_s
    per_case={}
    for cid in ids:
        per_case[cid]={}
        for method in METHODS:
            samples=by[cid].get(method,[])
            if len(samples)!=repeats:
                raise RuntimeError(f"Missing run for {cid}/{method}")
            # Timeouts are censored and scored as PAR2, never as success.
            total=0.0
            native_completed=[]
            for sample in samples:
                if sample["result"] in ("SAT","UNSAT"):
                    total+=sample["wall_s"]
                    native_completed.append(sample["native_ms"])
                elif sample["result"]=="TIMEOUT":
                    total+=penalty
                else:
                    raise RuntimeError("ERROR result must not be aggregated as timeout")
            per_case[cid][method]={"par2_s":total/repeats,
                "solved":sum(x["result"] in ("SAT","UNSAT") for x in samples),
                "native_ms_completed":(statistics.median(native_completed) if native_completed else None)}
    def total_for(ks,method):
        if not ks:return None
        score=sum(per_case[k][method]["par2_s"] for k in ks)
        plain=sum(per_case[k]["plain"]["par2_s"] for k in ks)
        return {"n_cases":len(ks),
                "par2_score_s":round(score,6),
                "speed_ratio_plain_over_method":round(plain/max(score,1e-9),6),
                "solved_runs":sum(per_case[k][method]["solved"] for k in ks),
                "total_runs":len(ks)*repeats,
                "fully_solved_cases":sum(per_case[k][method]["solved"]==repeats for k in ks),
                "faster_cases_par2":sum(per_case[k][method]["par2_s"] <
                                        per_case[k]["plain"]["par2_s"] for k in ks)}
    totals={method:total_for(ids,method) for method in METHODS}
    selected=[k for k in ids if features[k]["confidence_selected"]==1]
    old_selected=[k for k in ids if features[k]["old_selected"]==1]
    groups={
        "confidence_selected":{m:total_for(selected,m) for m in METHODS},
        "confidence_rejected":{m:total_for([k for k in ids if k not in selected],m) for m in METHODS},
        "old_selected":{m:total_for(old_selected,m) for m in METHODS}
    }
    # Benefit 5% valid only when BOTH plain and unconditional majority
    # solved all repeats. Other labels are unknown due to censoring.
    assessable=[k for k in ids if per_case[k]["plain"]["solved"]==repeats
                and per_case[k]["majority"]["solved"]==repeats]
    beneficial={k for k in assessable if
                per_case[k]["majority"]["par2_s"]<=0.95*per_case[k]["plain"]["par2_s"]}
    confusion={}
    for label,choice in [("v7_2",set(old_selected)),("v7_2_1",set(selected))]:
        available=set(assessable)
        chosen=choice & available
        TP=len(chosen & beneficial)
        FP=len(chosen-beneficial)
        FN=len(beneficial-chosen)
        TN=len(available-chosen-beneficial)
        confusion[label]={"assessable":len(assessable),
                          "not_assessable_due_to_timeout":len(ids)-len(assessable),
                          "selected_total":len(choice),
                          "TP":TP,"FP":FP,"FN":FN,"TN":TN,
                          "precision":round(TP/(TP+FP),5) if TP+FP else None,
                          "recall":round(TP/(TP+FN),5) if TP+FN else None}
    family=defaultdict(list)
    for k in ids:family[families[k]].append(k)
    family_report={fam:{"n":len(ks),
                        "methods":{m:total_for(ks,m) for m in METHODS},
                        "confidence_selected":sum(features[k]["confidence_selected"] for k in ks)}
                   for fam,ks in sorted(family.items())}
    return {
        "data_type":"published external SAT Competition 2025 (not DRNAS generated)",
        "cases":len(ids),"repetitions":repeats,"timeout_per_process_seconds":timeout_s,
        "PAR2_penalty_seconds":penalty,
        "known_labels":dict(Counter(answers.values())),
        "selected_by_confidence":len(selected),
        "selected_by_old_gate":len(old_selected),
        "selector_gate_us_mean":round(statistics.mean(v["confidence_gate_us"] for v in features.values()),5),
        "selector_gate_us_median":round(statistics.median(v["confidence_gate_us"] for v in features.values()),5),
        "methods":totals,"subsets":groups,"precision_exploratory_only":confusion,
        "by_family":family_report,
        "notes":[
            "Every original CNF is externally sourced and SHA-256 verified, never modified.",
            "Run timeout enforced outside native process. PAR-2 includes process startup; native timing excludes DIMACS read.",
            "All five methods receive same unchanged formula and process timeout, in shuffled order.",
            "Training of confidence thresholds occurred on synthetic formulas; no parameter tuning on these real inputs.",
            "External corpus provides SAT/UNSAT labels; every SAT solution checked by unchanged native solver.",
            "For timeout-censored rows no speedup is asserted and precision uses only assessable formulas.",
            "Subset of 32 compact benchmark families, not a full SAT Competition leaderboard."
        ]
    }

def run(binary, verification, group, outdir, timeout_s, repeats):
    verification=json.loads(Path(verification).read_text())
    inputs=verification[group]
    root=Path(outdir);root.mkdir(parents=True,exist_ok=True)
    csvpath=root/"raw.csv"
    features={}
    rows=[]
    with csvpath.open("w",newline="",encoding="utf8") as f:
        writer=csv.DictWriter(f,fieldnames=COLUMNS);writer.writeheader()
        for idx,entry in enumerate(inputs):
            if entry["expected_sha256"]!=entry["observed_sha256"]:
                raise RuntimeError("Source verification metadata invalid")
            input_path=Path(entry["path"])
            # Verification on actual disk bytes before every problem.
            import hashlib
            if hashlib.sha256(input_path.read_bytes()).hexdigest()!=entry["expected_sha256"]:
                raise RuntimeError("File modified after download: "+entry["name"])
            case=entry["name"];expected=entry["status"]
            features[case]=inspect_features(binary,input_path,idx+2091,timeout_s)
            scheduled=[(m,r) for m in METHODS for r in range(repeats)]
            random.Random(0x73121+idx).shuffle(scheduled)
            for method,rep in scheduled:
                observation=run_process(binary,method,input_path,2091+idx*37,timeout_s)
                row={"case":case,"family":entry["family"],"known_answer":expected,
                    "method":method,"repeat":rep,"result":observation["result"],
                    "expected":expected,"wall_s":observation["wall_s"],
                    "native_ms":observation.get("native_ms"),
                    "selected":observation.get("selected"),
                    "hint_count":observation.get("hint_count"),
                    "analysis_us":observation.get("analysis_us"),
                    "pair_reuse":observation.get("pair_reuse"),
                    "variables":features[case]["variables"],
                    "clauses":features[case]["clauses"],
                    "timeout_s":timeout_s,"error":observation.get("error","")}
                rows.append(row)
                writer.writerow(row)
                f.flush()
                if row["result"] not in ("TIMEOUT",expected):
                    # Abort on a wrong answer, parser failure or crash.
                    raise RuntimeError(f"Invalid result {case} {method}: "
                                       f"received {row['result']} expected {expected}. "
                                       f"Error {row['error']}")
            solved=Counter(r["result"] for r in rows if r["case"]==case)
            print(f"{group} {idx+1}/{len(inputs)} {entry['family']} expected={expected} "
                  f"confidence={features[case]['confidence_selected']} results={dict(solved)}",
                  flush=True)
    (root/"features.json").write_text(json.dumps(features,indent=2))
    summary=compute_report(rows,features,timeout_s,repeats)
    (root/"summary.json").write_text(json.dumps(summary,indent=2))
    print("SUMMARY",json.dumps({k:summary[k] for k in
          ("cases","selected_by_confidence","selector_gate_us_mean","methods",
           "precision_exploratory_only")},indent=2))
    return summary

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--binary",required=True)
    p.add_argument("--verification",required=True)
    p.add_argument("--group",required=True,choices=["pilot","holdout"])
    p.add_argument("--outdir",required=True)
    p.add_argument("--timeout",type=float,default=6.0)
    p.add_argument("--repeats",type=int,default=2)
    a=p.parse_args()
    run(a.binary,a.verification,a.group,a.outdir,a.timeout,a.repeats)
