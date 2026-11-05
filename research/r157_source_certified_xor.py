#!/usr/bin/env python3
"""R157 source-exact GF2 rows for CDCL live IPASIR-UP, no inferred parity.

Recover complete 2..6-literal parity CNF blocks and source unit assignments.
Apply units algebraically and emit only parity rows of length 2..6 (the
in-process source bridge's supported sizes). Rank by residual-CNF variable
frequency, frozen before solver timing. Prove every row as an original XOR
block plus original units; record original source SHA and selection.
"""
import argparse,collections,hashlib,json,pathlib
from collections import defaultdict
def need(ok,msg):
 if not ok:raise RuntimeError("R157_SOURCE_PROOF_REFUSED "+msg)
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def extract(source,rows_path,proof_path,max_rows=180):
 clauses=[];clause=[];n=None;declared=None
 for line in pathlib.Path(source).read_text().splitlines():
  if not line or line.startswith(("c","%")):continue
  if line.startswith("p "):
   a=line.split();need(len(a)==4 and a[1]=="cnf","invalid header")
   n=int(a[2]);declared=int(a[3]);continue
  for s in line.split():
   v=int(s)
   if v:clause.append(v)
   else:clauses.append(tuple(clause));clause=[]
 need(n is not None and not clause and len(clauses)==declared,"source CNF parse mismatch")
 units={};inconsistent=False
 for c in clauses:
  if len(c)!=1:continue
  v=abs(c[0]);bit=int(c[0]>0)
  if v in units and units[v]!=bit:inconsistent=True
  else:units[v]=bit
 groups=defaultdict(set)
 for c in clauses:
  if len(c)<2 or len(c)>6 or len({abs(x) for x in c})!=len(c):continue
  lit=sorted(c,key=abs);vs=tuple(abs(x) for x in lit)
  groups[vs].add(sum(1<<i for i,x in enumerate(lit) if x<0))
 raw=[];covered=set()
 for vs,masks in groups.items():
  k=len(vs)
  for maskparity,rhs in ((0,1),(1,0)):
   required={j for j in range(1<<k) if j.bit_count()%2==maskparity}
   if not required<=masks:continue
   raw.append((vs,rhs))
   covered.update((vs,mask) for mask in required)
 # Residual clauses exclude complete parity groups and explicit units.
 freq=collections.Counter()
 for c in clauses:
  if len(c)==1:continue
  lit=sorted(c,key=abs)
  k=len(c)
  if 2<=k<=6 and len({abs(x) for x in c})==k:
   vs=tuple(abs(x) for x in lit)
   mask=sum(1<<i for i,x in enumerate(lit) if x<0)
   if (vs,mask) in covered:continue
  freq.update(abs(v) for v in c)
 eligible=[];seen=set();unit_simplified=0
 for vs,rhs in raw:
  gone=[v for v in vs if v in units]
  remain=tuple(v for v in vs if v not in units)
  derived=rhs
  for v in gone:derived^=units[v]
  if gone:unit_simplified+=1
  # Skip unit rows (the CNF engine already handles native source units).
  if not 2<=len(remain)<=6:continue
  key=(remain,derived)
  if key in seen:continue
  seen.add(key)
  overlap=sum(min(freq[v],250) for v in remain)
  if overlap==0:continue
  impact=overlap/float(len(remain)*len(remain))
  eligible.append((impact,remain,derived,vs,rhs,gone))
 eligible.sort(key=lambda x:(-x[0],len(x[1]),x[1],x[2]))
 selected=eligible[:max_rows]
 rows_path=pathlib.Path(rows_path);rows_path.parent.mkdir(parents=True,exist_ok=True)
 rows_path.write_text("".join(f"{len(v)} {rhs} "+ " ".join(map(str,v))+"\n" for _,v,rhs,*_ in selected))
 evidence=dict(protocol="DRNAS-R157-SOURCE-CERTIFIED-LIVE-GF2-20261105-v1",
  source_sha256=sha(source),variables=n,clauses=len(clauses),
  source_complete_parity_equations=len(raw),units=len(units),
  inconsistent_source_units=inconsistent,source_unit_simplified=unit_simplified,
  usable_residual_linked_equations=len(eligible),selected_rows=len(selected),
  selected=[dict(vars=list(v),rhs=rhs,source_vars=list(source_vs),source_rhs=source_rhs,
    substituted_units=list(gone),residual_importance=round(score,4)) for score,v,rhs,source_vs,source_rhs,gone in selected],
  safety="Every selected row is source complete parity block XOR source unit clauses, no guessed pattern",
  source="Original 2025/2026 SHA-frozen R154 original mixed CNF, known development set")
 pathlib.Path(proof_path).write_text(json.dumps(evidence,sort_keys=True,indent=2)+"\n")
 print("R157_CERTIFIED_SOURCE",json.dumps({k:evidence[k] for k in ("source_sha256","source_complete_parity_equations","units","usable_residual_linked_equations","selected_rows")},sort_keys=True),flush=True)
 return evidence
if __name__=="__main__":
 a=argparse.ArgumentParser()
 a.add_argument("--cnf",required=True);a.add_argument("--rows",required=True);a.add_argument("--proof",required=True)
 arg=a.parse_args();extract(arg.cnf,arg.rows,arg.proof)
