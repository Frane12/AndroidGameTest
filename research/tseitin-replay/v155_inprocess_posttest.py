#!/usr/bin/env python3
"""Frozen-policy V15.5 IN-PROCESS end-to-end evaluation on 480 NEW seed CNFs.
This is a new-seed engineering replication of the generator, NOT independent
official SAT Competition material or a new research discovery.
Do not tune selector after looking at these results.
"""
import collections,hashlib,json,os,random,statistics,subprocess,time
from pathlib import Path
import v155_training as m
NEW_SEED="DRNAS-MICRO-155-INPROCESS-SEED-B-20261101"
REPS=2
SOLVERS=("kissat","v153","native")
def output(p,obj):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def native_run(case):
 cnf=Path(case).resolve()
 args=[str(Path("bin/v155_inprocess").resolve()),str(cnf),
       str(Path("bin/kissat_solver").resolve()),
       str(Path("bin/v153_unified").resolve())]
 start=time.perf_counter()
 try:
  p=subprocess.run(args,capture_output=True,text=True,timeout=m.CAP)
 except subprocess.TimeoutExpired:
  return dict(status="TIMEOUT",seconds=m.CAP,payload=None,model=[],route="timeout")
 dt=time.perf_counter()-start
 if dt>m.CAP:return dict(status="TIMEOUT",seconds=m.CAP,payload=None,model=[],route="timeout")
 lines=p.stdout.splitlines()
 route_line=[x for x in lines if x.startswith("DRNAS_V155_ROUTE\t")]
 assert len(route_line)==1,(p.stdout[:500],p.returncode)
 path=route_line[0].split("\t")[1]
 assert path in ("kissat","v153")
 tagged=[x.split("\t",1)[1] for x in lines if x.startswith("DRNAS_HYBRID_RESULT\t")]
 if tagged:
  assert p.returncode==0 and len(tagged)==1,(p.returncode,p.stderr[-250:])
  payload=json.loads(tagged[0])
  status=payload["status"]
  model=payload.get("model",[])
 else:
  assert p.returncode in (10,20),(p.returncode,p.stderr[-250:],p.stdout[-250:])
  payload=None
  status="SAT" if p.returncode==10 else "UNSAT"
  assert ("s SATISFIABLE" if status=="SAT" else "s UNSATISFIABLE") in lines
  model=[int(v) for line in lines if line.startswith("v ") for v in line.split()[1:] if v!="0"]
 return dict(status=status,seconds=round(dt,7),payload=payload,model=model,route=path)
def main():
 original=json.loads(Path("prior-dataset/manifest.json").read_text())
 frozen=json.loads(Path("policy/frozen-policy.json").read_text())
 assert original["count"]==480 and original["seed"]==m.SEED
 assert frozen["protocol"]==m.SEED and frozen["accepted"]
 assert frozen["feature_key"]=="signature"
 assert frozen["rules"] and set(frozen["rules"])=={
  "0-0-1-2-1-1-0","0-0-2-2-1-0-0","1-0-0-0-1-1-0"}
 # Never train/tune on this dataset: change only deterministic seed
 # and keep the same 20 formula families, sizes, and generator.
 m.SEED=NEW_SEED
 m.freeze("native-new-480")
 cases=json.loads(Path("native-new-480/manifest.json").read_text())["samples"]
 assert len(cases)==480
 assert not ({x["sha256"] for x in original["samples"]}&
             {x["sha256"] for x in cases}),"new generator overlaps prior 480"
 m.setup()
 # Full protocol/scheme equivalence between Python feature specification
 # and native C++ classification before looking at any runtime results.
 classifications=collections.Counter()
 for c in cases:
  cnf=Path("native-new-480")/c["relative_path"]
  args=[str(Path("bin/v155_inprocess").resolve()),str(cnf.resolve()),
        str(Path("bin/kissat_solver").resolve()),
        str(Path("bin/v153_unified").resolve()),"--classify-only"]
  check=subprocess.run(args,capture_output=True,text=True,check=True)
  ln=check.stdout.strip().split("\t")
  assert len(ln)==3 and ln[0]=="DRNAS_V155_SIGNATURE"
  expected=frozen["rules"].get(c["features"]["signature"],{}).get("solver","v153")
  assert ln[1]==c["features"]["signature"] and ln[2]==expected,(c["id"],ln,c["features"])
  classifications[expected]+=1
 print("V155_NATIVE_FEATURE_EQUIVALENCE_PASS",len(cases),dict(classifications),flush=True)
 rows=[]
 for i,c in enumerate(cases):
  path=Path("native-new-480")/c["relative_path"]
  n,clauses=m.read_clauses(path)
  assert m.features(n,clauses)==c["features"]
  for rep in range(REPS):
   order=list(SOLVERS)
   rng=random.Random(int(hashlib.sha256((NEW_SEED+c["id"]+str(rep)).encode()).hexdigest()[:16],16))
   rng.shuffle(order)
   for solver in order:
    try:
     res=native_run(path) if solver=="native" else m.invoke(solver,path)
     status=res["status"]
     assert status in (c["expected"],"TIMEOUT"),(c["id"],solver,status,c["expected"])
     if status=="SAT":m.verify_sat(n,clauses,res["model"]);check="independent_model"
     elif status=="UNSAT" and res["payload"]:
      assert m.check153(res["payload"],clauses)
      check="independent_v153_unsat_proof"
     elif status=="UNSAT":check="generator_expected"
     else:check="timeout"
     rows.append(dict(id=c["id"],family=c["family"],solver=solver,rep=rep,
                      status=status,seconds=res["seconds"],route=res["route"],check=check))
    except Exception as e:
     rows.append(dict(id=c["id"],family=c["family"],solver=solver,rep=rep,
                      status="ERROR",seconds=m.CAP,route="exception",error=str(e)[:250]))
  if i%40==39:
   output("native-progress.json",dict(complete=False,rows=rows))
   print("V155_NATIVE_PROGRESS",i+1,"/",len(cases),flush=True)
 assert len(rows)==480*2*3==2880
 assert all(x["status"]!="ERROR" for x in rows),[x for x in rows if x["status"]=="ERROR"][:3]
 vals=collections.defaultdict(list)
 for x in rows:
  vals[x["solver"],x["id"]].append(m.CAP*2 if x["status"]=="TIMEOUT" else x["seconds"])
 summary={}
 for solver in SOLVERS:
  cost=sum(statistics.median(v) for (s,_),v in vals.items() if s==solver)
  subset=[x for x in rows if x["solver"]==solver]
  summary[solver]=dict(cases=480,trials=len(subset),solved=sum(x["status"]!="TIMEOUT" for x in subset),
                       par2_sum_seconds=round(cost,7),
                       route_counts=dict(collections.Counter(x["route"] for x in subset)),
                       sat_witness_checks=sum(x["check"]=="independent_model" for x in subset),
                       v153_unsat_proof_checks=sum(x["check"]=="independent_v153_unsat_proof" for x in subset))
 for solver,stats in summary.items():print("V155_NATIVE_RESULT",solver,json.dumps(stats,sort_keys=True),flush=True)
 base=min(summary["kissat"]["par2_sum_seconds"],summary["v153"]["par2_sum_seconds"])
 gain=100*(base-summary["native"]["par2_sum_seconds"])/base
 report=dict(protocol=NEW_SEED,original_policy_protocol=frozen["protocol"],
             frozen_policy=frozen,summary=summary,selected=dict(classifications),
             gain_vs_best_single_solver_percent=round(gain,4),
             warnings=["This is a deterministic new-seed generator replication, not official SAT Competition",
                       "Native startup, structural scan and exec included in wall-clock time",
                       "Do not infer general-world performance from generated instances",
                       "All SAT models and native V15.3 UNSAT proofs independently checked"])
 output("v155-native-final.json",report)
 output("v155-native-raw.json",{"records":rows})
 print("V155_NATIVE_AUDIT_PASS",len(rows),"case_count",len(cases),"gain_pct",round(gain,4),flush=True)
if __name__=="__main__":main()
