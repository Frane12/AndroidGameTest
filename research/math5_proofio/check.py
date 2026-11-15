#!/usr/bin/env python3
"""Exact proof-sequence regression and paired original-CNF timing audit."""
import argparse,gzip,itertools,json,random,statistics,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'research/math5_general'))
import benchmark as b
ORIGINAL=b.command
VARIANT='TEXT'
def command(arm,cnf,proof,cert,cap):
    b.BIN[arm]='build/drnas-math5-text' if VARIANT=='BASE' else 'build/drnas-math5-proofio'
    c=ORIGINAL(arm,cnf,proof,cert,cap)
    if VARIANT=='TEXT':c+=['--proof-text']
    # BINARY deliberately supplies no format flag: test the production default.
    return c
b.command=command

def decode(data,binary):
    if not binary:return [list(map(int,l.split()))[:-1] for l in data.decode().splitlines()]
    rows=[];i=0
    while i<len(data):
        assert data[i]==97;i+=1;clause=[]
        while True:
            u=shift=0
            while True:
                c=data[i];i+=1;u|=(c&127)<<shift;shift+=7
                if c<128:break
            if not u:break
            clause.append(-(u>>1) if u&1 else u>>1)
        rows.append(clause)
    return rows

def selftest():
    global VARIANT
    b.pin();rng=random.Random(151126);cases=[]
    for i in range(40):
        n=6;clauses=[]
        for _ in range(12+i):
            clauses.append([v*rng.choice([-1,1]) for v in rng.sample(range(1,n+1),3)])
        sat=any(all(any((assignment[abs(l)-1])==(l>0) for l in c) for c in clauses) for assignment in itertools.product([False,True],repeat=n))
        cases.append((n,clauses,sat))
    for x,y in [(63,64),(8191,8192),(16383,16384)]:
        cases.append((y,[[x,y],[-x,y],[x,-y],[-x,-y]],False))
    counts={'SAT':0,'UNSAT':0,'proof_sequence_equal':0}
    with tempfile.TemporaryDirectory(prefix='proofio-control-',dir=ROOT) as tmp:
        folder=Path(tmp)
        for i,(n,clauses,sat) in enumerate(cases):
            cnf=folder/f'{i}.cnf';cnf.write_text(f'p cnf {n} {len(clauses)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in clauses))
            source=dict(id=i,family='CONTROL',path=str(cnf),sha256=b.sha(cnf));decoded=[]
            for VARIANT in ['BASE','TEXT','BINARY']:
                trialdir=folder/f'{i}-{VARIANT}';row=b.trial(source,'OFF',0,trialdir,cap=5)
                assert row['accepted'] and row['status']==('SAT_VERIFIED' if sat else 'UNSAT_VERIFIED'),row
                decoded.append(decode(gzip.decompress((trialdir/'proof.drat.gz').read_bytes()),VARIANT=='BINARY'))
                counts['SAT' if sat else 'UNSAT']+=1
            assert decoded[0]==decoded[1]==decoded[2],('changed_proof_sequence',i)
            counts['proof_sequence_equal']+=1
        # The checker must reject a forged binary empty-clause proof for SAT.
        cnf=folder/'reject.cnf';cnf.write_text('p cnf 2 1\n1 2 0\n')
        bad=folder/'bad.drat';bad.write_bytes(b'a\0')
        ck=b.run([str(ROOT/'build/drat-trim'),str(cnf),str(bad)],folder/'reject-check',5)
        assert ck['rc']!=0
    b.save(ROOT/'research/math5_proofio/selftest.json',counts)
    print('PROOFIO_SELFTEST_PASS '+json.dumps(counts))

def audit(source_dir):
    global VARIANT
    b.pin();sources=json.loads((source_dir/'manifest.json').read_text())['sources']
    out=ROOT/'proofio_results';out.mkdir(exist_ok=False);rows=[]
    for idx in [11,62,64,82,2,12,26]:
        source=dict(next(s for s in sources if s['id']==idx))
        source['path']=str(source_dir.parent/source['path'])
        for rep in range(3):
            for VARIANT in (['TEXT','BINARY'] if rep%2==0 else ['BINARY','TEXT']):
                row=b.trial(source,'MATH5',rep,out/f'{idx}-{rep}-{VARIANT}',cap=3 if idx in [2,12,26] else 10)
                row['variant']=VARIANT;rows.append(row)
                assert not row['critical'],row
    report=[]
    for idx in [11,62,64,82,2,12,26]:
        item=dict(id=idx)
        for v in ['TEXT','BINARY']:
            rr=[r for r in rows if r['id']==idx and r['variant']==v]
            item[v]=dict(accepted=sum(r['accepted'] for r in rr),median_e2e_s=statistics.median(r['e2e_s'] for r in rr),median_proof_bytes=statistics.median(r['proof_bytes'] for r in rr),median_cpu_s=statistics.median(r['solver_cpu_s'] for r in rr),statuses=[r['status'] for r in rr])
        report.append(item)
    b.save(ROOT/'research/math5_proofio/audit.json',dict(scope='Local diagnostic, seven previously seen originals; not GENERAL100 result.',trials=rows,summary=report))
    print('PROOFIO_AUDIT '+json.dumps(report))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['selftest','audit']);p.add_argument('--sources',type=Path);a=p.parse_args()
    if a.action=='selftest':selftest()
    else:audit(a.sources.resolve())
