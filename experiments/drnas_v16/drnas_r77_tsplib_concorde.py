#!/usr/bin/env python3
"""DRNAS R77 TSPLIB95 benchmark vs OFFICIAL Waterloo Concorde 2003 exact TSP solver.

Pilot: frozen three classical EUC_2D instances with known independent optima.
Same TSPLIB distance matrices, same exact objective, same runner, 12s cap/arm.
Three arms: R75 four processes pinned to ONE CPU; Concorde ONE CPU;
and R75 four processes pinned to FOUR distinct CPUs (not resource-matched).
All final tours are checked against original TSPLIB weights. Concorde counted
PROVEN only if actual completion announces Optimal Solution AND the written
Hamiltonian tour independently verifies exact integer objective. Known published
optima are used strictly by the AUDIT, never passed to either solver.
No soft deferral, no Kissat, and no claims for unfinished runs.
"""
from __future__ import annotations
import argparse, gzip, hashlib, json, math, os, random, re, subprocess
import tempfile, time, urllib.request
from pathlib import Path
import drnas_r75_shared_route as drnas

PROTO="DRNAS-R77-TSPLIB-CONCORDE-20261104-v1"
SEED=7711042026
KNOWN={"eil51":(51,426),"berlin52":(52,7542),"st70":(70,675)}
CASES=tuple(KNOWN)
MODES=("drnas_shared_1core","concorde_exact_1core","drnas_shared_4core")
REPS=2;SHARDS=3;CAP=12.0
OFFICIAL="https://comopt.ifi.uni-heidelberg.de/software/TSPLIB95/tsp"
MIRROR="https://raw.githubusercontent.com/pdrozdowski/TSPLib.Net/master/TSPLIB95/tsp"

def ck(ok,s):
    if not ok:raise RuntimeError("R77_FAIL_CLOSED "+str(s))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def parse_tsplib(raw):
    text=raw.decode("utf-8-sig")
    attrs={};rows={};section=False
    for rawline in text.splitlines():
        line=rawline.strip()
        if not line:continue
        if line.upper()=="NODE_COORD_SECTION":
            section=True;continue
        if line.upper()=="EOF":break
        if not section:
            if ":" in line:
                key,val=line.split(":",1)
                attrs[key.strip().upper()]=val.strip()
            continue
        parts=line.split()
        ck(len(parts)>=3,"bad coordinate")
        k=int(parts[0])
        ck(k not in rows,"duplicate coordinate")
        rows[k]=(float(parts[1]),float(parts[2]))
    ck(attrs.get("TYPE")=="TSP" and attrs.get("EDGE_WEIGHT_TYPE")=="EUC_2D",
       "only symmetric EUC_2D supported")
    n=int(attrs.get("DIMENSION","0"))
    ck(n>=4 and set(rows)==set(range(1,n+1)),"wrong coordinates/dimension")
    xy=[rows[i] for i in range(1,n+1)]
    # Official TSPLIB NINT Euclidean edge weights: int(sqrt(sum squares) + 0.5).
    d=[[0 if i==j else int(math.hypot(xy[i][0]-xy[j][0],
           xy[i][1]-xy[j][1])+0.5) for j in range(n)] for i in range(n)]
    ck(all(d[i][j]==d[j][i] for i in range(n) for j in range(n)),
       "asymmetric EUC_2D")
    return attrs,xy,d

def fetch_one(name):
    attempts=[]
    for url,compressed in ((f"{OFFICIAL}/{name}.tsp.gz",True),
                           (f"{MIRROR}/{name}.tsp",False)):
        try:
            with urllib.request.urlopen(urllib.request.Request(
                url,headers={"User-Agent":"DRNAS-research-R77"}),timeout=25) as f:
                data=f.read(1_000_001)
            ck(len(data)<1_000_001,"overlong TSPLIB source")
            raw=gzip.decompress(data) if compressed else data
            parsed=parse_tsplib(raw)
            return raw,url,parsed
        except Exception as e:
            attempts.append((url,type(e).__name__,str(e)[:120]))
    raise RuntimeError("TSPLIB unavailable "+json.dumps(attempts))

def freeze(folder):
    root=Path(folder);root.mkdir(parents=True,exist_ok=True)
    cases=[]
    for name in CASES:
        raw,url,(attrs,xy,d)=fetch_one(name)
        n,opt=KNOWN[name]
        ck(len(d)==n and attrs.get("NAME","").lower()==name.lower(),
           "wrong TSPLIB identity "+name)
        src=root/(name+".tsp");src.write_bytes(raw)
        first,initial=drnas.nearest_neighbor(d)
        entry=dict(name=name,file=src.name,source=url,sha256=sha(src),
                   known_optimum_for_audit=opt,dimension=n,
                   initial_upper=initial,raw_bytes=len(raw))
        cases.append(entry)
        print("R77_TSPLIB_FROZEN",name,n,url,
              "initial_upper",initial,"source_sha",entry["sha256"],flush=True)
    manifest=dict(protocol=PROTO,cases=cases,methods=list(MODES),cap_s=CAP,
                  repeats=REPS,seed=SEED,shards=SHARDS,
                  binary_source="official Waterloo Linux Concorde 03.12.19, 32-bit static",
                  limitations=[
                    "Three previously public TSPLIB EUC_2D instances, NOT blind",
                    "One-core DRNAS uses four processes all pinned to the same CPU",
                    "Four-core DRNAS is supplementary; not hardware-equal to Concorde",
                    "Concorde binary precompiled for historical 32-bit Linux; differing ISA/compilation may matter",
                    "Input parsing, process startup and solver time are in the per-trial wall metric",
                    "Concorde without validated explicit tour is recorded unproven, never given a win",
                    "Published known optimum used for AUDIT only, never supplied to algorithms",
                    "12-second capped pilot; two repetitions; larger evaluation needed",
                    "Do NOT reinterpret this as DRNAS SAT versus Kissat performance"])
    (root/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
    (root/"sources.sha256").write_text(
        "".join(c["sha256"]+"  "+c["file"]+"\n" for c in cases))
    print("R77_FREEZE_PASS",len(cases),sha(root/"manifest.json"),flush=True)

def parse_concorde_tour(path,n):
    raw=Path(path).read_text()
    vals=list(map(int,re.findall(r"-?\d+",raw)))
    ck(len(vals)==n+1 and vals[0]==n,"Concorde .sol format mismatch")
    tour=vals[1:]
    ck(len(tour)==n and set(tour)==set(range(n)),
       "Concorde .sol not a Hamiltonian permutation")
    # Rotate tour to 0; closes at zero.
    idx=tour.index(0)
    return tour[idx:]+tour[:idx]+[0]

def run_concorde(d,src,binary,cpu,cap,seed=99):
    start=time.monotonic()
    initial,initial_cost=drnas.nearest_neighbor(d)
    with tempfile.TemporaryDirectory(prefix="r77-concorde-") as tmp:
        out=Path(tmp)/"concorde.sol"
        cmd=[str(binary),"-s",str(seed),"-o",str(out),str(src)]
        rc=None;timeout=False;output=""
        try:
            p=subprocess.run(cmd,cwd=tmp,capture_output=True,text=True,
                             errors="replace",timeout=cap)
            rc=p.returncode;output=(p.stdout+"\n"+p.stderr)
        except subprocess.TimeoutExpired as e:
            timeout=True
            output=((e.stdout or b"").decode("utf-8","replace") if isinstance(e.stdout,bytes) else (e.stdout or ""))
        wall=time.monotonic()-start
        matches=re.findall(r"Optimal Solution:\s*([0-9]+(?:\.[0-9]+)?)",
                           output,re.IGNORECASE)
        best=initial_cost;tour=initial;proved=False;has_witness=out.exists()
        if matches:
            ck(not timeout and rc==0,"Concorde claimed optimum despite crash/time cap")
            ck(has_witness,"Concorde claimed optimum but has no tour")
            route=parse_concorde_tour(out,len(d))
            value=drnas.route_cost(d,route)
            announced=float(matches[-1])
            ck(abs(value-announced)<=0.01,"Concorde solution objective differs from verified tour")
            best=value;tour=route;proved=wall<=cap
        return dict(mode="concorde_exact_1core",best=best,tour=tour,
            proven_optimum=proved,elapsed_s=round(min(cap,wall),6),
            actual_wall_s=round(wall,6),cores=1,
            reported_optimal=bool(matches),witness_written=has_witness,
            timed_out=timeout,returncode=rc,
            stdout_tail=output[-2500:],
            initial_upper=initial_cost)

def run_drnas(d,cpus,mode,cap):
    ck(mode in ("drnas_shared_1core","drnas_shared_4core"),"mode")
    assigned=[cpus[0]]*4 if mode=="drnas_shared_1core" else cpus[:4]
    start=time.monotonic()
    r=drnas.trial(d,"shared",assigned,cap)
    wall=time.monotonic()-start
    return dict(mode=mode,best=r["best"],tour=r["tour"],
      proven_optimum=r["proven_optimum"] and wall<=cap,
      elapsed_s=round(min(wall,cap),6),actual_wall_s=round(wall,6),
      cores=1 if mode=="drnas_shared_1core" else 4,
      workers_completed=r["finished_workers"],visited_nodes=r["nodes"],
      pruned_branches=r["pruned"],shared_updates=r["signals_sent"],
      initial_upper=r["initial_upper"])

def measure(a):
    root=Path(a.sources)
    m=json.loads((root/"manifest.json").read_text())
    ck(m["protocol"]==PROTO and len(m["cases"])==SHARDS and
       m["cap_s"]==CAP and m["methods"]==list(MODES),"manifest drift")
    ck(0<=a.shard<SHARDS,"bad shard")
    binary=Path(a.concorde).resolve()
    ck(binary.is_file() and os.access(binary,os.X_OK),
       "official Concorde binary missing or not executable")
    cpus=sorted(os.sched_getaffinity(0))
    ck(len(cpus)>=4,"requires four available runner cpus")
    out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
    (out/"meta.json").write_text(json.dumps(dict(
        protocol=PROTO,shard=a.shard,manifest_sha=sha(root/"manifest.json"),
        binary_sha=sha(binary),cpus=cpus[:4]),indent=2)+"\n")
    rows=[]
    for c in m["cases"][a.shard::SHARDS]:
        src=(root/c["file"]).resolve()
        ck(sha(src)==c["sha256"],"TSPLIB source hash drift")
        attrs,xy,d=parse_tsplib(src.read_bytes())
        ck(len(d)==c["dimension"],"dimension drift")
        first,initial=drnas.nearest_neighbor(d)
        ck(initial==c["initial_upper"],"nearest initial state drift")
        for rep in range(REPS):
            modes=list(MODES)
            random.Random(int(hashlib.sha256(
                 (c["sha256"]+str(rep)+PROTO).encode()).hexdigest(),16)).shuffle(modes)
            for mode in modes:
                original_affinity=os.sched_getaffinity(0)
                try:
                    os.sched_setaffinity(0,
                       {cpus[0]} if mode!="drnas_shared_4core" else set(cpus[:4]))
                    r=(run_concorde(d,src,binary,cpus[0],CAP)
                       if mode=="concorde_exact_1core"
                       else run_drnas(d,cpus,mode,CAP))
                finally:os.sched_setaffinity(0,original_affinity)
                drnas.validate(d,r["tour"],r["best"])
                ck(r["initial_upper"]==initial and r["best"]<=initial,
                    "invalid initial route or worsening")
                ck(r["best"]>=c["known_optimum_for_audit"],
                    "claimed cost less than known TSPLIB optimum")
                if r["proven_optimum"]:
                    ck(r["best"]==c["known_optimum_for_audit"],
                       "claim of proven wrong optimum")
                row=dict(instance=c["name"],source_sha=c["sha256"],rep=rep,**r)
                rows.append(row)
                (out/"rows.json").write_text(json.dumps(rows,indent=2)+"\n")
                print("R77_TRIAL",c["name"],rep,mode,
                   "cost",r["best"],"PROVEN" if r["proven_optimum"] else "UNPROVEN",
                   "wall",r["elapsed_s"],"cores",r["cores"],flush=True)
    ck(len(rows)==len(m["cases"][a.shard::SHARDS])*REPS*len(MODES),
       "partial benchmark")

def audit(a):
    root=Path(a.sources);m=json.loads((root/"manifest.json").read_text())
    ck(m["protocol"]==PROTO and len(m["cases"])==SHARDS,"manifest")
    allrows=[];seen=set();binary_hashes=set()
    for i in range(SHARDS):
        f=Path(a.combined)/f"r77-shard-{i}"/"results"
        meta=json.loads((f/"meta.json").read_text())
        ck(meta["shard"]==i and meta["protocol"]==PROTO and
           meta["manifest_sha"]==sha(root/"manifest.json"),
           "mixed manifest")
        binary_hashes.add(meta["binary_sha"])
        part=json.loads((f/"rows.json").read_text())
        ck(len(part)==len(m["cases"][i::SHARDS])*REPS*len(MODES),
           "missing attempts")
        for r in part:
            key=(r["instance"],r["rep"],r["mode"])
            ck(key not in seen,"duplicate attempt")
            seen.add(key)
            c=next(z for z in m["cases"] if z["name"]==r["instance"])
            ck(r["source_sha"]==c["sha256"],"incorrect source")
            _,_,d=parse_tsplib((root/c["file"]).read_bytes())
            drnas.validate(d,r["tour"],r["best"])
            ck(r["best"]>=c["known_optimum_for_audit"],"under known optimum")
            if r["proven_optimum"]:
                ck(r["best"]==c["known_optimum_for_audit"],
                   "incorrect proof")
        allrows+=part
    ck(len(binary_hashes)==1 and len(allrows)==SHARDS*REPS*len(MODES),
       "mixed binaries or missing paired trials")
    summary={}
    for mode in MODES:
        v=[r for r in allrows if r["mode"]==mode]
        summary[mode]=dict(attempts=len(v),
            proven=sum(r["proven_optimum"] for r in v),
            total_time_s=round(sum(r["elapsed_s"] for r in v),6),
            total_par2_s=round(sum(r["elapsed_s"] if r["proven_optimum"]
                                  else 2*CAP for r in v),6),
            cores=4 if mode.endswith("4core") else 1,
            total_best_cost=sum(r["best"] for r in v))
    result=dict(protocol=PROTO,summary=summary,binary_sha=next(iter(binary_hashes)),
                rows=allrows,limitations=m["limitations"])
    Path(a.json).write_text(json.dumps(result,indent=2)+"\n")
    lines=[
      "# R77: DRNAS shared-route exact TSP vs REAL official Concorde",
      "Pilot on frozen TSPLIB EUC_2D instances with original integer distances.",
      "Same hardware, precommitted 12-second cap per attempt and two repeats.",
      "| Algorithm | Cores | Proofs / 6 | Sum wall (s) | PAR2 (s) |",
      "|---|---:|---:|---:|---:|"]
    for mode in MODES:
        z=summary[mode]
        lines.append(f"| {mode} | {z['cores']} | {z['proven']}/{z['attempts']} | "+
                     f"{z['total_time_s']:.3f} | {z['total_par2_s']:.3f} |")
    lines+=["","| Instance | Known optimum | Rep | DRNAS 1core | Concorde 1core | DRNAS 4core |",
            "|---|---:|---:|---|---|---|"]
    for c in m["cases"]:
        for rep in range(REPS):
            x={r["mode"]:r for r in allrows if r["instance"]==c["name"] and r["rep"]==rep}
            def fmt(mode):
                v=x[mode];s="PROVEN" if v["proven_optimum"] else "unproven"
                return f"{v['best']} / {v['elapsed_s']:.3f}s ({s})"
            lines.append(f"| {c['name']} | {c['known_optimum_for_audit']} | {rep} | "+
                " | ".join(fmt(k) for k in MODES)+" |")
    lines+=["","### Caveats"]+["- "+x for x in m["limitations"]]
    Path(a.md).write_text("\n".join(lines)+"\n")
    print("R77_FINAL_AUDIT_PASS",json.dumps(summary,sort_keys=True),flush=True)

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="action",required=True)
    f=sub.add_parser("freeze");f.add_argument("--out",required=True)
    x=sub.add_parser("measure")
    for k in ("sources","out","concorde"):x.add_argument("--"+k,required=True)
    x.add_argument("--shard",type=int,required=True)
    x=sub.add_parser("audit")
    for k in ("sources","combined","json","md"):x.add_argument("--"+k,required=True)
    a=p.parse_args()
    {"freeze":lambda:freeze(a.out),"measure":lambda:measure(a),
     "audit":lambda:audit(a)}[a.action]()
if __name__=="__main__":main()
