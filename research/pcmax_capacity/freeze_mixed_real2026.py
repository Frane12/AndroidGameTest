#!/usr/bin/env python3
"""Freeze original, *unaltered* SAT Competition 2026 CNFs against earlier SHA256.

Pinned identifiers and hashes match original GitHub run 43641628537;
catalog labels are metadata, NEVER considered proof of SAT/UNSAT.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
from benchmark_official2026_clause1 import CASES,CATALOG_URL,MAX_ARCHIVE,MAX_CNF,retrieve,unpack,header

PINS={
"47173e8ab499159d3aa301b0101fe170":"43553556a809fb9029278ac45752e3c805a8cbe8e2fea48934b968242b52ebf5",
"48432767076e402d2accbf2da7260885":"fe67da067d07731deaf5ecf15d2a34e8ff2d073141a1e9eab5d77dcd2b774960",
"546a73eef02dda3719018050b09e9392":"38ae1a9d54e147ffa3852083aab73181212e1983692f3f0889e30edbc3c6aa74",
"5f10d57cf49586518e1a103f03984e74":"d4bbfb69cec852340bc64fc10f2d9329610081b23d961d216a2e7654ded40126",
"93f5b06574be09ad5b46778248421019":"832436b9fbda1e1d11ee19d64c318788d69810f1c2f4fb4623378ad4efbdb820",
"17baf7fa29b82de40adb837adee0dffb":"e40f1566b6d168487c3d839eb435f05f44c722fcbd1c24aa9c6c6c0eab304790",
"353837b1b8fdcab109c3925fc9d73512":"5bea29d3875cbb75d162ad38026666c4bcc9dde84628b5b300d7d3fd428b6097",
"03e49a528251af9a7b7e1ca03c33b162":"bf0a806d6c0677c1606add37d62dbbe04087a7dcd470cedb9f652bf85a709ec7",
"046d5e1432c39dc4b085a80fab3a8be6":"5665c15884dcc168ad9059f6151e93b90d3e017f86a677e071e35b405a583f56",
"0d082b8fa36f662217bee5524cd24d3a":"3ce86f563e46d7e9697043c5fb2998c4b7aa20802d354222d6ad3392ac39d57b",
"12ac1c71ff0405cc150c2a2db6c4a255":"47ccdc6cf39d585f19b2b6c9e5cf23b71652af0b8cbc4b090f0137e71797aaed",
"13eb6e05dd8decd305dae2fc148b0ede":"d876dbec0e00bb1bd67ff7e913a78999dfafee63f03ff9102785bbe51de49425",
}
def sha(path):
    dig=hashlib.sha256()
    with open(path,"rb") as f:
        for chunk in iter(lambda:f.read(1<<20),b""):
            dig.update(chunk)
    return dig.hexdigest()
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--out",type=Path,required=True)
    a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=False)
    inputs=a.out/"inputs"
    inputs.mkdir()
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    catalog=a.out/"official-catalog.csv"
    retrieve(CATALOG_URL,catalog,3_000_000)
    meta={}
    for line in catalog.read_text().splitlines():
        parts=line.split()
        if len(parts)==6:
            file_id,author,family,label,iso,participation=parts
            meta[file_id]=(author,family,label)
    rows=[]
    assert len(CASES)==len(PINS)==12
    for i,(file_id,author,family,label) in enumerate(CASES):
        assert meta[file_id]==(author,family,label),(file_id,meta.get(file_id))
        src=inputs/(f"{i:02d}-{file_id}.cnf")
        archive=inputs/(f"{i:02d}-{file_id}.cnf.xz")
        download_s,archive_bytes=retrieve(
            "https://benchmark-database.de/file/"+file_id+"?context=cnf",
            archive,MAX_ARCHIVE)
        decomp_bytes=unpack(archive,src)
        nv,clauses=header(src)
        actual=sha(src)
        assert actual==PINS[file_id],("SOURCE_SHA256_MISMATCH",file_id,actual,PINS[file_id])
        row=dict(id=i,file_id=file_id,family=family,label=label,
                 variables=nv,clauses=clauses,
                 source_sha256=actual,archive_sha256=sha(archive),
                 archive_bytes=archive_bytes,decompressed_bytes=decomp_bytes,
                 path="inputs/"+src.name)
        rows.append(row)
        print("FROZEN_REAL2026_SOURCE "+json.dumps(row,sort_keys=True),flush=True)
        archive.unlink()
    data={"source":"official SAT2026 GBD originals; sha256 pinned to prior certified run",
          "pinned_reference_run":43641628537,"catalog_sha256":sha(catalog),
          "catalog_url":CATALOG_URL,"cpu":cpu,"sources":rows}
    (a.out/"manifest.json").write_text(json.dumps(data,indent=2)+"\n")
    print("FROZEN_REAL2026_PASS "+json.dumps(dict(sources=len(rows),
          selected_sha256=[r["source_sha256"] for r in rows]),sort_keys=True),flush=True)
if __name__=="__main__":
    main()
