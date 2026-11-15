#!/usr/bin/env python3
"""Real source-disjoint SAT2026 catalog original-CNF test; no synthetic/re-encoded inputs.

Frozen selections were made before testing. One logical CPU per process. Outcomes
are distinguished as independently checked structural UNSAT, raw solver claims,
UNKNOWN, ineligible-size, and download errors. This is an OOD probe, not blind
SAT Competition scoring or standard DRAT/LRAT proof coverage.
"""
import argparse
import hashlib
import json
import lzma
import os
import resource
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG_COMMIT = "d2f8f186dacc48b9bab7e4374aef0a3f46b96582"
CATALOG_URL = ("https://raw.githubusercontent.com/satcompetition/2026/" +
               CATALOG_COMMIT + "/downloads/benchmark-compilation-script/benchmarks2026.csv")
# Preregistered, disjoint from the prior original12 and original PCMAX20.
# Four shards, four formulas each. Original byte streams are never modified.
CASES = [
    ("1680176921bab3f01c4f7c33791c8c23","schreiber","school-timetabling","unknown"),
    ("5faba478cb08194407b5ec957ab08599","schreiber","school-timetabling","sat"),
    ("6a0bd19edf62a95755d7d58f20417421","schreiber","school-timetabling","sat"),
    ("8ce8dbfecaf77bdc2229bf552cc757a8","schreiber","school-timetabling","sat"),
    ("9aa85c5c114245c182ed6afbe3d8daed","schreiber","school-timetabling","unsat"),
    ("a9a88f9a0016b672d4407e8768051de0","schreiber","school-timetabling","unsat"),
    ("ad2247443454da1fbd4543dd1fa5b57c","schreiber","school-timetabling","unsat"),
    ("b0abaa97c4663edc2048d86de3e2b226","schreiber","school-timetabling","unsat"),
    ("d28a602947d617e451ee58799debc160","schreiber","school-timetabling","unsat"),
    ("fa3e27fb7209620b792d5c75a75d669b","schreiber","school-timetabling","unknown"),
    ("266e890b706cf336378bf148bbda1aff","zheng","exam-scheduling","unsat"),
    ("4676e00348f494bfbee37c5ec592ec7c","zheng","exam-scheduling","unsat"),
    ("5d8b47745dba3fe50f9c8712be389cd5","zheng","exam-scheduling","unsat"),
    ("6045a464ee2c202630728c86168efae4","zheng","exam-scheduling","unsat"),
    ("68ab843144710875f37f714ef8872630","zheng","exam-scheduling","unsat"),
    ("6eb49b2189f09219995daa0aaf54d72d","zheng","exam-scheduling","unsat"),
]
PRIOR_2026 = {
    "47173e8ab499159d3aa301b0101fe170", "48432767076e402d2accbf2da7260885",
    "546a73eef02dda3719018050b09e9392", "5f10d57cf49586518e1a103f03984e74",
    "93f5b06574be09ad5b46778248421019", "17baf7fa29b82de40adb837adee0dffb",
    "353837b1b8fdcab109c3925fc9d73512", "03e49a528251af9a7b7e1ca03c33b162",
    "046d5e1432c39dc4b085a80fab3a8be6", "0d082b8fa36f662217bee5524cd24d3a",
    "12ac1c71ff0405cc150c2a2db6c4a255", "13eb6e05dd8decd305dae2fc148b0ede",
}
MAX_ARCHIVE = 55 * 1024 * 1024
MAX_RAW = 180 * 1024 * 1024
CAP_S = 8.0
GUARD_MS = 2000

def get(url, out, max_bytes):
    err = None
    for attempt in range(2):
        try:
            total = 0
            req = urllib.request.Request(url,headers={"User-Agent":"DRNAS-PCMAX-Real2026-OOD/1.0"})
            with urllib.request.urlopen(req,timeout=75) as src, out.open("wb") as fd:
                while True:
                    chunk=src.read(1<<20)
                    if not chunk: break
                    total+=len(chunk)
                    if total>max_bytes: raise ValueError("max_archive_bytes_exceeded")
                    fd.write(chunk)
            return total
        except Exception as exc:
            err = exc
            out.unlink(missing_ok=True)
            if attempt == 0: time.sleep(1)
    raise RuntimeError("download_failed: " + repr(err))

def unpack(archive, cnf):
    with archive.open("rb") as fd:
        magic=fd.read(6)
    reader=lzma.open if magic==b"\xfd7zXZ\x00" else open
    total=0
    sha=hashlib.sha256()
    with reader(archive,"rb") as inp, cnf.open("wb") as out:
        while True:
            buf=inp.read(1<<20)
            if not buf:break
            total+=len(buf)
            if total>MAX_RAW:raise ValueError("max_raw_bytes_exceeded")
            sha.update(buf)
            out.write(buf)
    return total,sha.hexdigest()

def header(cnf):
    with cnf.open("rb") as inp:
        for _ in range(10000):
            line=inp.readline(50000)
            if not line:break
            if line.startswith(b"p cnf "):
                fields=line.split()
                if len(fields)==4:
                    n,c=map(int,fields[2:])
                    if n<=0 or c<0:raise ValueError("invalid_DIMACS_header")
                    return n,c
    raise ValueError("missing_DIMACS_header")

def timed(cmd, seconds):
    started=time.perf_counter()
    try:
        run=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           text=True,timeout=seconds,check=False)
        return dict(rc=run.returncode,wall_s=round(time.perf_counter()-started,6),
                    timeout=False,stdout=run.stdout[-18000:],stderr=run.stderr[-3000:])
    except subprocess.TimeoutExpired:
        return dict(rc=None,wall_s=round(time.perf_counter()-started,6),
                    timeout=True,stdout="",stderr="TIMEOUT")

def trial(arm, cnf, cert, binpaths, checker):
    if arm=="DRNAS_STRUCTURAL":
        cmd=[str(binpaths["guard"]),str(cnf),"--mode","core","--time","8",
             "--pcmax-only","--pcmax-budget-ms",str(GUARD_MS),
             "--pcmax-certificate",str(cert)]
        r=timed(cmd,CAP_S)
    elif arm=="KISSAT":
        r=timed([str(binpaths["kissat"]),"--quiet",str(cnf)],CAP_S)
    else:
        r=timed([str(binpaths["cadical"]),"-q",str(cnf)],CAP_S)
    row={k:r[k] for k in ("rc","wall_s","timeout")}
    row.update(status="TIMEOUT" if r["timeout"] else
               "SAT_REPORTED" if r["rc"]==10 else
               "UNSAT_REPORTED" if r["rc"]==20 else
               "UNKNOWN" if r["rc"] in (0,124) else "ERROR",
               verified=False,check_s=None)
    if arm=="DRNAS_STRUCTURAL":
        markers=[line[len("c PCMAX_CAPACITY "):] for line in r["stdout"].splitlines()
                 if line.startswith("c PCMAX_CAPACITY ")]
        if markers:
            try:
                telemetry=json.loads(markers[-1])
                row.update(reason=telemetry.get("reason"),
                           groups=telemetry.get("groups"),machines=telemetry.get("machines"))
            except ValueError:row["reason"]="bad_telemetry"
        if r["rc"]==20:
            if not cert.is_file():
                row["status"]="INVALID_MISSING_CERTIFICATE"
            else:
                v=timed([sys.executable,str(checker),str(cnf),str(cert)],45)
                row["check_s"]=v["wall_s"]
                if v["rc"]==0 and "UNSAT_STRUCTURAL_CERTIFICATE_VERIFIED" in v["stdout"]:
                    row["status"]="UNSAT_STRUCTURAL_VERIFIED"
                    row["verified"]=True
                else:
                    row["status"]="INVALID_CERTIFICATE"
                    row["checker_error"]=v["stderr"][-200:]
        elif cert.exists():
            row["status"]="INVALID_CERTIFICATE_ON_UNKNOWN"
    return row

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--shard",type=int,required=True,choices=range(4))
    a.add_argument("--out",type=Path,required=True)
    a.add_argument("--guard",type=Path,default=Path("build/drnas-pcmax"))
    a.add_argument("--kissat",type=Path,default=Path("build/kissat"))
    a.add_argument("--cadical",type=Path,default=Path("build/cadical"))
    args=a.parse_args()
    assert len(CASES)==16 and len({x[0] for x in CASES})==16
    assert set(x[0] for x in CASES).isdisjoint(PRIOR_2026)
    assert args.out.exists() is False
    args.out.mkdir(parents=True)
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    binpaths={name:path.resolve() for name,path in
              (("guard",args.guard),("kissat",args.kissat),("cadical",args.cadical))}
    for path in binpaths.values():assert path.is_file(),path
    checker=(ROOT/"research/pcmax_capacity/check_capacity.py").resolve()
    prior=json.loads((ROOT/"research/pcmax_capacity/sources20.json").read_text())
    prior_sha={x["sha256"] for x in prior["entries"]}
    raw_catalog=args.out/"catalog2026.csv"
    get(CATALOG_URL,raw_catalog,2000000)
    catalog={}
    for line in raw_catalog.read_text().splitlines():
        cols=line.split()
        if len(cols)==6:catalog[cols[0]]=tuple(cols[1:])
    for md5, author, family, label in CASES:
        assert md5 in catalog,(md5,"catalog_missing")
        assert catalog[md5][:3]==(author,family,label),(md5,catalog[md5])
    selected=[dict(md5=md5,author=author,family=family,label=label,
                   url="https://benchmark-database.de/file/"+md5+"?context=cnf",
                   index=i) for i,(md5,author,family,label) in enumerate(CASES)
                   if i%4==args.shard]
    frozen=dict(protocol="SOURCE_DISTINCT_REAL2026_OOD_V1",
                selection="prespecified_16_catalog_IDs_without_prior_original12_or_pcmax20",
                catalog_commit=CATALOG_COMMIT,catalog_url=CATALOG_URL,
                catalog_sha256=hashlib.sha256(raw_catalog.read_bytes()).hexdigest(),
                source_ids=[x[0] for x in CASES],shard=args.shard,cpu=cpu,
                cap_s=CAP_S,guard_budget_ms=GUARD_MS,
                arms=["DRNAS_STRUCTURAL","KISSAT","CADICAL"],
                binaries={k:hashlib.sha256(p.read_bytes()).hexdigest() for k,p in binpaths.items()},
                checker_sha256=hashlib.sha256(checker.read_bytes()).hexdigest())
    (args.out/"frozen.json").write_text(json.dumps(frozen,indent=2)+"\n")
    cases=[]
    rows=[]
    logfile=args.out/"trials.jsonl"
    with logfile.open("w") as fh:
        for entry in selected:
            prefix=f"{entry['index']:02d}-{entry['md5']}"
            packed=args.out/(prefix+".xz")
            cnf=args.out/(prefix+".cnf")
            meta=dict(entry)
            try:
                packed_bytes=get(entry["url"],packed,MAX_ARCHIVE)
                unpacked,sha=unpack(packed,cnf)
                nv,nclause=header(cnf)
                if sha in prior_sha:raise ValueError("duplicate_original20_SHA256")
                meta.update(source_sha256=sha,variables=nv,clauses=nclause,
                            compressed_bytes=packed_bytes,raw_bytes=unpacked,
                            input_status="RETRIEVED")
            except Exception as ex:
                meta.update(input_status="SOURCE_ERROR",error=repr(ex))
                cnf.unlink(missing_ok=True)
                packed.unlink(missing_ok=True)
                print("REAL26_INPUT "+json.dumps(meta,sort_keys=True),flush=True)
                cases.append(meta)
                continue
            print("REAL26_INPUT "+json.dumps(meta,sort_keys=True),flush=True)
            cases.append(meta)
            # rotate arm order within the pre-registered four-source shard
            arm_order=["DRNAS_STRUCTURAL","KISSAT","CADICAL"]
            rot=entry["index"]%len(arm_order)
            arm_order=arm_order[rot:]+arm_order[:rot]
            for arm in arm_order:
                cert=args.out/(prefix+".capacity.json")
                cert.unlink(missing_ok=True)
                result=trial(arm,cnf,cert,binpaths,checker)
                result.update(source_id=entry["md5"],index=entry["index"],
                              source_sha256=sha,label=entry["label"],family=entry["family"],arm=arm,
                              variables=nv,clauses=nclause)
                if entry["label"]=="sat" and result["status"].startswith("UNSAT"):
                    result["status"]="CRITICAL_FALSE_UNSAT_VS_CATALOG"
                if result["status"].startswith("INVALID") or result["status"].startswith("CRITICAL"):
                    result["audit_failure"]=True
                else:result["audit_failure"]=False
                rows.append(result)
                fh.write(json.dumps(result,sort_keys=True)+"\n")
                fh.flush()
                print("REAL26_TRIAL "+json.dumps({k:result.get(k) for k in
                      ("source_id","arm","status","wall_s","check_s","reason","variables","clauses")},
                      sort_keys=True),flush=True)
            # Large input is reproducible via file ID+hash; do not upload gigabytes.
            if cnf.stat().st_size>10_000_000:cnf.unlink()
            if packed.stat().st_size>10_000_000:packed.unlink()
    report=dict(protocol="SOURCE_DISTINCT_REAL2026_OOD_V1",shard=args.shard,
                cases=cases,rows=rows,attempted=len(selected),
                inputs_ok=sum(x["input_status"]=="RETRIEVED" for x in cases),
                structural_verified=sum(x["verified"] for x in rows),
                audit_errors=sum(x["audit_failure"] for x in rows),
                note="Original CNFs, not modified/re-encoded. Only DRNAS structural certificates are independently checked here; raw CDCL statuses lack proof/model validation.")
    (args.out/"summary.json").write_text(json.dumps(report,indent=2)+"\n")
    print("REAL26_SUMMARY "+json.dumps({k:report[k] for k in
          ("shard","attempted","inputs_ok","structural_verified","audit_errors")},sort_keys=True),flush=True)
    if report["audit_errors"]:raise SystemExit("AUDIT FAILURE — see trials.jsonl")

if __name__=="__main__":
    main()
