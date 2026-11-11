#!/usr/bin/env python3
import json,collections
from pathlib import Path
rows=[];seen=set();trained=None
for shard in (0,1):
 paths=list((Path("audits")/f"GENERALIST4-{shard}").rglob(f"results_{shard}.json"))
 assert len(paths)==1,(shard,paths)
 d=json.loads(paths[0].read_text())
 t=set(d["training_sha"])
 if trained is None:trained=t
 assert t==trained
 for src in d["sources"]:
  assert src["sha256"] not in trained
  assert src["sha256"] not in seen
  seen.add(src["sha256"])
 rows.extend(d["rows"])
assert len(seen)==10 and len(rows)==100,(len(seen),len(rows))
groups=collections.defaultdict(dict)
arms=("A36_75","A39_PROTECT","A40_TREE","AUTO","KISSAT")
for r in rows:
 key=(r["sha256"],r["rep"])
 assert r["arm"] not in groups[key]
 groups[key][r["arm"]]=r
 assert r["status"]!="SAT_VERIFIED" or r["original_SAT_witness_verified"]
 assert not r["independent_UNSAT_proof_verified"]
assert len(groups)==20 and all(set(d)==set(arms) for d in groups.values())
stats={}
for arm in arms:
 items=[r for r in rows if r["arm"]==arm]
 stats[arm]={"verified_PAR2_s":round(sum(r["PAR2_verified_s"] for r in items),6),
 "reported_PAR2_s":round(sum(r["PAR2_reported_s"] for r in items),6),
 "sat_verified":sum(r["status"]=="SAT_VERIFIED" for r in items),
 "unsat_unverified":sum(r["status"]=="UNSAT_UNVERIFIED" for r in items),
 "timeouts":sum(r["status"]=="UNKNOWN" for r in items)}
by_family=collections.defaultdict(lambda:collections.defaultdict(list))
for r in rows:by_family[r["family"]][r["arm"]].append(r["PAR2_verified_s"])
families={fam:{arm:round(sum(values),6) for arm,values in data.items()} for fam,data in by_family.items()}
feedback=[]
for key,g in groups.items():
 auto=g["AUTO"]
 best=min(("A36_75","A39_PROTECT","A40_TREE"),key=lambda arm:g[arm]["PAR2_verified_s"])
 feedback.append({"sha256":key[0],"rep":key[1],"chosen":auto["executed_arm"],
  "best_observed":best,"regret_s":round(auto["PAR2_verified_s"]-g[best]["PAR2_verified_s"],6),
  "feature":auto["fingerprint_key"]})
out={"original_sha":len(seen),"trials":len(rows),"training_sha":len(trained),"sha_disjoint":True,
 "one_cpu":True,"independent_unsat_lrat":False,"stats":stats,
 "families":families,"policy_nondefault_trials":sum(x["chosen"]!="A36_75" for x in feedback),
 "feedback":feedback}
Path("generalist4_audit.json").write_text(json.dumps(out,indent=2,sort_keys=True)+"\n")
print("GENERALIST4_AUDIT "+json.dumps({k:v for k,v in out.items() if k!="feedback"},sort_keys=True),flush=True)
print("GENERALIST4_AUDIT_PASS original_sha=true paired=true",flush=True)
