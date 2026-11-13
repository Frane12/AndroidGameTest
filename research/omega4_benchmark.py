#!/usr/bin/env python3
"""MATH Ω4 initial live-trail, proof-safe matched development pilot.

1 identical CaDiCaL binary; modes: clean, shadow, live.
XOR3 source rows independently re-extracted from original unchanged CNF.
Synthetic fixtures demonstrate 3-row implication/conflict and near-SAT controls.
40 previously seen external formulas: source-structure-only selection, NOT blind.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import statistics
import collections
import itertools
import random
import argparse

ROOT=Path("mre_omega4")
BINARY=ROOT/"bin/omega4_bridge"
EXPORT=ROOT/"bin/omega4_rows"
CAP=3.0
ARMS=("clean","shadow","live")

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write_json(path, obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,sort_keys=True,indent=2)+"\n")

def parse_cnf(raw):
    n=m=None
    clauses=[];pending=[]
    for line in raw.decode("ascii").splitlines():
        ls=line.strip()
        if not ls or ls.startswith("c"):continue
        if ls.startswith("%"):break
        if ls.startswith("p "):
            p=ls.split()
            if len(p)!=4 or p[1]!="cnf" or n is not None:raise ValueError("Bad CNF header")
            n,m=map(int,p[2:]);continue
        if n is None:raise ValueError("Missing header")
        for value in ls.split():
            v=int(value)
            if abs(v)>n:raise ValueError("Out of range")
            if v:pending.append(v)
            else:clauses.append(tuple(pending));pending.clear()
    if n is None or pending or m!=len(clauses):raise ValueError("Incomplete original")
    return n,clauses

def sat_model_check(raw, stdout):
    n, clauses=parse_cnf(raw); vals={}
    for line in stdout.splitlines():
        if not line.startswith("v "):continue
        for v in map(int,line[2:].split()):
            if v:
                if abs(v)>n or (abs(v) in vals and vals[abs(v)]!=(v>0)):
                    raise ValueError("Inconsistent or out of range SAT model")
                vals[abs(v)]=v>0
    if not vals:raise ValueError("No model")
    for clause in clauses:
        if not any(vals.get(abs(v),False)==(v>0) for v in clause):
            raise ValueError("Model does not satisfy original")
    return True

def xor_cnf(rows,n=None,extra=()):
    if n is None:n=max(max(vs) for vs,_ in rows)
    clauses=[]
    for vs,rhs in rows:
        for mask in range(1<<len(vs)):
            if mask.bit_count()%2 == rhs:continue
            clauses.append([(-v if mask>>i&1 else v) for i,v in enumerate(vs)])
    clauses.extend([[x] for x in extra])
    return ("p cnf %d %d\n"%(n,len(clauses))+
        "".join(" ".join(map(str,c))+" 0\n" for c in clauses)).encode("ascii")

def independent_synthetic_check(raw, expected):
    n,clauses=parse_cnf(raw)
    if n>16:raise ValueError("synthetic oracle size")
    count=0
    for bits in itertools.product([False,True],repeat=n):
        if all(any(bits[abs(v)-1]==(v>0) for v in c) for c in clauses):count+=1
    if (count>0)!= (expected=="SAT"):
        raise ValueError("Wrong fixture truth label")
    return count

def fixtures(root):
    vs=[([1,2,3],0),([2,4,5],0),([3,4,6],0)]
    # The 3-row XOR yields x1 XOR x5 XOR x6 = 0, but no 1- or 2-row
    # source equation suffices to deduce x1 from x5, x6 alone.
    cases=[
       ("3way_sat",xor_cnf(vs,n=6,extra=[5,-6]),"SAT"),
       ("3way_unsat",xor_cnf(vs,n=6,extra=[-1,5,-6]),"UNSAT"),
       ("3way_nearmiss_sat",xor_cnf(vs,n=6,extra=[1,5,-6]),"SAT"),
       ("3way_allfree",xor_cnf(vs,n=6),"SAT")
    ]
    result=[]
    for name,raw,expected in cases:
        independent_synthetic_check(raw,expected)
        path=root/(name+".cnf")
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        result.append(dict(group="synthetic",name=name,path=str(path),sha256=sha(path),
                           expected=expected))
    return result

def external_frozen():
    manifest=Path("mre_xorabc2/manifest.json")
    m=json.loads(manifest.read_text())
    cases=m["cases"]
    assert len(cases)==40 and len({c["sha256"] for c in cases})==40
    roots=[Path(v) for v in ("mre_search5/cases","mre_search6/cases","mre_equiv9/cases")]
    lookup={}
    for root in roots:
        for p in root.glob("*.cnf"):
            lookup.setdefault(sha(p),p)
    result=[]
    for c in cases:
        path=lookup.get(c["sha256"])
        if path is None:raise RuntimeError("Missing original frozen CNF "+c["sha256"])
        if path.stat().st_size!=c["bytes"]:
            raise RuntimeError("Original source byte count drift "+c["sha256"])
        result.append(dict(group="historical_external",name=c.get("gbd",c["sha256"][:12]),
             path=str(path),sha256=c["sha256"],family=c.get("source_cohort","unknown"),
             expected="UNKNOWN"))
    return result

def export(path,tsv):
    start=time.perf_counter()
    p=subprocess.run([str(EXPORT.resolve()),"export",str(Path(path).resolve()),
         str(tsv.resolve())],capture_output=True,text=True,timeout=5)
    duration=time.perf_counter()-start
    if p.returncode!=0:raise RuntimeError("Source-only extractor failed "+p.stderr[-1000:])
    matches=[l.removeprefix("XORABC3_EXPORT ") for l in p.stdout.splitlines()
             if l.startswith("XORABC3_EXPORT ")]
    if len(matches)!=1:raise RuntimeError("No independently verified export")
    data=json.loads(matches[0])
    if data["verified"] is not True or data["rows"]>32 or data["selector"]!="source_frequency_only":
        raise RuntimeError("Unsound source selector")
    return duration,data

def run_arm(c,arm,tsv,prepass_s,cap):
    start=time.perf_counter()
    budget=cap-(prepass_s if arm!="clean" else 0)
    if budget<=0.25:
        return dict(status="TIMEOUT",e2e_s=cap,par2_reported=2*cap,
                    par2_verified=2*cap,reason="certification overhead exhausted cap")
    try:
        run=subprocess.run([str(BINARY.resolve()),arm,str(Path(c["path"]).resolve()),
             str(tsv.resolve()),str(max(.05,budget-.03))],
             capture_output=True,text=True,timeout=max(.1,budget-.01))
    except subprocess.TimeoutExpired:
        return dict(status="TIMEOUT",e2e_s=cap,par2_reported=2*cap,
                    par2_verified=2*cap,reason="runner timeout")
    elapsed=time.perf_counter()-start + (prepass_s if arm!="clean" else 0)
    statuses={"SAT","UNSAT","UNKNOWN"}
    found=[l for l in run.stdout.splitlines() if l.startswith("OMEGA4_RESULT ")]
    if run.returncode not in (0,10,20) or len(found)!=1:
        raise RuntimeError("Native proof safety / execution error "+
                           run.stderr[-1600:]+" stdout="+run.stdout[-300:])
    row=dict(re.findall(r"([a-z0-9_]+)=([^\s]+)",found[0]))
    status=row.get("status")
    if status not in statuses:raise RuntimeError("Unknown native status "+str(status))
    if status=="SAT":sat_model_check(Path(c["path"]).read_bytes(),run.stdout)
    if status in ("SAT","UNSAT") and elapsed>=cap:
        status="TIMEOUT"
    reported=status in ("SAT","UNSAT")
    verified=status=="SAT" # UNSAT needs independent original-CNF LRAT.
    score=(elapsed if reported else 2*cap)
    return dict(status=status,raw_status=row.get("status"),e2e_s=round(elapsed,6),
       par2_reported=round(score,6),par2_verified=round(elapsed if verified else 2*cap,6),
       model_original_checked=bool(verified),unsat_proof_independent=False,
       telemetry={k:int(v) for k,v in row.items() if k not in ("mode","status","solve_s")},
       native_s=float(row["solve_s"]),source_prepass_s=round(prepass_s,6) if arm!="clean" else 0)

def pilot(cap=CAP):
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    ROOT.mkdir(exist_ok=True);(ROOT/"cases").mkdir(exist_ok=True)
    cands=fixtures(ROOT/"cases")+external_frozen()
    with tempfile.TemporaryDirectory(dir=ROOT) as tdir:
        tmp=Path(tdir)
        prepared=[]
        for i,c in enumerate(cands):
            rowfile=tmp/(str(i)+".tsv")
            sec,proof=export(c["path"],rowfile)
            prepared.append((c,rowfile,sec,proof))
        # Deterministic, source-only selection, no solver result information:
        # 8 XOR-bearing and 8 XOR-absent original external sources.
        matches=[x for x in prepared if x[0]["group"]=="historical_external" and x[3]["rows"]>0]
        controls=[x for x in prepared if x[0]["group"]=="historical_external" and x[3]["rows"]==0]
        matches=sorted(matches,key=lambda x:x[0]["sha256"])[:8]
        controls=sorted(controls,key=lambda x:x[0]["sha256"])[:8]
        selected=prepared[:4]+matches+controls
        if len(selected)<7:raise RuntimeError("Too few external source cases")
        records=[]
        for c,tsv,sec,proof in selected:
            entry={k:v for k,v in c.items() if k!="path"}
            entry["source_rows"]=proof["rows"];entry["source_equations"]=proof["equations"]
            entry["row_sha256"]=sha(tsv)
            entry["arms"]={}
            for arm in ARMS:
                result=run_arm(c,arm,tsv,sec,cap)
                entry["arms"][arm]=result
            vals={r["status"] for r in entry["arms"].values() if r["status"]!="TIMEOUT" and r["status"]!="UNKNOWN"}
            if len(vals)>1:raise RuntimeError("SAT/UNSAT disagreement "+entry["sha256"])
            if c["group"]=="synthetic" and "TIMEOUT" not in vals and vals and vals!={c["expected"]}:
                raise RuntimeError("Synthetic oracle disagreement")
            records.append(entry)
            write_json(ROOT/"pilot.json",records)
            print("OMEGA4_TRIAL "+json.dumps(dict(group=entry["group"],name=entry["name"],
                 source_rows=entry["source_rows"],
                 arms={a:dict(status=entry["arms"][a]["status"],
                   e2e_s=entry["arms"][a]["e2e_s"],
                   units=entry["arms"][a].get("telemetry",{}).get("unit_proposals",0),
                   conflicts=entry["arms"][a].get("telemetry",{}).get("conflict_clauses",0))
                    for a in ARMS}),sort_keys=True),flush=True)
        def aggregate(group):
            selected=[x for x in records if x["group"]==group]
            return dict(count=len(selected),
             statuses={a:dict(collections.Counter(x["arms"][a]["status"] for x in selected)) for a in ARMS},
             PAR2_reported_s={a:round(sum(x["arms"][a]["par2_reported"] for x in selected),6) for a in ARMS},
             PAR2_verified_s={a:round(sum(x["arms"][a]["par2_verified"] for x in selected),6) for a in ARMS},
             source_rows=sum(x["source_rows"] for x in selected),
             units={a:sum(x["arms"][a].get("telemetry",{}).get("unit_proposals",0) for x in selected)
                   for a in ARMS},
             completed_reasons={a:sum(x["arms"][a].get("telemetry",{}).get("completed_reasons",0) for x in selected)
                   for a in ARMS})
        report=dict(protocol="OMEGA4_SOURCE_CERT_LIVE_1CPU_DEVELOPMENT_PILOT",
            sha256_cpp=sha("research/omega4_live_gf2.cpp"),
            sha256_bridge=sha(BINARY),sha256_exporter=sha(EXPORT),
            frozen_source_manifest_sha256=sha("mre_xorabc2/manifest.json"),
            source_cohort="historical previously seen 40, selection by original certified XOR presence",
            native_experiment_type="CaDiCaL 2.1.0 IPASIR-UP actual CDCL trail",
            one_logical_CPU=True,cap_e2e_s=cap,
            sources=len(records),synthetic=aggregate("synthetic"),
            historical_external=aggregate("historical_external"),
            no_independent_original_UNSAT_LRAT=True,
            findings="Live online Gauss-Jordan with real trail vs matched shadow; no claims of SAT novelty.")
        write_json(ROOT/"report.json",report)
        print("OMEGA4_FINAL "+json.dumps(report,sort_keys=True),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--cap",type=float,default=CAP)
    a=p.parse_args()
    pilot(a.cap)
