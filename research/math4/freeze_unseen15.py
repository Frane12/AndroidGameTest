#!/usr/bin/env python3
"""Freeze 15 precommitted unseen original SAT2026 GBD CNFs BEFORE any solver.

Source IDs in research/math4/holdout_selection.json were committed separately.
Download or size failures are reported and NEVER replaced with easier formulas.
The catalog's SAT/UNSAT labels are metadata, not a proof.
"""
import hashlib
import json
import lzma
import os
import re
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"hall3"))
from collect import download,CAT_URL,MAX_ARCHIVE,MAX_RAW

ROOT=Path(__file__).resolve().parents[2]
DEST=ROOT/"math4_holdout"
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
    selection=json.loads((ROOT/"research/math4/holdout_selection.json").read_text())
    assert selection["source_count"]==15 and selection["selection_frozen_before_any_run"]
    assert len({s["file_id"] for s in selection["source_ids"]})==15
    catalog_raw=download(CAT_URL,3_000_000)
    cat={}
    for line in catalog_raw.decode().splitlines():
        parts=line.split()
        if len(parts)==6:
            k,a,f,label,iso,participates=parts
            cat[k]=dict(author=a,family=f,catalog_label=label,
                        isohash=iso,participates=participates)
    DEST.mkdir(parents=True,exist_ok=False)
    (DEST/"cnf").mkdir()
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    rows=[]
    errors=[]
    for idx,entry in enumerate(selection["source_ids"]):
        assert cat[entry["file_id"]]=={
            key:entry[key] for key in ("author","family","catalog_label","isohash","participates")}
        url="https://benchmark-database.de/file/"+entry["file_id"]+"?context=cnf"
        base=dict(entry,id=idx,url=url,selected_before_results=True)
        try:
            archive=download(url,MAX_ARCHIVE)
            if archive.startswith(b"\xfd7zXZ\x00"):
                decoder=lzma.LZMADecompressor()
                raw=decoder.decompress(archive,max_length=MAX_RAW+1)
                if len(raw)>MAX_RAW or not decoder.eof:
                    raise ValueError("raw_size_gate")
            else:raw=archive
            if len(raw)>MAX_RAW:raise ValueError("raw_size_gate")
            header=re.search(rb"^p\s+cnf\s+(\d+)\s+(\d+)\s*$",raw,re.M)
            if not header:raise ValueError("missing_DIMACS_header")
            nv,nclauses=map(int,header.groups())
            if nv>200000 or nclauses>2000000:raise ValueError("declared_dimensions_gate")
            rel=Path("math4_holdout/cnf")/f"{idx:02d}-{entry['file_id']}.cnf"
            (ROOT/rel).write_bytes(raw)
            result=dict(base,status="DOWNLOADED_SOURCE_PINNED",path=str(rel),
                        sha256=sha(raw),archive_sha256=sha(archive),
                        variables=nv,clauses=nclauses,bytes=len(raw),
                        archive_bytes=len(archive))
            rows.append(result)
            print("MATH4_HOLDOUT_INPUT "+json.dumps({
                k:result[k] for k in ("id","file_id","family","catalog_label",
                  "variables","clauses","sha256")},sort_keys=True),flush=True)
        except Exception as exc:
            result=dict(base,status="SOURCE_UNAVAILABLE_OR_RESOURCE_GATE",
                        error=type(exc).__name__+":"+str(exc)[:240])
            errors.append(result)
            print("MATH4_HOLDOUT_INPUT_SKIPPED "+json.dumps(result,sort_keys=True),flush=True)
    m={"protocol":selection["protocol"],"selection_sha256":sha(
            (ROOT/"research/math4/holdout_selection.json").read_bytes()),
       "catalog_sha256":sha(catalog_raw),"catalog_url":CAT_URL,
       "source_disjoint_from_prior24":True,"cpu":cpu,
       "selected_count":15,"downloaded_count":len(rows),"excluded_or_failed":errors,
       "sources":rows}
    (DEST/"manifest.json").write_text(json.dumps(m,indent=2,sort_keys=True)+"\n")
    print("MATH4_HOLDOUT_FROZEN "+json.dumps({
        "selected":15,"downloaded":len(rows),"excluded":len(errors),
        "families":sorted({r["family"] for r in rows})},sort_keys=True),flush=True)
    assert len(rows)>=8,"not enough source-valid cases; do not replace sources"
if __name__=="__main__":main()
