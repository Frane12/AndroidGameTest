#!/usr/bin/env python3
"""DRNAS V15.5: generated *micro-curriculum* and honest split-based selector learning.
480 never-before-generated small CNFs, 14 classes x 24, 12 train/6 validation/6 holdout
per class, balanced SAT/UNSAT in every split. Each instance has a SHA256 freeze manifest.
All CNFs randomized and names anonymized, no solver uses family or expected label.
Train only on measured runtimes of candidate V15.1, V15.3, Kissat; a conservative
feature-only selector is frozen BEFORE blind holdout. No P=NP, no official SAT claim.
"""
import argparse,collections,hashlib,json,math,os,random,resource,statistics,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,"research/tseitin-replay")
from v153_regression import (FAMILIES as LEGACY_FAMILIES,build_hall,build_mixed_xor,build_equiv_xor,
                              build_equiv_binary,build_reference,xorclauses)
EXTRA_FAMILIES=["medium_planted3","medium_planted4","medium_equiv",
                "medium_xor_tseitin","medium_graph3","medium_pigeonhole"]
FAMILIES=LEGACY_FAMILIES+EXTRA_FAMILIES
from v153_proof_checker import verify_certificate as check153
from v151_proof_checker import verify_certificate as check151
SEED="DRNAS-MICRO-155-20261101-v1"
SPLITS=("train","validation","holdout")
SOLVERS=("kissat","v151","v153")
REPS=3
CAP=2.0
SAMPLE_PER_FAMILY=24
THRESHOLDS=(1.05,1.10,1.20)
def sha(data):return hashlib.sha256(data).hexdigest()
def save(file,obj):
 p=Path(file);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")

def medium_formula(family,rng,unsat):
 """Extra medium problems with independently known SAT/UNSAT construction."""
 cls=[]
 if family in ("medium_planted3","medium_planted4"):
  width=3 if family.endswith("3") else 4
  n=rng.choice((72,96,120))
  planted=[False]+[bool(rng.randrange(2)) for _ in range(n)]
  for _ in range(4*n):
   ids=rng.sample(range(1,n+1),width)
   for _retry in range(100):
    lits=[i*rng.choice((-1,1)) for i in ids]
    if any((v>0)==planted[abs(v)] for v in lits):break
   cls.append(lits)
  if unsat:
   # Independent exact UNSAT core: all assignments of a 4-variable
   # support are excluded using two opposite parity equations.
   vars_=rng.sample(range(1,n+1),4)
   cls+=xorclauses(vars_,0,rng)+xorclauses(vars_,1,rng)
 elif family=="medium_equiv":
  n=rng.choice((80,104,128))
  x=list(range(1,n//2+1))
  for a,b in zip(x,x[1:]):
   cls.extend([[-a,b],[a,-b]])
  u,v=x[0],x[-1]
  other=[n-2,n-1]
  cls+=xorclauses([u]+other,0,rng)
  cls+=xorclauses([v]+other,int(unsat),rng)
  if not unsat:
   # Witness x_i=0, other=0 satisfies parity, add residual clauses
   # planted to hold on this simple witness.
   planted={i:False for i in range(1,n+1)}
   for _ in range(n):
    vs=rng.sample(range(1,n+1),3)
    lits=[w*rng.choice((-1,1)) for w in vs]
    if not any((z>0)==planted[abs(z)] for z in lits):lits[0]=-abs(lits[0])
    cls.append(lits)
 elif family=="medium_xor_tseitin":
  n=rng.choice((64,96,128))
  # Chain: y_i = y_(i-1) XOR x_i with 4 CNF clauses/gate.
  xs=list(range(1,17));aux=list(range(17,33))
  def xor3(a,b,c):
   # Even parity a XOR b XOR c = 0.
   return xorclauses([a,b,c],0,rng)
  prev=xs[0]
  for x,out in zip(xs[1:],aux):
   cls+=xor3(prev,x,out)
   prev=out
  # Force all x bits and output to their expected parity (not a
  # planted-model label used at prediction time).
  bits=[rng.randrange(2) for _ in xs]
  parity=0
  for bit in bits:parity^=bit
  cls += [[v if bit else -v] for v,bit in zip(xs,bits)]
  cls.append([prev if (parity^int(unsat)) else -prev])
  for _ in range(2*n):
   # Guaranteed redundant positive weakenings of original unit constraints.
   target=rng.choice(xs)
   lit=target if bits[target-1] else -target
   other=rng.sample(range(1,n+1),2)
   cls.append([lit,other[0],-other[1]])
 elif family=="medium_graph3":
  vertices=rng.choice((14,20,28));colors=3;n=vertices*colors
  def v(i,c):return i*colors+c+1
  planted=[rng.randrange(colors) for _ in range(vertices)]
  # For SAT, only cross-color edges, planted coloring witnesses SAT.
  edges=set()
  for i in range(vertices-1):
   for j in range(i+1,vertices):
    if planted[i]!=planted[j] and rng.random()<.20:edges.add((i,j))
  if unsat:
   # K4 is not 3-colorable, regardless of rest.
   for i in range(4):
    for j in range(i+1,4):edges.add((i,j))
  for i in range(vertices):
   cls.append([v(i,c) for c in range(colors)])
   for c in range(colors):
    for d in range(c+1,colors):
     cls.append([-v(i,c),-v(i,d)])
  for i,j in sorted(edges):
   for c in range(colors):cls.append([-v(i,c),-v(j,c)])
 elif family=="medium_pigeonhole":
  H=rng.choice((5,6));B=H+int(unsat);n=H*B
  def v(b,h):return b*H+h+1
  for b in range(B):cls.append([v(b,h) for h in range(H)])
  for h in range(H):
   for b in range(B):
    for j in range(b+1,B):cls.append([-v(b,h),-v(j,h)])
 else:raise ValueError("unrecognized medium family "+family)
 return n,cls

def formula(family,index):
 seed=int(sha((SEED+"::"+family+"::"+str(index)).encode())[:16],16)
 rng=random.Random(seed); unsat=bool(index%2)
 if family in EXTRA_FAMILIES:
  n,clauses=medium_formula(family,rng,unsat)
 elif family.startswith("hall_"):
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
 """Observable lightweight CNF-only signatures; no family/answer features."""
 m=len(clauses);counts=collections.Counter(map(len,clauses))
 units=counts.get(1,0); binary=counts.get(2,0)
 negatives=sum(len(c)==2 and all(x<0 for x in c) for c in clauses)
 pos_wide=sum(3<=len(c)<=32 and all(x>0 for x in c) for c in clauses)
 # Approximate XOR footprint: multiple masks share an exact support,
 # but never inspect expected answers or solver response.
 xor_support=collections.Counter()
 signed_binary=set()
 active=collections.Counter()
 for c in clauses:
  for x in c:active[abs(x)]+=1
  if len(c)==2:
   signed_binary.add(tuple(c))
  if 3<=len(c)<=10:
   support=tuple(sorted(map(abs,c)))
   if len(set(support))==len(c):xor_support[support]+=1
 xor_mass=sum(v for k,v in xor_support.items() if v>=4)
 max_width=max(map(len,clauses))
 balance=sum(1 for cnt in active.values() if cnt>=4)
 # Coarse bins deliberately transfer between independent random seeds.
 bins=(0 if n<=48 else 1 if n<=128 else 2,
       0 if units==0 else 1 if units<=8 else 2,
       0 if binary/m<.25 else 1 if binary/m<.75 else 2,
       0 if negatives/m<.12 else 1 if negatives/m<.35 else 2,
       0 if pos_wide<3 else 1,
       0 if max_width<=3 else 1 if max_width<=6 else 2,
       0 if xor_mass==0 else 1 if xor_mass/m<.40 else 2)
 return {"n":n,"m":m,"units":units,"binary_frac":round(binary/m,5),
    "negative_binary_frac":round(negatives/m,5),
    "positive_wide":pos_wide,"max_width":max_width,"xor_mask_mass":xor_mass,
    "active_variables":len(active),"at_least_4_occurrences":balance,
    "signature":"-".join(map(str,bins)),
    "coarse_signature":"-".join(map(str,(bins[0],bins[1],bins[2],bins[4],bins[6])))}

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
 assert len(manifest)==len(FAMILIES)*SAMPLE_PER_FAMILY==480
 assert len({x["sha256"] for x in manifest})==480
 assert collections.Counter(x["split"] for x in manifest)=={"train":240,"validation":120,"holdout":120}
 # Freeze every split including holdout before training. Holdout information
 # must never be read by train/validation steps except its immutable hashes.
 save(root/"manifest.json",{"seed":SEED,"categories":FAMILIES,
   "count":480,"splits":{"train":240,"validation":120,"holdout":120},
   "repeats":REPS,"timeout":CAP,"samples":manifest,
   "warnings":["Constructed/generated, not official competition benchmarks",
               "Model training is a rule/threshold selector, not neural training",
               "Solver must be run on original CNF and answers independently checked",
               "Native UNSAT certificates are independently replayed; Kissat UNSAT relies on generator logic",
               "No family names or expected labels used as inference features"]})
 print("V155_FREEZE_PASS",len(manifest),"categories",len(FAMILIES),"train",240,"validation",120,"holdout",120,flush=True)
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
 assert frozen["seed"]==SEED and frozen["count"]==480
 cases=[x for x in frozen["samples"] if x["split"]==split]
 assert len(cases)=={"train":240,"validation":120,"holdout":120}[split]
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
   print("V155_PROGRESS",split,pos+1,"/",len(cases),"seconds",round(time.monotonic()-begin,2),flush=True)
 assert len(rows)==len(cases)*REPS*len(SOLVERS)
 assert all(x["status"]!="ERROR" for x in rows),[x for x in rows if x["status"]=="ERROR"][:3]
 save(out,{"split":split,"rows":rows,"complete":True})
 print("V155_MEASURE_PASS",split,"cases",len(cases),"trials",len(rows),flush=True)
def percase_cost(rows):
 grouped=collections.defaultdict(list)
 for r in rows:grouped[r["id"],r["solver"]].append(r)
 return {key:statistics.median([x["seconds"] if x["status"]!="TIMEOUT" else CAP*2 for x in rr])
         for key,rr in grouped.items()}
def build_policy(rows,manifest,threshold,feature_key):
 """Conservative switches from default V15.3 to Kissat for slower signatures."""
 score=percase_cost(rows);groups=collections.defaultdict(list)
 for c in manifest["samples"]:
  if c["split"]=="train":groups[c["features"][feature_key]].append(c["id"])
 mapping={}
 for sig,ids in groups.items():
  if len(ids)<6:continue
  a=sum(score[i,"v153"] for i in ids);b=sum(score[i,"kissat"] for i in ids)
  if a/b>=threshold and a-b>=0.004:
   mapping[sig]={"solver":"kissat","train_cases":len(ids),"ratio_v153_vs_kissat":round(a/b,5)}
 return mapping
def evaluate(rows,manifest,rules,feature_key):
 score=percase_cost(rows); ids=sorted({r["id"] for r in rows})
 byid={x["id"]:x for x in manifest["samples"]}
 totals=collections.defaultdict(float);counter=collections.Counter()
 for cid in ids:
  selected=rules.get(byid[cid]["features"][feature_key],{}).get("solver","v153")
  counter[selected]+=1
  for solver in SOLVERS:totals[solver]+=score[cid,solver]
  totals["selector"]+=score[cid,selected]
 # Conservative policy-overhead estimate: an additional full DIMACS parsing
 # pass is priced at 75 microseconds/case, regardless of selected solver.
 # This is a fixed proposed budget, NOT a measurement of an implemented native
 # classifier. Always disclose it as a modelling assumption.
 totals["selector"]+=len(ids)*0.000075
 return {"cases":len(ids),"par2_sum":{k:round(v,7) for k,v in sorted(totals.items())},
         "chosen":dict(counter),"assumed_feature_scan_overhead_s_per_case":0.000075}
def train(source,train_file,out):
 manifest=json.loads((Path(source)/"manifest.json").read_text())
 data=json.loads(Path(train_file).read_text())
 assert data["split"]=="train" and data["complete"] and len(data["rows"])==2160
 choices={}
 for threshold in THRESHOLDS:
  for feature_key in ("signature","coarse_signature"):
   k=str(threshold)+"/"+feature_key
   rules=build_policy(data["rows"],manifest,threshold,feature_key)
   choices[k]={"rules":rules,"feature_key":feature_key,"threshold":threshold,
               "training":evaluate(data["rows"],manifest,rules,feature_key)}
   print("V155_TRAIN",k,"rules",len(rules),"selected",choices[k]["training"]["chosen"],flush=True)
 save(out,{"protocol":SEED,"choices":choices,
    "training_only":True,"policy_overhead":"Assumed 75us/CNF scan; must validate with native timing later"})
 print("V155_TRAIN_PASS",len(choices),flush=True)
def validate(source,model_file,val_file,out):
 manifest=json.loads((Path(source)/"manifest.json").read_text())
 model=json.loads(Path(model_file).read_text())
 data=json.loads(Path(val_file).read_text())
 assert data["split"]=="validation" and data["complete"] and len(data["rows"])==1080
 stats={k:evaluate(data["rows"],manifest,c["rules"],c["feature_key"])
        for k,c in model["choices"].items()}
 best=min(stats,key=lambda k:stats[k]["par2_sum"]["selector"])
 minimum=min(stats[best]["par2_sum"][z] for z in SOLVERS if z in ("kissat","v153"))
 chosen=stats[best]["par2_sum"]["selector"]
 improvement=100*(minimum-chosen)/max(minimum,1e-9)
 baseline=min(("kissat","v153"),key=lambda z:stats[best]["par2_sum"][z])
 # Pre-registered minimum validation gain >2% relative to best single solver.
 accepted=improvement>=2.0
 frozen={"protocol":SEED,"choices_evaluated":stats,
         "baseline_strategy":baseline,"accepted":accepted,
         "selected_key":best if accepted else None,
         "feature_key":model["choices"][best]["feature_key"] if accepted else None,
         "rules":model["choices"][best]["rules"] if accepted else {},
         "fallback":"v153" if accepted else baseline,
         "validation_improvement_vs_best_fixed_pct":round(improvement,4),
         "modelled_feature_probe_cost_s_per_case":0.000075,
         "note":"Validation chooses once. Holdout has no policy updates; no class/label data available at decision time."}
 save(out,frozen)
 print("V155_VALIDATION_PASS","accepted",accepted,"best_fixed",baseline,
       "rules",len(frozen["rules"]),"improvement_pct",round(improvement,4),flush=True)
def audit(source,policy_file,test_file,out):
 manifest=json.loads((Path(source)/"manifest.json").read_text())
 frozen=json.loads(Path(policy_file).read_text())
 data=json.loads(Path(test_file).read_text())
 assert data["split"]=="holdout" and data["complete"] and len(data["rows"])==1080
 assert len({x["id"] for x in data["rows"]})==120
 assert all(x["status"] in ("SAT","UNSAT","TIMEOUT") for x in data["rows"])
 # If validation did not accept selector, use frozen best single solver.
 if frozen["accepted"]:
  res=evaluate(data["rows"],manifest,frozen["rules"],frozen["feature_key"])
  chosen=res["par2_sum"]["selector"]
  strategy="feature_selector"
 else:
  res=evaluate(data["rows"],manifest,{},"coarse_signature")
  chosen=res["par2_sum"][frozen["fallback"]]
  strategy="fixed_"+frozen["fallback"]
 best_fixed=min(res["par2_sum"][x] for x in ("v153","kissat"))
 gain=100*(best_fixed-chosen)/max(best_fixed,1e-9)
 outp={"protocol":SEED,"count":len(data["rows"]),"holdout":res,
       "selected_strategy":strategy,"selector_accepted":frozen["accepted"],
       "gain_vs_best_fixed_pct":round(gain,4),
       "training_validation_frozen":frozen,
       "checks":{"native_unsat_proof_replays":sum(x["check"]=="independent_unsat_certificate" for x in data["rows"]),
                 "sat_witness_checks":sum(x["check"]=="independent_model" for x in data["rows"])},
       "warnings":["Synthetic seed-separated holdout, not official competition",
                   "75us per-case classifier overhead is a PREREGISTERED ESTIMATE, not actual native measurement",
                   "Sub-millisecond results require larger independent benchmarks to confirm"]}
 save(out,outp)
 for name,value in res["par2_sum"].items():print("V155_HOLDOUT_PAR2",name,value,flush=True)
 print("V155_AUDIT_PASS",len(data["rows"]),"cases",120,
       "strategy",strategy,"gain_vs_best_fixed_pct",round(gain,4),flush=True)
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
