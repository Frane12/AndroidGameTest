#!/usr/bin/env python3
"""LTM6 proof-first, paired one-core E2E benchmark.

Three arms share the same native A36_75 CDCL policy:
BASE = no structural bridge; LTM5 = certified pre-solve binary clauses;
LTM6 = certified structure gate + live native GF2 CDCL.
Original model checked externally. UNSAT not credited without LRAT.
A compact structural evidence journal is saved, never used as a trained policy
or as a mathematical justification for adding clauses.
This offline-reproducible cohort contains only generated formulas, NOT SATLIB.
"""
import hashlib
import json
import pathlib
import resource
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path.cwd()))
sys.path.insert(0, "research")
import drnas_atlas13_generator as G
import drnas_atlas_wide500 as W
from mi_ltm5.cdcl_bridge import write_derived

ROOT=pathlib.Path("ltm6_results")
ROOT.mkdir(exist_ok=True)
CAP=3.0
ARMS=("BASE","LTM5","LTM6")
BINARY=pathlib.Path("mre_atlas23/bin/drnas_ltm6")
SYNTH=(
    ("xor_dense_sat",40),("xor_dense_sat",41),
    ("xor_dense_sat",42),("xor_dense_sat",43),
    ("xor_dense_unsat",40),("xor_dense_unsat",41),
    ("mixed_circuit",40),("random3_sat",40),
    ("random3_sat",41),("mixed_hard",41),
)

def parse_metrics(output):
    stats={}
    graph={}
    for line in output.splitlines():
        if line.startswith("ATLAS13_TRIAL "):
            stats=dict(p.split("=",1) for p in line.split()[1:] if "=" in p)
        if line.startswith("LTM6_GRAPH "):
            graph=dict(p.split("=",1) for p in line.split()[1:] if "=" in p)
    return stats,graph

def checked_model(original,output):
    assigned={}
    for line in output.splitlines():
        if not line.startswith("v "):continue
        for token in line[2:].split():
            lit=int(token)
            if lit==0:continue
            v=abs(lit)
            if v in assigned and assigned[v]!=(lit>0):
                return False
            assigned[v]=(lit>0)
    n,clauses=W.parse_original(original)
    if any(v>n or v<1 for v in assigned):return False
    return all(any(assigned.get(abs(lit))==(lit>0) for lit in c)
               for c in clauses)

def run(case,rep,arm):
    original=case["path"]
    assert hashlib.sha256(original.read_bytes()).hexdigest()==case["sha256"]
    started=time.monotonic()
    cnf=original
    bridge={}
    if arm=="LTM5":
        cnf=ROOT / (case["sha256"]+f"-{rep}.ltm5.cnf")
        bridge=write_derived(original,cnf)
    left=CAP-(time.monotonic()-started)
    stats={};graph={};out="";rc=124
    if left>0.02:
        mode="LTM6_LIVE" if arm=="LTM6" else "A36_75"
        cmd=[str(BINARY),str(cnf),"--mode",mode,"--time",str(left),
             "--seed",str(rep+1),"--policy","1.0,0.85"]
        def limits():
            resource.setrlimit(resource.RLIMIT_CPU,(6,7))
            resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
        try:
            proc=subprocess.run(cmd,text=True,capture_output=True,timeout=left+0.08,
                                preexec_fn=limits)
            rc,out=proc.returncode,proc.stdout
            if rc not in (0,10,20):
                raise RuntimeError(f"native exit {rc} {proc.stderr[-400:]}")
        except subprocess.TimeoutExpired:
            rc=124
    if rc==10 and not checked_model(original.read_bytes(),out):
        raise RuntimeError("INVALID ORIGINAL-CNF SAT WITNESS for "+case["sha256"])
    status={10:"SAT_VERIFIED",20:"UNSAT_UNVERIFIED"}.get(rc,"UNKNOWN")
    stats,graph=parse_metrics(out)
    elapsed=min(CAP,round(time.monotonic()-started,6))
    if arm=="LTM6" and "enabled" not in graph and rc!=124:
        raise RuntimeError("Missing LTM6 native structural gate instrumentation")
    def stat(k):
        return int(float(stats.get(k,0)))
    return dict(
        arm=arm,rep=rep,sha256=case["sha256"],family=case["family"],
        index=case["index"],status=status,e2e_s=elapsed,
        PAR2_verified_s=elapsed if status=="SAT_VERIFIED" else 2*CAP,
        PAR2_reported_s=elapsed if status!="UNKNOWN" else 2*CAP,
        original_SAT_verified=status=="SAT_VERIFIED",
        independent_UNSAT_verified=False,
        conflicts=stat("conflicts"),decisions=stat("decisions"),
        watch_visits=stat("watch_visits"),maxrss_kb=stat("atlas16_maxrss_kb"),
        ltm5_added=bridge.get("added",0),
        source_rows=stat("ltm6_source_rows"),
        short_pairs=stat("ltm6_short_pairs"),
        live_enabled=stat("ltm6_gate"),
        live_xor_checks=stat("ltm6_live_checks"),
        live_xor_implications=stat("ltm6_live_implications"),
        live_xor_conflicts=stat("ltm6_live_conflicts"),
        live_reason_clauses=stat("ltm6_reason_clauses"),
        live_derived_implications=stat("ltm6_derived_implications"),
        live_budget_off=stat("ltm6_budget_off"),
        graph=graph,bridge_gate=bridge.get("gate","baseline"),
    )

cases=[]
for category,index in SYNTH:
    n,clauses,_=G.build(category,index)
    raw=W.canonical(n,clauses)
    cases.append((category,index,raw,"ATLAS13 deterministic generator"))
# OFFLINE FIX: exclude remote SATLIB archive fetch from the required smoke cohort.
# Every source is deterministic, reproducible, and SHA-checked. The two
# additional control formulas are generated independently of any remote CDN.
# Do NOT report this synthetic cohort as an independent SATLIB benchmark.
assert len(cases)==10
assert len(set(hashlib.sha256(c[2]).hexdigest() for c in cases))==10

sources=[]
for family,index,raw,provenance in cases:
    sha=hashlib.sha256(raw).hexdigest()
    path=ROOT/(sha+".cnf")
    path.write_bytes(raw)
    sources.append(dict(family=family,index=index,path=path,sha256=sha,
                        provenance=provenance))
print("LTM6_MANIFEST "+json.dumps(dict(cases=len(sources),reps=2,arms=ARMS,
      trials=len(sources)*2*len(ARMS),cap_s=CAP,one_cpu=True,
      corpus_type='deterministic_synthetic_only',external_downloads=0,
      original_source_sha256=[x["sha256"] for x in sources])),flush=True)

rows=[]
for case in sources:
    for rep in range(2):
        statuses=set()
        for arm in ARMS:
            r=run(case,rep,arm)
            rows.append(r)
            statuses.add(r["status"])
            print("LTM6_NATIVE_TRIAL "+json.dumps(r,sort_keys=True),flush=True)
        if {"SAT_VERIFIED","UNSAT_UNVERIFIED"} <= statuses:
            raise RuntimeError("SAT-vs-UNSAT contradiction; audit refused")
summary={}
for arm in ARMS:
    subset=[r for r in rows if r["arm"]==arm]
    summary[arm]=dict(
        trials=len(subset),
        SAT_verified=sum(r["status"]=="SAT_VERIFIED" for r in subset),
        UNSAT_unverified=sum(r["status"]=="UNSAT_UNVERIFIED" for r in subset),
        UNKNOWN=sum(r["status"]=="UNKNOWN" for r in subset),
        PAR2_verified_s=round(sum(r["PAR2_verified_s"] for r in subset),6),
        PAR2_reported_s=round(sum(r["PAR2_reported_s"] for r in subset),6),
        E2E_s=round(sum(r["e2e_s"] for r in subset),6),
        conflicts=sum(r["conflicts"] for r in subset),
        ltm5_added=sum(r["ltm5_added"] for r in subset),
        live_enabled=sum(r["live_enabled"] for r in subset),
        live_xor_checks=sum(r["live_xor_checks"] for r in subset),
        live_xor_implications=sum(r["live_xor_implications"] for r in subset),
        live_xor_conflicts=sum(r["live_xor_conflicts"] for r in subset),
        live_reason_clauses=sum(r["live_reason_clauses"] for r in subset),
        live_derived_implications=sum(r["live_derived_implications"] for r in subset),
    )
summary["speedup_verified_BASE_over_LTM6"]=round(
    summary["BASE"]["PAR2_verified_s"]/max(.000001,summary["LTM6"]["PAR2_verified_s"]),6)
summary["speedup_reported_BASE_over_LTM6"]=round(
    summary["BASE"]["PAR2_reported_s"]/max(.000001,summary["LTM6"]["PAR2_reported_s"]),6)
# Evidence journal: raw per-source structural characteristics and paired
# measured gains. Not a certified cross-formula inference rule or live policy.
memory=[]
for case in sources:
    subset=[r for r in rows if r["sha256"]==case["sha256"]]
    selected=[r for r in subset if r["arm"]=="LTM6"]
    by_arm={arm:sum(r["PAR2_verified_s"] for r in subset if r["arm"]==arm)
            for arm in ARMS}
    memory.append(dict(
        sha256=case["sha256"],family=case["family"],index=case["index"],
        source_rows=max(r["source_rows"] for r in selected),
        short_pairs=max(r["short_pairs"] for r in selected),
        gate_fired=any(r["live_enabled"] for r in selected),
        confirmed_implications=sum(r["live_xor_implications"] for r in selected),
        measured_PAR2_verified=by_arm,
        best_observed_arm=min(ARMS,key=lambda a:by_arm[a]),
        valid_as_global_clause_proof=False,
        evaluated_only_not_deployed=True,
    ))
(ROOT/"results.json").write_text(json.dumps(dict(summary=summary,rows=rows),indent=2))
(ROOT/"structural_memory.json").write_text(json.dumps(memory,indent=2))
print("LTM6_NATIVE_FINAL "+json.dumps(summary,sort_keys=True),flush=True)
print("LTM6_NATIVE_AUDIT_PASS source_SHA=true paired=true one_cpu=true native_live_trail_GF2=true original_SAT_verified=true UNSAT_certified=false memory_is_evidence_only=true",flush=True)
