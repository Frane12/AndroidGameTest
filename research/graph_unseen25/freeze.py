#!/usr/bin/env python3
"""Freeze SAT2025 graph CNF originals BEFORE running any solver or classifier.

The exact ordered GBD hashes are permanently prespecified in prespec.json
(committed a37fe1b before any solver evaluation). If even one original
cannot be downloaded or safely parsed, this prepare stage ABORTS. Never
replace a selected source according to solver outcomes.
"""
import hashlib,io,json,lzma,os,pathlib,sys,time,urllib.error,urllib.request

ROOT=pathlib.Path(__file__).resolve().parents[2]
HERE=pathlib.Path(__file__).resolve().parent
PRE=HERE/"prespec.json"
OUT=HERE/"inputs"
FROZEN=ROOT/"unified_realblind100_inputs/manifest.json"
MAX_ARCHIVE=45_000_000
MAX_SOURCE=100_000_000

def digest(src):
    return hashlib.sha256(src).hexdigest()

def bounded_download(url):
    req=urllib.request.Request(url,headers={
        "User-Agent":"DRNAS-SAT-Research/1.0 (source-only frozen benchmark)",
        "Accept":"application/x-xz,application/octet-stream,*/*"})
    errors=[]
    for retry in range(3):
        try:
            with urllib.request.urlopen(req,timeout=65) as response:
                body=response.read(MAX_ARCHIVE+1)
                if len(body)>MAX_ARCHIVE:raise ValueError("compressed instance size limit")
            if body.startswith(b"\xfd7zXZ\x00"):
                with lzma.LZMAFile(io.BytesIO(body),"rb") as source:
                    chunks=[];n=0
                    while True:
                        c=source.read(min(1<<20,MAX_SOURCE-n+1))
                        if not c:break
                        n+=len(c)
                        if n>MAX_SOURCE:raise ValueError("decompressed source size limit")
                        chunks.append(c)
                    raw=b"".join(chunks)
            else:
                raw=body
            if len(raw)>MAX_SOURCE:raise ValueError("uncompressed source size limit")
            return raw,digest(body),len(body)
        except (urllib.error.URLError,TimeoutError,OSError,EOFError,lzma.LZMAError) as e:
            errors.append(str(e))
            if retry<2:time.sleep(2+retry*2)
    raise RuntimeError("original download failed: "+repr(errors))

def dimacs_metadata(raw):
    # Blind syntax-only parse: never inspect/compute satisfying status, type,
    # clique or graph presence before all source bytes are SHA-frozen.
    nv=nc=None;current=0;count=0;max_seen=0
    for line in io.BytesIO(raw):
        try:tok=line.decode("ascii").split()
        except UnicodeError as exc:raise ValueError("DIMACS non-ASCII bytes") from exc
        if not tok or tok[0]=="c":continue
        if tok[0]=="p":
            if nv is not None or len(tok)!=4 or tok[1]!="cnf":
                raise ValueError("malformed DIMACS header")
            nv,nc=int(tok[2]),int(tok[3])
            if not (0<nv<=2_000_000 and 0<nc<=4_000_000):
                raise ValueError("DIMACS declared source size gate")
            continue
        if nv is None:raise ValueError("no source header")
        for field in tok:
            literal=int(field)
            if abs(literal)>nv:raise ValueError("source variable out of bounds")
            if literal:
                current+=1
                max_seen=max(max_seen,abs(literal))
            else:
                if current>2_000_000:raise ValueError("source max clause size")
                count+=1;current=0
    if nv is None or current or count!=nc:
        raise ValueError(f"DIMACS clause count mismatch got={count} declared={nc}")
    return {"variables":nv,"clauses":count,"max_variable_used":max_seen}

def main():
    expected=json.loads(PRE.read_text())
    assert expected["protocol"]=="DRNAS-GRAPH-UNSEEN-2025-FREEZE-V1"
    assert expected["no_solver_before_source_sha_freeze"]
    choices=expected["instances"]
    assert len(choices)==expected["number_selected"]==10
    assert [i["id"] for i in choices]==list(range(10))
    assert len({i["gbd_hash"] for i in choices})==10
    previously=json.loads(FROZEN.read_text())
    known={s["file_id"] for s in previously["sources"]}
    overlap=sorted({x["gbd_hash"] for x in choices}&known)
    if overlap:raise RuntimeError("known 67-sources GBD collision: "+str(overlap))
    OUT.mkdir(parents=True,exist_ok=True)
    assert not (OUT/"manifest.json").exists(),"refusing overwrite of prior holdout source freeze"
    records=[]
    for spec in choices:
        gbd=spec["gbd_hash"]
        if len(gbd)!=32 or not all(c in "0123456789abcdef" for c in gbd):
            raise ValueError("bad frozen metadata hash "+gbd)
        url=f"https://benchmark-database.de/file/{gbd}?context=cnf"
        raw,archive_sha,archive_bytes=bounded_download(url)
        meta=dimacs_metadata(raw)
        path=OUT/f'{spec["id"]:02d}-{gbd}.cnf'
        if path.exists():raise RuntimeError("candidate already in workspace: "+str(path))
        path.write_bytes(raw)
        record={"id":spec["id"],"file_id":gbd,
            "gbd_hash":gbd,"gbd_catalog_family":spec["family"],
            "author":spec["author"],"track":"main_2025",
            "family":spec["family"],"filename":spec["filename"],
            "catalog_label":"unknown", # neutral; source labels never given to solvers
            "path":str(path.relative_to(ROOT)),
            "sha256":digest(raw),"bytes":len(raw),
            "archive_sha256":archive_sha,
            "archive_bytes":archive_bytes,"url":url,**meta}
        records.append(record)
        print("GRAPH_UNSEEN25_SOURCE_FREEZE "+json.dumps({
            "id":spec["id"],"gbd":gbd,"family":spec["family"],
            "sha256":record["sha256"],"bytes":len(raw),
            "vars":record["variables"],"clauses":record["clauses"]},
            sort_keys=True),flush=True)
    manifest={
        "status":"SOURCE_FROZEN_NO_SOLVER_TESTED",
        "protocol":expected["protocol"],
        "prespec_sha256":digest(PRE.read_bytes()),
        "frozen_2026_manifest_sha256":digest(FROZEN.read_bytes()),
        "source_count":len(records),
        "all_gbd_hashes_disjoint_from_old67":True,
        "sources":records,
        "no_outcome_based_replacements":True,
        "track":"main_2025",
        "scope":"Prospective for this experiment only; cannot assert absence from all historic branches."}
    tmp=OUT/"manifest.json.tmp"
    tmp.write_text(json.dumps(manifest,sort_keys=True,indent=2)+"\n")
    os.replace(tmp,OUT/"manifest.json")
    print("GRAPH_UNSEEN25_FREEZE_READY "+json.dumps(
        {"N":len(records),"manifest_sha256":digest((OUT/"manifest.json").read_bytes()),
        "previous_collision_count":len(overlap),
        "preselected_before_any_solver":True},sort_keys=True),flush=True)

if __name__=="__main__":main()
