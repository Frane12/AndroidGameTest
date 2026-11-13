#!/usr/bin/env python3
"""Independent truth table / original witness / DRAT checks; never solver agreement alone."""
import itertools,json,os,random,subprocess,tempfile,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'research'))
import drnas_x47_long_bench as B

def oracle(n,cs):
    for bits in itertools.product((False,True),repeat=n):
        if all(any(bits[abs(l)-1]==(l>0) for l in c) for c in cs):return True
    return False

def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    rng=random.Random(513113)
    count=0;unsats=0;events={}
    binary=ROOT/'build/drnas-x51';checker=ROOT/'build/drat-trim'
    variants=[['--x51-telemetry'],['--x51-bounded','--x51-telemetry'],['--x51-adaptive','--x51-telemetry'],['--x51-bounded','--x51-budget','1','--x51-telemetry']]
    with tempfile.TemporaryDirectory() as td:
        cnf=Path(td)/'case.cnf';proof=Path(td)/'case.drat'
        cases=[(0,[]),(0,[[]]),(1,[[1],[-1]]),(3,[[1,1],[-1,2],[2,-2],[3]])]
        for i in range(260):
            n=rng.randrange(1,11)
            cs=[]
            for _ in range(rng.randrange(0,7*n+1)):
                vs=rng.sample(range(1,n+1),rng.randrange(1,min(n,4)+1))
                cs.append([v*rng.choice((-1,1)) for v in vs])
            cases.append((n,cs))
        for n,cs in cases:
            expected=oracle(n,cs)
            text=f'p cnf {n} {len(cs)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in cs)
            cnf.write_text(text)
            source={'nvars':n,'nclauses':len(cs),'content':text}
            if count%52==0:
                frozen=subprocess.run([str(ROOT/'build/frozen-core'),str(cnf),'--mode','core','--stats'],capture_output=True,text=True,timeout=5)
                logged=subprocess.run([str(ROOT/'build/frozen-proof'),str(cnf),'--mode','core','--stats','--proof',str(proof)],capture_output=True,text=True,timeout=5)
                assert frozen.returncode==logged.returncode==(10 if expected else 20)
                fs=json.loads(next(l[10:] for l in frozen.stderr.splitlines() if l.startswith('X41_STATS ')))
                ls=json.loads(next(l[10:] for l in logged.stderr.splitlines() if l.startswith('X41_STATS ')))
                for k in ('conflicts','decisions','propagations','learnt','restarts','reduce_removed'):
                    assert fs[k]==ls[k],('proof logging altered frozen search',k,fs[k],ls[k])
            old=subprocess.run([str(ROOT/'build/drnas-x5'),str(cnf),'--mode','core','--stats'],capture_output=True,text=True,timeout=5)
            passive=subprocess.run([str(binary),str(cnf),'--mode','core','--stats','--x51-telemetry'],capture_output=True,text=True,timeout=5)
            assert old.returncode==passive.returncode==(10 if expected else 20)
            get=lambda q:json.loads(next(l[10:] for l in q.stderr.splitlines() if l.startswith('X41_STATS ')))
            for k in ('conflicts','decisions','propagations','learnt','restarts','reduce_removed'):
                assert get(old)[k]==get(passive)[k],('passive changed search',k)
            for flags in variants:
                p=subprocess.run([str(binary),str(cnf),'--mode','core','--time','3','--proof',str(proof),*flags],capture_output=True,text=True,timeout=5)
                assert p.returncode==(10 if expected else 20),(n,cs,flags,p.stderr)
                if expected:assert B.verify_model_on_original_text(source,p.stdout)
                else:
                    q=subprocess.run([str(checker),str(cnf),str(proof)],capture_output=True,text=True,timeout=5)
                    assert (q.returncode==0 or 'c trivial UNSAT' in q.stdout) and 's VERIFIED' in q.stdout,(flags,q.stdout,q.stderr)
                    unsats+=1
                count+=1
        for fam in B.SYNTH_FAMILIES:
            for i in range(3):
                source=B.make_synthetic(fam,5100000+i)
                cnf.write_text(source['content'])
                for flags in variants:
                    p=subprocess.run([str(binary),str(cnf),'--mode','core','--time','0.7','--stats','--proof',str(proof),*flags],capture_output=True,text=True,timeout=3)
                    assert p.returncode in (0,10,20),p.stderr
                    if p.returncode==10:assert B.verify_model_on_original_text(source,p.stdout)
                    if p.returncode==20:
                        assert source['cert']=='PHP_STRUCTURAL_CORE'
                        q=subprocess.run([str(checker),str(cnf),str(proof)],capture_output=True,text=True,timeout=15)
                        assert (q.returncode==0 or 'c trivial UNSAT' in q.stdout) and 's VERIFIED' in q.stdout,q.stdout
                        unsats+=1
                    telemetry=json.loads([l[10:] for l in p.stderr.splitlines() if l.startswith('X51_STATS ')][-1])
                    if '--x51-bounded' in flags or '--x51-adaptive' in flags:
                        assert telemetry['max_clause_work'] <= (1 if '--x51-budget' in flags else 256),telemetry
                    st=json.loads(next(l[9:] for l in p.stderr.splitlines() if l.startswith('X5_STATS ')))
                    for k,v in st.items():events[k]=events.get(k,0)+v
                    count+=1
        # Require that tests actually exercise minimization and physical collection.
        assert events['minimized_literals']>0 and events['collections']>0,events
        # Reject syntactically invalid source rather than claiming UNSAT.
        for text in ['p cnf 1 1\n2 0\n','p cnf 1 2\n1 0\n']:
            cnf.write_text(text)
            p=subprocess.run([str(binary),str(cnf)],capture_output=True)
            assert p.returncode==1
        # Independent checker must reject a deliberately false refutation.
        cnf.write_text('p cnf 2 1\n1 2 0\n');proof.write_text('0\n')
        q=subprocess.run([str(checker),str(cnf),str(proof)],capture_output=True,text=True)
        assert 's VERIFIED' not in q.stdout
    result={'runs':count,'independent_unsat_proofs':unsats,'events':events,'status':'PASS'}
    print(json.dumps(result,sort_keys=True))
    (ROOT/'build/test_x51_result.json').write_text(json.dumps(result,indent=2)+'\n')
if __name__=='__main__':main()
