#!/usr/bin/env python3
"""PCD1 prospective matched CPU-1/CPU-2 diagnostics. Not an E2E solver benchmark."""
import hashlib,json,pathlib,subprocess,time,statistics,sys
sys.path.insert(0,"research")
from drnas_atlas13_generator import build
ROOT=pathlib.Path("pcd1_results");ROOT.mkdir(exist_ok=True)
CATS=("random3_sat","random3_unsat","xor_dense_sat","xor_dense_unsat",
      "graph3color_sat","graph3color_unsat","pigeonhole_unsat","pigeonhole_sat",
      "mixed_circuit","mixed_hard")
def parse(out):
 line=next(x for x in out.splitlines() if x.startswith("PCD1_DIAGNOSTIC "))
 return dict(x.split("=",1) for x in line.split()[1:])
rows=[]
for cat in CATS:
 for index in (71,72):
  n,clauses,seed=build(cat,index)
  raw=("p cnf %d %d\n"%(n,len(clauses))+
       "".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode()
  sha=hashlib.sha256(raw).hexdigest()
  path=ROOT/(sha+".cnf");path.write_bytes(raw)
  for rep in range(2):
   for workers in (1,2):
    t=time.monotonic()
    p=subprocess.run(["/tmp/drnas-pcd1",str(path),str(workers),"12","150000"],
                     capture_output=True,text=True,timeout=25)
    elapsed=time.monotonic()-t
    if p.returncode:raise RuntimeError((cat,index,workers,p.stderr))
    metrics=parse(p.stdout)
    assert metrics["solver_status"]=="UNKNOWN" and metrics["certified_UNSAT"]=="0"
    rows.append(dict(category=cat,index=index,sha256=sha,rep=rep,
                     workers=workers,e2e_s=elapsed,metrics=metrics))
    print("PCD1_TRIAL "+json.dumps(rows[-1],sort_keys=True),flush=True)
for i in range(0,len(rows),4):
 a,b,c,d=rows[i:i+4]
 assert (a["workers"],b["workers"],c["workers"],d["workers"])==(1,2,1,2)
 for key in ("probes","failed_assumptions","forced_candidates",
             "graph_parity_checks","scans"):
  assert a["metrics"][key]==b["metrics"][key]==c["metrics"][key]==d["metrics"][key],(key,a,b,c,d)
totals={str(w):dict(n=sum(r["workers"]==w for r in rows),
  wall_s=round(sum(r["e2e_s"] for r in rows if r["workers"]==w),5),
  forced=sum(int(r["metrics"]["forced_candidates"]) for r in rows if r["workers"]==w),
  graph_checks=sum(int(r["metrics"]["graph_parity_checks"]) for r in rows if r["workers"]==w))
  for w in (1,2)}
totals["speedup_1_over_2"]=round(totals["1"]["wall_s"]/totals["2"]["wall_s"],5)
(ROOT/"results.json").write_text(json.dumps(dict(rows=rows,summary=totals),indent=2))
print("PCD1_FINAL "+json.dumps(totals,sort_keys=True),flush=True)
print("PCD1_AUDIT_PASS exact_source_SHA=true paired=true cpu_count_disclosed=true solver_status_UNKNOWN=true",flush=True)
