#!/usr/bin/env python3
"""Time-to-quality benchmark: verified TSPLIB LKH trace and DRNAS v3.1 checkpoint best-so-far."""
import argparse,csv,json,re,subprocess,time
from pathlib import Path
import numpy as np
from drnas_v31 import initial_tours,move,tour_len,warmup
from compare_lkh import make,write_tsp,parse_tour,length

CHECKPOINTS = (2,4,6,8,10)

def drnas_trace(n,seed,mode,budget=10):
    began=time.perf_counter()
    coords,d,nn=make(n,seed)
    bases=initial_tours(n,d,nn,72001+seed,64)
    prep=time.perf_counter()-began
    tours=np.asarray(bases,dtype=np.int32)
    pos=np.empty_like(tours)
    for w in range(64): pos[w,tours[w]]=np.arange(n,dtype=np.int32)
    lens=np.asarray([tour_len(t,d) for t in tours],dtype=np.float64)
    bi=int(np.argmin(lens));best=float(lens[bi]);best_tour=tours[bi].copy()
    trace=[(time.perf_counter()-began,best)]
    votes=np.zeros((n,n),dtype=np.float32)
    inbox=[];w=epoch=steps=packets=events=route_copies=0
    comm_seconds=0.0
    while time.perf_counter()-began < budget:
        role=w//16
        cursor=(epoch*157+w*193)%n
        delta,a,b,c,e,advised=move(tours[w],pos[w],d,nn,votes,role,(w%2)==1,mode=='batched_lookup',cursor)
        steps+=1
        if a>=0:
            lens[w]+=delta
            if mode=='batched_lookup' and -delta>1.0: inbox.append((a,b,c,e,min(100.,-float(delta))))
            if lens[w]<best-1e-4:
                best=float(lens[w]);best_tour=tours[w].copy()
                trace.append((time.perf_counter()-began,best))
        w+=1
        if w==64:
            w=0;epoch+=1
            if mode=='batched_lookup' and epoch%2==0 and inbox:
                ts=time.perf_counter()
                for a,b,c,e,g in sorted(inbox,key=lambda z:z[4],reverse=True)[:16]:
                    v=np.float32(g/20.)
                    for x,y,s in ((a,c,1),(b,e,1),(a,b,-1),(c,e,-1)):
                        votes[x,y]+=s*v;votes[y,x]+=s*v
                events+=min(16,len(inbox));inbox.clear();packets+=1
                comm_seconds+=time.perf_counter()-ts
            if mode in ('route_share','batched_lookup') and epoch%4==0:
                ts=time.perf_counter();lag=int(np.argmax(lens))
                if lens[lag]>best*1.05:
                    tours[lag,:]=best_tour
                    pos[lag,tours[lag]]=np.arange(n,dtype=np.int32)
                    lens[lag]=best;route_copies+=1
                comm_seconds+=time.perf_counter()-ts
    elapsed=time.perf_counter()-began
    return dict(events=trace,elapsed=elapsed,prep=prep,steps=steps,packets=packets,edge_events=events,route_copies=route_copies,comm_seconds=comm_seconds,notes='measured elapsed from instance generation incl all prep; 64 virtual agents')

def lkh_trace(n,seed,exe,work,budget=10):
    work.mkdir(parents=True,exist_ok=True)
    coords,d,nn=make(n,seed)
    tsp=work/f'tsp_{n}_{seed}.tsp'; par=work/f'tsp_{n}_{seed}.par';tourfile=work/f'tsp_{n}_{seed}.tour'
    write_tsp(coords,tsp)
    par.write_text('\n'.join((f'PROBLEM_FILE = {tsp.resolve()}',f'OUTPUT_TOUR_FILE = {tourfile.resolve()}',
           'RUNS = 1','MAX_TRIALS = 3','MOVE_TYPE = 5','PATCHING_C = 3','PATCHING_A = 2',
           f'SEED = {19+seed}',f'TIME_LIMIT = {budget}','TRACE_LEVEL = 1','')))
    started=time.perf_counter()
    proc=subprocess.run([str(Path(exe).resolve()),str(par.resolve())],capture_output=True,text=True,timeout=110)
    elapsed=time.perf_counter()-started
    output=proc.stdout+'\nSTDERR\n'+proc.stderr
    (work/f'tsp_{n}_{seed}.log').write_text(output)
    if proc.returncode: raise RuntimeError(f'LKH failed {proc.returncode}: {proc.stderr[-400:]}')
    mp=re.search(r'Preprocessing time\s*=\s*([\d.]+)\s*sec',output)
    if not mp: raise RuntimeError('No LKH preprocessing time in log; cannot timestamp incumbent')
    preprocess=float(mp.group(1))
    events=[]
    for line in output.splitlines():
        m=re.search(r'^\*\s*\d+: Cost\s*=\s*(\d+),\s*Time\s*=\s*([\d.]+)\s*sec',line.strip())
        if m:
            cost=int(m.group(1)); dt=float(m.group(2))
            t=preprocess+dt
            if not events or cost<events[-1][1]:events.append((t,cost))
    if not events: raise RuntimeError('LKH log has no timestamped incumbent entries')
    lkh_tour=parse_tour(tourfile,n)
    verified=length(lkh_tour,d)
    if abs(verified-events[-1][1])>0.1:raise RuntimeError(f'LKH cost mismatch! logged={events[-1][1]} recalculated={verified}')
    return dict(events=events,elapsed=elapsed,prep=preprocess,steps=0,packets=0,edge_events=0,route_copies=0,comm_seconds=0.0,
                notes='LKH event time approximated from printed preprocessing + trial CPU time; wall includes all phases; LKH can exceed TIME_LIMIT in preprocessing')

def snapshot(events,t):
    known=[v for ts,v in events if ts<=t+1.e-9]
    return min(known) if known else None

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--cities',nargs='+',type=int,default=[2000,5000]);p.add_argument('--seeds',nargs='+',type=int,default=[0,1,2])
    p.add_argument('--lkh',default='./LKH3/LKH');p.add_argument('--out',default='tsp_time_quality_v32.csv')
    p.add_argument('--work',default='tsp_time_quality_artifacts');p.add_argument('--seconds',type=int,default=10)
    a=p.parse_args();warmup()
    fields=['cities','seed','method','checkpoint_s','best_length_units','status','first_incumbent_s','final_length_units',
            'end_to_end_s','prep_s','steps','packets','edge_events','route_copies','communication_s','notes']
    outfile=Path(a.out);outfile.parent.mkdir(parents=True,exist_ok=True)
    with outfile.open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader()
        for n in a.cities:
            for seed in a.seeds:
                for mode in ('LKH-3','DRNAS route_share','DRNAS batched_lookup'):
                    try:
                        if mode=='LKH-3':r=lkh_trace(n,seed,a.lkh,Path(a.work),a.seconds)
                        else:r=drnas_trace(n,seed,'route_share' if mode.endswith('route_share') else 'batched_lookup',a.seconds)
                        status='ok'
                    except Exception as e:
                        r=dict(events=[],elapsed=0.0,prep=0.,steps=0,packets=0,edge_events=0,route_copies=0,comm_seconds=0.0,notes=str(e))
                        status='error';print('BENCHMARK ERROR',n,seed,mode,str(e),flush=True)
                    for sec in CHECKPOINTS:
                        v=snapshot(r['events'],sec)
                        row=dict(cities=n,seed=seed,method=mode,checkpoint_s=sec,best_length_units='' if v is None else round(v/1000,4),
                                 status=status if v is not None or status=='error' else 'no_incumbent_yet',
                                 first_incumbent_s=round(r['events'][0][0],4) if r['events'] else '',
                                 final_length_units=round(r['events'][-1][1]/1000,4) if r['events'] else '',
                                 end_to_end_s=round(r['elapsed'],4),prep_s=round(r['prep'],4),steps=r['steps'],packets=r['packets'],
                                 edge_events=r['edge_events'],route_copies=r['route_copies'],communication_s=round(r['comm_seconds'],4),notes=r['notes'])
                        writer.writerow(row)
                        print(json.dumps(row,ensure_ascii=False),flush=True)
                    f.flush()
    print('RESULTS',str(outfile.resolve()),flush=True)
if __name__=='__main__': main()
