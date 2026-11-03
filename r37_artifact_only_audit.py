#!/usr/bin/env python3
"""R37 no-solver rerun: audit new R36 passive scans against frozen official cohort."""
import argparse,json
from pathlib import Path
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--manifest",required=True);p.add_argument("--root",required=True)
 p.add_argument("--out",required=True)
 a=p.parse_args()
 manifest=json.loads(Path(a.manifest).read_text())
 cohort={c["id"]:c for c in manifest["cases"]}
 assert len(cohort)==12 and len(manifest["cases"])==12
 records={}
 for shard in range(4):
  path=Path(a.root)/("shadow-"+str(shard))/"shadow.json"
  rows=json.loads(path.read_text())
  assert len(rows)==3,(shard,len(rows))
  for row in rows:
   ident=row["case_id"]
   assert ident in cohort and ident not in records,ident
   expected=cohort[ident]
   assert row["sha256"]==expected["sha256"],("sha",ident)
   assert row["official_label"]==expected["official_label"],("label",ident)
   assert row["scanned_clauses"]>0
   assert row["mode"]=="shadow_only" and row["solver_interventions"]==0
   assert row["certified_binary_units"]>=0
   records[ident]=row
 assert set(records)==set(cohort)
 summary={
 "protocol":"R37 artifact-only postprocessing of frozen official 2026 12 CNFs",
 "original_solver_run":41632056202,
 "reran_solver":False,
 "n_official_cases":12,
 "sha_matches":12,
 "n_passive_scan_records":len(records),
 "xor_present":sum(r["xor_variables"]>0 for r in records.values()),
 "binary_units_certified":sum(r["certified_binary_units"] for r in records.values()),
 "mean_scan_elapsed_s":sum(r["elapsed_s"] for r in records.values())/12,
 "truncated_scan_count":sum(bool(r["truncated"]) for r in records.values()),
 "caution":"No active solver XOR intervention was tested, hence no R36 or R37 speedup claim."
 }
 Path(a.out).write_text(json.dumps({"summary":summary,"cases":list(records.values())},indent=2)+"\n")
 print("R37_ARTIFACT_ONLY_AUDIT_PASS",json.dumps(summary,sort_keys=True),flush=True)
if __name__=="__main__":main()
