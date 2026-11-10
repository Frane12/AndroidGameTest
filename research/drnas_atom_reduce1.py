#!/usr/bin/env python3
"""ATOM-REDUCE1: bounded resolution audit, strictly offline, no feedback to solver.

Proof checks:
  (a) exact binary resolution on two CDCL-learned clauses;
  (b) RUP using ORIGINAL CNF alone, or ORIGINAL + earlier learned clauses.
RUP is checked by fixed-point unit propagation of negated candidate.
Candidates are NOT injected into CDCL or used to select original input.
"""
import itertools,json
from pathlib import Path

def normalize(seq):
 s=set(seq)
 if any(-x in s for x in s):return None
 return tuple(sorted(s,key=lambda x:(abs(x),x)))

def rup(clauses,candidate):
 # CNF & neg(candidate) must UP-reach conflict.
 assignment={}
 for lit in candidate:
  v=abs(lit);want=lit<0
  if v in assignment and assignment[v]!=want:return True
  assignment[v]=want
 while True:
  changed=False
  for clause in clauses:
   rem=[]
   sat=False
   for lit in clause:
    val=assignment.get(abs(lit))
    if val is None:rem.append(lit)
    elif val==(lit>0):sat=True;break
   if sat:continue
   if not rem:return True
   if len(rem)==1:
    lit=rem[0];v=abs(lit);want=lit>0
    if v in assignment:
     if assignment[v]!=want:return True
    else:
     assignment[v]=want;changed=True
  if not changed:return False

def analyze(original,learned,group_start=16,group_end=20):
 # every earlier learned clause is a consequence, but prefix matters:
 # compare candidates to the exact knowledge available before the chain.
 prefix=original+learned[:group_start-1]
 prior={normalize(c) for c in prefix}
 pair_count=0;taut=0;candidates={}
 for i in range(group_start-1,min(group_end,len(learned))):
  for j in range(i):
   a=set(learned[i]);b=set(learned[j])
   for p in sorted(a):
    if -p not in b:continue
    pair_count+=1
    result=normalize((a-{p})|(b-{-p}))
    if result is None:taut+=1;continue
    if result in prior:continue
    if len(result)>=min(len(a),len(b)):continue
    key=result
    if key not in candidates or (i+1,j+1)<(candidates[key]["parents"][0],candidates[key]["parents"][1]):
     candidates[key]=dict(clause=list(result),parents=[i+1,j+1],pivot=p,width=len(result),parent_widths=[len(a),len(b)])
 selected=sorted(candidates.values(),key=lambda x:(x["width"],x["parents"]))
 verified=[]
 for item in selected:
  c=item["clause"]
  item["rup_original"]=rup(original,c)
  item["rup_prechain"]=rup(prefix,c)
  item["subsumes_original"]=sum(set(c).issubset(set(o)) for o in original)
  item["subsumes_prechain_learned"]=sum(set(c).issubset(set(o)) for o in learned[:group_start-1])
  # Exact resolution itself certifies entailment from already verified parents;
  # RUP is an additional independent check, not a precondition for resolution.
  verified.append(item)
 summary=dict(group=[group_start,group_end],original_clauses=len(original),
  earlier_learned=len(learned[:group_start-1]),learned_total=len(learned),
  considered_resolutions=pair_count,tautologies=taut,
  shorter_unique_resolvents=len(verified),
  rup_original=sum(x["rup_original"] for x in verified),
  rup_prechain=sum(x["rup_prechain"] for x in verified),
  subsumes_original_candidates=sum(x["subsumes_original"]>0 for x in verified),
  minimum_candidate_width=min((x["width"] for x in verified),default=None))
 return dict(summary=summary,candidates=verified[:80])

def from_trace(trace,cnf,output):
 learned=[]
 for line in Path(trace).read_text().splitlines():
  if "kind=learn " not in line:continue
  t=dict(p.split("=",1) for p in line.split() if "=" in p)
  learned.append([int(x) for x in t["clause"].split(",")])
 original=[]
 for line in Path(cnf).read_text().splitlines():
  if not line or line.startswith(("c","p","%")):continue
  nums=[int(x) for x in line.split()]
  assert nums[-1]==0
  original.append(nums[:-1])
 result=analyze(original,learned,16,20) if len(learned)>=20 else analyze(original,learned,1,min(len(learned),5))
 result["source_trace"]=str(trace)
 Path(output).write_text(json.dumps(result,sort_keys=True,indent=2))
 return result
