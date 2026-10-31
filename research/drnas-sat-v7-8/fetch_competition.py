#!/usr/bin/env python3
"""Fetch pinned original SAT Competition 2025 CNFs for V7.8 independent shards.

Delegates exact XZ bytes / SHA256 checks to the previously vetted V7.2.1
source fetcher. Never substitutes a missing file. Pilot frozen separately.
"""
import argparse,importlib.util,json
from pathlib import Path
def main(args):
    spec=json.loads(Path(args.manifest).read_text())
    root=Path(args.outdir).resolve()
    root.mkdir(parents=True,exist_ok=True)
    old=Path("research/drnas-sat-real-2025/fetch_benchmarks.py")
    module=importlib.util.spec_from_file_location("drnas_original_2025_fetch",old)
    imp=importlib.util.module_from_spec(module)
    module.loader.exec_module(imp)
    if args.shards<1 or not 0<=args.shard<args.shards:
        raise ValueError("Shard index invalid")
    d=dict(source=spec["source_origin"],
        source_commit=spec["source_commit"],selection_rule=spec["selection_rule"],
        pilot=[],holdout=[],shard=args.shard,shard_count=args.shards)
    for group in ("pilot","holdout"):
        items=spec[group]
        if group=="holdout":
            items=[] if args.pilot_only else [c for idx,c in enumerate(items) if idx%args.shards==args.shard]
        elif not args.pilot_only:
            items=[]
        target=root/group
        target.mkdir(parents=True,exist_ok=True)
        for row in items:
            path=target/row["name"]
            got=imp.download_exact(row,path)
            got["path"]=str(path)
            d[group].append(got)
            print(f"AUTHENTICATED {group} {row['name']} {row['status']} "
                  f"SHA256={got['observed_sha256']}",flush=True)
    (root/"source-verification.json").write_text(json.dumps(d,indent=2)+"\n")
    if not d["pilot"] and not d["holdout"]:
        raise RuntimeError("Empty competition shard")
if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--manifest",required=True)
    p.add_argument("--outdir",required=True)
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--shards",type=int,default=1)
    p.add_argument("--pilot-only",action="store_true",help="Only fetch two frozen pilot instances")
    main(p.parse_args())
