#!/usr/bin/env python3
"""Independent correctness and exact search/addition-stream invariance."""
import hashlib,itertools,json,os,random,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'research'))
from drnas_x5_mix96 import source
import drnas_x47_long_bench as B
KEYS=('conflicts','decisions','propagations','learnt','restarts','reduce_removed','binary_edges','binary_propagations')
def oracle(n,cs):
    return any(all(any(bits[abs(l)-1]==(l>0) for l in c) for c in cs) for bits in itertools.product((False,True),repeat=n))
def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});rng=random.Random(521113)
    cases=[]
    for i in range(144):
        n=rng.randrange(1,10);cs=[[v*rng.choice((-1,1)) for v in rng.sample(range(1,n+1),rng.randrange(1,min(n,4)+1))] for _ in range(rng.randrange(7*n+1))]
        cases.append({'name':f'truth_{i}','nvars':n,'nclauses':len(cs),'content':f'p cnf {n} {len(cs)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in cs),'expected':10 if oracle(n,cs) else 20})
    cases += [{'name':'empty_sat','nvars':0,'nclauses':0,'content':'p cnf 0 0\n','expected':10},{'name':'empty_unsat','nvars':0,'nclauses':1,'content':'p cnf 0 1\n0\n','expected':20}]
    for family,index in [('cardinality',9900004),('php',9600004),('random4',10500000)]:
        x=source(family,index);x['name']=family;x['expected']={'SAT':10,'UNSAT':20}.get(x['expected_status']);cases.append(x)
    rows=[];proofs=0;total_deletions=0
    with tempfile.TemporaryDirectory() as td:
        td=Path(td);cnf=td/'case.cnf';proof=td/'case.drat'
        for s in cases:
            cnf.write_text(s['content']);baseline=None
            for arm,binary,flags in [('X5','drnas-x5',[]),('X52_OFF','drnas-x52',[]),('X52_DELETE','drnas-x52',['--x52-proof-deletions'])]:
                start=time.monotonic()
                p=subprocess.run([str(ROOT/'build'/binary),str(cnf),'--mode','core','--time','20','--stats','--proof',str(proof),*flags],capture_output=True,text=True,timeout=23)
                solve=time.monotonic()-start;assert p.returncode in (10,20),(s['name'],arm,p.returncode,p.stderr[-1000:])
                if s['expected']:assert p.returncode==s['expected']
                st=json.loads(next(l[10:] for l in p.stderr.splitlines() if l.startswith('X41_STATS ')))
                additions=hashlib.sha256();deletions=0
                with proof.open('rb') as f:
                    for l in f:
                        if l.startswith(b'd '):deletions+=1
                        else:additions.update(l)
                identity=(p.returncode,tuple(st[k] for k in KEYS),additions.hexdigest())
                if baseline is None:baseline=identity
                else:assert identity==baseline,('search/addition stream changed',s['name'],arm)
                if arm=='X52_DELETE':assert deletions==st['reduce_removed']
                else:assert deletions==0
                start=time.monotonic()
                if p.returncode==10:assert B.verify_model_on_original_text(s,p.stdout)
                else:
                    q=subprocess.run([str(ROOT/'build/drat-trim'),str(cnf),str(proof)],capture_output=True,text=True,timeout=60)
                    assert 's VERIFIED' in q.stdout and (q.returncode==0 or 'c trivial UNSAT' in q.stdout),(s['name'],arm,q.stdout[-2000:],q.stderr)
                    proofs+=1
                check=time.monotonic()-start;total_deletions+=deletions
                rows.append({'case':s['name'],'arm':arm,'solve_s':solve,'check_s':check,'proof_bytes':proof.stat().st_size,'deleted':deletions,'conflicts':st['conflicts']})
        assert total_deletions>1000,total_deletions
        cnf.write_text('p cnf 2 1\n1 2 0\n');proof.write_text('d 1 2 0\n0\n')
        q=subprocess.run([str(ROOT/'build/drat-trim'),str(cnf),str(proof)],capture_output=True,text=True)
        assert 's VERIFIED' not in q.stdout
    result={'status':'PASS','runs':len(rows),'cases':len(cases),'verified_unsat_proofs':proofs,'proof_deletions_exercised':total_deletions,'replays':[r for r in rows if not r['case'].startswith(('truth_','empty_'))]}
    print(json.dumps(result,sort_keys=True));(ROOT/'build/test_x52_result.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
