#!/usr/bin/env python3
"""Freeze source-only original SAT2025 CNF; no solver, no score filtering."""
import bz2,concurrent.futures,gzip,hashlib,io,json,lzma,os,re,urllib.request
from pathlib import Path
R=Path(__file__).resolve().parents[2]; OUT=R/"sat_real2025_inputs"
COMMIT="1de9acf01846f96fd3d6a460bc2238ce3bb4e3a6"
CAT=f"https://raw.githubusercontent.com/satcompetition/2025/{COMMIT}/downloads/SC2025.uri"
IDX=[11+18*i for i in range(22)] # preregistered; never select by outcomes
RAWMAX=18*1024*1024; CNFMAX=36*1024*1024
KNOWN={"243e5d0079606862166a4619691cbbb8ffc9c8c14eb16250138b16d724c6bc83",
       "fc529dff1a6f763c97b0ed1dd33199e0d9dd26c50d210f9032e4fdaab5534c16"}
def sha(b):return hashlib.sha256(b).hexdigest()
def fetch(url,cap=RAWMAX,seconds=35):
    req=urllib.request.Request(url,headers={"User-Agent":"DRNAS-REAL2025-Source-Audit/1.0",
                                             "Accept":"application/octet-stream"})
    with urllib.request.urlopen(req,timeout=seconds) as stream:
        b=stream.read(cap+1)
        if len(b)>cap:raise ValueError("compressed size cap")
        return b,stream.geturl()
def decode(b):
    if b.startswith(b"\xfd7zXZ\x00"):fd=lzma.LZMAFile(io.BytesIO(b));kind="xz"
    elif b.startswith(b"\x1f\x8b"):fd=gzip.GzipFile(fileobj=io.BytesIO(b));kind="gzip"
    elif b.startswith(b"BZh"):fd=bz2.BZ2File(io.BytesIO(b));kind="bzip2"
    else:return b,"plain"
    with fd:out=fd.read(CNFMAX+1)
    if len(out)>CNFMAX:raise ValueError("expanded size cap")
    return out,kind
def download(pair):
    ix,gbd=pair;url="https://benchmark-database.de/file/"+gbd
    row=dict(index=ix,gbd=gbd,url=url)
    try:
        raw,dest=fetch(url)
        data,kind=decode(raw)
        if len(data)>CNFMAX:raise ValueError("CNF size cap")
        header=[l.split() for l in data.splitlines() if l.startswith(b"p cnf ")]
        if len(header)!=1 or len(header[0])!=4:raise ValueError("bad DIMACS header")
        n,m=map(int,header[0][2:])
        if not (0<n<=20000000 and 0<m<=30000000):raise ValueError("bad dimensions")
        row.update(status="DOWNLOADED",sha256=sha(data),compressed_sha256=sha(raw),
                   bytes=len(data),raw_bytes=len(raw),vars=n,clauses=m,
                   compression=kind,redirect=dest)
        return row,data
    except Exception as e:
        row.update(status="EXCLUDED_SOURCE_ACQUISITION",reason=(type(e).__name__+": "+str(e))[:200])
        return row,None
def main():
    assert not OUT.exists()
    (OUT/"cnf").mkdir(parents=True)
    catalog,_=fetch(CAT,100000,25)
    entries=[s.strip() for s in catalog.decode().splitlines() if s.strip()]
    if len(entries)!=400 or not all(
        re.fullmatch(r"https://benchmark-database\.de/file/[a-f0-9]{32}",s) for s in entries):
        raise RuntimeError("SAT2025 catalog changed")
    candidates=[(i,entries[i].rsplit("/",1)[1]) for i in IDX]
    prev=R/"cf7/manifest.json"
    prior=json.loads(prev.read_text())
    assert prior["count"]==100
    excluded=set(KNOWN)|{s["sha256"] for s in prior["sources"]}
    results=[];ready=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for row,data in pool.map(download,candidates):
            if data is not None:
                if row["sha256"] in excluded:
                    row.update(status="EXCLUDED_KNOWN_SHA",reason="known frozen original")
                elif row["sha256"] in {s["sha256"] for s in ready}:
                    row.update(status="EXCLUDED_DUPLICATE",reason="same source SHA")
                else:
                    name=f'{row["index"]:03d}-{row["sha256"][:16]}.cnf'
                    dst=OUT/"cnf"/name;dst.write_bytes(data)
                    row.update(status="READY",path=str(dst.relative_to(R)))
                    ready.append(row)
            results.append(row)
            print("REAL2025_SOURCE "+json.dumps(
                {k:row.get(k) for k in ("index","gbd","status","bytes","reason")}),flush=True)
    manifest=dict(protocol="DRNAS-REAL2025-FROZEN-ORIGINAL-V1",
       catalog=CAT,catalog_sha256=sha(catalog),candidate_positions=IDX,
       all_source_attempts=results,ready_sources=ready,ready_count=len(ready),
       previous_CF7_sha256=sha(prev.read_bytes()),known_hash_count=len(excluded),
       compressed_limit=RAWMAX,dimacs_limit=CNFMAX,
       selection="fixed 22 catalog indices, source size/acquisition only; no solver outcomes",
       blind_scope="untested in this experiment; historical exposure beyond known reference SHA not exhaustively audited",
       provenance="SAT Competition 2025 Main GBD URI",solver_executed=False,
       git_sha=os.getenv("GITHUB_SHA"))
    (OUT/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    (OUT/"source.sha256").write_text("".join(
       s["sha256"]+"  cnf/"+Path(s["path"]).name+"\n" for s in ready))
    print("REAL2025_FREEZE "+json.dumps(dict(attempted=len(results),ready=len(ready),
       manifest_sha256=sha((OUT/"manifest.json").read_bytes()),
       catalog_sha256=sha(catalog)),sort_keys=True),flush=True)
    if len(ready)<4:raise RuntimeError("Too few accessible frozen originals; STOP without solver runs")
if __name__=="__main__":main()
