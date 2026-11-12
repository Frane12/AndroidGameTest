#!/usr/bin/env python3
"""LTM9 vs 4 reference arms: official SAT Competition 2024 source CNFs.

Eight size-stratified original CNFs selectively fetched via HTTP ranges from
the official archived 400-instance main track (not the whole 4.3 GB archive).
Selection is deterministic without inspecting SAT labels or tuning solvers.
This is an official-source PILOT, not a blind competition-wide claim.
"""
import bz2
import gzip
import hashlib
import json
import lzma
import os
import pathlib
import resource
import shutil
import subprocess
import time

from remotezip import RemoteZip
from drnas_ltm9_independent_cert import (parse_dimacs,certificate_from_stdout,
                                         verify_php_certificate,CertificateError)
from drnas_ltm9_refs_unseen import witness_ok

ARCHIVE="https://zenodo.org/records/15095752/files/sat-competition-2024-main-benchmarks.zip?download=1"
OUT=pathlib.Path("ltm9_official2024")
ARMS=("LTM9_CERT","LTM8_BASE","Kissat","CaDiCaL","CryptoMiniSat")
SEEDS=(17,29)
CAP=8.0
SOURCE_COUNT=8
MAX_RAW=30000000

def unpack(entry,raw):
    ext=entry.lower()
    if ext.endswith(".cnf.xz"):
        decoder=lzma.LZMADecompressor()
        unpacked=decoder.decompress(raw,max_length=MAX_RAW+1)
        if not decoder.eof:raise RuntimeError("decompressed .xz exceeds safety cap")
    elif ext.endswith(".cnf.gz"):
        unpacked=gzip.decompress(raw)
    elif ext.endswith(".cnf.bz2"):
        unpacked=bz2.decompress(raw)
    elif ext.endswith(".cnf"):
        unpacked=raw
    else:
        raise RuntimeError("unexpected archive entry type")
    if not unpacked or len(unpacked)>MAX_RAW:
        raise RuntimeError("CNF exceeds source size bound")
    return unpacked

def fetch_sources():
    with RemoteZip(ARCHIVE,timeout=90) as z:
        candidates=sorted(
            (i for i in z.infolist()
             if not i.is_dir() and i.filename.lower().endswith(
                 (".cnf",".cnf.xz",".cnf.gz",".cnf.bz2"))
             and 70000<=i.file_size<=2000000),
            key=lambda i:(i.file_size,i.filename))
        if len(candidates)<SOURCE_COUNT+4:
            raise RuntimeError(f"Too few eligible competition CNFs: {len(candidates)}")
        # Non-endpoint quantiles, distinct from the endpoints of older pilots.
        positions=[((len(candidates)-1)*(2*i+1))//(2*SOURCE_COUNT)
                   for i in range(SOURCE_COUNT)]
        if len(set(positions))!=SOURCE_COUNT:raise RuntimeError("duplicate archive selection")
        result=[]
        for n,pos in enumerate(positions):
            entry=candidates[pos]
            raw=unpack(entry.filename,z.read(entry))
            target=OUT/"sources"/f"official_{n:02d}.cnf"
            target.write_bytes(raw)
            # Every source is original, unchanged and validated as DIMACS.
            parsed=parse_dimacs(target)
            sha=hashlib.sha256(raw).hexdigest()
            result.append(dict(id=n,archive_entry=entry.filename,
                               compressed_entry_bytes=entry.file_size,
                               bytes=len(raw),sha256=sha,path=str(target),
                               n=parsed["n"],clauses=len(parsed["clauses"])))
            print("LTM9_OFFICIAL_SOURCE "+json.dumps(result[-1]),flush=True)
        if len({x["sha256"] for x in result})!=SOURCE_COUNT:
            raise RuntimeError("duplicate official source SHA")
    return result

def command(arm,path,seed):
    if arm in ("LTM9_CERT","LTM8_BASE"):
        exe=("mre_atlas23/bin/drnas_ltm9_certificate" if arm=="LTM9_CERT"
             else "mre_atlas23/bin/drnas_ltm8_base")
        return [exe,str(path),"--mode","LTM8_FAST","--time",str(CAP),
                "--seed",str(seed),"--policy","1.0,0.85"]
    if arm=="Kissat":return ["kissat","-q","--seed="+str(seed),str(path)]
    if arm=="CaDiCaL":return ["cadical","-q","--seed="+str(seed),str(path)]
    if arm=="CryptoMiniSat":
        return ["cryptominisat5","--threads=1","--verb=0",str(path)]
    raise ValueError(arm)

def run(arm,src,source,seed):
    # Disable cross-instance training in BOTH native arms.
    env=dict(os.environ,DRNAS_LTM8_MEMORY="",OMP_NUM_THREADS="1",
             OPENBLAS_NUM_THREADS="1")
    started=time.monotonic()
    try:
        p=subprocess.run(command(arm,source["path"],seed),capture_output=True,text=True,
                         timeout=CAP,env=env,preexec_fn=lambda:
                         resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3)))
        rc=p.returncode
        stdout=p.stdout
        stderr=p.stderr
    except subprocess.TimeoutExpired:
        rc=124;stdout="";stderr="timeout"
    e2e=time.monotonic()-started
    cert_checked=None
    try:
        c=certificate_from_stdout(stdout)
        if c is not None:
            if arm!="LTM9_CERT" or rc!=20:
                raise CertificateError("certificate emitted with invalid arm/status")
            cert_checked=verify_php_certificate(src,c)
    except CertificateError as e:
        return dict(arm=arm,source_id=source["id"],sha256=source["sha256"],seed=seed,
                    rc=rc,status="INVALID_CERT",e2e_s=round(e2e,6),error=str(e))
    if rc==10:
        status=("SAT_VERIFIED" if witness_ok(src["n"],src["clauses"],stdout)
                else "INVALID_SAT")
    elif rc==20:
        status=("UNSAT_MATH_CERTIFIED" if cert_checked else "UNSAT_UNVERIFIED")
    elif rc in (0,124):
        status="UNKNOWN"
    else:
        status="ERROR"
    solved=status in ("SAT_VERIFIED","UNSAT_MATH_CERTIFIED","UNSAT_UNVERIFIED")
    verified=status in ("SAT_VERIFIED","UNSAT_MATH_CERTIFIED")
    row=dict(arm=arm,source_id=source["id"],sha256=source["sha256"],seed=seed,
             rc=rc,status=status,e2e_s=round(e2e,6),
             PAR2_reported_s=round(e2e if solved else 2*CAP,6),
             PAR2_math_verified_s=round(e2e if verified else 2*CAP,6),
             php_certificate=cert_checked)
    if status in ("ERROR","INVALID_SAT"):
        row["diagnostics"]=(stdout+"\n"+stderr)[-1200:]
    return row

def summarize(rows):
    result={}
    for arm in ARMS:
        a=[x for x in rows if x["arm"]==arm]
        result[arm]=dict(trials=len(a),
                         reported_solved=sum(x["status"] in (
                             "SAT_VERIFIED","UNSAT_MATH_CERTIFIED","UNSAT_UNVERIFIED") for x in a),
                         SAT_verified=sum(x["status"]=="SAT_VERIFIED" for x in a),
                         UNSAT_math_certified=sum(x["status"]=="UNSAT_MATH_CERTIFIED" for x in a),
                         UNSAT_unverified=sum(x["status"]=="UNSAT_UNVERIFIED" for x in a),
                         errors=sum(x["status"] in ("ERROR","INVALID_SAT","INVALID_CERT") for x in a),
                         PAR2_reported_s=round(sum(x.get("PAR2_reported_s",2*CAP) for x in a),6),
                         PAR2_math_verified_s=round(
                             sum(x.get("PAR2_math_verified_s",2*CAP) for x in a),6),
                         e2e_s=round(sum(x["e2e_s"] for x in a),6))
    return result

def main():
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    if OUT.exists():raise RuntimeError("fresh official output directory required")
    (OUT/"sources").mkdir(parents=True)
    for cmd in ("kissat","cadical","cryptominisat5"):
        if not shutil.which(cmd):raise RuntimeError("missing reference solver: "+cmd)
    source_records=fetch_sources()
    manifest=dict(archive=ARCHIVE,track="SAT Competition 2024 Main",
                  source_count=SOURCE_COUNT,selection="fixed internal quantiles of eligible archive entries (compressed size 70 KB-2 MB); pilot",
                  full_archive_downloaded=False,
                  no_source_transform=True,not_globally_blind=True,
                  one_logical_cpu=True,cpu=cpu,time_cap_s=CAP,
                  repetitions=len(SEEDS),arms=ARMS,
                  cross_formula_policy_memory=False,
                  UNSAT_independent_LRAT=False,
                  math_certificate_checked_against_original=True,
                  sources=source_records)
    (OUT/"manifest.json").write_text(json.dumps(manifest,indent=2))
    rows=[]
    claims={}
    with (OUT/"trials.jsonl").open("w") as fd:
        for record in source_records:
            parsed=parse_dimacs(record["path"])
            for rep,seed in enumerate(SEEDS):
                arms=list(ARMS)
                k=(record["id"]+rep)%len(arms)
                arms=arms[k:]+arms[:k]
                for arm in arms:
                    row=run(arm,parsed,record,seed)
                    row["shard"]=record["id"]//2
                    rows.append(row)
                    fd.write(json.dumps(row)+"\n");fd.flush()
                    print("LTM9_OFFICIAL_TRIAL "+json.dumps(row),flush=True)
                    if row["status"] in ("INVALID_CERT","INVALID_SAT","ERROR"):
                        raise RuntimeError("invalid official result/solver crash")
                    label=("SAT" if row["status"]=="SAT_VERIFIED"
                           else "UNSAT" if row["status"].startswith("UNSAT_") else None)
                    if label:
                        old=claims.setdefault(record["sha256"],label)
                        if old!=label:
                            raise RuntimeError("SAT/UNSAT contradiction on original official CNF")
    total=summarize(rows)
    summary=dict(total=total,
                 shards={str(i):summarize([x for x in rows if x["shard"]==i]) for i in range(4)},
                 source_count=SOURCE_COUNT,trial_count=len(rows),
                 pilot=True,original_cnf=True,independent_LRAT=False,
                 verified_math_certificate=True,
                 note="Official SAT Competition 2024 size-stratified pilot, not global blind holdout")
    (OUT/"summary.json").write_text(json.dumps(summary,indent=2))
    print("LTM9_OFFICIAL_FINAL "+json.dumps(summary),flush=True)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as f:
            f.write("\nOfficial SAT Competition 2024 source pilot (8 original CNFs × 2 × 5 = 80 trials; 8s cap; one CPU).\n\n")
            f.write("| Solver | Reported solved | SAT witness | PHP math proof | UNSAT unverified | PAR2 reported | PAR2 verified |\n|---|---:|---:|---:|---:|---:|---:|\n")
            for arm,v in total.items():
                f.write(f"| {arm} | {v['reported_solved']}/{v['trials']} | {v['SAT_verified']} | {v['UNSAT_math_certified']} | {v['UNSAT_unverified']} | {v['PAR2_reported_s']:.3f} | {v['PAR2_math_verified_s']:.3f} |\n")
            f.write("\nMathematical PHP witness validation is separate from the detector but is not LRAT/DRAT verification.\n")
    print("LTM9_OFFICIAL_PASS",flush=True)

if __name__=="__main__":main()
