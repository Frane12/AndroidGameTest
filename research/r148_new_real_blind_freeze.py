#!/usr/bin/env python3
"""Prospective R148 holdout freeze: NEW real CNFs only, deterministic source choice.

Before performance measurement, exclude SHA, URL, and published filename/GBD
identity from original R132/125, R135/56, R135S/21, R135/400. Do not select
using speed, structural features, solver result, or category performance.
This is an independent candidate holdout relative to these supplied ledgers,
not a claim of globally unseen or official SAT Competition performance.
"""
import collections,hashlib,json,pathlib,urllib.request,io,gzip,lzma,bz2
ROOT=pathlib.Path("r148blind")
FROZEN=ROOT/"frozen"
PROTO="DRNAS-R148-REAL-50-PROSPECTIVE-SHA-URL-EXCLUDED-20261105-v1"
LIMIT=8_000_000
SPECS={
    "miter":("https://benchmark-database.de/getinstances?query=family%3Dmiter&context=cnf",10),
    "cryptography":("https://benchmark-database.de/getinstances?query=family%3Dcryptography&context=cnf",10),
    "xor_shifting":("https://benchmark-database.de/getinstances?query=family%3Dxor-shifting&context=cnf",10),
    "uniform_random":("https://benchmark-database.de/getinstances?query=family%3Duniform-random&context=cnf",10),
    "official2024":("https://benchmark-database.de/getinstances?query=track%3Dmain_2024&context=cnf",10),
}
PRIOR={
    "r132_125":("prior/r132/manifest.json",125,"cases"),
    "r135_56":("prior/r135/manifest.json",56,"cases"),
    "r135s_21":("prior/r135s/frozen/manifest.json",21,"cases"),
    "r135_400":("holdout-400/manifest-400.json",400,"formulas"),
}
def sha(b):return hashlib.sha256(b).hexdigest()
def sha_file(p):
    h=hashlib.sha256()
    with pathlib.Path(p).open("rb") as f:
        for piece in iter(lambda:f.read(1048576),b""):h.update(piece)
    return h.hexdigest()
def need(x,m):
    if not x:raise RuntimeError("R148_BLIND_FREEZE_REFUSED "+str(m))
def download(url,max_bytes=LIMIT):
    req=urllib.request.Request(url,headers={"User-Agent":"DRNAS-R148-SHA-Frozen-Independent-SAT-CNF-Research/1.0"})
    with urllib.request.urlopen(req,timeout=45) as r:
        raw=r.read(max_bytes+1)
    need(len(raw)<=max_bytes,"compressed source too large")
    return raw
def unpack(raw):
    if raw.startswith(b"\xfd7zXZ"): f=lzma.LZMAFile(io.BytesIO(raw))
    elif raw.startswith(b"\x1f\x8b"): f=gzip.GzipFile(fileobj=io.BytesIO(raw))
    elif raw.startswith(b"BZh"): f=bz2.BZ2File(io.BytesIO(raw))
    else: return raw
    with f: plain=f.read(LIMIT+1)
    need(len(plain)<=LIMIT,"unpacked source too large")
    return plain
def verify_dimacs(b):
    need(0<len(b)<=LIMIT,"source size outside bounds")
    seen_header=False;numvars=0;numclauses=0;count=0;open_clause=False
    for line in b.splitlines():
        t=line.strip()
        if not t or t==b"c" or t.startswith(b"c ") or t.startswith(b"c\t"):continue
        if t==b"%":break
        if t.startswith(b"p "):
            need(not seen_header,"duplicate header")
            fields=t.split()
            need(len(fields)==4 and fields[:2]==[b"p",b"cnf"],"wrong DIMACS header")
            numvars=int(fields[2]);numclauses=int(fields[3])
            need(0<numvars<=10_000_000 and 0<numclauses<=2_000_000,"invalid DIMACS bounds")
            seen_header=True
            continue
        need(seen_header,"literals before header")
        for word in t.split():
            value=int(word)
            need(abs(value)<=numvars,"literal outside declared variables")
            if value==0:
                count+=1;open_clause=False
                need(count<=numclauses,"too many clauses")
            else:open_clause=True
    need(seen_header and not open_clause and count==numclauses,"incomplete DIMACS clause count")
    return numvars,numclauses
def freeze():
    used_sha=set();used_urls=set();used_ids=set();prior_hashes={}
    for name,(path,expected,field) in PRIOR.items():
        p=pathlib.Path(path)
        need(p.is_file(),"required independent source ledger missing: "+str(p))
        raw=p.read_bytes();prior_hashes[name]=sha(raw)
        report=json.loads(raw)
        cases=report[field]
        need(len(cases)==expected,"unexpected historical source size "+name)
        for c in cases:
            if c.get("sha256"):used_sha.add(c["sha256"])
            for k in ("url","source_url","download_url","original_url","gbd","file_id","id","compressed_file"):
                if c.get(k):
                    val=str(c[k])
                    if val.startswith(("https://","http://")):used_urls.add(val)
                    used_ids.add(val.rsplit("/",1)[-1].split("?")[0])
    need(len(used_sha)>=400,"known SHA exclusion incomplete")
    FROZEN.mkdir(parents=True,exist_ok=True)
    records=[];index_provenance={};rejected=collections.Counter()
    for cohort,(index,target) in SPECS.items():
        body=download(index,4_000_000)
        urls=sorted({u.strip() for u in body.decode("utf-8").splitlines()
                     if u.strip().startswith(("https://","http://"))},
            key=lambda u:sha((PROTO+"|"+cohort+"|"+u).encode()))
        need(bool(urls),"source index unavailable "+cohort)
        accepted=0;attempted=0
        for url in urls:
            if accepted>=target or attempted>=125:break
            ident=url.rsplit("/",1)[-1].split("?")[0]
            if url in used_urls or ident in used_ids:
                rejected[cohort+"_old_url_or_id"]+=1
                continue
            attempted+=1
            try:
                raw=download(url);plain=unpack(raw)
                need(len(plain)<=LIMIT,"unpacked original CNF exceeds 8MB")
                h=sha(plain)
                if h in used_sha:
                    rejected[cohort+"_known_SHA"]+=1
                    used_ids.add(ident);used_urls.add(url)
                    continue
                nv,nc=verify_dimacs(plain)
                filename=f"{cohort}-{accepted:03d}.cnf"
                (FROZEN/filename).write_bytes(plain)
                need(sha_file(FROZEN/filename)==h,"source SHA changed while freezing")
                records.append(dict(id=filename,cohort=cohort,sha256=h,url=url,gbd=ident,
                                    bytes=len(plain),variables=nv,clauses=nc,raw_source_sha256=sha(raw)))
                used_sha.add(h);used_ids.add(ident);used_urls.add(url)
                accepted+=1
                print("R148_BLIND_FROZEN_CASE",cohort,accepted,h[:12],flush=True)
            except Exception as e:
                rejected[cohort+"_download_or_DiMACS"]+=1
        index_provenance[cohort]=dict(index=index,index_sha256=sha(body),
                                       available_urls=len(urls),attempted_downloads=attempted,
                                       accepted=accepted,target=target)
    need(len(records)>=36,("insufficient new independent real CNFs",len(records),dict(rejected)))
    need(len(records)<=50 and len({c["sha256"] for c in records})==len(records),"bad frozen count")
    manifest=dict(protocol=PROTO,phase="FROZEN_BEFORE_FIRST_SOLVER_TIMING",
        cases=records,original_sha_verified=True,
        SHA_URL_ID_EXCLUDED_against=prior_hashes,index_provenance=index_provenance,
        count=len(records),cohort_counts=dict(collections.Counter(c["cohort"] for c in records)),
        rejection_counts=dict(rejected),precommitted_quota={k:v[1] for k,v in SPECS.items()},
        pilot_and_original_400_not_reused=True,source_unchanged=True,
        no_speed_or_solve_outcome_selection=True,repeats=2,shards=8,cap_s=15.0,
        modes=["kissat","cadical","r118","r135","r148"],
        caveat="External real CNF pool, SHA-disjoint with listed historical artifacts; new independent holdout, not official ranking; UNSAT lacks independent LRAT")
    (FROZEN/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    print("R148_BLIND_FREEZE_FINAL",json.dumps({"count":len(records),"cohorts":manifest["cohort_counts"],
        "prior_manifests_sha256":prior_hashes,"rejection_counts":dict(rejected)},sort_keys=True),flush=True)
if __name__=="__main__":freeze()
