#!/usr/bin/env python3
import pathlib,json,collections
root=pathlib.Path("audits")
files=sorted(root.glob("ATLAS40-*/mre_atlas40/*/result_*.json"))
assert len(files)==6,("missing shard results",len(files))
arms={"A36_75","A39_PROTECT","A40_YOUNG","A40_MATURE","KISSAT","CMS"}
stats=collections.defaultdict(lambda:dict(par2=0.0,strict=0.0,solved=0,sat=0,unsat_unverified=0,trials=0,gate=0,rss_kb=0))
seen=set()
for f in files:
 d=json.loads(f.read_text());group=collections.defaultdict(dict)
 for r in d["rows"]:
  a=r["arm"]; key=(r["sha256"],r["rep"])
  assert a in arms and a not in group[key]
  group[key][a]=r
  assert r["independent_UNSAT_proof_verified"] is False
  assert r["original_SAT_witness_verified"]==(r["status"]=="SAT_VERIFIED")
  seen.add((r["cohort"],r["family"],r["index"],r["sha256"]))
  v=stats[(r["cohort"],a)]
  v["par2"]+=r["PAR2_reported_s"];v["strict"]+=r["PAR2_verified_s"]
  v["solved"]+=r["status"]!="UNKNOWN";v["sat"]+=r["status"]=="SAT_VERIFIED"
  v["unsat_unverified"]+=r["status"]=="UNSAT_UNVERIFIED"
  v["gate"]+=r["telemetry"]["atlas40_gate_pass"]
  v["rss_kb"]=max(v["rss_kb"],r["telemetry"]["atlas16_maxrss_kb"])
  v["trials"]+=1
 for key,g in group.items():
  assert set(g)==arms,("unpaired",f,key,set(g))
  st={r["status"] for r in g.values()}
  assert not ({"SAT_VERIFIED","UNSAT_UNVERIFIED"}<=st),("contradiction",key)
 assert len(group)==(10 if d["cohort"] in ("regression","hard") else 6)
 print("ATLAS40_SHARD_AUDIT "+json.dumps(dict(file=str(f),trials=len(d["rows"]),pairs=len(group))),flush=True)
assert len(seen)==26
for cohort in ("regression","extension","hard"):
 results={a:stats[(cohort,a)] for a in sorted(arms)}
 for v in results.values():
  v["par2"]=round(v["par2"],6);v["strict"]=round(v["strict"],6)
 print("ATLAS40_COHORT_AUDIT "+json.dumps(dict(cohort=cohort,arms=results),sort_keys=True),flush=True)
tot={}
for a in sorted(arms):
 v={k:(max(stats[(c,a)][k] for c in ("regression","extension","hard")) if k=="rss_kb" else sum(stats[(c,a)][k] for c in ("regression","extension","hard"))) for k in ("par2","strict","solved","sat","unsat_unverified","trials","gate","rss_kb")}
 v["par2"]=round(v["par2"],6);v["strict"]=round(v["strict"],6)
 tot[a]=v
base=tot["A36_75"]["par2"]
for v in tot.values():v["speedup_vs_A36"]=round(base/v["par2"],5)
assert all(v["trials"]==52 for v in tot.values())
print("ATLAS40_AUDIT_PASS "+json.dumps(dict(unique_SHA=len(seen),trials=312,arms=tot,blind=False,independent_UNSAT_verified=False),sort_keys=True),flush=True)
