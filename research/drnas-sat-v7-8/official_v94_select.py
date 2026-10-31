#!/usr/bin/env python3
"""Freeze 12 new original SAT Competition 2026 CNFs BEFORE any DRNAS trials.

Uses ONLY pinned public competition metadata and input CNF size, and explicitly
excludes every instance previously used in the 2026 short/long 18-case audit.
The new 12 are an additional project-level holdout, not a blind competition.
"""
import csv,hashlib,json,sys
from pathlib import Path
from collections import defaultdict
from official_shortlong_select import download_and_features,REV,SCORES_GIT_BLOB
SALT="DRNAS-v94-official-2026-new-holdout-12-20261031-v1"
# Six SAT / six UNSAT; official CaDiCaL runtime fast=0.5..5s,
# mid=5..25s; runtime only affects cohort selection, not gate features.
QUOTAS={"sat_fast":3,"unsat_fast":3,"sat_mid":3,"unsat_mid":3}
SOURCE="original_manifest/official_shortlong_manifest.json"
scores=Path("official_scores.csv")
assert scores.is_file()
prior=json.loads(Path(SOURCE).read_text())
prior_ids={x["id"] for x in prior["cases"]}
assert len(prior_ids)==18
with scores.open(newline="",encoding="utf8") as f:records=list(csv.DictReader(f))
baseline=[r for r in records if r["solverid"]=="biere_cadical3[main]"]
assert len(baseline)==400
pools=defaultdict(list)
for row in baseline:
    if row["instanceid"] in prior_ids:continue
    if row["status"] not in ("sat-verified","unsat-verified"):continue
    sec=float(row["runtime"])
    if sec<.5 or sec>25:continue
    grade="fast" if sec<5 else "mid"
    label="sat" if row["status"]=="sat-verified" else "unsat"
    pools[label+"_"+grade].append(dict(id=row["instanceid"],
             official_label=label.upper(),stratum=label+"_"+grade,
             official_baseline_s=sec))
def order(s):return hashlib.sha256((SALT+"/"+s).encode()).hexdigest()
cases=[];attempts=[]
for group,quota in QUOTAS.items():
    candidates=sorted(pools[group],key=lambda x:order(group+"/"+x["id"]))
    for item in candidates:
        if len([x for x in cases if x["stratum"]==group])>=quota:break
        try:
            data=download_and_features(item["id"])
        except Exception as e:
            attempts.append({"id":item["id"],"stratum":group,
                "accepted":False,"reason":str(e)})
            print("V94_REJECT",group,item["id"],str(e),flush=True)
            continue
        cases.append({**item,**data,"split":"new_holdout"})
        attempts.append({"id":item["id"],"stratum":group,"accepted":True})
        print("V94_ACCEPT",group,item["id"],item["official_baseline_s"],
              data["cnf_bytes"],data["sha256"],flush=True)
    got=len([x for x in cases if x["stratum"]==group])
    if got!=quota:raise RuntimeError(f"Insufficient suitable new CNFs for {group}: {got}/{quota}")
assert len(cases)==12 and not ({x["id"] for x in cases}&prior_ids)
cases.sort(key=lambda x:order("schedule/"+x["id"]))
manifest={"protocol":SALT,"official_commit":REV,"scores_git_blob":SCORES_GIT_BLOB,
          "original_18_excluded":sorted(prior_ids),"quotas":QUOTAS,
          "warnings":["2026 competition instances already published; not truly blind",
                      "Official CaDiCaL runtimes used for selection only",
                      "Only 12 cases, file-size-limited, not competition representative",
                      "No data-dependent v9.4 selector threshold tuning allowed"],
          "rejected_or_accepted_candidates":attempts,"cases":cases}
Path("official_v94_manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
print("V94_FROZEN_NEW_HOLDOUT",len(cases),
      "sha256",hashlib.sha256(Path("official_v94_manifest.json").read_bytes()).hexdigest(),flush=True)
