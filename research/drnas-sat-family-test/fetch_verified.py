#!/usr/bin/env python3
"""Fetch *only* preregistered SHA256-pinned ORIGINAL polynomial CNF instances.

No synthesized, renamed, re-ordered or modified CNF. Three publicly
documented >100MB size exclusions are never substituted. Solver results
must not affect dataset selection. Each holdout shard is disjoint.
"""
import argparse,hashlib,importlib.util,json
from pathlib import Path

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--manifest",required=True)
    p.add_argument("--group",choices=("pilot","holdout"),required=True)
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--shards",type=int,default=1)
    p.add_argument("--outdir",required=True)
    args=p.parse_args()
    if args.shards<1 or not 0<=args.shard<args.shards:
        raise ValueError("Invalid shard coordinates")
    spec=json.loads(Path(args.manifest).read_text())
    selected=[v for v in spec["samples"] if v["group"]==args.group and
                 v["source_validation"]["validation"]=="sha256_verified"]
    if args.group=="holdout":
        selected=[v for i,v in enumerate(selected) if i%args.shards==args.shard]
    root=Path(args.outdir).resolve();root.mkdir(parents=True,exist_ok=True)
    module=importlib.util.spec_from_file_location(
       "drnas_original_gbd_preflight",
       "research/drnas-sat-family-test/preflight.py")
    imp=importlib.util.module_from_spec(module)
    module.loader.exec_module(imp)
    output=dict(pilot=[],holdout=[],source="https://benchmark-database.de/",
                frozen_manifest=args.manifest,shard=args.shard,shards=args.shards,
                excluded_originals=[dict(hash=v["hash"],name=v["name"],
                   reason=v["source_validation"]["reason"])
                   for v in spec["samples"] if v["source_validation"]["validation"]=="excluded_size_only"])
    for v in selected:
        data,meta=imp.download(v,spec)
        freeze=v["source_validation"]
        if (len(data)!=freeze["bytes"] or
            hashlib.sha256(data).hexdigest()!=freeze["sha256"] or
            meta["variables"]!=freeze["variables"] or
            meta["clauses"]!=freeze["clauses"]):
            raise RuntimeError("FROZEN SOURCE MISMATCH "+v["name"])
        path=root/(v["hash"]+".cnf")
        path.write_bytes(data)
        record=dict(name=v["name"],hash=v["hash"],status=v["status"],
            family="polynomial-multiplication/"+v["author"],
            path=str(path),expected_sha256=freeze["sha256"],
            original_url=v["url"],variables=freeze["variables"],
            clauses=freeze["clauses"],original_bytes=freeze["bytes"])
        output[args.group].append(record)
        print("PINNED_AUTHENTIC "+v["name"]+" "+freeze["sha256"],flush=True)
    if not output[args.group]:
        raise RuntimeError("Empty frozen shard")
    (root/"source-verification.json").write_text(
        json.dumps(output,indent=2)+"\n",encoding="utf8")
    print("PREPARED "+str(len(output[args.group]))+" authentic original CNFs",flush=True)

if __name__=="__main__":main()
