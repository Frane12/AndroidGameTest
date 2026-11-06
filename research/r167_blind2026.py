#!/usr/bin/env python3
"""DRNAS R167 official SAT Competition 2026 main-track BLIND development holdout.

The native C++ solver binary was compiled and tested BEFORE the official GBD
IDs were preregistered. Eight non-adaptive official 2026 source instances.
Failures to acquire valid CNFs are INFRA, never counted as algorithm timeouts.
No post-outcome replacement. Two repetitions, same SHA-locked C++ binary,
single pinned CPU per shard, order balanced deterministically per instance.
Outputs include exact SHA-256, SAT witness check and independent XOR proof replay.
Research comparison only, not official competition or unseen-to-world claims.
"""
import argparse
import bz2
import gzip
import hashlib
import io
import json
import lzma
import os
import pathlib
import random
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile

sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r166_independent_verifier as independent
ROOT=pathlib.Path("r167")
M=ROOT/"blind-manifest.json"
MODES=("auto","clean")
SHARDS=4
MAX_RAW=90_000_000
MAX_CNF=175_000_000

def check(cond,explanation):
    if not cond:raise AssertionError("R167_BLIND_AUDIT_FAIL "+str(explanation))
def read(p):return json.loads(pathlib.Path(p).read_text())
def save(p,obj):
    pathlib.Path(p).write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")
def sha(p):
    h=hashlib.sha256()
    with pathlib.Path(p).open("rb") as f:
        for block in iter(lambda:f.read(1<<20),b""):h.update(block)
    return h.hexdigest()
def get_cases():
    m=read(M);samples=m["selection"]
    check(m["protocol"]=="DRNAS-R167-2026-MAIN-BLIND-FROZEN-8-v1","protocol mismatch")
    check(len(samples)==8 and len({x["gbd_md5"] for x in samples})==8,"bad source set")
    check(m["native_build_run"]==42149826500,"native binary not pinned")
    check(m["repetitions"]==2 and m["cap_per_solver_s"]==20,"benchmark conditions changed")
    check(all(len(x["gbd_md5"])==32 and all(c in "0123456789abcdef" for c in x["gbd_md5"]) for x in samples),
          "bad GBD source identifier")
    return m,samples
def transfer(uri,target,limit=MAX_RAW,seconds=70):
    request=urllib.request.Request(uri,headers={"User-Agent":"DRNAS-R167-research/1.0","Accept":"*/*"})
    total=0
    with urllib.request.urlopen(request,timeout=seconds) as response, target.open("wb") as outfile:
        while True:
            chunk=response.read(1<<18)
            if not chunk:break
            total+=len(chunk)
            if total>limit:raise RuntimeError("GBD payload exceeds preregistered size limit")
            outfile.write(chunk)
    check(total>20,"empty or tiny download")
    return total
def decompress(raw,dest):
    header=raw.open("rb").read(8)
    if header.startswith(b"\x1f\x8b"): opener=lambda: gzip.open(raw,"rb")
    elif header.startswith(b"\xfd7zXZ\x00"):opener=lambda: lzma.open(raw,"rb")
    elif header.startswith(b"BZh"):opener=lambda: bz2.open(raw,"rb")
    elif header.startswith(b"\x28\xb5\x2f\xfd"):
        with dest.open("wb") as out:
            proc=subprocess.Popen(["zstd","-dc",str(raw)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            count=0
            try:
                while True:
                    chunk=proc.stdout.read(1<<18)
                    if not chunk:break
                    count+=len(chunk)
                    if count>MAX_CNF:raise RuntimeError("zstd decompressed source too large")
                    out.write(chunk)
            finally:
                if proc.poll() is None:proc.kill()
                proc.communicate()
            check(proc.returncode==0,"zstd decode failed")
        return count
    elif header.startswith(b"PK\x03\x04"):
        with zipfile.ZipFile(raw) as z:
            files=[i for i in z.infolist() if not i.is_dir() and i.filename.endswith(".cnf")]
            check(len(files)==1,"zip does not contain exactly one CNF")
            check(files[0].file_size<=MAX_CNF,"zip source exceeds limit")
            with z.open(files[0]) as src,dest.open("wb") as out:
                count=0
                for chunk in iter(lambda:src.read(1<<18),b""):
                    count+=len(chunk)
                    if count>MAX_CNF:raise RuntimeError("zip decompressed source too large")
                    out.write(chunk)
        return count
    else:opener=lambda:raw.open("rb")
    count=0
    with opener() as src,dest.open("wb") as out:
        while True:
            chunk=src.read(1<<18)
            if not chunk:break
            count+=len(chunk)
            if count>MAX_CNF:raise RuntimeError("decompressed source too large")
            out.write(chunk)
    return count
def acquire(case,idx):
    md5=case["gbd_md5"]
    target=ROOT/(f"source-{idx}.cnf")
    raw=ROOT/(f"raw-{idx}.bin")
    errors=[]
    for scheme in ("https","http"):
        raw.unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        uri=f"{scheme}://benchmark-database.de/file/{md5}"
        try:
            transferred=transfer(uri,raw)
            size=decompress(raw,target)
            check(size>=15,"GBD payload contains no CNF")
            with target.open("rb") as inp:
                pre=inp.read(2048)
            check(b"p cnf " in pre or b"p cnf\t" in pre,
                  "GBD response is not DIMACS CNF; possible HTML/redirect")
            n,clauses=independent.read_dimacs(target)
            check(n>=0 and len(clauses)>=0,"invalid DIMACS")
            return dict(status="SOURCE_OK",index=case["index"],gbd_md5=md5,
                        source_uri=uri,source_sha256=sha(target),
                        compressed_bytes=transferred,cnf_bytes=size,
                        variables=n,clauses=len(clauses)),target
        except Exception as exc:
            errors.append(f"{scheme}:{type(exc).__name__}:{str(exc)[:240]}")
    return dict(status="INFRA_UNAVAILABLE",index=case["index"],
                gbd_md5=md5,errors=errors),None

def parse_output(output,exit_code,source,cap,method):
    lines=output.splitlines()
    record=[json.loads(l[len("R167_RESULT "):]) for l in lines if l.startswith("R167_RESULT ")]
    check(len(record)==1,"missing native structured result")
    item=record[0]
    check(item["status"] in ("SAT","UNSAT","TIMEOUT"),"bad solver status")
    check(exit_code=={"SAT":10,"UNSAT":20,"TIMEOUT":0}[item["status"]],
          "solver return code differs from result")
    check(item["source_sha256"]==sha(source),"C++ source SHA does not match downloaded CNF")
    check(abs(float(item["cap_s"])-cap)<0.0001,"native time cap mismatch")
    check("s "+{"SAT":"SATISFIABLE","UNSAT":"UNSATISFIABLE","TIMEOUT":"UNKNOWN"}[item["status"]] in lines,
          "missing official status line")
    check(item["method"] in ("CDCL_CLEAN","CDCL_FALLBACK","NATIVE_EXACT_GF2",
                            "CDCL_CLEAN_OVER_CAP","CDCL_FALLBACK_OVER_CAP",
                            "NATIVE_EXACT_GF2_OVER_CAP"),
          "unexpected algorithm route")
    if method=="clean":check(item["method"].startswith("CDCL_CLEAN"),"baseline was not clean")
    if item["status"]=="SAT":
        model={}
        for l in lines:
            if not l.startswith("v "):continue
            for lit in l[2:].split():
                v=int(lit)
                if v==0:continue
                check(abs(v) not in model or model[abs(v)]==(v>0),
                      "conflicting SAT model literals")
                model[abs(v)]=v>0
        n,clauses=independent.read_dimacs(source)
        check(len(model)>=n,"incomplete model")
        for clause in clauses:
            check(any(model.get(abs(v))==(v>0) for v in clause),
                  "independent SAT model violates source clause")
    return item

def trial(case,source,mode,repeat,native,cap):
    proof=ROOT/f"proof-{case['gbd_md5']}-{repeat}.json"
    if mode=="auto":proof.unlink(missing_ok=True)
    cmd=[str(native.resolve()),str(source.resolve()),"--cap",str(cap)]
    if mode=="clean":cmd.append("--force-clean")
    else:cmd.extend(["--proof",str(proof.resolve())])
    t=time.perf_counter()
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=cap+20)
    wall=time.perf_counter()-t
    check(p.returncode in (0,10,20),"native died "+p.stderr.decode(errors="replace")[-1200:])
    item=parse_output(p.stdout.decode(errors="replace"),p.returncode,source,cap,mode)
    if wall>cap and item["status"]!="TIMEOUT":raise RuntimeError("native crossed cap without TIMEOUT result")
    verified=False
    if mode=="auto" and item["method"]=="NATIVE_EXACT_GF2":
        check(proof.is_file(),"native exact branch missing proof file")
        data=read(proof)
        proof_status=independent.verify(source,data)["status"]
        check(proof_status==item["status"],"independent GF2 proof result mismatch")
        verified=True
    elif mode=="auto":
        check(not proof.exists(),"CDCL fallback unexpectedly produced XOR proof")
    row=dict(source_sha256=sha(source),index=case["index"],gbd_md5=case["gbd_md5"],
             mode=mode,repeat=repeat,status=item["status"],route=item["method"],
             exact=item["exact"],xor_rows=item["xor_rows"],covered=item["covered"],
             native_wall_s=item["wall_s"],host_wall_s=round(wall,6),
             cap_s=cap,par2_s=round(2*cap if item["status"]=="TIMEOUT" else wall,6),
             SAT_independently_checked=item["status"]=="SAT",
             GF2_proof_independently_replayed=verified,
             UNSAT_independently_verified=verified and item["status"]=="UNSAT")
    return row

def shard(idx,native):
    manifest,cases=get_cases()
    check(idx in range(SHARDS),"shard out of range")
    pin=read(ROOT/"build-pin.json")
    check(sha(native)==pin["binary_sha256"],"frozen native binary sha mismatch")
    check(sha(pathlib.Path("research/r167_native_exact_gf2.cpp"))==pin["source_cpp_sha256"],
          "solver code changed after blind selection")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    total=[];errors=[];sources=[]
    for i,case in enumerate(cases):
        if i%SHARDS!=idx:continue
        item,path=acquire(case,i)
        sources.append(item)
        print("R167_SOURCE",json.dumps(item,sort_keys=True),flush=True)
        if path is None:continue
        for repeat in range(2):
            modes=list(MODES)
            random.Random("R167-BLIND-PARITY-"+case["gbd_md5"]+str(repeat)).shuffle(modes)
            for mode in modes:
                try:result=trial(case,path,mode,repeat,native,float(manifest["cap_per_solver_s"]))
                except Exception as exc:
                    failure=dict(index=case["index"],gbd_md5=case["gbd_md5"],mode=mode,
                                 repeat=repeat,error=str(exc)[:750])
                    errors.append(failure)
                    print("R167_INFRA_TRIAL",json.dumps(failure),flush=True)
                    continue
                total.append(result)
                save(ROOT/f"shard-{idx}.json",
                     dict(index=idx,pin=pin,trials=total,acquisition=sources,errors=errors))
                print("R167_BLIND_TRIAL",json.dumps(result,sort_keys=True),flush=True)
    save(ROOT/f"shard-{idx}.json",
         dict(index=idx,pin=pin,trials=total,acquisition=sources,errors=errors))
    print("R167_BLIND_SHARD_PASS",idx,len(total),len(errors),flush=True)

def audit():
    m,cases=get_cases()
    results=[];sources=[];errors=[];pins=[]
    for i in range(SHARDS):
        d=read(ROOT/f"shard-{i}.json")
        check(d["index"]==i,"shard index drift")
        results+=d["trials"];sources+=d["acquisition"];errors+=d["errors"];pins.append(d["pin"])
    check(len({p["binary_sha256"] for p in pins})==1,"native binary differed between shards")
    check(len({p["source_cpp_sha256"] for p in pins})==1,"C++ code hash differed between shards")
    check(len(sources)==8,"source selection missing a preregistered GBD identifier")
    check({(s["index"],s["gbd_md5"]) for s in sources}==
          {(c["index"],c["gbd_md5"]) for c in cases},"source list drift")
    valid={s["gbd_md5"]:s for s in sources if s["status"]=="SOURCE_OK"}
    keys=set()
    for r in results:
        key=(r["gbd_md5"],r["repeat"],r["mode"])
        check(key not in keys,"duplicate solver result")
        check(r["gbd_md5"] in valid and r["source_sha256"]==valid[r["gbd_md5"]]["source_sha256"],
              "original CNF SHA drift")
        keys.add(key)
    for c in cases:
        if c["gbd_md5"] not in valid:continue
        for repeat in range(2):
            ar=[r for r in results if r["gbd_md5"]==c["gbd_md5"] and r["repeat"]==repeat]
            if len(ar)!=2:continue
            outcomes={r["status"] for r in ar if r["status"]!="TIMEOUT"}
            check(len(outcomes)<=1,"disagreeing SAT/UNSAT outputs on identical source")
    summary={}
    for mode in MODES:
        arr=[r for r in results if r["mode"]==mode]
        summary[mode]={
            "completed_trials":len(arr),"solved":sum(r["status"]!="TIMEOUT" for r in arr),
            "SAT":sum(r["status"]=="SAT" for r in arr),
            "UNSAT":sum(r["status"]=="UNSAT" for r in arr),
            "PAR2_s_on_completed":round(sum(r["par2_s"] for r in arr),5),
            "GF2_fastpath_solved":sum(r["route"]=="NATIVE_EXACT_GF2" and r["status"]!="TIMEOUT" for r in arr),
        }
    pairs=[]
    for c in cases:
        if c["gbd_md5"] not in valid:continue
        for repeat in range(2):
            arr=[r for r in results if r["gbd_md5"]==c["gbd_md5"] and r["repeat"]==repeat]
            d={r["mode"]:r for r in arr}
            if set(d)!=set(MODES):continue
            a,b=d["auto"],d["clean"]
            both=a["status"]!="TIMEOUT" and b["status"]!="TIMEOUT"
            pairs.append({
                "index":c["index"],"gbd_md5":c["gbd_md5"],"repeat":repeat,
                "auto_status":a["status"],"clean_status":b["status"],
                "auto_wall_s":a["host_wall_s"],"clean_wall_s":b["host_wall_s"],
                "auto_route":a["route"],"auto_par2_s":a["par2_s"],"clean_par2_s":b["par2_s"],
                "measured_speedup":round(b["host_wall_s"]/a["host_wall_s"],4) if both and a["host_wall_s"]>0 else None,
                "timeout_lower_bound":round(20/a["host_wall_s"],4) if b["status"]=="TIMEOUT" and a["status"]!="TIMEOUT" else None
            })
    same_pair_par2={
        mode:round(sum(p[mode+"_par2_s"] for p in pairs),6) for mode in MODES
    }
    state="BLIND_AUDIT_PASS" if len(valid)==8 and len(pairs)==16 and not errors else (
          "BLIND_PARTIAL_INFRA" if pairs else "BLIND_NO_VALID_PAIRED_RESULTS")
    report=dict(status=state,official_source="SAT Competition 2026 main track GBD",
                official_index_blob_sha1=m["official_uri_git_blob_sha1"],
                selection=m["selection"],frozen_source_cpp_sha256=pins[0]["source_cpp_sha256"],
                native_binary_sha256=pins[0]["binary_sha256"],
                preregistered_instances=8,downloaded_valid_instances=len(valid),
                attempted_trials=len(results),valid_pairs=len(pairs),caps=20,
                sources=sources,errors=errors,summary=summary,
                comparable_paired_par2_s=same_pair_par2,pairs=pairs,
                blind_to_code=True,not_official_competition=True,
                limitations=["Official 2026 main GBD selected post native code freeze",
                "No resampling or filtering by SAT status/speed",
                "Failed downloads are infrastructure, not solver timeout",
                "This is an independent holdout for R167, not globally unseen formulas",
                "GF2 UNSAT parity certificate replay is not competition LRAT/FRAT",
                "Two repeats, 20s cap; not equivalent to official competition scoring"])
    save(ROOT/"blind-report.json",report)
    txt=["# DRNAS R167 native C++ blind SAT Competition 2026","",
         "Pre-registered 8 GBD ids, 2 paired repetitions, 20 seconds per solver.",
         f"Status: {state}; valid inputs {len(valid)}/8; comparable pairs {len(pairs)}/16.",
         "","| Mode | Completed | Solved | SAT | UNSAT | GF2 fast path | PAR2 on completed |",
         "|---|---:|---:|---:|---:|---:|---:|"]
    for mode in MODES:
        d=summary[mode]
        txt.append(f'| {mode} | {d["completed_trials"]} | {d["solved"]} | {d["SAT"]} | {d["UNSAT"]} | {d["GF2_fastpath_solved"]} | {d["PAR2_s_on_completed"]} |')
    txt.extend(["",f"Matched pairs PAR2 auto={same_pair_par2['auto']}, clean={same_pair_par2['clean']}.",
                "This is NOT an official SAT Competition result.",
                "","## Per instance"])
    for p in pairs:
        txt.append(f"- {p['gbd_md5'][:12]} run {p['repeat']}: auto {p['auto_status']} ({p['auto_route']}, {p['auto_wall_s']}s), clean {p['clean_status']} ({p['clean_wall_s']}s)")
    if errors:
        txt.extend(["","## Infrastructure errors"])
        txt.extend("- "+str(x)[:240] for x in errors)
    (ROOT/"blind-summary.md").write_text("\n".join(txt)+"\n")
    print("R167_BLIND_FINAL",json.dumps({k:report[k] for k in
          ("status","preregistered_instances","downloaded_valid_instances","valid_pairs",
           "summary","comparable_paired_par2_s")},sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("shard","audit"))
    p.add_argument("--shard",type=int,default=0)
    p.add_argument("--native",default="r167/native")
    args=p.parse_args()
    if args.action=="shard":shard(args.shard,pathlib.Path(args.native))
    else:audit()
