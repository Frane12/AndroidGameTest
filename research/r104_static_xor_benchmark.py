#!/usr/bin/env python3
"""R104 paired real SATLIB / synthetic Tseitin XOR experiment.

Methods: clean CaDiCaL, existing live bridge, certified root GF(2) with
binary-only or width<=4 parity consequences. All wallclock preparation charged.
"""
import argparse
import csv
import hashlib
import itertools
import json
import pathlib
import random
import subprocess
import sys
import time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r104_static_xor_prepass as prepass
import r88_cooperative as r88

def tseitin(path,vertices,seed,unsat):
    # 3-regular connected graph = randomized cycle + perfect antipodal matching.
    assert vertices%2==0 and vertices>=8
    rng=random.Random(seed)
    labels=list(range(vertices));rng.shuffle(labels)
    edges=[tuple(sorted((labels[i],labels[(i+1)%vertices])))
           for i in range(vertices)]
    edges += [tuple(sorted((labels[i],labels[i+vertices//2])))
              for i in range(vertices//2)]
    assert len(edges)==3*vertices//2 and len(set(edges))==len(edges)
    rng.shuffle(edges)
    adjacency=[[] for _ in range(vertices)]
    for i,(u,v) in enumerate(edges,1):
        adjacency[u].append(i);adjacency[v].append(i)
    assert all(len(a)==3 for a in adjacency)
    witness=[0]+[rng.randrange(2) for _ in edges]
    rhs=[sum(witness[i] for i in vs)%2 for vs in adjacency]
    if unsat:rhs[0]^=1
    # Each edge appears exactly twice; XOR over all equations forces 0=1
    # iff one vertex RHS was flipped. No single duplicated contradictory row.
    assert sum(rhs)%2==int(unsat)
    clauses=[]
    for vs,r in zip(adjacency,rhs):
        vs=sorted(vs)
        for bits in itertools.product((0,1),repeat=3):
            if sum(bits)%2!=r:
                clauses.append(tuple(-v if b else v for v,b in zip(vs,bits)))
    r88.write_augmented(len(edges),clauses,[],path)
    return 'UNSAT' if unsat else 'SAT'

def metric(log,name):
    for token in log.split():
        if token.startswith(name+'='):
            return int(token.split('=',1)[1])
    return 0

def run_solver(exe,mode,source,rows,cap,prep_s):
    t=time.perf_counter()
    txt=''
    try:
        x=subprocess.run([exe,mode,str(source),str(rows)],capture_output=True,
                         text=True,timeout=max(.01,cap-prep_s))
        solver_s=time.perf_counter()-t
        if x.returncode not in (10,20):
            raise RuntimeError(f'R104_FAIL_CLOSED solver mode={mode} exit={x.returncode} '
                               f'stderr={x.stderr[-1000:]} stdout={x.stdout[-1000:]}')
        result='SAT' if x.returncode==10 else 'UNSAT'
        if result=='SAT' and 'sat_model_checked=1' not in x.stdout:
            raise RuntimeError('R104_FAIL_CLOSED SAT model source CNF not checked')
        if 'disabled=1' in x.stdout:raise RuntimeError('R104_FAIL_CLOSED callback invalid')
        txt=x.stdout
        if solver_s+prep_s>cap:result='TIMEOUT'
    except subprocess.TimeoutExpired:
        solver_s=max(.01,cap-prep_s)
        result='TIMEOUT'
    total=solver_s+prep_s
    return result,round(solver_s,6),round(total,6),round(
        2*cap if result=='TIMEOUT' else total,6),metric(txt,'clauses_emitted')

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--real-root',required=True)
    ap.add_argument('--out',required=True)
    ap.add_argument('--solver',required=True)
    ap.add_argument('--cap',type=float,default=8.0)
    args=ap.parse_args()
    out=pathlib.Path(args.out);out.mkdir(parents=True,exist_ok=True)
    files=[p for p in sorted(pathlib.Path(args.real_root).rglob('*.cnf'))
           if p.stat().st_size<2000000]
    assert len(files)>=6
    selected=[files[0],files[1],files[len(files)//2],files[-3],files[-2],files[-1]]
    cases=[('real','unknown',p) for p in selected]
    for vertices in (16,32,48,64):
        for unsat in (False,True):
            p=out/f'tseitin_v{vertices}_seed104_unsat{int(unsat)}.cnf'
            expected=tseitin(p,vertices,104,unsat)
            cases.append(('tseitin',expected,p))
    records=[]
    methods=['clean','live','static2','static4']
    for origin,expected,path in cases:
        sha=hashlib.sha256(path.read_bytes()).hexdigest()
        derived={}
        for width in (2,4):
            name=f'static{width}'
            converted=out/f'{sha[:12]}.{name}.cnf'
            evidence=out/f'{sha[:12]}.{name}.json'
            diag=prepass.produce(path,converted,evidence,width=width)
            derived[name]=(converted,diag)
            if origin=='tseitin' and expected=='UNSAT' and not diag['contradiction']:
                raise RuntimeError('R104_FAIL_CLOSED synthetic parity UNSAT certificate missing')
            if origin=='tseitin' and expected=='SAT' and diag['contradiction']:
                raise RuntimeError('R104_FAIL_CLOSED contradiction on planted SAT witness')
        t=time.perf_counter()
        live_rows=out/f'{sha[:12]}.live.tsv'
        subprocess.run(['python3','research/r93_export_verified_rows.py','export',
                        '--cnf',str(path),'--rows',str(live_rows),
                        '--evidence',str(out/f'{sha[:12]}.live.json')],
                       check=True,timeout=90,capture_output=True,text=True)
        live_prep=time.perf_counter()-t
        for rep in range(2):
            order=methods[:]
            random.Random(sha+str(rep)+'R104').shuffle(order)
            for method in order:
                if method=='clean':
                    solve_source=path;mode='clean';rows=live_rows;prep=0.
                elif method=='live':
                    solve_source=path;mode='active';rows=live_rows;prep=live_prep
                else:
                    solve_source,diag=derived[method]
                    mode='clean';rows=live_rows;prep=diag['prep_s']
                if prep>=args.cap:
                    result='TIMEOUT';solver_s=0.;total=args.cap;par2=2*args.cap;emitted=0
                else:
                    result,solver_s,total,par2,emitted=run_solver(
                        args.solver,mode,solve_source,rows,args.cap,prep)
                if origin=='tseitin' and result!='TIMEOUT' and result!=expected:
                    raise RuntimeError(f'R104_FAIL_CLOSED synthetic answer discrepancy: '
                                       f'{path.name} {method} {result} expected={expected}')
                diag=derived.get(method,(None,{}))[1]
                records.append(dict(formula=path.name,sha256=sha,origin=origin,
                    expected=expected,rep=rep,method=method,status=result,
                    solver_s=solver_s,prep_s=round(prep,6),total_s=total,
                    par2_s=par2,emitted=emitted,
                    static_clauses=diag.get('new_clauses',0),
                    static_short_rows=diag.get('short_rows',0),
                    certified_xor_unsat=diag.get('contradiction',False),
                    source_xors=derived['static2'][1]['original_xors']))
        print('R104_CASE',path.name,'expected',expected,
              'original_xors',derived['static2'][1]['original_xors'],
              'GF2_unsat',derived['static2'][1]['contradiction'],
              'added2',derived['static2'][1]['new_clauses'],
              'added4',derived['static4'][1]['new_clauses'],flush=True)
    if len(records)!=len(cases)*2*len(methods):
        raise RuntimeError('R104 incorrect trial count')
    for origin,expected,path in cases:
        for rep in range(2):
            statuses={r['status'] for r in records
                      if r['formula']==path.name and r['rep']==rep
                      and r['status']!='TIMEOUT'}
            if len(statuses)>1:
                raise RuntimeError('R104_FAIL_CLOSED SAT/UNSAT mismatch')
    with (out/'paired.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]))
        w.writeheader();w.writerows(records)
    summary={}
    for origin in ('real','tseitin'):
        for method in methods:
            rr=[r for r in records if r['origin']==origin and r['method']==method]
            summary[f'{origin}_{method}']=dict(
                trials=len(rr),solved=sum(x['status']!='TIMEOUT' for x in rr),
                par2_s=round(sum(x['par2_s'] for x in rr),6),
                prep_s=round(sum(x['prep_s'] for x in rr),6),
                static_clauses=sum(x['static_clauses'] for x in rr),
                proof_unsat=sum(x['certified_xor_unsat'] for x in rr))
    report=dict(protocol='R104-PROOF-GF2-ROOT-EXPLORATORY',cases=len(cases),
        trials=len(records),cap_s=args.cap,summary=summary,
        notes='Same pinned solver; deterministic SATLIB dev and planted graph-parity Tseitin instances. Preparation charged per method. Static GF2 contradiction independently replayed against immutable complete 3-XOR CNF patterns. SAT models checked against augmented CNF. Real-world UNSAT without GF2 certificate not independently proved. Not blind holdout.')
    (out/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print('R104_COMPLETE_AUDIT',json.dumps(report),flush=True)

if __name__=='__main__':main()
