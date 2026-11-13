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

ROOT=Path("mre_omega42")
BINARY=ROOT/"bin/omega42_bridge"
EXPORT=ROOT/"bin/omega42_rows"
CAP=5.0
ARMS=("clean","shadow","live","gated","component_shadow","component")

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
    found=[l for l in run.stdout.splitlines() if l.startswith("OMEGA42_RESULT ")]
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
       native_s=float(row["solve_s"]),source_prepass_s=round(prepass_s,6) if arm!="clean" else 0,
       cdcl_stats=parse_cdcl_statistics(run.stdout,arm))


SHARDS=4
REPS=2

def select_sources():
    """Same 16 historical case identities as Ω4, plus four synthetic controls."""
    ROOT.mkdir(exist_ok=True)
    (ROOT/"cases").mkdir(exist_ok=True)
    cands=fixtures(ROOT/"cases")+external_frozen()
    # The selector depends ONLY on independently certified source XOR rows.
    selected=[]
    with tempfile.TemporaryDirectory(dir=ROOT) as tmpdir:
        tmp=Path(tmpdir)
        cert=[]
        for i,c in enumerate(cands):
            tsv=tmp/(str(i)+".tsv")
            secs,proof=export(c["path"],tsv)
            cert.append((c,proof))
        matches=sorted((x for x in cert if x[0]["group"]=="historical_external"
                      and x[1]["rows"]>0),key=lambda x:x[0]["sha256"])[:8]
        controls=sorted((x for x in cert if x[0]["group"]=="historical_external"
                      and x[1]["rows"]==0),key=lambda x:x[0]["sha256"])[:8]
        if len(matches)!=8 or len(controls)!=8:
            raise RuntimeError("Historical frozen candidate selector mismatch")
        selected=[c for c,p in cert[:4]+matches+controls]
    if len(selected)!=20 or len({c["sha256"] for c in selected})!=20:
        raise RuntimeError("Selection not 20 unique source SHAs")
    return selected

def parse_cdcl_statistics(output,arm):
    try:
        block=output.split("OMEGA4_STATS_BEGIN mode="+arm+"\n",1)[1]
        block=block.split("OMEGA4_STATS_END mode="+arm,1)[0]
    except (IndexError,ValueError):
        return {}
    out={}
    for key in ("conflicts","decisions","propagations","learned"):
        values=re.findall(r"(?:^|\n)\s*(?:c\s+)?"+key+r":\s+(\d+)\b",block,re.M)
        out[key]=int(values[-1]) if values else None
    return out

def benchmark(shard,cap,reps):
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    cands=select_sources()
    selected=[(i,c) for i,c in enumerate(cands) if i%SHARDS==shard]
    records=[]
    for idx,c in selected:
        if sha(c["path"])!=c["sha256"]:
            raise RuntimeError("Original SHA mutated")
        with tempfile.TemporaryDirectory(dir=ROOT) as temp:
            tsv=Path(temp)/"source-certified.tsv"
            preparation,proof=export(c["path"],tsv)
            if not proof["verified"] or proof["rows"]>32:
                raise RuntimeError("Proof exporter verification failed")
            for rep in range(reps):
                entry={k:v for k,v in c.items() if k!="path"}
                entry.update(rep=rep,shard=shard,source_rows=proof["rows"],
                             source_equations=proof["equations"],
                             source_row_sha256=sha(tsv),
                             original_sha256=sha(c["path"]),arms={})
                order=list(ARMS)
                random.Random(c["sha256"]+":Ω4.2:"+str(rep)).shuffle(order)
                for arm in order:
                    result=run_arm(c,arm,tsv,preparation,cap)
                    entry["arms"][arm]=result
                statuses={z["status"] for z in entry["arms"].values()
                          if z["status"] not in ("TIMEOUT","UNKNOWN")}
                if len(statuses)>1:
                    raise RuntimeError("SAT/UNSAT cross-mode disagreement "+entry["sha256"])
                if c["group"]=="synthetic" and statuses and statuses!={c["expected"]}:
                    raise RuntimeError("Synthetic oracle disagreement "+entry["sha256"])
                records.append(entry)
                write_json(ROOT/("shard-"+str(shard)+".json"),records)
                print("OMEGA42_TRIAL "+json.dumps({
                    "shard":shard,"rep":rep,"case":c["name"],"group":c["group"],
                    "row_count":proof["rows"],
                    "arms":{a:{"status":v["status"],"e2e_s":v["e2e_s"],
                         "reported_PAR2":v["par2_reported"],
                         "scans":v.get("telemetry",{}).get("online_scans"),
                         "comp_scans":v.get("telemetry",{}).get("component_scans"),
                         "skips":v.get("telemetry",{}).get("gated_skips"),
                         "comp_skips":v.get("telemetry",{}).get("component_skips"),
                         "comp_count":v.get("telemetry",{}).get("component_count"),
                         "proposals":v.get("telemetry",{}).get("unit_proposals"),
                         "reasons":v.get("telemetry",{}).get("completed_reasons")}
                        for a,v in entry["arms"].items()}},sort_keys=True),flush=True)
    if len(records)!=(len(selected)*reps):
        raise RuntimeError("Incomplete paired shard")
    print("OMEGA42_SHARD_PASS "+str(shard)+" "+str(len(records)),flush=True)

def aggregate(reps):
    rows=[]
    for i in range(SHARDS):
        path=ROOT/("shard-"+str(i)+".json")
        if not path.exists():raise RuntimeError("Missing shard "+str(i))
        rows+=json.loads(path.read_text())
    if len(rows)!=20*reps or len({(r["sha256"],r["rep"]) for r in rows})!=20*reps:
        raise RuntimeError("Invalid paired count, duplicates or missing records")
    for r in rows:
        if set(r["arms"])!=set(ARMS):raise RuntimeError("Arms not matched")
        for arm in ARMS:
            v=r["arms"][arm]
            if v.get("telemetry",{}).get("unsafe_claims",0):
                raise RuntimeError("Unsafe GF2 proof claim")
    def score(rr,arm):
        vals=[r["arms"][arm] for r in rr]
        numeric=("unit_proposals","completed_reasons","conflict_clauses","reason_replays",
                 "online_scans","gated_skips","scan_wall_ns","gf2_row_xors",
                 "sum_reason_width","delivered_reason_count","sum_proof_depth",
                 "checked_proof_rows","unit_candidates","conflicts_seen",
                 "component_count","component_scans","component_skips",
                 "component_memo_hits","component_dirty_events",
                 "component_heuristic_rejections","stale_proposals_discarded",
                 "checked_reason_lits")
        tele={k:sum(v.get("telemetry",{}).get(k,0) for v in vals) for k in numeric}
        tele["average_proof_depth"]=round(tele["sum_proof_depth"]/tele["checked_proof_rows"],3) if tele["checked_proof_rows"] else None
        tele["average_export_reason_width"]=round(tele["sum_reason_width"]/tele["delivered_reason_count"],3) if tele["delivered_reason_count"] else None
        tele["scan_milliseconds"]=round(tele["scan_wall_ns"]/1e6,3)
        tele["scan_ms_per_completed_reason"]=round(tele["scan_milliseconds"]/tele["completed_reasons"],4) if tele["completed_reasons"] else None
        stats={k:sum(v.get("cdcl_stats",{}).get(k) or 0 for v in vals if v.get("cdcl_stats",{}).get(k) is not None)
               for k in ("conflicts","decisions","propagations","learned")}
        coverage={k:sum(v.get("cdcl_stats",{}).get(k) is not None for v in vals) for k in stats}
        return dict(n=len(vals),statuses=dict(collections.Counter(v["status"] for v in vals)),
             PAR2_reported_s=round(sum(v["par2_reported"] for v in vals),6),
             PAR2_verified_s=round(sum(v["par2_verified"] for v in vals),6),
             wall_E2E_s=round(sum(v["e2e_s"] for v in vals),6),
             source_prepass_s=round(sum(v.get("source_prepass_s",0) for v in vals),6),
             telemetry=tele,cdcl_stats=stats,cdcl_coverage=coverage)
    group_keys=("synthetic","historical_external")
    scores={k:{arm:score([r for r in rows if r["group"]==k],arm) for arm in ARMS} for k in group_keys}
    def paired(arm,base,group):
        selected=[r for r in rows if r["group"]==group]
        diffs=[r["arms"][arm]["par2_reported"]-r["arms"][base]["par2_reported"] for r in selected]
        return dict(n=len(diffs),gain_PAR2_s=round(-sum(diffs),6),
               wins=sum(d<-.02 for d in diffs),losses=sum(d>.02 for d in diffs),
               ties=sum(abs(d)<=.02 for d in diffs))
    pairs={k:{
         "component_vs_clean":paired("component","clean",k),
         "component_vs_gated":paired("component","gated",k),
         "component_vs_component_shadow":paired("component","component_shadow",k),
         "component_shadow_vs_clean":paired("component_shadow","clean",k),
         "gated_vs_clean":paired("gated","clean",k),
         "gated_vs_live":paired("gated","live",k),
         "live_vs_shadow":paired("live","shadow",k),
         "live_vs_clean":paired("live","clean",k)
         } for k in group_keys}
    output=dict(protocol="DRNAS_MATH_OMEGA42_TRUE_CDCL_COMPONENTS_V1",
           source_cohort="Historical development SHA-locked 16 originals (8 source-XOR positive, 8 negative), 4 independently labeled synthetic controls",
           NOT_BLIND=True,ORIGINAL_UNSAT_PROOF_INDEPENDENT=False,
           one_logical_cpu=True,cap_s=CAP,shards=SHARDS,repetitions=reps,
           matched_trials=len(rows)*len(ARMS),
           known_originals=16,synthetic_controls=4,
           binary_sha256=sha(BINARY),source_sha256=sha("research/omega4_live_gf2.cpp"),
           source_manifest_sha256=sha("mre_xorabc2/manifest.json"),
           scores=scores,pairs=pairs,
           caveats="Backend UNSAT lacks independent LRAT; original-model SAT verification is mandatory; source-only cohort is historical. CaDiCaL statistics missing are missing, never zero.")
    write_json(ROOT/"report.json",output)
    print("OMEGA42_FINAL "+json.dumps(output,sort_keys=True),flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("cmd",choices=("shard","aggregate"))
    ap.add_argument("--shard",type=int,default=-1)
    ap.add_argument("--cap",type=float,default=CAP)
    ap.add_argument("--reps",type=int,default=REPS)
    args=ap.parse_args()
    if args.cmd=="shard":
        if not 0<=args.shard<SHARDS:raise ValueError("Bad shard")
        benchmark(args.shard,args.cap,args.reps)
    else: aggregate(args.reps)
