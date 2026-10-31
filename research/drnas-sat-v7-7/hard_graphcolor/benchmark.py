#!/usr/bin/env python3
"""Exact C++ DRNAS v7.7 versus CaDiCaL 3.0.1 and Kissat 4.0.4.

Same exact predeclared k-colorability CNF, wall cap=60s, 2 rotated repeats.
Methods: plain, same-observer no-hints, quality_guided, randomized hints,
independent Kissat. Both SAT and UNSAT allowed, never guess missing labels.
Every SAT model is rechecked (native checked inside C++; Kissat in Python).
"""
import argparse,csv,hashlib,json,random,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from benchmark import execute

METHODS=('plain','quality_plain','quality_guided','quality_random','kissat404')
CUTOFF=60.
REPEATS=2
FIELDS=('case','family','k','vertices','edges','rep','method','status','elapsed_s',
        'native_s','par2_s','observed_clauses','short_fraction',
        'extended','resumed','hints','error','cnf_sha256','graph_sha256')

def verify_kissat_witness(cnf_path,stdout,graph_col,n,k):
    values={}
    for line in stdout.splitlines():
        if line.lstrip().startswith('v '):
            for token in line.strip().split()[1:]:
                l=int(token)
                if l==0:continue
                if abs(l) in values and values[abs(l)] != (l>0):
                    raise RuntimeError('Contradictory Kissat SAT model')
                values[abs(l)]=(l>0)
    if not values:raise RuntimeError('Kissat SAT result missing a verifiable witness')
    clauses=0;clause=[];header=False
    with Path(cnf_path).open(encoding='ascii') as f:
        for line in f:
            line=line.strip()
            if not line or line.startswith('c'):continue
            if line.startswith('p cnf '):
                if header:raise RuntimeError('Duplicate header')
                header=True;continue
            if not header:raise RuntimeError('Missing header')
            for token in line.split():
                l=int(token)
                if l:
                    clause.append(l)
                else:
                    if not any(values.get(abs(z),False)==(z>0) for z in clause):
                        raise RuntimeError('Kissat SAT witness violates original CNF')
                    clauses+=1;clause=[]
    if clause:raise RuntimeError('Unterminated CNF')
    colors={}
    for v in range(1,n+1):
        picks=[color for color in range(1,k+1) if values.get((v-1)*k+color,False)]
        if len(picks)!=1:raise RuntimeError('Kissat model is not an exact vertex coloring')
        colors[v]=picks[0]
    ecount=0
    for line in Path(graph_col).read_text(encoding='ascii').splitlines():
        if line.startswith('e '):
            _,a,b=line.split();a=int(a);b=int(b)
            if colors[a]==colors[b]:
                raise RuntimeError('Kissat model violates a graph edge')
            ecount+=1
    return dict(verified_clauses=clauses,verified_graph_edges=ecount)

def run_one(native,kissat,mode,source,meta,seed):
    start=time.perf_counter()
    if mode!='kissat404':
        try:
            r=execute(native,mode,source,seed,CUTOFF)
            return dict(status=r['answer'],elapsed_s=r['wall_s'],
              native_s=r.get('native_s'),hints=r.get('phases'),
              observed_clauses=r.get('observed'),short_fraction=r.get('short_fraction'),
              extended=r.get('extended'),resumed=r.get('resumed'),
              error=r.get('error',''))
        except Exception as ex:
            return dict(status='ERROR',elapsed_s=min(time.perf_counter()-start,CUTOFF),
                        error=f'{type(ex).__name__}: {str(ex)[:280]}')
    try:
        r=subprocess.run([kissat,str(source)],capture_output=True,text=True,
                    check=False,timeout=CUTOFF)
    except subprocess.TimeoutExpired:
        return dict(status='TIMEOUT',elapsed_s=CUTOFF,error='')
    sec=time.perf_counter()-start
    if r.returncode not in (0,10,20):
        return dict(status='ERROR',elapsed_s=sec,
                    error=f'Kissat exit {r.returncode}: {r.stderr[-200:]}')
    labels=[x.strip() for x in r.stdout.splitlines() if x.startswith('s ')]
    if labels==['s SATISFIABLE']:
        try:
            verify_kissat_witness(source,r.stdout,meta['normalized_graph'],
                                   meta['vertices'],meta['k'])
        except Exception as exc:
            return dict(status='ERROR',elapsed_s=sec,error='Invalid Kissat SAT model: '+str(exc)[:240])
        return dict(status='SAT',elapsed_s=sec,error='')
    if labels==['s UNSATISFIABLE']:
        return dict(status='UNSAT',elapsed_s=sec,error='')
    return dict(status='ERROR',elapsed_s=sec,error='Ambiguous/missing Kissat answer '+str(labels)[:130])

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--native',required=True)
    p.add_argument('--kissat',required=True)
    p.add_argument('--cases',required=True)
    p.add_argument('--outdir',required=True)
    a=p.parse_args()
    entries=json.loads(Path(a.cases).read_text())
    assert len(entries)==2
    out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    rows=[];status={}
    with (out/'raw.csv').open('w',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader()
        for i,entry in enumerate(entries):
            inp=Path(entry['input_cnf'])
            assert hashlib.sha256(inp.read_bytes()).hexdigest()==entry['input_cnf_sha256']
            known=None;counts={}
            for rep in range(REPEATS):
                methods=list(METHODS)
                random.Random(770777000 + int(entry['input_cnf_sha256'][:8],16)+rep*917).shuffle(methods)
                for mode in methods:
                    r=run_one(a.native,a.kissat,mode,inp,entry,
                              (7777000+int(entry['input_cnf_sha256'][:8],16)+rep*399)%2**32)
                    answer=r['status']
                    if answer not in ('SAT','UNSAT','TIMEOUT','ERROR'):
                        raise RuntimeError('Unrecognized status '+repr(answer))
                    if answer in ('SAT','UNSAT'):
                        if known and answer!=known:
                            raise RuntimeError('CONTRADICTORY SAT/UNSAT results on '+entry['case']+
                                               ': '+known+' != '+answer+' ('+mode+')')
                        known=answer
                    rec=dict(case=entry['case'],family=entry['family'],k=entry['k'],
                      vertices=entry['vertices'],edges=entry['undirected_edges'],rep=rep,
                      method=mode,status=answer,elapsed_s=round(float(r['elapsed_s']),6),
                      native_s=r.get('native_s') or '',par2_s=round(float(r['elapsed_s']),6)
                             if answer in ('SAT','UNSAT') else 2*CUTOFF,
                      observed_clauses=r.get('observed_clauses',''),
                      short_fraction=r.get('short_fraction',''),extended=r.get('extended',''),
                      resumed=r.get('resumed',''),hints=r.get('hints',''),
                      error=r.get('error',''),cnf_sha256=entry['input_cnf_sha256'],
                      graph_sha256=entry['source_graph_sha256'])
                    rows.append(rec);w.writerow(rec);f.flush()
                    counts[answer]=counts.get(answer,0)+1
                    print('RESULT',entry['case'],rep,mode,answer,
                          round(float(r['elapsed_s']),3),'s',str(r.get('error',''))[:120],flush=True)
            status[entry['case']]=dict(known_outcome=known or 'UNKNOWN',counts=counts)
            print('CASE',i+1,'/2',entry['case'],status[entry['case']],flush=True)
    (out/'status.json').write_text(json.dumps(status,indent=2))
    assert len(rows)==2*REPEATS*len(METHODS)
    print('PASS shard completed',len(rows),'same-CNF controlled solver trials',flush=True)
if __name__=='__main__':main()
