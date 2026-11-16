#!/usr/bin/env python3
"""Freeze 10 ORIGINAL SAT Competition 2025 Main graph-related CNFs.

Source selection is already committed in prespec.json (commit 1c206ef3).
NO solver, family recognizer, proof emitter, source performance classifier,
SAT/UNSAT label or candidate-generated output may run in this script.

Recheck exact original GBD hashes and ISO hashes against both previous
development manifests; download, bound, parse, hash, and freeze ALL 10
sources. Fail closed if even one selected original is unavailable.
"""
import hashlib,io,json,lzma,os,pathlib,time,urllib.error,urllib.request

ROOT=pathlib.Path(__file__).resolve().parents[2]
HERE=pathlib.Path(__file__).resolve().parent
PRE=HERE/"prespec.json"
OUT=HERE/"inputs"
OLD67=ROOT/"unified_realblind100_inputs/manifest.json"
OLD10=ROOT/"research/graph_unseen25/inputs/manifest.json"
GBD_BASE="https://benchmark-database.de/file/"
MAX_ARCHIVE=50_000_000
MAX_RAW=110_000_000

def hash_bytes(data):
    return hashlib.sha256(data).hexdigest()

def decode_original(data):
    if data.startswith(b"\xfd7zXZ\x00"):
        with lzma.LZMAFile(io.BytesIO(data),"rb") as d:
            parts=[];sofar=0
            while True:
                chunk=d.read(min(1<<20,MAX_RAW-sofar+1))
                if not chunk:break
                sofar+=len(chunk)
                if sofar>MAX_RAW:raise ValueError("decompressed source exceeds size policy")
                parts.append(chunk)
            return b"".join(parts)
    if len(data)>MAX_RAW:raise ValueError("original source exceeds raw size limit")
    return data

def download_original(gbd):
    target=GBD_BASE+gbd+"?context=cnf"
    req=urllib.request.Request(target,headers={
        "User-Agent":"DRNAS-SAT/2026-11-16 (prespecified source-only frozen evaluation)",
        "Accept":"application/x-xz,application/octet-stream,*/*"})
    faults=[]
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req,timeout=60) as remote:
                parts=[];downloaded=0
                while True:
                    block=remote.read(min(1<<20,MAX_ARCHIVE-downloaded+1))
                    if not block:break
                    downloaded+=len(block)
                    if downloaded>MAX_ARCHIVE:raise ValueError("compressed GBD source too large")
                    parts.append(block)
            archive=b"".join(parts)
            raw=decode_original(archive)
            return raw,hash_bytes(archive),len(archive),target
        except (urllib.error.URLError,TimeoutError,OSError,EOFError,lzma.LZMAError) as error:
            faults.append(str(error))
            if attempt<2:time.sleep(2+attempt*2)
    raise RuntimeError("GBD download unavailable (no substitution allowed): "+
                       gbd+" "+repr(faults))

def syntax_only(raw):
    nv=nc=None;count=0;pending=0;maxvar=0
    for line in io.BytesIO(raw):
        tokens=line.decode("ascii").split()
        if not tokens or tokens[0]=="c":continue
        if tokens[0]=="p":
            if nv is not None or len(tokens)!=4 or tokens[1]!="cnf":
                raise ValueError("invalid original DIMACS header")
            nv,nc=int(tokens[2]),int(tokens[3])
            if not (0<nv<=4_000_000 and 0<nc<=8_000_000):
                raise ValueError("DIMACS source upper variable/clause bound")
            continue
        if nv is None:raise ValueError("missing original DIMACS header")
        for term in tokens:
            literal=int(term)
            if abs(literal)>nv:raise ValueError("original literal not in header")
            if literal:
                pending+=1;maxvar=max(maxvar,abs(literal))
            else:
                if pending>2_000_000:raise ValueError("original clause exceeds width bound")
                pending=0;count+=1
    if nv is None or pending!=0 or count!=nc:
        raise ValueError(f"invalid original CNF count {count} != {nc}")
    return {"variables":nv,"clauses":count,"max_variable_used":maxvar}

def check_disjoint(prespec):
    a=json.loads(OLD67.read_text())["sources"]
    b=json.loads(OLD10.read_text())["sources"]
    previous=a+b
    ids={s.get("file_id",s.get("gbd_hash")) for s in previous}
    iso={s.get("isohash") for s in previous}
    old_families={s["family"] for s in previous}
    chosen=prespec["records"]
    assert len(chosen)==10 and {x["id"] for x in chosen}==set(range(10))
    assert len({s["gbd_hash"] for s in chosen})==len(chosen)
    assert len({s["isohash"] for s in chosen})==len(chosen)
    assert all(len(s["gbd_hash"])==len(s["isohash"])==32 for s in chosen)
    dup=({x["gbd_hash"] for x in chosen}&ids)
    dupiso=({x["isohash"] for x in chosen}&iso)
    dupfam=({x["family"] for x in chosen}&old_families)
    if dup or dupiso or dupfam:
        raise RuntimeError("HOLDOUT LEAK: catalog IDs/isohashes/families overlap "+
            repr({"ids":sorted(dup),"isohashes":sorted(dupiso),"families":sorted(dupfam)}))
    return {"old67_manifest_sha256":hash_bytes(OLD67.read_bytes()),
            "old10_manifest_sha256":hash_bytes(OLD10.read_bytes()),
            "previous_source_count":len(previous),
            "previous_family_count":len(old_families),
            "family_disjoint":True,"source_GBD_disjoint":True,
            "source_isohash_disjoint":True}

def size_metadata(choices):
    """Network-only resource eligibility audit, NO downloaded source inspection."""
    records=[]
    for item in choices:
        url=GBD_BASE+item["gbd_hash"]+"?context=cnf"
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"DRNAS-source-freeze-size-audit"},
                                        method="HEAD")
            with urllib.request.urlopen(req,timeout=22) as remote:
                raw=remote.headers.get("Content-Length")
                content_len=int(raw) if raw and raw.isdigit() else None
                content_type=remote.headers.get("Content-Type")
            record={"id":item["id"],"family":item["family"],
                    "gbd":item["gbd_hash"],
                    "compressed_size_bytes":content_len,
                    "content_type":content_type}
        except Exception as exc:
            record={"id":item["id"],"family":item["family"],
                    "gbd":item["gbd_hash"],"compressed_size_bytes":None,
                    "head_error":str(exc)[:170]}
        print("GRAPH_DISJOINT25_SIZE_METADATA "+json.dumps(record,sort_keys=True),
              flush=True)
        records.append(record)
    too_big=[x for x in records
             if x["compressed_size_bytes"] is not None
             and x["compressed_size_bytes"]>MAX_ARCHIVE]
    if too_big:
        raise ValueError("PREDECLARED_ORIGINALS_EXCEED_DOWNLOAD_BUDGET: "+
                         json.dumps(too_big,sort_keys=True))
    return records

def main():
    prespec=json.loads(PRE.read_text())
    assert prespec["protocol"]=="DRNAS-GRAPH-FAMILY-DISJOINT25-SMALL-PRESPEC-V2"
    assert prespec["candidate_locked_before_any_evaluation"]
    assert prespec["no_replacement_after_freeze_or_outcomes"]
    provenance=check_disjoint(prespec)
    size_metadata(prespec["records"])
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/"manifest.json").exists():
        raise RuntimeError("existing source-frozen manifest: REFUSE overwrite")
    records=[]
    for spec in prespec["records"]:
        gbd=spec["gbd_hash"]
        raw,archive_sha,archive_bytes,url=download_original(gbd)
        bounds=syntax_only(raw)
        file=OUT/f'{spec["id"]:02d}-{gbd}.cnf'
        if file.exists():raise RuntimeError("original source already frozen: "+str(file))
        file.write_bytes(raw)
        record={**spec,"file_id":gbd,"path":str(file.relative_to(ROOT)),
                "sha256":hash_bytes(raw),"source_bytes":len(raw),
                "archive_sha256":archive_sha,"archive_bytes":archive_bytes,
                "source_url":url,"catalog_label":"unknown",
                **bounds}
        records.append(record)
        print("GRAPH_DISJOINT25_FROZEN_SOURCE "+json.dumps({
            "id":record["id"],"gbd":gbd,"family":record["family"],
            "source_sha256":record["sha256"],
            "variables":record["variables"],"clauses":record["clauses"],
            "source_bytes":record["source_bytes"]},sort_keys=True),flush=True)
    manifest={"status":"FROZEN_SOURCE_ONLY_NO_SOLVER_RUN",
              "protocol":prespec["protocol"],
              "prespec_sha256":hash_bytes(PRE.read_bytes()),
              "original_2025_track":"main_2025",
              "selected_count":len(records),"sources":records,
              "provenance":provenance,
              "fixed_selection_before_source_download":True,
              "not_tested_in_this_experiment":True,
              "no_candidate_replacements":True,
              "note":"Source/family/isohash-disjoint from frozen 67+10 datasets, not guaranteed never seen anywhere else."}
    temporary=OUT/"manifest.json.tmp"
    temporary.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    os.replace(temporary,OUT/"manifest.json")
    print("GRAPH_DISJOINT25_SOURCE_FREEZE_COMPLETE "+json.dumps({
        "sources":len(records),"families":len({s["family"] for s in records}),
        "source_manifest_sha256":hash_bytes((OUT/"manifest.json").read_bytes()),
        **provenance},sort_keys=True),flush=True)

if __name__=="__main__":main()
