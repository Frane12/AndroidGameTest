#!/usr/bin/env python3
"""Original 2026 submitted CNFs: Schreiber timetabling + Zheng exam scheduling.

No reconstruction or CNF conversion. The byte-for-byte input comes from GBD
(file hashes indexed by the official SAT Competition 2026 compilation CSV).
The optional native DRNAS PCMAX guard is run standalone with a finite budget.
Only an independently validated capacity certificate counts as UNSAT.
The catalog label alone NEVER counts as a solver result.
"""
import argparse
import hashlib
import json
import lzma
import os
import resource
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
CATALOG_COMMIT = "d2f8f186dacc48b9bab7e4374aef0a3f46b96582"
CATALOG_URL = ("https://raw.githubusercontent.com/satcompetition/2026/"
               + CATALOG_COMMIT + "/downloads/benchmark-compilation-script/benchmarks2026.csv")
CASES = [
  ("47173e8ab499159d3aa301b0101fe170","schreiber","school-timetabling","unsat"),
  ("48432767076e402daccbf2da7260885","schreiber","school-timetabling","unsat"),
  ("546a73eef02dda3719018050b09e9392","schreiber","school-timetabling","unsat"),
  ("5f10d57cf49586518e1a103f03984e74","schreiber","school-timetabling","unsat"),
  ("93f5b06574be09ad5b46778248421019","schreiber","school-timetabling","unsat"),
  ("17baf7fa29b82de40adb837adee0dffb","schreiber","school-timetabling","sat"),
  ("353837b1b8fdcab109c3925fc9d73512","schreiber","school-timetabling","sat"),
  ("03e49a528251af9a7b7e1ca03c33b162","schreiber","school-timetabling","unknown"),
  ("046d5e1432c39dc4b085a80fab3a8be6","zheng","exam-scheduling","unsat"),
  ("0d082b8fa36f662217bee5524cd24d3a","zheng","exam-scheduling","unsat"),
  ("12ac1c71ff0405cc150c2a2db6c4a255","zheng","exam-scheduling","unsat"),
  ("13eb6e05dd8decd305dae2fc148b0ede","zheng","exam-scheduling","unsat"),
]
MAX_ARCHIVE = 75_000_000
MAX_CNF = 210_000_000

def retrieve(url, path, limit):
    headers={"User-Agent":"DRNAS-native-PCMAX-original-2026-audit/1.0"}
    request=urllib.request.Request(url,headers=headers)
    t=time.perf_counter()
    size=0
    with urllib.request.urlopen(request,timeout=75) as s, path.open("wb") as f:
        while True:
            b=s.read(1<<20)
            if not b: break
            size+=len(b)
            if size>limit:
                raise ValueError("download_exceeds_75MB")
            f.write(b)
    return round(time.perf_counter()-t,4),size

def unpack(source, target):
    total=0
    op = lzma.open if source.open("rb").read(6)==b"\xfd7zXZ\x00" else open
    with op(source,"rb") as f, target.open("wb") as out:
        while True:
            piece=f.read(1<<20)
            if not piece:break
            total+=len(piece)
            if total>MAX_CNF:
                raise ValueError("unpacked_exceeds_210MB")
            out.write(piece)
    return total

def header(path):
    with path.open("rb") as f:
        for _ in range(100000):
            line=f.readline(50000)
            if not line:break
            if line.lstrip().startswith(b"p cnf "):
                parts=line.split()
                if len(parts)==4:return int(parts[2]),int(parts[3])
    raise ValueError("DIMACS_header_not_found")

def timed(cmd, limit):
    t=time.perf_counter()
    try:
        p=subprocess.run(cmd, capture_output=True, text=True, timeout=limit,check=False)
        return dict(returncode=p.returncode,timeout=False,
                    wall_s=round(time.perf_counter()-t,6),
                    stdout=p.stdout[-50000:],stderr=p.stderr[-10000:])
    except subprocess.TimeoutExpired:
        return dict(returncode=None,timeout=True,
                    wall_s=round(time.perf_counter()-t,6),
                    stdout="",stderr="hard_process_timeout")

def dump(row,fh):
    fh.write(json.dumps(row,sort_keys=True)+"\n")
    fh.flush()
    print("PCMAX2026_ORIGINAL_TRIAL "+json.dumps(row,sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--binary",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--budget-ms",type=int,default=1000)
    p.add_argument("--repetitions",type=int,default=2)
    a=p.parse_args()
    assert 0<a.budget_ms<=5000 and a.repetitions in (1,2,3)
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    a.out.mkdir(parents=True,exist_ok=False)
    src_dir=a.out/"official-original-inputs"
    src_dir.mkdir()
    cert_dir=a.out/"certificates"
    cert_dir.mkdir()
    checker=REPO/"research/pcmax_capacity/check_capacity.py"
    assert checker.exists()
    cat_path=a.out/"original2026-official-catalog.csv"
    cat_s,cat_bytes=retrieve(CATALOG_URL,cat_path,3_000_000)
    catalog={}
    for line in cat_path.read_text().splitlines():
        parts=line.split()
        if len(parts)==6:
            digest, author, family, label, iso, participating=parts
            catalog[digest]=dict(author=author,family=family,label=label,
                                  iso=iso,participating=participating)
    frozen=[]
    for md5,author,family,label in CASES:
        assert catalog[md5]["author"]==author and catalog[md5]["family"]==family
        assert catalog[md5]["label"]==label,(md5,catalog[md5])
        frozen.append(dict(file_id=md5,author=author,family=family,catalog_label=label,
               url="https://benchmark-database.de/file/"+md5+"?context=cnf"))
    (a.out/"frozen_selection.json").write_text(json.dumps(dict(
        official_csv_url=CATALOG_URL,official_csv_sha256=hashlib.sha256(cat_path.read_bytes()).hexdigest(),
        cases=frozen,repetitions=a.repetitions,discovery_budget_ms=a.budget_ms,
        process_cpu=cpu,base_binary_sha256=hashlib.sha256(a.binary.read_bytes()).hexdigest(),
        checker_sha256=hashlib.sha256(checker.read_bytes()).hexdigest()),indent=2)+"\n")
    old_manifest=json.loads((REPO/"research/pcmax_capacity/sources20.json").read_text())
    existing_sha={x["sha256"] for x in old_manifest["entries"]}
    rows=[]
    with (a.out/"trials.jsonl").open("w") as log:
        for i,entry in enumerate(frozen):
            cnf=src_dir/(f"{i:02d}-{entry['file_id']}.cnf")
            archive=src_dir/(f"{i:02d}-{entry['file_id']}.cnf.xz")
            base={k:entry[k] for k in ("file_id","author","family","catalog_label")}
            try:
                download_s,archive_bytes=retrieve(entry["url"],archive,MAX_ARCHIVE)
                decomp_bytes=unpack(archive,cnf)
                nv,nclauses=header(cnf)
                compressed_hash=hashlib.sha256(archive.read_bytes()).hexdigest()
                source_sha=hashlib.sha256(cnf.read_bytes()).hexdigest()
                if source_sha in existing_sha:
                    raise ValueError("source_SHA256_duplicate_of_PCMax20")
                base.update(download_s=download_s,archive_bytes=archive_bytes,
                            decompressed_bytes=decomp_bytes,variables=nv,
                            clauses=nclauses,archive_sha256=compressed_hash,source_sha256=source_sha)
                print("PCMAX2026_ORIGINAL_INPUT "+json.dumps(base,sort_keys=True),flush=True)
            except Exception as e:
                record=dict(**base,status="INPUT_ERROR",detail=str(e))
                dump(record,log);rows.append(record)
                if cnf.exists():cnf.unlink()
                if archive.exists():archive.unlink()
                continue
            for rep in range(a.repetitions):
                certificate=cert_dir/(f"{i:02d}-{entry['file_id']}-r{rep}.capacity.json")
                command=[str(a.binary.resolve()),str(cnf.resolve()),
                  "--mode","core","--time",str(a.budget_ms/1000+5),
                  "--pcmax-only","--pcmax-budget-ms",str(a.budget_ms),
                  "--pcmax-certificate",str(certificate.resolve())]
                native=timed(command, limit=a.budget_ms/1000+15)
                messages=[json.loads(s[len("c PCMAX_CAPACITY "):])
                          for s in native["stdout"].splitlines()
                          if s.startswith("c PCMAX_CAPACITY ")]
                telemetry=messages[-1] if messages else {}
                row=dict(**base,rep=rep,native_wall_s=native["wall_s"],
                         native_rc=native["returncode"],status="UNKNOWN",
                         reason=telemetry.get("reason","no_telemetry"),
                         reported_counts={k:telemetry.get(k) for k in
                          ("groups","machines","demand","capacity")},verified=False)
                if native["returncode"]==20 and "s UNSATISFIABLE" in native["stdout"]:
                    if not certificate.exists():
                        row.update(status="INVALID_MISSING_CERTIFICATE")
                    else:
                        check=timed([sys.executable,str(checker.resolve()),
                            str(cnf.resolve()),str(certificate.resolve())],limit=120)
                        row["checker_wall_s"]=check["wall_s"]
                        row["total_wall_s"]=round(native["wall_s"]+check["wall_s"],6)
                        try:
                            proof=json.loads(check["stdout"])
                            if check["returncode"]==0 and proof.get("status")=="UNSAT_STRUCTURAL_CERTIFICATE_VERIFIED":
                                row.update(status="UNSAT_VERIFIED",verified=True,
                                    demand=proof["required"],capacity_sum=proof["capacity_sum"])
                                if entry["catalog_label"]=="sat":
                                    row["status"]="CRITICAL_UNSAT_VS_SAT_CATALOG"
                            else:
                                row.update(status="CERTIFICATE_REJECTED",
                                           checker_rc=check["returncode"],
                                           checker_error=check["stderr"][-1200:])
                        except Exception:
                            row.update(status="CERTIFICATE_REJECTED",
                                       checker_rc=check["returncode"],
                                       checker_error=check["stderr"][-1200:])
                elif native["returncode"]==0 and "s UNKNOWN" in native["stdout"]:
                    if certificate.exists():
                        row["status"]="INVALID_UNKNOWN_CERTIFICATE_EXISTS"
                else:
                    row.update(status="SOLVER_ERROR",
                               native_stderr=native["stderr"][-1200:])
                row.setdefault("total_wall_s",row["native_wall_s"])
                rows.append(row)
                dump(row,log)
            # Avoid duplicating original CNFs in the job artifact if enormous.
            # The exact database file IDs and both byte hashes stay in the manifest.
            if cnf.stat().st_size > 30_000_000:cnf.unlink()
            if archive.stat().st_size > 30_000_000:archive.unlink()
    report=dict(source="SAT2026 official submission catalog and GBD original CNF downloads",
      selected_sources=len(frozen),downloads_ok=len(set(r.get("file_id") for r in rows if r.get("source_sha256"))),
      trials=len([r for r in rows if "rep" in r]),unsat_verified=sum(r["verified"] for r in rows),
      catalog_not_certification=True,rows=rows)
    (a.out/"summary.json").write_text(json.dumps(report,indent=2)+"\n")
    print("PCMAX2026_ORIGINAL_SUMMARY "+json.dumps({k:report[k] for k in
          ("selected_sources","downloads_ok","trials","unsat_verified")}),flush=True)
    bad=[r for r in rows if r["status"] in
      ("INVALID_MISSING_CERTIFICATE","CERTIFICATE_REJECTED",
       "INVALID_UNKNOWN_CERTIFICATE_EXISTS","CRITICAL_UNSAT_VS_SAT_CATALOG","SOLVER_ERROR")]
    if bad:
        print("AUDIT_ERRORS "+json.dumps([r["status"] for r in bad]),flush=True)
        raise SystemExit(1)

if __name__=="__main__":
    main()
