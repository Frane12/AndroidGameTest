#!/usr/bin/env python3
"""Preregister a previously-unrun 72-instance, label-stratified 2026 SAT evaluation.
Sampling depends on PUBLIC official CaDiCaL runtimes and original 20 exclusion,
not on any DRNAS trial. It is not a blind or representative random holdout.
Freeze this exact code before running the first 72-instance evaluation.
"""
import argparse,csv,hashlib,json
from pathlib import Path
SEED="DRNAS-SAT-20261031-prereg72-v1-do-not-retune"
# 72: heterogeneous, intentionally nonrepresentative strata; report each separately.
QUOTAS={"SAT_fast":10,"SAT_mid":12,"SAT_hard":12,
        "UNSAT_fast":4,"UNSAT_mid":12,"UNSAT_hard":14,
        "UNKNOWN_hard":8}
BASELINE="biere_cadical3[main]"
OFFICIAL_SCORES_BLOB="9c926b2bd35ac0fb4f3d0cf8f58c97178d43faef"
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--scores",required=True)
    p.add_argument("--previous",required=True)
    p.add_argument("--out",required=True)
    a=p.parse_args()
    with open(a.previous,newline="",encoding="utf8") as f:
        old=list(csv.DictReader(f))
    assert len(old)==24 and sum(x["status"]=="READY" for x in old)==20
    excluded={x["gbd_id"] for x in old}
    excluded.update(("4ae685a11b5cecca76dc3d463481ce92",
                     "0c9da400944b002f90fd385d4fdab385"))
    with open(a.scores,newline="",encoding="utf8") as f:
        scores=list(csv.DictReader(f))
    verified={}
    baseline={}
    for row in scores:
        case=row["instanceid"]
        if row["status"] in ("sat-verified","unsat-verified"):
            label="SAT" if row["status"]=="sat-verified" else "UNSAT"
            if case in verified and verified[case]!=label:
                raise RuntimeError("Conflicting public verified labels "+case)
            verified[case]=label
        if row["solverid"]==BASELINE:
            if case in baseline:raise RuntimeError("Duplicate CaDiCaL baseline "+case)
            baseline[case]=row
    groups={key:[] for key in QUOTAS}
    for case,rec in baseline.items():
        if case in excluded:continue
        label=verified.get(case,"UNKNOWN")
        t=float(rec["runtime"])
        bucket="fast" if t<=20 and rec["status"] in ("sat-verified","unsat-verified") else (
               "mid" if t<=600 and rec["status"] in ("sat-verified","unsat-verified") else "hard")
        if label=="UNKNOWN":bucket="hard"
        name=label+"_"+bucket
        if name in groups:
            groups[name].append(dict(id=case,label=label,stratum=name,
                official_cadical3_runtime_s=t,
                official_cadical3_status=rec["status"]))
    selected=[]
    for name,quota in QUOTAS.items():
        pool=sorted(groups[name],key=lambda x:hashlib.sha256(
            (SEED+"/"+name+"/"+x["id"]).encode()).hexdigest())
        if len(pool)<quota:raise RuntimeError(
            "Not enough previously unused "+name+": "+str(len(pool)))
        selected+=pool[:quota]
        print("PREREG_STRATUM",name,"population",len(pool),"selected",quota,flush=True)
    assert len(selected)==72 and len({x["id"] for x in selected})==72
    selected.sort(key=lambda x:hashlib.sha256((SEED+"/order/"+x["id"]).encode()).hexdigest())
    for i,rec in enumerate(selected):rec["index"]=i
    obj=dict(protocol="DRNAS-2026-preregistered-72-v1",
        seed=SEED,official_scores_git_blob=OFFICIAL_SCORES_BLOB,
        source_dataset="SAT Competition 2026 official scores.csv, pinned Git revision",
        selection="label-and-baseline-runtime stratified cryptographic deterministic",
        previously_examined_ids_excluded=sorted(excluded),strata_quota=QUOTAS,
        limitations=["Not a blind holdout; public labels used for stratification",
          "Not a random draw from the competition distribution; no overall general-win claim",
          "No DRNAS measurements used in selecting these instance IDs"],
        cases=selected)
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
    print("PREREG_COMPLETE",len(selected),"manifest_sha256",
          hashlib.sha256(out.read_bytes()).hexdigest(),flush=True)
if __name__=="__main__":main()
