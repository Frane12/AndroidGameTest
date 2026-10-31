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


def canonical_dimacs(data):
    """Copy identical SAT clauses into strict DIMACS.
    Historical SATLIB files can declare a wrong clause count.
    This only corrects the header; no clause/literal is modified.
    """
    declared_vars=None
    declared_clauses=None
    clauses=[]
    pending=[]
    for raw in data.splitlines():
        line=raw.strip()
        if not line:
            continue
        if line.startswith(b"c"):
            continue
        if line.startswith(b"p "):
            pieces=line.decode("ascii").split()
            if len(pieces)<4 or pieces[1].lower()!="cnf":
                raise ValueError("Invalid original DIMACS header")
            if declared_vars is not None:
                raise ValueError("Repeated DIMACS header")
            declared_vars=int(pieces[2])
            declared_clauses=int(pieces[3])
            continue
        if line.startswith(b"%"):
            break
        for word in line.split():
            try:
                lit=int(word)
            except ValueError as error:
                raise ValueError("Non-integer literal in original CNF") from error
            if lit==0:
                clauses.append(tuple(pending))
                pending=[]
            else:
                pending.append(lit)
    if pending:
        raise ValueError("Unterminated CNF clause")
    if declared_vars is None:
        raise ValueError("Missing CNF header")
    maxvar=max((abs(l) for cl in clauses for l in cl),default=0)
    if maxvar>declared_vars:
        raise ValueError("Original literal exceeds declared variable count")
    header=("p cnf %d %d\n"%(declared_vars,len(clauses))).encode("ascii")
    data=header+b"".join(
        b" ".join(str(l).encode("ascii") for l in cl)+b" 0\n"
        for cl in clauses
    )
    return data,{"declared_vars":declared_vars,
                 "declared_clauses":declared_clauses,
                 "canonical_clauses":len(clauses),
                 "header_corrected":declared_clauses!=len(clauses)}

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
                normalized=normal[name]
                payload,header_info=canonical_dimacs(normalized)
                if header_info["header_corrected"]:
                    # A mismatched clause count indicates incomplete or malformed
                    # historical CNF. Do not silently repair or substitute it.
                    out.append(("invalid_sources",dict(
                        name=filename,source_set=entry["set"],
                        intended_group=group,family=entry["family"],
                        declared_clauses=header_info["declared_clauses"],
                        actual_clauses=header_info["canonical_clauses"],
                        member_raw_sha256=originals[name],
                        normalized_sha256=sha(normalized),
                        archive_sha256=entry["archive_sha256"],
                        reason="source DIMACS clause count mismatch: cannot certify the intended original benchmark"
                    )))
                    continue
                dest.write_bytes(payload)
                out.append((group,dict(
                    name=filename,original_member=name,
                    family=entry["family"],status=entry["status"],
                    original_archive_url=entry["url"],
                    source="SATLIB external benchmark",
                    archive_sha256=entry["archive_sha256"],
                    member_raw_sha256=originals[name],
                    normalized_sha256=sha(normalized),
                    canonical_dimacs_header=header_info,
                    expected_sha256=sha(payload),
                    observed_sha256=sha(payload),
                    path=str(dest.resolve()),
                    normalization="Legacy SATLIB '%' trailer and line endings removed",
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
            "selection_rule":spec["selection_rule"],"pilot":[],"holdout":[],"invalid_sources":[]}
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
