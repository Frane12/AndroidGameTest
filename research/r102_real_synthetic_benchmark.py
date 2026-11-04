#!/usr/bin/env python3
"""R102 real SATLIB + synthetic parity: clean/monitor/active, paired, bounded."""
import argparse,csv,hashlib,itertools,json,pathlib,random,subprocess,time
def synthetic(path,n,k,seed,contradict):
    rng=random.Random(seed)
    witness=[0]+[rng.randrange(2) for _ in range(n)]
    clauses=[]; rows=[]
    for _ in range(k):
        vs=sorted(rng.sample(range(1,n+1),3))
        rhs=sum(witness[v] for v in vs)%2
        rows.append((vs,rhs))
    if contradict: rows.append((rows[0][0],1-rows[0][1]))
    for vs,rhs in rows:
        for bits in itertools.product((0,1),repeat=len(vs)):
            if sum(bits)%2!=rhs:
                clauses.append([(-v if b else v) for v,b in zip(vs,bits)])
    with open(path,'w') as f:
        f.write(f'p cnf {n} {len(clauses)}\n')
        for c in clauses:f.write(' '.join(map(str,c))+' 0\n')
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--real-root',required=True);ap.add_argument('--out',required=True);ap.add_argument('--solver',required=True);ap.add_argument('--cap',type=float,default=8);a=ap.parse_args()
    out=pathlib.Path(a.out);out.mkdir(parents=True,exist_ok=True)
    real=[p for p in sorted(pathlib.Path(a.real_root).rglob('*.cnf')) if p.stat().st_size<2000000]
    assert len(real)>=6
    real=[real[0],real[1],real[len(real)//2],real[-3],real[-2],real[-1]]
    cases=[('real',p) for p in real]
    for n,k in ((24,12),(36,24),(48,36)):
        for seed in (101,202):
            for unsat in (False,True):
                p=out/f'synthetic_n{n}_k{k}_seed{seed}_unsat{int(unsat)}.cnf'
                synthetic(p,n,k,seed,unsat);cases.append(('synthetic',p))
    records=[]
    for origin,p in cases:
        sha=hashlib.sha256(p.read_bytes()).hexdigest()
        rows=out/(sha[:16]+'.tsv');ev=out/(sha[:16]+'.proof.json')
        start=time.perf_counter()
        subprocess.run(['python3','research/r93_export_verified_rows.py','export','--cnf',str(p),'--rows',str(rows),'--evidence',str(ev)],check=True,timeout=60)
        prep=time.perf_counter()-start
        for rep in range(2):
            modes=['clean','monitor','active','select3','select4']
            random.Random(sha+str(rep)).shuffle(modes)
            for mode in modes:
                charged=0 if mode=='clean' else prep
                t=time.perf_counter()
                try:
                    r=subprocess.run([a.solver,mode,str(p),str(rows)],capture_output=True,text=True,timeout=max(.01,a.cap-charged))
                    elapsed=time.perf_counter()-t
                    if r.returncode not in (10,20):raise RuntimeError(f'FAIL CLOSED {p} {mode} exit {r.returncode}: {r.stderr[-300:]} {r.stdout[-300:]}')
                    status='SAT' if r.returncode==10 else 'UNSAT'
                    if status=='SAT' and 'sat_model_checked=1' not in r.stdout:raise RuntimeError('SAT model not checked')
                    if 'disabled=1' in r.stdout:raise RuntimeError('propagator disabled')
                    if elapsed+charged>a.cap:status='TIMEOUT'
                    txt=r.stdout
                except subprocess.TimeoutExpired:
                    elapsed=max(.01,a.cap-charged);status='TIMEOUT';txt=''
                def metric(k):
                    for token in txt.split():
                        if token.startswith(k+'='):return int(token.split('=',1)[1])
                    return 0
                records.append(dict(formula=p.name,sha256=sha,origin=origin,rep=rep,mode=mode,status=status,
                    solver_s=round(elapsed,6),prep_s=round(charged,6),total_s=round(elapsed+charged,6),
                    par2_s=round(2*a.cap if status=='TIMEOUT' else elapsed+charged,6),
                    emitted=metric('clauses_emitted'),signals=metric('live_signals'),
                    selective_rejected=metric('selective_rejected'),
                    watch_literal_probes=metric('watch_literal_probes')))
        print('R102_CASE',origin,p.name,'verified',json.loads(ev.read_text()).get('exported'),flush=True)
    assert len(records)==len(cases)*2*5
    for origin,p in cases:
        for rep in range(2):
            statuses={r['status'] for r in records if r['formula']==p.name and r['rep']==rep and r['status']!='TIMEOUT'}
            if len(statuses)>1:raise RuntimeError('SAT/UNSAT DISAGREEMENT '+p.name)
    with (out/'paired.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(records[0]));w.writeheader();w.writerows(records)
    summary={}
    for origin in ('real','synthetic'):
        for mode in ('clean','monitor','active','select3','select4'):
            rr=[r for r in records if r['origin']==origin and r['mode']==mode]
            summary[origin+'_'+mode]=dict(trials=len(rr),solved=sum(r['status']!='TIMEOUT' for r in rr),
                par2_s=round(sum(r['par2_s'] for r in rr),6),emitted=sum(r['emitted'] for r in rr))
    result=dict(protocol='R102-REAL-SATLIB-AND-SYNTHETIC-EXPLORATORY',cases=len(cases),trials=len(records),
      summary=summary,notes='Real SATLIB is previously used development data, not blind holdout. Synthetic planted SAT and contradictory parity UNSAT; UNSAT proofs not independently checked. All modes share formula, rep, cap and pinned solver. Preprocessing charged to monitor/active. Not a causal selective-clause ablation.')
    (out/'summary.json').write_text(json.dumps(result,indent=2))
    print('R102_COMPLETE_AUDIT',json.dumps(result),flush=True)
if __name__=='__main__':main()
