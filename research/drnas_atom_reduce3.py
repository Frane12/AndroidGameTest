#!/usr/bin/env python3
"""ATOM REDUCE3, offline proof-first local resolution.
Seeds are original CNF clauses touching retrospectively identified
REDUCE2 graph variables. This is HINDSIGHT analysis, not blind selection.
All accepted resolvents have explicit exact two-parent resolution and
are independently RUP checked against ORIGINAL CNF. Never alter solver.
"""
import json
from collections import Counter
from pathlib import Path
from drnas_atom_reduce1 import normalize,rup

def cnf_read(path):
 lines=Path(path).read_text().splitlines()
 clauses=[];header=None
 for line in lines:
  if not line or line.startswith(("c","%")):continue
  if line.startswith("p "):
   p=line.split();header=(int(p[2]),int(p[3]));continue
  bits=[int(i) for i in line.split()]
  assert bits[-1]==0
  clauses.append(tuple(bits[:-1]))
 assert header and len(clauses)==header[1]
 return clauses

def analyze(cnf,trace_path,reason_audit_path,output):
 original=cnf_read(cnf)
 data=json.loads(Path(reason_audit_path).read_text())
 focus=data["focus_16_20"]
 core=set(focus["shared_reason_variables"])
 if not core:core={abs(l) for l in original[0]}
 source_ids=set(focus["shared_original_cids"])
 # Local network, allow 1-hop original neighbors of core variables.
 seeds={i for i,c in enumerate(original) if any(abs(l) in core for l in c)}
 seeds|=source_ids
 learned=[]
 for line in Path(trace_path).read_text().splitlines():
  if "kind=learn " in line:
   d=dict(x.split("=",1) for x in line.split()[1:])
   learned.append(tuple(int(x) for x in d["clause"].split(",")))
 # Each derivation retains proof ancestry, not just a found clause.
 known={normalize(original[i]):dict(lits=normalize(original[i]),kind="original",id=i)
        for i in seeds if normalize(original[i]) is not None}
 initial=len(known)
 generated={}; counts=Counter()
 frontier=list(known.values())
 # two rounds; 3-SAT seed parents, resolvents max 4 literals.
 for depth in (1,2):
  new=[]
  base=list(known.values())
  if depth==1:
   pairs=((a,b) for i,a in enumerate(base) for b in base[i+1:])
  else:
   pairs=((a,b) for a in frontier for b in base if a["lits"]!=b["lits"])
  for a,b in pairs:
   counts["pairs"]+=1
   if counts["pairs"]>120000:break
   sa=set(a["lits"]);sb=set(b["lits"])
   for lit in sorted(sa,key=lambda x:(abs(x),x)):
    if -lit not in sb:continue
    counts["pivots"]+=1
    c=normalize((sa-{lit})|(sb-{-lit}))
    if c is None:
     counts["tautology"]+=1;continue
    if len(c)>4:
     counts["too_wide"]+=1;continue
    if c in known:continue
    # Exact resolution is sound from original inputs.
    v=dict(lits=c,kind="derived",depth=depth,pivot=lit,
           parents=[list(a["lits"]),list(b["lits"])])
    known[c]=v;new.append(v)
    if len(generated)<20000:generated[c]=v
   if counts["pairs"]>120000:break
  counts[f"depth{depth}_generated"]=len(new)
  frontier=new[:2000]
  if not frontier or counts["pairs"]>120000:break
 # audit independent entailment by unit propagation on original CNF;
 # exact resolution certificates remain valid even when a resolvent is not RUP.
 original_list=[list(c) for c in original]
 derived=list(generated.values())
 for item in derived:
  item["rup_original"]=rup(original_list,item["lits"])
  item["subsumes_chain"]= [i+1 for i,c in enumerate(learned)
                               if 16<=i+1<=20 and set(item["lits"]).issubset(set(c))]
  item["shorter_than_parents"]=len(item["lits"])<max(map(len,item["parents"]))
 selected=sorted(derived,key=lambda x:(-len(x["subsumes_chain"]),len(x["lits"]),x["depth"]))[:60]
 counts["rup_original"]=sum(x["rup_original"] for x in derived)
 counts["subsumes_chain"]=sum(bool(x["subsumes_chain"]) for x in derived)
 counts["shorter_than_parents"]=sum(x["shorter_than_parents"] for x in derived)
 counts["empty_clause"]=sum(len(x["lits"])==0 for x in derived)
 result=dict(mode="retrospective_local_resolution_not_blind",
  source_clauses=len(original),seed_clauses=initial,shared_original_cids=sorted(source_ids),
  core_variables=sorted(core),summary=dict(counts),
  candidates=selected,generated_total=len(derived),
  chain_learned=[list(c) for c in learned[15:20]],
  note="Proof-valid resolvents may not reduce CDCL conflicts or runtime; full solver impact untested.")
 Path(output).write_text(json.dumps(result,indent=2,sort_keys=True))
 return result
