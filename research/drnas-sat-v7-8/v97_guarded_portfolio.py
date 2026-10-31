#!/usr/bin/env python3
"""DRNAS V9.7: frozen two-core guarded prediction, prospective 24 new SATLIB CNFs.

The original V9.2 Sparse solver ALWAYS runs on its own physical core; a
speculative independent CaDiCaL solver runs on another core. The selected
validated first answer wins. On 1 physical core the scheme falls back to
ordinary V9.2 Sparse (no speculative process). There is NO formal zero-regret
guarantee: startup, hardware contention, memory bandwidth and core availability
can still cause a slowdown. Report both time and added CPU cost.
"""
import argparse,collections,csv,hashlib,io,json,os,random,statistics,subprocess,tarfile,time
from pathlib import Path
from v96_predictive_holdout import FAMILIES,cnf_clean,parse_cnf,predict

SALT="drnas-v97-safe-hedge-20261031-frozen-v1"
CAP=4.0
REPEATS=3
MODES=("ca_plain","v92_sparse","v92_structural","v97_guarded",
       "v97_hedge_broad","v97_hedge_plain")
ROUTING=("v97_guarded","v97_hedge_broad","v97_hedge_plain")

def physical_cpus():
    avail=sorted(os.sched_getaffinity(0))
    if not avail:return []
    groups={}
    for c in avail:
        try:
            base=Path("/sys/devices/system/cpu/cpu%d/topology"%c)
            key=((base/"physical_package_id").read_text().strip(),
                 (base/"core_id").read_text().strip())
        except (OSError,ValueError):
            key=("fallback",str(c))
        groups.setdefault(key,[]).append(c)
    return [cs[0] for cs in groups.values()]

def verify_answer(proc,mode,expected):
    stdout,stderr=proc.communicate(timeout=1)
    if proc.returncode!=0:
        raise ValueError("invalid process %s rc=%s %s"%(mode,proc.returncode,stderr[-250:]))
    lines=[line for line in stdout.splitlines() if line.startswith("DRNAS_CAUSAL\t")]
    if len(lines)!=1:raise ValueError("missing/duplicate DRNAS_CAUSAL %s"%mode)
    attrs=dict(part.split("=",1) for part in lines[0].split("\t")[1:])
    if attrs.get("mode")!=mode or attrs.get("answer")!=expected:
        raise ValueError("solver wrong mode/status for %s: %s"%(mode,attrs))
    return attrs

def start_solver(exe,mode,cnf,seed,core):
    def pin():os.sched_setaffinity(0,{core})
    return subprocess.Popen([exe,mode,str(cnf),str(seed)],
         stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
         preexec_fn=pin,start_new_session=True)

def kill(p):
    if p.poll() is None:
        p.kill()
    try:p.communicate(timeout=1)
    except subprocess.TimeoutExpired:
        p.kill();p.communicate()

def race(exe,cnf,seed,truth,choice,cores,deadline):
    """Return winner before cap, or TIMEOUT; always keeps sparse alive."""
    if len(cores)<2:
        p=None
        try:
            p=start_solver(exe,"v92_sparse",cnf,seed,cores[0])
            p.communicate(timeout=max(.001,deadline-time.monotonic()))
            if p.returncode is None:raise subprocess.TimeoutExpired("",0)
            # communicate() above consumed stdout; use direct subprocess for 1 core instead
            raise RuntimeError("one-core branch should use direct fallback")
        finally:
            if p is not None:kill(p)
    running={}
    winner=None;attrs={}
    try:
        # Give baseline the first start, so it has scheduling priority.
        running["v92_sparse"]=start_solver(exe,"v92_sparse",cnf,seed,cores[0])
        running[choice]=start_solver(exe,choice,cnf,seed,cores[1])
        while time.monotonic()<deadline:
            for mode,p in tuple(running.items()):
                if p.poll() is not None:
                    result=verify_answer(p,mode,truth)
                    winner=mode;attrs=result
                    break
            if winner:break
            time.sleep(.002)
    finally:
        for mode,p in running.items():
            if mode!=winner:kill(p)
    if winner:return truth,winner,attrs
    return "TIMEOUT","timeout",{}

def load_cases(previous,prior_v96,shard):
    fam=FAMILIES[shard]
    src=Path(previous)/("shard-"+str(shard))
    meta=json.loads((src/"manifest.json").read_text())
    screened=json.loads((src/"screen.json").read_text())
    prev=json.loads((Path(prior_v96)/("v96-shard-"+str(shard))/"results"/"manifest.json").read_text())
    assert meta["group"]==fam and len(screened)==20 and len(prev["cases"])==6
    assert all(x["family"]==fam for x in prev["cases"])
    excluded={x["source_member"] for x in screened}
    excluded|={x["source_member"] for x in prev["cases"]}
    archive=(src/(fam+".tar.gz")).read_bytes()
    assert hashlib.sha256(archive).hexdigest()==meta["archive_sha256"]
    with tarfile.open(fileobj=io.BytesIO(archive),mode="r:gz") as t:
        files={m.name:m for m in t if m.isfile() and m.name.endswith(".cnf")}
        unseen=[name for name in files if name not in excluded]
        ranked=sorted(unseen,key=lambda s:hashlib.sha256((SALT+"/"+s).encode()).hexdigest())
        assert len(ranked)>=6 and len(excluded)>=26
        out=[]
        for i,member in enumerate(ranked[:6]):
            body=t.extractfile(files[member]).read()
            clean=cnf_clean(body)
            n,clauses=parse_cnf(clean)
            out.append(dict(id=fam+"-"+str(i),family=fam,source_member=member,
                     sha256=hashlib.sha256(clean).hexdigest(),
                     original_sha256=hashlib.sha256(body).hexdigest(),
                     truth="UNSAT" if fam.startswith("uuf") else "SAT",
                     vars=n,clauses=len(clauses),body=clean))
    return out

def benchmark(args):
    root=Path(args.out);root.mkdir(parents=True,exist_ok=True)
    cpus=physical_cpus()
    if not cpus:raise RuntimeError("no accessible CPU")
    cases=load_cases(args.source,args.prior,args.shard)
    (root/"manifest.json").write_text(json.dumps({
        "protocol":SALT,"shard":args.shard,"cap":CAP,"repeats":REPEATS,
        "physical_cpu_slots":cpus[:2],"cases":[{k:v for k,v in c.items() if k!="body"} for c in cases]},indent=2))
    exe=str(Path(args.exe).resolve())
    fields=("id","family","sha256","rep","mode","routed","winner","status",
            "wall_s","score","physical_cores","error")
    with (root/"raw.csv").open("w",newline="") as fp:
        wr=csv.DictWriter(fp,fieldnames=fields);wr.writeheader()
        for c in cases:
            cnf=root/(c["id"]+".cnf");cnf.write_bytes(c["body"])
            for rep in range(REPEATS):
                order=list(MODES)
                random.Random(int(c["sha256"][:8],16)+rep*757).shuffle(order)
                for mode in order:
                    start=time.monotonic();deadline=start+CAP
                    score="";route=mode;winner="";status="ERROR";error=""
                    try:
                        if mode=="v97_guarded":
                            decision,score=predict(c["body"])
                            route="v92_structural" if decision=="v92_structural" else "ca_plain"
                        elif mode=="v97_hedge_broad":route="v92_structural"
                        elif mode=="v97_hedge_plain":route="ca_plain"
                        if mode in ROUTING and len(cpus)>1:
                            status,winner,_=race(exe,cnf,
                                (830031+rep*527+int(c["sha256"][:8],16))%(2**32),
                                c["truth"],route,cpus,time.monotonic()+max(0,deadline-time.monotonic()))
                        else:
                            if mode in ROUTING:route="v92_sparse"
                            seed=(830031+rep*527+int(c["sha256"][:8],16))%(2**32)
                            process=start_solver(exe,route,cnf,seed,cpus[0])
                            try:
                                process.wait(timeout=max(.001,deadline-time.monotonic()))
                                verify_answer(process,route,c["truth"])
                                winner=route;status=c["truth"]
                            finally:
                                kill(process)
                    except subprocess.TimeoutExpired:
                        status="TIMEOUT";winner="timeout"
                    except Exception as e:
                        error=str(e);status="ERROR"
                    elapsed=min(CAP,time.monotonic()-start)
                    if elapsed>=CAP and status!="ERROR":
                        status="TIMEOUT";winner="timeout"
                    row=dict(id=c["id"],family=c["family"],sha256=c["sha256"],
                       rep=rep,mode=mode,routed=route,winner=winner,status=status,
                       wall_s=round(elapsed,6),score=score,
                       physical_cores=len(cpus),error=error)
                    wr.writerow(row);fp.flush()
                    print("V97_TRIAL",c["id"],rep,mode,"=>",route,
                        winner,status,row["wall_s"],flush=True)
                    if status=="ERROR":raise RuntimeError(str(row))
            cnf.unlink()
    print("V97_SHARD_PASS",args.shard,flush=True)

def audit(args):
    root=Path(args.source);cases=[];rows=[]
    for i in range(4):
        folder=root/("v97-shard-"+str(i))/"results"
        manifest=json.loads((folder/"manifest.json").read_text())
        assert manifest["protocol"]==SALT and manifest["shard"]==i
        assert manifest["cap"]==CAP and manifest["repeats"]==REPEATS
        assert len(manifest["cases"])==6
        cases.extend(manifest["cases"])
        rows+=list(csv.DictReader((folder/"raw.csv").open()))
    assert len(cases)==24 and len({x["sha256"] for x in cases})==24
    assert len(rows)==len(cases)*REPEATS*len(MODES)
    assert len({(x["sha256"],int(x["rep"]),x["mode"]) for x in rows})==len(rows)
    assert all(x["status"] in ("SAT","UNSAT","TIMEOUT") and
               (x["status"]==("UNSAT" if x["family"].startswith("uuf") else "SAT")
                 or x["status"]=="TIMEOUT") and not x["error"] for x in rows)
    costs={}
    for c in cases:
        costs[c["sha256"]]={}
        for mode in MODES:
            cc=[x for x in rows if x["sha256"]==c["sha256"] and x["mode"]==mode]
            assert len(cc)==REPEATS
            costs[c["sha256"]][mode]=statistics.mean(
                float(x["wall_s"]) if x["status"]!="TIMEOUT" else CAP*2 for x in cc)
    summary={}
    for mode in MODES:
        rr=[r for r in rows if r["mode"]==mode]
        summary[mode]={"solved":sum(r["status"]!="TIMEOUT" for r in rr),
            "mean_PAR2":statistics.mean(
                float(r["wall_s"]) if r["status"]!="TIMEOUT" else CAP*2 for r in rr)}
    evaluations={}
    for mode in ROUTING:
        relative=[costs[c["sha256"]]["v92_sparse"]/
                  costs[c["sha256"]][mode] for c in cases]
        evaluations[mode]={"wins_gt_1p25x":sum(r>1.25 for r in relative),
            "losses_below_0p8x":sum(r<.8 for r in relative),
            "worst_slowdown_over_sparse":max(1/r for r in relative),
            "mean_speedup_over_sparse":summary["v92_sparse"]["mean_PAR2"]/summary[mode]["mean_PAR2"]}
    o=Path(args.out);o.mkdir(parents=True,exist_ok=True)
    data=dict(protocol=SALT,completed_rows=len(rows),cases=len(cases),
        repeats=REPEATS,cap=CAP,summary=summary,evaluations=evaluations,
        portfolio_choices=collections.Counter(x["routed"] for x in rows if x["mode"]=="v97_guarded"),
        portfolio_winners=collections.Counter(x["winner"] for x in rows if x["mode"]=="v97_guarded"),
        per_case=[dict(case=c["id"],truth=c["truth"],sha256=c["sha256"],
                       PAR2=costs[c["sha256"]]) for c in cases],
        warnings=["No mathematically guaranteed zero-regression: scheduler and startup overhead remain",
            "CPU resource usage can nearly double under parallel hedging",
            "SATLIB same families as prior runs; disjoint source members but not external competition",
            "UNSAT official archive labels and agreement, without independently checked proof"])
    (o/"report.json").write_text(json.dumps(data,indent=2))
    lines=["# DRNAS V9.7 guarded predictive portfolio: 24 fresh unscreened SATLIB CNFs","",
      "72 paired attempts per arm, 4 s wall cap, PAR2=8 s; two independent physical cores for portfolio when available.","",
      "| Strategy | Solved/72 | Mean PAR2 |","|---|---:|---:|"]
    for mode in MODES:
        x=summary[mode];lines.append("| %s | %s/72 | %.6fs |"%(mode,x["solved"],x["mean_PAR2"]))
    for mode in ROUTING:
        x=evaluations[mode];lines.append("\n%s vs Sparse: wins=%d losses=%d, worst slowdown=%.3fx"%(
            mode,x["wins_gt_1p25x"],x["losses_below_0p8x"],x["worst_slowdown_over_sparse"]))
    lines+=["","Predicted candidate counts: "+str(dict(data["portfolio_choices"])),
       "Returned winner counts: "+str(dict(data["portfolio_winners"])),
       "Caution: no unconditional no-regression guarantee, and CPU cost is higher."]
    text="\n".join(lines)+"\n"
    (o/"report.md").write_text(text);print(text,flush=True)

def audit_v96(args):
    root=Path(args.prior);modes=("ca_plain","v92_sparse","v92_structural","v96_predict")
    rows=[]
    for i in range(4):
        folder=root/("v96-shard-"+str(i))/"results"
        manifest=json.loads((folder/"manifest.json").read_text())
        assert len(manifest["cases"])==6
        rows+=list(csv.DictReader((folder/"raw.csv").open()))
    assert len(rows)==288
    for mode in modes:
        rr=[r for r in rows if r["mode"]==mode]
        assert len(rr)==72 and all(not r["error"] for r in rr)
        solved=sum(r["status"] in ("SAT","UNSAT") for r in rr)
        par2=statistics.mean(float(r["wall_s"]) if r["status"] in ("SAT","UNSAT") else 8 for r in rr)
        print("V96_SAVED_AUDIT",mode,"solved",solved,"mean_PAR2",round(par2,6),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("command",choices=("bench","audit","audit-v96"))
    p.add_argument("--source",required=True);p.add_argument("--prior",default="prior_v96")
    p.add_argument("--out",default="results");p.add_argument("--exe",default="./v92_probe")
    p.add_argument("--shard",type=int,default=0)
    args=p.parse_args()
    if args.command=="bench":benchmark(args)
    elif args.command=="audit":audit(args)
    else:audit_v96(args)
