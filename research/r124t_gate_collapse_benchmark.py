#!/usr/bin/env python3
"""R124T: exploit R124's verified source gates by replacing redundant gate
definitions, NOT adding clauses to unchanged CNFs like R125.
The C++ pass may remove a fully witnessed target gate block only when a
source-proven equivalent representative block remains and two equivalence
clauses replace the removed 3/4 original clauses.
All changes are independently reconstructed from the original source and
16-assignment Boolean proofs before original Kissat is run. SAT models are
checked against the unchanged original input. Timeout includes preprocessing.
New external holdout excludes all R120/R121/R122/R123/R125 source identities.
"""
from __future__ import annotations
import argparse,csv,json,pathlib,re,subprocess
import r125_native_gate_benchmark as core

core.ROOT=pathlib.Path("r124t")
core.PROTO="DRNAS-R124T-PROVEN-GATE-COLLAPSE-20261105-v1"
core.NATIVE=pathlib.Path("r124t/r124t_native").resolve()
core.SOURCES={
 "miter":(core.SOURCES["miter"][0],30),
 "official2026":(core.SOURCES["official2026"][0],60),
}
_original_prior=core.prior

def prior():
 seen,ids,report=_original_prior()
 path=core.ROOT/"prior"/"r125"/"manifest.json"
 if not path.is_file():
  raise RuntimeError("R124T_MISSING_R125_PREVIOUSLY_USED_HOLDOUT")
 manifest=json.loads(path.read_text())
 cases=manifest["cases"]
 assert len(cases)>=80,("R125_INCOMPLETE_PRIOR_LEDGER",len(cases))
 for c in cases:
  seen.add(c["sha256"])
  for key in ("gbd","url"):
   if c.get(key):
    ids.add(c[key].rsplit("/",1)[-1].split("?")[0])
 report["r125"]=core.sha_file(path)
 return seen,ids,report
core.prior=prior

def native(source,out="-",proof="-",timeout=6):
 core.get_binary()
 run=subprocess.run([str(core.NATIVE),str(source),str(out),str(proof)],
   capture_output=True,text=True,timeout=timeout)
 if run.returncode:
  raise RuntimeError("R124T_NATIVE_EXIT "+str(run.returncode)+" "+run.stdout[-300:]+run.stderr[-500:])
 found=re.findall(r"^R124T_SUMMARY (\{.*\})$",run.stdout,re.M)
 if len(found)!=1:
  raise RuntimeError("R124T_NATIVE_SUMMARY_MISSING "+run.stdout[-400:])
 result=json.loads(found[0])
 detail=re.findall(r"^R124T_COLLAPSE_DETAIL (\{.*\})$",run.stdout,re.M)
 if result["equivalence_pairs"]:
  if out!="-":
   assert len(detail)==1,("MISSING_COLLAPSE_DETAIL",str(source))
   report=json.loads(detail[0])
   assert report["dropped_clauses"]>report["added_equivalence_clauses"]
   result["removed_gate_clauses"]=report["dropped_clauses"]
   result["net_clauses_saved"]=report["dropped_clauses"]-report["added_equivalence_clauses"]
 else:
  assert not detail,("FALSE_COLLAPSE_DETAIL",str(source))
 return result
core.native=native

def verify_transform(original,transformed,certificate):
 """Recreate exact transformation without trusting native transformation code.
 Each removed target gate must be independently witnessed in original source;
 its claimed normalized output equality is exhaustively checked on <=4 vars.
 Each leader gate remains intact after all removals.
 """
 n,source=core.parse_dimacs(original.read_bytes())
 n2,destination=core.parse_dimacs(transformed.read_bytes())
 assert n==n2,("CHANGED_VARIABLE_DIMENSIONS",str(original))
 with open(certificate,newline="") as f:
  rows=list(csv.DictReader(f,delimiter="\t"))
 assert rows,("R124T_MISSING_CERTIFICATE",str(certificate))
 removed=set();protected=set();added=[];outputs=set()
 for row in rows:
  op1,a1,b1,z1=row["op1"],int(row["a1"]),int(row["b1"]),int(row["z1"])
  op2,a2,b2,z2=row["op2"],int(row["a2"]),int(row["b2"]),int(row["z2"])
  rec=(op1,a1,b1,z1,op2,a2,b2,z2,int(row["q1"]),int(row["q2"]))
  if abs(z2) in outputs:
   raise AssertionError(("TARGET_OUTPUT_REMOVED_TWICE",abs(z2)))
  outputs.add(abs(z2))
  # Independent 16-row semantic proof based on clauses present in original.
  added.extend(core.verify_pair_semantics(rec,source))
  left=set(core.gate_requirements(op1,a1,b1,z1))
  right=set(core.gate_requirements(op2,a2,b2,z2))
  assert len(left) in (3,4) and len(right) in (3,4)
  assert not left.intersection(removed),("LEADER_ALREADY_DELETED",rec)
  assert not right.intersection(protected.union(removed)),("CLAUSE_PROTECTION_CONFLICT",rec)
  protected.update(left)
  removed.update(right)
 orig=[tuple(sorted(cl)) for cl in source]
 modified=[tuple(sorted(cl)) for cl in destination]
 expected=[cl for cl in orig if cl not in removed]+added
 assert modified==expected,("DIFFERENT_FROM_SOURCE_CERTIFIED_TRANSFORM",str(original))
 assert protected.issubset(set(modified)),("LOST_LEADER_WITNESS",str(original))
 assert len(orig)>len(expected),("NO_CLAUSE_COUNT_REDUCTION",str(original))
 count_removed=len(orig)-len([cl for cl in orig if cl not in removed])
 return dict(derived_pairs=len(rows),derived_clauses=len(added),
   removed_clauses=count_removed,net_clauses_saved=count_removed-len(added),
   proof="independent_original_gate_clause_16_row_boolean_implication_and_exact_CNF_diff")
core.verify_augmentation=verify_transform

def aggregate():
 core.aggregate()
 target=core.ROOT/"results.json"
 report=json.loads(target.read_text())
 report["protocol"]=core.PROTO
 report["experiment_type"]="source-proven local redundant XOR/AND/OR gate definition collapse: remove 3-4 certified clauses; add 2 signed equivalence clauses"
 report["original_formula_unchanged"]=False
 report["original_source_preserved_separately_for_audit"]=True
 report["source_proof"]="independent 16-assignment proof per replacement, exact source CNF diff and retained leader witnesses"
 report["unsat_caveat"]="Equisatisfiability of each local rewrite follows from retained source gate truth tables; no independent solver UNSAT search certificate checked."
 report["failure_rule"]="No native activation does not imply speedup; all native scanning, proof and Kissat times count against same 15s per solver; promote only after positive independent paired PAR2."
 target.write_text(json.dumps(report,indent=2)+"\n")
 print("R124T_FINAL",json.dumps(report),flush=True)

def main():
 ap=argparse.ArgumentParser()
 ap.add_argument("command",choices=("control","freeze","monitor","benchmark","aggregate"))
 ap.add_argument("--shard",type=int,default=0)
 a=ap.parse_args()
 if a.command=="control":core.control()
 elif a.command=="freeze":core.freeze()
 elif a.command=="monitor":core.monitor(a.shard)
 elif a.command=="benchmark":core.benchmark(a.shard)
 else:aggregate()

if __name__=="__main__":main()
