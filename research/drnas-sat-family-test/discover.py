#!/usr/bin/env python3
"""Discover original GBD polynomial-multiplication CNF family metadata.

Discovery ONLY; it does NOT benchmark, choose results by runtime, nor
modify original CNFs. Candidate metadata is verified before later freeze.
"""
import json,os,re,sqlite3,urllib.request
from pathlib import Path
root=Path("polynomial_discovery");root.mkdir(exist_ok=True)
base="https://benchmark-database.de"
headers={"User-Agent":"DRNAS-SAT-Research-Corpus-Discovery/1.0"}
def get(url,max_size=120_000_000):
    req=urllib.request.Request(url,headers=headers)
    with urllib.request.urlopen(req,timeout=75) as res:
        data=res.read(max_size+1)
    if len(data)>max_size:raise RuntimeError(f"Exceeded size {url}")
    return data
uri=base+"/getinstances?family=polynomial-multiplication"
data=get(uri,15_000_000)
uri_list=[line.strip() for line in data.decode().splitlines() if line.strip()]
print("GBD family URI count",len(uri_list),uri_list[:12],flush=True)
(root/"family_urls.json").write_text(json.dumps(uri_list,indent=2)+"\n")
for url in [base+"/getdatabase/meta.db",base+"/getdatabase/meta"]:
    try:
        blob=get(url)
        print("META DOWNLOAD",url,"bytes",len(blob),"header",repr(blob[:32]),flush=True)
        if blob.startswith(b"SQLite format 3"):
            (root/"gbd_meta.db").write_bytes(blob)
            break
    except Exception as e:
        print("METADATA ERROR",url,type(e).__name__,str(e)[:250],flush=True)
db=root/"gbd_meta.db"
if db.exists():
    con=sqlite3.connect(str(db))
    tables=con.execute("SELECT name,sql FROM sqlite_master WHERE type='table'").fetchall()
    print("TABLES",json.dumps(tables)[:18000],flush=True)
    for name,sql in tables[:12]:
        if not re.fullmatch(r"[A-Za-z0-9_]+",name):continue
        rows=con.execute(f'SELECT * FROM "{name}" LIMIT 3').fetchall()
        print("SAMPLE",name,str(rows)[:2500],flush=True)
    con.close()
else:
    print("META not downloaded. URI manifest still available.",flush=True)
