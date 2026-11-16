#!/usr/bin/env python3
"""DRNAS IPG-BDD2 C++ native proof-gated integration audit.

The C++ solver runs natively, one process on one logical CPU. Python exists
only in the OFFLINE benchmark and INDEPENDENT source-CNF verification path.
No external checker is called by the C++ solver itself.

BDD capacity is deliberately disabled (budget 0) for this diagnostic benchmark,
so that IPG-BDD2 gets an opportunity on the same source as the older capacity
guard. In normal combined use the certified capacity module runs first.

Exact source bytes are pinned; the reference Python producer and the source-
independent backward checker are NOT used by the native C++ implementation.
"""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"results/ipg_bdd2_native"
SRC=ROOT/"research"
BINARY=ROOT/"build/drnas-pcmax-mg7-ipg1-bdd2"
FROZEN=ROOT/"build/drnas-pcmax-mg7-ipg1"
CHECK=SRC/"ipg_bdd_checker.py"
PY_PROD=SRC/"ipg_bdd_profiles.py"
DRAT=ROOT/"drat-trim/drat-trim"
sys.path.insert(0,str(SRC))
from ipg_bdd_fixtures import cases
sys.path.insert(0,str(ROOT/"research/pcmax_capacity"))
from benchmark import materialize

def invoke(argv,timeout=15):
    begin=time.monotonic()
    try:
        r=subprocess.run([str(x) for x in argv],capture_output=True,text=True,
                         timeout=timeout)
        return r.returncode,round(time.monotonic()-begin,6),r.stdout,r.stderr
    except subprocess.TimeoutExpired:
        return 124,round(time.monotonic()-begin,6),"","TIMEOUT"

def sat_check(path,stdout):
    from ipg_bdd_checker import read_source
    nv,nc,clauses=read_source(path.read_bytes())
    vals={}
    for line in stdout.splitlines():
        a=line.split()
        if a and a[0]=="v":
            for s in a[1:]:
                lit=int(s)
                if lit:vals[abs(lit)]=lit>0
    return len(vals)==nv and all(
        any(vals[abs(lit)]==(lit>0) for lit in clause)
        for clause in clauses)

def run_one(path,expect,kind,old=False):
    stem=path.name.removesuffix(".cnf")
    arm="PREVIOUS_UNION" if old else "IPG_BDD2_NATIVE"
    folder=OUT/("original" if kind=="ORIGINAL" else "generated")/stem/arm
    folder.mkdir(parents=True,exist_ok=True)
    graph=folder/"source_graph.json"
    cert=folder/"count_certificate.json"
    capacity=folder/"unused_capacity.json"
    proof=folder/"fallback.drat"
    args=[FROZEN if old else BINARY,path.resolve(),"--mode","core",
          "--time","2.5" if kind=="ORIGINAL" else "2",
          "--stats","--pcmax-capacity","--pcmax-budget-ms","0",
          "--pcmax-certificate",capacity,"--residual-scc","--proof",proof]
    if not old:
        args += ["--ipg-bdd2","--ipg-bdd2-budget-ms","750",
                 "--ipg-bdd2-graph",graph,"--ipg-bdd2-certificate",cert]
    rc,secs,stdout,stderr=invoke(args,7)
    (folder/"solver.stdout").write_text(stdout)
    (folder/"solver.stderr").write_text(stderr)
    kindmarkers=[line.rsplit(" ",1)[-1] for line in stdout.splitlines()
                 if line.startswith("c PCMAX_UNIFIED_PROOF_KIND ")]
    row={"name":stem,"arm":arm,"expected":expect,"source_kind":kind,
         "source_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
         "native_wall_s":secs,"solver_rc":rc,"proof_kind":kindmarkers,
         "status":"UNKNOWN"}
    if not old:
        for line in stdout.splitlines():
            if line.startswith("c IPG_BDD2 "):
                try:row["native_telemetry"]=json.loads(line[len("c IPG_BDD2 "):])
                except ValueError:row["status"]="ERROR_TELEMETRY_INVALID"
    if rc==20 and "s UNSATISFIABLE" in stdout:
        if graph.exists() or cert.exists():
            if (old or kindmarkers!=["IPG_BDD2_JSON_NEEDS_INDEPENDENT_CHECKER"]
                    or not graph.exists() or not cert.exists()):
                row["status"]="ERROR_PROOF_ROUTING"
            else:
                checker_rc,check_s,check_out,check_err=invoke(
                    [sys.executable,CHECK,"--cnf",path,"--graph",graph,
                     "--certificate",cert],30)
                (folder/"independent_checker.log").write_text(check_out+"\n"+check_err)
                row.update(checker_s=check_s,checker_rc=checker_rc)
                if checker_rc==0 and "IPG_BDD_ACCEPT " in check_out:
                    row["status"]="IPG_BDD_SOURCE_COUNT_UNSAT_VERIFIED"
                else:
                    row["status"]="ERROR_SOURCE_PROOF_REJECTED"
                if proof.is_file() and proof.stat().st_size:
                    row["status"]="ERROR_CERTIFICATE_MIXED_WITH_DRAT"
                # Compare independent Python *producer* only as a regression
                # oracle, not as a required part of the native solver.
                if row["status"]=="IPG_BDD_SOURCE_COUNT_UNSAT_VERIFIED":
                    reference=folder/"python_reference.json"
                    p_rc,_,p_out,p_err=invoke(
                        [sys.executable,PY_PROD,"--graph",graph,"--certificate",reference],35)
                    if p_rc:
                        row["status"]="ERROR_PYTHON_REFERENCE"
                        (folder/"reference_error.log").write_text(p_out+p_err)
                    else:
                        a=json.loads(cert.read_text())
                        b=json.loads(reference.read_text())
                        for key in ("classes","per_machine_profiles","global_reachable_sizes"):
                            if a[key]!=b[key]:
                                row["status"]="ERROR_NATIVE_REFERENCE_DIFFERENCE"
                                row["difference_field"]=key
                                break
        elif kindmarkers==["DRAT_PROOF"] and proof.exists():
            chk,check_s,chout,cherr=invoke([DRAT,path,proof],35)
            (folder/"independent_drat.log").write_text(chout+"\n"+cherr)
            row["checker_rc"]=chk;row["checker_s"]=check_s
            row["status"]="DRAT_UNSAT_VERIFIED" if chk==0 and (
                "s VERIFIED" in chout+"\n"+cherr) else "ERROR_DRAT_REJECTED"
        else:
            row["status"]="ERROR_UNSUPPORTED_PROOF_KIND"
    elif rc==10 and "s SATISFIABLE" in stdout:
        row["status"]="SAT_MODEL_VERIFIED" if sat_check(path,stdout) else "ERROR_INVALID_MODEL"
    elif rc==0 and "s UNKNOWN" in stdout:
        row["status"]="UNKNOWN"
    elif rc==124:
        row["status"]="TIMEOUT"
    else:
        row["status"]="ERROR_NATIVE_RUN"
    print("IPG_BDD2_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    return row

def corruptions(rows,files):
    errors=[]
    solved=next((r for r in rows if r["arm"]=="IPG_BDD2_NATIVE" and
                 r["status"]=="IPG_BDD_SOURCE_COUNT_UNSAT_VERIFIED"),None)
    if solved is None:return ["no source-bound verified native IPG BDD2 UNSAT to audit"]
    path=files[solved["name"]]
    folder=OUT/("original" if solved["source_kind"]=="ORIGINAL" else "generated")/solved["name"]/"IPG_BDD2_NATIVE"
    graph=folder/"source_graph.json"
    cert=folder/"count_certificate.json"
    raw=json.loads(cert.read_text())
    muts=[
       ("hash",lambda obj:obj.update(source_sha256="0"*64)),
       ("class",lambda obj:obj["classes"][0].append(999)),
       ("profile",lambda obj:obj["per_machine_profiles"][0].clear()),
       ("global",lambda obj:obj.update(global_reachable_sizes=[1,1,1])),
    ]
    for label,modify in muts:
        altered=json.loads(json.dumps(raw))
        modify(altered)
        fake=OUT/("corrupted_"+label+".json")
        fake.write_text(json.dumps(altered)+"\n")
        rc,_,_,_=invoke([sys.executable,CHECK,"--cnf",path,
                        "--graph",graph,"--certificate",fake],25)
        if rc==0:errors.append("forged "+label+" certificate accepted")
    changed=OUT/"tampered_source.cnf"
    changed.write_bytes(path.read_bytes()+b"c source bytes tampered\n")
    rc,_,_,_=invoke([sys.executable,CHECK,"--cnf",changed,
                    "--graph",graph,"--certificate",cert],25)
    if rc==0:errors.append("tampered source accepted")
    tampered_graph=json.loads(graph.read_text())
    tampered_graph["machine_graphs"][0]["transitions"][0][2]=(
        tampered_graph["machine_graphs"][0]["transitions"][0][0])
    fake=OUT/"tampered_graph.json"
    fake.write_text(json.dumps(tampered_graph)+"\n")
    rc,_,_,_=invoke([sys.executable,CHECK,"--cnf",path,
                    "--graph",fake,"--certificate",cert],25)
    if rc==0:errors.append("tampered BDD transition accepted")
    return errors

def main():
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    OUT.mkdir(parents=True,exist_ok=True)
    generated=cases(OUT/"generated_sources")
    manifest=json.loads((ROOT/"research/pcmax_capacity/sources20.json").read_text())["entries"]
    original_dir=OUT/"original_sources";original_dir.mkdir(exist_ok=True)
    # Small original set and SAT controls, with independent SOURCE SHA.
    official=[]
    for index in [0,2,5,10,1,6,11]:
        item=manifest[index]
        path=materialize(item,original_dir,True)
        if hashlib.sha256(path.read_bytes()).hexdigest()!=item["sha256"]:
            raise ValueError("original source SHA mismatch: "+item["name"])
        official.append((path,item["expected_status"]))
    rows=[];errors=[];files={}
    for item in generated:
        path=OUT/"generated_sources"/item["name"]
        files[path.stem]=path
        row=run_one(path,item["expected"],"GENERATED")
        rows.append(row)
        if row["status"].startswith("ERROR"):errors.append(str(row))
    for path,label in official:
        files[path.stem]=path
        row=run_one(path,label,"ORIGINAL")
        rows.append(row)
        if row["status"].startswith("ERROR"):errors.append(str(row))
    # Validate that the original branch's frozen baseline remains runnable
    # without the new module on representative sources.
    for path,label in [(
        OUT/"generated_sources"/"mixed_gap_m3.cnf","UNSAT"
    ),(official[0][0],official[0][1])]:
        row=run_one(path,label,"ORIGINAL" if path==official[0][0] else "GENERATED",old=True)
        rows.append(row)
        if row["status"].startswith("ERROR"):errors.append(str(row))
    errors+=corruptions(rows,files)
    native=[r for r in rows if r["arm"]=="IPG_BDD2_NATIVE"]
    orig=[r for r in native if r["source_kind"]=="ORIGINAL"]
    gen=[r for r in native if r["source_kind"]=="GENERATED"]
    # Frozen expected hit: existing Python prototype already independently
    # proved source-bound m11 PCMAX UNSAT with 16 selected jobs.
    target=next(r for r in orig if "m11-1517-6802" in r["name"])
    if target["status"]!="IPG_BDD_SOURCE_COUNT_UNSAT_VERIFIED":
        errors.append("native m11-1517-6802 regression vs independent source Python prototype")
    if any(r["expected"]=="SAT" and r["status"] in
        ("IPG_BDD_SOURCE_COUNT_UNSAT_VERIFIED","DRAT_UNSAT_VERIFIED") for r in native):
        errors.append("false UNSAT on SAT-labeled control")
    summary={
       "status":"PASS" if not errors else "FAIL",
       "generated_count":len(gen),
       "generated_source_verified":sum(r["status"]=="IPG_BDD_SOURCE_COUNT_UNSAT_VERIFIED" for r in gen),
       "generated_expected_unsat":sum(r["expected"]=="UNSAT" for r in gen),
       "original_count":len(orig),
       "original_source_verified":sum(r["status"]=="IPG_BDD_SOURCE_COUNT_UNSAT_VERIFIED" for r in orig),
       "original_unknown":sum(r["status"] in ("UNKNOWN","TIMEOUT") for r in orig),
       "native_m11_source_verified":target["status"]=="IPG_BDD_SOURCE_COUNT_UNSAT_VERIFIED",
       "reference_old_arms":sum(r["arm"]=="PREVIOUS_UNION" for r in rows),
       "errors":errors,
       "note":"Native C++ in-process IPG BDD source count guard; Python used exclusively for independent verification. Prior known source-frozen originals, not blind PAR2. Structural proof NOT standard VeriPB/DRAT."
    }
    (OUT/"rows.json").write_text(json.dumps(rows,indent=2,sort_keys=True)+"\n")
    (OUT/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    print("IPG_BDD2_TOTAL "+json.dumps(summary,sort_keys=True),flush=True)
    return 0 if not errors else 1
if __name__=="__main__":raise SystemExit(main())
