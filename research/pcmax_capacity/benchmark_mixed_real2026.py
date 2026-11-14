#!/usr/bin/env python3
"""Certified same-input 5-arm benchmark on 12 original SAT Competition 2026 CNFs.

All five arms share a one-logical-CPU pin and 6-second end-to-end
solve+independent-proof-check cap (configured by CLI). Every source byte is
pinned to prior run 43641628537. Catalog status is not solver certification.
The new proof-first MATH-MIXED and HALL2 opt-in guards run within one CDCL
process, not as parallel solver portfolios. MIXED/HALL2 accepted UNSAT needs
an independently checked source-derived certificate or verified CDCL DRAT.
"""
import argparse
import collections
import hashlib
import json
import math
import os
from pathlib import Path
import random
import resource
import statistics
import subprocess
import sys
import time

from check_clause_hall import check as hall_check
from check_mixed_unsat import verify as mixed_check

ARMS=("MIXED","HALL2","X5_BASE","KISSAT","CADICAL")
def sha(path):
    d=hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda:f.read(1<<20),b""):
            d.update(chunk)
    return d.hexdigest()

def cap_proof_file():
    # Bound proof spam; resource exits are UNSOLVED, not verified.
    max_size=128*1024*1024
    resource.setrlimit(resource.RLIMIT_FSIZE,(max_size,max_size))

def invoke(cmd,timeout):
    t=time.perf_counter()
    try:
        p=subprocess.run(list(map(str,cmd)),capture_output=True,text=True,
                         timeout=max(0.05,timeout),
                         preexec_fn=cap_proof_file,check=False)
        return dict(rc=p.returncode,wall_s=time.perf_counter()-t,
                    stdout=p.stdout,stderr=p.stderr,killed=False)
    except subprocess.TimeoutExpired:
        return dict(rc=None,wall_s=time.perf_counter()-t,
                    stdout="",stderr="HARD_PROCESS_TIMEOUT",killed=True)

def model_verified(path,output,nvars):
    model={}
    for line in output.splitlines():
        if not line.startswith("v "):
            continue
        for token in line.split()[1:]:
            try:lit=int(token)
            except ValueError:return False
            if lit==0:continue
            if abs(lit)>nvars:return False
            val=(lit>0)
            prev=model.get(abs(lit))
            if prev is not None and prev!=val:return False
            model[abs(lit)]=val
    if not model:return False
    saw_header=False
    expected=-1
    count=0
    clause_open=False
    satisfied=False
    try:
        with path.open("r",encoding="ascii") as f:
            for line in f:
                tokens=line.split()
                if not tokens or tokens[0]=="c":continue
                if tokens[0]=="p":
                    if saw_header or len(tokens)!=4 or tokens[1]!="cnf":return False
                    if int(tokens[2])!=nvars:return False
                    expected=int(tokens[3]);saw_header=True;continue
                if not saw_header:return False
                for token in tokens:
                    lit=int(token)
                    if lit!=0:
                        if abs(lit)>nvars:return False
                        clause_open=True
                        if model.get(abs(lit)) == (lit>0):satisfied=True
                    else:
                        count+=1
                        if not satisfied:return False
                        clause_open=False
                        satisfied=False
    except (OSError,ValueError,UnicodeError):
        return False
    return saw_header and not clause_open and count==expected

def certify_guard(path,certificate):
    proof=json.loads(certificate.read_text())
    fmt=proof.get("format")
    raw=path.read_bytes()
    if fmt=="pcmax-clause-hall-v1":
        checked=hall_check(raw,proof)
        if checked.get("status")!="UNSAT_CLAUSE_HALL_CERTIFICATE_VERIFIED":
            raise ValueError("clause Hall checker did not verify")
        return fmt
    if fmt=="drnas-mixed-unsat1":
        checked=mixed_check(raw,proof)
        if checked.get("status")!="UNSAT_VERIFIED":
            raise ValueError("mixed proof checker did not verify")
        return proof.get("method","mixed_unknown")
    raise ValueError("unrecognized guard proof format")

def evaluate(source,arm,rep,args,out):
    path=Path(source["path"])
    source_hash=sha(path)
    if source_hash!=source["source_sha256"]:
        raise RuntimeError("SOURCE_SHA_MISMATCH "+path.name)
    prefix=out/"proofs"/f'{source["id"]:02d}_{arm}_r{rep}'
    prefix.parent.mkdir(parents=True,exist_ok=True)
    proof=Path(str(prefix)+".drat")
    cert=Path(str(prefix)+".guard.json")
    for p in (proof,cert):p.unlink(missing_ok=True)
    core=["--mode","core","--time",str(args.cap)]
    if arm in ("MIXED","HALL2"):
        cmd=[args.math_binary,path,*core,
             "--math-mixed-guard" if arm=="MIXED" else "--pcmax-clause-guard",
             "--pcmax-budget-ms",str(args.guard_ms),
             "--pcmax-certificate",cert,"--proof",proof]
    elif arm=="X5_BASE":
        cmd=[args.base_binary,path,*core,"--proof",proof]
    elif arm=="KISSAT":
        cmd=[args.kissat,path,proof]
    elif arm=="CADICAL":
        cmd=[args.cadical,"-q","--no-binary",path,proof]
    else:raise ValueError("INVALID ARM")
    subprocess_result=invoke(cmd,args.cap+0.30)
    solve_elapsed=subprocess_result["wall_s"]
    stdout=subprocess_result["stdout"]
    stderr=subprocess_result["stderr"]
    rc=subprocess_result["rc"]
    telemetry=[json.loads(l[len("c PCMAX_CAPACITY "):])
               for l in stdout.splitlines() if l.startswith("c PCMAX_CAPACITY ")]
    guard_data=telemetry[-1] if telemetry else {}
    status="UNKNOWN"
    proof_type=None
    proof_check_elapsed=0.0
    if subprocess_result["killed"] or solve_elapsed>args.cap:
        status="TIMEOUT"
    elif rc==10:
        if not model_verified(path,stdout,source["variables"]):
            raise RuntimeError(f"WRONG_SAT_WITNESS:{source['file_id']}:{arm}:{rep}")
        if source["label"]=="unsat":
            # Catalog metadata does not establish a result, but conflicting
            # answers must be reviewed before treating the run as valid.
            raise RuntimeError(f"SAT_VS_OFFICIAL_UNSAT_LABEL:{source['file_id']}:{arm}:{rep}")
        status="SAT_VERIFIED"
    elif rc==20:
        if arm in ("MIXED","HALL2") and cert.is_file():
            t=time.perf_counter()
            try:
                proof_type=certify_guard(path,cert)
            except Exception as e:
                raise RuntimeError(f"GUARD_PROOF_REJECTED:{source['file_id']}:{arm}:{rep}:{e}") from e
            proof_check_elapsed=time.perf_counter()-t
            if source["label"]=="sat":
                raise RuntimeError(f"UNSAT_VS_OFFICIAL_SAT_LABEL:{source['file_id']}:{arm}:{rep}")
            status="UNSAT_CERTIFIED"
        elif proof.is_file() and proof.stat().st_size>0:
            remaining=args.cap-solve_elapsed
            if remaining<=0.0:
                status="UNSAT_CHECK_BUDGET"
            else:
                checker=invoke([args.drat_trim,path,proof],min(remaining,12.0))
                proof_check_elapsed=checker["wall_s"]
                if checker["killed"]:
                    status="UNSAT_CHECK_TIMEOUT"
                elif checker["rc"]==0 and "s VERIFIED" in checker["stdout"]:
                    if source["label"]=="sat":
                        raise RuntimeError(f"UNSAT_VS_OFFICIAL_SAT_LABEL:{source['file_id']}:{arm}:{rep}")
                    status="UNSAT_CERTIFIED"
                    proof_type="DRAT"
                else:
                    # An independent checker rejecting a solver's claimed UNSAT
                    # is a critical research finding; do not hide it in PAR2.
                    raise RuntimeError(f"DRAT_REJECTED:{source['file_id']}:{arm}:{rep}:"
                                       +checker["stderr"][-400:])
        else:
            status="UNSAT_UNVERIFIED"
    elif rc in (0,153):
        status="UNKNOWN"
    else:
        status="PROCESS_ERROR"
    e2e=solve_elapsed+proof_check_elapsed
    accepted=status in ("UNSAT_CERTIFIED","SAT_VERIFIED") and e2e<=args.cap
    if not accepted and status in ("UNSAT_CERTIFIED","SAT_VERIFIED"):
        status="TIMEOUT_WITH_PROOF"
    if status in ("PROCESS_ERROR","WRONG_SAT_WITNESS"):
        raise RuntimeError(f"{status}:{source['file_id']}:{arm}:{rc}:{stderr[-500:]}")
    row={
        "id":source["id"],"family":source["family"],"label":source["label"],
        "file_id":source["file_id"],"sha256":source_hash,
        "variables":source["variables"],"clauses":source["clauses"],
        "arm":arm,"rep":rep,"cap_s":args.cap,"guard_ms":args.guard_ms,
        "rc":rc,"status":status,"accepted":accepted,
        "e2e_s":round(e2e,6),"solve_s":round(solve_elapsed,6),
        "proof_check_s":round(proof_check_elapsed,6),
        "PAR2_verified_s":round(e2e if accepted else 2*args.cap,6),
        "certificate_method":proof_type,
        "module_reason":guard_data.get("reason"),
        "module_groups":guard_data.get("groups"),
        "module_demand":guard_data.get("demand"),
        "module_capacity":guard_data.get("capacity"),
        "proof_bytes":proof.stat().st_size if proof.is_file() else 0,
        "model_independently_checked":status=="SAT_VERIFIED",
        "source_pinned":True,
    }
    print("MIXED_REAL2026_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    return row

def shard(args):
    frozen=Path(args.frozen)
    m=json.loads((frozen/"manifest.json").read_text())
    out=Path(args.out)
    out.mkdir(parents=True,exist_ok=False)
    cpu=min(os.sched_getaffinity(0))
    os.sched_setaffinity(0,{cpu})
    sources=[]
    for x in m["sources"]:
        if x["id"]%args.shards==args.shard:
            item=dict(x)
            item["path"]=str(frozen/x["path"])
            sources.append(item)
    assert len(sources)==3 and args.shards==4 and m["pinned_reference_run"]==43641628537
    bins={"MIXED":args.math_binary,"HALL2":args.math_binary,
          "X5_BASE":args.base_binary,"KISSAT":args.kissat,
          "CADICAL":args.cadical,"DRAT":args.drat_trim}
    binsha={k:sha(Path(v)) for k,v in bins.items()}
    frozen_arms=list(ARMS)
    with (out/"trials.jsonl").open("w") as f:
        for src in sources:
            for rep in range(args.reps):
                arms=frozen_arms[:]
                random.Random(1729+src["id"]*31+rep*911).shuffle(arms)
                for arm in arms:
                    row=evaluate(src,arm,rep,args,out)
                    f.write(json.dumps(row,sort_keys=True)+"\n")
                    f.flush()
    rows=[json.loads(t) for t in (out/"trials.jsonl").read_text().splitlines()]
    metadata={"shard":args.shard,"shards":args.shards,"reps":args.reps,
              "cpu":cpu,"cap_s":args.cap,"guard_ms":args.guard_ms,
              "catalog_sha256":m["catalog_sha256"],
              "binary_sha256":binsha,"sources":[x["source_sha256"] for x in sources],
              "trials":len(rows),"verified":sum(r["accepted"] for r in rows),
              "PAR2_by_arm":{a:round(sum(r["PAR2_verified_s"] for r in rows if r["arm"]==a),4)
                              for a in ARMS}}
    (out/"shard-summary.json").write_text(json.dumps(metadata,indent=2)+"\n")
    print("MIXED_REAL2026_SHARD_PASS "+json.dumps(metadata,sort_keys=True),flush=True)

def aggregate(args):
    inputs=Path(args.downloads)
    rows=[]
    manifests=[]
    for shard in range(4):
        folder=inputs/(f"mixed-real-shard-{shard}")/(f"shard-{shard}")
        data=json.loads((folder/"shard-summary.json").read_text())
        manifests.append(data)
        rows.extend(json.loads(l) for l in (folder/"trials.jsonl").read_text().splitlines())
    assert len(rows)==12*5*2,len(rows)
    assert len(set(r["sha256"] for r in rows))==12
    assert all(m["cap_s"]==args.cap and m["reps"]==2 for m in manifests)
    baseline=manifests[0]["binary_sha256"]
    assert all(m["binary_sha256"]==baseline for m in manifests)
    assert len(set(r["id"] for r in rows))==12
    expected={(src,arm,rep) for src in range(12) for arm in ARMS for rep in range(2)}
    observed={(r["id"],r["arm"],r["rep"]) for r in rows}
    assert observed==expected,(len(observed),len(expected),expected-observed)
    stats={}
    for arm in ARMS:
        sub=[r for r in rows if r["arm"]==arm]
        stats[arm]={
            "PAR2_verified_s":round(sum(r["PAR2_verified_s"] for r in sub),6),
            "solved":sum(r["accepted"] for r in sub),
            "sat":sum(r["status"]=="SAT_VERIFIED" for r in sub),
            "unsat":sum(r["status"]=="UNSAT_CERTIFIED" for r in sub),
            "timeout":sum(r["status"]=="TIMEOUT" for r in sub),
            "other":dict(collections.Counter(r["status"] for r in sub)),
            "median_e2e_s":round(statistics.median(r["e2e_s"] for r in sub),6),
            "proof_methods":dict(collections.Counter(r["certificate_method"] for r in sub
                                                       if r["certificate_method"])),
        }
    base=stats["X5_BASE"]["PAR2_verified_s"]
    for arm in ARMS:
        v=stats[arm]["PAR2_verified_s"]
        stats[arm]["gain_vs_X5_base_pct"]=round(100*(base-v)/base,3) if base else None
    out=Path(args.out)
    out.mkdir(parents=True,exist_ok=False)
    report={
        "protocol":"original SAT2026 SHA-pinned retrospective pairwise trial, 1 logical CPU",
        "note":"Competition catalog labels do not count as certified solver answers",
        "cap_s":args.cap,"repetitions":2,"sources":12,"trials":len(rows),
        "verified_par2_policy":"2*cap for timeout, unknown, unverified or proof-check beyond cap",
        "stats":stats,"shard_metadata":manifests,
    }
    (out/"results.json").write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    (out/"trials.jsonl").write_text("".join(json.dumps(r,sort_keys=True)+"\n" for r in rows))
    lines=["# Original SAT2026 -- MATH-MIXED native vs HALL2, X5, Kissat, CaDiCaL","",
           "12 pinned original SAT2026 CNFs, 2 repetitions, one CPU per solver.",
           f"Verified end-to-end PAR2, cap {args.cap:g}s, unknown/unverified = {2*args.cap:g}s.","",
           "| Solver | Verified/24 | SAT | UNSAT | PAR2 (s) | Gain vs frozen X5 |",
           "|---|---:|---:|---:|---:|---:|"]
    for arm in ARMS:
        x=stats[arm]
        lines.append(f"| {arm} | {x['solved']}/24 | {x['sat']} | {x['unsat']} | "
                     f"{x['PAR2_verified_s']:.3f} | {x['gain_vs_X5_base_pct']:+.2f}% |")
    lines.extend(["","All UNSAT require independently checked DRAT or original-clause structural proof; "
                  "all SAT require independent model validation. "
                  "A no-answer guard with unchanged CDCL fallback is counted by end-to-end runtime, not just guard time."])
    readme="\n".join(lines)+"\n"
    (out/"README.md").write_text(readme)
    print(readme,flush=True)
    print("MIXED_REAL2026_FINAL "+json.dumps({
        "sources":12,"trials":len(rows),"cap_s":args.cap,
        "stats":stats},sort_keys=True),flush=True)

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("shard","aggregate"))
    parser.add_argument("--shard",type=int,default=0)
    parser.add_argument("--shards",type=int,default=4)
    parser.add_argument("--frozen",default="frozen-real2026")
    parser.add_argument("--downloads",default="shards-downloaded")
    parser.add_argument("--out",required=True)
    parser.add_argument("--reps",type=int,default=2)
    parser.add_argument("--cap",type=float,default=6.0)
    parser.add_argument("--guard-ms",type=int,default=120)
    parser.add_argument("--math-binary",type=Path,default=Path("build/drnas-pcmax"))
    parser.add_argument("--base-binary",type=Path,default=Path("build/drnas-pcmax-base"))
    parser.add_argument("--kissat",type=Path,default=Path("reference/build/kissat"))
    parser.add_argument("--cadical",type=Path,default=Path("reference/build/cadical"))
    parser.add_argument("--drat-trim",type=Path,default=Path("reference/build/drat-trim"))
    args=parser.parse_args()
    if args.action=="shard":
        assert args.shard in range(4) and args.reps==2 and 0<args.guard_ms<=args.cap*1000
        shard(args)
    else:
        aggregate(args)
