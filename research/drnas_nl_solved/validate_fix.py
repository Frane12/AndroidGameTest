#!/usr/bin/env python3
import json,os,random,subprocess,sys,tempfile
from pathlib import Path
R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/'research/drnas_nl_solved'))
import bench as T
from validate import oracle
def main():
    os.chdir(R);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    frozen_before=T.sha('build/drnas-nl-solved')
    cases=[(3,[[1,1],[-1,2],[2,-2],[3,-3,3]]),(2,[[],[1]]),
           (3,[[3,-1,-2],[-3,1],[-3,2],[1],[2],[-3]]),
           (3,[[-3,1,2],[3,-1],[3,-2],[-1],[-2]])]
    for i in range(64):
        rng=random.Random(111400+i);n=5+i%4;cs=[]
        for _ in range(5+i%35):
            vs=rng.sample(range(1,n+1),rng.randint(1,3));cs.append([v*rng.choice([-1,1]) for v in vs])
        cases.append((n,cs))
    sat=unsat=0;out=Path('nl_fixed_validation');out.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        td=Path(td);cnf=td/'case.cnf';proof=td/'proof.drat'
        for i,(n,cs) in enumerate(cases):
            expected=10 if oracle(n,cs) else 20
            cnf.write_text(f'p cnf {n} {len(cs)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in cs))
            for mode in ('base','fixed','observe'):
                p=subprocess.run(['build/drnas-nl-fixed',str(cnf),'--mode','core','--time','1','--x5-no-minimize',
                    '--coop4','off','--coop5','off','--nl-focus',mode,'--proof',str(proof)],capture_output=True,text=True,timeout=3)
                assert p.returncode==expected,(i,mode,p.returncode,expected)
                if expected==10:assert T.B.check_sat(p.stdout,cs,n);sat+=1
                else:
                    q=subprocess.run(['build/drat-trim',str(cnf),str(proof)],capture_output=True,text=True,timeout=5)
                    assert q.returncode>=0 and 's VERIFIED' in q.stdout,(i,mode,q.stdout);unsat+=1
        for mode in ('inputs','both'):
            p=subprocess.run(['build/drnas-nl-fixed',str(cnf),'--nl-focus',mode],capture_output=True,text=True,timeout=2)
            assert p.returncode not in (0,10,20) and 'unsafe AND branching prior removed' in p.stderr
    real=[]
    for s in json.load(open('research/drnas_nl_solved/cohort_summary.json'))['sources']:
        assert T.sha(s['path'])==s['sha256'];n,cs=T.B.parse_cnf(Path(s['path']).read_bytes());traces={};models={};stats={}
        for arm,bin,mode in [('FROZEN_BASE','build/drnas-nl-solved','base'),('FIXED','build/drnas-nl-fixed',None),('OBSERVE','build/drnas-nl-fixed','observe')]:
            trace=out/f"{s['id']}-{arm}.jsonl"
            cmd=[bin,s['path'],'--mode','trace','--transitions',str(trace),'--time','1','--x5-no-minimize','--coop4','off','--coop5','off','--stats']
            if mode:cmd+=['--nl-focus',mode]
            p=subprocess.run(cmd,capture_output=True,text=True,timeout=2)
            assert p.returncode==10 and T.B.check_sat(p.stdout,cs,n),(s['id'],arm)
            models[arm]=p.stdout;st=T.events(p.stderr,'X41_STATS')[0];stats[arm]=st
            tr=[json.loads(l) for l in trace.read_text().splitlines()];traces[arm]=[x['decision_literal'] for x in tr if x['type']=='transition']
            if arm=='OBSERVE':
                gate=T.events(p.stderr,'NL_FOCUS')[0];assert gate['gates']>0 and gate['blocked_prior_variables']>0 and gate['actual_branch_overrides']==0
        assert traces['FROZEN_BASE']==traces['FIXED']==traces['OBSERVE']
        assert models['FROZEN_BASE']==models['FIXED']==models['OBSERVE']
        assert all(st['decisions']==32 and st['conflicts']==0 for st in stats.values())
        real.append({'id':s['id'],'name':s['filename'],'decision_literals':traces['FIXED'],'decisions':32,'conflicts':0,'all_models_identical':True,'gate_recognition_active_but_no_overrides':True})
    report={'status':'PASS','synthetic_cases':len(cases),'synthetic_trials':sat+unsat,'sat_models_verified':sat,'unsat_drat_verified':unsat,
            'unsafe_modes_rejected':True,'default_fixed_tested':True,'real_sources':len(real),'real_trials':len(real)*3,'real':real,
            'frozen_reference_unchanged':T.sha('build/drnas-nl-solved')==frozen_before,
            'frozen_binary_sha256':frozen_before}
    assert report['frozen_reference_unchanged']
    T.save(out/'report.json',report);print('NL_FIXED_VALIDATION_PASS',json.dumps(report))
if __name__=='__main__':main()
