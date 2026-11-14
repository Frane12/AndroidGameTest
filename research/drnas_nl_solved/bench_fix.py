#!/usr/bin/env python3
"""Replay the AND-prior repair on the unchanged solved-only cohorts."""
import argparse,collections,gzip,json,os,platform,random,statistics,sys
from pathlib import Path
R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/'research/drnas_nl_solved'))
import bench as T
ARMS=('BASE','FIXED','KISSAT','CADICAL')
old_command=T.command
def command(s,arm,proof):
    if arm in ('KISSAT','CADICAL'):return old_command(s,arm,proof)
    cmd=[str(R/'build/drnas-nl-fixed'),str(R/s['path']),'--mode','core','--time','4.93','--stats',
         '--x5-no-minimize','--coop4','off','--coop5','off','--delta2','local','--proof',str(proof)]
    # Exercise the repaired default; BASE is the control in this same executable.
    if arm=='BASE':cmd+=['--nl-focus','base']
    return cmd
T.command=command
def main():
    p=argparse.ArgumentParser();p.add_argument('--reps',type=int,default=10);p.add_argument('--out',default='nl_fixed_results');a=p.parse_args()
    assert a.reps>1
    os.chdir(R);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    build=json.load(open('build/NL_FIXED_BUILD.json'))
    assert T.sha('build/drnas_nl_fixed.cpp')==build['source_sha256']
    assert T.sha('build/drnas-nl-fixed')==build['binary_sha256']
    assert T.sha('build/drnas-nl-solved')==build['frozen_binary_sha256']
    simon=json.load(open('research/drnas_nl_solved/cohort_summary.json'))['sources']
    src=[dict(s,name=s['filename'],stratum='simon',cohort_id=f"REAL36:{s['id']}") for s in simon]
    src+=json.load(open('research/drnas_nl_solved/medium_cohort.json'))['sources']
    assert len(src)==14 and len({s['id'] for s in src})==14
    cnfs={}
    for s in src:
        assert T.sha(s['path'])==s['sha256'];cnfs[s['id']]=T.B.parse_cnf(Path(s['path']).read_bytes())
    out=Path(a.out);raw=out/'raw';raw.mkdir(parents=True,exist_ok=False)
    protocol=dict(sources=src,arms=ARMS,reps=a.reps,cap_s=5,checker_cap_s=25,
        one_cpu=list(os.sched_getaffinity(0)),one_solver_process=True,build=build,
        binary_sha256={arm:T.sha('build/drnas-nl-fixed' if arm in ('BASE','FIXED') else f'cross/x59/build/{arm.lower()}') for arm in ARMS},
        time_definition='Process launch, parse, solve, proof/model emission; independent check separately',
        same_binary_native_control=True,retrospective=True,blind_holdout=False,
        nonlinear_AND_filter='Nine Simon originals only; five transfer controls are unfiltered',
        new_mathematical_pruning=False,platform=platform.platform())
    T.save(out/'protocol.json',protocol)
    def run(s,arm,rep):
        r=T.trial(s,arm,rep,raw,cnfs);r.update(name=s['name'],stratum=s['stratum'],cohort_id=s['cohort_id'])
        stem=raw/f"{s['id']}-{rep}-{arm}";proof=stem.with_suffix('.drat')
        if proof.exists():
            r['proof_sha256']=T.sha(proof)
            with gzip.open(str(proof)+'.gz','wb') as z:z.write(proof.read_bytes())
            proof.unlink()
        if r['status']=='SAT_VERIFIED':r['model_stdout_sha256']=T.sha(stem.with_suffix('.stdout'))
        return r
    warm=[]
    for s in src:
        for arm in ARMS:warm.append(run(s,arm,-1));T.save(out/'warmups.json',warm)
    print('NL_FIXED_WARMUPS',len(warm),sum(r['verified'] for r in warm),flush=True)
    rows=[]
    with (out/'trials.jsonl').open('w') as f:
        for rep in range(a.reps):
            order=list(src);random.Random(141527+rep).shuffle(order)
            for s in order:
                native=['BASE','FIXED'];refs=['KISSAT','CADICAL']
                if rep%2:native.reverse();refs.reverse()
                for arm in (native+refs if rep%2==0 else refs+native):
                    r=run(s,arm,rep);rows.append(r);f.write(json.dumps(r,sort_keys=True)+'\n');f.flush()
            print('NL_FIXED_REPEAT',rep+1,'/',a.reps,'verified',sum(r['verified'] for r in rows),'/',len(rows),flush=True)
    by={(r['id'],r['rep'],r['arm']):r for r in rows};checks=collections.Counter()
    for s in src:
        for rep in range(a.reps):
            x,y=(by[(s['id'],rep,arm)] for arm in ('BASE','FIXED'))
            if not(x['verified'] and y['verified']):continue
            assert x['status']==y['status'],'OUTCOME_DRIFT'
            for k in ('decisions','conflicts','propagations','learnt','restarts'):
                assert x['stats']['X41_STATS'][k]==y['stats']['X41_STATS'][k],('SEARCH_DRIFT',s['name'],rep,k)
            checks['identical_search_counter_pairs']+=1
            key='model_stdout_sha256' if x['status']=='SAT_VERIFIED' else 'proof_sha256'
            assert x[key]==y[key],('OUTPUT_DRIFT',s['name'],rep)
            checks['identical_sat_model_pairs' if key=='model_stdout_sha256' else 'identical_unsat_proof_pairs']+=1
    table=[]
    for s in src:
        entry=dict(id=s['id'],name=s['name'],stratum=s['stratum'],arms={})
        for arm in ARMS:
            rr=[r for r in rows if r['id']==s['id'] and r['arm']==arm]
            entry['arms'][arm]=dict(verified=sum(r['verified'] for r in rr),trials=len(rr),
                median_wall_s=statistics.median(r['wall_s'] for r in rr),
                median_wall_check_s=statistics.median(r.get('wall_plus_check_s',10) for r in rr),
                par2_s=sum(r['par2_s'] for r in rr))
        aa=entry['arms'];entry['fixed_gain_pct']=100*(1-aa['FIXED']['median_wall_s']/aa['BASE']['median_wall_s'])
        rng=random.Random(1414+s['id']);g=[]
        for _ in range(3000):
            reps=rng.choices(range(a.reps),k=a.reps)
            x=statistics.median(by[(s['id'],rep,'BASE')]['wall_s'] for rep in reps)
            y=statistics.median(by[(s['id'],rep,'FIXED')]['wall_s'] for rep in reps)
            g.append(100*(1-y/x))
        g.sort();entry['paired_repeat_bootstrap_ci95_pct']=[g[74],g[2924]];table.append(entry)
    totals={}
    for stratum in ('simon','medium','easy_control','all'):
        tt=[x for x in table if stratum=='all' or x['stratum']==stratum]
        med={arm:sum(x['arms'][arm]['median_wall_s'] for x in tt) for arm in ARMS}
        par={arm:sum(x['arms'][arm]['par2_s'] for x in tt) for arm in ARMS}
        check={arm:sum(x['arms'][arm]['median_wall_check_s'] for x in tt) for arm in ARMS}
        totals[stratum]=dict(sources=len(tt),sum_source_medians_s=med,sum_source_medians_with_check_s=check,par2_s=par,
            fixed_gain_pct=100*(1-med['FIXED']/med['BASE']))
    report=dict(status='COMPLETE',sources=len(src),reps=a.reps,attempts=len(rows),
        verified=sum(r['verified'] for r in rows),no_timeouts=all(r['verified'] for r in rows),
        statuses=dict(collections.Counter(r['status'] for r in rows)),native_pairs=dict(checks),
        table=table,totals=totals,warmups=len(warm),warmups_verified=sum(r['verified'] for r in warm),
        one_cpu=protocol['one_cpu'],binary_sha256=protocol['binary_sha256'],build=build,
        retrospective=True,blind_holdout=False,promotion=False,
        ci_scope='Timing noise within selected sources, not family generalization; only three medium originals',
        interpretation='Corrective removal of unsupported AND priority; generic in-place preparation retained. No new pruning.')
    T.save(out/'report.json',report)
    print('NL_FIXED_FINAL',json.dumps({k:report[k] for k in ('status','attempts','verified','statuses','native_pairs','totals')}),flush=True)
if __name__=='__main__':main()
