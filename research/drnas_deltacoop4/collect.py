#!/usr/bin/env python3
"""Freeze 60 diverse original SAT2024 medium-size CNFs; no runtime selection.

Compressed size is a proxy for scale, NOT an a priori solver difficulty label.
Retrieval uses HTTP ZIP ranges, not a 4.3GB full download. Retrospective cohort.
"""
import bz2
import gzip
import hashlib
import json
import lzma
from pathlib import Path
import random
import re
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import drnas_x55_cpu_real36 as B

ARCHIVE="https://zenodo.org/records/15095752/files/sat-competition-2024-main-benchmarks.zip?download=1"
ROOT=Path("delta4_sources")
N=60
SHARDS=12
MAX_RAW=24_000_000
MAX_VARS=1_000_000

def family(name):
    n=Path(name).name.lower()
    n=re.sub(r"\.cnf(\.(xz|gz|bz2))?$","",n)
    n=n.replace(".sanitized","")
    n=re.sub(r"\d+","#",n)
    return re.sub(r"[_\-.]+","-",n).strip("-")

def compact(x):
    return json.dumps(x,sort_keys=True,separators=(",",":"))

def freeze_selection(entries):
    for lo,hi in ((40000,900000),(12000,1200000),(4000,1800000)):
        eligible=[e for e in entries if not e.is_dir()
                  and e.filename.lower().endswith((".cnf",".cnf.xz",".cnf.gz",".cnf.bz2"))
                  and lo<=e.file_size<=hi]
        by={}
        for e in sorted(eligible,key=lambda e:(e.file_size,e.filename)):
            by.setdefault(family(e.filename),e)
        pool=sorted(by.values(),key=lambda e:(e.file_size,e.filename))
        if len(pool)>=N+8:
            chosen_indices=[((2*i+1)*len(pool))//(2*N) for i in range(N)]
            assert len(set(chosen_indices))==N
            chosen=[pool[i] for i in chosen_indices]
            other=[e for i,e in enumerate(pool) if i not in set(chosen_indices)]
            random.Random(4404).shuffle(chosen)
            return chosen,other,{"compressed_tier":[lo,hi],
                "eligible_entries":len(eligible),"distinct_filename_families":len(by)}
    raise RuntimeError("DELTA4_INSUFFICIENT_METADATA_DIVERSE_MEDIUM_FAMILIES")

def unpack(e,data):
    name=e.filename.lower()
    if name.endswith(".xz"):
        z=lzma.LZMADecompressor()
        raw=z.decompress(data,max_length=MAX_RAW+1)
        if not z.eof:raise ValueError("large xz")
    elif name.endswith(".gz"):
        raw=gzip.decompress(data)
    elif name.endswith(".bz2"):
        raw=bz2.decompress(data)
    else:raw=data
    if len(raw)>MAX_RAW:raise ValueError("large raw CNF")
    m=re.search(rb"(?m)^p cnf ([0-9]+) ([0-9]+)\s*$",raw)
    if m is None:raise ValueError("invalid CNF header")
    n=int(m.group(1))
    if not (1<=n<=MAX_VARS):raise ValueError("variable limit")
    if len(raw)<5000:raise ValueError("too tiny")
    return raw,n,int(m.group(2))

def collect():
    from remotezip import RemoteZip
    ROOT.mkdir(exist_ok=True)
    originals,_=B.official_manifest()
    prior_sha={s["sha256"] for s in originals}
    with RemoteZip(ARCHIVE,timeout=90) as archive:
        primary,spares,tier=freeze_selection(archive.infolist())
        candidates=primary+spares
        chosen=[];families=set();hashes=set()
        for e in candidates:
            if len(chosen)==N:break
            fam=family(e.filename)
            if fam in families:continue
            try:
                raw,n,clauses=unpack(e,archive.read(e))
            except (ValueError,lzma.LZMAError,EOFError,OSError) as exc:
                print("DELTA4_SKIP",compact({"file":e.filename,"why":str(exc)[:130]}),flush=True)
                continue
            source_sha=hashlib.sha256(raw).hexdigest()
            if source_sha in hashes or source_sha in prior_sha:continue
            i=len(chosen);path=ROOT/"cases"/f"{i:03d}_{source_sha[:16]}.cnf"
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(raw)
            row={"id":i,"source":e.filename,"family":fam,"sha256":source_sha,
                 "path":str(path),"nvars":n,"nclauses":clauses,"raw_bytes":len(raw),
                 "archive_compressed_bytes":e.file_size,"shard":i%SHARDS,
                 "dataset":"SAT Competition 2024 main original"}
            chosen.append(row);families.add(fam);hashes.add(source_sha)
            print("DELTA4_SOURCE",compact(row),flush=True)
    if len(chosen)!=N:raise RuntimeError(f"DELTA4_ONLY_{len(chosen)}_ELIGIBLE_CNF")
    manifest={"archive":ARCHIVE,"source_count":N,"shards":SHARDS,
              "selection":tier,"classification":"medium compressed size, NOT certified medium solving hardness",
              "uses_solver_outcomes_for_selection":False,
              "originals_unchanged":True,"family_key":"normalized filenames; not proven generative family",
              "prior_real36_SHA_excluded":True,
              "blind_holdout":False,"retrospective":True,"promotion":False,
              "repetitions":2,"cap_s":10.0,"sources":chosen}
    out=ROOT/"manifest.json"
    out.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    report={"source_count":N,"families":len(families),"nvars_min":min(x["nvars"] for x in chosen),
            "nvars_max":max(x["nvars"] for x in chosen),"bytes_min":min(x["raw_bytes"] for x in chosen),
            "bytes_max":max(x["raw_bytes"] for x in chosen),
            "manifest_sha256":hashlib.sha256(out.read_bytes()).hexdigest()}
    print("DELTA4_SOURCES_FROZEN",compact(report),flush=True)

def load():
    path=ROOT/"manifest.json";raw=path.read_bytes()
    meta=json.loads(raw)
    assert meta["source_count"]==N and len(meta["sources"])==N
    assert len({s["sha256"] for s in meta["sources"]})==N
    assert len({s["family"] for s in meta["sources"]})==N
    for s in meta["sources"]:
        assert hashlib.sha256(Path(s["path"]).read_bytes()).hexdigest()==s["sha256"]
    return meta["sources"],hashlib.sha256(raw).hexdigest()

if __name__=="__main__":
    collect()
