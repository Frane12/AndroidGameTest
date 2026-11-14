#!/usr/bin/env python3
"""Test the frozen preparation change on previously native-solved real CNFs."""
import argparse,gzip,json,os,random,statistics,sys
from pathlib import Path
R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/'research/drnas_nl_solved'))
import bench as T
ARMS=('BASE','INPLACE','KISSAT','CADICAL')
def main():
    p=argparse.ArgumentParser();p.add_argument('--reps',type=int,default=10);p.add_argument('--out',default='medium_results')
    p.add_argument('--expected-binary-sha',default='7c11ef877f18fea0e6f84e2445aa1bb4cc295245dcabfd81477b7528fc3cd81a');a=p.parse_args()
    os.chdir(R);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    assert T.sha('build/drnas-nl-solved')==a.expected_binary_sha,'FROZEN_TESTED_BINARY_DRIFT'
    assert T.sha('build/drnas_nl_solved.cpp')=='b1b6bc8ddd870f4d0c7dd78ffeec0009df4d3459596980d4e948424aa9a273cb','FROZEN_SOURCE_DRIFT'
    protocol=json.load(open('research/drnas_nl_solved/medium_cohort.json'));src=protocol['sources'];cnfs={}
    for s in src:
        assert T.sha(s['path'])==s['sha256'];assert len(s['historical_trials'])==2
        assert all(r['verified'] for r in s['historical_trials'])
        cnfs[s['id']]=T.B.parse_cnf(Path(s['path']).read_bytes())
    assert len({s['id'] for s in src})==len(src),'LOCAL_ID_COLLISION'
    out=Path(a.out);raw=out/'raw';raw.mkdir(parents=True,exist_ok=False)
    protocol.update(arms=ARMS,reps=a.reps,cap_s=5,checker_cap_s=25,one_cpu=list(os.sched_getaffinity(0)),
        time_definition='Solver process launch, parsing, solving, proof/model output; independent checking separately',
        retrospective=True,blind_holdout=False,nonlinear_AND_filter=False,
        purpose='Transfer of generic clause-preparation optimization beyond Simon, no new branching policy',
        binary_sha256={arm:T.sha('build/drnas-nl-solved' if arm in ('BASE','INPLACE') else f'cross/x59/build/{arm.lower()}') for arm in ARMS})
    T.save(out/'protocol.json',protocol)
    rows=[]
    def run(s,arm,rep):
        r=T.trial(s,arm,rep,raw,cnfs);r.update(name=s['name'],cohort_id=s['cohort_id'],stratum=s['stratum'])
        proof=raw/f"{s['id']}-{rep}-{arm}.drat"
        if proof.exists():
            r['proof_sha256']=T.sha(proof)
            with gzip.open(str(proof)+'.gz','wb') as z:z.write(proof.read_bytes())
            proof.unlink()
        print('MEDIUM_TRIAL',json.dumps({k:r[k] for k in ('cohort_id','arm','rep','status','verified','wall_s')}),flush=True)
        return r
    warm=[]
    for s in src:
        for arm in ARMS:
            r=run(s,arm,-1);warm.append(r);T.save(out/'warmups.json',warm)
            # Retain a newly observed regression; never silently drop a source.
    with (out/'trials.jsonl').open('w') as f:
        for rep in range(a.reps):
            order=list(src);random.Random(141414+rep).shuffle(order)
            for s in order:
                native=['BASE','INPLACE'];refs=['KISSAT','CADICAL']
                if rep%2:native.reverse();refs.reverse()
                order_arms=native+refs if rep%2==0 else refs+native
                for arm in order_arms:
                    r=run(s,arm,rep);rows.append(r);f.write(json.dumps(r,sort_keys=True)+'\n');f.flush()
            print('MEDIUM_REPEAT',rep+1,'/',a.reps,flush=True)
    by={(r['id'],r['rep'],r['arm']):r for r in rows};checks=[]
    for s in src:
        for rep in range(a.reps):
            x,y=(by[(s['id'],rep,arm)] for arm in ('BASE','INPLACE'))
            if not(x['verified'] and y['verified']):continue
            assert x['status']==y['status'],'OUTCOME_DRIFT'
            keys=('decisions','conflicts','propagations','learnt','restarts')
            identical=all(x['stats']['X41_STATS'][k]==y['stats']['X41_STATS'][k] for k in keys)
            assert identical,('SEARCH_DRIFT',s['name'],rep)
            checks.append((s['id'],rep))
    table=[]
    for s in src:
        entry={'id':s['id'],'name':s['name'],'stratum':s['stratum'],'arms':{}}
        for arm in ARMS:
            rr=[r for r in rows if r['id']==s['id'] and r['arm']==arm]
            entry['arms'][arm]={'verified':sum(r['verified'] for r in rr),'trials':len(rr),
                'median_wall_s':statistics.median(r['wall_s'] for r in rr),
                'median_wall_check_s':statistics.median(r.get('wall_plus_check_s',10) for r in rr),
                'par2_s':sum(r['par2_s'] for r in rr),
                'median_parse_s':statistics.median(r['stats']['NL_FOCUS']['parse_s'] for r in rr if 'NL_FOCUS' in r.get('stats',{})) if arm in ('BASE','INPLACE') else None,
                'median_search_s':statistics.median(r['stats']['NL_FOCUS']['search_s'] for r in rr if 'NL_FOCUS' in r.get('stats',{})) if arm in ('BASE','INPLACE') else None}
        aa=entry['arms'];entry['inplace_gain_pct']=100*(1-aa['INPLACE']['median_wall_s']/aa['BASE']['median_wall_s'])
        rng=random.Random(114+s['id']);g=[]
        for _ in range(3000):
            reps=rng.choices(range(a.reps),k=a.reps)
            x=statistics.median(by[(s['id'],rep,'BASE')]['wall_s'] for rep in reps)
            y=statistics.median(by[(s['id'],rep,'INPLACE')]['wall_s'] for rep in reps)
            g.append(100*(1-y/x))
        g.sort();entry['paired_repeat_bootstrap_ci95_pct']=[g[74],g[2924]]
        table.append(entry)
    totals={}
    for stratum in ('medium','easy_control','all'):
        tt=[x for x in table if stratum=='all' or x['stratum']==stratum]
        v={arm:sum(x['arms'][arm]['median_wall_s'] for x in tt) for arm in ARMS}
        totals[stratum]={'sources':len(tt),'sum_source_medians_s':v,'inplace_gain_pct':100*(1-v['INPLACE']/v['BASE'])}
    report={'status':'COMPLETE','sources':len(src),'reps':a.reps,'attempts':len(rows),
        'verified':sum(r['verified'] for r in rows),'no_timeouts':all(r['verified'] for r in rows),
        'sat_verified':sum(r['status']=='SAT_VERIFIED' for r in rows),
        'unsat_certified':sum(r['status']=='UNSAT_CERTIFIED' for r in rows),
        'identical_native_search_pairs':len(checks),'table':table,'totals':totals,
        'warmups':len(warm),'warmups_verified':sum(r['verified'] for r in warm),
        'one_cpu':protocol['one_cpu'],'binary_sha256':protocol['binary_sha256'],
        'retrospective':True,'blind_holdout':False,'promotion':False,
        'ci_scope':'Timing noise conditional on the selected CNFs; only three medium instances, not a generalization claim'}
    T.save(out/'report.json',report);print('MEDIUM_FINAL',json.dumps(report),flush=True)
if __name__=='__main__':main()
