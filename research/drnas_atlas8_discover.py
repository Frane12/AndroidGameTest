#!/usr/bin/env python3
"""ATLAS8: discover proof-checked local Boolean reductions and persist an append-only
catalog. Each entry is a 2-4-variable CNF block and its *equivalent* prime
implicate CNF, verified exhaustively over all local assignments.
Only accept blocks with fewer literals; no SAT label leakage. No solver speed claim.
"""
import argparse,collections,hashlib,itertools,json,pathlib,random
CATALOG=pathlib.Path("research/atlas8_reduction_table.jsonl")
def canon(c):
 c=tuple(sorted(set(c),key=lambda x:(abs(x),x<0)))
 return None if any(-x in c for x in c) else c
def sat(clauses,assign):
 return all(any(assign[abs(x)]==(x>0) for x in c) for c in clauses)
def truth(clauses,k):
 return tuple(sat(clauses,{i+1:bool((bits>>i)&1) for i in range(k)}) for bits in range(1<<k))
def literals(cs):return sum(len(c) for c in cs)
def prime_cnf(t,k):
 result=[]
 for size in range(1,k+1):
  for vs in itertools.combinations(range(1,k+1),size):
   for signs in itertools.product((-1,1),repeat=size):
    clause=tuple(v*s for v,s in zip(vs,signs))
    if all((not t[b]) or any(bool((b>>(abs(x)-1))&1)==(x>0) for x in clause) for b in range(1<<k)):
     # This is an implicate: every satisfying assignment satisfies it.
     result.append(clause)
  # Exhaust all clause sizes: stopping early can lose required implicates.
 primes=[c for c in result if not any(set(d)<set(c) for d in result)]
 # greedy exact truth-preserving removal from all prime implicates
 current=list(primes)
 for c in sorted(current,key=lambda x:-len(x)):
  trial=[x for x in current if x!=c]
  if truth(trial,k)==t:current=trial
 return current
def normalize(clauses):
 vs=sorted({abs(l) for c in clauses for l in c})
 if not 2<=len(vs)<=4:return None
 mp={v:i+1 for i,v in enumerate(vs)}
 normalized=[canon((mp[abs(l)] if l>0 else -mp[abs(l)]) for l in c) for c in clauses]
 if any(c is None for c in normalized):return None
 cc=tuple(sorted(set(normalized)))
 return len(vs),cc
def discover(n,clauses,limit=240):
 # Exact local blocks: only include clauses whose support is inside the chosen
 # variables. Replacing all such clauses with an equivalent CNF is sound.
 supports=collections.Counter(tuple(sorted(set(abs(l) for l in c))) for c in clauses if 2<=len(c)<=4)
 keys=sorted(supports,key=lambda x:(-supports[x],x))
 found={}
 for sup in keys[:limit]:
  for k in (len(sup),):
   if not 2<=k<=4:continue
   block=[c for c in clauses if set(map(abs,c)).issubset(sup)]
   if not 2<=len(block)<=24:continue
   norm=normalize(block)
   if norm is None:continue
   dim,local=norm
   if dim!=k:continue
   t=truth(local,k)
   if not any(t) or all(t):continue
   new=prime_cnf(t,k)
   if truth(new,k)!=t:raise AssertionError("truth mismatch: reject and stop")
   old_lit=literals(local);new_lit=literals(new)
   if new_lit>=old_lit:continue
   key=hashlib.sha256(json.dumps([k,local],sort_keys=True).encode()).hexdigest()
   found[key]=dict(id=key,vars=k,original=[list(c) for c in local],
     reduced=[list(c) for c in new],old_literals=old_lit,new_literals=new_lit,
     saved_literals=old_lit-new_lit,verified_assignments=1<<k,
     proof="exhaustive truth-table equivalence",applications_observed=0,observed_sources=[])
 return found
def merge(existing,new):
 # Idempotent across repeated CI runs: count distinct source CNF hashes.
 result={k:dict(v) for k,v in existing.items()}
 for k,v in new.items():
  if k in result:
   assert result[k]["reduced"]==v["reduced"] and result[k]["original"]==v["original"]
   sources=set(result[k].get("observed_sources",[]))|set(v.get("observed_sources",[]))
   result[k]["observed_sources"]=sorted(sources)
   result[k]["applications_observed"]=len(sources)
  else:
   result[k]=dict(v)
   sources=set(v.get("observed_sources",[]))
   result[k]["observed_sources"]=sorted(sources)
   result[k]["applications_observed"]=len(sources)
 return result
def verify_record(v):
 k=int(v["vars"])
 old=tuple(tuple(c) for c in v["original"])
 new=tuple(tuple(c) for c in v["reduced"])
 assert 2<=k<=4
 assert hashlib.sha256(json.dumps([k,old],sort_keys=True).encode()).hexdigest()==v["id"]
 assert truth(old,k)==truth(new,k),(v["id"],"record truth mismatch")
 assert literals(new)<literals(old),(v["id"],"non-reduction")
 assert v["saved_literals"]==literals(old)-literals(new)
 assert v["observed_sources"]==sorted(set(v["observed_sources"]))
 assert v["applications_observed"]==len(v["observed_sources"])
def selftest():
 # Every possible truth table through three variables; sampled four-variable tables.
 rng=random.Random(17011)
 count=0
 for k in (2,3,4):
  samples=list(range(1<<(1<<k))) if k<4 else [0,(1<<(1<<k))-1]+[rng.randrange(1<<(1<<k)) for _ in range(384)]
  for mask in samples:
   t=tuple(bool((mask>>b)&1) for b in range(1<<k))
   reduced=prime_cnf(t,k)
   assert truth(reduced,k)==t,(k,mask,"prime implicates not equivalent")
   count+=1
 print("ATLAS8_SELFTEST_PASS "+json.dumps(dict(tables=count,kind="exhaustive k2/k3 + randomized k4")),flush=True)
def read(path):
 if not path.exists():return {}
 return {v["id"]:v for line in path.read_text().splitlines() if line.strip() for v in [json.loads(line)]}
def save(path,records):
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text("".join(json.dumps(v,sort_keys=True,separators=(",",":"))+"\n" for _,v in sorted(records.items())))
def run():
 from importlib.machinery import SourceFileLoader
 gen=SourceFileLoader("atlas7","research/drnas_atlas7_hardmixed300.py").load_module()
 p=argparse.ArgumentParser();p.add_argument("--train",type=int,default=200);p.add_argument("--catalog",default=str(CATALOG));args=p.parse_args()
 assert 1<=args.train<=200
 selftest()
 cases=[(c,i) for c in gen.CATEGORIES for i in range(20)]
 random.Random(20261111).shuffle(cases)
 base=read(pathlib.Path(args.catalog));seen={};hits=collections.Counter()
 for j,(c,i) in enumerate(cases[:args.train],1):
  n,clauses,seed=gen.build(c,i)
  got=discover(n,clauses)
  source_sha=hashlib.sha256(gen.dimacs(n,clauses)).hexdigest()
  for v in got.values():
   v['observed_sources']=[source_sha]
   v['applications_observed']=1
   verify_record(v)
   hits[c]+=1
  seen=merge(seen,got)
  if j%25==0:print("ATLAS8_DISCOVERY "+json.dumps(dict(done=j,patterns=len(seen),hits=dict(hits))),flush=True)
 merged=merge(base,seen)
 for v in merged.values():verify_record(v)
 save(pathlib.Path(args.catalog),merged)
 reloaded=read(pathlib.Path(args.catalog))
 assert reloaded==merged,'persist/reload mismatch'
 summary=dict(training=args.train,previous=len(base),discovered=len(seen),persistent_total=len(merged),
   source="ATLAS7 training partition only",holdout_accessed=False,
   equivalence="exhaustive local 2-4 variable truth tables",
   note="discovery and persistence only; applying reductions in native solver and E2E benefit not yet measured")
 print("ATLAS8_FINAL "+json.dumps(summary,sort_keys=True),flush=True)
if __name__=="__main__":run()
