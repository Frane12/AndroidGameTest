#!/usr/bin/env python3
"""Holdout paired TSP comparison on unseen-in-this-series seeds 3,4,5.

Identical TSPLIB EUC_2D instances, v4, v4.2 and bounded-escape v4.3,
plus real pinned LKH-3. For DRNAS, wall clock begins before coordinate
generation and distance matrix; LKH starts at binary process invocation.
LKH first incumbent times approximate log preprocessing + trial CPU time.
"""
import argparse,csv,json,time
from pathlib import Path
from drnas_v4 import fast_make,run as v4_run,warmup as old_warmup
from drnas_v42 import run as v42_run
from drnas_v43 import run as v43_run,warmup
from time_quality_v32 import lkh_trace,snapshot

CUTS=(2,4,6,8,10,15,20,25,30)
METHODS=("LKH-3","DRNAS v4","DRNAS v4.2 selective","DRNAS v4.3 bounded")

def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("--cities",type=int,nargs="+",default=[2000,5000])
    cli.add_argument("--seeds",type=int,nargs="+",default=[3,4,5])
    cli.add_argument("--seconds",type=int,default=30)
    cli.add_argument("--lkh",default="./LKH3/LKH")
    cli.add_argument("--out",default="drnas_tsp_v43_holdout.csv")
    cli.add_argument("--work",default="drnas_tsp_v43_logs")
    args=cli.parse_args()
    warmup()
    fields=["cities","seed","method","checkpoint_s","length_units","status",
        "first_incumbent_s","final_length_units","total_wall_s","prep_s",
        "steps","restart_waves","uphill_kicks","uphill_cost_units",
        "no_candidate_kicks","restart_lineage_best_updates",
        "communication_s","protected_elite_slots","notes"]
    output=Path(args.out);output.parent.mkdir(parents=True,exist_ok=True)
    with output.open("w",newline="") as fh:
        writer=csv.DictWriter(fh,fieldnames=fields);writer.writeheader()
        for n in args.cities:
            for seed in args.seeds:
                for method in METHODS:
                    try:
                        if method=="LKH-3":
                            r=lkh_trace(n,seed,args.lkh,Path(args.work),args.seconds)
                            prep=r["prep"]
                        else:
                            began=time.perf_counter()
                            coords,d,nn=fast_make(n,seed)
                            if method=="DRNAS v4":
                                r=v4_run(n,seed,d,nn,args.seconds,start=began)
                            elif method=="DRNAS v4.2 selective":
                                r=v42_run(n,seed,d,nn,args.seconds,mode="v42",start=began)
                            else:
                                r=v43_run(n,seed,d,nn,args.seconds,mode="v43",start=began)
                            prep=r["events"][1][0] if len(r["events"])>1 else r["events"][0][0]
                        status="ok"
                    except Exception as exc:
                        status="error"
                        print("BENCHMARK_ERROR",n,seed,method,repr(exc),flush=True)
                        r={"events":[],"elapsed":0}
                        prep=0
                    for sec in CUTS:
                        v=snapshot(r["events"],sec)
                        row=dict(cities=n,seed=seed,method=method,checkpoint_s=sec,
                           length_units="" if v is None else round(v/1000,5),
                           status=status if status=="error" else ("ok" if v is not None else "no_incumbent_yet"),
                           first_incumbent_s=round(r["events"][0][0],5) if r["events"] else "",
                           final_length_units=round(r["events"][-1][1]/1000,5) if r["events"] else "",
                           total_wall_s=round(r["elapsed"],4),
                           prep_s=round(prep,4),steps=r.get("steps",0),
                           restart_waves=r.get("restart_waves",0),
                           uphill_kicks=r.get("uphill_kicks",0),
                           uphill_cost_units=round(r.get("uphill_kick_cost",0)/1000,5),
                           no_candidate_kicks=r.get("no_candidate_kicks",0),
                           restart_lineage_best_updates=r.get("escape_best_updates",0),
                           communication_s=round(r.get("comm_seconds",0),5),
                           protected_elite_slots=r.get("protected_elite_slots",0),
                           notes=("LKH logged preprocessing + trial CPU time (approximate)"
                               if method=="LKH-3" else "64 sequential virtual agents, wall starts before matrix"))
                        writer.writerow(row)
                        print(json.dumps(row),flush=True)
                    fh.flush()
    print("RESULT_CSV",str(output.resolve()),flush=True)

if __name__=="__main__":
    main()
