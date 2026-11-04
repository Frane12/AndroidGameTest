#!/usr/bin/env python3
"""Pre-registered paired TSP v5.1 holdout on untouched seeds 12,13,14.

Identical TSPLIB EUC_2D instances, v4.2, v4.3 and v5 exact 4-opt\nwith/without shared lookup,
plus real pinned LKH-3. For DRNAS, wall clock begins before coordinate
generation and distance matrix; LKH starts at binary process invocation.
LKH first incumbent times approximate log preprocessing + trial CPU time.
"""
import argparse,csv,json,time
from pathlib import Path
from drnas_v4 import fast_make
from drnas_v43 import run as v43_run
from drnas_v51 import run as v51_run,warmup
from drnas_v5 import run as v5_run
from time_quality_v32 import lkh_trace,snapshot

CUTS=(2,4,6,8,10,15,20,25,30)
METHODS=("LKH-3","DRNAS v4.3 bounded","DRNAS v5 no-sharing","DRNAS v5.1 five-opt")

def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("--cities",type=int,nargs="+",default=[2000,5000])
    cli.add_argument("--seeds",type=int,nargs="+",default=[12,13,14])
    cli.add_argument("--seconds",type=int,default=30)
    cli.add_argument("--lkh",default="./LKH3/LKH")
    cli.add_argument("--out",default="drnas_tsp_v51_holdout.csv")
    cli.add_argument("--work",default="drnas_tsp_v51_logs")
    args=cli.parse_args()
    warmup()
    fields=["cities","seed","method","checkpoint_s","length_units","status",
        "first_incumbent_s","final_length_units","total_wall_s","prep_s",
        "steps","restart_waves","uphill_kicks","uphill_cost_units",
        "no_candidate_kicks","restart_lineage_best_updates",
        "communication_s","protected_elite_slots",
        "policy_bridge_waves","policy_bounded_waves","policy_probes",
        "policy_bridge_best_updates","policy_bounded_best_updates",
        "policy_bridge_gain_units","policy_bounded_gain_units",
        "four_opt_moves","accepted_moves","shared_packets","shared_edge_votes",
        "shared_table_bytes","five_opt_calls","five_opt_moves","five_opt_seconds","notes"]
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
                            if method=="DRNAS v4.3 bounded":
                                r=v43_run(n,seed,d,nn,args.seconds,mode="v43",start=began)
                            elif method=="DRNAS v5 no-sharing":
                                r=v5_run(n,seed,d,nn,args.seconds,mode="v5_no_share",start=began)
                            else:
                                r=v51_run(n,seed,d,nn,args.seconds,mode="v51_five",start=began)
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
                           policy_bridge_waves=r.get("policy_bridge_waves",0),
                           policy_bounded_waves=r.get("policy_bounded_waves",0),
                           policy_probes=r.get("policy_probes",0),
                           policy_bridge_best_updates=r.get("policy_bridge_best_updates",0),
                           policy_bounded_best_updates=r.get("policy_bounded_best_updates",0),
                           policy_bridge_gain_units=round(r.get("policy_bridge_gain",0)/1000,5),
                           policy_bounded_gain_units=round(r.get("policy_bounded_gain",0)/1000,5),
                           four_opt_moves=r.get("four_opt_moves",0),
                           accepted_moves=r.get("accepted_moves",0),
                           shared_packets=r.get("shared_packets",0),
                           shared_edge_votes=r.get("shared_edge_votes",0),
                           shared_table_bytes=r.get("shared_table_bytes",0),
                           five_opt_calls=r.get("five_opt_calls",0),
                           five_opt_moves=r.get("five_opt_moves",0),
                           five_opt_seconds=round(r.get("five_opt_seconds",0),5),
                           notes=("LKH logged preprocessing + trial CPU time (approximate)"
                               if method=="LKH-3" else "64 sequential virtual agents, wall starts before matrix"))
                        writer.writerow(row)
                        print(json.dumps(row),flush=True)
                    fh.flush()
    print("RESULT_CSV",str(output.resolve()),flush=True)

if __name__=="__main__":
    main()
