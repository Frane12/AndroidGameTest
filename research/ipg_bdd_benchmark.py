#!/usr/bin/env python3
"""IPG-BDD1 proof-gated source-CNF bridge audit with frozen originals.

Source-only native extraction using SAME frozen PCMAX BDD graph extractor,
independent backward recurrence checker, deterministic two-class count DP.
Official benchmark labels are held in runner only, never sent to producer.
A reported UNSAT is accepted only if the independent checker validates the
complete original source and all machine BDD profiles.

All source-controlled work serially pinned to one logical CPU. Not blind,
not verified performance PAR2, and not a complete PCMAX solver.
"""
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time

ROOT=pathlib.Path(__file__).resolve().parents[1]
OUT=ROOT/"results/ipg_bdd1"
EXEC=ROOT/"build/drnas-ipg-bdd-extract"
PRODUCER=ROOT/"research/ipg_bdd_profiles.py"
CHECKER=ROOT/"research/ipg_bdd_checker.py"
sys.path.insert(0,str(ROOT/"research"))
from ipg_bdd_fixtures import cases
sys.path.insert(0,str(ROOT/"research/pcmax_capacity"))
from benchmark import materialize

def cmd(argv,seconds):
    start=time.monotonic()
    try:
        r=subprocess.run([str(x) for x in argv],capture_output=True,
                         text=True,timeout=seconds)
        return r.returncode,round(time.monotonic()-start,6),r.stdout+"\n"+r.stderr
    except subprocess.TimeoutExpired:
        return 124,round(time.monotonic()-start,6),"TIMEOUT"

def test_case(kind,name,path,expected,rows,errors):
    dest=OUT/("original_cases" if kind=="FROZEN_ORIGINAL" else "generated_cases")/name.removesuffix(".cnf")
    dest.mkdir(parents=True,exist_ok=True)
    graph=dest/"source_graph.json"
    cert=dest/"ipg_bdd_certificate.json"
    first,sec,out=cmd([EXEC,path.resolve(),"--output",graph.resolve()],12)
    (dest/"extract.log").write_text(out)
    row={
        "name":name,"kind":kind,"expected":expected,
        "sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
        "extract_rc":first,"extract_s":sec,
        "status":"UNKNOWN","graph_extracted":graph.is_file(),
    }
    if first!=0:
        errors.append(name+" native extractor crashed")
        row["status"]="ERROR_NATIVE_EXTRACT"
    elif not graph.is_file():
        row["reason"]="source_graph_not_supported"
    else:
        try:
            structure=json.loads(graph.read_text())
            row["selected_jobs"]=len(structure["eligible_groups"])
            row["machines_extracted"]=len(structure["machine_graphs"])
            row["BDD_transitions"]=sum(len(m["transitions"]) for m in structure["machine_graphs"])
        except (OSError,ValueError,KeyError) as exc:
            errors.append(name+" malformed native graph "+str(exc))
            row["status"]="ERROR_INVALID_EXTRACTED_GRAPH"
        if row["status"]=="UNKNOWN":
            prod,psec,pout=cmd([sys.executable,PRODUCER,"--graph",graph,
                                "--certificate",cert],16)
            (dest/"producer.log").write_text(pout)
            row["producer_s"]=psec
            if prod!=0 or not cert.is_file():
                errors.append(name+" producer did not return safely")
                row["status"]="ERROR_PRODUCER"
            else:
                proposed=json.loads(cert.read_text())
                row["status"]=proposed["status"]
                row["reason"]=proposed.get("reason")
                row["classes"]=[len(g) for g in proposed.get("classes",[])]
                if proposed["status"]=="UNSAT_SOURCE_BDD_COUNT_UNCHECKED":
                    rc,cs,cout=cmd([sys.executable,CHECKER,"--cnf",path,
                                    "--graph",graph,"--certificate",cert],30)
                    (dest/"checker.log").write_text(cout)
                    row.update(checker_rc=rc,checker_s=cs)
                    if rc!=0 or "IPG_BDD_ACCEPT " not in cout:
                        errors.append(name+" unverified original-source UNSAT")
                        row["status"]="ERROR_UNVERIFIED_UNSAT"
                    else:
                        row["status"]="IPG_BDD_SOURCE_COUNT_UNSAT_VERIFIED"
                        if expected=="SAT":
                            errors.append(name+" FALSE_UNSAT against independent SAT control")
                elif row["status"]!="UNKNOWN":
                    errors.append(name+" unknown conclusion format")
    print("IPG_BDD_TRIAL "+json.dumps(row,sort_keys=True),flush=True)
    rows.append(row)
    (OUT/"rows.json").write_text(json.dumps(rows,sort_keys=True,indent=2)+"\n")
    return row

def mutation_tests(rows):
    failures=[]
    one=next((r for r in rows if r["status"]=="IPG_BDD_SOURCE_COUNT_UNSAT_VERIFIED"),None)
    if one is None:
        return ["no IPG-BDD1 independently verified UNSAT to tamper"]
    base=OUT/("original_cases" if one["kind"]=="FROZEN_ORIGINAL" else "generated_cases")/one["name"].removesuffix(".cnf")
    graph=base/"source_graph.json";cert=base/"ipg_bdd_certificate.json"
    rawpath=OUT/"generated"/one["name"] if one["kind"]!="FROZEN_ORIGINAL" else OUT/"originals"/one["name"]
    original=json.loads(cert.read_text())
    for key,modify in [
        ("source_sha",lambda d:d.update(source_sha256="0"*64)),
        ("bdd_profile",lambda d:d["per_machine_profiles"][0].clear()),
        ("wrong_target",lambda d:d["classes"][0].append(999)),
        ("fake_rows",lambda d:d.update(global_reachable_sizes=[1,1,1])),
    ]:
        changed=json.loads(json.dumps(original))
        modify(changed)
        fake=OUT/(f"forged_{key}.json")
        fake.write_text(json.dumps(changed)+"\n")
        rc,sec,output=cmd([sys.executable,CHECKER,"--cnf",rawpath,
                           "--graph",graph,"--certificate",fake],30)
        if rc==0:failures.append("independent checker accepted mutated "+key)
    mutated=OUT/"tampered_source.cnf"
    mutated.write_bytes(rawpath.read_bytes()+b"c altered ORIGINAL bytes\n")
    rc,_,_=cmd([sys.executable,CHECKER,"--cnf",mutated,
                "--graph",graph,"--certificate",cert],30)
    if rc==0:failures.append("independent checker accepted altered source")
    # Forge an implication edge in graph, independently checked against CNF.
    changed=json.loads(graph.read_text())
    edge=changed["machine_graphs"][0]["transitions"][0]
    edge[2]=edge[0] # illegal self-loop and non-source transition
    fake=OUT/"tampered_source_graph.json"
    fake.write_text(json.dumps(changed)+"\n")
    rc,_,_=cmd([sys.executable,CHECKER,"--cnf",rawpath,
                "--graph",fake,"--certificate",cert],30)
    if rc==0:failures.append("independent checker accepted unsupported BDD edge")
    return failures

def main():
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    OUT.mkdir(parents=True,exist_ok=True)
    gen=cases(OUT/"generated")
    rows=[];errors=[]
    for e in gen:
        test_case("GENERATED_BDD",e["name"],OUT/"generated"/e["name"],
                  e["expected"],rows,errors)
    original_files=OUT/"originals"
    original_files.mkdir(exist_ok=True)
    manifest=json.loads((ROOT/"research/pcmax_capacity/sources20.json").read_text())["entries"]
    for i in [0,2,5,10,1,6,11,12]:
        entry=manifest[i]
        try:
            path=materialize(entry,original_files,True)
            if hashlib.sha256(path.read_bytes()).hexdigest()!=entry["sha256"]:
                raise ValueError("frozen original CNF SHA256 mismatch")
            test_case("FROZEN_ORIGINAL",path.name,path,
                      entry["expected_status"],rows,errors)
        except Exception as exc:
            errors.append("official original index "+str(i)+": "+str(exc))
            print("IPG_BDD_SOURCE_ERROR "+str(exc),flush=True)

    errors+=mutation_tests(rows)
    summary={
        "generated_total":len(gen),
        "generated_verified_unsat":sum(r["kind"]=="GENERATED_BDD" and r["status"]=="IPG_BDD_SOURCE_COUNT_UNSAT_VERIFIED" for r in rows),
        "generated_expected_unsat":sum(e["expected"]=="UNSAT" for e in gen),
        "generated_sat_controls":sum(e["expected"]=="SAT" for e in gen),
        "source_frozen_originals":sum(r["kind"]=="FROZEN_ORIGINAL" for r in rows),
        "original_graphs_extracted":sum(r["kind"]=="FROZEN_ORIGINAL" and r["graph_extracted"] for r in rows),
        "original_verified_unsat":sum(r["kind"]=="FROZEN_ORIGINAL" and r["status"]=="IPG_BDD_SOURCE_COUNT_UNSAT_VERIFIED" for r in rows),
        "original_unknown":sum(r["kind"]=="FROZEN_ORIGINAL" and r["status"]=="UNKNOWN" for r in rows),
        "errors":errors,
        "status":"PASS" if not errors else "FAIL",
        "warning":"Preselected retrospective source-frozen PCMAX family and exact-generated BDD fixtures. Count certificate is independently checked, NOT VeriPB/DRAT; performance is NOT prospective verified PAR2, and no general PCMAX polynomial claim.",
    }
    (OUT/"summary.json").write_text(json.dumps(summary,sort_keys=True,indent=2)+"\n")
    print("IPG_BDD_TOTAL "+json.dumps(summary,sort_keys=True),flush=True)
    return 0 if not errors else 1
if __name__=="__main__":sys.exit(main())
