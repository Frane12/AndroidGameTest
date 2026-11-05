#!/usr/bin/env python3
"""R156 DEVELOPMENT: paired native residual-aware XOR/CDCL vs unchanged R155/R153.

Use 4 original R154 mixed-residual formulas, 4 known full XOR/unit
controls, and 2 non-XOR controls. The entire set is a pre-exposed
development diagnostic, NOT a new blind independent benchmark.
Preserve R155/R156 stdout after timeout to reveal activation that
R155's older audit falsely recorded as zero. All added constraints are
independently proved in the original source GF(2) span, including
Tseitin-encoded 5..12-variable equations, before accepting results.
"""
import argparse,collections,hashlib,json,os,pathlib,random,re,statistics,subprocess,time
import sys
sys.path.insert(0,str(pathlib.Path("research").resolve()))
import r155_mixed_benchmark as old
from collections import defaultdict
ROOT=pathlib.Path("r156");FROZEN=ROOT/"frozen"
old.ROOT=ROOT;old.INPUT=FROZEN;old.old.ROOT=ROOT
PROTO="DRNAS-R156-RESIDUAL-COUPLED-MIXED-GF2-DEV-20261105-v1"
SHARDS=4;REPS=2;CAP=15.
MODES=("r156","r155","r153","kissat","cryptominisat")
BIN={"r156":ROOT/"r156","r155":ROOT/"r155","r153":ROOT/"r153",
     "kissat":pathlib.Path("built/bin/kissat_4_0_4"),
     "cryptominisat":pathlib.Path("/usr/bin/cryptominisat5")}
def need(cond,msg):
 if not cond:raise RuntimeError("R156_AUDIT_REFUSED "+str(msg))
def h(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def rd(p):return json.loads(pathlib.Path(p).read_text())
def wr(p,d):
 p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(d,sort_keys=True,indent=2)+"\n")
def cases():
 allcases,manifest=old.cases()
 selected=[]
 for cohort,limit in (("mixed_residual",4),("complete_xor",2),("xor_plus_units",2),("nonxor_control",2)):
  a=sorted((x for x in allcases if x["cohort"]==cohort),key=lambda x:x["id"])
  need(len(a)>=limit,"missing frozen cases cohort "+cohort)
  selected.extend(a[:limit])
 need(len(selected)==10 and len({x["sha256"] for x in selected})==10,"frozen source selection")
 for x in selected:
  need(h(FROZEN/(x["id"]+".cnf"))==x["sha256"],"original source SHA "+x["id"])
 return selected,manifest
def source_equations(cnf):
 n,clauses=old.old.orig.parse_clauses(cnf)
 groups=collections.defaultdict(set);eq=[]
 for c in clauses:
  if len(c)==1:eq.append(((abs(c[0]),),int(c[0]>0)))
  if len(c)<2 or len(c)>6 or len(set(map(abs,c)))!=len(c):continue
  lits=sorted(c,key=abs)
  key=tuple(abs(x) for x in lits)
  groups[key].add(sum(1<<i for i,x in enumerate(lits) if x<0))
 for vs,masks in groups.items():
  k=len(vs)
  if {m for m in range(1<<k) if m.bit_count()%2==0}<=masks:eq.append((vs,1))
  if {m for m in range(1<<k) if m.bit_count()%2==1}<=masks:eq.append((vs,0))
 return n,clauses,eq
def certify_r156(cnf,stdout):
 s=stdout.decode(errors="replace")
 # Prove exact R156 rows using ONLY source complete XOR blocks + original units.
 found=re.findall(r"^c R156_ROUTE augmented_gf2_residual selected=(\d+) added_clauses=(\d+) auxiliary_vars=(\d+) original_clauses=(\d+) detector_us=(\d+)$",s,re.M)
 rows=re.findall(r"^c R156_DERIVED_EQ rhs=([01]) vars=([\d,]+)$",s,re.M)
 if not found:
  need(not rows,"derived R156 rows without executable marker")
  return dict(activated=False,rows=0,aux=0,clauses=0,detector_us=None)
 need(len(found)==1 and rows,"invalid duplicated/missing R156 route")
 n,clauses,source=source_equations(cnf)
 need(bool(source),"no source XOR proof")
 basis={}
 for vs,rhs in source:
  val=(sum(1<<(v-1) for v in vs)|((rhs&1)<<n))
  while val:
   p=val.bit_length()-1
   if p not in basis:basis[p]=val;break
   val^=basis[p]
 seen=set();added=0;aux=0
 for rs,vs_s in rows:
  rhs=int(rs);vs=tuple(map(int,vs_s.split(",")))
  need(1<=len(vs)<=12 and tuple(sorted(set(vs)))==vs and all(1<=v<=n for v in vs),"bad GF2 row variables")
  need((vs,rhs) not in seen,"duplicate derived parity")
  seen.add((vs,rhs))
  val=sum(1<<(v-1) for v in vs)|(rhs<<n)
  while val:
   p=val.bit_length()-1
   need(p in basis,"R156 parity NOT implied by original source XOR GF2 system")
   val^=basis[p]
  k=len(vs)
  added+=(1<<(k-1)) if k<=4 else 4*(k-2)+2
  aux+=max(0,k-2) if k>=5 else 0
 selected,cls,ex,src_count,us=map(int,found[0])
 need(len(rows)==selected and cls==added and ex==aux and src_count==len(clauses),"R156 equation/Tseitin budgets not consistent")
 need(len(rows)<=48 and added<=384 and aux<=120,"R156 budget exceeded")
 return dict(activated=True,rows=len(rows),aux=aux,clauses=added,detector_us=us)
def original_sat_check(cnf,stdout):
 # R156 includes existential Tseitin variables >n. They are NOT part of
 # the original formula and must be omitted when checking source witness.
 n,_=old.old.orig.parse_clauses(cnf)
 lines=[]
 for line in stdout.decode(errors="replace").splitlines():
  if line.startswith("v "):
   vs=[int(x) for x in line[2:].split() if int(x)!=0 and abs(int(x))<=n]
   if vs:lines.append("v "+" ".join(map(str,vs))+" 0")
 old.old.orig.sat_model_check(cnf,("\n".join(lines)+"\n").encode())
def route_from_stdout(mode,out):
 s=out.decode(errors="replace")
 if mode=="r156":
  if "c R156_ROUTE augmented_gf2_residual " in s:return "augmented_gf2_residual"
  if "c R28_ROUTE certified_" in s:return "gf2"
  if "c R28_ROUTE fallback " in s:return "fallback"
 if mode=="r155":
  if "c R155_ROUTE augmented_gf2_short " in s:return "augmented_gf2_short"
  if "c R28_ROUTE certified_" in s:return "gf2"
  if "c R28_ROUTE fallback " in s:return "fallback"
 if mode=="r153":
  if "c R28_ROUTE certified_" in s:return "gf2"
  if "c R28_ROUTE fallback " in s:return "fallback"
 return mode
def runtrial(c,mode,rep):
 fn=FROZEN/(c["id"]+".cnf")
 need(h(fn)==c["sha256"],"original CNF mutated")
 cmd=[str(BIN[mode]),str(fn)]
 if mode in ("r156","r155","r153"):cmd.append(str(BIN["kissat"]))
 t=time.perf_counter();stdout=b"";status="TIMEOUT";elapsed=CAP;returncode=None
 try:
  result=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=CAP)
  stdout=result.stdout;returncode=result.returncode
  elapsed=min(CAP,time.perf_counter()-t)
  need(returncode in (10,20),f"native solver failed mode={mode} exit={returncode} stderr={result.stderr[-200:]}")
  status="SAT" if returncode==10 else "UNSAT"
 except subprocess.TimeoutExpired as e:
  # This is the major R155 audit bug fix: TimeoutExpired.stdout retains the
  # already flushed *preprocessing metadata*. It must never be discarded.
  stdout=e.stdout or b""
 route=route_from_stdout(mode,stdout)
 proof="timeout" if status=="TIMEOUT" else "UNSAT_no_independent_LRAT"
 r156proof=certify_r156(fn,stdout) if mode=="r156" else dict(activated=False,rows=0,aux=0,clauses=0,detector_us=None)
 if mode=="r155" and route=="augmented_gf2_short":
  old.implied_short_proofs(fn,stdout)
 if status=="SAT":
  original_sat_check(fn,stdout);proof="original_CNF_SAT_witness_verified"
 elif status=="UNSAT" and route=="gf2":
  old.old.replay_xor_unsat(fn,stdout)
  proof="independent_source_GF2_UNSAT"
 elif status=="UNSAT" and route=="augmented_gf2_residual":
  need(r156proof["activated"],"uncertified R156 source consequence")
  proof="source_GF2_entailed_encoding_NO_INDEPENDENT_LRAT"
 elif status=="UNSAT" and route=="augmented_gf2_short":
  proof="source_GF2_entailed_encoding_NO_INDEPENDENT_LRAT"
 return dict(id=c["id"],sha256=c["sha256"],cohort=c["cohort"],family=c["family"],
             mode=mode,rep=rep,status=status,seconds=round(elapsed,6),
             par2=round(2*CAP if status=="TIMEOUT" else elapsed,6),
             route=route,proof=proof,activated=r156proof["activated"],
             eq_count=r156proof["rows"],aux=r156proof["aux"],
             appended_clauses=r156proof["clauses"],decision_us=r156proof["detector_us"],
             timeout_metadata_recovered=bool(status=="TIMEOUT" and route in ("augmented_gf2_residual","augmented_gf2_short")))
def selftest():
 cs,_=cases()
 need(all(pathlib.Path(x).is_file() for x in BIN.values()),"missing solver executable")
 for c in cs:
  if c["cohort"]!="mixed_residual":continue
  p=FROZEN/(c["id"]+".cnf")
  proc=subprocess.run([str(BIN["r156"]),str(p),"/bin/true"],capture_output=True,timeout=10)
  need(proc.returncode==0,"R156 /bin/true exact source probe failed")
  proof=certify_r156(p,proc.stdout)
  need(proof["activated"],"R156 residual CNF not reached on "+c["id"])
  print("R156_SOURCE_PROOF_PASS",c["id"],json.dumps(proof,sort_keys=True),flush=True)
def shard(idx):
 need(idx in range(SHARDS),"bad shard")
 cs,m=cases()
 if hasattr(os,"sched_getaffinity"):os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 selftest()
 rows=[]
 for j,c in enumerate(cs):
  if j%SHARDS!=idx:continue
  for rep in range(REPS):
   order=list(MODES);random.Random(PROTO+c["sha256"]+str(rep)).shuffle(order)
   for mode in order:
    row=runtrial(c,mode,rep)
    rows.append(row);wr(ROOT/f"shard-{idx}.json",rows)
    print("R156_TRIAL",json.dumps(row,sort_keys=True),flush=True)
 need(len(rows)==sum(REPS*len(MODES) for j in range(len(cs)) if j%SHARDS==idx),"short shard")
 print("R156_SHARD_PASS",idx,len(rows),flush=True)
def audit():
 cs,m=cases();rows=[];pins=set();commits=set();cpus=set();keys=set()
 for shard in range(SHARDS):
  block=rd(ROOT/f"shard-{shard}.json")
  expect=sum(REPS*len(MODES) for j in range(len(cs)) if j%SHARDS==shard)
  need(len(block)==expect,f"shard {shard} missing")
  pin=rd(ROOT/f"pin-{shard}.json")
  pins.add(json.dumps(pin["binaries"],sort_keys=True));commits.add(pin["commit"]);cpus.add(pin["cpu"])
  for row in block:
   c=next((z for z in cs if z["id"]==row["id"]),None)
   need(c and row["sha256"]==c["sha256"],"source drift")
   key=(row["id"],row["rep"],row["mode"])
   need(key not in keys,"duplicate paired trial");keys.add(key)
   need(abs(row["par2"]-(2*CAP if row["status"]=="TIMEOUT" else row["seconds"]))<1e-5,"bad PAR2")
   need(row["status"]!="SAT" or row["proof"]=="original_CNF_SAT_witness_verified","missing source SAT model")
  rows.extend(block)
 need(len(rows)==len(cs)*REPS*len(MODES),"missing total trials")
 need(len(pins)==len(commits)==1,"pin/commit drift")
 by=defaultdict(list)
 for row in rows:by[row["id"]].append(row)
 for c in cs:
  z=by[c["id"]]
  need(len(z)==REPS*len(MODES),"incomplete formula pairing")
  need(len({r["status"] for r in z if r["status"]!="TIMEOUT"})<=1,"original source SAT/UNSAT disagreement")
 summary={};categories=sorted({c["cohort"] for c in cs})
 for category in ["all"]+categories:
  z=[x for x in rows if category=="all" or x["cohort"]==category]
  summary[category]={}
  for mode in MODES:
   q=[x for x in z if x["mode"]==mode]
   summary[category][mode]=dict(attempts=len(q),solved=sum(x["status"]!="TIMEOUT" for x in q),
      par2_s=round(sum(x["par2"] for x in q),6),
      activated=sum(x["route"] in ("augmented_gf2_residual","augmented_gf2_short") for x in q),
      completed_augmented=sum(x["route"] in ("augmented_gf2_residual","augmented_gf2_short") and x["status"]!="TIMEOUT" for x in q),
      timeout_activation_recovered=sum(x["timeout_metadata_recovered"] for x in q),
      median_decision_us=statistics.median([x["decision_us"] for x in q if x["decision_us"] is not None]) if any(x["decision_us"] is not None for x in q) else None)
 print("R156_SUMMARY",json.dumps(summary,sort_keys=True),flush=True)
 summary["all"]["r156"]["PAR2_gain_vs_r155_pct"]=round(100*(summary["all"]["r155"]["par2_s"]-summary["all"]["r156"]["par2_s"])/summary["all"]["r155"]["par2_s"],5)
 report=dict(status="AUDIT_PASS_RESEARCH_ONLY",protocol=PROTO,not_blind=True,previously_seen_source_run=42107642696,
  source_orig_count=len(cs),attempts=len(rows),repetitions=REPS,cap_s=CAP,par2_timeout=2*CAP,
  original_manifest_sha256=h(FROZEN/"manifest.json"),binary_pins=json.loads(next(iter(pins))),
  commit=next(iter(commits)),cpu_models=sorted(cpus),summary=summary,paired=rows,
  caveats=["R156 uses selected 10 PREVIOUSLY EXPOSED development CNFs; not a new holdout",
   "R155 timeout route metadata recovered rather than discarded",
   "R156 source GF2 entailment replayed independently, wide Tseitin rows equisatisfiable",
   "SAT output filtered for auxiliary vars and checked against original source",
   "Augmented UNSAT is not independently LRAT certified",
   "Regression/no-regression on general SAT requires larger source-disjoint external holdout"])
 wr(ROOT/"report.json",report)
 print("R156_FINAL",json.dumps({"summary":summary,"attempts":len(rows),"status":report["status"]},sort_keys=True),flush=True)
if __name__=="__main__":
 a=argparse.ArgumentParser();a.add_argument("action",choices=("shard","audit"));a.add_argument("--shard",type=int,default=0)
 x=a.parse_args()
 {"shard":lambda:shard(x.shard),"audit":audit}[x.action]()
