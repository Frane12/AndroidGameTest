#!/usr/bin/env python3
"""R52: prospective Main Track 2026 SHA-pinned matched comparison.
Official CaDiCaL3 scores used ONLY for pre-timing SAT/UNSAT and runtime strata,
never DRNAS outcome selection. Excludes R32p + R32r + R49/R51 identities.
R49 gate is frozen R49 logic. One CPU/core and strict 40s wall per method.
Official winner is NOT tested; Kissat4.0.4 and CaDiCaL3.0.1 are references.
"""
from __future__ import annotations
import argparse
import collections
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import random
import resource
import subprocess
import tempfile
import time
import urllib.request

import r32p_real_satcomp26_benchmark as r32p
import r32r_more_real_satcomp26_benchmark as r32r
import r49_pivot_coherence_gate as r49
import r32t_certified_short_xor as xor

PROTO="DRNAS-R52-PROSPECTIVE-2026-TOPREFS-20261103-v1"
URI="https://satcompetition.github.io/2026/downloads/track_main_2026.uri"
SCORES="https://satcompetition.github.io/2026/downloads/scores.csv"
SALT="DRNAS-R52-PRECOMMITTED-STRATA-20261103-v1"
STRATA=("sat_fast","unsat_fast","sat_mid","unsat_mid")
MODES=("kissat_pinned","drnas_r49_gate","drnas_r32t_xor","kissat_4_0_4","cadical_3_0_1")
PER_STRATUM=3
MAX_TRIES_PER_STRATUM=10
CAP=40.
SHARDS=6
RAW_CAP=28*1024*1024
CNF_CAP=48*1024*1024
MAX_READY=12

def check(ok,msg):
    if not ok: raise RuntimeError("R52_AUDIT_FAIL "+str(msg))
def digest(p):
    h=hashlib.sha256()
    with open(p,"rb") as f:
        for c in iter(lambda:f.read(1<<20),b""):h.update(c)
    return h.hexdigest()
def fetch_bytes(url,limit=32*1024*1024):
    req=urllib.request.Request(url,headers={"User-Agent":"DRNAS-SAT-Independent-2026-R52/1.0"})
    with urllib.request.urlopen(req,timeout=60) as resp:
        b=resp.read(limit+1)
    check(len(b)<=limit,"source exceeds declared download cap")
    return b
def sha_order(x):
    return hashlib.sha256((SALT+":"+x).encode()).hexdigest()
def freeze(a):
    folder=Path(a.out);folder.mkdir(parents=True,exist_ok=True)
    listing=fetch_bytes(URI,100000).decode().strip().splitlines()
    uris=[u.strip().split("/")[-1] for u in listing]
    check(len(uris)==400 and len(set(uris))==400,"official Main2026 URI list changed")
    available=set(uris)
    past={h for _,h in r32p.PINS}|{h for _,h in r32r.PINS}
    check(len(past)==37,"prior source exclusion registry unexpectedly changed")
    csv_raw=fetch_bytes(SCORES,32*1024*1024)
    scores=list(csv.DictReader(io.StringIO(csv_raw.decode("utf-8"))))
    reference=[x for x in scores if x["solverid"]=="biere_cadical3[main]"
               and x["instanceid"] in available]
    check(len(reference)==400,"official baseline score coverage missing")
    pools={k:[] for k in STRATA}
    for x in reference:
        g=x["instanceid"]
        if g in past or g in r32p.PINS:continue
        status=x["status"]
        if status not in ("sat-verified","unsat-verified"):continue
        t=float(x["runtime"])
        tier="fast" if .0<=t<10 else ("mid" if 10<=t<80 else None)
        if tier is None:continue
        key=("sat" if status=="sat-verified" else "unsat")+"_"+tier
        pools[key].append(dict(gbd=g,official_control_s=t,
                                official_result="SAT" if status=="sat-verified" else "UNSAT",
                                original_2026_index=uris.index(g)))
    r32p.CNF_LIMIT=CNF_CAP
    cases=[];tries=[];seen=set()
    for category in STRATA:
        options=sorted(pools[category],key=lambda c:sha_order(category+"/"+c["gbd"]))
        ready=0
        for candidate in options[:MAX_TRIES_PER_STRATUM]:
            g=candidate["gbd"]
            trace=dict(category=category,gbd=g,index=candidate["original_2026_index"])
            check(g not in seen and g not in past,"duplicate/old original id")
            seen.add(g)
            try:
                raw,redirect=r32p.request_url(
                    "https://benchmark-database.de/file/"+g,RAW_CAP,seconds=65)
                cnf,compression=r32p.decode(raw)
                check(len(cnf)<=CNF_CAP,"too big original CNF")
                n,m=r32p.parse_dimacs_metadata(cnf)
                name=g+".cnf"
                path=folder/name
                path.write_bytes(cnf)
                case=dict(**candidate,name=name,sha256=digest(path),
                    bytes=len(cnf),compressed_bytes=len(raw),
                    compression=compression,variables=n,clauses=m,
                    source_url="https://benchmark-database.de/file/"+g,
                    redirect=redirect)
                cases.append(case);ready+=1
                trace.update(state="READY",sha256=case["sha256"],n=n,m=m,bytes=len(cnf))
            except Exception as err:
                (folder/(g+".cnf")).unlink(missing_ok=True)
                trace.update(state="EXCLUDED_DOWNLOAD_SIZE_OR_PARSE",
                             reason=str(err)[:350])
            tries.append(trace)
            print("R52_FREEZE_CANDIDATE",json.dumps(trace),flush=True)
            if ready==PER_STRATUM:break
    check(len(cases)>=8,"fewer than 8 size-eligible pinned official sources")
    check(len(cases)<=MAX_READY and len({c["gbd"] for c in cases})==len(cases),
          "duplicate or too many")
    for c in cases:
        check(c["gbd"] not in past and digest(folder/c["name"])==c["sha256"],
              "prior source overlap or drift")
    manifest=dict(protocol=PROTO,uri_source=URI,score_source=SCORES,
        official_uri_sha256=hashlib.sha256("\n".join(listing).encode()).hexdigest(),
        official_score_sha256=hashlib.sha256(csv_raw).hexdigest(),
        rule=dict(strata=STRATA,per_stratum=PER_STRATUM,max_attempts=MAX_TRIES_PER_STRATUM,
                  bands_seconds={"fast":"0-10","mid":"10-80"},
                  salt=SALT,prior_excluded_ids=sorted(past),
                  score_baseline="biere_cadical3[main]",size_raw=RAW_CAP,
                  size_cnf=CNF_CAP),
        non_blind_official_baseline_selection=True,
        no_DRNAS_prior_results_used_for_case_selection=True,
        not_globally_unseen_guaranteed=True,
        benchmark_cap_seconds=CAP,modes=MODES,cases=cases,
        download_log=tries)
    (folder/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    (folder/"source.sha256").write_text("".join(
         c["sha256"]+"  "+c["name"]+"\n" for c in cases))
    print("R52_FREEZE_PASS",len(cases),"originals",len(tries),
          "attempted",flush=True)

def child_memory():
    resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))

def trial(original,mode,binaries):
    start=time.monotonic()
    prep=0.;added=0;gate=False;xor_eq=0
    with tempfile.TemporaryDirectory(prefix="drnas-r52-") as tmp:
        inputfile=original
        if mode=="drnas_r49_gate":
            plan=r49.compute_plan(original)
            gate=plan["gate"]
            derived=r49.selection("gate",plan)
            added=len(derived)
            if added:
                candidate=Path(tmp)/"r49.cnf"
                rw=r49.r48.safe_rewrite(original,candidate,derived)
                check(rw["added"]==added,"R49 rewrite failed")
                inputfile=candidate
        if mode=="drnas_r32t_xor":
            augmented=Path(tmp)/"xor.cnf"
            cert=Path(tmp)/"xor.json"
            info=xor.build(original,augmented,cert)
            xor.audit(original,augmented,cert)
            added=info["added_clauses"]
            xor_eq=info["chosen_short_equations"]
            inputfile=augmented
        prep=time.monotonic()-start
        answer="TIMEOUT"
        if prep<CAP:
            try:
                p=subprocess.run([str(binaries[mode]),str(inputfile)],
                    capture_output=True,text=True,errors="replace",
                    timeout=CAP-prep,preexec_fn=child_memory)
                check(p.returncode in (10,20),
                      "solver exit "+str(p.returncode)+" "+p.stderr[-200:])
                answer="SAT" if p.returncode==10 else "UNSAT"
                if answer=="SAT":
                    r32p.verify_sat_witness(original,p.stdout)
            except subprocess.TimeoutExpired:
                answer="TIMEOUT"
        elapsed=time.monotonic()-start
        if elapsed>CAP:answer="TIMEOUT"
        return dict(mode=mode,answer=answer,
              wall_s=round(min(elapsed,CAP),6),
              prep_s=round(prep,6),par2_s=round(
                  min(elapsed,CAP) if answer!="TIMEOUT" else CAP*2,6),
              added_clauses=added,r49_gate=gate,xor_equations=xor_eq)

def measure(a):
    m=json.loads((Path(a.sources)/"manifest.json").read_text())
    check(m["protocol"]==PROTO,"frozen manifest required")
    check(0<=a.shard<SHARDS,"invalid shard")
    binarypaths={k:Path(getattr(a,k)).resolve() for k in MODES
          if k in ("kissat_pinned","kissat_4_0_4","cadical_3_0_1")}
    binarypaths["drnas_r49_gate"]=binarypaths["kissat_pinned"]
    binarypaths["drnas_r32t_xor"]=binarypaths["kissat_pinned"]
    check(all(v.is_file() for v in binarypaths.values()),"missing binary")
    if hasattr(os,"sched_setaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    folder=Path(a.out);folder.mkdir(parents=True,exist_ok=True)
    hashes={k:digest(v) for k,v in binarypaths.items()}
    (folder/"meta.json").write_text(json.dumps(
        dict(protocol=PROTO,shard=a.shard,
             manifest_sha256=digest(Path(a.sources)/"manifest.json"),
             binary_sha256=hashes),indent=2)+"\n")
    rows=[]
    for c in m["cases"][a.shard::SHARDS]:
        orig=Path(a.sources)/c["name"]
        check(digest(orig)==c["sha256"],"official CNF hash mismatch")
        order=list(MODES)
        random.Random(int(sha_order(c["sha256"]),16)).shuffle(order)
        for mode in order:
            data=trial(orig,mode,binarypaths)
            row=dict(gbd=c["gbd"],original_sha256=c["sha256"],**data)
            rows.append(row)
            print("R52_REAL2026_TRIAL",c["gbd"],mode,row["answer"],
                  row["wall_s"],"PAR2",row["par2_s"],"added",row["added_clauses"],
                  flush=True)
            (folder/"rows.json").write_text(json.dumps(rows,indent=2)+"\n")
    check(len(rows)==len(m["cases"][a.shard::SHARDS])*len(MODES),
          "incomplete shard")

def audit(a):
    m=json.loads((Path(a.sources)/"manifest.json").read_text())
    check(m["protocol"]==PROTO,"wrong protocol")
    rows=[];seen=set();binaries=collections.defaultdict(set)
    for shard in range(SHARDS):
        root=Path(a.combined)/("r52-shard-"+str(shard))/"results"
        meta=json.loads((root/"meta.json").read_text())
        check(meta["shard"]==shard and
             meta["manifest_sha256"]==digest(Path(a.sources)/"manifest.json"),
             "shard original mismatch")
        for k,v in meta["binary_sha256"].items():binaries[k].add(v)
        for r in json.loads((root/"rows.json").read_text()):
            key=(r["gbd"],r["mode"])
            check(key not in seen,"duplicate result")
            seen.add(key);rows.append(r)
    check(len(rows)==len(m["cases"])*len(MODES)
       and all(len(x)==1 for x in binaries.values()),"incomplete or binary mismatch")
    for c in m["cases"]:
        group=[r for r in rows if r["gbd"]==c["gbd"]]
        check(len(group)==len(MODES) and {r["mode"] for r in group}==set(MODES),
             "unpaired source")
        check(all(r["original_sha256"]==c["sha256"] for r in group),
              "source SHA drift")
        check(len({r["answer"] for r in group if r["answer"]!="TIMEOUT"})<=1,
              "wrong SAT vs UNSAT")
    out={}
    for mode in MODES:
        rr=[r for r in rows if r["mode"]==mode]
        out[mode]=dict(n=len(rr),solved=sum(r["answer"]!="TIMEOUT" for r in rr),
         timeouts=sum(r["answer"]=="TIMEOUT" for r in rr),
         par2_sum_s=round(sum(r["par2_s"] for r in rr),6),
         total_added_clauses=sum(r["added_clauses"] for r in rr),
         r49_active=sum(r["r49_gate"] for r in rr),
         xor_active=sum(r["xor_equations"]>0 for r in rr))
    base=out["kissat_pinned"]["par2_sum_s"]
    for z in out.values():z["delta_vs_pinned_pct"]=round(
        100*(z["par2_sum_s"]/base-1),4)
    data=dict(protocol=PROTO,summary=out,rows=rows,
        source_manifest=m,binary_sha256={k:next(iter(v)) for k,v in binaries.items()},
        caveat=["Public official 2026 Main Track sources; limited small stratified subset",
        "Official CaDiCaL timings used ONLY for cohort stratification before DRNAS runs",
        "Not a fresh submission to official competition, not official rank",
        "Exclusion registry covers prior R32p/R32r source IDs, not entire project history",
        "Original SAT witnesses independently checked, UNSAT without external LRAT",
        "Single pinned Kissat is used for DRNAS policy; only source clauses differ",
        "Different hardware and limit from 2026 contest; not direct record comparison",
        "Single core, single serial process per trial, max 3GiB and 40s time cap"])
    Path(a.out).write_text(json.dumps(data,indent=2)+"\n")
    lines=["# DRNAS R52 — prospective official 2026 Main Track matched benchmark",
        "Cases selected using public CaDiCaL score strata before any DRNAS run.",
        "Same one GitHub runner core, 40s overall cap, 3GiB, PAR2 timeout = 80s.",
        "Not the official winner or official competition ranking.",
        "",
        "| Mode | Solved | PAR2 sum seconds | Delta vs original pinned Kissat |",
        "|---|---:|---:|---:|"]
    for mode in MODES:
        z=out[mode]
        lines.append(f'| {mode} | {z["solved"]}/{z["n"]} | {z["par2_sum_s"]:.3f} | {z["delta_vs_pinned_pct"]:+.2f}% |')
    lines+=["","## Instance wall-clock seconds",
      "| 2026 GBD prefix | "+" | ".join(MODES)+" |",
      "|---|"+("|---:|"*len(MODES))]
    for c in m["cases"]:
        by={r["mode"]:r for r in rows if r["gbd"]==c["gbd"]}
        lines.append("| "+c["gbd"][:12]+" | "+" | ".join(
              f'{by[z]["wall_s"]:.3f}' if by[z]["answer"]!="TIMEOUT" else "TIMEOUT (40)"
              for z in MODES)+" |")
    lines+=["","## Auditing","Complete SHA and exclusions in JSON artifact.",
            "Solver comparison excludes the 2026 champion because its exact binary was not prepared."]
    Path(a.markdown).write_text("\n".join(lines)+"\n")
    print("R52_FINAL_AUDIT_PASS",json.dumps(out),flush=True)

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="command",required=True)
    x=sub.add_parser("freeze");x.add_argument("--out",required=True)
    x=sub.add_parser("measure")
    for k in ("sources","shard","out","kissat_pinned","kissat_4_0_4","cadical_3_0_1"):
        x.add_argument("--"+k,required=True)
    x=sub.add_parser("audit")
    for k in ("sources","combined","out","markdown"):x.add_argument("--"+k,required=True)
    a=p.parse_args()
    if a.command=="freeze":freeze(a)
    elif a.command=="measure":
        a.shard=int(a.shard);measure(a)
    else:audit(a)

if __name__=="__main__": main()
