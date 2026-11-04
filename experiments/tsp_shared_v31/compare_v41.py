#!/usr/bin/env python3
"""Exact same EUC_2D instances and wall-clock checkpoints:
genuine LKH-3, v4, v4.1 ablation without restarts, v4.1 with restarts.

For v4 and v4.1 timing starts *before* distance matrix construction.
LKH timing starts with invoking its binary and excludes external TSPLIB
file generation. Its first event time is reconstructed from its logged
preprocessing time plus trial time (CPU vs wall distinction noted).
Results are exploratory: single CPU runner, 64 sequential virtual agents,
no claim of strict time-budget parity when LKH initialization exceeds limit.
"""
import argparse,csv,json,time,statistics
from pathlib import Path
from drnas_v4 import fast_make,run as v4_run,warmup as v4_warmup
from drnas_v41 import run as v41_run
from time_quality_v32 import lkh_trace,snapshot

CHECKPOINTS=(2,4,6,8,10,15,20,25,30)

def main():
    a=argparse.ArgumentParser()
    a.add_argument('--cities',nargs='+',type=int,default=[2000,5000])
    a.add_argument('--seeds',nargs='+',type=int,default=[0,1,2])
    a.add_argument('--seconds',type=int,default=30)
    a.add_argument('--lkh',default='./LKH3/LKH')
    a.add_argument('--out',default='drnas_tsp_v41_paired.csv')
    a.add_argument('--work',default='tsp_v41_lkh_logs')
    cfg=a.parse_args()
    v4_warmup()
    cols=['cities','seed','method','checkpoint_s','best_length_units','status',
          'first_incumbent_s','final_length_units','end_to_end_s','preparation_s',
          'steps','two_opt_moves','three_opt_moves','route_copies',
          'restart_waves','restarted_agents','perturbations','escape_best_updates',
          'communication_s','notes']
    out=Path(cfg.out);out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('w',newline='') as fh:
        writer=csv.DictWriter(fh,fieldnames=cols);writer.writeheader()
        for n in cfg.cities:
            for seed in cfg.seeds:
                for method in ('LKH-3','DRNAS v4','DRNAS v4.1 no-restart','DRNAS v4.1 restart'):
                    try:
                        if method=='LKH-3':
                            r=lkh_trace(n,seed,cfg.lkh,Path(cfg.work),cfg.seconds)
                            prep=r['prep']
                            notes='Original LKH-3; prep + trial time approximates first incumbent'
                        else:
                            begin=time.perf_counter()
                            coords,d,nn=fast_make(n,seed)
                            if method=='DRNAS v4':
                                r=v4_run(n,seed,d,nn,budget=cfg.seconds,start=begin)
                            else:
                                r=v41_run(n,seed,d,nn,budget=cfg.seconds,
                                          mode='v41' if method.endswith('restart') and
                                          not method.endswith('no-restart') else 'v41_no_restart',
                                          start=begin)
                            prep=r['events'][1][0] if len(r['events'])>1 else r['events'][0][0]
                            notes='64 sequential virtual agents; search time includes cold instance prep'
                        status='ok'
                    except Exception as e:
                        status='error'
                        print('BENCHMARK_ERROR',n,seed,method,repr(e),flush=True)
                        r={'events':[],'elapsed':0}
                        prep=0;notes=repr(e)
                    for checkpoint in CHECKPOINTS:
                        length=snapshot(r['events'],checkpoint)
                        row=dict(cities=n,seed=seed,method=method,checkpoint_s=checkpoint,
                            best_length_units='' if length is None else round(length/1000,5),
                            status=status if status=='error' else ('ok' if length is not None else 'no_incumbent_yet'),
                            first_incumbent_s=round(r['events'][0][0],5) if r['events'] else '',
                            final_length_units=round(r['events'][-1][1]/1000,5) if r['events'] else '',
                            end_to_end_s=round(r['elapsed'],4),
                            preparation_s=round(prep,4),steps=r.get('steps',0),
                            two_opt_moves=r.get('two_opt_moves',0),
                            three_opt_moves=r.get('three_opt_moves',0),
                            route_copies=r.get('route_copies',0),
                            restart_waves=r.get('restart_waves',0),
                            restarted_agents=r.get('restarted_agents',0),
                            perturbations=r.get('perturbations',0),
                            escape_best_updates=r.get('escape_best_updates',0),
                            communication_s=round(r.get('comm_seconds',0),5),notes=notes)
                        writer.writerow(row)
                        print(json.dumps(row),flush=True)
                    fh.flush()
    print('RESULT_CSV',out.resolve(),flush=True)

if __name__=='__main__':main()
