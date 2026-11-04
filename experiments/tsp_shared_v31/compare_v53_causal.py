#!/usr/bin/env python3
"""V53: precommitted causal bidirectional edge-memory experiment.

Synthetic but exactly paired TSPLIB EUC_2D instances (new seeds 18..23).
Every agent sends edge votes in BOTH arms; only the reader changes. All
attempted local moves remain strictly improving. LKH3 is an external control.
Prepared before outcomes; no tuning on these seeds.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,random,statistics,time
from pathlib import Path
from drnas_v4 import fast_make
from drnas_v53 import run,warmup
from time_quality_v32 import lkh_trace,snapshot

PROTO="DRNAS-TSP-V53-BIDIRECTIONAL-SHARED-EDGE-CAUSAL-20261104-V1"
SEEDS=(18,19,20,21,22,23)
CITIES=(2000,5000)
REPS=(0,1)
SECONDS=30
CUTS=(2,4,8,15,30)
MODES=("sham","shared","LKH-3")
FIELDS=("protocol","seed","cities","rep","mode","checkpoint_s",
        "length_units","final_units","status","wall_s","first_incumbent_s",
        "coord_sha256","steps","accepted_moves","five_opt_moves",
        "shared_packets","shared_edge_votes","unique_sending_agents",
        "recipient_calls","nonzero_shared_credits","communication_s",
        "consumer_mode","git_sha","run_id")

def check(condition,message):
    if not condition:raise RuntimeError("V53_FAIL_CLOSED "+message)

def save(path,obj):
    Path(path).write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")

def selected_orders(seed,cities,rep):
    choices=list(MODES)
    rnd=random.Random(f"{PROTO}:{seed}:{cities}:{rep}")
    rnd.shuffle(choices)
    return choices

def measure(args):
    check(args.seed in SEEDS,"unregistered holdout seed")
    check(args.seconds==SECONDS,"declared cap drift")
    warmup()
    import os
    if hasattr(os,"sched_setaffinity"):
        allowed=os.sched_getaffinity(0)
        os.sched_setaffinity(0,{min(allowed)})
    output=Path(args.out);output.mkdir(parents=True,exist_ok=True)
    rows=[];raw=[]
    lkh=Path(args.lkh).resolve()
    check(lkh.is_file(),"LKH-3 binary missing")
    for cities in CITIES:
        coords,d,nn=fast_make(cities,args.seed)
        source_sha=hashlib.sha256(coords.tobytes()).hexdigest()
        del coords,d,nn
        for rep in REPS:
            for mode in selected_orders(args.seed,cities,rep):
                notes=""
                start=time.perf_counter()
                try:
                    if mode=="LKH-3":
                        r=lkh_trace(cities,args.seed,str(lkh),
                            output/"lkh"/f"{cities}-{rep}",args.seconds)
                        wall=time.perf_counter()-start
                    else:
                        started=time.perf_counter()
                        coords,d,nn=fast_make(cities,args.seed)
                        check(hashlib.sha256(coords.tobytes()).hexdigest()==source_sha,
                              "coordinate mutation")
                        r=run(cities,args.seed,d,nn,args.seconds,
                              mode="v53_"+mode,start=started)
                        wall=time.perf_counter()-start
                        check(r["consumer_mode"]==(
                            "incoming_messages" if mode=="shared" else "sham_zero_reads"),
                            "wrong read channel")
                        check(r["final"]>0 and r["shared_packets"]>0,
                              "no successful agent-to-agent messages")
                        check(r["recipient_calls"]>0,"recipient never consulted channel")
                    check(r["events"] and all(
                          a[1]>=b[1] for a,b in zip(r["events"],r["events"][1:])),
                          "invalid best-so-far trajectory")
                    status="ok"
                except Exception as exc:
                    notes=type(exc).__name__+":"+str(exc)[:250]
                    status="error";r=dict(events=[])
                    wall=time.perf_counter()-start
                    print("V53_CASE_ERROR",cities,args.seed,rep,mode,notes,flush=True)
                telemetry=dict(
                    steps=r.get("steps",0),accepted_moves=r.get("accepted_moves",0),
                    five_opt_moves=r.get("five_opt_moves",0),
                    shared_packets=r.get("shared_packets",0),
                    shared_edge_votes=r.get("shared_edge_votes",0),
                    unique_sending_agents=r.get("unique_sending_agents",0),
                    recipient_calls=r.get("recipient_calls",0),
                    nonzero_shared_credits=r.get("nonzero_shared_credits",0),
                    communication_s=round(r.get("comm_seconds",0.0),5),
                    consumer_mode=r.get("consumer_mode","reference"))
                for sec in CUTS:
                    best=snapshot(r["events"],sec)
                    row=dict(protocol=PROTO,seed=args.seed,cities=cities,rep=rep,
                        mode=mode,checkpoint_s=sec,
                        length_units=round(best/1000,6) if best is not None else "",
                        final_units=round(r["events"][-1][1]/1000,6)
                            if r["events"] else "",
                        status=status if status=="error" else
                            ("ok" if best is not None else "pending"),
                        wall_s=round(wall,5),
                        first_incumbent_s=round(r["events"][0][0],5)
                            if r["events"] else "",
                        coord_sha256=source_sha,**telemetry,
                        git_sha=os.environ.get("GITHUB_SHA","local"),
                        run_id=os.environ.get("GITHUB_RUN_ID","local"))
                    rows.append(row)
                raw.append(dict(seed=args.seed,cities=cities,rep=rep,mode=mode,
                    status=status,notes=notes,events=r["events"],
                    **telemetry))
                save(output/"progress.json",dict(protocol=PROTO,seed=args.seed,
                    rows=len(rows),data=raw))
                print("V53_TRIAL",json.dumps(dict(cities=cities,seed=args.seed,
                    rep=rep,mode=mode,status=status,
                    final_units=rows[-1]["final_units"],
                    sends=telemetry["shared_packets"],
                    senders=telemetry["unique_sending_agents"],
                    recipient_reads=telemetry["recipient_calls"],
                    notes=notes)),flush=True)
    with (output/"results.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS)
        w.writeheader();w.writerows(rows)
    check(len(rows)==len(CITIES)*len(REPS)*len(MODES)*len(CUTS),
          "incomplete paired trials")
    check(all(r["status"]!="error" for r in rows),"one or more methods crashed")
    print("V53_SHARD_PASS",args.seed,len(rows),flush=True)

def audit(args):
    combined=Path(args.combined)
    files=sorted(combined.glob("v53-seed-*/results/results.csv"))
    check(len(files)==len(SEEDS),"missing seed shards")
    all_rows=[]
    for p in files:
        rows=list(csv.DictReader(p.open()))
        expected_seed=int(p.parent.parent.name.rsplit("-",1)[-1])
        check(len(rows)==len(CITIES)*len(REPS)*len(MODES)*len(CUTS),
              "incomplete shard rows")
        check(all(int(r["seed"])==expected_seed for r in rows),"shard mix")
        all_rows.extend(rows)
    groups={}
    for r in all_rows:
        check(r["protocol"]==PROTO,"wrong version")
        key=(int(r["cities"]),int(r["seed"]),int(r["rep"]),int(r["checkpoint_s"]))
        group=groups.setdefault(key,{})
        check(r["mode"] not in group,"duplicate mode")
        group[r["mode"]]=r
    check(len(groups)==len(SEEDS)*len(CITIES)*len(REPS)*len(CUTS),"incomplete keys")
    records=[]
    for (cities,seed,rep,sec),method in sorted(groups.items()):
        check(set(method)==set(MODES),"paired method missing")
        check(len({r["coord_sha256"] for r in method.values()})==1,
              "different TSPLIB input")
        check(all(r["status"]!="error" for r in method.values()),"solver crash")
        for name in ("sham","shared"):
            q=method[name]
            check(int(q["shared_packets"])>0
                and int(q["recipient_calls"])>0
                and int(q["unique_sending_agents"])>=2,
                "two-way broadcast not exercised")
            check(q["consumer_mode"]==(
                "incoming_messages" if name=="shared" else "sham_zero_reads"),
                "read-channel ablation invalid")
        if sec!=SECONDS:continue
        check(all(method[m]["length_units"] for m in MODES),
              "missing 30-second final route")
        clean=float(method["sham"]["length_units"])
        shared=float(method["shared"]["length_units"])
        ref=float(method["LKH-3"]["length_units"])
        records.append(dict(cities=cities,seed=seed,rep=rep,
            sham=clean,shared=shared,lkh=ref,
            saved_units=round(clean-shared,6),
            improvement_pct=round(100*(clean-shared)/clean,7),
            gap_to_lkh_pct=round(100*(shared-ref)/ref,7),
            shared_messages=int(method["shared"]["shared_packets"]),
            senders=int(method["shared"]["unique_sending_agents"]),
            recipient_calls=int(method["shared"]["recipient_calls"])))
    check(len(records)==len(SEEDS)*len(CITIES)*len(REPS),"missing finals")
    bycase={}
    for r in records:
        bycase.setdefault((r["cities"],r["seed"]),[]).append(r)
    diffs=[statistics.mean(x["improvement_pct"] for x in v) for v in bycase.values()]
    mean=statistics.mean(diffs)
    median=statistics.median(diffs)
    # Hierarchical unit of resampling is independent city/seed case,
    # not two correlated repeats nor time checkpoints.
    rng=random.Random(511853)
    draws=[statistics.mean(rng.choices(diffs,k=len(diffs)))
           for _ in range(4000)]
    draws.sort()
    ci=(draws[99],draws[3899])
    wins=sum(x>0 for x in diffs)
    losses=sum(x<0 for x in diffs)
    ties=len(diffs)-wins-losses
    # Rule is fixed before seeing outcome.
    confirmed=ci[0]>0 and wins>losses and wins>=8
    summary=dict(protocol=PROTO,instances=len(bycase),repeats=len(REPS),
        methods=list(MODES),checkpoints=list(CUTS),seconds=SECONDS,
        independent_case_mean_improvement_pct=mean,
        case_median_improvement_pct=median,
        bootstrap_clustered_95pct_ci_pct=ci,
        win_cases=wins,loss_cases=losses,tie_cases=ties,
        communication_benefit_confirmed_on_this_cohort=confirmed,
        next_step="fresh unseen holdout needed for generalization",
        limitations=[
          "TSPLIB-compatible Euclidean instances are generated deterministically and are not named industrial TSPLIB instances.",
          "64 virtual agent states run sequentially, not on 64 CPU cores.",
          "Sham still receives champion-tour copying, so the test isolates only incremental edge-memory communication.",
          "LKH process timing excludes external coordinate creation; checkpoint timing therefore differs slightly.",
          "Results on development seeds cannot establish a universal SAT/TSP breakthrough.",
          "No test-tuning or selecting faster source IDs after outcomes."])
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True)
    save(out/"summary.json",summary)
    save(out/"paired_results.json",records)
    with (out/"paired_results.csv").open("w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]))
        w.writeheader();w.writerows(records)
    md=["# DRNAS TSP v5.3 — bidirectional communication causal test","",
        f"Independent instances: {len(bycase)}; repeats: {len(REPS)}",
        f"Compared same CPU budget {SECONDS} s: shared vs message-written-but-hidden sham; LKH-3.",
        f"Mean percentage quality gain: {mean:+.5f}% (higher is better).",
        f"Case clustered 95% bootstrap CI: [{ci[0]:+.5f}%, {ci[1]:+.5f}%].",
        f"Win/tie/loss: {wins}/{ties}/{losses}.",
        f"Confirmed within this predeclared cohort: {confirmed}.","",
        "| Cities | Seed | Mean sham | Mean shared | Mean LKH | Shared gain % |",
        "|---:|---:|---:|---:|---:|---:|"]
    for key,v in sorted(bycase.items()):
        md.append("| {} | {} | {:.4f} | {:.4f} | {:.4f} | {:+.5f}% |".format(
            key[0],key[1],
            statistics.mean(x["sham"] for x in v),
            statistics.mean(x["shared"] for x in v),
            statistics.mean(x["lkh"] for x in v),
            statistics.mean(x["improvement_pct"] for x in v)))
    md.extend(["","Caveat: 64 sequential virtual agents. LKH process timings differ.",
         "No world-record claim; only an isolated incremental edge-sharing study."])
    (out/"v53-report.md").write_text("\n".join(md)+"\n")
    print("V53_CAUSAL_AUDIT_PASS",json.dumps({k:v for k,v in summary.items()
        if k in ("instances","independent_case_mean_improvement_pct",
                 "bootstrap_clustered_95pct_ci_pct","win_cases","loss_cases",
                 "communication_benefit_confirmed_on_this_cohort")}),flush=True)

if __name__=="__main__":
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="mode",required=True)
    q=sub.add_parser("measure")
    q.add_argument("--seed",type=int,required=True)
    q.add_argument("--seconds",type=int,default=SECONDS)
    q.add_argument("--lkh",required=True)
    q.add_argument("--out",required=True)
    q=sub.add_parser("audit")
    q.add_argument("--combined",required=True)
    q.add_argument("--out",required=True)
    a=p.parse_args()
    if a.mode=="measure":measure(a)
    else:audit(a)
