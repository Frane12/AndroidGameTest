#!/usr/bin/env python3
"""DRNAS R201 mechanistic CMS incremental certified partial-XOR pilot.

Pre-exposed R194 CNFs, NOT blind test and NOT intrasearch CDCL callbacks.
Four modes: CMS plain, shadow stage, staged source-certified XOR, static XOR.
Each derived row is exactly a 2-source XOR, checked against original CNF
parity clauses by independent bounded truth-table reconstruction. No LRAT.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import itertools
import json
import pathlib
import random
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import r164_pure_exact_gf2 as exact
import r166x_certified_gauss as gf

ROOT=pathlib.Path("r201")
PROTO="DRNAS-R201-CMS-INCREMENTAL-2ROW-SOURCE-VERIFIED-PILOT-v1"
CAP=5.0
REPS=2
MODES=("plain","shadow","stage","static")
FAMILIES=("complete_xor","xor_plus_units","mixed_residual","nonxor_control")
MAX_SOURCE=96
MAX_DERIVED=16
FIRST_CONFLICTS=32

def need(cond,msg):
    if not cond:raise RuntimeError("R201_FAIL_CLOSED "+str(msg))

def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def save(path,info):
    path=pathlib.Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(info,indent=2,sort_keys=True)+"\n")

def vars_mask(vs):
    mask=0
    for v in vs:
        need(v>=1 and not(mask>>(v-1)&1),"invalid XOR row variables")
        mask|=1<<(v-1)
    return mask

def bits(mask):
    out=[]
    while mask:
        q=mask & -mask
        out.append(q.bit_length())
        mask^=q
    return tuple(out)

def independently_verify_source(clauses,vs,rhs):
    """Check each forbidden XOR assignment has its entire falsifying CNF clause."""
    vs=tuple(vs)
    existing={tuple(sorted(c,key=abs)) for c in clauses if len(c)==len(vs)}
    for assignment in itertools.product((0,1),repeat=len(vs)):
        if (sum(assignment)&1)==rhs:
            continue
        clause=tuple(sorted((-v if a else v for v,a in zip(vs,assignment)),key=abs))
        if clause not in existing:return False
    return True

def source_candidates(clauses):
    eq,_,_=gf.source_equations(clauses)
    unique={}
    for vs,rhs in eq:
        if 2<=len(vs)<=6:
            vs=tuple(vs)
            if independently_verify_source(clauses,vs,rhs):
                unique[(vs,rhs)]=None
    return sorted(unique,key=lambda t:(len(t[0]),t[0],t[1]))

def export(source,outstem):
    start=time.perf_counter()
    source=pathlib.Path(source)
    n,clauses=exact.parse_dimacs(source)
    verified=source_candidates(clauses)
    selected=verified[:MAX_SOURCE]
    originals={(vars_mask(vs),rhs) for vs,rhs in verified}
    proposed={}
    for i,(va,ra) in enumerate(selected):
        aa=vars_mask(va)
        for j in range(i+1,len(selected)):
            vb,rb=selected[j]
            bb=vars_mask(vb)
            if not(aa&bb):continue
            cc=aa^bb
            if not 2<=cc.bit_count()<=8 or (cc,ra^rb) in originals:continue
            proposed.setdefault((cc,ra^rb),(i,j))
    chosen=sorted(proposed,key=lambda x:(x[0].bit_count(),x[0],x[1]))[:MAX_DERIVED]
    derived=[]
    for mask,rhs in chosen:
        i,j=proposed[(mask,rhs)]
        va,ra=selected[i];vb,rb=selected[j]
        need(vars_mask(va)^vars_mask(vb)==mask and ra^rb==rhs,"XOR replay mismatch")
        need(independently_verify_source(clauses,va,ra) and
             independently_verify_source(clauses,vb,rb),"source parity not certified")
        derived.append(dict(vars=bits(mask),rhs=rhs,parents=(i,j)))
    stem=pathlib.Path(outstem);stem.parent.mkdir(parents=True,exist_ok=True)
    tsv=stem.with_suffix(".tsv")
    tsv.write_text("".join(f"{len(d['vars'])} {d['rhs']} "+
               " ".join(map(str,d["vars"]))+"\n" for d in derived))
    meta=dict(protocol=PROTO,source_sha256=sha(source),variables=n,
       source_clauses=len(clauses),source_rows_found=len(verified),
       source_rows_considered=len(selected),derived_rows=len(derived),
       derived=derived,parents=[dict(vars=vs,rhs=rhs) for vs,rhs in selected],
       rows_sha256=sha(tsv),bounded_max_derived=MAX_DERIVED)
    save(stem.with_suffix(".proof.json"),meta)
    # Perform independent replay from the immutable original source.
    replay(source,stem)
    meta["preprocess_s"]=time.perf_counter()-start
    save(stem.with_suffix(".proof.json"),meta)
    return meta

def replay(source,stem):
    stem=pathlib.Path(stem)
    cert=json.loads(stem.with_suffix(".proof.json").read_text())
    need(cert["source_sha256"]==sha(source),"source SHA drift")
    n,clauses=exact.parse_dimacs(source)
    need(cert["variables"]==n and cert["source_clauses"]==len(clauses),"CNF changed")
    parents=cert["parents"]
    for p in parents:
        need(independently_verify_source(clauses,tuple(p["vars"]),p["rhs"]),
             "parent XOR not logically implied by original CNF")
    rows=[]
    for d in cert["derived"]:
        a,b=d["parents"]
        need(a!=b and 0<=a<len(parents) and 0<=b<len(parents),"bad ancestry")
        aa,bb=parents[a],parents[b]
        need(vars_mask(aa["vars"])^vars_mask(bb["vars"])==vars_mask(d["vars"]),
             "derived XOR parity trace failure")
        need((aa["rhs"]^bb["rhs"])==d["rhs"],"derived XOR rhs failure")
        rows.append(f"{len(d['vars'])} {d['rhs']} "+" ".join(map(str,d["vars"]))+"\n")
    tsv=stem.with_suffix(".tsv")
    need(tsv.read_text()=="".join(rows) and cert["rows_sha256"]==sha(tsv),
         "TSV/proof divergence")
    return True

def fixture(folder):
    folder=pathlib.Path(folder);folder.mkdir(parents=True,exist_ok=True)
    clauses=[]
    for vs,rhs in [((1,2,3),1),((1,2,4),1)]:
        for values in itertools.product((0,1),repeat=3):
            if (sum(values)&1)==rhs:continue
            clauses.append(tuple(-v if b else v for v,b in zip(vs,values)))
    # The two rows imply x3 XOR x4 = 0. Keep mixed residual CNF.
    clauses.extend([(3,5),(-5,4)])
    source=folder/"partial_fixture.cnf"
    source.write_text(f"p cnf 5 {len(clauses)}\n"+"".join(
        " ".join(map(str,c))+" 0\n" for c in clauses))
    return source

def run_case(driver,source,mode,stem,preprocess_s,rep,cap=CAP):
    start=time.perf_counter()
    witness=pathlib.Path(str(stem)+f"-{mode}-{rep}.witness")
    available=cap-(preprocess_s if mode in ("stage","static") else 0)
    row={"protocol":PROTO,"mode":mode,"rep":rep,"source_sha256":sha(source),
         "preprocess_s":round(preprocess_s if mode in ("stage","static") else 0,6),
         "time_cap_s":cap}
    if available<=.01:
        row.update(status="TIMEOUT",elapsed_s=cap,par2_s=2*cap,
                   reason="PREPROCESS_EXCEEDED_BUDGET")
        return row
    cmd=[str(pathlib.Path(driver).resolve()),mode,str(pathlib.Path(source).resolve()),
         str(pathlib.Path(stem).with_suffix(".tsv").resolve()),str(FIRST_CONFLICTS),
         str(available),str(witness.resolve())]
    try:
        proc=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                            text=True,timeout=available+0.03,check=False)
        elapsed=time.perf_counter()-start
        lines=[l for l in proc.stdout.splitlines() if l.startswith("R201_DRIVER ")]
        need(proc.returncode==0 and len(lines)==1,
             "native driver failed: "+proc.stdout[-1500:])
        d=json.loads(lines[0][len("R201_DRIVER "):])
        row.update(d)
        row["native_elapsed_s"]=round(elapsed,6)
        status=d["status"]
        if status=="SAT":
            need(d["sat_model_original_verified"] and witness.is_file(),"no SAT model")
            n,clauses=exact.parse_dimacs(source)
            model={int(v) for v in witness.read_text().split() if v!="0"}
            need(len({abs(v) for v in model})==len(model),"contradictory witness")
            for clause in clauses:
                need(any(lit in model for lit in clause),
                     "SAT witness does not satisfy ORIGINAL source CNF")
            row["sat_witness_replayed_original"]=True
        elif status=="UNSAT":
            row["unsat_note"]="CMS_ONLY: no independent LRAT"
        elif status=="UNKNOWN":
            status="TIMEOUT"
        else:need(False,"unknown native status")
    except subprocess.TimeoutExpired:
        status="TIMEOUT"
        elapsed=available
        row["reason"]="WALL_CAP_TIMEOUT"
    row["status"]=status
    row["elapsed_s"]=round(min(cap,elapsed+row["preprocess_s"]),6)
    row["par2_s"]=round(2*cap if status=="TIMEOUT" else row["elapsed_s"],6)
    return row

def smoke(driver):
    with tempfile.TemporaryDirectory() as tmp:
        source=fixture(pathlib.Path(tmp))
        stem=pathlib.Path(tmp)/"certified"
        evidence=export(source,stem)
        need(evidence["derived_rows"]>=1,"fixture must prove a partial XOR")
        for mode in MODES:
            trial=run_case(driver,source,mode,stem,evidence["preprocess_s"],0,3.0)
            need(trial["status"]=="SAT",f"fixture {mode}: {trial}")
            print("R201_SMOKE_TRIAL",json.dumps(trial,sort_keys=True),flush=True)
        # Poison one parent; fail-closed replay must catch the alteration.
        certpath=stem.with_suffix(".proof.json")
        cert=json.loads(certpath.read_text())
        cert["parents"][0]["rhs"] ^= 1
        save(certpath,cert)
        try: replay(source,stem)
        except RuntimeError: pass
        else:need(False,"tampered XOR certificate accepted")
    print("R201_SMOKE_PASS",flush=True)

def source_for_shard(index):
    need(index in range(len(FAMILIES)),"invalid shard")
    frozen=json.loads(pathlib.Path("r189/frozen/manifest.json").read_text())
    family=FAMILIES[index]
    cases=sorted([c for c in frozen["cases"]
            if c.get("real") and c.get("family")==family],key=lambda c:c["sha256"])
    need(len(cases)>=1,"missing family "+family)
    return cases[0]

def bench(driver,index):
    case=source_for_shard(index)
    source=pathlib.Path("r189/frozen")/(case["id"]+".cnf")
    need(sha(source)==case["sha256"],"immutable original SHA mismatched")
    root=ROOT/"raw"/str(index);root.mkdir(parents=True,exist_ok=True)
    stem=root/"certified"
    evidence=export(source,stem)
    rows=[]
    for rep in range(REPS):
        modes=list(MODES)
        random.Random(PROTO+case["sha256"]+str(rep)).shuffle(modes)
        for mode in modes:
            row=run_case(driver,source,mode,stem,evidence["preprocess_s"],rep)
            row.update(case=case["id"],family=case["family"],shard=index,
                       certified_derived_available=evidence["derived_rows"])
            rows.append(row)
            print("R201_TRIAL",json.dumps(row,sort_keys=True),flush=True)
            save(ROOT/f"shard-{index}.json",{"protocol":PROTO,"source_sha256":case["sha256"],
                  "family":case["family"],"evidence":evidence,"rows":rows})
    need(len(rows)==len(MODES)*REPS,"incomplete shard")
    print("R201_SHARD_PASS",index,len(rows),flush=True)

def audit():
    rows=[]
    for i in range(len(FAMILIES)):
        p=ROOT/f"shard-{i}.json"
        d=json.loads(p.read_text())
        need(d["protocol"]==PROTO and d["family"]==FAMILIES[i],"shard provenance")
        need(len(d["rows"])==REPS*len(MODES),"incomplete paired trials")
        for r in d["rows"]:
            need(r["source_sha256"]==d["source_sha256"],"wrong source SHA")
            rows.append(r)
    need(len(rows)==len(FAMILIES)*REPS*len(MODES),"incomplete paired audit")
    sums={}
    for mode in MODES:
        rr=[r for r in rows if r["mode"]==mode]
        need(len(rr)==len(FAMILIES)*REPS,"missing solver mode")
        sums[mode]={"attempts":len(rr),"solved":sum(r["status"]!="TIMEOUT" for r in rr),
            "par2_s":round(sum(r["par2_s"] for r in rr),6),
            "SAT":sum(r["status"]=="SAT" for r in rr),
            "UNSAT_unverified":sum(r["status"]=="UNSAT" for r in rr),
            "rows_injected":sum(r.get("certified_rows_injected",0) for r in rr),
            "prep_s":round(sum(r["preprocess_s"] for r in rr),6)}
    summary={"status":"R201_PILOT_PASS","protocol":PROTO,"trials":len(rows),
         "sums":sums,"limitations":["Preexposed R194 real formulas only",
         "CMS 5.11.15 staged between solve calls, not IPASIR-UP callbacks",
         "UNSAT answers lack independent LRAT proof",
         "Results are mechanistic; no SOTA or global SAT claim"]}
    save(ROOT/"summary.json",summary)
    print("R201_FINAL",json.dumps(summary,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("smoke","bench","audit"))
    p.add_argument("--driver",default="r201/r201-stage-cms")
    p.add_argument("--shard",type=int,default=0)
    a=p.parse_args()
    {"smoke":lambda:smoke(a.driver),
     "bench":lambda:bench(a.driver,a.shard),
     "audit":audit}[a.action]()
