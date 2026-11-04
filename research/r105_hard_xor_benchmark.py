#!/usr/bin/env python3
"""R105: precommitted hard graph-Tseitin + previously unused SATLIB parity subset.

No instance chosen based on performance; per-instance SHA manifest and deterministic
random order. SAT/UNSAT agreement required; synthetic UNSAT requires independent
GF(2) ancestry replay, and SAT models are verified by the native solver.
"""
import argparse,csv,hashlib,itertools,json,pathlib,random,subprocess,sys,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'experiments'/'drnas_v16'))
import r88_cooperative as r88
import r104_static_xor_prepass as static
import r105_gf2_contradiction_only as certificate

FROZEN_R101_R104_USED={
    'par16-1-c.cnf','par16-1.cnf','par32-3.cnf','par32-4-c.cnf',
    'par8-4.cnf','par8-5-c.cnf','par8-5.cnf'
}
METHODS=('clean','gf2cert','static2')
FROZEN_SEEDS=(105019,105031)
FROZEN_SIZES=(128,256,512,1024,2048)
SAT_CONTROLS=(256,1024)

def hard_tseitin(path,vertices,seed,contradict):
    """Connected Hamiltonian cubic graph; independently randomized perfect matching.

    This graph differs structurally from R104's antipodal cycle matching.
    """
    assert vertices>=8 and vertices%2==0
    rng=random.Random(seed ^ (vertices*0x9e3779b1))
    order=list(range(vertices));rng.shuffle(order)
    ring={tuple(sorted((order[i],order[(i+1)%vertices])))
          for i in range(vertices)}
    assert len(ring)==vertices
    matching=None
    for attempt in range(300):
        candidates=list(range(vertices));rng.shuffle(candidates)
        pairs={tuple(sorted((candidates[i],candidates[i+1])))
               for i in range(0,vertices,2)}
        if len(pairs)==vertices//2 and not (pairs & ring):
            matching=pairs
            break
    if matching is None:raise RuntimeError('R105_FAIL_CLOSED matching generation exhausted')
    edges=sorted(ring|matching)
    rng.shuffle(edges)
    adj=[[] for _ in range(vertices)]
    for i,(u,v) in enumerate(edges,1):
        adj[u].append(i);adj[v].append(i)
    if not all(len(x)==3 for x in adj):raise RuntimeError('R105_FAIL_CLOSED degree mismatch')
    witness=[0]+[rng.randrange(2) for _ in edges]
    rhs=[sum(witness[i] for i in vs)%2 for vs in adj]
    if contradict:rhs[0]^=1
    if sum(rhs)%2!=int(contradict):
        raise RuntimeError('R105_FAIL_CLOSED inconsistent parity label')
    clauses=[]
    for vs,bit in zip(adj,rhs):
        vs=sorted(vs)
        for signs in itertools.product((0,1),repeat=3):
            if sum(signs)%2 != bit:
                clauses.append(tuple(-v if b else v for v,b in zip(vs,signs)))
    r88.write_augmented(len(edges),clauses,[],path)
    return ('UNSAT' if contradict else 'SAT')

def metric(output,name):
    for token in output.split():
        if token.startswith(name+'='):
            try:return int(token.split('=',1)[1])
            except ValueError:pass
    return 0

def solve(exe,source,rows,cap,prep):
    elapsed=0.
    if prep>=cap:
        return dict(status='TIMEOUT',solver_s=0.,total_s=cap,par2_s=2*cap,emitted=0)
    start=time.perf_counter()
    try:
        result=subprocess.run([exe,'clean',str(source),str(rows)],
                              capture_output=True,text=True,timeout=max(.01,cap-prep))
        elapsed=time.perf_counter()-start
        if result.returncode not in (10,20):
            raise RuntimeError(f'R105_FAIL_CLOSED: native solver code={result.returncode} '
                               f'stderr={result.stderr[-500:]} stdout={result.stdout[-500:]}')
        status='SAT' if result.returncode==10 else 'UNSAT'
        if status=='SAT' and 'sat_model_checked=1' not in result.stdout:
            raise RuntimeError('R105_FAIL_CLOSED unverified SAT model')
        if elapsed+prep>cap:status='TIMEOUT'
        log=result.stdout
    except subprocess.TimeoutExpired:
        elapsed=max(.01,cap-prep)
        status='TIMEOUT'
        log=''
    total=elapsed+prep
    return dict(status=status,solver_s=round(elapsed,6),
                total_s=round(total,6),
                par2_s=round(2*cap if status=='TIMEOUT' else total,6),
                emitted=metric(log,'clauses_emitted'))

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--real-root',required=True)
    p.add_argument('--out',required=True)
    p.add_argument('--solver',required=True)
    p.add_argument('--cap',type=float,default=12.)
    a=p.parse_args()
    out=pathlib.Path(a.out);out.mkdir(parents=True,exist_ok=True)
    all_real=[f for f in pathlib.Path(a.real_root).rglob('*.cnf')
              if f.stat().st_size<2_000_000 and f.name not in FROZEN_R101_R104_USED]
    # Selection by hash before running any solver, not cherry-picked by difficulty.
    real=sorted(all_real,key=lambda x:hashlib.sha256(x.read_bytes()).hexdigest())[:4]
    cases=[dict(origin='satlib_unused_R101_R104',expect='unknown',source=x)
           for x in real]
    for size in FROZEN_SIZES:
        for seed in FROZEN_SEEDS:
            path=out/f'hard_cubic_v{size}_seed{seed}_UNSAT.cnf'
            expected=hard_tseitin(path,size,seed,True)
            cases.append(dict(origin='hard_tseitin',expect=expected,source=path))
    for size in SAT_CONTROLS:
        seed=105043
        path=out/f'hard_cubic_v{size}_seed{seed}_SAT.cnf'
        expected=hard_tseitin(path,size,seed,False)
        cases.append(dict(origin='hard_tseitin',expect=expected,source=path))
    manifest=[]
    for obj in cases:
        s=obj['source']
        manifest.append(dict(formula=s.name,sha256=hashlib.sha256(s.read_bytes()).hexdigest(),
                             origin=obj['origin'],expected=obj['expect']))
    (out/'manifest.json').write_text(json.dumps(
        dict(protocol='R105-FROZEN-SIZE-SEEDS-AND-EXCLUSIONS',cases=manifest,
             sizes=FROZEN_SIZES,seeds=FROZEN_SEEDS,
             exclusions=sorted(FROZEN_R101_R104_USED)),indent=2)+'\n')
    print('R105_FROZEN_MANIFEST',json.dumps(manifest),flush=True)
    dummy=out/'unused.tsv'
    dummy.write_text('# clean mode: no external propagator\n')
    records=[]
    for i,obj in enumerate(cases):
        path=obj['source'];sha=manifest[i]['sha256']
        cert_path=out/(sha[:14]+'.cert.cnf')
        cert_report=out/(sha[:14]+'.cert.json')
        cert=certificate.run(path,cert_path,cert_report)
        static_path=out/(sha[:14]+'.static2.cnf')
        static_report=out/(sha[:14]+'.static2.json')
        static2=static.produce(path,static_path,static_report,width=2)
        if cert['contradiction']!=static2['contradiction']:
            raise RuntimeError('R105_FAIL_CLOSED independent GF2 strategies disagree')
        if obj['expect']=='UNSAT' and not cert['contradiction']:
            raise RuntimeError('R105_FAIL_CLOSED missing synthetic UNSAT certificate')
        if obj['expect']=='SAT' and cert['contradiction']:
            raise RuntimeError('R105_FAIL_CLOSED false UNSAT on planted SAT')
        configs={'clean':(path,0.),
                 'gf2cert':(cert_path,cert['prep_s']),
                 'static2':(static_path,static2['prep_s'])}
        for rep in range(2):
            methods=list(METHODS)
            random.Random(sha+str(rep)+'R105').shuffle(methods)
            for method in methods:
                cnf,prep=configs[method]
                data=solve(a.solver,cnf,dummy,a.cap,prep)
                if obj['expect']!='unknown' and data['status']!='TIMEOUT' and data['status']!=obj['expect']:
                    raise RuntimeError(f'R105_FAIL_CLOSED wrong synthetic answer: '
                                       f'{path.name} {method} {data["status"]}')
                records.append(dict(formula=path.name,sha256=sha,origin=obj['origin'],
                                    expected=obj['expect'],rep=rep,method=method,
                                    prep_s=round(prep,7),
                                    xor_count=cert['original_xors'],
                                    gf2_contradiction=cert['contradiction'],
                                    derived_binary_clauses=static2['new_clauses'],**data))
        print('R105_CASE',path.name,'expected',obj['expect'],
              'gf2_proof',cert['contradiction'],
              'prep_ms',round(cert['prep_s']*1000,2),
              'method_results',json.dumps({method:[
                    dict(rep=r['rep'],status=r['status'],par2=r['par2_s'])
                    for r in records if r['formula']==path.name and r['method']==method]
                  for method in METHODS}),flush=True)
    if len(records)!=len(cases)*2*len(METHODS):
        raise RuntimeError('R105_FAIL_CLOSED incomplete paired trials')
    for obj in cases:
        path=obj['source']
        for rep in range(2):
            statuses={r['status'] for r in records if r['formula']==path.name
                     and r['rep']==rep and r['status']!='TIMEOUT'}
            if len(statuses)>1:
                raise RuntimeError(f'R105_FAIL_CLOSED SAT/UNSAT disagreement {path.name}')
    with (out/'paired.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(records[0]))
        writer.writeheader();writer.writerows(records)
    summary={}
    for origin in ('satlib_unused_R101_R104','hard_tseitin'):
        for method in METHODS:
            rr=[r for r in records if r['origin']==origin and r['method']==method]
            summary[f'{origin}_{method}']=dict(
                trials=len(rr),solved=sum(r['status']!='TIMEOUT' for r in rr),
                par2_s=round(sum(r['par2_s'] for r in rr),6),
                prep_s=round(sum(r['prep_s'] for r in rr),6),
                gf2_proofs=sum(r['gf2_contradiction'] for r in rr))
    audit=dict(protocol='R105-HARD-CUBIC-TSEITIN-PAIRED',cases=len(cases),
               trials=len(records),cap_s=a.cap,
               real_dev_cases=len(real),synthetic_cases=len(cases)-len(real),
               summary=summary,notes='SATLIB only excluded R101/R104 previously used names, not a project-wide or SAT Competition blind holdout. Synthetic instances are seeded new Hamiltonian cubic graphs, no result-based selection. Same pinned CaDiCaL, full prep time counted, timeouts PAR2. Verified 3-XOR input signatures, certified GF2 contradiction ancestry replay; synthetic SAT models checked, synthetic UNSAT graph parity proven. Timed-out baseline only supports cap-limited lower bounds.')
    (out/'summary.json').write_text(json.dumps(audit,indent=2)+'\n')
    print('R105_COMPLETE_AUDIT',json.dumps(audit),flush=True)
if __name__=='__main__':main()
