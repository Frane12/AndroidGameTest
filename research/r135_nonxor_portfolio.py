#!/usr/bin/env python3
"""R135 frozen non-XOR portfolio: bounded BIG/Horn scan chooses Kissat/CaDiCaL.
Precommitted BEFORE any timings on independent 400-CNF corpus. Pure original
CNF; solver selection only. All costs included. No promotion without proof.
"""
import argparse,collections,csv,gzip,hashlib,json,os,pathlib,random,statistics,subprocess,sys,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r134_nonxor_shadow as shadow
import r127_early_xor_benchmark as witness
ROOT=pathlib.Path("r135");SOURCE=pathlib.Path("holdout-400")
PROTO="DRNAS-R135-FROZEN-NONXOR-BIG-HORN-PORTFOLIO-20261105-v1"
CAP=15.0;REPS=2;SHARDS=8;MODES=("kissat","cadical","r118","r135")
KISSAT=pathlib.Path("built/bin/kissat_4_0_4")
CADICAL=pathlib.Path("built/bin/cadical_3_0_1")
R118=pathlib.Path("r135/r118")
# Frozen conservative hypothesis: dense binary/Horn formulas prefer Kissat;
# sparse non-Horn formulas may favor CaDiCaL. 8 MiB scan / 120k clauses.
# No training on 400 sources, no post-hoc threshold optimization.
BINARY_THRESHOLD=0.30
HORN_THRESHOLD=0.55

def need(x,m):
    if not x:raise RuntimeError("R135_REFUSED "+m)
def digest(p):return shadow.digest(p)
def write(p,x):
    p=pathlib.Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(x,sort_keys=True,indent=2)+"\n")
def read_sources():
    mpath=SOURCE/"manifest-400.json"
    need(mpath.is_file(),"missing 400 master manifest")
    m=json.loads(mpath.read_text())
    need(m.get("protocol")=="DRNAS-400-PROSPECTIVE-20261105-v1" and m.get("status")=="COMPLETE","wrong 400 freeze protocol")
    cases=m.get("formulas")
    need(isinstance(cases,list) and len(cases)==400,"expected exactly 400 frozen formulas")
    seen=set();resolved=[]
    for i,c in enumerate(cases):
        sha=c.get("sha256")
        need(isinstance(sha,str) and len(sha)==64 and sha not in seen,"missing or duplicate original SHA")
        seen.add(sha)
        compressed=pathlib.Path(c["compressed_file"])
        need(not compressed.is_absolute() and ".." not in compressed.parts,"unsafe original CNF path")
        cp=compressed if compressed.is_file() else SOURCE/compressed
        need(cp.is_file(),"missing frozen compressed CNF "+str(cp))
        raw=gzip.open(cp,"rb").read(8_000_001)
        need(len(raw)<=8_000_000 and hashlib.sha256(raw).hexdigest()==sha,"original SHA mismatch "+str(cp))
        dest=ROOT/"unpacked"/(sha+".cnf")
        dest.parent.mkdir(parents=True,exist_ok=True)
        if not dest.exists() or digest(dest)!=sha:dest.write_bytes(raw)
        resolved.append(dict(id=str(dest),sha256=sha,cohort=c.get("category","unknown")))
    return digest(mpath),resolved

def choose(src):
    st=time.perf_counter()
    f=shadow.scan(src)
    # No selection on incomplete scans; conservative direct Kissat.
    if not f["fully_scanned"]:reason="incomplete_scan";target="kissat"
    elif f["binary_ratio"]>=BINARY_THRESHOLD or f["horn_ratio"]>=HORN_THRESHOLD:
        reason="binary_or_horn";target="kissat"
    else:reason="sparse_nonhorn";target="cadical"
    return target,reason,f,round(time.perf_counter()-st,6)
def invoke(src,mode,rep):
    start=time.perf_counter();selection=None;cost=0.0;reason="direct";features=None
    if mode=="r135":
        target,reason,features,cost=choose(src)
        selection=target
        command=[str((KISSAT if target=="kissat" else CADICAL).resolve()),str(src.resolve())]
    elif mode=="r118":command=[str(R118.resolve()),str(src.resolve()),str(KISSAT.resolve())]
    else:command=[str((KISSAT if mode=="kissat" else CADICAL).resolve()),str(src.resolve())]
    elapsed=time.perf_counter()-start
    try:
        remaining=max(0.001,CAP-elapsed)
        if elapsed>=CAP:raise subprocess.TimeoutExpired(command,CAP)
        p=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=remaining)
        elapsed=time.perf_counter()-start
        need(p.returncode in (10,20),"solver non-SAT exit "+str(p.returncode)+" "+p.stderr[-300:].decode(errors="replace"))
        status="SAT" if p.returncode==10 else "UNSAT"
        if elapsed>=CAP:status="TIMEOUT"
        proof="timeout"
        if status=="SAT":
            witness.check_original_sat(p.stdout,src)
            proof="source_SAT_witness_verified"
        elif status=="UNSAT":proof="UNSAT_without_independent_LRAT_proof"
    except subprocess.TimeoutExpired:
        elapsed=CAP;status="TIMEOUT";proof="timeout"
    return dict(mode=mode,repeat=rep,status=status,seconds=round(min(elapsed,CAP),6),
        par2=30.0 if status=="TIMEOUT" else round(elapsed,6),proof=proof,
        selector_target=selection,selector_reason=reason,selector_cost_s=cost,
        binary_ratio=features["binary_ratio"] if features else None,
        horn_ratio=features["horn_ratio"] if features else None,
        fully_scanned=features["fully_scanned"] if features else None)
def run(shard):
    need(0<=shard<SHARDS,"shard out of range")
    source_sha,cases=read_sources()
    for p in (KISSAT,CADICAL,R118):need(p.is_file(),"missing pinned solver "+str(p))
    if hasattr(os,"sched_getaffinity"):
        aff=os.sched_getaffinity(0);os.sched_setaffinity(0,{min(aff)})
    rows=[]
    for i,c in enumerate(cases):
        if i%SHARDS!=shard:continue
        src=pathlib.Path(c["id"])
        for rep in range(REPS):
            modes=list(MODES);random.Random(PROTO+c["sha256"]+str(rep)).shuffle(modes)
            votes=set()
            for mode in modes:
                row=dict(protocol=PROTO,source_manifest_sha256=source_sha,shard=shard,
                    **c,**invoke(src,mode,rep))
                rows.append(row)
                if row["status"]!="TIMEOUT":
                    votes.add(row["status"])
                    need(len(votes)<=1,"SAT/UNSAT disagreement "+c["id"])
                print("R135_PAIRED",json.dumps(row,sort_keys=True),flush=True)
                write(ROOT/f"shard-{shard}.json",dict(protocol=PROTO,shard=shard,source_manifest_sha256=source_sha,
                    rows=rows,pinned_sha256={str(p):digest(p) for p in (KISSAT,CADICAL,R118)}))
    need(len(rows)==len(cases[shard::SHARDS])*REPS*len(MODES),"incomplete shard")
    print("R135_SHARD_PASS",shard,len(rows),flush=True)
def audit():
    source_sha,cases=read_sources()
    shards=[json.loads((ROOT/f"shard-{i}.json").read_text()) for i in range(SHARDS)]
    need(all(x["protocol"]==PROTO and x["source_manifest_sha256"]==source_sha for x in shards),"protocol or manifest drift")
    need(len(set(json.dumps(x["pinned_sha256"],sort_keys=True) for x in shards))==1,"binary pin mismatch")
    rows=[r for sh in shards for r in sh["rows"]]
    need(len(rows)==len(cases)*REPS*len(MODES),"missing paired rows")
    idx={};bysha={c["sha256"]:c for c in cases}
    for r in rows:
        need(r["sha256"] in bysha and bysha[r["sha256"]]["id"]==r["id"],"formula drift")
        need(r["mode"] in MODES and r["repeat"] in (0,1),"mode/repeat")
        need(r["status"] in ("SAT","UNSAT","TIMEOUT"),"bad status")
        need(abs(r["par2"]-(30 if r["status"]=="TIMEOUT" else r["seconds"]))<1e-5,"PAR2 wrong")
        if r["status"]=="SAT":need(r["proof"]=="source_SAT_witness_verified","SAT witness missing")
        if r["status"]=="UNSAT":need(r["proof"]=="UNSAT_without_independent_LRAT_proof","UNSAT proof tier")
        k=(r["sha256"],r["repeat"],r["mode"]);need(k not in idx,"duplicate");idx[k]=r
    for c in cases:
        for rep in range(REPS):
            need(len(set(idx[(c["sha256"],rep,m)]["status"] for m in MODES)-{"TIMEOUT"})<=1,"SAT/UNSAT contradiction")
    stats={}
    for m in MODES:
        a=[r for r in rows if r["mode"]==m];solved=[r["seconds"] for r in a if r["status"]!="TIMEOUT"]
        stats[m]=dict(trials=len(a),solved=len(solved),SAT=sum(r["status"]=="SAT" for r in a),
            UNSAT=sum(r["status"]=="UNSAT" for r in a),timeouts=len(a)-len(solved),
            par2_total_s=round(sum(r["par2"] for r in a),6),
            median_solved_wall_s=round(statistics.median(solved),6) if solved else None,
            total_wall_s=round(sum(r["seconds"] for r in a),6))
    comparisons={}
    for m in ("cadical","r118","r135"):
        diffs=[sum(idx[(c["sha256"],rep,m)]["par2"]-idx[(c["sha256"],rep,"kissat")]["par2"] for rep in range(REPS)) for c in cases]
        comparisons[m]=dict(gain_vs_kissat_pct=round(100*(stats["kissat"]["par2_total_s"]/stats[m]["par2_total_s"]-1),6),
            faster_formula_pairs=sum(d<-.00001 for d in diffs),
            slower_formula_pairs=sum(d>.00001 for d in diffs),
            regressions_2x=sum(sum(idx[(c["sha256"],rep,m)]["par2"] for rep in range(REPS))>=2*sum(idx[(c["sha256"],rep,"kissat")]["par2"] for rep in range(REPS)) for c in cases))
    selected=[r for r in rows if r["mode"]=="r135"]
    report=dict(protocol=PROTO,formulas=len(cases),measurements=len(rows),repeats=REPS,cap_s=CAP,
        source_manifest_sha256=source_sha,source_sha_verified=True,
        precommitted_thresholds=dict(binary_ratio=BINARY_THRESHOLD,horn_ratio=HORN_THRESHOLD),
        summary=stats,comparisons=comparisons,
        selector=dict(target_counts=dict(collections.Counter(r["selector_target"] for r in selected)),
            reason_counts=dict(collections.Counter(r["selector_reason"] for r in selected)),
            total_scan_s=round(sum(r["selector_cost_s"] for r in selected),6),
            median_scan_s=round(statistics.median(r["selector_cost_s"] for r in selected),6)),
        no_independent_unsat_proof=True,official_world_ranking_claim=False,
        verdict="NO_PROMOTION_UNTIL_INDEPENDENT_UNSAT_CERTIFICATION",
        note="New SHA-frozen 400-case source. No performance-based formula exclusion. All selector scan cost included. Same run, cap, repeated seed and pinned binaries; runner hardware may differ between shards.")
    write(ROOT/"report.json",report)
    with (ROOT/"paired.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print("R135_FINAL",json.dumps(report,sort_keys=True),flush=True)
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("command",choices=("run","audit"));p.add_argument("--shard",type=int,default=0)
    a=p.parse_args();{"run":lambda:run(a.shard),"audit":audit}[a.command]()
