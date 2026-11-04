#!/usr/bin/env python3
"""R88 bulk import: true source-identifiable 2025/2026 SAT Competition CNFs.

No solved-time, solver-answer, XOR or structure prefilter. Deterministic
SHA-ranked shard selection, with size/format exclusions logged. Cohorts can be
revisited across different DRNAS projects; only within this R88 database are
prior records excluded. Selection is not globally guaranteed unseen.
"""
from __future__ import annotations
import argparse, csv, hashlib, io, json, os, time
from pathlib import Path
import r32p_real_satcomp26_benchmark as r32p
import r52_prospective_2026_toprefs as r52
import r73_fresh_quick_unseen_2025 as r73
import r88_cooperative as core

PROTO="DRNAS-R88-BULK-OFFICIAL-CNF-20261104-v1"
LISTS={2025:r73.SC2025,2026:r52.URI}
SALT="DRNAS-R88-FROZEN-BEFORE-SOLVE-NO-SPEED-SCREEN"
TARGET=5
SHARDS=4
TRIES=30
MAX_PACKED=10*1024*1024
MAX_RAW=24*1024*1024

def read_catalog(year):
    raw=r52.fetch_bytes(LISTS[year],250000)
    names=[line.rsplit("/",1)[-1].strip() for line in raw.decode().splitlines() if line.strip()]
    core.require(len(names)>=250 and len(names)==len(set(names)),"official catalog malformed")
    return names,hashlib.sha256(raw).hexdigest()

def import_shard(a):
    root=Path(a.out);root.mkdir(parents=True,exist_ok=True)
    names,index_sha=read_catalog(a.year)
    history=set()
    if a.history and Path(a.history).exists():
        history=set(json.loads(Path(a.history).read_text()).get("previous_ids",[]))
    scores={}; scores_hash=""
    if a.year==2026:
        raw=r52.fetch_bytes(r52.SCORES,32*1024*1024)
        scores_hash=hashlib.sha256(raw).hexdigest()
        scores={r["instanceid"]:r["status"] for r in csv.DictReader(io.StringIO(raw.decode()))
                if r.get("solverid")=="biere_cadical3[main]"}
        core.require(len(scores)==400,"2026 official labels incomplete")
    # GITHUB_RUN_NUMBER rotates deterministic source order between runs.
    # Every historical R88 source ID is excluded independent of performance.
    epoch=os.environ.get("GITHUB_RUN_NUMBER","local-0")
    ranked=sorted((x for x in names if x not in history),
         key=lambda x:hashlib.sha256(
            (SALT+":"+str(a.year)+":"+epoch+":"+x).encode()).hexdigest())
    candidates=[x for i,x in enumerate(ranked) if i % a.shards == a.shard]
    selected=[];attempts=[]
    for gbd in candidates[:a.attempts]:
        if len(selected)>=a.target:break
        note={"gbd":gbd,"year":a.year,"shard":a.shard}
        file=root/(str(a.year)+"-"+gbd+".cnf")
        status=scores.get(gbd,"UNKNOWN")
        if a.year==2026 and status not in ("sat-verified","unsat-verified"):
            note["state"]="OFFICIAL_VERDICT_NOT_VERIFIED"
            attempts.append(note);continue
        try:
            packed,redirect=r32p.request_url(
                "https://benchmark-database.de/file/"+gbd,MAX_PACKED,seconds=22)
            plain,compression=r32p.decode(packed)
            core.require(len(plain)<=MAX_RAW,"decompressed size cap")
            file.write_bytes(plain)
            n,clauses=core.read_cnf(file)
            features=core.fingerprint(n,clauses)
            digest=core.sha(file)
            core.require(all(c["sha256"]!=digest for c in selected),
                         "duplicate source content")
            c=dict(gbd=gbd,year=a.year,filename=file.name,sha256=digest,
                 bytes=len(plain),variables=n,clauses=len(clauses),
                 compression=compression,source_url="https://benchmark-database.de/file/"+gbd,
                 source_redirect=redirect,official_status=(
                   "SAT" if status=="sat-verified" else
                   "UNSAT" if status=="unsat-verified" else "UNKNOWN"),
                 historically_used="unknown_outside_R88",
                 selection_not_using_speed_or_structure=True,
                 **{k:v for k,v in features.items() if k not in ("variables","clauses")})
            selected.append(c)
            note.update(state="IMPORTED_ORIGINAL",sha256=digest,bytes=len(plain),
                        structure=features["structure"],n=n,m=len(clauses))
        except Exception as e:
            file.unlink(missing_ok=True)
            note.update(state="FETCH_FORMAT_SIZE_EXCLUDED",
                reason=(type(e).__name__+": "+str(e))[:220])
        attempts.append(note)
        print("R88_BULK_IMPORT",json.dumps(note,sort_keys=True),flush=True)
    manifest=dict(protocol=PROTO,year=a.year,shard=a.shard,shards=a.shards,
        target=a.target,attempted=len(attempts),accepted=len(selected),
        catalog_url=LISTS[a.year],index_sha256=index_sha,
        official_2026_score_sha256=scores_hash,rotation=epoch,
        no_solver_or_XOR_prescreen=True,
        previous_r88_source_ids_excluded=len(history),
        attempts=attempts,cases=selected,
        warnings=[
          "Real original competition DIMACS only; source sizes and format impose selection bias.",
          "Past experiments outside the R88 database may have used these sources.",
          "2025 UNSAT answers lack independent LRAT proof; report provisional only.",
          "2026 original status comes from independently published competition verdict metadata.",
          "Time cap and hardware differ from official SAT Competition benchmarks.",
          "Selection spans 2025/2026 Main pool, not all SAT application domains.",
          "Classifications are structural heuristics, not certified source-domain labels."])
    (root/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    (root/"source.sha256").write_text("".join(
        f'{c["sha256"]}  {c["filename"]}\n' for c in selected))
    core.require(len(selected)>0,"no usable original CNF in shard")
    print("R88_BULK_SHARD_PASS",a.year,a.shard,len(selected),len(attempts),flush=True)

def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as t:
        p=Path(t)/"test.cnf"
        p.write_text("c original\np cnf 3 2\n1 2 0\n-1 3 0\n")
        assert core.read_cnf(p)==(3,[(1,2),(-1,3)])
        assert core.fingerprint(3,core.read_cnf(p)[1])["clauses"]==2
    print("R88_BULK_IMPORT_SELFTEST_PASS")

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("selftest")
    q=sub.add_parser("import")
    q.add_argument("--year",type=int,choices=(2025,2026),required=True)
    q.add_argument("--shard",type=int,required=True)
    q.add_argument("--shards",type=int,default=SHARDS)
    q.add_argument("--target",type=int,default=TARGET)
    q.add_argument("--attempts",type=int,default=TRIES)
    q.add_argument("--out",required=True);q.add_argument("--history")
    a=p.parse_args()
    if a.cmd=="selftest":selftest()
    else:
        core.require(0<=a.shard<a.shards,"invalid shard")
        import_shard(a)

if __name__=="__main__":main()
