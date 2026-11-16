#!/usr/bin/env python3
"""IPG-BDD3 C++ source-bound paired proof audit, single logical CPU, serial.

Arms:
  BDD2: frozen previous C++ two-class source-count guard
  BDD3: new three-class guard, with BDD2 disabled for measurement parity
Both use the SAME original CNF bytes, the same CPU and the same time cap.
No source names, labels or expected outcomes enter either solver.

Every structural UNSAT MUST pass a separate ORIGINAL-CNF independent
Python checker. CDCL UNSAT requires pinned DRAT-TRIM; SAT requires a model
satisfying every source clause. UNKNOWN never counts as solved.

Synthetic prospective-like generation is precommitted by seed and written
to immutable manifest BEFORE running either arm. It is not a genuine blind
competition evaluation and cannot establish general PAR2 superiority.
"""
import hashlib
import json
import os
import pathlib
import random
import subprocess
import sys
import time

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"results/ipg_bdd3_native"
PREVIOUS=ROOT/"build/drnas-pcmax-mg7-ipg1-bdd2"
NATIVE=ROOT/"build/drnas-pcmax-mg7-ipg1-bdd3"
CHECK3=ROOT/"research/ipg_bdd3_checker.py"
CHECK2=ROOT/"research/ipg_bdd_checker.py"
DRAT=ROOT/"drat-trim/drat-trim"
sys.path.insert(0,str(ROOT/"research"))
from ipg_bdd_fixtures import cases,instance,oracle
sys.path.insert(0,str(ROOT/"research/pcmax_capacity"))
from benchmark import materialize

def run(args,timeout=24):
    start=time.monotonic()
    try:
        r=subprocess.run([str(a) for a in args],capture_output=True,
                         text=True,timeout=timeout)
        return r.returncode,round(time.monotonic()-start,6),r.stdout,r.stderr
    except subprocess.TimeoutExpired:
        return 124,round(time.monotonic()-start,6),"","TIMEOUT"

def check_model(path,out):
    from ipg_bdd_checker import read_source
    nv,nc,clauses=read_source(path.read_bytes())
    values={}
    for line in out.splitlines():
        t=line.split()
        if t and t[0]=="v":
            for item in t[1:]:
                x=int(item)
                if x:values[abs(x)]=x>0
    return len(values)==nv and all(
        any(values[abs(l)]==(l>0) for l in clause)
        for clause in clauses
    )

def frozen_new_cases():
    folder=OUT/"sealed_generated"
    folder.mkdir(parents=True,exist_ok=True)
    randomizer=random.Random(2401162026)
    generated=[]
    # Three distinct lengths are intentionally common, so this is not a
    # benchmark tuned exclusively to two-type fixed-cardinality instances.
    for trial in range(24):
        n=randomizer.randint(5,9)
        lengths=randomizer.sample(range(2,15),3)
        jobs=[randomizer.choice(lengths) for _ in range(n)]
        T=randomizer.randint(max(jobs)-1,max(jobs)*2+1)
        m=2 if trial%2==0 else 3
        data,_=instance(jobs,m,T)
        name=f"sealed_{trial:03d}_m{m}.cnf"
        target=folder/name
        target.write_bytes(data)
        generated.append({
            "name":name,"sha256":hashlib.sha256(data).hexdigest(),
            "label":"SAT" if oracle(jobs,m,T) else "UNSAT",
            "n":n,"m":m,"distinct_lengths":len(set(jobs)),
        })
    # Freeze this manifest before reading any solver output.
    (OUT/"sealed_manifest.json").write_text(json.dumps(
        {"generation_seed":2401162026,"sources":generated},indent=2,sort_keys=True)+"\n")
    return [(folder/x["name"],x["label"],"SEALED_SYNTHETIC") for x in generated]

def originals():
    roots=OUT/"frozen_originals"
    roots.mkdir(parents=True,exist_ok=True)
    entries=json.loads((ROOT/"research/pcmax_capacity/sources20.json").read_text())["entries"]
    result=[]
    # Named retrospective originals, including difficult mixed SAT cases.
    for i in [0,2,3,5,7,10,1,6,11,12]:
        e=entries[i]
        source=materialize(e,roots,True)
        if hashlib.sha256(source.read_bytes()).hexdigest()!=e["sha256"]:
            raise ValueError("source SHA mismatch: "+e["name"])
        result.append((source,e["expected_status"],"RETROSPECTIVE_ORIGINAL"))
    return result

def one(path,expected,kind,arm):
    key=path.name.removesuffix(".cnf")
    folder=OUT/"trials"/key/arm
    folder.mkdir(parents=True,exist_ok=True)
    graph=folder/"graph.json"
    certificate=folder/"certificate.json"
    drat=folder/"fallback.drat"
    capacity=folder/"unused_capacity.json"
    cmd=[NATIVE if arm=="BDD3" else PREVIOUS,path.resolve(),
         "--mode","core","--time","2.2" if kind=="RETROSPECTIVE_ORIGINAL" else "2",
         "--stats","--pcmax-capacity","--pcmax-budget-ms","0",
         "--pcmax-certificate",capacity,"--residual-scc",
         "--proof",drat]
    if arm=="BDD3":
        cmd+=["--ipg-bdd3","--ipg-bdd3-budget-ms","600",
              "--ipg-bdd3-graph",graph,"--ipg-bdd3-certificate",certificate]
    else:
        cmd+=["--ipg-bdd2","--ipg-bdd2-budget-ms","600",
              "--ipg-bdd2-graph",graph,"--ipg-bdd2-certificate",certificate]
    rc,secs,out,err=run(cmd,8)
    (folder/"stdout.log").write_text(out)
    (folder/"stderr.log").write_text(err)
    kinds=[line.rsplit(" ",1)[-1] for line in out.splitlines()
           if line.startswith("c PCMAX_UNIFIED_PROOF_KIND ")]
    row={"name":key,"source_kind":kind,"arm":arm,"expected":expected,
         "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
         "solver_rc":rc,"native_wall_s":secs,"status":"UNKNOWN","proof_kind":kinds}
    for line in out.splitlines():
        prefix="c IPG_BDD3 " if arm=="BDD3" else "c IPG_BDD2 "
        if line.startswith(prefix):
            try:row["telemetry"]=json.loads(line[len(prefix):])
            except json.JSONDecodeError:
                row["status"]="ERROR_BAD_TELEMETRY"
    if rc==20 and "s UNSATISFIABLE" in out:
        if certificate.is_file():
            required=("IPG_BDD3_JSON_NEEDS_INDEPENDENT_CHECKER" if arm=="BDD3"
                      else "IPG_BDD2_JSON_NEEDS_INDEPENDENT_CHECKER")
            if kinds!=[required] or not graph.is_file():
                row["status"]="ERROR_INCONSISTENT_PROOF_KIND"
            else:
                check=CHECK3 if arm=="BDD3" else CHECK2
                vc,vt,vout,verr=run(
                    [sys.executable,check,"--cnf",path,"--graph",graph,
                     "--certificate",certificate],40)
                (folder/"checker.log").write_text(vout+"\n"+verr)
                marker="IPG_BDD3_ACCEPT " if arm=="BDD3" else "IPG_BDD_ACCEPT "
                row.update(checker_rc=vc,checker_s=vt)
                row["status"]="SOURCE_UNSAT_VERIFIED" if vc==0 and marker in vout else "ERROR_SOURCE_REJECTED"
                if drat.is_file() and drat.stat().st_size:
                    row["status"]="ERROR_MIXED_PROOFS"
                if row["status"]=="SOURCE_UNSAT_VERIFIED":
                    # Certificate size is a key goal for IPG-BDD3.
                    row["proof_bytes"]=certificate.stat().st_size
                    row["graph_bytes"]=graph.stat().st_size
        elif kinds==["DRAT_PROOF"] and drat.is_file() and drat.stat().st_size:
            vr,vt,vout,verr=run([DRAT,path,drat],30)
            (folder/"checker_drat.log").write_text(vout+"\n"+verr)
            row.update(checker_rc=vr,checker_s=vt)
            row["status"]="DRAT_UNSAT_VERIFIED" if vr==0 and "s VERIFIED" in vout+"\n"+verr else "ERROR_DRAT_REJECTED"
        else:
            row["status"]="ERROR_NO_PROOF"
    elif rc==10 and "s SATISFIABLE" in out:
        row["status"]="SAT_MODEL_VERIFIED" if check_model(path,out) else "ERROR_INVALID_MODEL"
    elif rc==0 and "s UNKNOWN" in out:
        row["status"]="UNKNOWN"
    elif rc==124:
        row["status"]="TIMEOUT"
    else:
        row["status"]="ERROR_NATIVE_RUN"
    if expected=="SAT" and row["status"] in ("SOURCE_UNSAT_VERIFIED","DRAT_UNSAT_VERIFIED"):
        row["status"]="ERROR_FALSE_UNSAT"
    print("IPG_BDD3_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    return row

def tamper_test(all_rows,files):
    hit=next((r for r in all_rows if r["arm"]=="BDD3" and
              r["status"]=="SOURCE_UNSAT_VERIFIED"),None)
    if not hit:
        return ["no accepted BDD3 source proof for adversarial verification"]
    path=files[hit["name"]]
    base=OUT/"trials"/hit["name"]/"BDD3"
    cert=json.loads((base/"certificate.json").read_text())
    graph=base/"graph.json"
    problems=[]
    for case,edit in (
        ("source_hash",lambda x:x.update(source_sha256="0"*64)),
        ("wrong_class",lambda x:x["classes"][0].append(999)),
        ("wrong_profile",lambda x:x["machine_profile_sizes"].__setitem__(0,-99)),
        ("wrong_rows",lambda x:x.update(global_reachable_sizes=[1,1,1])),
    ):
        fake=json.loads(json.dumps(cert))
        edit(fake)
        altered=OUT/(f"forged_{case}.json")
        altered.write_text(json.dumps(fake)+"\n")
        rc,_,_,_=run([sys.executable,CHECK3,"--cnf",path,
                     "--graph",graph,"--certificate",altered],20)
        if rc==0:problems.append(case+" forged evidence accepted")
    changed=OUT/"changed_source.cnf"
    changed.write_bytes(path.read_bytes()+b"c deliberately changed\n")
    rc,_,_,_=run([sys.executable,CHECK3,"--cnf",changed,
                 "--graph",graph,"--certificate",base/"certificate.json"],20)
    if rc==0:problems.append("source-byte tamper accepted")
    return problems

def main():
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    OUT.mkdir(parents=True,exist_ok=True)
    baseline=cases(OUT/"generated_fixture")
    tasks=[(OUT/"generated_fixture"/x["name"],x["expected"],"GENERATED_KNOWN") for x in baseline]
    tasks+=frozen_new_cases()
    tasks+=originals()
    files={path.name.removesuffix(".cnf"):path for path,_,_ in tasks}
    rows=[];errors=[]
    # Cases paired by exact source bytes, fixed arm order, serial one CPU.
    for source,expected,kind in tasks:
        for arm in ("BDD2","BDD3"):
            row=one(source,expected,kind,arm)
            rows.append(row)
            if row["status"].startswith("ERROR"):
                errors.append(f"{row['name']} {arm}: {row['status']}")
        (OUT/"rows.json").write_text(json.dumps(rows,indent=2,sort_keys=True)+"\n")
    errors+=tamper_test(rows,files)
    a=[x for x in rows if x["arm"]=="BDD2"]
    b=[x for x in rows if x["arm"]=="BDD3"]
    byname={x["name"]:x for x in a}
    novel=[x["name"] for x in b if x["status"]=="SOURCE_UNSAT_VERIFIED" and
           byname[x["name"]]["status"]!="SOURCE_UNSAT_VERIFIED"]
    original_novel=[x for x in novel if any(
        y["name"]==x and y["source_kind"]=="RETROSPECTIVE_ORIGINAL" for y in b)]
    summary={
        "status":"PASS" if not errors else "FAIL",
        "pair_count":len(tasks),"trials":len(rows),
        "generated_known":len(baseline),"sealed_generated":24,
        "original_retrospective":sum(k=="RETROSPECTIVE_ORIGINAL" for _,_,k in tasks),
        "bdd2_source_verified":sum(x["status"]=="SOURCE_UNSAT_VERIFIED" for x in a),
        "bdd3_source_verified":sum(x["status"]=="SOURCE_UNSAT_VERIFIED" for x in b),
        "bdd3_original_source_verified":sum(x["status"]=="SOURCE_UNSAT_VERIFIED" and
          x["source_kind"]=="RETROSPECTIVE_ORIGINAL" for x in b),
        "bdd3_new_source_proofs_vs_bdd2":novel,
        "bdd3_new_original_proofs_vs_bdd2":original_novel,
        "bdd3_compact_proof_bytes":[x["proof_bytes"] for x in b if x["status"]=="SOURCE_UNSAT_VERIFIED"],
        "errors":errors,
        "note":"First-pass experimental native 3D source-count test on known and sealed-generated CNFs plus retrospective official PCMAX. Sealed synthetics are blind-to-solver only, NOT blind competition data. Standard VeriPB/DRAT for BDD3 not yet implemented."
    }
    (OUT/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    print("IPG_BDD3_TOTAL "+json.dumps(summary,sort_keys=True),flush=True)
    return 1 if errors else 0
if __name__=="__main__":raise SystemExit(main())
