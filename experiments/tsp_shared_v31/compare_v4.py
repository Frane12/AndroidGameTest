#!/usr/bin/env python3
"""Paired TSP v4 vs genuine LKH-3 and DRNAS v3.1 at wall-clock checkpoints.
All costs are TSPLIB EUC_2D integer edge weights. JIT warmup is excluded
from each instance, just as building the LKH binary is excluded.
LKH event timestamps are approximated by printed preprocess + trial CPU time.
LKH startup/solve timing excludes generating the input file; DRNAS v4
includes point generation, distance matrix construction, and tour setup.
"""
import argparse, csv, json, time, statistics
from pathlib import Path
from drnas_v4 import fast_make,run as v4_run,warmup
from time_quality_v32 import lkh_trace,drnas_trace,snapshot

CHECKPOINTS=(2,4,6,8,10,15,20,25,30)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--cities',type=int,nargs='+',default=[2000,5000])
    p.add_argument('--seeds',type=int,nargs='+',default=[0,1,2])
    p.add_argument('--seconds',type=int,default=30)
    p.add_argument('--lkh',default='./LKH3/LKH')
    p.add_argument('--out',default='tsp_v4_lkh_paired.csv')
    p.add_argument('--work',default='tsp_v4_lkh_logs')
    a=p.parse_args()
    warmup()
    cols=['cities','seed','method','checkpoint_s','best_length_units','status','first_incumbent_s',
          'final_length_units','end_to_end_s','prep_s','steps','two_opt_moves','three_opt_moves',
          'route_copies','communication_s','notes']
    outfile=Path(a.out);outfile.parent.mkdir(parents=True,exist_ok=True)
    with outfile.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=cols);writer.writeheader()
        for n in a.cities:
            for seed in a.seeds:
                for method in ('LKH-3','DRNAS v3.1 route_share','DRNAS v4 early-3opt'):
                    try:
                        if method=='LKH-3':
                            r=lkh_trace(n,seed,a.lkh,Path(a.work),a.seconds)
                        elif method=='DRNAS v3.1 route_share':
                            r=drnas_trace(n,seed,'route_share',a.seconds)
                        else:
                            start=time.perf_counter()
                            coords,d,nn=fast_make(n,seed)
                            r=v4_run(n,seed,d,nn,a.seconds,start=start)
                            r['prep']=r['events'][0][0]
                        status='ok'
                    except Exception as e:
                        status='error';r={'events':[],'elapsed':0,'prep':0,'steps':0,'notes':str(e)}
                        print('BENCHMARK ERROR',n,seed,method,str(e),flush=True)
                    for t in CHECKPOINTS:
                        score=snapshot(r['events'],t)
                        record=dict(
                            cities=n,seed=seed,method=method,checkpoint_s=t,
                            best_length_units='' if score is None else round(score/1000,5),
                            status=status if score is not None or status=='error' else 'no_incumbent_yet',
                            first_incumbent_s=round(r['events'][0][0],4) if r['events'] else '',
                            final_length_units=round(r['events'][-1][1]/1000,5) if r['events'] else '',
                            end_to_end_s=round(r['elapsed'],4),
                            prep_s=round(r.get('prep',0),4),
                            steps=r.get('steps',0),
                            two_opt_moves=r.get('two_opt_moves',0),
                            three_opt_moves=r.get('three_opt_moves',0),
                            route_copies=r.get('route_copies',0),
                            communication_s=round(r.get('comm_seconds',0),5),
                            notes=r.get('notes','64 virtual agents; fast EUC_2D matrix; 16 elites; 2-opt/3-opt'))
                        writer.writerow(record)
                        print(json.dumps(record),flush=True)
                    f.flush()
    print('OUT',outfile.resolve())

if __name__=='__main__':
    main()
