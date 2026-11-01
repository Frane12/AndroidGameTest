#!/usr/bin/env python3
"""Independent GF(2) certificate of 10 previously tested real Dubois SATLIB CNFs.

Each group of four 3-clauses forbidding four parity-incompatible assignments
is a Boolean XOR3 equation. Derive all constraints independently from original
CNFs and check one explicit contradictory XOR sum (0 = 1 mod 2). This is a
known structural property of Dubois benchmarks, not an original theorem.
"""
from __future__ import annotations
import collections,csv,hashlib,json
from pathlib import Path
from itertools import product
import v1531_satlib as legacy

CORPUS=Path("/tmp/satlib-go/testdata/satlib")
PIN="fc0e735aff48989326f256121b5ed6fc585858c3"
SHORT=Path("research/sat-analytics-data/short40/results.json")
OUT=Path("affine-logic-audit")
def sha(b):return hashlib.sha256(b).hexdigest()
def extract_xor3(clauses):
 groups=collections.defaultdict(set)
 for cl in clauses:
  if len(cl)!=3 or len(set(map(abs,cl)))!=3:raise RuntimeError("Nontriple clause")
  vs=tuple(sorted(map(abs,cl)))
  mask=sum(1<<i for i,v in enumerate(vs) if v in cl)
  groups[vs].add(mask)
 if 4*len(groups)!=len(clauses):
  raise RuntimeError("CNF not entirely built of four-clause XOR3 groups")
 out=[]
 for vs,masks in sorted(groups.items()):
  if len(masks)!=4:raise RuntimeError("Not four patterns per variable triple")
  parities={mask.bit_count()%2 for mask in masks}
  if len(parities)!=1:raise RuntimeError("Not an XOR3 parity quartet")
  parity=next(iter(parities))
  for values in product((0,1),repeat=3):
   clause_sat=all(any((values[j] if mask>>j&1 else 1-values[j])
                      for j in range(3)) for mask in masks)
   xor_sat=(sum(values)%2==parity)
   if clause_sat!=xor_sat:raise RuntimeError("CNF/XOR truth table mismatch")
  lhs=0
  for v in vs:lhs^=1<<(v-1)
  out.append({"vars":list(vs),"rhs":parity,"mask":lhs,"sign_patterns":sorted(masks)})
 return out
def prove(eqs,n):
 pivots={};rank=0
 for i,e in enumerate(eqs):
  lhs=e["mask"];rhs=e["rhs"];comb=1<<i
  for v in range(1,n+1):
   bit=1<<(v-1)
   if not(lhs&bit):continue
   if v in pivots:
    a,b,c=pivots[v];lhs^=a;rhs^=b;comb^=c
   else:
    pivots[v]=(lhs,rhs,comb);rank+=1;break
  else:
   if lhs==0 and rhs==1:
    index=[j for j in range(len(eqs)) if comb&(1<<j)]
    lhs2=0;rhs2=0
    for j in index:lhs2^=eqs[j]["mask"];rhs2^=eqs[j]["rhs"]
    if lhs2!=0 or rhs2!=1:raise RuntimeError("Contradiction certificate invalid")
    return rank,index
 raise RuntimeError("No GF(2) contradiction (cannot assert UNSAT)")
def main():
 OUT.mkdir(parents=True,exist_ok=True)
 d=json.loads(SHORT.read_text())
 rows=[m for m in d["manifest"] if m["family"]=="dubois_unsat"]
 if len(rows)!=10:raise RuntimeError("Expected ten real Dubois formulas")
 results=[];certificate={}
 for r in rows:
  src=CORPUS/r["source"]
  raw=src.read_bytes()
  got,clean,n,clauses,trailer=legacy.normalize_satlib(src)
  if got!=raw or sha(raw)!=r["sha256_source"] or sha(clean)!=r["sha256_normalized"]:
   raise RuntimeError("Source SHA drift "+str(src))
  eq=extract_xor3(clauses)
  rank,indices=prove(eq,n)
  k=n//3
  if n!=3*k or len(clauses)!=8*k or len(eq)!=2*k or rank!=2*k-1 or len(indices)!=2*k:
   raise RuntimeError("Unexpected structure on "+str(src))
  row={"file":r["source"],"sha256":sha(clean),
     "nvars":n,"clauses":len(clauses),"xor_equations":len(eq),
     "rank_coeff":rank,"rank_augmented":rank+1,
     "contradictory_equation_count":len(indices),
     "cnf_xor_equivalence_checked":True,"certificate_verified":True}
  results.append(row)
  certificate[r["source"]]={"equations":[{"variables":eq[i]["vars"],"rhs":eq[i]["rhs"]} for i in indices],
    "xor_sum_lhs":"zero_vector","xor_sum_rhs":1}
 if len({x["sha256"] for x in results})!=10:raise RuntimeError("Duplicate formula")
 summary={"reference":"Original SATLIB Dubois UNSAT, previously measured V15.3.1 external short40",
   "source_repo":"mitchellh/go-sat","pinned_commit":PIN,
   "all_cnf_hashes_verified":True,
   "all_ten_gf2_contradictions_proved":True,
   "family_law":"For these ten Dubois k instances: variables=3k, clauses=8k, XOR3 equations=2k; coefficient rank=2k-1, augmented rank=2k.",
   "proof":"Four CNF clauses per triple encode x^y^z=b; summing a dependent subset yields lhs=0 and rhs=1 modulo 2.",
   "scope":"Known Dubois structure, not novel proof that arbitrary SAT can be solved by linear algebra.",
   "cases":results,
   "certificates":certificate}
 (OUT/"affine_certificates.json").write_text(json.dumps(summary,indent=2)+"\n")
 with (OUT/"affine_summary.csv").open("w",newline="") as f:
  w=csv.DictWriter(f,fieldnames=list(results[0]));w.writeheader();w.writerows(results)
 report=["# DRNAS SAT — independent parity proof for 10 external Dubois formulas",
  "Original CNFs pinned at "+PIN+"; all raw and normalized SHA256 values match the V15.3.1 measured manifest.",
  "",
  "For these examples named dubois(k), n = 3k variables; m = 8k clauses;",
  "there are exactly 2k independent-*looking* XOR3 constraint rows but",
  "rank(A) = 2k−1 and rank([A|b]) = 2k. Their combined equations yield",
  "**0=1 in GF(2)**, a checkable UNSAT certificate.",
  "Every quadruple of CNF clauses was checked against the corresponding",
  "XOR3 truth table over all eight assignments.",
  "",
  "| Formula | Vars | Clauses | XOR equations | rank A | rank [A|b] | Certificate equations |",
  "|---|---:|---:|---:|---:|---:|---:|"]
 for r in results:
  report.append(f"| {Path(r['file']).name} | {r['nvars']} | {r['clauses']} | {r['xor_equations']} | {r['rank_coeff']} | {r['rank_augmented']} | {r['contradictory_equation_count']} |")
 report.extend(["","**Scope:** This demonstrates the known hidden parity structure of this selected benchmark family; it is not a new mathematical theorem or general SAT breakthrough.",
 "The certificate is independently reconstructible from public original clauses and does not rely on trusting solver status."])
 (OUT/"report.md").write_text("\n".join(report)+"\n")
 print("\n".join(report),flush=True)
if __name__=="__main__":main()
