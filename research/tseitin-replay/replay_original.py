"""Independent replay of the public SC2024 case against its frozen digest."""
import hashlib,json,subprocess,sys
from copy import deepcopy
from pathlib import Path
from proofcheck import dimacs, check_hidden
sys.path.insert(0,'research/drnas-sat-v7-8')
from official_shortlong_select import download_and_features

expected='4f67d895b9faabc983934cf1ce8233a666b88e8dc62937719fa24e2b41a10de7'
case='c69c5163c9087ffe770743bd4cdafcc9'
def main():
    p=Path('original.cnf')
    info=download_and_features(case,p)
    assert hashlib.sha256(p.read_bytes()).hexdigest()==info['sha256']==expected
    n,clauses=dimacs(p)
    assert (n,len(clauses))==(243,648)
    run=subprocess.run(['./bin/v144_native',str(p),'./bin/kissat_solver','0'],
                       text=True,capture_output=True,check=True,timeout=8)
    tag=[s for s in run.stdout.splitlines() if s.startswith('DRNAS_V144_RESULT\t')]
    assert len(tag)==1
    result=json.loads(tag[0].split('\t')[1])
    assert result['status']=='UNSAT' and result['path']=='hidden_parity_gf2'
    rows=result['proof']
    check_hidden(clauses,rows)
    for mutation in ('drop_row','flip_rhs'):
        bad=deepcopy(rows)
        if mutation=='drop_row':bad.pop()
        else:bad[0]['rhs']^=1
        try:check_hidden(clauses,bad)
        except (ValueError,AssertionError):pass
        else:raise ValueError('Invalid proof accepted')
    summary=dict(cnf_sha256=expected, variables=n, clauses=len(clauses), equations=len(rows),
                 referenced_clauses=len({i for r in rows for i in r['clause_indices']}),
                 xor_left=0,xor_right=1,rejected_tampered_proofs=2)
    for name, value in [('certificate',result),('replay',summary)]:
        Path(name+'.json').write_text(json.dumps(value,indent=2)+'\n')
    print(json.dumps(summary))
if __name__=='__main__':main()
