#!/usr/bin/env python3
"""Graph coloring SATLIB same-CNF controlled benchmark and Kissat reference.

Runs unchanged DRNAS 7.7 native code + SAME CaDiCaL 3.0.1 plain mode
+ Kissat 4.0.4 on the identical SHA-pinned SATLIB CNF (all are 3-color SAT).
Each graph COL is separately proven equivalent to the original CNF by
extract_certified_graphs.py. No graph transformations in timed SAT path.
"""
import argparse,csv,hashlib,json,random,statistics,subprocess,time
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from benchmark import execute
METHODS=('plain','quality_plain','quality_guided','quality_random','kissat404')
CUTOFF=15.
REPEATS=2

def verify_kissat_model(path,stdout):
    vals={}
    for line in stdout.splitlines():
        if line.lstrip().startswith('v '):
            for piece in line.lstrip()[2:].split():
                lit=int(piece)
                if lit:vals[abs(lit)]=lit>0
    if not vals:return False
    clause=[];header=False
    with open(path,encoding='ascii') as stream:
        for line in stream:
            line=line.strip()
            if not line or line[0]=='c':continue
            if line[0]=='%':break
            if line.startswith('p '):header=True;continue
            if not header:raise ValueError('missing CNF header')
            for token in line.split():
                lit=int(token)
                if not lit:
                    if not any(vals.get(abs(v))==(v>0) for v in clause):
                        raise ValueError('Kissat SAT assignment violates original CNF')
                    clause=[]
                else:clause.append(lit)
    if clause:raise ValueError('unclosed CNF')
    return True

def run(binary,kissat,method,path,seed):
    start=time.perf_counter()
    if method!='kissat404':
        try:
            r=execute(binary,method,path,seed,CUTOFF)
            return dict(answer=r['answer'],elapsed_s=r['wall_s'],
                error=r.get('error',''),phase_count=r.get('phases',0),
                extended=r.get('extended',0),observer_clauses=r.get('observed',0))
        except Exception as e:
            return dict(answer='ERROR',elapsed_s=min(time.perf_counter()-start,CUTOFF),
                error=f'{type(e).__name__}: {e}'[:400])
    try:
        p=subprocess.run([kissat,str(path)],text=True,capture_output=True,
                         timeout=CUTOFF,check=False)
    except subprocess.TimeoutExpired:
        return dict(answer='TIMEOUT',elapsed_s=CUTOFF,error='')
    elapsed=time.perf_counter()-start
    if p.returncode not in (0,10,20):
        return dict(answer='ERROR',elapsed_s=elapsed,error='exit '+str(p.returncode)+' '+p.stderr[-220:])
    if 's SATISFIABLE' in p.stdout and 's UNSATISFIABLE' not in p.stdout:
        try:
            if not verify_kissat_model(path,p.stdout):
                raise ValueError('missing model')
        except Exception as e:
            return dict(answer='ERROR',elapsed_s=elapsed,error='Kissat invalid witness: '+str(e))
        return dict(answer='SAT',elapsed_s=elapsed,error='')
    if 's UNSATISFIABLE' in p.stdout:
        return dict(answer='UNSAT',elapsed_s=elapsed,error='')
    return dict(answer='ERROR',elapsed_s=elapsed,error='No unambiguous Kissat result')

def main():
    a=argparse.ArgumentParser()
    for name in ('--native','--kissat','--graphs','--outdir'):a.add_argument(name,required=True)
    a=a.parse_args()
    entries=json.loads(Path(a.graphs).read_text())
    assert 1<=len(entries)<=20
    out=Path(a.outdir);out.mkdir(parents=True,exist_ok=True)
    rows=[];checks=[]
    with (out/'raw.csv').open('w',newline='',encoding='utf8') as f:
        columns=['case','rep','method','status','wall_seconds','par2_seconds',
                 'phase_count','extended','observer_clauses','error','cnf_sha256',
                 'graph_sha256','vertices','edges']
        w=csv.DictWriter(f,fieldnames=columns);w.writeheader()
        for i,e in enumerate(entries):
            original=Path(e['input_cnf']);graph=Path(e['graph_col'])
            assert hashlib.sha256(original.read_bytes()).hexdigest()==e['cnf_sha256']
            assert hashlib.sha256(graph.read_bytes()).hexdigest()==e['graph_sha256']
            assert e['k']==3 and e['graph_relation']=='EXACT_CNF_MULTIMSET_EQUALITY'
            outcomes=[]
            for rep in range(REPEATS):
                order=list(METHODS)
                random.Random(770720261+int(e['cnf_sha256'][:8],16)+rep*361).shuffle(order)
                for method in order:
                    r=run(a.native,a.kissat,method,original,
                          (770720261+int(e['cnf_sha256'][:8],16)+rep*37)%2**32)
                    status=r['answer']
                    if status not in ('SAT','TIMEOUT','ERROR'):
                        raise RuntimeError('Incorrect reported SAT class '+e['case']+' / '+method+': '+status)
                    outcome=dict(case=e['case'],rep=rep,method=method,
                      status=status,wall_seconds=round(float(r['elapsed_s']),6),
                      par2_seconds=round(float(r['elapsed_s']),6) if status=='SAT' else 2*CUTOFF,
                      phase_count=r.get('phase_count',''),extended=r.get('extended',''),
                      observer_clauses=r.get('observer_clauses',''),error=r.get('error',''),
                      cnf_sha256=e['cnf_sha256'],graph_sha256=e['graph_sha256'],
                      vertices=e['vertices'],edges=e['edges'])
                    rows.append(outcome);w.writerow(outcome);f.flush()
                    outcomes.append((method,status))
                    print('TRIAL',i+1,'/',len(entries),e['case'],rep,method,
                          status,round(float(r['elapsed_s']),5),'s',flush=True)
            checks.append(dict(case=e['case'],results=outcomes))
            print('GRAPH',i+1,'/',len(entries),e['case'],
                  'completed',sum(y=='SAT' for m,y in outcomes),'/10',flush=True)
    (out/'status_audit.json').write_text(json.dumps(checks,indent=2))
    print('PASS dataset complete,',len(rows),'trials for',len(entries),'certified 3-color graphs',flush=True)
if __name__=='__main__':main()
