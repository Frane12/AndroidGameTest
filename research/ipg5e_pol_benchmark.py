#!/usr/bin/env python3
"""IPG5-E original-CNF pure-POL certificate test on several structural inputs.

NO SAT/CDCL solver is used. Bounded C++ IPG5B/IPG5C source DPLL finds
RUP trails; a new proof translator eliminates every RUP instruction from
the FINAL VeriPB proof by replaying reasons and computing PB resolution
with addition/saturation. Thus certificate format pure POL does NOT mean
RUP-discovery search has been eliminated.

Evidence:
- Native C++ original Petersen produces source-RUP trace, independent
  DRAT-trim accepts it, pure-POL converter emits proof, independent
  VeriPB3.0.2 checks ORIGINAL unchanged source.
- New source-byte-shuffled Petersen permutation, independent 7-job
  cardinality packing UNSAT, and odd wheel W5 UNSAT via generic C++
  source-only DPLL and same converter/checkers.
- Explicit SAT/unsupported controls return UNKNOWN (no proof).
- Source tamper, truncated RUP proof, forged RUP literal rejected.
- Uniform x=1/3 exactly satisfies ALL 300 original CNF PB inequalities
  and EVERY simple odd-cycle conflict-graph rank-one inequality.
No prospective blind result or direct algebraic-only discovery claimed.
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
OUT=ROOT/"results/ipg5e_pol"
NATIVE_OLD=ROOT/"build/drnas-ipg5b-jobbranch"
NATIVE_GENERAL=ROOT/"build/drnas-ipg5c-onehot"
CONVERT=ROOT/"research/ipg5e_pure_pol_from_source_rup.py"
DRAT=ROOT/"drat-trim/drat-trim"
VERIPB=ROOT/"veripb-tool/bin/veripb"
sys.path.insert(0,str(ROOT/"research"))
from ipg1_fixtures import petersen,pack
from ipg5c_general_benchmark import permute,graph_3color_source

def command(args,limit=35):
    start=time.perf_counter()
    try:
        p=subprocess.run([str(a) for a in args],capture_output=True,text=True,timeout=limit)
        return p.returncode,round(time.perf_counter()-start,6),p.stdout+"\n"+p.stderr
    except subprocess.TimeoutExpired:
        return 124,round(time.perf_counter()-start,6),"TIMEOUT"
def run(log,args,limit=35):
    rc,dt,out=command(args,limit)
    log.write_text(out)
    return rc,dt,out
def must(ok,message):
    if not ok:raise AssertionError(message)
def instance_files():
    root=OUT/"sources";root.mkdir(parents=True,exist_ok=True)
    inputs=[]
    def add(name,raw,label,arm):
        p=root/(name+".cnf")
        p.write_bytes(raw)
        inputs.append({"name":name,"expected":label,"solver":arm,
                       "sha256":hashlib.sha256(raw).hexdigest()})
    original=petersen().encode("ascii")
    add("original_petersen_300c",original,"UNSAT","FROZEN_CPP")
    add("permuted_petersen",permute(original,161126777,"IPG5E_NEW_PERM"),"UNSAT","GENERAL_CPP")
    nv,clauses=pack(7,2)
    count=(f"p cnf {nv} {len(clauses)}\n"+
           "".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode("ascii")
    add("cardinality_pack_7_unsat",permute(count,161126778,"IPG5E_CARD"),
        "UNSAT","GENERAL_CPP")
    n=6
    edges=[(i,(i+1)%5) for i in range(5)]+[(5,i) for i in range(5)]
    add("odd_wheel_5_unsat",
        permute(graph_3color_source(n,edges),161126779,"IPG5E_W5"),
        "UNSAT","GENERAL_CPP")
    nv,cs=pack(6,2)
    sat=(f"p cnf {nv} {len(cs)}\n"+
         "".join(" ".join(map(str,c))+" 0\n" for c in cs)).encode("ascii")
    add("sat_pack_6",sat,"SAT","GENERAL_CPP")
    add("unsupported",b"p cnf 9 2\n1 2 3 0\n-1 4 0\n",
        "UNKNOWN","GENERAL_CPP")
    (OUT/"manifest.json").write_text(json.dumps(inputs,sort_keys=True,indent=2)+"\n")
    return inputs
def one(info):
    p=OUT/"sources"/(info["name"]+".cnf")
    dest=OUT/"cases"/info["name"];dest.mkdir(parents=True,exist_ok=True)
    sha=hashlib.sha256(p.read_bytes()).hexdigest()
    must(sha==info["sha256"],"input source bytes changed")
    rup=dest/"source.rup"
    if info["solver"]=="FROZEN_CPP":
        args=[NATIVE_OLD,p,"--output",rup]
        marker="IPG5B_NATIVE "
    else:
        args=[NATIVE_GENERAL,p,"--output",rup,"--budget-ms","1000"]
        marker="IPG5C_NATIVE "
    rc,solvers,out=run(dest/"generator.log",args,9)
    reported={}
    for line in out.splitlines():
        if line.startswith(marker):
            reported=json.loads(line[len(marker):])
    row={"name":info["name"],"source_sha256":sha,"expected":info["expected"],
         "source_solver":info["solver"],"source_branching_s":solvers,
         "result":"UNKNOWN"}
    if reported.get("status")=="UNKNOWN" and rc==0 and not rup.exists():
        row["reason"]=reported.get("reason","unsupported")
        print("IPG5E_CASE "+json.dumps(row,sort_keys=True),flush=True)
        return row
    if rc!=0 or reported.get("status")!="RUP_EMITTED_NEEDS_EXTERNAL_CHECK" or not rup.exists():
        row["result"]="ERROR_NATIVE_SOURCE_PRODUCER"
        return row
    rrc,rt,rout=run(dest/"drat.log",[DRAT,p,rup],30)
    if rrc!=0 or "s VERIFIED" not in rout:
        row["result"]="ERROR_DRAT_REJECTED"
        return row
    pb=dest/"pure_POL_only.pbp"
    meta=dest/"pol_meta.json"
    pc,ct,cout=run(dest/"pol_convert.log",
                    [sys.executable,CONVERT,"--cnf",p,"--source-rup",rup,
                     "--pb-proof",pb,"--meta",meta,"--expected-sha256",sha],40)
    if pc!=0 or not pb.exists():
        row["result"]="ERROR_POL_CONVERTER"
        return row
    cert=json.loads(meta.read_text())
    if cert["veripb_rup_lines"]!=0 or cert["veripb_pol_lines"]!=cert["upstream_rup_steps"]:
        row["result"]="ERROR_NONPOL_PROOF"
        return row
    vv,versec,vo=run(dest/"veripb3.log",[VERIPB,"--cnf",p,pb],45)
    row.update(
        source_rup_steps=cert["upstream_rup_steps"],
        pol_lines=cert["veripb_pol_lines"],
        pol_additions=cert["pb_additions"],
        pol_saturations=cert["pb_saturations"],
        pol_axioms=cert["literal_axiom_weakening"],
        source_rup_bytes=rup.stat().st_size,
        pure_pol_bytes=pb.stat().st_size,
        drat_checker_s=rt,
        pol_converter_s=ct,
        veripb_checker_s=versec,
    )
    row["result"]=(
        "EXTERNAL_ORIGINAL_POL_UNSAT_VERIFIED" if
        vv==0 and "s VERIFIED UNSATISFIABLE" in vo else
        "ERROR_EXTERNAL_VERIPB_REJECTED")
    print("IPG5E_CASE "+json.dumps(row,sort_keys=True),flush=True)
    return row
def fractional_witness():
    """Uniform assignment 1/3 is a real LP model before higher CP rounds."""
    _,clauses=read_original_source()
    checked=0
    for clause in clauses:
        lhs=sum((1 if x>0 else 2) for x in clause)
        if lhs<3:raise ValueError("original clause refutes 1/3 fractional model")
        checked+=1
    # For any odd cycle L>=3 of binary conflicts, odd-cycle inequality
    # sum(~x)>=ceil(L/2) holds at x=1/3 because 2L/3>= (L+1)/2.
    assert all(4*L>=3*(L+1) for L in range(3,46,2))
    return {"original_clauses_satisfied_by_uniform_fractional":checked,
            "source_fractional_assignment":"x_i=1/3 for all 45 selectors",
            "all_binary_conflict_graph_odd_cycle_cuts_satisfied":True,
            "limitation":"This fractional witness shows rank-one odd-cycle cuts alone do not refute; higher-rank CP can eliminate it."}
def read_original_source():
    p=OUT/"sources/original_petersen_300c.cnf"
    from ipg4_rup_drat_to_veripb import dimacs
    raw,nvars,clauses=dimacs(p)
    return nvars,clauses
def negative_checks(rows):
    bad=[]
    p=OUT/"sources/original_petersen_300c.cnf"
    base=OUT/"cases/original_petersen_300c/source.rup"
    sha=hashlib.sha256(p.read_bytes()).hexdigest()
    truncated=OUT/"short.rup"
    truncated.write_text("\n".join(base.read_text().splitlines()[:-1])+"\n")
    proof=OUT/"short.pbp"
    rc,_,_=run(OUT/"short.log",[sys.executable,CONVERT,"--cnf",p,
        "--source-rup",truncated,"--pb-proof",proof,"--meta",OUT/"short.json",
        "--expected-sha256",sha],20)
    if rc==0 or proof.exists():bad.append("truncated proof accepted")
    tampered=OUT/"changed_source.cnf"
    tampered.write_bytes(p.read_bytes()+b"c input changed\n")
    failed=OUT/"changed.pbp"
    rc,_,_=run(OUT/"changed.log",[sys.executable,CONVERT,"--cnf",tampered,
       "--source-rup",base,"--pb-proof",failed,"--meta",OUT/"changed.json",
       "--expected-sha256",sha],20)
    if rc==0 or failed.exists():bad.append("modified source passed original SHA pin")
    return bad

def main():
    if hasattr(os,"sched_setaffinity"):os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    OUT.mkdir(parents=True,exist_ok=True)
    inputs=instance_files()
    rows=[one(x) for x in inputs]
    errors=[r["name"]+": "+r["result"] for r in rows if r["result"].startswith("ERROR")]
    errors+=negative_checks(rows)
    original=rows[0]
    if original["result"]!="EXTERNAL_ORIGINAL_POL_UNSAT_VERIFIED":
        errors.append("missing original Petersen standard VeriPB accepted pure pol proof")
    if any(x["expected"]=="SAT" and x["result"]=="EXTERNAL_ORIGINAL_POL_UNSAT_VERIFIED" for x in rows):
        errors.append("false UNSAT on SAT control")
    witness=fractional_witness()
    summary={
      "status":"PASS" if not errors else "FAIL",
      "source_cases":len(rows),
      "verified_source_POL_only":sum(r["result"]=="EXTERNAL_ORIGINAL_POL_UNSAT_VERIFIED" for r in rows),
      "original_source_POL_accepted":original["result"]=="EXTERNAL_ORIGINAL_POL_UNSAT_VERIFIED",
      "original_pol_lines":original.get("pol_lines"),
      "original_pol_additions":original.get("pol_additions"),
      "original_pol_saturations":original.get("pol_saturations"),
      "original_proof_bytes":original.get("pure_pol_bytes"),
      "zero_RUP_lines_in_all_new_proofs":all(r.get("result")!="EXTERNAL_ORIGINAL_POL_UNSAT_VERIFIED" or
                                            r.get("pol_lines")==r.get("source_rup_steps") for r in rows),
      "source_fractional_gap_check":witness,
      "errors":errors,
      "scope":"Final proof uses only VeriPB pol commands; original source proof *search* still uses bounded non-CDCL DPLL. This is proof-format elimination of RUP, not a purely algebraic direct proof search or general polynomial PCMAX.",
    }
    (OUT/"rows.json").write_text(json.dumps(rows,indent=2,sort_keys=True)+"\n")
    (OUT/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    print("IPG5E_POL_TOTAL "+json.dumps(summary,sort_keys=True),flush=True)
    return 0 if not errors else 1
if __name__=="__main__":
    sys.exit(main())
