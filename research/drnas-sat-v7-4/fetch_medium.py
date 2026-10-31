#!/usr/bin/env python3
"""Fetch and validate authentic SATLIB archives with frozen, hash-based selection.

Every archive is SHA256 pinned. Every original member is recorded with SHA256.
The only allowed data normalization is removal of SATLIB '%' terminal and
line ending harmonization. NO clause/header repairs. Malformed selected
sources are quarantined, counted, and never replaced.
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

SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._+-]*\Z")
def digest(data):
    return hashlib.sha256(data).hexdigest()

def normalize(source):
    lines=[]
    for line in source.splitlines():
        if line.startswith(b"%"):
            break
        lines.append(line)
    return b"\n".join(lines)+b"\n"

def validate(payload):
    n=None
    declared=None
    total=0
    unterminated=0
    max_id=0
    for line in payload.splitlines():
        line=line.strip()
        if not line or line[:1]==b"c":
            continue
        if line[:1]==b"p":
            fields=line.split()
            if n is not None or len(fields)!=4 or fields[1]!=b"cnf":
                return False,"invalid or repeated DIMACS header"
            n=int(fields[2]);declared=int(fields[3])
            if n<0 or declared<0:
                return False,"negative header dimension"
            continue
        if n is None:
            return False,"clauses before header"
        for token in line.split():
            literal=int(token)
            if literal==0:
                total+=1
                unterminated=0
            else:
                unterminated+=1
                max_id=max(max_id,abs(literal))
    if n is None:
        return False,"missing DIMACS header"
    if unterminated:
        return False,"unterminated clause"
    if declared!=total:
        return False,f"declared {declared} clauses but contains {total}"
    if max_id>n:
        return False,f"literal {max_id} exceeds {n} variables"
    return True,{"variables":n,"clauses":total}

def load_archive(entry):
    errors=[]
    for attempt in range(3):
        try:
            req=urllib.request.Request(entry["url"],headers={"User-Agent":"DRNAS-SAT-v7.4-independent-research"})
            with urllib.request.urlopen(req,timeout=45) as response:
                data=response.read(14_000_000)
            if len(data)>=14_000_000:
                raise ValueError("archive too large")
            if digest(data)!=entry["archive_sha256"]:
                raise ValueError("SHA256 of archive differs from frozen source")
            found={}
            raw_hash={}
            with tarfile.open(fileobj=io.BytesIO(data),mode="r:gz") as tf:
                for m in tf.getmembers():
                    if not m.isfile() or not m.name.lower().endswith(".cnf"):
                        continue
                    basename=Path(m.name).name
                    if not SAFE.fullmatch(basename) or basename in found:
                        raise ValueError("invalid or duplicated member name")
                    fp=tf.extractfile(m)
                    if fp is None:raise ValueError("missing member content")
                    payload=fp.read()
                    raw_hash[basename]=digest(payload)
                    found[basename]=normalize(payload)
            if len(found)!=entry["count"]:
                raise ValueError(f"expected {entry['count']} archive members, got {len(found)}")
            if sum(len(x) for x in found.values())!=entry["expected_total_normalized_bytes"]:
                raise ValueError("normalized original corpus size does not match pinned manifest")
            return found,raw_hash
        except (ValueError,OSError,tarfile.TarError) as exc:
            errors.append(str(exc))
            if attempt<2:time.sleep(2*(attempt+1))
    raise RuntimeError("Cannot authenticate "+entry["set"]+": "+"; ".join(errors))

def collect(spec,outdir, shard, shard_count):
    out=Path(outdir).resolve()
    out.mkdir(parents=True,exist_ok=True)
    report={
        "source":"Original SATLIB benchmarks, hashed archives",
        "source_commit":spec["source_commit"],
        "selection_rule":spec["frozen_selection"],
        "shard":shard,"shard_count":shard_count,
        "pilot":[],"holdout":[],"invalid_sources":[],
        "archives":[]
    }
    all_holdout=[]
    for archive in spec["archives"]:
        files,hashes=load_archive(archive)
        name=archive["set"]
        pilot_num=spec["pilot_per_set"][name]
        count=spec["cases_per_set"][name]
        ordered=sorted(files,key=lambda filename:digest((name+"|"+filename).encode()))
        offset=spec.get("selection_skip_per_set",{}).get(name,0)
        selected=ordered[offset:offset+count]
        if len(selected)!=count:raise RuntimeError("Insufficient fresh archive members for "+name)
        print(f"VERIFIED {name}: archive SHA256={archive['archive_sha256']} "
              f"member_count={len(files)} selected={count}",flush=True)
        report["archives"].append({"set":name,"archive_sha256":archive["archive_sha256"],"selected":count})
        for index,member in enumerate(selected):
            group="pilot" if index<pilot_num else "holdout"
            payload=files[member]
            valid,detail=validate(payload)
            name_and_member=name+"__"+member
            meta={
                "name":name_and_member,
                "family":name,
                "status":archive["status"],
                "source":"SATLIB external archive",
                "original_url":archive["url"],
                "source_archive_sha256":archive["archive_sha256"],
                "original_member":member,
                "raw_member_sha256":hashes[member],
                "expected_sha256":digest(payload),
                "observed_sha256":digest(payload),
                "bytes":len(payload),
            }
            if not valid:
                report["invalid_sources"].append(dict(meta,group=group,reason=detail))
                print(f"QUARANTINED {name_and_member}: {detail}",flush=True)
                continue
            file_path=out/group/name_and_member
            file_path.parent.mkdir(parents=True,exist_ok=True)
            file_path.write_bytes(payload)
            meta["path"]=str(file_path)
            if group=="pilot":
                report["pilot"].append(meta)
            else:
                all_holdout.append(meta)
    # Balanced fixed sharding across archives by round-robin original lists.
    # Stable ordering is frozen and independent of solving performance.
    for i,record in enumerate(all_holdout):
        if i%shard_count==shard:
            report["holdout"].append(record)
    out.joinpath("source-verification.json").write_text(json.dumps(report,indent=2))
    print(f"SELECTED valid pilot={len(report['pilot'])} "
          f"holdout_this_shard={len(report['holdout'])}, "
          f"all_holdout={len(all_holdout)}, malformed={len(report['invalid_sources'])}",flush=True)
    if not report["pilot"] and not report["holdout"]:
        raise RuntimeError("No valid benchmark instances")
    return report

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--manifest",required=True)
    parser.add_argument("--outdir",required=True)
    parser.add_argument("--shard",type=int,default=0)
    parser.add_argument("--shards",type=int,default=1)
    args=parser.parse_args()
    if args.shards<1 or not 0<=args.shard<args.shards:
        parser.error("shard must lie in [0, shards)")
    spec=json.loads(Path(args.manifest).read_text())
    collect(spec,args.outdir,args.shard,args.shards)
