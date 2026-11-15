#!/usr/bin/env python3
"""ARG3-REALARG1: fixed ORIGINAL SAT Competition 2025 argumentation cohort.
Source acquisition and SHA freeze ONLY; never invokes a SAT solver.
All 19 precommitted GBD IDs (selected by published "argumentation" family,
not by SAT outcome, difficulty or our implementation's success).
NO replacements for downloads or out-of-limit inputs.
"""
import bz2,concurrent.futures,gzip,hashlib,io,json,lzma,os,re,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"arg3_realarg_inputs"
CATALOG_COMMIT="1de9acf01846f96fd3d6a460bc2238ce3bb4e3a6"
CATALOG=f"https://raw.githubusercontent.com/satcompetition/2025/{CATALOG_COMMIT}/downloads/SC2025.uri"
CATALOG_SHA="d02406bb212498ea1d2d9f2e968f9a8f6ad3b6bc479ae1b1368d5b4d638a9120"
SOURCE_LIMIT=48*1024*1024
COMPRESSED_LIMIT=24*1024*1024
# Official GBD metadata: ?context=cnf&track=main_2025 ; family=argumentation
# Outcomes deliberately excluded; all distinct family entries except previously
# studied b9ed6fd14f4fc969ec966a4b54c36872.
IDS=[
"00d5a43a481477fa4d56a2ce152a6cfb",
"16564a6acba6b9fc887c447d4e507767",
"1e87463fee15de63143796fd92d88a58",
"2241a1fb5bdbac0c1a3c1980ed8b332d",
"43fbacb24ea30054dece1de179c4ca7e",
"465c7f101b2d24de63f6a6f544faa9ee",
"674affb219c049cdbff1b65a6b7bedcc",
"69ed23c545d2a48f735f2187d919a5dd",
"6fab31665147f538da92dc16c3a239ad",
"8b267f95678c90b2179944de7233b090",
"96a472b1fd7bf855fbe44fc2d5e745ce",
"9754fc1acf450ee2ed2083a211cfa487",
"aa5585572cc045a3c2209b083635d598",
"ac51df6b340190cd1182c06ff2955afa",
"c0074020a48535e6062421cea2850dd0",
"e3bd4a397f34a99c47d1b2e0e9abcd43",
"e9f6eb5654365bb115e6d96405ea9a76",
"f371fb73e6bd6d05b306519818bd5c89",
"f569dc48ad062a3110ff08a8d59e59ab",
]
DEVELOPMENT_GBD="b9ed6fd14f4fc969ec966a4b54c36872"
KNOWN_ORIGINAL_SHA="c46261a9a52b8080ddc040f6b58e7a48eb651993ff6f67ae78830848b8e14fb2"
def digest(b):return hashlib.sha256(b).hexdigest()
def fetch(url,limit=COMPRESSED_LIMIT,timeout=40):
    req=urllib.request.Request(url,headers={
      "User-Agent":"DRNAS-ARG3-original-source-freeze-20261115/1.0",
      "Accept":"application/octet-stream"})
    with urllib.request.urlopen(req,timeout=timeout) as f:
        data=f.read(limit+1)
        if len(data)>limit:raise ValueError("compressed bytes exceed frozen cap")
        return data,f.geturl()
def decode(raw):
    if raw.startswith(b"\xfd7zXZ\x00"):stream=lzma.LZMAFile(io.BytesIO(raw));kind="xz"
    elif raw.startswith(b"\x1f\x8b"):stream=gzip.GzipFile(fileobj=io.BytesIO(raw));kind="gzip"
    elif raw.startswith(b"BZh"):stream=bz2.BZ2File(io.BytesIO(raw));kind="bzip2"
    else:
        if len(raw)>SOURCE_LIMIT:raise ValueError("plain source bytes exceed cap")
        return raw,"plain"
    with stream:source=stream.read(SOURCE_LIMIT+1)
    if len(source)>SOURCE_LIMIT:raise ValueError("expanded source bytes exceed cap")
    return source,kind
def acquire(gbd):
    url="https://benchmark-database.de/file/"+gbd
    row=dict(gbd=gbd,url=url)
    try:
        compressed,redirect=fetch(url)
        original,codec=decode(compressed)
        heads=[line.split() for line in original.splitlines()
               if line.startswith(b"p cnf ")]
        if len(heads)!=1 or len(heads[0])!=4:raise ValueError("non-DIMACS header")
        n,m=map(int,heads[0][2:])
        if not(0<n<=30000000 and 0<m<=30000000):
            raise ValueError("unexpected DIMACS dimensions")
        row.update(status="DOWNLOADED",sha256=digest(original),
             compressed_sha256=digest(compressed),compressed_bytes=len(compressed),
             bytes=len(original),vars=n,clauses=m,compression=codec,redirect=redirect)
        return row,original
    except Exception as exc:
        row.update(status="EXCLUDED_SOURCE_ERROR",
                   reason=(type(exc).__name__+": "+str(exc))[:300])
        return row,None
def main():
    if OUT.exists():raise RuntimeError("frozen source folder already exists")
    assert len(IDS)==19 and len(set(IDS))==19
    assert all(re.fullmatch(r"[0-9a-f]{32}",g) for g in IDS)
    assert DEVELOPMENT_GBD not in IDS
    (OUT/"cnf").mkdir(parents=True)
    official,_=fetch(CATALOG,100000,30)
    if digest(official)!=CATALOG_SHA:raise RuntimeError("official SAT2025 list SHA changed")
    catalog={x.strip().rsplit("/",1)[-1] for x in official.decode().splitlines() if x.strip()}
    if not set(IDS)<=catalog:raise RuntimeError("predeclared original GBD not in official catalog")
    known=set([KNOWN_ORIGINAL_SHA])
    prior=[]
    for path in (ROOT/"cf7/manifest.json", ROOT/"sat_real2025_inputs/manifest.json"):
        if not path.exists():raise RuntimeError("known previous original-source manifest missing")
        data=json.loads(path.read_text())
        prior.append(dict(path=str(path.relative_to(ROOT)),sha256=digest(path.read_bytes())))
        sources=data.get("sources",data.get("ready_sources",[]))
        known.update(s["sha256"] for s in sources)
    ready=[];attempts=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        for row,source in pool.map(acquire,IDS):
            if source is not None:
                if row["sha256"] in known:
                    row.update(status="EXCLUDED_KNOWN_SOURCE_SHA",
                               reason="previous original source SHA overlap")
                elif row["sha256"] in {x["sha256"] for x in ready}:
                    row.update(status="EXCLUDED_DUPLICATE_SOURCE_SHA",
                               reason="duplicated source bytes")
                else:
                    name=f'{len(attempts):02d}-{row["sha256"][:16]}.cnf'
                    path=OUT/"cnf"/name
                    path.write_bytes(source)
                    assert digest(path.read_bytes())==row["sha256"]
                    row.update(status="READY",path=str(path.relative_to(ROOT)))
                    ready.append(row)
            attempts.append(row)
            print("ARG3_SOURCE_ATTEMPT "+json.dumps(
                {k:row.get(k) for k in ("gbd","status","vars","clauses","bytes","reason")},
                sort_keys=True),flush=True)
    frozen=dict(protocol="DRNAS-ARG3-REALARG-FROZEN1",
      selection="published SAT2025 Main Track argumentation family; all 19 precommitted GBD except known #299",
      category="argumentation",category_source="GBD cnf/meta 2025",
      official_catalog=CATALOG,official_catalog_sha256=CATALOG_SHA,
      precommitted_gbd_ids=IDS,known_development_source_gbd=DEVELOPMENT_GBD,
      comparison_manifests=prior,known_previous_original_sha_count=len(known),
      raw_download_limit=COMPRESSED_LIMIT,max_original_bytes=SOURCE_LIMIT,
      attempts=attempts,ready_sources=ready,ready_count=len(ready),
      no_outcome_labels_used=True,not_proof_of_total_historical_nonexposure=True,
      no_replacement_of_failed_downloads=True,no_solvers_executed=True,
      code_sha=os.environ.get("GITHUB_SHA"))
    (OUT/"manifest.json").write_text(json.dumps(frozen,sort_keys=True,indent=2)+"\n")
    (OUT/"source.sha256").write_text("".join(
        row["sha256"]+"  cnf/"+Path(row["path"]).name+"\n" for row in ready))
    print("ARG3_SOURCE_FREEZE "+json.dumps(dict(
      attempted=len(attempts),ready=len(ready),rejected=len(attempts)-len(ready),
      manifest_sha256=digest((OUT/"manifest.json").read_bytes()),
      catalog_sha256=CATALOG_SHA),sort_keys=True),flush=True)
    if len(ready)<4:raise RuntimeError("fewer than 4 original sources: do not benchmark")
if __name__=="__main__":main()
