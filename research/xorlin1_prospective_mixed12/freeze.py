#!/usr/bin/env python3
"""Freeze twelve preregistered original GBD SAT-competition XOR, Tseitin, SAT and non-XOR CNFs.

Source selection v2 is permanently committed in prespec.json (commit 77453e6) after v1 source-only resource abort; no solver outcomes observed.
NO solver, family recognizer, proof emitter, source performance classifier,
SAT/UNSAT classification algorithm or candidate-generated output may run in this script.

Recheck exact original GBD hashes and 16/32-digit ISO hashes against the
five previous development manifests (107 CNFs); download and freeze ALL 10
sources. Fail closed if even one selected original is unavailable.
"""
import hashlib,io,json,lzma,os,pathlib,time,urllib.error,urllib.request

ROOT=pathlib.Path(__file__).resolve().parents[2]
HERE=pathlib.Path(__file__).resolve().parent
PRE=HERE/"prespec.json"
OUT=HERE/"inputs"
OLD67=ROOT/"unified_realblind100_inputs/manifest.json"
OLD10=ROOT/"research/graph_unseen25/inputs/manifest.json"
OLD_OTHER=ROOT/"research/graph_family_disjoint25/inputs/manifest.json"
OLD_XOR3=ROOT/"research/xor3_prospective_gbd10/inputs/manifest.json"
OLD_XOR234=ROOT/"research/xor234_prospective_tseitin10/inputs/manifest.json"
GBD_BASE="https://benchmark-database.de/file/"
MAX_ARCHIVE=20_000_000
MAX_RAW=50_000_000

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
    earlier=[
       OLD67,OLD10,OLD_OTHER,OLD_XOR3,OLD_XOR234
    ]
    manifests=[json.loads(p.read_text()) for p in earlier]
    previous=[source for m in manifests for source in m["sources"]]
    assert len(previous)==107,("PRIOR_REFERENCE_COUNT_CHANGED",len(previous))
    old_ids={s.get("gbd_hash",s.get("file_id")) for s in previous}
    old_isos={s.get("isohash") for s in previous if s.get("isohash")}
    old_isos.update(s.get("isohash2") for s in previous if s.get("isohash2"))
    chosen=prespec["sources"]
    assert len(chosen)==12 and {x["id"] for x in chosen}==set(range(12))
    assert len({s["gbd_hash"] for s in chosen})==12
    assert len({s["isohash"] for s in chosen})==12
    assert len({s["isohash2"] for s in chosen})==12
    assert all(len(s["gbd_hash"])==len(s["isohash"])==32
               and len(s["isohash2"])==16 for s in chosen)
    duplicated_ids=sorted({x["gbd_hash"] for x in chosen}&old_ids)
    duplicated_iso=sorted(({x["isohash"] for x in chosen} |
                           {x["isohash2"] for x in chosen})&old_isos)
    cross_iso={x["isohash"] for x in chosen}&{x["isohash2"] for x in chosen}
    if duplicated_ids or duplicated_iso or cross_iso:
        raise RuntimeError( "OLD107_HOLDOUT_SOURCE_IDENTITY_LEAK: " +
              repr({"duplicate_gbd":duplicated_ids,
                    "duplicate_isohash_or_isohash2":duplicated_iso,"cross_new_isohash":sorted(cross_iso)}))
    return {"old_manifests_sha256":{str(p.relative_to(ROOT)):hash_bytes(p.read_bytes())
                                    for p in earlier},
            "previous_source_count":107,
            "previous_gbd_overlap":0,"previous_iso_overlap":0,
            "source_GBD_disjoint":True,"source_isohashes_disjoint":True,
            "family_disjoint":False}
    
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
        print("XORLIN1_PROSPECTIVE_SIZE_METADATA "+json.dumps(record,sort_keys=True),
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
    assert prespec["protocol"]=="DRNAS-XORLIN1-PROSPECTIVE-MIXED12-STRICT-20261117-V2"
    assert prespec["selection_type"].startswith("metadata-only")
    assert prespec["no_source_substitution_after_outcomes"]
    provenance=check_disjoint(prespec)
    size_metadata(prespec["sources"])
    OUT.mkdir(parents=True,exist_ok=True)
    if (OUT/"manifest.json").exists():
        raise RuntimeError("existing source-frozen manifest: REFUSE overwrite")
    records=[]
    for spec in prespec["sources"]:
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
        print("XORLIN1_PROSPECTIVE_FROZEN_SOURCE "+json.dumps({
            "id":record["id"],"gbd":gbd,"family":record["family"],
            "source_sha256":record["sha256"],
            "variables":record["variables"],"clauses":record["clauses"],
            "source_bytes":record["source_bytes"]},sort_keys=True),flush=True)
    manifest={"status":"FROZEN_SOURCE_ONLY_NO_SOLVER_RUN",
              "protocol":prespec["protocol"],
              "prespec_sha256":hash_bytes(PRE.read_bytes()),
              "original_track_set":sorted({x["track"] for x in records}),
              "selected_count":len(records),"sources":records,
              "provenance":provenance,
              "fixed_selection_before_source_download":True,
              "not_tested_in_this_experiment":True,
              "no_candidate_replacements":True,
              "note":"Source identity/isohash disjoint from 107 prior frozen CNFs. Seven mixed catalog families; labels are only metadata and never solver input."}
    temporary=OUT/"manifest.json.tmp"
    temporary.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    os.replace(temporary,OUT/"manifest.json")
    print("XORLIN1_PROSPECTIVE_SOURCE_FREEZE_COMPLETE "+json.dumps({
        "sources":len(records),"families":len({s["family"] for s in records}),
        "source_manifest_sha256":hash_bytes((OUT/"manifest.json").read_bytes()),
        **provenance},sort_keys=True),flush=True)

if __name__=="__main__":main()
