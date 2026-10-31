#!/usr/bin/env python3
"""Freeze a truly NEW-to-this-project 12-CNF official 2026 cohort.

Exclude all prior 18+12 CNFs, select using ONLY public competition CaDiCaL
official runtime and file-size limits, not ANY DRNAS measurement.
Record fastest published 2026 Main solver per case for contextual comparison;
those official results ran on DIFFERENT hardware and are not speed records
we can directly challenge by our times.
"""
import csv,hashlib,json,math
from collections import defaultdict
from pathlib import Path
from official_shortlong_select import download_and_features,REV,SCORES_GIT_BLOB
SALT="DRNAS-v96-OOD-official-new-12-frozen-budgets-64-96-128-256-20261031-v1"
QUOTAS={"SAT":6,"UNSAT":6}
def fingerprint(s):return hashlib.sha256((SALT+"|"+s).encode()).hexdigest()
def main():
    old18=json.loads(Path("known18/official_shortlong_manifest.json").read_text())
    old12=json.loads(Path("known12/official_v94_manifest.json").read_text())
    used={x["id"] for x in old18["cases"]}|{x["id"] for x in old12["cases"]}
    assert len(old18["cases"])==18 and len(old12["cases"])==12 and len(used)==30
    with Path("official_scores.csv").open(newline="",encoding="utf8") as f:
        rows=list(csv.DictReader(f))
    baseline=[r for r in rows if r["solverid"]=="biere_cadical3[main]"]
    assert len(baseline)==400
    per_id=defaultdict(list)
    for r in rows:
        if r["status"] in ("sat-verified","unsat-verified"):
            try:sec=float(r["runtime"])
            except (ValueError,KeyError):continue
            if math.isfinite(sec) and sec>=0:
                per_id[r["instanceid"]].append((sec,r["solverid"]))
    pool=defaultdict(list)
    for r in baseline:
        id=r["instanceid"]
        if id in used or r["status"] not in ("sat-verified","unsat-verified"):continue
        secs=float(r["runtime"])
        if secs<1 or secs>180:continue
        label="SAT" if r["status"]=="sat-verified" else "UNSAT"
        best=min(per_id[id],default=None)
        pool[label].append(dict(id=id,official_label=label,
             stratum=label.lower()+("_fast" if secs<10 else "_moderate" if secs<50 else "_hard"),
             official_baseline_s=secs,official_best_s=best[0] if best else None,
             official_fastest_solver=best[1] if best else None))
    cases=[];attempts=[]
    for label in QUOTAS:
        # Prefer official CaDiCaL results near 12 seconds; this targets
        # interpretable mid-hard runs without conditioning on DRNAS success.
        candidates=sorted(pool[label],key=lambda x:(
            abs(math.log(max(x["official_baseline_s"],.1)/12.0)),
            fingerprint(x["id"])))
        for item in candidates:
            if sum(x["official_label"]==label for x in cases)>=QUOTAS[label]:break
            try:
                info=download_and_features(item["id"])
            except Exception as e:
                attempts.append({"id":item["id"],"label":label,"ok":False,"error":str(e)})
                print("V96_SOURCE_SKIP",label,item["id"],str(e),flush=True)
                continue
            cases.append({**item,**info,"split":"unseen_to_DRNAS"})
            attempts.append({"id":item["id"],"label":label,"ok":True})
            print("V96_SELECT",label,item["id"],item["official_baseline_s"],
                "official_best",item["official_fastest_solver"],item["official_best_s"],
                "sha256",info["sha256"],flush=True)
        count=sum(x["official_label"]==label for x in cases)
        if count!=QUOTAS[label]:
            raise RuntimeError("insufficient official unused downloadable "+label+
                               " "+str(count)+" / "+str(QUOTAS[label]))
    assert len(cases)==12 and not ({x["id"] for x in cases}&used)
    cases.sort(key=lambda x:fingerprint("run-order/"+x["id"]))
    manifest={"protocol":SALT,"reference":REV,"scores_git_blob":SCORES_GIT_BLOB,
        "prior_30_excluded":sorted(used),"n":12,"quotas":QUOTAS,
        "methods_frozen":["ca_plain","v96_64","v96_96","v96_128","v96_256"],
        "wall_limit_s":15,"timeout_PAR2_s":30,"repeats":2,
        "selection":"official CaDiCaL published time near 12s; never selected by DRNAS timings",
        "warnings":["published 2026 instances are public and only project-level holdout",
            "preselecting by baseline may bias speedup comparisons",
            "official best per CNF is different hardware, NOT a world-record claim",
            "12 formulas insufficient to certify world-leading solver",
            "UNSAT proof certificate independently unchecked"],
        "attempts":attempts,"cases":cases}
    out=Path("official_v96_manifest.json")
    out.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    print("V96_FROZEN",len(cases),"manifestsha",
          hashlib.sha256(out.read_bytes()).hexdigest(),flush=True)
if __name__=="__main__":main()
