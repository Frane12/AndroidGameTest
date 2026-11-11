#!/usr/bin/env python3
"""Train GENERALIST4 once from immutable verified-par2 GENERALIST2 artifacts.
No holdout sources are visited; policy and input SHA audit are frozen.
"""
import json,sys
from pathlib import Path
sys.path.insert(0,"research")
from drnas_atlas40_benchmark import source_set
from generalist.generalist3 import fingerprint,learn,BASE
import hashlib
root=Path("audits")
rows=[]
all_sha=set()
for cohort in ("regression","extension","hard"):
    sources={s["sha256"]:s for s in source_set(cohort)}
    for shard in (0,1):
        matches=list((root/f"GENERALIST2-{cohort}-{shard}").rglob(f"result_{shard}.json"))
        assert len(matches)==1,(cohort,shard,[str(x) for x in matches])
        obj=json.loads(matches[0].read_text())
        for trial in obj["rows"]:
            if trial["arm"]=="KISSAT":continue
            sha=trial["sha256"]
            assert sha in sources
            src=sources[sha]
            feat=fingerprint(src["path"])
            assert feat["sha256"]==sha
            cap=float(obj["cap_s"])
            score=float(trial["PAR2_verified_s"])
            assert trial["status"]!="SAT_VERIFIED" or trial["original_SAT_witness_verified"]
            assert score>=0 and score<=2*cap+0.001
            rows.append(dict(sha256=sha,feature_key=feat["key"],arm=trial["arm"],
                             verified_par2_s=score,cap_s=cap,original_verified=True))
            all_sha.add(sha)
assert len(rows)==156 and len(all_sha)==26,(len(rows),len(all_sha))
cells=learn(rows,min_distinct=8,min_ratio=1.05)
model={"version":3,"baseline":BASE,"cells":cells,
       "training_sha":sorted(all_sha),"training_run_id":43048240072,
       "selection_frozen":True,"status":"trained on 26 source CNFs; external holdout untested"}
Path("generalist4_policy.json").write_text(json.dumps(model,indent=2,sort_keys=True)+"\n")
print("GENERALIST4_TRAIN "+json.dumps({"sha":len(all_sha),"rows":len(rows),
     "cells":len(cells),"selected":{k:v for k,v in cells.items() if v["arm"]!=BASE}},sort_keys=True),flush=True)
