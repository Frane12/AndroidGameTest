#!/usr/bin/env python3
"""SHA256 preflight of ORIGINAL independent GBD polynomial-multiplication CNFs.

This step deliberately does NOT run a solver. Reports original CNF bytes,
SHA256 and DIMACS header before any empirical measurements are performed.
No generated, permuted, relabeled or repaired benchmark is accepted.
"""
import argparse,hashlib,json,lzma,re,time,urllib.request
from pathlib import Path

def download(row,manifest):
    last=None
    for attempt in range(3):
        try:
            request=urllib.request.Request(row["url"],headers={
              "User-Agent":"DRNAS-SAT-authenticated-family-validation/1.0"})
            with urllib.request.urlopen(request,timeout=55) as resp:
                compressed=resp.read(manifest["max_compressed_bytes"]+1)
            if len(compressed)>manifest["max_compressed_bytes"]:
                raise ValueError("Compressed original exceeds preregistered cap")
            # GBD serves exact archived XZ-compressed original CNF bytes.
            original=lzma.decompress(compressed,format=lzma.FORMAT_XZ,
                                    memlimit=250_000_000)
            if len(original)>manifest["max_plain_bytes"]:
                raise ValueError("Uncompressed original exceeds preregistered cap")
            header=re.search(rb"(?m)^p[ \t]+cnf[ \t]+([0-9]+)[ \t]+([0-9]+)[ \t]*\r?$",original)
            if not header:
                raise ValueError("Original CNF missing strict DIMACS p cnf header")
            v,m=map(int,header.groups())
            if v<=0 or m<=0:
                raise ValueError("Nonpositive DIMACS dimensions")
            return original,dict(
               hash=row["hash"],name=row["name"],group=row["group"],
               status=row["status"],author=row["author"],
               sha256=hashlib.sha256(original).hexdigest(),
               compressed_sha256=hashlib.sha256(compressed).hexdigest(),
               compressed_bytes=len(compressed),original_bytes=len(original),
               variables=v,clauses=m,url=row["url"])
        except (OSError,ValueError,lzma.LZMAError,EOFError) as exc:
            last=exc
            if attempt<2:time.sleep(2*(attempt+1))
    raise RuntimeError(f"Original source cannot be authenticated: {row['name']} ({row['hash']}): {last}")

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--manifest",required=True)
    a.add_argument("--shard",required=True,type=int)
    a.add_argument("--shards",required=True,type=int)
    a.add_argument("--outdir",required=True)
    args=a.parse_args()
    spec=json.loads(Path(args.manifest).read_text())
    root=Path(args.outdir).resolve();root.mkdir(parents=True,exist_ok=True)
    entries=[row for i,row in enumerate(spec["samples"]) if i%args.shards==args.shard]
    outcome=dict(shard=args.shard,expected=len(entries),preflight=[],excluded_for_size=[])
    for idx,row in enumerate(entries):
        try:
            raw,meta=download(row,spec)
        except RuntimeError as exc:
            # Only predeclared size-cap exclusions are allowed here.
            # All actual download/hash/format failures remain fatal.
            if "exceeds preregistered cap" not in str(exc):
                raise
            outcome["excluded_for_size"].append(dict(
                name=row["name"],hash=row["hash"],reason=str(exc),
                size_cap_bytes=spec["max_plain_bytes"]))
            print("EXCLUDED_SIZE_LIMIT "+row["name"]+" "+str(exc),flush=True)
            continue
        target=root/(row["hash"]+".cnf")
        target.write_bytes(raw)
        outcome["preflight"].append(meta)
        print(f"VERIFIED {idx+1}/{len(entries)} {row['name']} "
              f"known={row['status']} vars={meta['variables']} "
              f"clauses={meta['clauses']} bytes={len(raw)} "
              f"SHA256={meta['sha256']}",flush=True)
    (root/"preflight.json").write_text(json.dumps(outcome,indent=2)+"\n")
    if len(outcome["preflight"])+len(outcome["excluded_for_size"])!=len(entries):
        raise RuntimeError("Incomplete preregistered source set")
if __name__=="__main__":main()
