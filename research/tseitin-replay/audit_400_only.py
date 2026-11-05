#!/usr/bin/env python3
"""Final fail-closed acquisition audit; NO SAT-solving or analytical ingestion."""
import csv,gzip,hashlib,json,pathlib,sys
ROOT=pathlib.Path("holdout-400")
KINDS=("official","external_application","external_xor","external_nonxor")
sha=lambda x:hashlib.sha256(x).hexdigest()
def main():
 if not pathlib.Path("research/sat-analytics-data/current/formulas.csv").is_file():raise RuntimeError("missing prior SQLite export")
 known=set()
 with open("research/sat-analytics-data/current/formulas.csv",newline="") as f:
  for row in csv.DictReader(f):
   for k,v in row.items():
    if "sha" in k.lower() and len(v or "")==64:known.add(v.lower())
 reports=[];allrows=[];errors=[];seen=set()
 for k in KINDS:
  f=ROOT/(k+".json")
  if not f.is_file():errors.append("missing "+str(f));continue
  r=json.loads(f.read_text());reports.append(r)
  if r.get("category")!=k or r.get("count")!=100 or len(r.get("formulas",[]))!=100 or r.get("status")!="COMPLETE":errors.append("incomplete "+k)
  for x in r.get("formulas",[]):
   h=x["sha256"];p=pathlib.Path(x["compressed_file"])
   if h in seen or h in known:errors.append("duplicate or historical SHA "+h)
   seen.add(h)
   try:
    if not p.is_file():raise RuntimeError("missing compressed CNF "+str(p))
    with gzip.open(p,"rb") as f:raw=f.read(8_000_001)
    if len(raw)>8_000_000 or sha(raw)!=h:raise RuntimeError("decompressed hash/size mismatch "+h)
    if len(raw)!=x["bytes"]:raise RuntimeError("raw byte mismatch "+h)
   except Exception as e:errors.append(str(e))
   allrows.append(x)
 if len(allrows)!=400 or len(seen)!=400:errors.append("not 400 SHA-distinct source files")
 master={"protocol":"DRNAS-400-PROSPECTIVE-20261105-v1","status":"COMPLETE" if not errors else "FAILED_AUDIT","count":len(allrows),"distribution":{x["category"]:sum(y["category"]==x["category"] for y in allrows) for x in allrows},"candidate_sha256":sorted(seen),"exclusion_historical_sha_count":len(known),"source_reports_sha256":{k:sha((ROOT/(k+".json")).read_bytes()) for k in KINDS if (ROOT/(k+".json")).is_file()},"errors":errors,"benchmark_executed":False,"sqlite_modified":False,"formulas":allrows}
 ROOT.mkdir(exist_ok=True)
 masterpath=ROOT/"manifest-400.json";masterpath.write_text(json.dumps(master,indent=2,sort_keys=True)+"\n")
 (ROOT/"manifest-400.sha256").write_text(sha(masterpath.read_bytes())+"  manifest-400.json\n")
 (ROOT/"audit.txt").write_text("Acquisition audit: "+master["status"]+"\nFormulas: "+str(len(allrows))+"\n"+"\n".join(errors)+"\n")
 print(json.dumps({"status":master["status"],"count":len(allrows),"errors":errors[:20],"manifest_sha256":sha(masterpath.read_bytes())},sort_keys=True),flush=True)
 if errors:sys.exit(3)
if __name__=="__main__":main()
