#!/usr/bin/env python3
"""DRNAS Medical v0.1 paired SAT benchmark; charge preprocessing and verify models."""
import argparse,csv,hashlib,json,multiprocessing as mp,pathlib,subprocess,time,sys,queue

def parse(path):
    clauses=[];nv=None; nc=None
    for line in path.read_text().splitlines():
        line=line.strip()
        if not line or line.startswith('c'): continue
        if line.startswith('p '):
            parts=line.split()
            assert parts[:2]==['p','cnf'] and len(parts)==4
            nv,nc=int(parts[2]),int(parts[3]); continue
        clause=[int(v) for v in line.split()]
        assert clause[-1]==0
        clauses.append(clause[:-1])
    assert nv is not None and len(clauses)==nc
    assert all(1<=abs(l)<=nv for c in clauses for l in c)
    return nv,clauses

def verify_model(clauses,model):
    assign={abs(v):v>0 for v in model}
    return all(any(assign.get(abs(lit))==(lit>0) for lit in c) for c in clauses)

def worker(name,clauses,out):
    try:
        from pysat.solvers import Solver
        with Solver(name=name,bootstrap_with=clauses) as solver:
            start=time.perf_counter()
            sat=solver.solve()
            seconds=time.perf_counter()-start
            valid=(not sat or verify_model(clauses,solver.get_model() or []))
        out.put(dict(status='SAT' if sat else 'UNSAT',solver_s=round(seconds,6),valid=valid))
    except BaseException as exc:
        out.put(dict(status='ERROR',solver_s=0,valid=False,error=str(exc)))

def solve(name,clauses,cap):
    ctx=mp.get_context('spawn')
    out=ctx.Queue()
    p=ctx.Process(target=worker,args=(name,clauses,out))
    started=time.perf_counter()
    p.start()
    p.join(cap)
    if p.is_alive():
        p.terminate()
        p.join(5)
        result=dict(status='TIMEOUT',solver_s=cap,valid=False)
    else:
        try: result=out.get(timeout=1)
        except queue.Empty:
            result=dict(status='ERROR',solver_s=0,valid=False,error='solver returned no result')
    result['wall_s']=round(time.perf_counter()-started,6)
    out.close()
    return result

def check(record,expected):
    if record['status']=='ERROR':
        raise RuntimeError('solver error: '+str(record))
    if record['status']=='SAT' and not record['valid']:
        raise RuntimeError('invalid SAT witness')
    if expected in ('SAT','UNSAT') and record['status'] in ('SAT','UNSAT') and record['status']!=expected:
        raise RuntimeError('wrong result: expected '+expected+' got '+record['status'])

def benchmark(root,cap,repeats,r108_limit):
    manifest=json.loads((root/'manifest.json').read_text())
    assert manifest['protocol']=='DRNAS-MEDICAL-V0.1-BOOLEAN-SYNTHETIC'
    records=[]
    scan_indices=[i for i,x in enumerate(manifest['cases']) if x['nodes']==6 and x['period']==1]
    scan_indices += [i for i,x in enumerate(manifest['cases'])
                     if x['family']=='xor' and x['nodes']==6 and x['period']==2]
    scan_indices=set(scan_indices[:r108_limit])
    for ix,item in enumerate(manifest['cases']):
        path=root/item['name']
        assert hashlib.sha256(path.read_bytes()).hexdigest()==item['sha256']
        _,original=parse(path)
        prepped=root/'preprocessed'/path.name
        prep_s=0;certified=False;prep_status='SKIPPED'
        if ix in scan_indices:
            prepped.parent.mkdir(exist_ok=True)
            evidence=root/'preprocessed'/(path.stem+'.json')
            started=time.perf_counter()
            try:
                p=subprocess.run([sys.executable,'research/r108_hidden_xor.py','export',
                                  '--cnf',str(path),'--out',str(evidence),
                                  '--augmented',str(prepped),'--rounds','1'],
                                 capture_output=True,text=True,timeout=12)
                prep_s=time.perf_counter()-started
                if p.returncode: raise RuntimeError('R108 failed: '+p.stderr[-500:])
                meta=json.loads(evidence.read_text())
                assert meta['sha256']==item['sha256']
                certified=bool(meta['gf2_unsat'])
                if certified:
                    assert parse(prepped)[1][-1]==[]
                else:
                    assert prepped.read_bytes()==path.read_bytes()
                prep_status='COMPLETE'
            except subprocess.TimeoutExpired:
                prep_s=time.perf_counter()-started
                prep_status='TIMEOUT'
        candidates=[('cadical195',path,0),('kissat404',path,0),('minisat22',path,0)]
        if prep_status=='COMPLETE':
            candidates.append(('r108+cadical195',prepped,prep_s))
        for rep in range(repeats):
            for label,file,overhead in candidates:
                _,clauses=parse(file)
                method='cadical195' if label.startswith('r108+') else label
                remaining=max(.01,cap-overhead)
                res=(dict(status='TIMEOUT',solver_s=0.,wall_s=0.,valid=False)
                     if overhead>=cap else solve(method,clauses,remaining))
                check(res,item['expected'])
                if certified and label=='r108+cadical195' and item['expected']=='SAT':
                    raise RuntimeError('R108 unsound UNSAT proof on SAT instance')
                record=dict(case=item['name'],family=item['family'],nodes=item['nodes'],period=item['period'],
                    sha256=item['sha256'],expected=item['expected'],repeat=rep,method=label,
                    status=res['status'],valid=res['valid'],prep_s=round(overhead,6),
                    solver_s=res['solver_s'],wall_s=res['wall_s'],
                    total_s=round(overhead+res['wall_s'],6),
                    par2_s=round(2*cap if res['status']=='TIMEOUT' else overhead+res['wall_s'],6),
                    certified_r108_unsat=certified if label.startswith('r108+') else False,
                    prepass_status=prep_status if label.startswith('r108+') else '')
                records.append(record)
                print('DRNAS_MEDICAL_TRIAL',json.dumps(record),flush=True)
    observed={}
    for r in records:
        if r['status'] in ('SAT','UNSAT'):
            old=observed.setdefault(r['case'],r['status'])
            if r['status']!=old: raise RuntimeError('cross-solver disagreement: '+r['case'])
    with (root/'paired.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]))
        w.writeheader()
        w.writerows(records)
    summary={m:dict(trials=sum(r['method']==m for r in records),
                    solved=sum(r['method']==m and r['status'] in ('SAT','UNSAT') for r in records),
                    total_par2_s=round(sum(r['par2_s'] for r in records if r['method']==m),6))
             for m in sorted({r['method'] for r in records})}
    report=dict(protocol='DRNAS-MEDICAL-V0.1-SYNTHETIC-PILOT',
        model_origin='synthetic_biology_inspired_not_real_biomedical_data',
        cap_s=cap,repeats=repeats,formula_count=len(manifest['cases']),
        compared_methods=summary,
        notes='wall_s includes solver process launch; DRNAS includes R108 preprocessing. '
        'Not a drug-discovery result, not a clinical model, not evidence of general superiority.')
    (root/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print('DRNAS_MEDICAL_SUMMARY',json.dumps(report),flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--dir',default='medical-results/cnfs')
    p.add_argument('--cap',type=float,default=8.)
    p.add_argument('--repeats',type=int,default=2)
    p.add_argument('--r108-limit',type=int,default=6)
    args=p.parse_args()
    benchmark(pathlib.Path(args.dir),args.cap,args.repeats,args.r108_limit)

if __name__=='__main__': main()
