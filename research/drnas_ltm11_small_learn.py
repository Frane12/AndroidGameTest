#!/usr/bin/env python3
"""LTM11 SMALL LEARN: learn reference-vs-native routing on original official SAT2024 CNFs.

20 TRAIN + 10 VALIDATION + 10 HELD-OUT source-disjoint instances.
IMPORTANT: The SAT2024 holdout has appeared in prior LTM10 logs. This is
EXPLORATORY reused-holdout evaluation, NOT a new statistically blind test.
Single logical CPU; one solver process at a time. The router is learned only
from verified SAT witnesses and independently checked LTM9 PHP math proofs.
LTM11 is a learned strategy selector across reference and native CDCL engines,
NOT a neural net and NOT learned clauses or altered proof rules.
"""
import collections
import gzip
import hashlib
import json
import lzma
import bz2
import math
import os
import pathlib
import random
import re
import resource
import shutil
import subprocess
import time

import drnas_ltm11_policy as P
from drnas_ltm9_independent_cert import (CertificateError,certificate_from_stdout,
                                         parse_dimacs,verify_php_certificate)

ARCHIVE="https://zenodo.org/records/15095752/files/sat-competition-2024-main-benchmarks.zip?download=1"
ROOT=pathlib.Path("ltm11_small_learn")
TRAIN_COUNT=20
VALID_COUNT=10
TEST_COUNT=10
SAMPLE_COUNT=40
SCREEN_CAP=2.5
TEST_CAP=6.0
TRAIN_SEED=17
TEST_SEEDS=(17,29)
SCREEN_ARMS=P.CANDIDATE_ARMS
TEST_ARMS=("LTM11","LTM9_FAST","LTM8_FAST","Kissat","CaDiCaL","CryptoMiniSat")
OLD_OFFICIAL={
 "GracefulGraph-K05-P02_c18.cnf.xz",
 "FmlaImplyChain_3_7_7.sanitized.cnf.xz",
 "1-ET-256-K-55.sanitized.cnf.xz",
 "circuit_48in64out_with_800gates_4in4out_dist128_seed1.sanitized.cnf.xz",
 "6s130-opt.cnf.xz","md5_48_1.cnf.xz",
 "hwmcc20miters-iso-mul2.sanitized.cnf.xz",
 "qwh.50.1250.shuffled-as.sat03-1655.cnf.xz",
}
MAX_RAW=24000000

def compact(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"))

def emit(name,obj):
    print(name+" "+compact(obj),flush=True)

def family_key(name):
    name=pathlib.PurePosixPath(name).name.lower()
    name=re.sub(r"\.cnf(?:\.(?:xz|bz2|gz))?$","",name)
    name=name.replace(".sanitized","")
    name=re.sub(r"\d+","#",name)
    name=re.sub(r"[_\-\.]+","-",name).strip("-")
    return name

def choose_archive_entries(all_entries):
    # Deterministic fallback if strict small-source size range lacks enough
    # distinct filename families. Never duplicate families across splits.
    # Selection depends on archive metadata only, never solver outcomes.
    tiers=((4000,50000),(1000,80000),(1000,200000),(1000,900000))
    for lo,hi in tiers:
        eligible=sorted(
           (item for item in all_entries
            if not item.is_dir()
            and item.filename.lower().endswith((".cnf",".cnf.xz",".cnf.gz",".cnf.bz2"))
            and lo<=item.file_size<=hi
            and pathlib.PurePosixPath(item.filename).name not in OLD_OFFICIAL),
           key=lambda e:(e.file_size,e.filename))
        by_family={}
        for e in eligible:
            key=family_key(e.filename)
            if key not in by_family:
                by_family[key]=e
        pool=sorted(by_family.values(),key=lambda e:(e.file_size,e.filename))
        if len(pool)<SAMPLE_COUNT:
            emit("LTM11_SELECTION_TIER_INSUFFICIENT",
                 dict(min_bytes=lo,max_bytes=hi,distinct_families=len(pool),
                      required=SAMPLE_COUNT))
            continue
        positions=[min(len(pool)-1,((2*i+1)*len(pool))//(2*SAMPLE_COUNT))
                   for i in range(SAMPLE_COUNT)]
        if len(set(positions))!=SAMPLE_COUNT:
            raise RuntimeError("nonunique source positions")
        selected=[pool[i] for i in positions]
        random.Random(1010).shuffle(selected)
        assert len({family_key(x.filename) for x in selected})==SAMPLE_COUNT
        emit("LTM11_SELECTION_TIER",
             dict(min_bytes=lo,max_bytes=hi,distinct_families=len(pool),
                  selected=SAMPLE_COUNT))
        return selected,len(eligible),len(pool)
    raise RuntimeError("Insufficient distinct official CNF families even after size-tier expansion")

def decode(entry,data):
    name=entry.filename.lower()
    if name.endswith(".xz"):
        dec=lzma.LZMADecompressor()
        result=dec.decompress(data,max_length=MAX_RAW+1)
        if not dec.eof:raise RuntimeError("xz source exceeds limit")
    elif name.endswith(".gz"):result=gzip.decompress(data)
    elif name.endswith(".bz2"):result=bz2.decompress(data)
    else:result=data
    if len(result)>MAX_RAW:raise RuntimeError("CNF uncompressed size limit")
    if not re.search(rb"(?m)^p cnf \d+ \d+\s*$",result):
        raise RuntimeError("no DIMACS header")
    return result

def collect():
    from remotezip import RemoteZip  # installed only in benchmark virtualenv
    (ROOT/"cases").mkdir(parents=True)
    with RemoteZip(ARCHIVE,timeout=90) as z:
        selected,eligible,families=choose_archive_entries(z.infolist())
        emit("LTM11_SELECTION",dict(eligible=eligible,distinct_name_families=families,
              selected=SAMPLE_COUNT,archive=ARCHIVE))
        sources=[]
        for i,item in enumerate(selected):
            raw=decode(item,z.read(item))
            sha=hashlib.sha256(raw).hexdigest()
            split=("train" if i<TRAIN_COUNT else
                   "validation" if i<TRAIN_COUNT+VALID_COUNT else "holdout")
            path=ROOT/"cases"/f"{i:03d}_{sha[:16]}.cnf"
            path.write_bytes(raw)
            obj=dict(id=i,source_file=item.filename,
                     normalized_name_family=family_key(item.filename),
                     split=split,sha256=sha,path=str(path),
                     bytes=len(raw),compressed_bytes=item.file_size)
            sources.append(obj)
            emit("LTM11_SOURCE",obj)
    if len({x["sha256"] for x in sources})!=SAMPLE_COUNT:
        raise RuntimeError("duplicate official source bytes")
    if len({x["normalized_name_family"] for x in sources})!=SAMPLE_COUNT:
        raise RuntimeError("name-family leakage across splits")
    manifest=dict(archive=ARCHIVE,collection="SAT Competition 2024 Main",
                  source_count=40,train=20,validation=10,holdout=10,
                  independently_untested_2024_names_excluded=len(OLD_OFFICIAL),
                  source_selection="smallest successful deterministic compressed-size tier over disjoint normalized name families",
                  selection_did_not_use_results=True,
                  family_disjoint_by_filename_heuristic=True,
                  global_novelty_not_guaranteed=True,
                  dataset_training_frozen_before_holdout=True,
                   exploratory_reused_prior_2024_holdout=True,
                   policy_changed_after_prior_holdout_inspection=True,
                   blind_generalization_claim=False,
                  source_sha256_enforced=True,
                  no_original_cnf_transformation=True,
                  train_cap_s=SCREEN_CAP,holdout_cap_s=TEST_CAP,
                  holdout_repetitions=2,
                  train_cpus=1,proof_type="independent PHP counting, not LRAT",
                  sources=sources)
    (ROOT/"manifest.json").write_text(json.dumps(manifest,indent=2))
    return sources

def command(arm,path,seed,cap):
    if arm in P.NATIVE_ARMS:
        exe=("mre_atlas23/bin/drnas_ltm9_certificate"
             if arm=="LTM9_FAST" else "mre_atlas23/bin/drnas_ltm8_base")
        mode=("LTM8_CHAOS" if arm=="LTM8_CHAOS" else "LTM8_FAST")
        return [exe,str(path),"--mode",mode,"--time",str(max(.1,cap)),
                "--seed",str(seed),"--policy","1.0,0.85"]
    if arm=="Kissat":return ["kissat","-q",f"--seed={seed}",str(path)]
    if arm=="CaDiCaL":return ["cadical","-q",f"--seed={seed}",str(path)]
    if arm=="CryptoMiniSat":return ["cryptominisat5","--threads=1","--verb=0",str(path)]
    raise ValueError(arm)

def sat_witness_valid(path,n,output):
    # Independent validation on original CNF, streaming rather than caching
    # all clauses. Missing/unassigned variables may not satisfy a clause.
    model={}
    for line in output.splitlines():
        if not line.startswith(("v ","v\t")):continue
        for tok in line[1:].split():
            try:v=int(tok)
            except ValueError:return False
            if v==0:continue
            if abs(v)>n or (abs(v) in model and model[abs(v)]!=(v>0)):
                return False
            model[abs(v)]=(v>0)
    if not model:return False
    header=None;count=0;clause_satisfied=False;pending=False
    with open(path,encoding="ascii",errors="replace") as f:
        for line in f:
            line=line.strip()
            if not line or line.startswith(("c","%")):continue
            if line.startswith("p "):
                parts=line.split()
                if len(parts)!=4 or parts[1]!="cnf" or header is not None:
                    return False
                header=(int(parts[2]),int(parts[3]))
                if header[0]!=n:return False
                continue
            if header is None:return False
            for tok in line.split():
                try:lit=int(tok)
                except ValueError:return False
                if lit:
                    pending=True
                    if model.get(abs(lit))==(lit>0):
                        clause_satisfied=True
                else:
                    if not pending or not clause_satisfied:return False
                    count+=1;pending=False;clause_satisfied=False
    return header is not None and count==header[1] and not pending

def nvars(path):
    with open(path,"rb") as f:
        for line in f:
            if line.startswith(b"p cnf "):
                return int(line.split()[2])
    raise ValueError("missing p cnf")

def run_solver(arm,source,seed,cap):
    original=pathlib.Path(source["path"])
    if hashlib.sha256(original.read_bytes()).hexdigest()!=source["sha256"]:
        raise RuntimeError("original CNF SHA changed")
    env=dict(os.environ,DRNAS_LTM8_MEMORY="",OMP_NUM_THREADS="1",
             OPENBLAS_NUM_THREADS="1")
    t=time.monotonic()
    try:
        p=subprocess.run(command(arm,original,seed,cap),capture_output=True,
                         text=True,timeout=cap,env=env,
                         preexec_fn=lambda:resource.setrlimit(
                             resource.RLIMIT_AS,(3*1024**3,3*1024**3)))
        rc=p.returncode;stdout=p.stdout;stderr=p.stderr
    except subprocess.TimeoutExpired:
        rc=124;stdout="";stderr="timeout"
    elapsed=time.monotonic()-t
    cert=None
    try:
        parsed=certificate_from_stdout(stdout)
        if parsed is not None:
            if arm!="LTM9_FAST" or rc!=20:
                raise CertificateError("certificate outside LTM9 UNSAT")
            cert=verify_php_certificate(parse_dimacs(original),parsed)
    except CertificateError as exc:
        raise RuntimeError(f"invalid original-CNF certificate {source['id']}: {exc}") from exc
    if rc==10:
        status="SAT_VERIFIED" if sat_witness_valid(original,nvars(original),stdout) else "INVALID_SAT"
    elif rc==20:
        status="UNSAT_MATH_CERTIFIED" if cert else "UNSAT_UNVERIFIED"
    elif rc in (0,124):
        status="UNKNOWN"
    else:
        status="ERROR"
    if status in ("ERROR","INVALID_SAT"):
        raise RuntimeError(f"solver {arm} invalid on source {source['id']}: {rc} {stderr[-400:]} {stdout[-400:]}")
    out=dict(arm=arm,id=source["id"],split=source["split"],seed=seed,
             status=status,e2e_s=round(elapsed,6),
             verified=(status in ("SAT_VERIFIED","UNSAT_MATH_CERTIFIED")),
             php_math_certified=(cert is not None),
             decisions=None,
             conflicts=None)
    # No false accuracy claims from timed out trials.
    for line in stdout.splitlines():
        if line.startswith("ATLAS13_TRIAL "):
            parts=dict(v.split("=",1) for v in line.split()[1:] if "=" in v)
            for field in ("decisions","conflicts"):
                try:out[field]=int(parts[field])
                except (KeyError,ValueError):pass
    return out

def with_metrics(row,cap):
    valid=row["status"] in ("SAT_VERIFIED","UNSAT_MATH_CERTIFIED")
    solved=valid or row["status"]=="UNSAT_UNVERIFIED"
    return dict(row,PAR2_reported_s=round(row["e2e_s"] if solved else 2*cap,6),
                PAR2_verified_s=round(row["e2e_s"] if valid else 2*cap,6))

def check_contradictions(rows):
    by_source=collections.defaultdict(set)
    for x in rows:
        if x["status"]=="SAT_VERIFIED":by_source[x["id"]].add("SAT")
        if x["status"] in ("UNSAT_MATH_CERTIFIED","UNSAT_UNVERIFIED"):
            by_source[x["id"]].add("UNSAT")
    for src,outcomes in by_source.items():
        if len(outcomes)>1:raise RuntimeError(f"SAT UNSAT disagreement source={src}")

def metrics(rows,cap,arms):
    return {arm:dict(trials=len(rs),
                     reported_solved=sum(x["status"] in ("SAT_VERIFIED","UNSAT_MATH_CERTIFIED","UNSAT_UNVERIFIED") for x in rs),
                     SAT_verified=sum(x["status"]=="SAT_VERIFIED" for x in rs),
                     UNSAT_math_certified=sum(x["status"]=="UNSAT_MATH_CERTIFIED" for x in rs),
                     UNSAT_unverified=sum(x["status"]=="UNSAT_UNVERIFIED" for x in rs),
                     timeout=sum(x["status"]=="UNKNOWN" for x in rs),
                     PAR2_reported_s=round(sum(x["PAR2_reported_s"] for x in rs),6),
                     PAR2_verified_s=round(sum(x["PAR2_verified_s"] for x in rs),6),
                     e2e_s=round(sum(x["e2e_s"] for x in rs),6))
            for arm in arms
            for rs in [[x for x in rows if x["arm"]==arm]]}

def screening(sources):
    rows=[]
    pairs=[]
    with (ROOT/"screen.jsonl").open("w") as fd:
        for source in sources:
            if source["split"]=="holdout":continue
            extraction_start=time.monotonic()
            features=P.extract(source["path"])
            features["feature_extract_s"]=time.monotonic()-extraction_start
            arm_rows={}
            for arm in SCREEN_ARMS:
                result=with_metrics(run_solver(arm,source,TRAIN_SEED,SCREEN_CAP),SCREEN_CAP)
                rows.append(result);arm_rows[arm]=result
                fd.write(compact(result)+"\n");fd.flush()
                emit("LTM11_SCREEN_TRIAL",result)
            pairs.append((source,features,arm_rows))
    check_contradictions(rows)
    train=[(f,r) for source,f,r in pairs if source["split"]=="train"]
    val=[(f,r) for source,f,r in pairs if source["split"]=="validation"]
    assert len(train)==20 and len(val)==10
    model=P.fit(train,val,SCREEN_CAP)
    names_train=[s["sha256"] for s,_,_ in pairs if s["split"]=="train"]
    names_val=[s["sha256"] for s,_,_ in pairs if s["split"]=="validation"]
    memory=P.save(model,ROOT/"ltm11_memory.json",names_train,names_val)
    emit("LTM11_TRAIN_FINAL",dict(train=20,validation=10,
         all_real_original_CNF=True,training_rows=len(rows),
         strict_verified_only=True,reference_arms_in_training=True,
         feature_extraction_cost_in_reward=True,policy=memory,
         reported_PAR2=metrics(rows,SCREEN_CAP,SCREEN_ARMS)))
    return memory

def run_learned(source,seed,memory):
    t=time.monotonic()
    feature=P.extract(source["path"])
    selected=P.pick(memory,feature)
    overhead=time.monotonic()-t
    remaining=TEST_CAP-overhead
    if remaining<.1:
        result=dict(arm=selected,id=source["id"],split="holdout",seed=seed,
                    status="UNKNOWN",e2e_s=TEST_CAP,verified=False,
                    php_math_certified=False,decisions=None,conflicts=None)
    else:
        result=run_solver(selected,source,seed,remaining)
    result["arm"]="LTM11"
    result["chosen_solver"]=selected
    result["feature_extract_s"]=round(overhead,6)
    result["e2e_s"]=round(overhead+result["e2e_s"],6)
    return with_metrics(result,TEST_CAP)

def holdout(sources):
    # Reload policy from disk to test actual persistent memory path.
    memory=P.load(ROOT/"ltm11_memory.json")
    rows=[]
    tested=[]
    with (ROOT/"holdout.jsonl").open("w") as fd:
        for source in sources:
            if source["split"]!="holdout":continue
            for rep,seed in enumerate(TEST_SEEDS):
                arms=list(TEST_ARMS)
                rot=(source["id"]+rep)%len(arms)
                arms=arms[rot:]+arms[:rot]
                for arm in arms:
                    row=(run_learned(source,seed,memory) if arm=="LTM11"
                         else with_metrics(run_solver(arm,source,seed,TEST_CAP),TEST_CAP))
                    row["shard"]=(source["id"]-30)//5
                    rows.append(row)
                    fd.write(compact(row)+"\n");fd.flush()
                    emit("LTM11_HOLDOUT_TRIAL",row)
            tested.append(source["id"])
    assert len(tested)==10 and len(rows)==10*2*len(TEST_ARMS)
    check_contradictions(rows)
    totals=metrics(rows,TEST_CAP,TEST_ARMS)
    shards={str(s):metrics([r for r in rows if r["shard"]==s],TEST_CAP,TEST_ARMS)
            for s in range(2)}
    routing=dict(collection="LTM11",
                 chosen_native=dict(collections.Counter(
                     x["chosen_solver"] for x in rows if x["arm"]=="LTM11")),
                 feature_extraction_s=round(sum(x["feature_extract_s"] for x in rows if x["arm"]=="LTM11"),5))
    report=dict(train_sources=20,validation_sources=10,holdout_sources=10,
                holdout_trials=len(rows),one_logical_cpu=True,
                policy=memory,totals=totals,shards=shards,routing=routing,
                official_cnf=True,full_archive=False,
                source_family_split_heuristic=True,
                strict_verification="SAT original witness or independently checked mathematical PHP only",
                UNSAT_independent_LRAT=False,
                claimed_global_generalization=False,
                 exploratory_reused_prior_2024_holdout=True,
                 policy_updated_after_prior_LTM10_holdout_inspection=True)
    (ROOT/"report.json").write_text(json.dumps(report,indent=2))
    emit("LTM11_REAL_FINAL",report)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a") as f:
            f.write("### LTM11 SMALL LEARN — official SAT2024 exploratory reused-holdout\n\n")
            f.write("20 train / 10 validation / 10 test; 2.5s training, 6s holdout; 2 repeats; one logical CPU. Prior holdout inspected; NOT a new blind result.\n\n")
            f.write("| Solver | Reported solved | SAT witness | PHP math certified | UNSAT unverified | PAR2 reported s | PAR2 verified s |\n")
            f.write("|---|---:|---:|---:|---:|---:|---:|\n")
            for arm,v in totals.items():
                f.write(f"| {arm} | {v['reported_solved']}/{v['trials']} | {v['SAT_verified']} | {v['UNSAT_math_certified']} | {v['UNSAT_unverified']} | {v['PAR2_reported_s']:.3f} | {v['PAR2_verified_s']:.3f} |\n")
            f.write("\nSource family splitting is a name-template heuristic, not guaranteed semantic disjointness. UNSAT without math certificate is not independently verified.\n")
    print("LTM11_REAL_PASS",flush=True)

def main():
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    for exe in ("kissat","cadical","cryptominisat5"):
        if not shutil.which(exe):raise RuntimeError("missing reference solver "+exe)
    if ROOT.exists():raise RuntimeError("fresh run required")
    sources=collect()
    screening(sources)
    holdout(sources)

if __name__=="__main__":main()
