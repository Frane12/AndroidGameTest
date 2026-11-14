#!/usr/bin/env python3
"""Frozen original SAT2026 ten-case follow-up: clause Hall detection diagnostics.

Only ORIGINAL CNFs downloaded by immutable GBD file ID; independent checker
required for all UNSAT verdicts. SAT/UNKNOWN never relabeled as UNSAT from catalog.
One pinned logical CPU, bounded guard, explicit UNKNOWNs, complete raw logs.
"""
import argparse
import collections
import hashlib
import json
import os
import statistics
import sys
from pathlib import Path

from benchmark_official2026_clause1 import (
    REPO, CASES, CATALOG_URL, MAX_ARCHIVE, MAX_CNF,
    retrieve, unpack, header, timed
)

SUCCESS_IDS = {"12ac1c71ff0405cc150c2a2db6c4a255",
               "13eb6e05dd8decd305dae2fc148b0ede"}
SELECTED = [x for x in CASES if x[0] not in SUCCESS_IDS]
assert len(SELECTED) == 10

def inspect_cnf(path):
    widths=collections.Counter()
    positive=collections.Counter()
    negative=collections.Counter()
    groups=collections.defaultdict(list)
    binary_conflicts=set()
    lines_read=0
    pending=[]
    n_clause=0
    def register(c):
        nonlocal n_clause
        n_clause+=1
        width=len(c)
        widths[width]+=1
        if width==2 and c[0] != -c[1]:
            a,b=-c[0],-c[1]
            if a>b:a,b=b,a
            binary_conflicts.add((a,b))
        if width>=2:
            if all(l>0 for l in c):
                positive[width]+=1
                if width<=128 and len(groups[width])<5000 and len(set(c))==width:
                    groups[width].append(tuple(c))
            if all(l<0 for l in c):negative[width]+=1
    with path.open("r",encoding="ascii") as f:
        for line in f:
            lines_read+=1
            line=line.strip()
            if not line or line.startswith("c") or line.startswith("p"):continue
            for t in line.split():
                v=int(t)
                if v:pending.append(v)
                else:
                    register(pending)
                    pending=[]
    assert not pending
    features=[]
    for w,original in sorted(groups.items(), key=lambda x: (-len(x[1]),x[0]))[:20]:
        used=set()
        disjoint=[]
        for c in original:
            if used.isdisjoint(c):
                used.update(c);disjoint.append(c)
        match=0
        tests=0
        if len(disjoint)>1 and w<=128:
            anchor=disjoint[0]
            for g in disjoint[1:11]:
                for a,b in zip(anchor,g):
                    if a>b:a,b=b,a
                    tests+=1
                    if (a,b) in binary_conflicts:match+=1
        features.append({"width":w,"sample_groups":len(original),
                         "disjoint_greedy":len(disjoint),
                         "hall_deficit_possible_by_count":len(disjoint)>w,
                         "same_column_blocked_edges_sample":match,
                         "same_column_tests":tests})
    return {
        "clauses_counted":n_clause,"lines":lines_read,
        "distinct_mutex_edges":len(binary_conflicts),
        "top_widths":widths.most_common(18),
        "positive_alo_widths":positive.most_common(15),
        "negative_only_widths":negative.most_common(10),
        "possible_groups":features,
        "over_128_positive":sum(n for w,n in positive.items() if w>128),
        "over_96_positive":sum(n for w,n in positive.items() if w>96),
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--binary",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--budget-ms",type=int,default=1000)
    ap.add_argument("--repetitions",type=int,default=2)
    ap.add_argument("--kissat",type=Path)
    ap.add_argument("--kissat-cap-s",type=float,default=8.0)
    a=ap.parse_args()
    assert a.binary.exists() and a.repetitions in (1,2,3) and 0<a.budget_ms<=5000
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    a.out.mkdir(parents=True,exist_ok=False)
    (a.out/"inputs").mkdir()
    (a.out/"certificates").mkdir()
    catalog_file=a.out/"benchmarks2026.csv"
    retrieve(CATALOG_URL,catalog_file,3_000_000)
    catalog={}
    for line in catalog_file.read_text().splitlines():
        fields=line.split()
        if len(fields)==6:
            h,author,family,label,*rest=fields
            catalog[h]=(author,family,label)
    report={
      "origin":"SAT Competition 2026 original GBD unmodified CNFs",
      "selection":"10 original source IDs: exclude prior 2 Hall1 verified",
      "catalog_sha256":hashlib.sha256(catalog_file.read_bytes()).hexdigest(),
      "case_ids":[x[0] for x in SELECTED],
      "cpu":cpu,"guard_budget_ms":a.budget_ms,"repetitions":a.repetitions,
      "binary_sha256":hashlib.sha256(a.binary.read_bytes()).hexdigest(),
      "checker_sha256":hashlib.sha256(
          (REPO/"research/pcmax_capacity/check_clause_hall.py").read_bytes()).hexdigest(),
      "kissat_path":str(a.kissat) if a.kissat else None,
      "rows":[]}
    checker=REPO/"research/pcmax_capacity/check_clause_hall.py"
    for idx,(md5,author,family,label) in enumerate(SELECTED):
        assert catalog[md5]==(author,family,label),(md5,catalog.get(md5))
        cnf=a.out/"inputs"/f"{idx:02d}-{md5}.cnf"
        compressed=cnf.with_suffix(".cnf.xz")
        meta={"file_id":md5,"author":author,"family":family,"catalog_label":label}
        try:
            downloaded,archive_bytes=retrieve(
                f"https://benchmark-database.de/file/{md5}?context=cnf",
                compressed, MAX_ARCHIVE)
            unpacked=unpack(compressed,cnf)
            nvars,nclauses=header(cnf)
            meta.update(source_sha256=hashlib.sha256(cnf.read_bytes()).hexdigest(),
                        compressed_sha256=hashlib.sha256(compressed.read_bytes()).hexdigest(),
                        archive_bytes=archive_bytes,cnf_bytes=unpacked,
                        variables=nvars,clauses=nclauses,download_s=downloaded)
            metrics=inspect_cnf(cnf)
            assert metrics["clauses_counted"]==nclauses, "parsed clause count mismatch"
            (a.out/f"features-{idx:02d}.json").write_text(json.dumps(metrics,indent=2)+"\n")
            print("PCMAX10_FEATURE "+json.dumps({**meta,"features":metrics},sort_keys=True),flush=True)
        except Exception as exc:
            meta.update(status="SOURCE_ERROR",error=repr(exc))
            report["rows"].append(meta)
            print("PCMAX10_INPUT_ERROR "+json.dumps(meta,sort_keys=True),flush=True)
            continue
        for rep in range(a.repetitions):
            cert=a.out/"certificates"/f"{idx:02d}-r{rep}.json"
            cmd=[str(a.binary.resolve()),str(cnf.resolve()),"--mode","core",
                 "--time",str(a.budget_ms/1000+5),"--pcmax-clause-guard","--pcmax-only",
                 "--pcmax-budget-ms",str(a.budget_ms),"--pcmax-certificate",str(cert.resolve())]
            native=timed(cmd,a.budget_ms/1000+15)
            lines=[s for s in native["stdout"].splitlines() if s.startswith("c PCMAX_CAPACITY ")]
            telemetry=json.loads(lines[-1][len("c PCMAX_CAPACITY "):]) if lines else {}
            row={**meta,"rep":rep,"arm":"CLAUSE_HALL","native_s":native["wall_s"],
                 "rc":native["returncode"],"guard_reason":telemetry.get("reason"),
                 "guard_groups":telemetry.get("groups"),"guard_machines":telemetry.get("machines"),
                 "status":"UNKNOWN","verified":False}
            if native["returncode"]==20 and "s UNSATISFIABLE" in native["stdout"]:
                if not cert.exists():
                    row["status"]="CERTIFICATE_MISSING"
                else:
                    validation=timed([sys.executable,str(checker.resolve()),
                                      str(cnf.resolve()),str(cert.resolve())],120)
                    row["checker_s"]=validation["wall_s"]
                    if validation["returncode"]==0:
                        proof=json.loads(validation["stdout"])
                        if proof.get("status")=="UNSAT_CLAUSE_HALL_CERTIFICATE_VERIFIED":
                            row["status"]="UNSAT_VERIFIED"
                            row["verified"]=True
                            row["demand"]=proof["required_groups"]
                            row["capacity"]=proof["resource_bound"]
                            if label=="sat":row["status"]="CRITICAL_SAT_CONTROL_CONTRADICTION"
                        else:row["status"]="CERTIFICATE_REJECTED"
                    else:
                        row["status"]="CERTIFICATE_REJECTED"
                        row["checker_error"]=validation["stderr"][-500:]
            elif native["returncode"]==0 and "s UNKNOWN" in native["stdout"]:
                if cert.exists():row["status"]="INVALID_UNKNOWN_HAS_CERT"
            else:row["status"]="SOLVER_ERROR"
            row["total_s"]=round(row["native_s"]+row.get("checker_s",0),6)
            report["rows"].append(row)
            print("PCMAX10_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
            if a.kissat and a.kissat.exists():
                k=timed([str(a.kissat.resolve()),str(cnf.resolve())],a.kissat_cap_s)
                kr={**meta,"rep":rep,"arm":"KISSAT","elapsed_s":k["wall_s"],
                    "status":"TIMEOUT" if k["timeout"] else (
                        "UNSAT_UNVERIFIED" if k["returncode"]==20 else
                        "SAT_UNVERIFIED" if k["returncode"]==10 else "UNKNOWN"),
                    "verified":False}
                report["rows"].append(kr)
                print("PCMAX10_TRIAL "+json.dumps(kr,sort_keys=True),flush=True)
        # Retain compressed originals only while <=30MB each; all hashes always retained.
        if cnf.stat().st_size>30_000_000:cnf.unlink()
        if compressed.stat().st_size>30_000_000:compressed.unlink()
    by_arm=collections.defaultdict(list)
    for r in report["rows"]:
        if "rep" in r:by_arm[r["arm"]].append(r)
    report["totals"]={a:{"trials":len(rs),
        "verified_unsat":sum(x.get("verified",False) for x in rs),
        "timeout":sum(x.get("status")=="TIMEOUT" for x in rs),
        "unknown":sum(x.get("status")=="UNKNOWN" for x in rs)}
        for a,rs in by_arm.items()}
    report["error_statuses"]=[x for x in report["rows"]
       if x.get("status") in ("SOURCE_ERROR","CERTIFICATE_MISSING","CERTIFICATE_REJECTED",
          "INVALID_UNKNOWN_HAS_CERT","CRITICAL_SAT_CONTROL_CONTRADICTION","SOLVER_ERROR")]
    (a.out/"summary.json").write_text(json.dumps(report,indent=2)+"\n")
    print("PCMAX10_SUMMARY "+json.dumps(report["totals"],sort_keys=True),flush=True)
    if report["error_statuses"]:raise SystemExit("benchmark errors: see summary")

if __name__=="__main__":
    main()
