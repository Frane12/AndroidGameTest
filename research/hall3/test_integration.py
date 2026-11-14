#!/usr/bin/env python3
"""Truth-table oracle, proof routing, and frozen CF7 search parity."""
import hashlib,itertools,json,os,random,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).resolve().parent))
import benchmark as B
sys.path.insert(0,str(ROOT/'research/pcmax_capacity'))
from test_clause_hall import php,write
sys.path.insert(0,str(ROOT/'research/pcmax_capacity/tests'))
from make_fixtures import build_scheduling,oracle

def main():
    B.pin();out=ROOT/'hall3_safety';out.mkdir(exist_ok=False)
    cases=[];rng=random.Random(2026111491)
    for i in range(64):
        n=rng.randrange(3,9);clauses=[]
        for _ in range(rng.randrange(2,45)):
            variables=rng.sample(range(1,n+1),rng.randrange(1,min(4,n)+1))
            clauses.append(tuple(v if rng.randrange(2) else -v for v in variables))
        sat=any(all(any(bits[abs(l)-1]==(l>0) for l in c) for c in clauses)
            for bits in itertools.product((False,True),repeat=n))
        cases.append((f'oracle-{i}',n,clauses,sat))
    for n,k in [(5,4),(4,4),(19,18),(18,18)]:
        _,clauses=php(n,k,signed=True);cases.append((f'hall-{n}-{k}',n*k,clauses,n<=k))
    for i,args in enumerate([([6,6,6],2,10),([6,4,6,4],2,10),([3,3,3,3,3],2,8)]):
        nv,clauses,groups,_=build_scheduling(*args)
        sat=oracle(nv,clauses,groups)['status']=='SAT'
        cases.append((f'weighted-{i}',nv,clauses,sat))
    totals=dict(cases=len(cases),verified=0,structural=0,drat_fallback=0,frozen_parity=0)
    for i,(name,nv,clauses,sat) in enumerate(cases):
        cnf=out/(name+'.cnf');write(cnf,clauses,nv)
        source=dict(id=i,family='safety',path=str(cnf.relative_to(ROOT)),sha256=B.sha(cnf))
        row=B.trial(source,'HALL3_ON',0,out/(name+'-on'),cap=4)
        assert row['verified'] and row['status']==('SAT_VERIFIED' if sat else 'UNSAT_VERIFIED'),(name,row)
        totals['verified']+=1
        totals['structural']+=str(row['certificate_kind']).startswith('STRUCTURAL')
        totals['drat_fallback']+=row['certificate_kind']=='DRAT'
        # Large pigeonhole is deliberately not solved by unassisted CF7 in this safety check.
        if nv<=32:
            off=out/(name+'-off');off.mkdir()
            cmd=B.command('CF7_OFF',cnf,off/'p.drat',off/'c.json',4)
            a=subprocess.run(cmd,capture_output=True,text=True,timeout=6)
            cmd[0]=str(ROOT/'build/drnas-cf7-frozen');cmd[cmd.index('--proof')+1]=str(off/'frozen.drat')
            b=subprocess.run(cmd,capture_output=True,text=True,timeout=6)
            assert a.returncode==b.returncode==(10 if sat else 20),(name,a.returncode,b.returncode)
            assert a.stdout==b.stdout,(name,'model/status parity')
            assert (off/'p.drat').read_bytes()==(off/'frozen.drat').read_bytes(),(name,'proof parity')
            totals['frozen_parity']+=1
    assert totals['structural']>=2 and totals['drat_fallback']>=1
    # A shared proof/certificate target must fail before either output is written.
    target=out/'collision.proof'
    p=subprocess.run([str(ROOT/'build/drnas-hall3'),str(out/'hall-5-4.cnf'),
        '--mode','core','--hall3','--proof',str(target),'--pcmax-certificate',str(target)],capture_output=True)
    assert p.returncode not in (0,10,20) and not target.exists()
    B.save(out/'summary.json',totals);B.emit('HALL3_SAFETY_PASS',totals)

if __name__=='__main__':main()
