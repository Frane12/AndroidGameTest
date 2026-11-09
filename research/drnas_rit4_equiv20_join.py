#!/usr/bin/env python3
"""RIT4: SHА-locked structural-only GF2/SCC/XOR4 scan of X20 and EQUIV2 result join.

No SAT solving, no modified CNFs, no fresh performance claims. All performance
values come from the already completed, independently audited EQUIV2 E2E run.
"""
from __future__ import annotations
import argparse
import collections
import csv
import hashlib
import json
import pathlib
import subprocess
import sys

PROTO="DRNAS-RIT4-X20-GF2-SCC-XOR4-EQUIV2-CAUSAL-JOIN-v1"
PARENT=42587550843
EQUIV2=42608986438
CAP=12.0
ARMS=("cadical_default","cadical3_default","cadical3_no_scc",
      "cadical3_scc1","cadical3_scc4","cadical3_no_equiv_gates",
      "native1","kissat1")
SHARDS=2

def fail_if(b,msg):
    if b:raise RuntimeError("RIT4_FAIL_CLOSED "+str(msg))

def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        for block in iter(lambda:f.read(1<<20),b""):h.update(block)
    return h.hexdigest()

def manifest(path):
    m=json.loads(pathlib.Path(path).read_text())
    cases=m["cases"]
    fail_if(len(cases)!=24 or len({c["sha256"] for c in cases})!=24,
            "expected exactly 24 unique frozen X20 SHA")
    for c in cases:
        fail_if(not all(k in c for k in ("filename","sha256","gbd","year")),
                "source metadata incomplete")
        fail_if(pathlib.PurePath(c["filename"]).name!=c["filename"],
                "unsafe filename")
    return cases

def scan_one(case,root):
    original=pathlib.Path(root)/case["filename"]
    fail_if(not original.is_file() or sha(original)!=case["sha256"],
            "missing or changed original SHA "+case["sha256"])
    cmd=[sys.executable,"research/drnas_rit3_original_sha_screen.py","case",
         "--source",str(original),"--sha",case["sha256"],
         "--gbd",case["gbd"],"--year",str(case["year"])]
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=11)
        fail_if(p.returncode!=0,"RIT3 subprocess failed "+p.stderr[-400:])
        a=[x.split(" ",1)[1] for x in p.stdout.splitlines()
           if x.startswith("RIT3_CASE ")]
        fail_if(len(a)!=1,"missing RIT3_CASE diagnostic")
        row=json.loads(a[0])
    except subprocess.TimeoutExpired:
        row=dict(source_sha256=case["sha256"],gbd=case["gbd"],year=case["year"],
                 stage="PROCESS_TIMEOUT",SAT_UNSAT="NOT_RUN",PAR2_s=None,
                 independent_UNSAT_LRAT=False,source_SHA_verified=True)
    fail_if(sha(original)!=case["sha256"],"source modified by screening")
    fail_if(row["source_sha256"]!=case["sha256"],"diagnostic SHA mismatch")
    row["rit4_protocol"]=PROTO
    row["original_x20"]=True
    return row

def scan(args):
    cases=manifest(args.manifest)
    fail_if(not (0<=args.shard<SHARDS),"invalid shard")
    out=pathlib.Path(args.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    rows=[]
    for i,c in enumerate(cases):
        if i%SHARDS!=args.shard:continue
        row=scan_one(c,args.cases)
        rows.append(row)
        out.write_text(json.dumps(rows,indent=2)+"\n")
        print("RIT4_SCAN "+json.dumps({k:row.get(k) for k in
            ("source_sha256","gbd","stage","gf2_rows_4","scc_rows",
             "shared_variables","rank_gain_from_scc","algebraic_mixed_only",
             "rup_mixed_only","analysis_wall_s")},sort_keys=True),flush=True)
    fail_if(len(rows)!=12,"incomplete shard")
    print("RIT4_SHARD_PASS",args.shard,len(rows),flush=True)

def load_e2e(folder,cases):
    report=json.loads((pathlib.Path(folder)/"report.json").read_text())
    fail_if(report["trials"]!=384 or report["sources"]!=24 or report["independent_LRAT"],
            "EQUIV2 audit report drift")
    consensus=set(report["historical_consensus"])
    rows=[]
    for i in range(8):
        part=json.loads((pathlib.Path(folder)/f"shard-{i}.json").read_text())
        fail_if(len(part)!=48,"EQUIV2 shard trial count "+str(i))
        rows.extend(part)
    expected={(c["sha256"],rep,arm) for c in cases for rep in (0,1) for arm in ARMS}
    seen={(r["original_sha256"],r["rep"],r["arm"]) for r in rows}
    fail_if(len(rows)!=384 or len(seen)!=384 or seen!=expected,
            "EQUIV2 SHA/rep/arm cohort pairing error")
    bysha=collections.defaultdict(lambda:collections.defaultdict(list))
    for r in rows:
        fail_if(r["status"]=="SAT" and not r["SAT_original_witness_verified"],
                "unverified SAT witness")
        fail_if(r["cap_s"]!=CAP,"E2E cap mismatch")
        accepted=(r["status"]=="SAT" or
                  (r["status"]=="UNSAT" and r["original_sha256"] in consensus))
        bysha[r["original_sha256"]][r["arm"]].append(
            dict(rep=r["rep"],status=r["status"],accepted=accepted,
                 par2=r["E2E_s"] if accepted else 2*CAP,
                 e2e=r["E2E_s"]))
    for arm in ARMS:
        actual=sum(p["par2"] for b in bysha.values() for p in b[arm])
        published=report["scores"][arm]["PAR2_s"]
        fail_if(abs(actual-published)>0.00002,
                "does not reproduce audited PAR2 "+arm)
        total=sum(p["accepted"] for b in bysha.values() for p in b[arm])
        fail_if(total!=report["scores"][arm]["solved"],
                "does not reproduce accepted outcomes "+arm)
    return bysha,report

def join(args):
    cases=manifest(args.manifest)
    root=pathlib.Path(args.results)
    original={c["sha256"]:c for c in cases}
    scanned=[]
    for shard in range(SHARDS):
        part=json.loads((root/f"shard-{shard}.json").read_text())
        fail_if(len(part)!=12,"structural shard count")
        scanned+=part
    fail_if(len(scanned)!=24 or {r["source_sha256"] for r in scanned}!=set(original),
            "structural SHA coverage")
    grouped,report=load_e2e(args.equiv2,cases)
    combined=[]
    for s in scanned:
        sha_=s["source_sha256"]
        entry=dict(source_sha256=sha_,gbd=s["gbd"],year=s["year"],
                   structure_status=s["stage"],gf2_2_3=s.get("gf2_rows_23"),
                   gf2_4=s.get("gf2_rows_4"),scc=s.get("scc_rows"),
                   shared_variables=s.get("shared_variables"),
                   rank_gain_scc=s.get("rank_gain_from_scc"),
                   algebraic_mixed=s.get("algebraic_mixed_only"),
                   rup_mixed=s.get("rup_mixed_only"),
                   original_SHA_verified=s.get("source_SHA_verified"),
                   analysis_wall_s=s.get("analysis_wall_s"))
        for arm in ARMS:
            trials=grouped[sha_][arm]
            fail_if(len(trials)!=2 or {p["rep"] for p in trials}!={0,1},
                    "incomplete EQUIV2 same-source pair")
            entry[f"{arm}_PAR2_s"]=round(sum(x["par2"] for x in trials),6)
            entry[f"{arm}_accepted"]=sum(x["accepted"] for x in trials)
            entry[f"{arm}_statuses"]=[x["status"] for x in sorted(trials,key=lambda x:x["rep"])]
        entry["delta_no_decompose_vs_cadical3_s"]=round(
            entry["cadical3_no_scc_PAR2_s"]-entry["cadical3_default_PAR2_s"],6)
        entry["delta_cadical3_vs_cadical173_s"]=round(
            entry["cadical3_default_PAR2_s"]-entry["cadical_default_PAR2_s"],6)
        combined.append(entry)
    combined.sort(key=lambda r:(r["delta_no_decompose_vs_cadical3_s"],r["source_sha256"]))
    root.mkdir(parents=True,exist_ok=True)
    (root/"joined.json").write_text(json.dumps(combined,indent=2)+"\n")
    fields=["source_sha256","gbd","year","structure_status","gf2_2_3","gf2_4",
            "scc","shared_variables","rank_gain_scc","algebraic_mixed","rup_mixed",
            "analysis_wall_s","cadical_default_PAR2_s","cadical3_default_PAR2_s",
            "cadical3_no_scc_PAR2_s","cadical3_scc4_PAR2_s","kissat1_PAR2_s",
            "native1_PAR2_s","delta_no_decompose_vs_cadical3_s",
            "delta_cadical3_vs_cadical173_s"]
    with (root/"joined.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction="ignore")
        w.writeheader();w.writerows(combined)
    all_count=lambda pred:sum(pred(r) for r in combined if r["structure_status"]=="OK")
    summary=dict(protocol=PROTO,original_sources=24,
       source_run=PARENT,recovered_e2e_run=EQUIV2,
       structural_completed=all_count(lambda r:True),
       structural_limited=sum(r["structure_status"]!="OK" for r in combined),
       with_xor4=all_count(lambda r:(r["gf2_4"] or 0)>0),
       with_shared_gf2_scc=all_count(lambda r:(r["shared_variables"] or 0)>0),
       with_joint_rank_gain=all_count(lambda r:(r["rank_gain_scc"] or 0)>0),
       with_mixed_RUP=all_count(lambda r:(r["rup_mixed"] or 0)>0),
       faster_without_decompose=[
          dict(sha=r["source_sha256"],delta_s=r["delta_no_decompose_vs_cadical3_s"],
               structural_status=r["structure_status"])
          for r in combined if r["delta_no_decompose_vs_cadical3_s"]<0][:5],
       slower_without_decompose=[
          dict(sha=r["source_sha256"],delta_s=r["delta_no_decompose_vs_cadical3_s"],
               structural_status=r["structure_status"])
          for r in sorted(combined,key=lambda x:-x["delta_no_decompose_vs_cadical3_s"])
          if r["delta_no_decompose_vs_cadical3_s"]>0][:5],
       referenced_PAR2={arm:report["scores"][arm]["PAR2_s"] for arm in ARMS},
       original_witness_gated=True,unsat_reference="historical source backend agreement",
       independent_UNSAT_LRAT=False,not_blind=True,
       new_CDCL_trials=0)
    (root/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
    print("RIT4_FINAL "+json.dumps(summary,sort_keys=True),flush=True)

def selftest():
    import tempfile,itertools
    with tempfile.TemporaryDirectory() as d:
        path=pathlib.Path(d)/"sample.cnf"
        vs=(1,2,3,4)
        blocks=[tuple(-v if flags[i] else v for i,v in enumerate(vs))
                for flags in itertools.product((False,True),repeat=4)
                if sum(flags)%2==1]
        cs=blocks+[(-2,5),(-5,3),(-3,6),(-6,2)]
        path.write_text(f"p cnf 6 {len(cs)}\n"+
                        "".join(" ".join(map(str,x))+" 0\n" for x in cs))
        case=dict(filename=path.name,sha256=sha(path),gbd="selftest",year="2026")
        r=scan_one(case,d)
        fail_if(r["stage"]!="OK" or r.get("gf2_rows_4",0)<1 or
                r.get("rank_gain_from_scc",0)<1,
                "XOR4 SCC selftest must find independent equations")
        print("RIT4_SELFTEST_PASS",flush=True)

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="action",required=True)
    s=sub.add_parser("scan")
    s.add_argument("--manifest",required=True)
    s.add_argument("--cases",required=True)
    s.add_argument("--shard",type=int,choices=[0,1],required=True)
    s.add_argument("--out",required=True)
    j=sub.add_parser("join")
    j.add_argument("--manifest",required=True)
    j.add_argument("--results",required=True)
    j.add_argument("--equiv2",required=True)
    sub.add_parser("selftest")
    args=p.parse_args()
    if args.action=="scan":scan(args)
    elif args.action=="join":join(args)
    else:selftest()

if __name__=="__main__":
    main()
