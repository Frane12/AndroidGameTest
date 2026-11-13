#!/usr/bin/env python3
"""Freeze original SAT2024 source bytes before any solver trial; no outcome screening."""
import argparse, hashlib, json
from pathlib import Path
from drnas_x47_official_dedup import official_sources

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--count",type=int,default=100)
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    if a.count<1 or a.out.exists():raise RuntimeError("invalid count or preexisting directory")
    cases=official_sources(a.count)
    a.out.mkdir(parents=True)
    manifest={"protocol":"X52-original-SAT2024-selection-v1","dataset":"SAT Competition 2024 main archive retrospective",
              "selection":"deterministic name-family stratification; SHA dedup; no solver-outcome screening",
              "sources":[]}
    for i,s in enumerate(cases):
        raw=s["content"].encode("ascii")
        h=hashlib.sha256(raw).hexdigest()
        assert h==s["sha256"]
        path=a.out/f"{i:03d}.cnf"
        path.write_bytes(raw)
        assert hashlib.sha256(path.read_bytes()).hexdigest()==h
        manifest["sources"].append({"id":i,"file":path.name,"sha256":h,
            "family":s["family"],"archive_path":s["archive_path"],
            "nvars":s["nvars"],"nclauses":s["nclauses"],"bytes":len(raw)})
    assert len(manifest["sources"])==a.count
    assert len({s["sha256"] for s in manifest["sources"]})==a.count
    assert len({s["family"] for s in manifest["sources"]})==a.count
    (a.out/"source_manifest.json").write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
    print("X52_FROZEN_SOURCES",json.dumps({"selected":a.count,"source_families":a.count,
          "unique_sha":a.count,"total_raw_bytes":sum(x["bytes"] for x in manifest["sources"])}),flush=True)
if __name__=="__main__":main()
