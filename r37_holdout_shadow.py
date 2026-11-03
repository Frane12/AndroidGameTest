#!/usr/bin/env python3
"""R37 passive R36 binary-path proof scan on independently frozen official cases."""
import argparse,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent/"research/drnas-sat-v7-8"))
sys.path.insert(0,str(Path(__file__).resolve().parent/"experiments/drnas_v16"))
from official_v94_select import download_and_features
from r36_binary_xor_proofs import scan
def main():
 p=argparse.ArgumentParser()
 p.add_argument("--manifest",required=True);p.add_argument("--shard",type=int,required=True)
 p.add_argument("--out",required=True);a=p.parse_args()
 m=json.loads(Path(a.manifest).read_text());assert len(m["cases"])==12 and 0<=a.shard<4
 cases=m["cases"][a.shard*3:(a.shard+1)*3];rows=[]
 out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
 for case in cases:
  dest=out/(case["id"]+".cnf")
  try:
   check=download_and_features(case["id"],dest)
   assert check["sha256"]==case["sha256"],"CNF SHA drift"
   assert check["features"]==case["features"],"CNF feature drift"
   row=scan(dest)
   row["case_id"]=case["id"];row["sha256"]=case["sha256"];row["official_label"]=case["official_label"]
   rows.append(row)
   print("R37_REAL_FORMULA",json.dumps({k:v for k,v in row.items() if k!="proofs"},sort_keys=True),flush=True)
  finally:dest.unlink(missing_ok=True)
 assert len(rows)==3
 (out/"shadow.json").write_text(json.dumps(rows,indent=2)+"\n")
 print("R37_SHADOW_SHARD_PASS",a.shard,len(rows),flush=True)
if __name__=="__main__":main()
