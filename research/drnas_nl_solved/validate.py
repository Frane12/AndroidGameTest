#!/usr/bin/env python3
"""Semantic regression: exhaustive oracle, original SAT models, DRAT UNSAT."""
import itertools,json,os,random,subprocess,sys,tempfile
from pathlib import Path
R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/'research'))
import drnas_x55_cpu_real36 as B
def oracle(n,cs):
    return any(all(any(bits[abs(l)-1]==(l>0) for l in c) for c in cs)
               for bits in itertools.product((False,True),repeat=n))
def main():
    os.chdir(R);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    cases=[(3,[[1,1],[-1,2],[2,-2],[3,-3,3]]),(2,[[],[1]]),
           (3,[[3,-1,-2],[-3,1],[-3,2],[1],[2],[-3]]),
           (3,[[-3,1,2],[3,-1],[3,-2],[-1],[-2]])]
    for i in range(64):
        rng=random.Random(111400+i);n=5+i%4;cs=[]
        for _ in range(5+i%35):
            vs=rng.sample(range(1,n+1),rng.randint(1,3));cs.append([v*rng.choice([-1,1]) for v in vs])
        cases.append((n,cs))
    checked=0;sat=unsat=0
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        for i,(n,cs) in enumerate(cases):
            expected=10 if oracle(n,cs) else 20
            cnf=td/'case.cnf';cnf.write_text(f'c semantic case {i}\np cnf {n} {len(cs)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in cs))
            for mode in ('base','inplace','inputs','both'):
                proof=td/'proof.drat'
                p=subprocess.run(['build/drnas-nl-solved',str(cnf),'--mode','core','--time','1','--x5-no-minimize',
                    '--coop4','off','--coop5','off','--nl-focus',mode,'--proof',str(proof)],capture_output=True,text=True,timeout=3)
                assert p.returncode==expected,(i,mode,p.returncode,expected,p.stderr[-1000:])
                if expected==10:assert B.check_sat(p.stdout,cs,n);sat+=1
                else:
                    q=subprocess.run(['build/drat-trim',str(cnf),str(proof)],capture_output=True,text=True,timeout=5)
                    assert q.returncode>=0 and 's VERIFIED' in q.stdout,(i,mode,q.stdout);unsat+=1
                checked+=1
    report={'status':'PASS','cases':len(cases),'trials':checked,'sat_models_verified':sat,
            'unsat_drat_verified':unsat,'exhaustive_oracle':True,'duplicates_tautologies_empty_clause':True,
            'synthetic_correctness_only_not_speed_cohort':True}
    Path('nl_solved_validation.json').write_text(json.dumps(report,indent=2)+'\n')
    print('NL_VALIDATION_PASS',json.dumps(report))
if __name__=='__main__':main()
