#!/usr/bin/env python3
"""V16.1 prospective signature selector (research evaluation, not native code).
Training: 84 CNFs from earlier frozen seed indices 0..11.
Prospective holdout: 84 newly-generated disjoint indices 12..23, frozen
BEFORE any holdout timing. No family/index/expected/solver timing in the
feature vector. Pre-registered 5% train margin and >=4 examples/signature.
Selector performance includes estimated 100us per CNF; real native classifier
must be separately measured before speed claims.
"""
import collections,hashlib,json,statistics,random,sys,time
from pathlib import Path
import v160_hidden_keys as g
SEED="V161-PROSPECTIVE-20261101-NOT-TOUCHED"
ROOT=Path("v161-prospective")
SOLVERS=("kissat_api","v1531","v159")
REPS=3
def features(n,clauses):
 m=len(clauses);k=collections.Counter(map(len,clauses))
 unit=k[1];binary=k[2];alo=sum(len(c)>=3 and all(v>0 for v in c) for c in clauses)
 negbin=sum(len(c)==2 and c[0]<0 and c[1]<0 for c in clauses)
 supports=collections.Counter(tuple(sorted(abs(v) for v in c)) for c in clauses if 2<=len(c)<=6 and len(set(map(abs,c)))==len(c))
 repeated=sum(v>=2 for v in supports.values())
 # O(m) and bounded support dictionary (input has at most 250 clauses).
 return "-".join(map(str,[int(unit>0),int(binary*4>=m),int(alo>=3 and negbin>=3),
                               int(repeated>=2),int(m>=100),int(k[3]*2>=m)]))
def run_records(indices,split):
 arr=[];rows=[]
 for fam in g.FAMILIES:
  for i in indices:
   raw,n,clauses,answer=g.gen(fam,i)
   sha=hashlib.sha256(raw).hexdigest()
   path=ROOT/split/(sha[:22]+".cnf")
   path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
   arr.append({"id":sha,"path":str(path),"expected":answer,
               "feature":features(n,clauses),"sha256":sha,
               # For audit only: withheld from predictor
               "audit_family":fam,"audit_index":i})
 assert len(arr)==len(g.FAMILIES)*len(indices)
 return arr
def measure(cases,split):
 rows=[]
 for ci,c in enumerate(cases):
  raw,n,cl,label=g.gen(c["audit_family"],c["audit_index"])
  assert hashlib.sha256(raw).hexdigest()==c["sha256"]
  p=Path(c["path"])
  for rep in range(REPS):
   order=list(SOLVERS)
   random.Random(int(hashlib.sha256((SEED+c["id"]+str(rep)).encode()).hexdigest()[:16],16)).shuffle(order)
   for solver in order:
    res=g.run(solver,p,n,cl,label)
    assert res["correct"] and res["status"]==label,(split,c["id"],solver,res)
    rows.append({"id":c["id"],"solver":solver,"rep":rep,
                 "seconds":res["seconds"],"route":res["route"]})
  if ci%28==27:print("V161_PROGRESS",split,ci+1,"/",len(cases),flush=True)
 return rows
def cost(rows):
 times=collections.defaultdict(list)
 for r in rows:times[r["id"],r["solver"]].append(r["seconds"])
 return {k:statistics.median(v) for k,v in times.items()}
def learn(cases,rows):
 costs=cost(rows);groups=collections.defaultdict(list)
 for x in cases:groups[x["feature"]].append(x["id"])
 rules={}
 for signature,ids in groups.items():
  if len(ids)<4:continue
  baseline=sum(costs[i,"v159"] for i in ids)
  for other in ("kissat_api","v1531"):
   candidate=sum(costs[i,other] for i in ids)
   # Switching must save >5% AND amortize 100us per occurrence.
   if candidate+len(ids)*0.0001<baseline*.95:
    if signature not in rules or candidate<rules[signature]["cost"]:
     rules[signature]={"solver":other,"cost":candidate,
                       "training_cases":len(ids),"training_gain_pct":round(100*(baseline-candidate)/baseline,4)}
 return rules
def evaluate(cases,rows,rules):
 c=cost(rows);sums=collections.defaultdict(float);chosen=collections.Counter()
 for case in cases:
  id=case["id"];pick=rules.get(case["feature"],{}).get("solver","v159")
  chosen[pick]+=1
  for solver in SOLVERS:sums[solver]+=c[id,solver]
  sums["selector"]+=c[id,pick]+.0001
 return {"sums_seconds":{k:round(v,7) for k,v in sums.items()},
         "chosen":dict(chosen),"estimated_scan_cost_seconds_per_case":.0001}
def main():
 ROOT.mkdir(exist_ok=True)
 train=run_records(range(12),"train")
 holdout=run_records(range(12,24),"holdout")
 assert not({x["sha256"] for x in train}&{x["sha256"] for x in holdout})
 manifest={"train":[{k:v for k,v in x.items() if k not in ("audit_family",)} for x in train],
           "holdout":[{k:v for k,v in x.items() if k not in ("audit_family",)} for x in holdout]}
 (ROOT/"frozen-dataset.json").write_text(json.dumps(manifest,indent=2))
 print("V161_FREEZE_PASS",len(train),len(holdout),flush=True)
 training_rows=measure(train,"train")
 rules=learn(train,training_rows)
 public_rules={k:{j:v for j,v in value.items() if j!="cost"} for k,value in rules.items()}
 (ROOT/"frozen-rules.json").write_text(json.dumps(public_rules,indent=2))
 print("V161_TRAIN_FROZEN",len(rules),"rules",json.dumps(public_rules,sort_keys=True),flush=True)
 holdout_rows=measure(holdout,"holdout")
 result=evaluate(holdout,holdout_rows,rules)
 result["training"]=evaluate(train,training_rows,rules)
 result["split_sha_disjoint"]=True
 result["holdout"]=len(holdout)
 result["trials"]=(len(train)+len(holdout))*REPS*len(SOLVERS)
 result["limitations"]=["Generator-family holdout is not an external SAT corpus",
                        "100us selector overhead is estimated, not measured",
                        "Native integration requires fresh out-of-family prospective evaluation"]
 (ROOT/"audit.json").write_text(json.dumps(result,indent=2))
 print("V161_HOLDOUT_RESULT",json.dumps(result["sums_seconds"],sort_keys=True),flush=True)
 print("V161_HOLDOUT_CHOICES",json.dumps(result["chosen"],sort_keys=True),flush=True)
 print("V161_AUDIT_PASS",result["trials"],flush=True)
if __name__=="__main__":main()
