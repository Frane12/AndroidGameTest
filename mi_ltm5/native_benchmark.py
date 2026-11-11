#!/usr/bin/env python3
"""Matched A36 CDCL baseline vs source-certified LTM5 graph reduction.

One logical CPU, same source SHA, E2E includes Python graph preparation.
Original SAT witness verification; UNSAT never independently certified.
"""
import hashlib,json,pathlib,resource,subprocess,time,sys
sys.path.insert(0,"research")
import drnas_atlas_wide500 as W
import drnas_atlas21_official as Verify
from mi_ltm5.cdcl_bridge import write_derived
ROOT=pathlib.Path("ltm5_native_results");ROOT.mkdir(exist_ok=True)
CAP=8.0
FAMILIES=("uf250-1065","uuf250-1065","flat200-479")
def run(p,sha,arm,rep):
 assert hashlib.sha256(p.read_bytes()).hexdigest()==sha
 start=time.monotonic()
 cnf=p;st={}
 if arm=="LTM5":
  cnf=ROOT/(sha+f"_{rep}.ltm5.cnf")
  st=write_derived(p,cnf)
 left=CAP-(time.monotonic()-start)
 if left<=0:return dict(status="UNKNOWN",e2e_s=CAP,telemetry=st)
 def limits():
  resource.setrlimit(resource.RLIMIT_CPU,(int(CAP)+2,int(CAP)+3))
  resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
 cmd=["mre_atlas23/bin/drnas_ltm5",str(cnf),"--mode","A36_75",
      "--time",str(left),"--seed",str(rep+1),"--policy","1.0,0.85"]
 try:
  p0=subprocess.run(cmd,capture_output=True,text=True,timeout=left,preexec_fn=limits)
  rc,out=p0.returncode,p0.stdout
 except subprocess.TimeoutExpired:rc,out=124,""
 if rc not in (10,20,124):raise RuntimeError(("native failed",rc,out[-200:]))
 if rc==10 and not Verify.model_ok(p,out):raise RuntimeError("INVALID ORIGINAL SAT WITNESS")
 status="SAT_VERIFIED" if rc==10 else "UNSAT_UNVERIFIED" if rc==20 else "UNKNOWN"
 metrics={}
 for line in out.splitlines():
  if line.startswith("ATLAS13_TRIAL "):
   metrics=dict(x.split("=",1) for x in line.split()[1:] if "=" in x)
 elapsed=round(time.monotonic()-start,6)
 return dict(status=status,e2e_s=elapsed,telemetry=st,
             conflicts=int(float(metrics.get("conflicts",0))),
             decisions=int(float(metrics.get("decisions",0))),
             watch_visits=int(float(metrics.get("watch_visits",0))),
             maxrss_kb=int(float(metrics.get("atlas16_maxrss_kb",0))))
corpus=W.source_corpus(limit=4)
rows=[]
for family in FAMILIES:
 for index in (0,1,2,3):
  n,clauses,sha,entry=corpus[family][index]
  raw=W.canonical(n,clauses);assert hashlib.sha256(raw).hexdigest()==sha
  p=ROOT/(sha+".cnf");p.write_bytes(raw)
  for rep in range(2):
   pair=[]
   for arm in ("BASE","LTM5"):
    r=run(p,sha,arm,rep)
    status=r.pop("status")
    row=dict(family=family,index=index,sha256=sha,rep=rep,arm=arm,
             status=status,original_SAT_verified=status=="SAT_VERIFIED",
             independent_UNSAT_verified=False,
             PAR2_reported_s=r["e2e_s"] if status!="UNKNOWN" else 2*CAP,
             PAR2_verified_s=r["e2e_s"] if status=="SAT_VERIFIED" else 2*CAP,**r)
    rows.append(row);pair.append(status)
    print("LTM5_NATIVE_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
   assert not ({"SAT_VERIFIED","UNSAT_UNVERIFIED"}<=set(pair))
summary={}
for arm in ("BASE","LTM5"):
 rr=[r for r in rows if r["arm"]==arm]
 summary[arm]=dict(trials=len(rr),SAT_verified=sum(r["status"]=="SAT_VERIFIED" for r in rr),
 UNSAT_unverified=sum(r["status"]=="UNSAT_UNVERIFIED" for r in rr),
 PAR2_reported_s=round(sum(r["PAR2_reported_s"] for r in rr),5),
 PAR2_verified_s=round(sum(r["PAR2_verified_s"] for r in rr),5),
 E2E_s=round(sum(r["e2e_s"] for r in rr),5),
 conflicts=sum(r["conflicts"] for r in rr),watch_visits=sum(r["watch_visits"] for r in rr),
 maxrss_kb=max(r["maxrss_kb"] for r in rr),
 added_clauses=sum(r["telemetry"].get("added",0) for r in rr))
summary["speedup_reported"]=round(summary["BASE"]["PAR2_reported_s"]/summary["LTM5"]["PAR2_reported_s"],5)
(ROOT/"results.json").write_text(json.dumps(dict(rows=rows,summary=summary),indent=2))
print("LTM5_NATIVE_FINAL "+json.dumps(summary,sort_keys=True),flush=True)
print("LTM5_NATIVE_AUDIT_PASS paired=true source_SHA=true original_SAT_verified=true UNSAT_certified=false one_cpu=true native_CDCL_input=true live_trail_callback=false",flush=True)
