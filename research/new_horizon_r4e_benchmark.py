#!/usr/bin/env python3
"""New Horizon R4e, frozen-source SHA paired five-arm experiment.

80 unchanged R4d original generated sources + 24 new adversarial mid-clause
control sources, 4 repetitions * 5 policies = 2080 attempts. NOT external blind.
"""
from __future__ import annotations
import argparse
import collections
import csv
import hashlib
import json
import pathlib
import random

import new_horizon_r4e as r4e
import new_horizon_r4d as r4d

ROOT=pathlib.Path("new_horizon_r4e")
FROZEN=ROOT/"frozen"
ORIGINAL=ROOT/"source/new_horizon_r4d/frozen"
OLD_SHA="7d7cd512a801ef3102141ad92e68c09275599ae9e4ebfeacc0855d104d358a47"
PROTO="DRNAS_NH_R4E_104x4x5_SHA_PAIRED_v1"
POLICIES=("clean","pure_only","r4d","r4e_mid","r4e_tri")
REPS=4
SHARDS=4
ADVERSARIAL_PER_FAMILY=12
ORIGINAL_COUNT=80
TOTAL=ORIGINAL_COUNT+2*ADVERSARIAL_PER_FAMILY

def need(ok, message):
    if not ok:
        raise AssertionError("NH_R4E_AUDIT_FAIL_CLOSED: "+str(message))

def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()

def read(path):
    return json.loads(pathlib.Path(path).read_text())

def save(path, payload):
    path=pathlib.Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n")

def dimacs(n, clauses):
    return f"p cnf {n} {len(clauses)}\n"+"".join(
        " ".join(map(str,c))+" 0\n" for c in clauses)

def control(family, i):
    n=124+i
    c=[(1,)]+[(-k,k+1) for k in range(1,n)]
    if family=="middle_sparse":
        # One true but non-binary clause amid a long 2SAT-looking source.
        c.insert(len(c)//2,(1,2,3))
    elif family=="middle_dense":
        # More redundant binary clauses; still false source-wide 2SAT.
        c=c+[(1,-j) for j in range(2,n)]+[(j,-j) for j in range(2,n)]
        # (1,-j) is SAT with all vars false except 1? No! The chain forces
        # all vars true. Replace with guaranteed true binary implications.
        c=[(1,)]+[(-k,k+1) for k in range(1,n)]
        c += [(-k,k+1) for k in range(1,n)] * 2
        c.insert(len(c)//2,(1,2,3))
    else:
        raise ValueError(family)
    return n,c,"SAT"

def selftest():
    r4e.selftest()
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        p=pathlib.Path(td)
        for family in ("middle_sparse","middle_dense"):
            for i in range(ADVERSARIAL_PER_FAMILY):
                n,c,expected=control(family,i)
                need(not r4d.r2.is_2cnf(c),"control accidentally true 2SAT")
                f=p/f"{family}-{i}.cnf"
                f.write_text(dimacs(n,c))
                for mode in ("mid","tri"):
                    ev=r4e.source_evidence(f,policy=mode)
                    need(ev["route"]=="clean","mixed original wrongly accepted")
    print("NH_R4E_BENCH_SELFTEST_PASS",flush=True)

def freeze():
    need(sha(ORIGINAL/"manifest.json")==OLD_SHA,"R4d old SHA changed")
    m=read(ORIGINAL/"manifest.json")
    need(len(m["cases"])==ORIGINAL_COUNT,"R4d source count")
    FROZEN.mkdir(parents=True,exist_ok=True)
    cases=[]
    for prior in m["cases"]:
        old=ORIGINAL/(prior["id"]+".cnf")
        need(sha(old)==prior["sha256"],"R4d original CNF drift")
        cid="unchanged-"+prior["id"]
        dest=FROZEN/(cid+".cnf")
        dest.write_bytes(old.read_bytes())
        cases.append(dict(id=cid,sha256=sha(dest),family=prior["family"],
            cap_s=prior["cap_s"],expected=prior["expected"],
            original_sha256=prior["sha256"]))
    for family in ("middle_sparse","middle_dense"):
        for i in range(ADVERSARIAL_PER_FAMILY):
            n,cs,expected=control(family,i)
            cid=f"new-{family}-{i}"
            dest=FROZEN/(cid+".cnf")
            dest.write_text(dimacs(n,cs))
            cases.append(dict(id=cid,sha256=sha(dest),family=family,
                cap_s=3.0,expected=expected))
    need(len(cases)==TOTAL and len({c["sha256"] for c in cases})==TOTAL,
         "invalid source set")
    random.Random(PROTO).shuffle(cases)
    save(FROZEN/"manifest.json",dict(protocol=PROTO,cases=cases,
        original_manifest_sha256=OLD_SHA,external_blind=False,
        same_native_binary=True,policies=POLICIES,repetitions=REPS))
    verify()
    print("NH_R4E_FREEZE_PASS",json.dumps(dict(sources=TOTAL,
          manifest_sha256=sha(FROZEN/"manifest.json"))),flush=True)

def verify():
    m=read(FROZEN/"manifest.json")
    need(m["protocol"]==PROTO and len(m["cases"])==TOTAL,
         "frozen manifest not right")
    for c in m["cases"]:
        need(sha(FROZEN/(c["id"]+".cnf"))==c["sha256"],
             "original formula hash drift")
    return m["cases"]

def trial(c,mode,rep,binary):
    p=FROZEN/(c["id"]+".cnf")
    need(sha(p)==c["sha256"],"changed source before solve")
    out=r4e.run_one(p,binary,c["cap_s"],mode,
        ROOT/"scratch"/(c["sha256"][:16]+f"-{mode}-{rep}"))
    status=out["status"]
    need(status in ("SAT","UNSAT","TIMEOUT"),"solver invalid status")
    if status!="TIMEOUT":
        need(status==c["expected"],"SAT/UNSAT disagrees with source")
    evidence=(out.get("r4e_evidence") or out.get("r4d_evidence") or {})
    t=round(out["elapsed"],6)
    return dict(id=c["id"],sha256=c["sha256"],family=c["family"],
        mode=mode,rep=rep,status=status,elapsed_s=t,
        par2_s=round(2*c["cap_s"] if status=="TIMEOUT" else t,6),
        cap_s=c["cap_s"],route=out["route"],proof=out["proof"],
        reason=out["reason"],scan_s=round(evidence.get("scan_s",0),6),
        scanned=evidence.get("scanned"),
        sample_windows=evidence.get("sample_windows",0))

def shard(idx,binary):
    cases=verify()
    need(0<=idx<SHARDS and pathlib.Path(binary).is_file(),"missing native or shard")
    results=[]
    for c in cases[idx::SHARDS]:
        for rep in range(REPS):
            modes=list(POLICIES)
            random.Random(PROTO+c["sha256"]+str(rep)).shuffle(modes)
            for mode in modes:
                r=trial(c,mode,rep,binary)
                results.append(r)
                save(ROOT/f"shard-{idx}.json",results)
                print("NH_R4E_TRIAL",json.dumps({k:r[k] for k in
                      ("id","mode","status","elapsed_s","route","sample_windows")}),
                      flush=True)
    need(len(results)==len(cases[idx::SHARDS])*REPS*len(POLICIES),
         "incomplete shard")
    print("NH_R4E_SHARD_PASS",idx,len(results),flush=True)

def audit():
    cases=verify()
    source={c["sha256"]:c for c in cases}
    data=[]
    for i in range(SHARDS):
        rows=read(ROOT/f"shard-{i}.json")
        need(len(rows)==len(cases[i::SHARDS])*REPS*len(POLICIES),
             "missing source/arm in shard")
        data+=rows
    need(len(data)==TOTAL*REPS*len(POLICIES),"wrong attempt count")
    paired=collections.defaultdict(list)
    for r in data:
        c=source.get(r["sha256"])
        need(c and c["id"]==r["id"],"source hash mismatch")
        expected=2*r["cap_s"] if r["status"]=="TIMEOUT" else r["elapsed_s"]
        need(abs(r["par2_s"]-expected)<.00001,"bad PAR2")
        paired[r["sha256"],r["rep"]].append(r)
    for c in cases:
        for rep in range(REPS):
            rows=paired[c["sha256"],rep]
            need(len(rows)==len(POLICIES) and
                 {r["mode"] for r in rows}==set(POLICIES),
                 "missing paired arm")
            need(len({r["status"] for r in rows if r["status"]!="TIMEOUT"})<=1,
                 "contradictory solver status")
    groups={"all":cases}
    for fam in sorted({c["family"] for c in cases}):
        groups[fam]=[c for c in cases if c["family"]==fam]
    summary={}
    for name,group in groups.items():
        h={c["sha256"] for c in group}
        summary[name]={}
        for mode in POLICIES:
            v=[r for r in data if r["sha256"] in h and r["mode"]==mode]
            summary[name][mode]=dict(attempts=len(v),
                solved=sum(r["status"]!="TIMEOUT" for r in v),
                par2_s=round(sum(r["par2_s"] for r in v),6),
                elapsed_s=round(sum(r["elapsed_s"] for r in v),6),
                scan_s=round(sum(r["scan_s"] for r in v),6),
                routes=dict(collections.Counter(r["route"] for r in v)),
                negative_middle=sum(r["reason"]=="middle_complete_long_clause_veto"
                                    for r in v),
                zero_clause_abstentions=sum(r["scanned"]==0 for r in v))
    result=dict(protocol=PROTO,status="COMPLETE_NOT_EXTERNAL_BLIND",
      original_sources=ORIGINAL_COUNT,new_controls=TOTAL-ORIGINAL_COUNT,
      cases=TOTAL,attempts=len(data),frozen_manifest_sha=sha(FROZEN/"manifest.json"),
      all_arms_exact_same_source=True,SAT_witnesses_checked=True,
      native_UNSAT_independent_LRAT_absent=True,
      microseconds_timing_noise=True,summary=summary)
    save(ROOT/"report.json",result)
    save(ROOT/"trials.json",data)
    with (ROOT/"trials.csv").open("w",newline="") as fd:
        w=csv.DictWriter(fd,fieldnames=list(data[0]))
        w.writeheader()
        w.writerows(data)
    md=["# DRNAS New Horizon R4e — middle-window negative-witness experiment","",
        f"{TOTAL} frozen formulas x {REPS} repetitions x {len(POLICIES)} arms = {len(data)} paired attempts.",
        "Known generator families; 80 reused R4d sources + 24 new controls. NOT external blind.","",
        "| Cohort | Mode | Solved | PAR2 seconds | Scan seconds | Middle vetoes |",
        "|---|---|---:|---:|---:|---:|"]
    for g,modes in summary.items():
        for mode,v in modes.items():
            md.append(f"| {g} | {mode} | {v['solved']}/{v['attempts']} | "+
                      f"{v['par2_s']} | {v['scan_s']} | {v['negative_middle']} |")
    md+=["","Veto is only a negative cost observation. No approximate SAT or UNSAT.",
         "Original SAT models checked; independent native UNSAT LRAT not present.",
         "No general speedup claim from small process-level timing."]
    (ROOT/"summary.md").write_text("\n".join(md)+"\n")
    print("NH_R4E_FINAL",json.dumps(summary,sort_keys=True),flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("cmd",choices=("selftest","freeze","verify","shard","audit"))
    ap.add_argument("--shard",type=int,default=0)
    ap.add_argument("--binary",default="new_horizon_r4e/r190-driver")
    a=ap.parse_args()
    if a.cmd=="selftest":
        selftest()
    elif a.cmd=="freeze":
        freeze()
    elif a.cmd=="verify":
        print("NH_R4E_VERIFY_PASS",len(verify()),flush=True)
    elif a.cmd=="shard":
        shard(a.shard,pathlib.Path(a.binary))
    else:
        audit()
