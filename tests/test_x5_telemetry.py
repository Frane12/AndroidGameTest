#!/usr/bin/env python3
"""Observational equivalence and preservation of progress after an external kill."""
import json,os,signal,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'research'))
import drnas_x5_diverse72 as D
import drnas_x5_bench as B

def stat(stderr):return json.loads(next(s[10:] for s in stderr.splitlines() if s.startswith('X41_STATS ')))
def main():
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    proved=0
    with tempfile.TemporaryDirectory() as temp:
        td=Path(temp);cnf=td/'case.cnf'
        for i,f in enumerate(D.FAMILIES):
            s=D.source(f,15003000+i%3);cnf.write_text(s['content']);results=[]
            for binary in ('drnas-x5','x5-telemetry'):
                proof=td/(binary+'.drat')
                p=subprocess.run([str(ROOT/'build'/binary),str(cnf),'--mode','core','--x5-no-minimize',
                    '--stats','--time','20','--proof',str(proof)],capture_output=True,text=True,timeout=25)
                assert p.returncode in (10,20),(binary,f,p.stderr[-1000:])
                if p.returncode==10:assert B.B.verify_model_on_original_text(s,p.stdout)
                else:
                    q=subprocess.run([str(ROOT/'build/drat-trim'),str(cnf),str(proof)],capture_output=True,text=True,timeout=20)
                    assert 's VERIFIED' in q.stdout and (q.returncode==0 or 'c trivial UNSAT' in q.stdout)
                    proved+=1
                results.append((p,proof.read_bytes()))
            left,right=results;assert left[0].returncode==right[0].returncode
            assert left[0].stdout==right[0].stdout and left[1]==right[1],('telemetry changed search output',f)
            s1,s2=stat(left[0].stderr),stat(right[0].stderr)
            for k in ('conflicts','decisions','propagations','learnt','restarts','reduce_removed'):assert s1[k]==s2[k],(f,k)
            events=[json.loads(x[12:]) for x in right[0].stderr.splitlines() if x.startswith('X5_PROGRESS ')]
            assert events[-1]['phase']=='finished' and events[-1]['conflicts']==s2['conflicts']
        # Large pigeonhole: a timeout must retain nonzero work and multiple time samples.
        holes=30;pigeons=31
        clauses=[[p*holes+h+1 for h in range(holes)] for p in range(pigeons)]
        clauses += [[-(p*holes+h+1),-(q*holes+h+1)] for h in range(holes) for p in range(pigeons) for q in range(p)]
        cnf.write_text(f'p cnf {holes*pigeons} {len(clauses)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in clauses))
        p=subprocess.Popen([str(ROOT/'build/x5-telemetry'),str(cnf),'--mode','core','--x5-no-minimize','--time','0'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
        try:p.communicate(timeout=2.25)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid,signal.SIGKILL);_,stderr=p.communicate()
        else:raise AssertionError('timeout fixture unexpectedly solved')
        events=[json.loads(x[12:]) for x in stderr.splitlines() if x.startswith('X5_PROGRESS ')]
        assert len(events)>=3 and events[-1]['elapsed_s']>=1.8 and events[-1]['conflicts']>0
        assert events[-1]['propagations']>0 and events[-1]['bcp_s']>0
        assert events[-1]['phase']=='search'
    print('X5_TELEMETRY_SELFTEST_PASS',json.dumps({'paired_formulas':12,'solver_runs':24,
        'independent_unsat_proofs':proved,'identical_search_counters_models_proofs':True,
        'external_timeout_retained_samples':len(events),'external_timeout_last':events[-1]}))
if __name__=='__main__':main()
