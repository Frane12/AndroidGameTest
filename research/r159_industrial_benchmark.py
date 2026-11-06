#!/usr/bin/env python3
"""R154 blinded original CNF transfer of frozen unchanged R153 on fresh SAT 2026
paired with frozen original R28, Kissat, CaDiCaL.
Prospectively SHA-excluded by original source manifest before solver timing.
Every successful SAT witness is checked on original CNF. Every R153 XOR
UNSAT subset proof is independently replayed including source unit clauses.
"""
from __future__ import annotations
import argparse,csv,hashlib,importlib.util,json,os,pathlib,random,re,statistics,subprocess,sys,time
from collections import Counter,defaultdict
ROOT=pathlib.Path("r159");ROOT.mkdir(exist_ok=True)
spec=importlib.util.spec_from_file_location("r115_source","research/r115_world_top_rematch.py")
orig=importlib.util.module_from_spec(spec);spec.loader.exec_module(orig)
PROTO="DRNAS-R158-INDUSTRIAL-SOURCE-FREEZE-PILOT-20261106-v1"
CAP=15.0;SHARDS=8;MODES=("r28","r153","r159","kissat","cadical")
BINARIES={"r28":ROOT/"r28","r153":ROOT/"r153","r159":ROOT/"r159","kissat":pathlib.Path("built/bin/kissat_4_0_4"),"cadical":pathlib.Path("built/bin/cadical_3_0_1")}
def need(ok,msg):
 if not ok:raise RuntimeError("R159_AUDIT_FAIL "+str(msg))
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(pathlib.Path(p).read_text())
def write(p,data):pathlib.Path(p).write_text(json.dumps(data,sort_keys=True,indent=2)+"\n")
def manifest():
 m=read(ROOT/"frozen/manifest.json")
 need(m["protocol"]==PROTO,"unexpected R154 frozen source protocol")
 need(len(m["cases"])>=8 and len({c["sha256"] for c in m["cases"]})==len(m["cases"]),"new SHA-disjoint source list")
 need(sum(m["cohort_counts"].values())==len(m["cases"]),"frozen family source counts")
 for c in m["cases"]:
  p=ROOT/"frozen"/(c["id"]+".cnf")
  need(sha(p)==c["sha256"],"source content SHA "+c["id"])
 return m
def replay_xor_unsat(cnf,stdout):
 # Reconstruct every unit clause and every complete XOR clause block from
 # the ORIGINAL CNF; never trust R153 annotations without replay.
 n,clauses=orig.parse_clauses(cnf)
 literals={c[0] for c in clauses if len(c)==1}
 groups=defaultdict(set)
 for cl in clauses:
  if len(cl)<2 or len(cl)>6 or len({abs(x) for x in cl})!=len(cl):continue
  lits=sorted(cl,key=lambda x:abs(x))
  vs=tuple(abs(x) for x in lits)
  groups[vs].add(sum(1<<i for i,x in enumerate(lits) if x<0))
 eq={}
 s=stdout.decode(errors="replace")
 for line in s.splitlines():
  m=re.fullmatch(r"c R28_EQ id=(\d+) rhs=([01]) vars=([\d,]+)",line)
  if not m:continue
  idx=int(m[1]);rhs=int(m[2]);vs=tuple(map(int,m[3].split(",")))
  need(idx not in eq and bool(vs) and len(set(vs))==len(vs) and all(0<x<=n for x in vs),"bad source equation")
  if len(vs)==1:
   need((vs[0] if rhs else -vs[0]) in literals,"unproven unit equation")
  else:
   need(2<=len(vs)<=6 and vs==tuple(sorted(vs)),"bad parity equation order")
   expected={mask for mask in range(1<<len(vs)) if mask.bit_count()%2==1-rhs}
   need(expected<=groups[vs],"unsupported complete parity equation")
  eq[idx]=(rhs,vs)
 cert=re.search(r"^c R28_UNSAT_CERT ids=([\d,]*)$",s,re.M)
 need(cert and "c R28_ROUTE certified_xor_contradiction" in s,"no R153 GF2 UNSAT trace")
 ids=[int(x) for x in cert[1].split(",") if x]
 need(ids and len(ids)==len(set(ids)) and all(i in eq for i in ids),"bad R153 contradiction IDs")
 rhs=0;bits=set()
 for idx in ids:
  v,vs=eq[idx];rhs^=v
  for var in vs:
   if var in bits:bits.remove(var)
   else:bits.add(var)
 need(not bits and rhs==1,"R153 independent unit/XOR contradiction not established")
 return True
def selftest():
 test_cases=[
  ("sat_with_unit",b"p cnf 2 3\n1 -2 0\n-1 2 0\n1 0\n","SAT","gf2_sat"),
  ("unsat_unit_vs_xor",b"p cnf 2 4\n1 -2 0\n-1 2 0\n1 0\n-2 0\n","UNSAT","gf2_unsat"),
  ("pure_xor",b"p cnf 2 2\n1 -2 0\n-1 2 0\n","SAT","gf2_sat"),
  ("no_xor",b"p cnf 2 2\n1 2 0\n1 0\n","SAT","fallback")
 ]
 for name,raw,status,route in test_cases:
  fn=ROOT/(name+".cnf");fn.write_bytes(raw)
  proc=subprocess.run([str(BINARIES["r153"]),str(fn),str(BINARIES["kissat"])],capture_output=True,timeout=10)
  need(proc.returncode==(10 if status=="SAT" else 20),name+" wrong answer, err="+proc.stderr[-200:].decode(errors="replace"))
  stdout=proc.stdout
  need(b"R153_DECISION_US " in stdout,name+" missing decision timer")
  if route!="fallback":
   need(("R28_ROUTE certified_pure_xor_sat" if route=="gf2_sat" else "R28_ROUTE certified_xor_contradiction").encode() in stdout,"wrong GF2 route "+name)
  else:
   need(b"R28_ROUTE fallback" in stdout,name+" no fallback")
  if status=="SAT":orig.sat_model_check(fn,stdout)
  else:replay_xor_unsat(fn,stdout)
  print("R153_SELFTEST_PASS",name,status,route,flush=True)
 # R159 must recognize complete XOR2/XOR3 source blocks, infer exact units,
 # and solve the ORIGINAL problem via pinned Kissat on sound strengthened CNF.
 r159_inputs=[
  ("xor2_derived",b"p cnf 3 5\n1 -2 0\n-1 2 0\n1 0\n-2 3 0\n3 0\n",1),
  ("xor3_derived",b"p cnf 4 7\n-1 2 3 0\n1 -2 3 0\n1 2 -3 0\n-1 -2 -3 0\n1 0\n-2 0\n-3 4 0\n",1),
 ]
 for name,raw,min_derived in r159_inputs:
  fn=ROOT/(name+".cnf");fn.write_bytes(raw)
  p=subprocess.run([str(BINARIES["r159"]),str(fn),str(BINARIES["kissat"])],capture_output=True,timeout=10)
  need(p.returncode==10,name+" status "+str(p.returncode)+" stderr="+p.stderr[-160:].decode(errors="replace"))
  mt=re.search(rb"c R159_PREP route=derived_units .+ derived=([0-9]+)",p.stdout)
  need(mt is not None and int(mt[1])>=min_derived,name+" XOR propagation missing")
  orig.sat_model_check(fn,p.stdout)
  print("R159_SELFTEST_PASS",name,"derived",mt[1].decode(),flush=True)
def trial(c,mode,rep):
 cnf=ROOT/"frozen"/(c["id"]+".cnf")
 need(sha(cnf)==c["sha256"],"R152 SHA changed")
 argv=[str(BINARIES[mode]),str(cnf)]
 if mode in ("r28","r153","r159"):argv.append(str(BINARIES["kissat"]))
 t0=time.perf_counter()
 result="TIMEOUT";proof="timeout";route="timeout";detector_us=None;seconds=CAP
 try:
  p=subprocess.run(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=CAP)
  seconds=min(CAP,time.perf_counter()-t0)
  need(p.returncode in (10,20),f"solver {mode} abnormal exit {p.returncode}: "+p.stderr[-300:].decode(errors="replace"))
  result="SAT" if p.returncode==10 else "UNSAT"
  payload=p.stdout
  if mode in ("r28","r153"):
   route="gf2_sat" if b"R28_ROUTE certified_pure_xor_sat" in payload else "gf2_unsat" if b"R28_ROUTE certified_xor_contradiction" in payload else "fallback"
  elif mode=="r159":
   mt=re.search(rb"c R159_PREP route=([a-z_]+) clauses=[0-9]+ patterns=[0-9]+ equations=[0-9]+ original_units=[0-9]+ derived=([0-9]+) decision_us=([0-9]+)",payload)
   need(mt is not None,"missing R159 XOR detector trace")
   route="r159_"+mt[1].decode()
   detector_us=int(mt[3])
  else:route=mode
  if mode=="r153":
   mt=re.search(rb"c R153_DECISION_US ([0-9]+) outcome=([a-z_]+)",payload)
   need(mt is not None,"missing R153 timing event")
   detector_us=int(mt[1])
  if result=="SAT":
   orig.sat_model_check(cnf,payload)
   proof="original_CNF_SAT_model_checked"
  elif route=="gf2_unsat":
   replay_xor_unsat(cnf,payload)
   proof="independently_replayed_original_XOR_unit_UNSAT"
  else:proof="UNSAT_without_independent_LRAT"
  # 2025/26 GBD instances have no common cross-year official score CSV.
  # Rely on independently checked original SAT witnesses / GF2 UNSAT source
  # contradictions; do not treat GBD metadata as an independent proof.
  official=(c.get("official") or {}).get("best_verified")
  if official:
   need(official["status"].startswith(result.lower()),"official verified SAT/UNSAT mismatch")
 except subprocess.TimeoutExpired:
  result="TIMEOUT";seconds=CAP;route="timeout";proof="timeout"
 return dict(id=c["id"],cohort=c["cohort"],family=c["family"],sha256=c["sha256"],
             mode=mode,repeat=rep,status=result,seconds=round(seconds,6),
             par2=round(2*CAP if result=="TIMEOUT" else seconds,6),
             route=route,proof=proof,detector_us=detector_us)
def shard(i):
 need(0<=i<SHARDS,"shard id")
 m=manifest()
 if hasattr(os,"sched_getaffinity"):os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 selftest()
 rows=[]
 for index,c in enumerate(m["cases"]):
  if index%SHARDS!=i:continue
  for rep in range(2):
   order=list(MODES);random.Random(PROTO+c["sha256"]+str(rep)).shuffle(order)
   for mode in order:
    row=trial(c,mode,rep)
    rows.append(row)
    write(ROOT/f"shard-{i}.json",rows)
    print("R159_PAIRED",json.dumps(row,sort_keys=True),flush=True)
 need(len(rows)==sum(2*len(MODES) for j,_ in enumerate(m["cases"]) if j%SHARDS==i),"incomplete shard")
 print("R159_SHARD_PASS",i,len(rows),flush=True)
def summary(rows,cases):
 out={}
 for cohort in ["all","xor_plus_units","complete_xor","mixed_residual","nonxor_control"]:
  z=[r for r in rows if cohort=="all" or r["cohort"]==cohort]
  out[cohort]={}
  for mode in MODES:
   k=[r for r in z if r["mode"]==mode]
   out[cohort][mode]=dict(trials=len(k),solved=sum(r["status"]!="TIMEOUT" for r in k),
     timeouts=sum(r["status"]=="TIMEOUT" for r in k),
     par2_s=round(sum(r["par2"] for r in k),6),
     decision_us_p50=round(statistics.median([r["detector_us"] for r in k if r["detector_us"] is not None]),3) if mode in ("r153","r159") and any(r["detector_us"] is not None for r in k) else None,
     routes=dict(Counter(r["route"] for r in k)))
  q=out[cohort]
  base=q["kissat"]["par2_s"]
  q["r153"]["gain_vs_kissat_pct"]=round(100*(base-q["r153"]["par2_s"])/base,4) if base else None
  base=q["r28"]["par2_s"]
  q["r153"]["gain_vs_r28_pct"]=round(100*(base-q["r153"]["par2_s"])/base,4) if base else None
  base=q["kissat"]["par2_s"]
  q["r159"]["gain_vs_kissat_pct"]=round(100*(base-q["r159"]["par2_s"])/base,4) if base else None
  base=q["r153"]["par2_s"]
  q["r159"]["gain_vs_r153_pct"]=round(100*(base-q["r159"]["par2_s"])/base,4) if base else None
 return out
def audit():
 m=manifest();rows=[];pairs=set();pins=set();commits=set();cpus=set()
 for i in range(SHARDS):
  p=ROOT/f"shard-{i}.json"
  need(p.exists(),"missing completed shard "+str(i))
  block=read(p)
  need(len(block)==sum(2*len(MODES) for j,_ in enumerate(m["cases"]) if j%SHARDS==i),"shard short "+str(i))
  pin=read(ROOT/f"pin-{i}.json")
  pins.add(json.dumps(pin["binaries"],sort_keys=True));commits.add(pin["commit"]);cpus.add(pin["cpu"])
  for row in block:
   c=next((x for x in m["cases"] if x["id"]==row["id"]),None)
   need(c is not None and row["sha256"]==c["sha256"],"formula mismatch")
   key=(row["id"],row["repeat"],row["mode"])
   need(key not in pairs,"duplicate measure")
   pairs.add(key)
   need(row["repeat"] in (0,1) and row["mode"] in MODES,"bad key")
   need(abs(row["par2"]-(2*CAP if row["status"]=="TIMEOUT" else row["seconds"]))<1e-5,"wrong PAR2")
   if row["status"]=="SAT":need(row["proof"]=="original_CNF_SAT_model_checked","unvalidated SAT witness")
   if row["route"]=="gf2_unsat":
    need(row["proof"]=="independently_replayed_original_XOR_unit_UNSAT","unvalidated proof")
  rows.extend(block)
 need(len(rows)==len(m["cases"])*2*len(MODES),"wrong trial total")
 need(len(pins)==len(commits)==1,"solver binary/commit drift across shards")
 groups=defaultdict(list)
 for row in rows:groups[row["id"]].append(row)
 need(all(len(groups[x["id"]])==2*len(MODES) for x in m["cases"]),"not complete 5-mode formula pairs")
 for id,g in groups.items():
  need(len({x["status"] for x in g if x["status"]!="TIMEOUT"})<=1,"status mismatch "+id)
 s=summary(rows,m["cases"])
 per=[]
 for c in m["cases"]:
  r=groups[c["id"]]
  per.append(dict(id=c["id"],sha256=c["sha256"],cohort=c["cohort"],family=c["family"],
    original_structural_signature=c["structural"],by_mode={mode:dict(
     par2_s=round(sum(x["par2"] for x in r if x["mode"]==mode),6),
     solved=sum(x["status"]!="TIMEOUT" for x in r if x["mode"]==mode),
     route=dict(Counter(x["route"] for x in r if x["mode"]==mode))) for mode in MODES}))
 # Formula-level bootstrap as diagnostic only, not claim of independent testing.
 random.seed(153)
 a=[dict((mode,sum(x["par2"] for x in groups[c["id"]] if x["mode"]==mode)) for mode in MODES) for c in m["cases"]]
 boot=[]
 for target in ("r153","r159"):
  for comp in ("kissat","r28","r153"):
   if target==comp:continue
   v=[]
   for _ in range(3000):
    pick=[a[random.randrange(len(a))] for __ in a]
    denom=sum(x[comp] for x in pick)
    v.append(100*(denom-sum(x[target] for x in pick))/denom)
   v.sort();boot.append(dict(target=target,comparator=comp,pct_95=[round(v[75],3),round(v[2924],3)]))
 report=dict(protocol="DRNAS-R159-DEVELOPMENT-INDUSTRIAL-XOR-20261106-v1",frozen_source_protocol=PROTO,status="AUDIT_PASS",source_run_id="same_workflow_precommitted_freeze",
  development_cohort_reuses_R158_20_originals=True,not_independent_holdout=True,
  formulas=len(m["cases"]),attempts=len(rows),cap_s=CAP,par2_timeout_penalty_s=2*CAP,
  raw_source_SHA256=list(c["sha256"] for c in m["cases"]),
  source_manifest_sha256=sha(ROOT/"frozen/manifest.json"),binary_pins=json.loads(next(iter(pins))),
  commit=list(commits)[0],cpu_models=sorted(cpus),
  solver_correctness="SAT witness original CNF checked; R153 GF2 UNSAT source subset proof independently replayed",
  disclaimer="SEEN R158 development cohort; this is not independent unseen validation. SAT witnesses are source-checked, GF2 UNSAT independently replayed, and fallback UNSAT lacks independent LRAT.",
  cohorts=s,per_formula=per,bootstrap_95_pct=boot)
 write(ROOT/"report.json",report)
 with (ROOT/"paired.csv").open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 print("R159_FINAL",json.dumps({"cohorts":s,"bootstrap":boot,"attempts":len(rows)},sort_keys=True),flush=True)
if __name__=="__main__":
 p=argparse.ArgumentParser();p.add_argument("action",choices=("shard","audit"));p.add_argument("--shard",type=int,default=0)
 a=p.parse_args()
 {"shard":lambda:shard(a.shard),"audit":audit}[a.action]()
