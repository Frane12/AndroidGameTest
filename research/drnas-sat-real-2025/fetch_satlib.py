#!/usr/bin/env python3
"""Fetch original public SATLIB benchmark archives, verify SHA256, preserve
content identity, normalize only SATLIB's documented trailing '%' marker and
line endings, and deterministically choose fixed pilot+holdout CNFs.
"""
import argparse
import hashlib
import io
import json
import re
import tarfile
import time
import urllib.request
from pathlib import Path

SAFE=re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*\Z")
def sha(data):return hashlib.sha256(data).hexdigest()
def normalized_satlib(data):
    # Identical normalization used in pinned rocsat SATLIB corpus; not
    # CNF preprocessing. Only strips non-DIMACS '%' trailer / line endings.
    lines=[]
    for line in data.splitlines():
        if line.startswith(b"%"):break
        lines.append(line)
    return b"\n".join(lines)+b"\n"

def fetch_one(entry,target):
    last=None
    for attempt in range(3):
        try:
            request=urllib.request.Request(entry["url"],headers={"User-Agent":"DRNAS-SAT-independent-benchmark/0.1"})
            with urllib.request.urlopen(request,timeout=50) as response:
                blob=response.read(15_000_000)
            if len(blob)>=15_000_000:
                raise RuntimeError("Compressed archive exceeded safety cap")
            observed=sha(blob)
            if observed!=entry["archive_sha256"]:
                raise RuntimeError(f"Archive SHA256 mismatch on {entry['set']}: {observed}")
            originals={}
            normal={}
            with tarfile.open(fileobj=io.BytesIO(blob),mode="r:gz") as archive:
                for member in archive.getmembers():
                    if not member.isfile() or not member.name.lower().endswith(".cnf"):
                        continue
                    name=Path(member.name).name
                    if not SAFE.fullmatch(name) or name in normal:
                        raise RuntimeError(f"Unsafe or duplicate CNF basename: {name}")
                    extracted=archive.extractfile(member)
                    if extracted is None:raise RuntimeError("Cannot extract "+name)
                    original=extracted.read()
                    originals[name]=sha(original)
                    normal[name]=normalized_satlib(original)
            if len(normal)!=entry["count"]:
                raise RuntimeError(f"Expected {entry['count']} CNFs, got {len(normal)}")
            if sum(map(len,normal.values()))!=entry["expected_total_normalized_bytes"]:
                raise RuntimeError("Extracted normalized bytes mismatch on "+entry["set"])
            selected=sorted(normal)[:5]  # FIRST pilot, NEXT up to 4 holdout.
            if len(selected)<2:raise RuntimeError("Archive has too few CNFs")
            out=[]
            for i,name in enumerate(selected):
                group="pilot" if i==0 else "holdout"
                # Names namespaced with archive identity to avoid collisions.
                filename=f"{entry['set']}__{name}"
                dest=target/group/filename
                dest.parent.mkdir(parents=True,exist_ok=True)
                payload=normal[name]
                dest.write_bytes(payload)
                out.append((group,dict(
                    name=filename,original_member=name,
                    family=entry["family"],status=entry["status"],
                    original_archive_url=entry["url"],
                    source="SATLIB external benchmark",
                    archive_sha256=entry["archive_sha256"],
                    member_raw_sha256=originals[name],
                    normalized_sha256=sha(payload),
                    expected_sha256=sha(payload),
                    observed_sha256=sha(payload),
                    path=str(dest.resolve()),
                    normalization="Only SATLIB '%' trailer and line endings removed",
                    bytes=len(payload))))
            return out
        except (OSError,RuntimeError,tarfile.TarError) as exc:
            last=exc
            if attempt<2:time.sleep(3*(attempt+1))
    raise RuntimeError(f"Cannot fetch original SATLIB archive {entry['set']}: {last}")

def main(spec_path,outdir):
    spec=json.loads(Path(spec_path).read_text())
    out=Path(outdir).resolve()
    out.mkdir(parents=True,exist_ok=True)
    report={"source":spec["source_corpus"],"source_commit":spec["source_commit"],
            "selection_rule":spec["selection_rule"],"pilot":[],"holdout":[]}
    for idx,entry in enumerate(spec["archives"]):
        selected=fetch_one(entry,out)
        for group,record in selected:report[group].append(record)
        print(f"Verified SATLIB archive {idx+1}/{len(spec['archives'])} "
              f"{entry['set']} selected={len(selected)}",flush=True)
    (out/"source-verification.json").write_text(json.dumps(report,indent=2))
    print(f"SATLIB fixed pilot={len(report['pilot'])}, holdout={len(report['holdout'])}",flush=True)
    return report

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--manifest",required=True)
    p.add_argument("--outdir",required=True)
    args=p.parse_args()
    main(args.manifest,args.outdir)
