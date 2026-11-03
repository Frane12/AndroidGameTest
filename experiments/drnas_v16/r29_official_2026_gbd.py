#!/usr/bin/env python3
"""R29 vs original SAT Competition 2026 Main GBD CNFs from R28 SHA archive.

Four modes, two paired repeats; independent reference labels, per-mode PAR-2.
The input cohort (10 prior development + 4 R28 additions) was seen before:
this is a retrospective ORIGINAL-CNF audit, not a fresh blind competition.
R29's original 12 MiB input guard is retained; fallback is a valid and important
result, not proof of an XOR optimization. Never call it an official leaderboard.
"""
from __future__ import annotations
import argparse,bz2,csv,gzip,hashlib,json,lzma,os,random,statistics,subprocess,time
from collections import Counter
from pathlib import Path

PROTOCOL="DRNAS-R29-2026-ORIGINAL-GBD-REPLAY-20261103-V1"
REPS=2
SHARDS=4
CAP=6.0
MODES=("Kissat_pinned","CaDiCaL301","R29_safe","R29_active")
SRC_PROTO="DRNAS-R28-AND-XOR-PHASE-AB-AUDIT-20261103-v1"
OFFICIAL_ROLES=("previously_measured_development","r28_additional_original_holdout")
def check(ok,msg):
    if not ok:raise RuntimeError("R29_OFFICIAL_AUDIT_FAIL: "+str(msg))
def sha(data):
    h=hashlib.sha256()
    if isinstance(data,Path):
        with data.open("rb") as f:
            for part in iter(lambda:f.read(1<<20),b""):h.update(part)
    else:h.update(data)
    return h.hexdigest()
def normalized_bytes(raw):
    if raw.startswith(b"\xfd7zXZ\x00"):return lzma.decompress(raw)
    if raw[:2]==b"\x1f\x8b":return gzip.decompress(raw)
    if raw.startswith(b"BZh"):return bz2.decompress(raw)
    return raw
def normalize(a):
    src=Path(a.original)
    spec=json.loads((src/"manifest.json").read_text())
    check(spec["protocol"]==SRC_PROTO and len(spec["cases"])==18,"R28 source manifest")
    out=Path(a.dest)
    out.mkdir(parents=True,exist_ok=True)
    items=[]
    for c in spec["cases"]:
        if c["role"] not in OFFICIAL_ROLES:continue
        source=src/c["path"]
        check(sha(source)==c["sha256"],"Original source SHA changed "+c["id"])
        raw=normalized_bytes(source.read_bytes())
        check(raw.startswith(b"p cnf ") or b"\np cnf " in raw[:1024],
              "Non DIMACS source "+c["id"])
        dest=f"official_{len(items):02d}.cnf"
        (out/dest).write_bytes(raw)
        items.append(dict(id=c["id"],source_role=c["role"],original_sha256=c["sha256"],
                          raw_sha256=sha(raw),path=dest,bytes=len(raw),
                          source=c["source"],expected=c["expected"],
                          from_archive=c["path"],source_compressed_bytes=source.stat().st_size))
    check(len(items)==14 and len({c["raw_sha256"] for c in items})==14,
          "Expected 14 original SHA-distinct 2026 GBD CNFs")
    result=dict(protocol=PROTOCOL,source_protocol=SRC_PROTO,
                source_manifest_sha256=sha(src/"manifest.json"),
                cap_s=CAP,repeats=REPS,shards=SHARDS,modes=MODES,
                cases=items,source_run_id=41614909924,
                caveats=["Actual original GBD CNFs previously analyzed in R28",
                         "Only 14 original GBD cases; 4 synthetic XOR controls excluded",
                         "No run claims official SAT Competition hardware/ranking",
                         "All solvers use normalized decompressed identical DIMACS bytes",
                         "R29 native cap remains 12 MiB, 3000 vars, 150k clauses; larger sources are passed directly to baseline",
                         "Both R29 unit injection and no-injection modes are measured, but only safe is default",
                         "Reference SAT/UNSAT labels are from preverified source manifest",
                         "SAT models are not independently verified here if unavailable",
                         "No independent UNSAT proof for baseline solver results",
                         "Timeout PAR2 penalty is 12 seconds; no unsolved actual time inference"])
    (out/"manifest.json").write_text(json.dumps(result,indent=2)+"\n")
    (out/"originals.sha256").write_text("".join(f'{c["raw_sha256"]}  {c["path"]}\n' for c in items))
    print("R29_OFFICIAL_FROZEN",len(items),sha(out/"manifest.json"),flush=True)
    for c in items:print("R29_OFFICIAL_CASE",c["id"],c["source_role"],c["bytes"],flush=True)

def parse_sat_status(p):
    if p.returncode in (10,20):
        return "SAT" if p.returncode==10 else "UNSAT"
    if "s UNSATISFIABLE" in p.stdout:return "UNSAT"
    if "s SATISFIABLE" in p.stdout:return "SAT"
    raise RuntimeError("Solver failed return="+str(p.returncode)+" stderr="+p.stderr[-450:])

def trial(case,mode,binpaths,path):
    if mode=="Kissat_pinned":cmd=[str(binpaths["kissat"]),str(path)]
    elif mode=="CaDiCaL301":cmd=[str(binpaths["cadical"]),str(path)]
    else:cmd=[str(binpaths["r29"]),str(path),str(binpaths["kissat"])]
    env=os.environ.copy()
    env["R29_MODE"]="active" if mode=="R29_active" else "shadow"
    start=time.monotonic()
    try:
        p=subprocess.run(cmd,env=env,capture_output=True,text=True,
                         errors="replace",timeout=CAP)
        wall=time.monotonic()-start
        status=parse_sat_status(p)
        expected=case["expected"].upper()
        check(status==expected,"Wrong answer for "+case["id"]+" "+mode+
              " status="+status+" expected="+expected)
        trace=next((x for x in p.stdout.splitlines() if x.startswith("c R29_ROUTE ")),"")
        route=trace.split()[2] if trace else "baseline"
        reason=next((x.split("reason=",1)[1].split()[0] for x in
                     p.stdout.splitlines() if x.startswith("c R29_ROUTE fallback reason=")),"")
        if mode.startswith("R29_"):check(bool(trace),"R29 missing route trace "+case["id"])
    except subprocess.TimeoutExpired:
        wall=time.monotonic()-start
        status="TIMEOUT";route="timeout";reason=""
    return dict(status=status,seconds=round(wall,6),
                PAR2=12.0 if status=="TIMEOUT" else round(wall,6),
                route=route,reason=reason)

def run(a):
    root=Path(a.inputs)
    spec=json.loads((root/"manifest.json").read_text())
    check(spec["protocol"]==PROTOCOL and len(spec["cases"])==14
          and spec["cap_s"]==CAP and spec["repeats"]==REPS,"Manifest changed")
    check(0<=a.shard<SHARDS,"Shard out of range")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    binpaths={k:Path(getattr(a,k)).resolve() for k in ("kissat","cadical","r29")}
    check(all(p.is_file() for p in binpaths.values()),"Missing binary")
    out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    metadata=dict(shard=a.shard,source_manifest_sha256=sha(root/"manifest.json"),
                  bin_sha256={k:sha(p) for k,p in binpaths.items()},
                  cpu=next((x for x in Path("/proc/cpuinfo").read_text().splitlines()
                            if x.startswith("model name")),"unknown"))
    (out/"metadata.json").write_text(json.dumps(metadata,indent=2)+"\n")
    rows=[]
    for case in spec["cases"][a.shard::SHARDS]:
        path=(root/case["path"]).resolve()
        check(sha(path)==case["raw_sha256"],"Input SHA drift "+case["id"])
        for rep in range(REPS):
            modes=list(MODES)
            seed=int(sha((case["raw_sha256"]+str(rep)+"paired").encode()),16)
            random.Random(seed).shuffle(modes)
            for mode in modes:
                result=trial(case,mode,binpaths,path)
                row=dict(id=case["id"],sha256=case["raw_sha256"],
                         role=case["source_role"],bytes=case["bytes"],
                         rep=rep,mode=mode,**result)
                rows.append(row)
                (out/"rows.json").write_text(json.dumps(rows,indent=1)+"\n")
                print("R29_OFFICIAL_TRIAL",case["id"],rep,mode,result["status"],
                      result["seconds"],result["route"],result["reason"],flush=True)
        outcomes={r["status"] for r in rows if r["id"]==case["id"] and r["status"]!="TIMEOUT"}
        check(len(outcomes)<=1,"SAT disagreement "+case["id"])
    print("R29_OFFICIAL_SHARD_DONE",a.shard,len(rows),flush=True)

def aggregate(a):
    root=Path(a.inputs);spec=json.loads((root/"manifest.json").read_text())
    bins=set();rows=[]
    for shard in range(SHARDS):
        p=Path(a.combined)/f"r29-official-shard-{shard}"/"results"
        md=json.loads((p/"metadata.json").read_text())
        check(md["shard"]==shard and md["source_manifest_sha256"]==sha(root/"manifest.json"),
              "Shard provenance mismatch")
        bins.add(json.dumps(md["bin_sha256"],sort_keys=True))
        part=json.loads((p/"rows.json").read_text())
        check(len(part)==len(spec["cases"][shard::SHARDS])*REPS*len(MODES),
              "Incomplete shard")
        rows+=part
    check(len(rows)==112 and len(bins)==1,"Expected 112 completed attempts and single binary identity")
    summary={}
    for role in ("ALL",)+OFFICIAL_ROLES:
        section=[c for c in spec["cases"] if role=="ALL" or c["source_role"]==role]
        z={}
        for mode in MODES:
            arows=[r for r in rows if r["mode"]==mode and
                   (role=="ALL" or r["role"]==role)]
            costs=[]
            solved=0;reg2=0
            for c in section:
                t=[r for r in arows if r["id"]==c["id"]]
                check(len(t)==REPS,"Missing repeat")
                cost=statistics.median(r["PAR2"] for r in t)
                costs.append(cost)
                solved+=all(r["status"]!="TIMEOUT" for r in t)
                b=[r for r in rows if r["id"]==c["id"] and r["mode"]=="Kissat_pinned"]
                check(len(b)==REPS,"Missing baseline")
                if cost>2*statistics.median(r["PAR2"] for r in b):reg2+=1
            z[mode]=dict(solved=int(solved),cases=len(section),
                         sum_median_PAR2=round(sum(costs),6),
                         timeout_attempts=sum(r["status"]=="TIMEOUT" for r in arows),
                         regressions_gt2x=reg2,
                         routes=dict(Counter(r["route"] for r in arows)),
                         fallback_reasons=dict(Counter(r["reason"] for r in arows if r["reason"])))
        b=z["Kissat_pinned"]["sum_median_PAR2"]
        for m in MODES:z[m]["gain_vs_Kissat_pct"]=round(100*(b-z[m]["sum_median_PAR2"])/max(1e-9,b),3)
        summary[role]=z
        print("R29_OFFICIAL_SUMMARY",role,json.dumps(z,sort_keys=True),flush=True)
    per=[]
    for c in spec["cases"]:
        r=[x for x in rows if x["id"]==c["id"]]
        q={m:round(statistics.median(x["PAR2"] for x in r if x["mode"]==m),6) for m in MODES}
        route=next(x["route"] for x in r if x["mode"]=="R29_safe")
        why=next(x["reason"] for x in r if x["mode"]=="R29_safe")
        per.append(dict(id=c["id"],role=c["source_role"],expected=c["expected"],
                        raw_bytes=c["bytes"],sha256=c["raw_sha256"],
                        route=route,reason=why,times=q))
    result=dict(protocol=PROTOCOL,manifest_sha256=sha(root/"manifest.json"),
                binary_sha256=json.loads(next(iter(bins))),
                summary=summary,per_case=per,rows=rows,
                limitations=["14 original SAT Competition 2026/GBD formulas, previously used in R28",
                             "This is not a new blind holdout or official competition evaluation",
                             "R29 12 MiB/3000-variable size guard can force Kissat fallback",
                             "PAR-2 max 6 s and all-mode hardware matched per formula",
                             "No independent UNSAT proof check; reference labels checked"])
    Path(a.out_json).write_text(json.dumps(result,indent=2)+"\n")
    md=["# DRNAS SAT R29 — 2026 Main Track original GBD CNF retrospective comparison",
        "14 SHA-verified original 2026 GBD instances; four modes, two paired repeats, 6 s cap.",
        "4 synthetic XOR controls were excluded; results are NOT an official SAT Competition ranking.",
        "The 14 inputs were already part of prior R28 analysis, not a fresh blind holdout.",
        "PAR-2 timeout penalty = 12 seconds; times are sums of per-case medians.",""]
    for role,data in summary.items():
        md+=[f"## {role}", "| Solver | Solved | Sum per-case median PAR-2 (s) | Timeouts (attempts) | >2× regressions | Gain vs Kissat |",
            "|---|---:|---:|---:|---:|---:|"]
        for name,z in data.items():
            md.append(f"| {name} | {z['solved']}/{z['cases']} | {z['sum_median_PAR2']:.4f} | {z['timeout_attempts']} | {z['regressions_gt2x']} | {z['gain_vs_Kissat_pct']:+.2f}% |")
    md+=["","## Formula-level comparisons","| Formula | Case type | Kissat | CaDiCaL | R29 safe | R29 active | R29 route |","|---|---|---:|---:|---:|---:|---|"]
    for row in per:
        d=row["times"]
        md.append(f"| {row['id']} | {row['role']} | {d['Kissat_pinned']:.3f} | {d['CaDiCaL301']:.3f} | {d['R29_safe']:.3f} | {d['R29_active']:.3f} | {row['route']} {row['reason']} |")
    Path(a.out_md).write_text("\n".join(md)+"\n")
    with Path(a.out_csv).open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print("R29_OFFICIAL_AUDIT_PASS",len(rows),len(per),flush=True)

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="cmd",required=True)
    x=sub.add_parser("normalize");x.add_argument("--original",required=True);x.add_argument("--dest",required=True)
    x=sub.add_parser("run")
    for k in ("inputs","kissat","cadical","r29","outdir"):x.add_argument("--"+k,required=True)
    x.add_argument("--shard",type=int,required=True)
    x=sub.add_parser("aggregate")
    for k in ("inputs","combined","out-json","out-md","out-csv"):x.add_argument("--"+k,required=True)
    args=p.parse_args()
    if args.cmd=="normalize":normalize(args)
    elif args.cmd=="run":run(args)
    else:aggregate(args)
if __name__=="__main__":main()
