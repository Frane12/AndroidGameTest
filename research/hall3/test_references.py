#!/usr/bin/env python3
"""Check the exact external solver interfaces before spending benchmark time."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).resolve().parent))
import benchmark as B
sys.path.insert(0,str(ROOT/'research/pcmax_capacity'))
from test_clause_hall import php,write

def main():
    B.pin();out=ROOT/'hall3_reference_smoke';out.mkdir(exist_ok=False)
    count=0
    for i,(n,k) in enumerate([(3,2),(2,2)]):
        _,clauses=php(n,k);cnf=out/f'php-{n}-{k}.cnf';write(cnf,clauses,n*k)
        s=dict(id=i,family='reference_contract',path=str(cnf.relative_to(ROOT)),sha256=B.sha(cnf))
        for arm in ('Kissat','CaDiCaL'):
            r=B.trial(s,arm,0,out/f'{i}-{arm}',4)
            assert r['verified'] and r['strict_accepted']
            assert r['status']==('UNSAT_VERIFIED' if n>k else 'SAT_VERIFIED')
            count+=1
    B.emit('HALL3_REFERENCE_PASS',dict(trials=count))

if __name__=='__main__':main()
