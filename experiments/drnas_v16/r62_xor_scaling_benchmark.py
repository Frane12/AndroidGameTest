#!/usr/bin/env python3
"""R62: frozen 125/250/500-variable synthetic scaling and negative controls.

Similar *dimensions*, not the original SATComp2026 formula. SHA-frozen before
measurement. No tuning on timings. R28 is a standalone exact-XOR/GF2 prior-art
front-end with unmodified SHA-pinned Kissat fallback, NOT native R32n.
"""
from __future__ import annotations
import argparse, hashlib, json, os, random, statistics, subprocess, time
from pathlib import Path
import r28_exact_gf2_benchmark as r28

SALT="DRNAS-R62-XOR-SCALING-125-250-500-NOV03-FRESH-UNSEEN-v1"
FAMILIES=("regular_xor3","local_xor3","rewired_xor3","near_xor3_control")
PER_FAMILY=4
DIMENSIONS=(125,250,500)
SHARDS=8
REPEATS=2
CAP=60.0
N=250
MODES=("kissat_pinned","r28_exact_gf2")
PROTOCOL="R62-PROSPECTIVE-SYNTHETIC-XOR-SCALING-125-250-500-v1"

def check(x,msg):
    if not x: raise RuntimeError("R61_AUDIT_FAIL "+str(msg))
def sha(data):
    if isinstance(data,Path):data=data.read_bytes()
    return hashlib.sha256(data).hexdigest()
def rng_for(family,index):
    return random.Random(int(sha(f"{SALT}/{family}/{index}".encode()),16))
def rank_of(rows):
    pivots={}
    for triple in rows:
        val=sum(1<<(x-1) for x in triple)
        while val:
            high=val.bit_length()-1
            if high not in pivots:
                pivots[high]=val
                break
            val^=pivots[high]
    return len(pivots)
def regular_rows(rng):
    for _ in range(5000):
        pp=[]
        for j in range(3):
            p=list(range(1,N+1));rng.shuffle(p);pp.append(p)
        rr=[tuple(sorted(pp[j][i] for j in range(3))) for i in range(N)]
        if any(len(set(row))!=3 for row in rr):continue
        if len(set(rr))!=N:continue
        if rank_of(rr)==N:return rr
    raise RuntimeError("Could not generate full-rank 3-regular matrix")

def make_case(family,index):
    rng=rng_for(family,index)
    if family=="local_xor3":
        perm=list(range(1,N+1));rng.shuffle(perm)
        rows=[tuple(sorted((perm[i],perm[(i+1)%N],perm[(i+2)%N]))) for i in range(N)]
    else:
        rows=regular_rows(rng)
    if family=="rewired_xor3":
        for _ in range(20):
            pos=rng.randrange(N)
            candidate=tuple(sorted(rng.sample(range(1,N+1),3)))
            old=rows[pos]
            rows[pos]=candidate
            if len(set(rows))!=N or rank_of(rows)!=N:rows[pos]=old
    check(len(rows)==N and len(set(rows))==N and all(len(set(x))==3 for x in rows),"XOR support distinctness")
    check(rank_of(rows)==N,"GF2 full rank")
    truth={j:rng.getrandbits(1) for j in range(1,N+1)}
    clauses=[]
    for support in rows:
        rhs=sum(truth[v] for v in support)&1
        for mask in range(8):
            if mask.bit_count()%2 != rhs:
                cl=[-v if (mask>>i)&1 else v for i,v in enumerate(support)]
                rng.shuffle(cl)
                clauses.append(cl)
    check(len(clauses)==4*N,"Should contain exactly 4 clauses per XOR3 row")
    if family=="near_xor3_control":
        # Break exactly one complete XOR block while retaining 1000 lines
        # and the known planted satisfying assignment. The detector must abstain.
        original=clauses[0]
        clauses[0]=list(clauses[7])
        check(clauses[0]!=original,"Control perturbation failed")
    rng.shuffle(clauses)
    check(all(any(((v>0)==bool(truth[abs(v)])) for v in c) for c in clauses),"Planted witness invalid")
    return clauses

def prepare(folder):
    global N
    out=Path(folder);out.mkdir(parents=True,exist_ok=True)
    cases=[]
    for dimension in DIMENSIONS:
        N=dimension
        for family in FAMILIES:
            for i in range(PER_FAMILY):
                clauses=make_case(family,i)
                raw=r28.dimacs(N,clauses)
                name=f"{family}_n{N}_{i:02d}.cnf"
                (out/name).write_bytes(raw)
                cases.append(dict(name=name,family=family,index=i,sha256=sha(raw),
                                  vars=N,clauses=4*N,expected="SAT"))
    check(len(cases)==48 and len(set(x["sha256"] for x in cases))==48,"Input uniqueness")
    meta=dict(protocol=PROTOCOL,salt=SALT,cases=cases,cap_s=CAP,repeats=REPEATS,
              modes=MODES,shards=SHARDS,synthetic=True,
              reference="Independent synthetic scaling; 125/250/500 variables, 4n clauses",
              limits=["Prospective 48 synthetic CNFs, not unseen official SAT2026 originals",
                      "GF2 Gaussian elimination is established prior art",
                      "R28 is not integrated native R32n",
                      "A Kissat timeout is censored, not a measured completion time",
                      "Selection conditions on full GF2 rank, not on solver time"])
    (out/"manifest.json").write_text(json.dumps(meta,indent=2)+"\n")
    (out/"source.sha256").write_text("".join(f'{x["sha256"]}  {x["name"]}\n' for x in cases))
    print("R62_FROZEN",len(cases),"MANIFEST",sha(out/"manifest.json"),flush=True)

def solve(mode,source,kissat,gf2,clauses):
    cmd=[str(kissat),str(source)] if mode=="kissat_pinned" else [str(gf2),str(source),str(kissat)]
    start=time.monotonic()
    try:
        p=subprocess.run(cmd,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                         errors="replace",timeout=CAP)
        elapsed=time.monotonic()-start
        check(p.returncode in (10,20),f"Native bad exit {mode} {p.returncode} {p.stderr[-240:]}")
        status="SAT" if p.returncode==10 else "UNSAT"
        check(status=="SAT","Planted formula cannot be UNSAT")
        check(r28.check_sat_model(p.stdout,N,clauses),"SAT certificate/witness invalid")
        if mode=="r28_exact_gf2":
            route=next((line.split()[2] for line in p.stdout.splitlines()
                        if line.startswith("c R28_ROUTE ")),"missing")
        else:route="original"
        elapsed=time.monotonic()-start
        if elapsed>CAP:
            return dict(status="TIMEOUT",wall_s=round(elapsed,6),par2_s=2*CAP,
                        route="censored_after_verification",witness_checked=True)
        return dict(status=status,wall_s=round(elapsed,6),par2_s=round(elapsed,6),
                    route=route,witness_checked=True)
    except subprocess.TimeoutExpired:
        return dict(status="TIMEOUT",wall_s=round(time.monotonic()-start,6),
                    par2_s=2*CAP,route="censored",witness_checked=False)

def measure(a):
    inputs=Path(a.inputs)
    spec=json.loads((inputs/"manifest.json").read_text())
    check(spec["protocol"]==PROTOCOL and spec["cap_s"]==CAP and
          spec["repeats"]==REPEATS and spec["modes"]==list(MODES),"Protocol mismatch")
    if hasattr(os,"sched_getaffinity"):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    kissat=Path(a.kissat).resolve();gf2=Path(a.gf2).resolve()
    check(kissat.is_file() and gf2.is_file(),"Missing binaries")
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    records=[]
    for case in spec["cases"][a.shard::SHARDS]:
        path=(inputs/case["name"]).resolve()
        check(sha(path)==case["sha256"],"Input SHA mismatch")
        n,clauses=r28.load_clauses(path)
        check(n==case["vars"] and n in DIMENSIONS and len(clauses)==4*n,"Dimensions mismatch")
        for rep in range(REPEATS):
            order=list(MODES)
            random.Random(int(sha(f'R61/order/{case["sha256"]}/{rep}'.encode()),16)).shuffle(order)
            for mode in order:
                result=solve(mode,path,kissat,gf2,clauses)
                if result["status"]=="SAT" and mode=="r28_exact_gf2":
                    expected_route="fallback" if case["family"]=="near_xor3_control" else "certified_pure_xor_sat"
                    check(result["route"]==expected_route,f"Unexpected GF2 route: {result['route']}")
                rec=dict(formula=case["name"],family=case["family"],sha256=case["sha256"],
                         repeat=rep,mode=mode,**result)
                records.append(rec)
                (out/"rows.json").write_text(json.dumps(records,indent=2)+"\n")
                print("R62_TRIAL",a.shard,case["name"],rep,mode,
                      result["status"],result["wall_s"],result["route"],flush=True)
    info=dict(shard=a.shard,manifest_sha=sha(inputs/"manifest.json"),
              kissat_sha=sha(kissat),gf2_sha=sha(gf2),rows=len(records),
              cpu=next((line for line in Path("/proc/cpuinfo").read_text().splitlines()
                        if line.startswith("model name")),"unknown"))
    (out/"metadata.json").write_text(json.dumps(info,indent=2)+"\n")
    check(len(records)==len(spec["cases"][a.shard::SHARDS])*REPEATS*2,"Missing shard rows")
    print("R62_SHARD_PASS",a.shard,len(records),flush=True)

def aggregate(a):
    inputs=Path(a.inputs)
    spec=json.loads((inputs/"manifest.json").read_text())
    full=[];binary_shas=set()
    for shard in range(SHARDS):
        root=Path(a.combined)/f"r61-shard-{shard}"/"results"
        meta=json.loads((root/"metadata.json").read_text())
        check(meta["shard"]==shard and meta["manifest_sha"]==sha(inputs/"manifest.json"),"Shard provenance")
        binary_shas.add((meta["kissat_sha"],meta["gf2_sha"]))
        rr=json.loads((root/"rows.json").read_text())
        check(len(rr)==len(spec["cases"][shard::SHARDS])*REPEATS*2,"Incomplete shard")
        full.extend(rr)
    check(len(binary_shas)==1 and len(full)==len(spec["cases"])*REPEATS*len(MODES),"Incomplete total or binary drift")
    report=[]
    for case in spec["cases"]:
        rs=[x for x in full if x["formula"]==case["name"]]
        check(len(rs)==4 and all(x["sha256"]==case["sha256"] for x in rs),"Case trials missing")
        by={m:[x for x in rs if x["mode"]==m] for m in MODES}
        k=by["kissat_pinned"];g=by["r28_exact_gf2"]
        check(all(x["status"] in ("SAT","TIMEOUT") for x in rs),"Invalid status")
        if case["family"]!="near_xor3_control":
            check(all(x["status"]=="SAT" and x["witness_checked"] for x in g),"Pure XOR exact-GF2 route failed")
        km=statistics.median(x["wall_s"] for x in k)
        gm=statistics.median(x["wall_s"] for x in g)
        gf2_solved=sum(x["status"]=="SAT" for x in g)
        both_timeout=all(x["status"]=="TIMEOUT" for x in k) and gf2_solved==2
        ratio=round(CAP/gm,1) if both_timeout else (
            round(km/gm,1) if gf2_solved==2 and all(x["status"]=="SAT" for x in k) else None)
        metric="censored_lower_bound" if both_timeout else (
            "both_solved_exact_ratio" if ratio is not None else "mixed_censoring")
        report.append(dict(formula=case["name"],family=case["family"],n=case["vars"],
                           kissat_median_observed_s=km,gf2_median_s=gm,
                           kissat_solved=sum(x["status"]=="SAT" for x in k),
                           gf2_solved=gf2_solved,ratio=ratio,ratio_kind=metric,
                           kissat_PAR2=sum(x["par2_s"] for x in k),
                           gf2_PAR2=sum(x["par2_s"] for x in g)))
    totals={}
    for f in ("ALL",)+FAMILIES+tuple(f"n{n}" for n in DIMENSIONS):
        rr=[x for x in report if f=="ALL" or x["family"]==f or f==f'n{x["n"]}']
        baseline=sum(x["kissat_PAR2"] for x in rr)
        candidate=sum(x["gf2_PAR2"] for x in rr)
        totals[f]=dict(formulas=len(rr),kissat_PAR2_s=round(baseline,6),
                       r28_PAR2_s=round(candidate,6),par2_improvement_pct=round(100*(baseline-candidate)/baseline,3),
                       kissat_solved_attempts=sum(x["kissat_solved"] for x in rr),
                       r28_solved_attempts=sum(x["gf2_solved"] for x in rr))
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    data=dict(protocol=PROTOCOL,synthetic=True,manifest_sha=sha(inputs/"manifest.json"),
              binary_hashes=list(binary_shas)[0],per_case=report,summary=totals,
              trials=full,limits=spec["limits"])
    (out/"r61-results.json").write_text(json.dumps(data,indent=2)+"\n")
    lines=["# R62 synthetic XOR scaling: 125, 250, 500 variables; 4n clauses",
           "48 source-frozen cases (125,250,500 vars; 4n clauses), 2 repeats, 60s timeout, pinned binaries.",
           "Censored ratios are **lower bounds**, not measured solved-to-solved speedups.",
           "These are **synthetic** CNFs, not new official 2026 benchmarks.", "",
           "| Formula | Kissat solved/2 | Kissat median observed s | R28 median s | Ratio | Kind |",
           "|---|---:|---:|---:|---:|---|"]
    for x in report:
        label=f'>={x["ratio"]}x' if x["ratio_kind"]=="censored_lower_bound" else (
            f'{x["ratio"]}x' if x["ratio"] is not None else "censored")
        lines.append(f'| {x["formula"]} | {x["kissat_solved"]}/2 | {x["kissat_median_observed_s"]:.6f} | {x["gf2_median_s"]:.6f} | {label} | {x["ratio_kind"]} |')
    lines+=["","## Aggregate PAR2", "| Group | Kissat PAR2 (s) | R28 PAR2 (s) | Gain |","|---|---:|---:|---:|"]
    for f,t in totals.items():
        lines.append(f'| {f} | {t["kissat_PAR2_s"]:.3f} | {t["r28_PAR2_s"]:.3f} | {t["par2_improvement_pct"]:.2f}% |')
    (out/"r61-report.md").write_text("\n".join(lines)+"\n")
    print("R62_FINAL_AUDIT_PASS",json.dumps(totals),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="mode",required=True)
    q=sub.add_parser("prepare");q.add_argument("--out",required=True)
    q=sub.add_parser("measure")
    for name in ("inputs","out","kissat","gf2"):q.add_argument("--"+name,required=True)
    q.add_argument("--shard",type=int,choices=range(SHARDS),required=True)
    q=sub.add_parser("aggregate")
    for name in ("inputs","combined","out"):q.add_argument("--"+name,required=True)
    a=p.parse_args()
    if a.mode=="prepare":prepare(a.out)
    elif a.mode=="measure":measure(a)
    else:aggregate(a)
