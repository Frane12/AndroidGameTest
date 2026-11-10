#!/usr/bin/env python3
"""SRE1 proof-first 144 matched 1CPU E2E:
three real-world encodings (SAT+UNSAT each) + six original MIXAB3 SHA;
six own C++ solver modes x 2 reps, cap 6 seconds. The synthetic CNFs are
not SAT Competition instances. Original UNSAT lacks independent LRAT.
"""
from __future__ import annotations
import argparse,hashlib,json,os,pathlib,random,re,shutil,subprocess,time
ROOT=pathlib.Path("mre_sre1")
BINARY=ROOT/"bin/drnas_sre1"
CASES=ROOT/"cases"
PROTOCOL="DRNAS-SRE1-SCC-GF2-UNITS-MODEL-LIFT-144-MATCHED-1CPU-v1"
MODES=("plain","gf2","sre_graph","sre_all","sre_all_gf2","sre_placebo")
CAP=6.0;REPS=2;SHARDS=3;EXPECTED=144
LOCKED=("daa0360a834fbd9f49437d2b3fd6b372d331774100d913d55c57c0de547eb623",
"e3e6b2c71ca07f5f17491a38490b29fb63045be258ad6837bcc4530b31438162")
def fail(ok,msg):
 if not ok:raise RuntimeError("SRE1_FAIL_CLOSED "+msg)
def sha(path):return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()
def put(path,obj):
 path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def get(path):return json.loads(pathlib.Path(path).read_text())
def dimacs(n,cls):
 return ("c DRNAS SRE1 synthetic real-world SAT laboratory\np cnf %d %d\n"%(n,len(cls)))+ "".join(" ".join(map(str,c))+" 0\n" for c in cls)
def parse(path):
 n=0;cls=[]
 for line in pathlib.Path(path).read_text().splitlines():
  line=line.strip()
  if not line or line.startswith("c"):continue
  if line.startswith("p"):
   _,fmt,n,declared=line.split();n=int(n);continue
  cls.append([int(x) for x in line.split() if int(x)!=0])
 fail(len(cls)==int(declared),"DIMACS clause count mismatch")
 return n,cls
def truth(n,cls):
 fail(n<=15,"independent brute checker only for synthetic <=15 vars")
 for mask in range(1<<n):
  if all(any(bool(mask&(1<<(abs(l)-1)))==(l>0) for l in c) for c in cls):
   return "SAT"
 return "UNSAT"
def radio(impossible=False):
 cls=[]
 for v in range(5):
  a=3*v+1
  cls.extend([[a,a+1,a+2],[-a,-a-1],[-a,-a-2],[-a-1,-a-2]])
 edges=[(0,1),(0,2),(1,2),(0,3),(2,3),(0,4),(1,4),(3,4)]
 if impossible:edges.append((1,3))
 for u,v in edges:
  cls.extend([[-(u*3+k+1),-(v*3+k+1)] for k in range(3)])
 return 15,cls
def circuit(impossible=False):
 cls=[]
 def eq(a,b):cls.extend([[-a,b],[a,-b]])
 def inv(a,b):cls.extend([[a,b],[-a,-b]])
 eq(1,2);eq(2,3);inv(3,4);eq(4,5);inv(5,6)
 cls.extend([[-7,1],[-7,6],[7,-1,-6],[7]])
 if impossible:cls.append([-1])
 return 7,cls
def xor_clauses(vars,rhs):
 out=[]
 for bits in range(1<<len(vars)):
  if bits.bit_count()%2==rhs:continue
  out.append([-v if bits>>i&1 else v for i,v in enumerate(vars)])
 return out
def parity(impossible=False):
 cls=xor_clauses((1,2,3),0)+xor_clauses((1,2,4),1)
 cls+=xor_clauses((4,5,6),0)+xor_clauses((4,5,7),1)
 cls.append([3])
 if impossible:cls.append([4])
 return 7,cls
def freeze():
 ROOT.mkdir(exist_ok=True);CASES.mkdir(exist_ok=True)
 fail(BINARY.is_file(),"missing own C++ executable")
 manifest=get("mre_mixab3/manifest.json")
 r={c["sha256"]:c for c in manifest["original_cases"]}
 fail(len(r)==12 and all(x in r for x in LOCKED),"MIXAB3 original source manifest drift")
 ranked=sorted((c for c in r.values() if c["sha256"] not in LOCKED),
  key=lambda c:(pathlib.Path("mre_mixab3/cases",c["filename"]).stat().st_size,c["sha256"]))
 originals=[r[k] for k in LOCKED]+ranked[:4]
 micro=[("radio_sat",radio(False)),("radio_unsat",radio(True)),
        ("circuit_sat",circuit(False)),("circuit_unsat",circuit(True)),
        ("parity_sat",parity(False)),("parity_unsat",parity(True))]
 cases=[]
 for i in range(6):
  name,(n,cls)=micro[i]
  content=dimacs(n,cls)
  path=CASES/(name+".cnf");path.write_text(content)
  verdict=truth(n,cls)
  fail(verdict==("SAT" if name.endswith("_sat") and not name.endswith("_unsat") else "UNSAT"),
       "independent micro truth disagrees with named case")
  cases.append(dict(name=name,sha256=sha(path),filename=path.name,bytes=path.stat().st_size,
          cohort="synthetic_lab",source_family=name.split("_")[0],
          independent_exhaustive_truth=verdict))
  src=originals[i]
  spath=pathlib.Path("mre_mixab3/cases")/src["filename"]
  path=CASES/(src["sha256"]+".cnf")
  shutil.copyfile(spath,path)
  fail(sha(path)==src["sha256"],"official original source SHA differs")
  cases.append(dict(name="official_"+str(i),sha256=src["sha256"],
      filename=path.name,bytes=path.stat().st_size,cohort="seen_original_2021_2025",
      source_family="original_official",independent_exhaustive_truth=None))
 fail(len(cases)==12 and len({c["sha256"] for c in cases})==12,"cohort duplicates")
 m=dict(protocol=PROTOCOL,cases=cases,modes=list(MODES),reps=REPS,shards=SHARDS,
      cap_s=CAP,trials=EXPECTED,binary_sha256=sha(BINARY),one_cpu=True,
      known_original_not_blind=True,no_foreign_sat_solver=True,
      raw_original_UNSAT_requires_independent_LRAT=True,source_run=42811023064)
 put(ROOT/"manifest.json",m)
 verify_frozen()
 print("SRE1_FROZEN "+json.dumps(dict(total=12,original_SHA=6,
        synthetic=6,paired=EXPECTED,one_cpu=True),sort_keys=True),flush=True)
def verify_frozen():
 m=get(ROOT/"manifest.json")
 fail(m["protocol"]==PROTOCOL and m["modes"]==list(MODES) and
      m["trials"]==EXPECTED and m["cap_s"]==CAP and
      m["binary_sha256"]==sha(BINARY),"binary or experiment changed")
 for c in m["cases"]:
  p=CASES/c["filename"]
  fail(p.is_file() and sha(p)==c["sha256"] and p.stat().st_size==c["bytes"],
       "source SHA drift "+c["name"])
 return m
def execute(case,mode):
 fail(mode in MODES,"bad arm")
 p=CASES/case["filename"]
 os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 start=time.perf_counter()
 try:
  proc=subprocess.run([str(BINARY.resolve()),str(p.resolve()),
    "--mode",mode,"--time",str(CAP)],capture_output=True,text=True,timeout=CAP+2)
 except subprocess.TimeoutExpired:raise RuntimeError("SRE1 process missed hard 6s cap")
 wall=time.perf_counter()-start
 fail(proc.returncode in (0,10,20),"native error "+proc.stderr[-500:])
 line=re.search(r"^c DRNAS_SRE1_RESULT (.+)$",proc.stdout,re.M)
 fail(line is not None,"missing native telemetry "+proc.stdout[-200:])
 d=dict(item.split("=",1) for item in line.group(1).split() if "=" in item)
 status=d["status"]
 fail(proc.returncode=={"SAT":10,"UNSAT":20,"UNKNOWN":0}[status],"exit mismatch")
 fail(d["third_party_solver_calls"]=="0" and d["mode"]==mode,
      "not native same-mode solver")
 n,clauses=parse(p)
 if status=="SAT":
  vals={}
  for line in proc.stdout.splitlines():
   if line.startswith("v "):
    for lit in map(int,line[2:].split()):
     if lit:
      fail(abs(lit) not in vals,"duplicate model var")
      vals[abs(lit)]=lit>0
  fail(len(vals)==n and all(any(vals[abs(l)]==(l>0) for l in c) for c in clauses),
       "model lifting failed original independent Python check")
 if case["cohort"]=="synthetic_lab" and status!="UNKNOWN":
  fail(status==case["independent_exhaustive_truth"],"synthetic full truth mismatch")
 accepted=status=="SAT" or (status=="UNSAT" and
    case["cohort"]=="synthetic_lab" and case["independent_exhaustive_truth"]=="UNSAT")
 nums=("original_vars","original_clauses","reduced_vars","reduced_clauses",
       "sre_equivalences","sre_opposites","sre_units","sre_tautologies",
       "sre_gf2_pairs","sre_gf2_units","sre_graph_arcs","sre_graph_scc",
       "sre_budget_skipped","conflicts","decisions","xor_implications")
 metrics={k:int(d[k]) for k in nums}
 return dict(mode=mode,sha256=case["sha256"],source=case["name"],
      cohort=case["cohort"],status=status,verified_accepted=accepted,
      independently_verified_SAT=status=="SAT",
      certified_synthetic_UNSAT=(status=="UNSAT" and case["cohort"]=="synthetic_lab"),
      raw_original_UNSAT_no_LRAT=(status=="UNSAT" and case["cohort"]!="synthetic_lab"),
      E2E_s=round(wall,6),solver_s=round(float(d["solver_s"]),6),
      preprocess_s=round(float(d["sre_reduce_s"]),6),
      cap_s=CAP,one_logical_cpu=True,
      third_party_solver_calls=0,metrics=metrics)
def verify():
 fail(BINARY.is_file(),"native solver not built")
 p=subprocess.run([str(BINARY.resolve()),"--selftest"],capture_output=True,text=True,timeout=90)
 fail(p.returncode==0 and "SRE1_SELFTEST_PASS " in p.stdout,
      "independent C++ exhaustive test failed: "+p.stderr[-800:])
 print(p.stdout.strip(),flush=True)
def shard(index,mode):
 m=verify_frozen()
 fail(index in range(SHARDS) and mode in MODES,"bad shard coords")
 cs=[c for i,c in enumerate(m["cases"]) if i%SHARDS==index]
 fail(len(cs)==4 and sum(c["cohort"]=="synthetic_lab" for c in cs)==2,
      "incomplete shard cohorts")
 rows=[]
 for c in cs:
  for rep in range(REPS):
   v=execute(c,mode)
   v.update(shard=index,rep=rep)
   rows.append(v);put(ROOT/f"shard-{index}-{mode}.json",rows)
   print("SRE1_TRIAL "+json.dumps(v,sort_keys=True),flush=True)
 fail(len(rows)==8,"expected 4 matched SHA x 2 reps")
 print("SRE1_SHARD_PASS",index,mode,len(rows),flush=True)
def audit():
 m=verify_frozen();allrows=[];seen=set()
 for i in range(SHARDS):
  for mode in MODES:
   rows=get(ROOT/f"shard-{i}-{mode}.json")
   fail(len(rows)==8,"incomplete source/arm shard")
   for z in rows:
    key=(z["sha256"],z["rep"],z["mode"])
    fail(key not in seen and z["mode"]==mode and z["shard"]==i,"bad matrix identity")
    seen.add(key);allrows.append(z)
 expected={(c["sha256"],rep,mode) for c in m["cases"]
           for rep in range(REPS) for mode in MODES}
 fail(len(allrows)==len(seen)==EXPECTED and seen==expected,"incomplete 144 matched trials")
 for c in m["cases"]:
  r=[x for x in allrows if x["sha256"]==c["sha256"]]
  decisions={x["status"] for x in r if x["status"]!="UNKNOWN"}
  fail(len(decisions)<=1,"SAT versus UNSAT contradiction "+c["sha256"])
 def penalty(x):return x["E2E_s"] if x["verified_accepted"] else 2*CAP
 def score(rows):
  return dict(trials=len(rows),certified_solved=sum(x["verified_accepted"] for x in rows),
     certified_SAT=sum(x["independently_verified_SAT"] for x in rows),
     independently_bruteforced_synthetic_UNSAT=sum(x["certified_synthetic_UNSAT"] for x in rows),
     raw_original_UNSAT_without_LRAT=sum(x["raw_original_UNSAT_no_LRAT"] for x in rows),
     TIMEOUT=sum(x["status"]=="UNKNOWN" for x in rows),
     PAR2_s=round(sum(penalty(x) for x in rows),6),
     E2E_s=round(sum(x["E2E_s"] for x in rows),6),
     preprocessing_s=round(sum(x["preprocess_s"] for x in rows),6),
     substitutions=sum(x["metrics"]["sre_equivalences"] for x in rows),
     derived_GF2_pairs=sum(x["metrics"]["sre_gf2_pairs"] for x in rows),
     root_unit_assignments=sum(x["metrics"]["sre_units"] for x in rows),
     vars_removed=sum(x["metrics"]["original_vars"]-x["metrics"]["reduced_vars"]
        for x in rows),native_conflicts=sum(x["metrics"]["conflicts"] for x in rows))
 keyed={(z["sha256"],z["rep"],z["mode"]):z for z in allrows}
 def compare(a,b,cohort):
  cs=[c for c in m["cases"] if c["cohort"]==cohort]
  diffs=[penalty(keyed[(c["sha256"],rep,a)])-penalty(keyed[(c["sha256"],rep,b)])
     for c in cs for rep in range(REPS)]
  return dict(wins=sum(d<-.01 for d in diffs),losses=sum(d>.01 for d in diffs),
      ties=sum(abs(d)<=.01 for d in diffs),net_PAR2_gain_s=round(-sum(diffs),6))
 parts={}
 for cohort in ("synthetic_lab","seen_original_2021_2025"):
  sub=[x for x in allrows if x["cohort"]==cohort]
  parts[cohort]={mode:score([x for x in sub if x["mode"]==mode]) for mode in MODES}
  base=parts[cohort]["plain"]["PAR2_s"]
  for mode in MODES:
   parts[cohort][mode]["PAR2_speedup_vs_plain_x"]=round(
       base/parts[cohort][mode]["PAR2_s"],6)
 result=dict(protocol=PROTOCOL,total_trials=len(allrows),source_original_sha=6,
  synthetic_instances=6,one_cpu=True,independent_original_SAT_witness=True,
  original_UNSAT_independent_LRAT=False,
  synthetic_UNSAT_independent_exhaustive_verification=True,
  globally_blind=False,own_native_cpp_no_foreign_solver=True,
  scores=parts,
  paired_synthetic_vs_plain={mode:compare(mode,"plain","synthetic_lab")
      for mode in MODES if mode!="plain"},
  paired_official_vs_plain={mode:compare(mode,"plain","seen_original_2021_2025")
      for mode in MODES if mode!="plain"},
  per_shard={str(i):{mode:score([x for x in allrows
     if x["shard"]==i and x["mode"]==mode]) for mode in MODES}
     for i in range(SHARDS)},
  caveats=["Six competition CNFs were previously seen and are not a blind holdout",
   "Six small synthetic sources demonstrate mathematical correctness, not competition speed",
   "Original UNSAT without independent LRAT penalized in strict PAR2",
   "SRE is a partial set of provable reductions, not a general polynomial SAT algorithm"])
 put(ROOT/"audit.json",result)
 print("SRE1_FINAL "+json.dumps(result,sort_keys=True),flush=True)
if __name__=="__main__":
 parser=argparse.ArgumentParser()
 parser.add_argument("command",choices=("verify","freeze","shard","audit"))
 parser.add_argument("--shard",type=int,default=0)
 parser.add_argument("--mode",default="plain",choices=MODES)
 args=parser.parse_args()
 {"verify":verify,"freeze":freeze,"audit":audit,
  "shard":lambda:shard(args.shard,args.mode)}[args.command]()
