#!/usr/bin/env python3
"""R153 decision-cost-only benchmark, unchanged 13 R152 source SHA CNFs.
No SAT solver is run. Native R28 and R153 --classify-only on the same CPU,
12 paired repetitions, randomized order, cold and warm estimates explicit.
"""
import hashlib,json,os,pathlib,random,re,statistics,subprocess,time
from collections import defaultdict
ROOT=pathlib.Path("r153decision")
M=json.loads((ROOT/"frozen/manifest.json").read_text())
assert M["protocol"]=="DRNAS-R152-NEW-LIGHTSOUT-FAMILY-XOR-20261105-v1"
assert len(M["cases"])==13
MODES=("r28","r153")
PROTO="DRNAS-R153-DECISION-COST-ONLY-13-REUSED-SHA-20261105-v1"
REPS=12
if hasattr(os,"sched_getaffinity"):os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
rows=[]
for c in M["cases"]:
 p=ROOT/"frozen"/(c["id"]+".cnf")
 assert sha(p)==c["sha256"]
 for rep in range(REPS):
  modes=list(MODES)
  random.Random(PROTO+c["sha256"]+str(rep)).shuffle(modes)
  for mode in modes:
   t0=time.perf_counter_ns()
   x=subprocess.run([str(ROOT/mode),str(p),"/bin/true","--classify-only"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=10)
   dt=(time.perf_counter_ns()-t0)/1000.
   assert x.returncode==0,(mode,c["id"],x.returncode,x.stderr[-250:])
   out=x.stdout
   route=("gf2_sat" if b"R28_ROUTE certified_pure_xor_sat" in out else
          "gf2_unsat" if b"R28_ROUTE certified_xor_contradiction" in out else
          "fallback" if b"R28_ROUTE fallback" in out else "unknown")
   assert route!="unknown",(mode,c["id"])
   native_us=None
   if mode=="r153":
    mm=re.search(rb"R153_DECISION_US ([0-9]+)",out)
    assert mm,(mode,c["id"])
    native_us=int(mm[1])
   rows.append(dict(id=c["id"],cohort=c["cohort"],sha256=c["sha256"],
                    mode=mode,rep=rep,route=route,process_wall_us=round(dt,3),
                    r153_native_decision_us=native_us))
  print("R153_DECISION_PAIR",c["id"],rep,flush=True)
grouped=defaultdict(list)
for a in rows:grouped[a["cohort"]].append(a)
grouped["all"]=rows
summary={}
for cohort,z in grouped.items():
 summary[cohort]={}
 for mode in MODES:
  t=[i["process_wall_us"] for i in z if i["mode"]==mode]
  n=[i["r153_native_decision_us"] for i in z if i["mode"]==mode and i["r153_native_decision_us"] is not None]
  summary[cohort][mode]=dict(count=len(t),median_wall_us=round(statistics.median(t),2),
    p95_wall_us=round(sorted(t)[int(.95*(len(t)-1))],2),
    native_median_us=round(statistics.median(n),2) if n else None)
 x=summary[cohort]
 x["decision_wall_improvement_pct"]=round(100*(x["r28"]["median_wall_us"]-x["r153"]["median_wall_us"])/x["r28"]["median_wall_us"],3)
by_case={}
for c in M["cases"]:
 v=[a for a in rows if a["id"]==c["id"]]
 by_case[c["id"]]={mode:dict(median_wall_us=round(statistics.median(a["process_wall_us"] for a in v if a["mode"]==mode),3),
  routes=sorted(set(a["route"] for a in v if a["mode"]==mode))) for mode in MODES}
 by_case[c["id"]]["cohort"]=c["cohort"]
result=dict(protocol=PROTO,kind="DEVELOPMENT_DECISION_COST_MICROBENCH_ONLY",reused_previous_13_sources=True,
 original_source_sha256=sha(ROOT/"frozen/manifest.json"),repetitions=REPS,attempts=len(rows),
 summary=summary,by_case=by_case,metrics="process_wall includes startup and proof output; R153 native_us starts before parser and ends before route proof output",
 source_sha_verified=True)
(ROOT/"report.json").write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
(ROOT/"raw.json").write_text(json.dumps(rows,sort_keys=True,indent=2)+"\n")
print("R153_DECISION_FINAL",json.dumps(summary,sort_keys=True),flush=True)
