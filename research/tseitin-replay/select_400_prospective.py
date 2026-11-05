#!/usr/bin/env python3
"""Offline manifest selection ONLY. Does not execute SAT solvers or ingest SQLite."""
import argparse,csv,hashlib,json,pathlib,sys
from collections import Counter

CATEGORIES=("official","external_application","external_xor","external_nonxor")
QUOTA={x:100 for x in CATEGORIES}
def sha(b): return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--candidates",required=True,help="CSV with path,source_url,source_set,source_year,category,source_commit,source_sha256")
 p.add_argument("--historical",required=True,help="Cumulative formulas.csv from last successful SQLite snapshot")
 p.add_argument("--additional-known",action="append",default=[],help="CSV with SHA256 column(s), including R115/R117/R124/R130/R131/R132")
 p.add_argument("--out",required=True)
 a=p.parse_args()
 known=set()
 for fn in [a.historical]+a.additional_known:
  with open(fn,newline="") as f:
   for row in csv.DictReader(f):
    for k,v in row.items():
     if "sha" in k.lower() and v and len(v.strip())==64:
      known.add(v.strip().lower())
 selected={k:[] for k in CATEGORIES}; seen=set(); rejected=Counter()
 with open(a.candidates,newline="") as f:
  rows=list(csv.DictReader(f))
 # Stable selection independent of runtime or outcome.
 rows.sort(key=lambda r:(r.get("category",""),r.get("source_set",""),r.get("source_url",""),r.get("path","")))
 for row in rows:
  cat=row.get("category","")
  if cat not in selected: rejected["unknown_category"]+=1;continue
  if len(selected[cat])>=QUOTA[cat]: continue
  if not row.get("source_url") or not row.get("source_set") or not row.get("source_commit"): rejected["missing_provenance"]+=1;continue
  if cat=="official" and not row.get("source_year"): rejected["official_without_year"]+=1;continue
  path=pathlib.Path(row.get("path",""))
  if not path.is_file(): rejected["missing_file"]+=1;continue
  b=path.read_bytes(); digest=sha(b)
  if digest!=row.get("source_sha256","").lower(): rejected["checksum_mismatch"]+=1;continue
  if digest in known: rejected["previously_seen"]+=1;continue
  if digest in seen: rejected["duplicate"]+=1;continue
  if not b.lstrip().startswith((b"c",b"p cnf")): rejected["invalid_dimacs_header"]+=1;continue
  seen.add(digest)
  selected[cat].append({**row,"sha256":digest,"bytes":len(b),"classification":"prospective_test_unseen"})
 output={"protocol":"drnas-five-step-v1","selection":"sorted_source_metadata_no_runtime","quota":QUOTA,"counts":{k:len(v) for k,v in selected.items()},"rejected":dict(rejected),"historical_hash_count":len(known),"formulas":[v for k in CATEGORIES for v in selected[k]],"status":"COMPLETE" if all(len(selected[k])==QUOTA[k] for k in CATEGORIES) else "INCOMPLETE"}
 out=pathlib.Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
 out.write_text(json.dumps(output,indent=2,sort_keys=True)+"\n")
 (out.parent/(out.name+".sha256")).write_text(sha(out.read_bytes())+"  "+out.name+"\n")
 print(json.dumps({"status":output["status"],"counts":output["counts"],"rejected":output["rejected"]}))
 if output["status"]!="COMPLETE":sys.exit(2)
if __name__=="__main__":main()
