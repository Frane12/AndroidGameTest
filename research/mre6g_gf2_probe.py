#!/usr/bin/env python3
"""Hard-wall bounded (killable) MRE6g GF2/CNF certificate extractor.

Called in its own Python process and terminated by the parent if the
predeclared wall deadline expires. No child proof may be used unless
the independent parent replays it against the exact ORIGINAL CNF.
"""
from __future__ import annotations
import argparse,json,pathlib,sys,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r164_pure_exact_gf2 as exact
import mre1_cross_representation as mre1

def main():
    p=argparse.ArgumentParser()
    p.add_argument("source")
    p.add_argument("output")
    p.add_argument("--inner-budget",type=float,default=.35)
    args=p.parse_args()
    start=time.perf_counter()
    n,original=exact.parse_dimacs(pathlib.Path(args.source))
    rows,proofs,stats=mre1.derive(original,max_s=args.inner_budget)
    if not stats["proof_replayed"]:
        raise RuntimeError("MRE6G_BAD_GF2_PROOF_REPLAY")
    binary=[p for p in proofs if len(p["clause"])==2]
    result=dict(original_clause_count=len(original),
         original_vars=n,source_rows=rows,proofs=proofs,stats=stats,
         derived_binary=len(binary),
         total_child_wall_s=round(time.perf_counter()-start,6))
    pathlib.Path(args.output).write_text(json.dumps(result,sort_keys=True)+"\n")
    print("MRE6G_GF2_PROBE_PASS",json.dumps(dict(
       derived_binary=len(binary),source_rows=len(rows),
       wall=result["total_child_wall_s"]),sort_keys=True),flush=True)

if __name__=="__main__":main()
