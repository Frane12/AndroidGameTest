#!/usr/bin/env python3
"""Optional ZykovColor SAME k=3 graph decision benchmark, when official deps exist.

Does NOT construct or patch ZykovColor. Requires a prebuilt legitimate
ZykovColor binary linked to licensed Gurobi/exactcolors etc. The intended
comparative task is --strategy 2 --num-colors 3 (SingleK), Zykov encoding 5.
Default --zykov-color would OVERRIDE user-supplied SingleK strategy; DO NOT
use that switch when claiming a fair 3-color decision comparison.
"""
import argparse,csv,hashlib,json,subprocess,time
from pathlib import Path

def execute(binfile,col,timeout):
    cmd=[binfile,str(col),'--encoding','5','--solver','1',
         '--strategy','2','--num-colors','3','--verbosity','0',
         '--reduce-graph','--use-clique','--mycielski-bound',
         '--clique-explanations','--myc-explanations',
         '--positive-pruning','--dominated-decisions',
         '--disable-cardinality']
    t=time.perf_counter()
    try:r=subprocess.run(cmd,text=True,capture_output=True,timeout=timeout)
    except subprocess.TimeoutExpired:
        return dict(status='TIMEOUT',wall_sec=timeout,reason='')
    elapsed=time.perf_counter()-t
    if r.returncode:
        return dict(status='ERROR',wall_sec=elapsed,
            reason=f'exit={r.returncode},stderr={r.stderr[-250:]}')
    if 'IncSatGC computed SAT for k = 3' in r.stdout:
        return dict(status='SAT',wall_sec=elapsed,reason='')
    if 'IncSatGC computed UNSAT for k = 3' in r.stdout:
        return dict(status='UNSAT',wall_sec=elapsed,reason='')
    return dict(status='ERROR',wall_sec=elapsed,reason='No fixed-k status marker: '+r.stdout[-220:])

def main():
    a=argparse.ArgumentParser()
    a.add_argument('--binary',required=True)
    a.add_argument('--graphs',required=True)
    a.add_argument('--outdir',required=True)
    a.add_argument('--timeout',type=float,default=15.)
    a=a.parse_args()
    if not Path(a.binary).is_file():raise RuntimeError('ZykovColor binary not provided')
    if a.timeout!=15.:raise RuntimeError('Expected frozen 15s limit')
    graphs=json.loads(Path(a.graphs).read_text())
    out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    results=[]
    for i,e in enumerate(graphs):
        col=Path(e['graph_col'])
        assert hashlib.sha256(col.read_bytes()).hexdigest()==e['graph_sha256']
        for rep in range(2):
            r=execute(a.binary,col,a.timeout)
            # Original SATLIB flat200 is SAT. Wrong UNSAT aborts.
            if r['status']=='UNSAT':raise RuntimeError('ZykovColor contradicts SATLIB known 3-colorability')
            results.append(dict(case=e['case'],rep=rep,method='ZykovColor-fixed3',
                status=r['status'],wall_seconds=r['wall_sec'],
                par2_seconds=r['wall_sec'] if r['status']=='SAT' else 30.,
                error=r['reason'],sha256=e['graph_sha256']))
            print('ZYKOV',i+1,'/',len(graphs),rep,r['status'],r['wall_sec'],flush=True)
    with (out/'zykov_raw.csv').open('w',newline='',encoding='utf8') as stream:
        w=csv.DictWriter(stream,fieldnames=list(results[0]));w.writeheader();w.writerows(results)
    print('Valid fixed k=3 ZykovColor results ready for SAME-graph comparison',flush=True)
if __name__=='__main__':main()
