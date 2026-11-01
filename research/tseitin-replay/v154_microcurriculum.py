#!/usr/bin/env python3
"""DRNAS V15.4: generated *micro-curriculum* and honest split-based selector learning.
336 never-before-generated small CNFs, 14 classes x 24, 12 train/6 validation/6 holdout
per class, balanced SAT/UNSAT in every split. Each instance has a SHA256 freeze manifest.
All CNFs randomized and names anonymized, no solver uses family or expected label.
Train only on measured runtimes of candidate V15.1, V15.3, Kissat; a conservative
feature-only selector is frozen BEFORE blind holdout. No P=NP, no official SAT claim.
"""
import argparse,collections,hashlib,json,math,os,random,resource,statistics,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,"research/tseitin-replay")
from v153_regression import (FAMILIES,build_hall,build_mixed_xor,build_equiv_xor,
                              build_equiv_binary,build_reference)
from v153_proof_checker import verify_certificate as check153
from v151_proof_checker import verify_certificate as check151
SEED="DRNAS-MICRO-154-20261101-v1"
SPLITS=("train","validation","holdout")
SOLVERS=("kissat","v151","v153")
REPS=3
CAP=2.0
SAMPLE_PER_FAMILY=24
THRESHOLDS=(1.15,1.30,1.50)
def sha(data):return hashlib.sha256(data).hexdigest()
def save(file,obj):
 p=Path(file);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def formula(family,index):
 seed=int(sha((SEED+"::"+family+"::"+str(index)).encode())[:16],16)
 rng=random.Random(seed); unsat=bool(index%2)
 if family.startswith("hall_"):
  n,clauses=build_hall(rng,unsat,family.removeprefix("hall_"))
 elif family.startswith("mixed_xor"):
  n,clauses=build_mixed_xor(rng,unsat,int(family.removeprefix("mixed_xor")))
 elif family=="equiv_xor3":n,clauses=build_equiv_xor(rng,unsat)
 elif family=="equiv_binary":n,clauses=build_equiv_binary(rng,unsat)
 else:n,clauses=build_reference(rng,unsat,family)
 # Safe, noisy controls: add logical WEAKENINGS of existing clauses
 # (F entails c v extra) and duplicate originals. Never alter SAT status.
 originals=[cl[:] for cl in clauses]
 if index%4:
  for k in range((index%4)*8):
   ref=rng.choice(originals)
   extras=[v for v in range(1,n+1) if v not in set(map(abs,ref))]
   if not extras:continue
   v=rng.choice(extras);extra=v if rng.randrange(2) else -v
   augmented=ref+[extra]
   if k%4==0:clauses.append(ref[:])
   clauses.append(augmented)
 # Consistent renumbering. Categories and labels never enter solver args.
 perm=list(range(1,n+1));rng.shuffle(perm)
 clauses=[[(1 if x>0 else -1)*perm[abs(x)-1] for x in cl] for cl in clauses]
 for cl in clauses:rng.shuffle(cl)
 rng.shuffle(clauses)
 # Literal DIMACS format; predictable content from fixed SHA seed.
 raw=(f"p cnf {n} {len(clauses)}\n"+
      "".join(" ".join(map(str,cl))+" 0\n" for cl in clauses)).encode()
 return raw,n,clauses,"UNSAT" if unsat else "SAT"
def features(n,clauses):
 m=len(clauses)
 units=sum(len(c)==1 for c in clauses)
 binary=sum(len(c)==2 for c in clauses)
 negative_binary=sum(len(c)==2 and all(x<0 for x in c) for c in clauses)
 positive_wide=sum(3<=len(c)<=32 and all(x>0 for x in c) for c in clauses)
 max_width=max(map(len,clauses))
 # Compact observable signature only. The class label is NEVER a feature.
 bins=(0 if n<=32 else 1 if n<=64 else 2,
       0 if units==0 else 1 if units<=2 else 2,
       0 if binary/m<.15 else 1 if binary/m<.65 else 2,
       0 if negative_binary/m<.15 else 1 if negative_binary/m<.65 else 2,
       0 if positive_wide==0 else 1 if positive_wide<=4 else 2,
       0 if max_width<=3 else 1 if max_width<=6 else 2)
 return {"n":n,"m":m,"units":units,"binary_frac":round(binary/m,5),
 "negative_binary_frac":round(negative_binary/m,5),
 "positive_wide":positive_wide,"max_width":max_width,
 "signature":"-".join(map(str,bins))}
def freeze(out):
 root=Path(out);(root/"cnf").mkdir(parents=True,exist_ok=True)
 manifest=[]
 for family in FAMILIES:
  # Separate SAT and UNSAT strata; assign seed indices to split
  # without inspecting solver results.
  assignment={}
  for parity in (0,1):
   ids=list(range(parity,SAMPLE_PER_FAMILY,2))
   ids.sort(key=lambda k:sha((SEED+"/split/"+family+"/"+str(k)).encode()))
   for k in ids[:6]:assignment[k]="train"
   for k in ids[6:9]:assignment[k]="validation"
   for k in ids[9:]:assignment[k]="holdout"
  for index in range(SAMPLE_PER_FAMILY):
   raw,n,clauses,label=formula(family,index)
   digest=sha(raw)
   anon="cnf/"+digest[:24]+".cnf"
   p=root/anon
   assert not p.exists(),("duplicate generated formula",family,index)
   p.write_bytes(raw)
   manifest.append({"id":digest[:24],"relative_path":anon,"sha256":digest,
     "family":family,"index":index,"expected":label,"split":assignment[index],
     "features":features(n,clauses)})
 assert len(manifest)==len(FAMILIES)*SAMPLE_PER_FAMILY==336
 assert len({x["sha256"] for x in manifest})==336
 assert collections.Counter(x["split"] for x in manifest)=={"train":168,"validation":84,"holdout":84}
 # Freeze every split including holdout before training. Holdout information
 # must never be read by train/validation steps except its immutable hashes.
 save(root/"manifest.json",{"seed":SEED,"categories":FAMILIES,
   "count":336,"splits":{"train":168,"validation":84,"holdout":84},
   "repeats":REPS,"timeout":CAP,"samples":manifest,
   "warnings":["Constructed/generated, not official competition benchmarks",
               "Model training is a rule/threshold selector, not neural training",
               "Solver must be run on original CNF and answers independently checked",
               "Native UNSAT certificates are independently replayed; Kissat UNSAT relies on generator logic",
               "No family names or expected labels used as inference features"]})
 print("V154_FREEZE_PASS",len(manifest),"categories",len(FAMILIES),"train",168,"validation",84,"holdout",84,flush=True)
def setup():
 if hasattr(os,"sched_setaffinity"):
  os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
 resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
def read_clauses(path):
 n=0;cls=[];pending=[]
 for line in Path(path).read_text().splitlines():
  if line.startswith("p "):n=int(line.split()[2]);continue
  for word in line.split():
   v=int(word)
   if v:pending.append(v)
   else:cls.append(pending);pending=[]
 assert n>0 and not pending
 return n,cls
def verify_sat(n,cls,model):
 assigned={}
 for lit in model:
  assert isinstance(lit,int) and lit and abs(lit)<=n
  assert abs(lit) not in assigned
  assigned[abs(lit)]=(lit>0)
 assert all(any(assigned.get(abs(lit))==(lit>0) for lit in c) for c in cls)
def invoke(name,case):
 p=Path("bin",{"v151":"v151_expanded","v153":"v153_unified","kissat":"kissat_solver"}[name]).resolve()
 cnf=Path(case).resolve()
 cmd=([str(p),str(cnf)] if name=="kissat"
      else [str(p),str(cnf),str(Path("bin/kissat_solver").resolve()),"1"])
 t=time.perf_counter()
 try:o=subprocess.run(cmd,text=True,capture_output=True,timeout=CAP)
 except subprocess.TimeoutExpired:return {"status":"TIMEOUT","seconds":CAP,"route":"timeout","model":[],"payload":None}
 dt=time.perf_counter()-t
 if dt>CAP:return {"status":"TIMEOUT","seconds":CAP,"route":"timeout","model":[],"payload":None}
 tagged=[line.split("\t",1)[1] for line in o.stdout.splitlines() if line.startswith("DRNAS_HYBRID_RESULT\t")]
 if tagged:
  assert len(tagged)==1 and o.returncode==0,(name,o.returncode,o.stderr[-200:])
  payload=json.loads(tagged[0])
  status=payload["status"]
  route=payload["path"]
  model=payload.get("model",[])
 else:
  assert o.returncode in (10,20),(name,o.returncode,o.stdout[-160:],o.stderr[-160:])
  status="SAT" if o.returncode==10 else "UNSAT"
  assert "s "+("SATISFIABLE" if status=="SAT" else "UNSATISFIABLE") in o.stdout.splitlines()
  payload=None
  model=[int(x) for line in o.stdout.splitlines() if line.startswith("v ") for x in line.split()[1:] if x!="0"]
  route="kissat" if name=="kissat" else "kissat_fallback"
 return {"status":status,"seconds":round(dt,7),"route":route,"model":model,"payload":payload}
def measured(split,source,out):
 setup()
 src=Path(source)
 frozen=json.loads((src/"manifest.json").read_text())
 assert frozen["seed"]==SEED and frozen["count"]==336
 cases=[x for x in frozen["samples"] if x["split"]==split]
 assert len(cases)=={"train":168,"validation":84,"holdout":84}[split]
 rows=[];begin=time.monotonic()
 for pos,case in enumerate(cases):
  path=src/case["relative_path"]
  assert sha(path.read_bytes())==case["sha256"]
  n,cls=read_clauses(path)
  assert features(n,cls)==case["features"]
  for rep in range(REPS):
   order=list(SOLVERS)
   rng=random.Random(int(sha((SEED+"/"+case["id"]+"/"+str(rep)).encode())[:16],16))
   rng.shuffle(order)
   for name in order:
    try:
     ans=invoke(name,path)
     status=ans["status"]
     assert status in (case["expected"],"TIMEOUT"),(case["id"],name,status,case["expected"])
     if status=="SAT":
      verify_sat(n,cls,ans["model"]);checked="independent_model"
     elif status=="UNSAT" and ans["payload"]:
      checker=check153 if name=="v153" else check151
      assert checker(ans["payload"],cls),(case["id"],name,ans["route"])
      checked="independent_unsat_certificate"
     elif status=="UNSAT":checked="generator_label_no_external_proof"
     else:checked="timeout"
     rows.append({"id":case["id"],"solver":name,"rep":rep,"status":status,
       "seconds":ans["seconds"],"route":ans["route"],"check":checked})
    except Exception as e:
     rows.append({"id":case["id"],"solver":name,"rep":rep,"status":"ERROR",
       "seconds":CAP,"route":"error","check":"reject","error":str(e)[:200]})
  if pos%28==27:
   save(out,{"split":split,"rows":rows,"complete":False})
   print("V154_PROGRESS",split,pos+1,"/",len(cases),"seconds",round(time.monotonic()-begin,2),flush=True)
 assert len(rows)==len(cases)*REPS*len(SOLVERS)
 assert all(x["status"]!="ERROR" for x in rows),[x for x in rows if x["status"]=="ERROR"][:3]
 save(out,{"split":split,"rows":rows,"complete":True})
 print("V154_MEASURE_PASS",split,"cases",len(cases),"trials",len(rows),flush=True)
def paired(rows):
 grouping=collections.defaultdict(list)
 for row in rows:grouping[row["id"],row["solver"]].append(row)
 return {k:(statistics.median(x["seconds"] if x["status"]!="TIMEOUT" else CAP*2 for x in v))
             for k,v in grouping.items()}
def build_policy(train,manifest,threshold):
 score=paired(train)
 groups=collections.defaultdict(list)
 for c in manifest["samples"]:
  if c["split"]=="train":groups[c["features"]["signature"]].append(c["id"])
 mapping={}
 for signature,ids in groups.items():
  if len(ids)<5:continue
  base=sum(score[i,"kissat"] for i in ids)
  choice="kissat";best=base
  for candidate in ("v151","v153"):
   total=sum(score[i,candidate] for i in ids)
   # At least 5 examples, minimum gain threshold and a small absolute
   # improvement floor to avoid selecting based solely on microsecond noise.
   if total<best and base/total>=threshold and base-total>=0.006:
    choice=candidate;best=total
  if choice!="kissat":mapping[signature]={"solver":choice,"train_cases":len(ids),
                        "train_par2_gain":round(base/best,5)}
 return mapping
def evaluate(rows,manifest,mapping):
 score=paired(rows)
 cases=[c for c in manifest["samples"] if c["split"]==rows[0]["split"]] if "split" in rows[0] else []
 # 'rows' contains only one split. Look up by IDs instead of outcome label.
 case_ids=sorted(set(x["id"] for x in rows))
 key_by={c["id"]:c["features"]["signature"] for c in manifest["samples"]}
 costs=collections.defaultdict(float);selected=collections.Counter()
 for cid in case_ids:
  key=key_by[cid]
  target=mapping.get(key,{}).get("solver","kissat")
  selected[target]+=1
  for solver in SOLVERS:costs[solver]+=score[cid,solver]
  costs["selector"]+=score[cid,target]
 return {"cases":len(case_ids),"par2_sum":{k:round(v,7) for k,v in sorted(costs.items())},
         "chosen":dict(selected)}
def train(source,train_file,out):
 manifest=json.loads((Path(source)/"manifest.json").read_text())
 data=json.loads(Path(train_file).read_text())
 assert data["split"]=="train" and data["complete"] and len(data["rows"])==1512
 for t in THRESHOLDS:
  m=build_policy(data["rows"],manifest,t)
  print("V154_TRAIN_CANDIDATE",t,"rules",len(m),flush=True)
 save(out,{"protocol":SEED,"thresholds":THRESHOLDS,
   "rules":{str(t):build_policy(data["rows"],manifest,t) for t in THRESHOLDS},
   "train_sums":{str(t):evaluate(data["rows"],manifest,build_policy(data["rows"],manifest,t)) for t in THRESHOLDS},
   "note":"Only observable CNF signature at inference; no family labels, no answer labels"})
 print("V154_TRAIN_PASS",flush=True)
def validate(source,train_model,val_file,out):
 manifest=json.loads((Path(source)/"manifest.json").read_text())
 model=json.loads(Path(train_model).read_text())
 data=json.loads(Path(val_file).read_text())
 assert data["split"]=="validation" and data["complete"] and len(data["rows"])==756
 trials={str(t):evaluate(data["rows"],manifest,model["rules"][str(t)]) for t in THRESHOLDS}
 base=trials[str(THRESHOLDS[0])]["par2_sum"]["kissat"]
 winner=min(THRESHOLDS,key=lambda t:trials[str(t)]["par2_sum"]["selector"])
 gain=(base-trials[str(winner)]["par2_sum"]["selector"])/max(base,1e-9)
 if gain<0.02:winner=None
 selected_rules=model["rules"].get(str(winner),{}) if winner else {}
 frozen={"protocol":SEED,"validation":trials,"selected_threshold":winner,
  "accepted":winner is not None,"rules":selected_rules,
  "observed_validation_gain_pct":round(100*gain,4),
  "fallback":"kissat","learning":"offline rule selector calibrated on training and validation",
  "caution":"No inference may use family labels, SAT labels, or holdout runtimes"}
 save(out,frozen)
 print("V154_VALIDATE_PASS","accepted",frozen["accepted"],
       "validation_gain_pct",frozen["observed_validation_gain_pct"],
       "rules",len(selected_rules),flush=True)
def audit(source,policy_file,test_file,out):
 manifest=json.loads((Path(source)/"manifest.json").read_text())
 frozen=json.loads(Path(policy_file).read_text())
 data=json.loads(Path(test_file).read_text())
 assert data["split"]=="holdout" and data["complete"] and len(data["rows"])==756
 assert len({x["id"] for x in data["rows"]})==84
 for t in data["rows"]:assert t["status"] in ("SAT","UNSAT","TIMEOUT")
 res=evaluate(data["rows"],manifest,frozen["rules"])
 base=res["par2_sum"]["kissat"];sel=res["par2_sum"]["selector"]
 gain=(base-sel)/base*100
 outp={"protocol":SEED,"holdout":res,"validation":frozen["validation"],
   "selector_accepted":frozen["accepted"],"gain_vs_kissat_pct":round(gain,4),
   "families":list(FAMILIES),"splits":manifest["splits"],
   "proof_checked":sum(x["check"]=="independent_unsat_certificate" for x in data["rows"]),
   "sat_models_checked":sum(x["check"]=="independent_model" for x in data["rows"]),
   "all_3_solver_trials":len(data["rows"]),
   "caution":"Unseen generated controls only; no official SAT claim and no native selector deployed"}
 save(out,outp)
 for k,v in sorted(res["par2_sum"].items()):
  print("V154_HOLDOUT_PAR2",k,v,flush=True)
 print("V154_POLICY",json.dumps(frozen["rules"],sort_keys=True),flush=True)
 print("V154_FINAL_AUDIT_PASS",len(data["rows"]),"holdout_cases",res["cases"],
       "gain_pct",round(gain,4),"accepted",frozen["accepted"],flush=True)
if __name__=="__main__":
 p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="cmd",required=True)
 f=sub.add_parser("freeze");f.add_argument("--out",required=True)
 m=sub.add_parser("measure");m.add_argument("--split",choices=SPLITS,required=True);m.add_argument("--source",required=True);m.add_argument("--out",required=True)
 t=sub.add_parser("train");t.add_argument("--source",required=True);t.add_argument("--measurements",required=True);t.add_argument("--out",required=True)
 v=sub.add_parser("validate");v.add_argument("--source",required=True);v.add_argument("--train",required=True);v.add_argument("--measurements",required=True);v.add_argument("--out",required=True)
 a=sub.add_parser("audit");a.add_argument("--source",required=True);a.add_argument("--policy",required=True);a.add_argument("--measurements",required=True);a.add_argument("--out",required=True)
 args=p.parse_args()
 if args.cmd=="freeze":freeze(args.out)
 elif args.cmd=="measure":measured(args.split,args.source,args.out)
 elif args.cmd=="train":train(args.source,args.measurements,args.out)
 elif args.cmd=="validate":validate(args.source,args.train,args.measurements,args.out)
 else:audit(args.source,args.policy,args.measurements,args.out)
