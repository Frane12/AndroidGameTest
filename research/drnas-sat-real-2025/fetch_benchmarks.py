#!/usr/bin/env python3
"""Fetch unchanged, published SAT Competition 2025 benchmarks.
The pinned manifest links back to the GBD official instance service via a
hash-pinned external corpus list (mpizenberg/rocsat, pinned commit).
No generated, modified, or selected-by-runtime CNF appears in the benchmark.
"""
import argparse
import hashlib
import json
import lzma
import time
import urllib.request
from pathlib import Path

def download_exact(entry, out):
    url=entry["url"]
    last=None
    for attempt in range(3):
        try:
            request=urllib.request.Request(url,headers={"User-Agent":"DRNAS-SAT-real-benchmark/0.1 (research)"})
            with urllib.request.urlopen(request,timeout=40) as response:
                payload=response.read(3_000_000)
            if len(payload)>2_999_999:
                raise RuntimeError("Compressed input exceeded 3 MB")
            try:
                plain=lzma.decompress(payload,format=lzma.FORMAT_XZ,memlimit=100_000_000)
            except lzma.LZMAError as exc:
                raise RuntimeError("Source did not serve expected XZ-compressed original CNF") from exc
            if len(plain)!=entry["bytes"]:
                raise RuntimeError("Size mismatch for "+entry["name"])
            observed=hashlib.sha256(plain).hexdigest()
            if observed!=entry["sha256"]:
                raise RuntimeError(f"SHA256 mismatch for {entry['name']} {observed}")
            # Preserve original bytes exactly, no rewriting or normalization.
            out.write_bytes(plain)
            return dict(name=entry["name"],status=entry["status"],
                        family=entry["family"],expected_sha256=entry["sha256"],
                        observed_sha256=observed,original_url=url,
                        bytes=len(plain),source="SAT Competition 2025")
        except (OSError,RuntimeError,lzma.LZMAError) as err:
            last=err
            if attempt<2:time.sleep(2*(attempt+1))
    raise RuntimeError(f"Cannot retrieve authenticated public benchmark {entry['name']} from {url}: {last}")

def main(manifest,outdir):
    spec=json.loads(Path(manifest).read_text())
    root=Path(outdir)
    root.mkdir(parents=True,exist_ok=True)
    report={"source":spec["source_origin"],"source_commit":spec["source_commit"],
            "selection_rule":spec["selection_rule"],"pilot":[],"holdout":[]}
    for group in ("pilot","holdout"):
        target=root/group
        target.mkdir(parents=True,exist_ok=True)
        for idx,entry in enumerate(spec[group]):
            # Explicit fixed selection. Download failure is FATAL, no replacement.
            dest=target/entry["name"]
            meta=download_exact(entry,dest)
            meta["path"]=str(dest.resolve())
            report[group].append(meta)
            print(f"SHA256 verified {group} {idx+1}/{len(spec[group])} "
                  f"{entry['family']} {entry['status']}",flush=True)
    (root/"source-verification.json").write_text(json.dumps(report,indent=2))
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--manifest",required=True)
    p.add_argument("--outdir",required=True)
    args=p.parse_args()
    main(args.manifest,args.outdir)
