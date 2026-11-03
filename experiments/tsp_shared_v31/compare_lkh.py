#!/usr/bin/env python3
"""External comparison: LKH-3 vs DRNAS TSP v3.1 on identical TSPLIB EUC_2D costs."""
import argparse,csv,json,subprocess,time,sys
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree
from drnas_v31 import initial_tours,run,warmup

def make(n,seed):
    xy=np.random.default_rng(88001+seed).uniform(0,1000,(n,2))
    coords=np.rint(xy*1000).astype(np.int32)
    delta=coords[:,None,:].astype(np.float64)-coords[None,:,:]
    d=np.floor(np.sqrt(np.sum(delta*delta,axis=2))+0.5).astype(np.float32)
    neighbors=cKDTree(coords).query(coords,k=33)[1][:,1:].astype(np.int32)
    return coords,d,neighbors

def write_tsp(xy,path):
    with open(path,'w') as f:
        f.write('NAME : DRNAS_PAIRED\nTYPE : TSP\nDIMENSION : '+str(len(xy))+'\nEDGE_WEIGHT_TYPE : EUC_2D\nNODE_COORD_SECTION\n')
        for i,(x,y) in enumerate(xy,1):f.write(f'{i} {x} {y}\n')
        f.write('EOF\n')

def parse_tour(path,n):
    lines=Path(path).read_text().splitlines()
    j=next(i for i,line in enumerate(lines) if line.strip().upper()=='TOUR_SECTION')
    tour=[]
    for line in lines[j+1:]:
        for token in line.split():
            if token in ('-1','EOF'):break
            tour.append(int(token)-1)
        if '-1' in line.split() or 'EOF' in line.split():break
    if len(tour)!=n or sorted(tour)!=list(range(n)):raise ValueError('invalid LKH tour')
    return np.array(tour,dtype=np.int32)

def length(tour,d):
    return float(d[tour,np.roll(tour,-1)].sum(dtype=np.float64))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--cities',nargs='+',type=int,default=[2000,5000])
    ap.add_argument('--seeds',nargs='+',type=int,default=[0])
    ap.add_argument('--seconds',type=int,default=6)
    ap.add_argument('--lkh',default='./LKH3/LKH')
    ap.add_argument('--out',default='tsp_world_compare.csv')
    a=ap.parse_args()
    warmup()
    fields=['cities','seed','solver','length_unscaled','length_units','search_seconds','preparation_seconds','total_seconds','steps','status','notes']
    p=Path(a.out);p.parent.mkdir(parents=True,exist_ok=True)
    with open(p,'w',newline='') as fp:
        writer=csv.DictWriter(fp,fieldnames=fields);writer.writeheader()
        def save(n,seed,name,score,search,prep,total,steps,status,notes):
            row={'cities':n,'seed':seed,'solver':name,'length_unscaled':score if score is not None else '',
                 'length_units':round(score/1000,5) if score is not None else '',
                 'search_seconds':round(search,4),'preparation_seconds':round(prep,4),
                 'total_seconds':round(total,4),'steps':steps,'status':status,'notes':notes}
            writer.writerow(row);fp.flush();print(json.dumps(row),flush=True)
        for n in a.cities:
            for seed in a.seeds:
                prep_start=time.perf_counter();coords,d,nn=make(n,seed)
                prep_cost=time.perf_counter()-prep_start
                work=Path('tsp_reference_inputs');work.mkdir(exist_ok=True)
                tsp=work/f'cities_{n}_seed_{seed}.tsp'
                par=work/f'cities_{n}_seed_{seed}.par'
                output=work/f'cities_{n}_seed_{seed}.tour'
                write_tsp(coords,tsp)
                par.write_text('\n'.join([
                  'PROBLEM_FILE = '+str(tsp.resolve()),'OUTPUT_TOUR_FILE = '+str(output.resolve()),
                  'RUNS = 1','MAX_TRIALS = 3','MOVE_TYPE = 5','PATCHING_C = 3','PATCHING_A = 2',
                  'SEED = '+str(19+seed),'TIME_LIMIT = '+str(a.seconds),'TRACE_LEVEL = 1','']))
                started=time.perf_counter()
                try:
                    proc=subprocess.run([str(Path(a.lkh).resolve()),str(par.resolve())],text=True,capture_output=True,timeout=a.seconds+35)
                    elapsed=time.perf_counter()-started
                    (work/f'cities_{n}_seed_{seed}.lkh.log').write_text(proc.stdout+'\nSTDERR\n'+proc.stderr)
                    if proc.returncode:raise RuntimeError('LKH return code '+str(proc.returncode))
                    tour=parse_tour(output,n)
                    val=length(tour,d)
                    save(n,seed,'LKH-3',round(val,3),elapsed,0,elapsed,0,'ok','LKH single run, 3 maximum trials, includes preprocessing')
                except Exception as e:
                    elapsed=time.perf_counter()-started
                    save(n,seed,'LKH-3',None,elapsed,0,elapsed,0,'failed',str(e))
                bases_start=time.perf_counter()
                bases=initial_tours(n,d,nn,72001+seed,64)
                init_cost=time.perf_counter()-bases_start
                for mode in ('independent','route_share','batched_lookup'):
                    r=run(d,nn,bases,mode,a.seconds)
                    save(n,seed,'DRNAS v3.1 '+mode,r['length'],r['seconds'],prep_cost+init_cost,
                         prep_cost+init_cost+r['seconds'],r['steps'],'ok',
                         f'64 virtual agents; events={r["edge_events"]}; packets={r["packets"]}; communication={r["comm_seconds"]}s')
if __name__=='__main__':main()
