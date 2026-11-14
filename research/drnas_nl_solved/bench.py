#!/usr/bin/env python3
"""Strict solved-only retrospective nonlinear cohort, source-verified SAT."""
import argparse, collections, hashlib, itertools, json, os, platform, random
import statistics, subprocess, sys, time
from pathlib import Path
R=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(R/'research'))
import drnas_x55_cpu_real36 as B
ARMS=('BASE','INPLACE','DELTA4X','KISSAT','CADICAL')
MODES={'BASE':'base','INPLACE':'inplace','NL_INPUT':'inputs','COMBINED':'both','DELTA4X':'base'}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2,sort_keys=True)+'\n')
def events(s,tag):
    return [json.loads(l.split(' ',1)[1]) for l in s.splitlines() if l.startswith(tag+' ')]
def gates(cs):
    original={tuple(sorted(set(c))) for c in cs}
    bins={c for c in original if len(c)==2}
    out=[]
    for c in sorted(original):
        if len(c)!=3 or len({abs(l) for l in c})!=3:continue
        for z in c:
            a,b=[-l for l in c if l!=z]
            p=tuple(sorted([-z,a]));q=tuple(sorted([-z,b]))
            if p in bins and q in bins:
                # Exhaustive local truth table equals z=a*b for signed literals.
                vs=sorted(map(abs,c));models=[]
                for bits in itertools.product((False,True),repeat=3):
                    v=dict(zip(vs,bits));ev=lambda l:v[abs(l)]==(l>0)
                    sat=all(any(ev(l) for l in cl) for cl in (c,p,q))
                    assert sat==(ev(z)==(ev(a) and ev(b)))
                    if sat:models.append([int(v[abs(l)]) for l in (a,b,z)])
                # The signed relation has degree 2; no global irreducibility claim.
                out.append({'z':z,'a':a,'b':b,'parents':[list(c),list(p),list(q)]})
    return out
def command(s,arm,proof):
    if arm in ('KISSAT','CADICAL'):
        return [str(R/f'cross/x59/build/{arm.lower()}')]+(['-q','--no-binary'] if arm=='CADICAL' else [])+[str(R/s['path']),str(proof)]
    return [str(R/'build/drnas-nl-solved'),str(R/s['path']),'--mode','core','--time','4.93','--stats',
            '--x5-no-minimize','--coop4','gate' if arm=='DELTA4X' else 'off','--coop5','off',
            '--delta2','d4x' if arm=='DELTA4X' else 'local','--nl-focus',MODES[arm],'--proof',str(proof)]
def trial(s,arm,rep,folder,cnfs):
    stem=f"{s['id']}-{rep}-{arm}";proof=folder/(stem+'.drat')
    t=time.perf_counter()
    try:
        p=subprocess.run(command(s,arm,proof),capture_output=True,text=True,timeout=5.1)
        wall=time.perf_counter()-t
    except subprocess.TimeoutExpired:
        return dict(id=s['id'],sha256=s['sha256'],arm=arm,rep=rep,verified=False,status='TIMEOUT',wall_s=5.1,par2_s=10.0)
    n,cs=cnfs[s['id']];check=time.perf_counter();status='UNKNOWN'
    if p.returncode==10:
        assert B.check_sat(p.stdout,cs,n),('BAD_ORIGINAL_MODEL',stem);status='SAT_VERIFIED'
    elif p.returncode==20:
        q=subprocess.run([str(R/'build/drat-trim'),str(R/s['path']),str(proof)],capture_output=True,text=True,timeout=25)
        assert q.returncode>=0 and 's VERIFIED' in q.stdout,('BAD_ORIGINAL_PROOF',stem)
        status='UNSAT_CERTIFIED'
    else:assert p.returncode==0,(stem,p.returncode,p.stderr[-2000:])
    verified=status in ('SAT_VERIFIED','UNSAT_CERTIFIED') and wall<=5
    check=time.perf_counter()-check
    (folder/(stem+'.stderr')).write_text(p.stderr)
    # Keep all models so the original CNF verification is reproducible.
    (folder/(stem+'.stdout')).write_text(p.stdout)
    if status!='UNSAT_CERTIFIED':proof.unlink(missing_ok=True)
    stats={tag:events(p.stderr,tag)[0] for tag in ('NL_FOCUS','X41_STATS','DELTA4X_STATS') if events(p.stderr,tag)}
    return dict(id=s['id'],sha256=s['sha256'],arm=arm,rep=rep,verified=verified,status=status,
                wall_s=wall,check_s=check,wall_plus_check_s=wall+check,par2_s=wall if verified else 10.0,stats=stats)
def main():
    p=argparse.ArgumentParser();p.add_argument('--history',required=True);p.add_argument('--reps',type=int,default=15);p.add_argument('--out',default='nl_solved_results');a=p.parse_args()
    os.chdir(R);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    manifest=json.load(open('real36_frozen/manifest.json'));old=json.load(open(a.history));selected=[];cnfs={};certs=[];excluded=[]
    for s in manifest:
        history=[r for r in old if r['sha256']==s['sha256'] and r['arm']=='OFF']
        if len(history)!=2 or not all(r['verified'] and r['status'] in ('SAT_VERIFIED','UNSAT_CERTIFIED') for r in history):
            excluded.append({'id':s['id'],'reason':'baseline not verified in both historical repetitions'});continue
        assert sha(s['path'])==s['sha256']
        n,cs=B.parse_cnf(Path(s['path']).read_bytes());gg=gates(cs)
        if not gg:excluded.append({'id':s['id'],'reason':'no complete nonlinear AND gate certificate'});continue
        selected.append(s);cnfs[s['id']]=(n,cs)
        certs.append(dict(id=s['id'],sha256=s['sha256'],gates=len(gg),all_gate_certificates=gg,prior_trials=history))
    assert [s['id'] for s in selected]==[2,8,14,18,22,26,29,32,35], 'COHORT_DRIFT'
    root=Path(a.out);raw=root/'raw';raw.mkdir(parents=True,exist_ok=False)
    save(root/'cohort.json',dict(sources=selected,certificates=certs,excluded=excluded,history_run=43587320318,
         selection='OFF verified twice below 5s AND complete signed AND gates',retrospective=True,blind_holdout=False))
    print('NL_COHORT',json.dumps({'count':len(selected),'gates':[x['gates'] for x in certs]}),flush=True)
    # One unscored, model-checked warmup for each source/arm.
    warmups=[]
    for s in selected:
        for arm in ARMS:
            row=trial(s,arm,-1,raw,cnfs);warmups.append(row)
            save(root/'warmups.json',warmups)
            assert row['verified'],('WARMUP_NOT_SOLVED',s['id'],arm)
    rows=[]
    with (root/'trials.jsonl').open('w') as f:
        for rep in range(a.reps):
            order=[(s,arm) for s in selected for arm in ARMS];random.Random(141126+rep).shuffle(order)
            for s,arm in order:
                r=trial(s,arm,rep,raw,cnfs);rows.append(r);f.write(json.dumps(r,sort_keys=True)+'\n');f.flush()
            print('NL_REPEAT',rep+1,'/',a.reps,flush=True)
    summary={};base_medians={}
    for arm in ARMS:
        rr=[r for r in rows if r['arm']==arm];med={str(s['id']):statistics.median(r['wall_s'] for r in rr if r['id']==s['id']) for s in selected}
        summary[arm]={'trials':len(rr),'verified':sum(r['verified'] for r in rr),'median_wall_by_source_s':med,
          'sum_source_medians_s':sum(med.values()),'par2_s':sum(r['par2_s'] for r in rr),
          'median_check_s':statistics.median(r.get('check_s',0) for r in rr),
          'median_parse_s':statistics.median(r['stats']['NL_FOCUS']['parse_s'] for r in rr if 'NL_FOCUS' in r.get('stats',{})) if arm in MODES else None,
          'median_search_s':statistics.median(r['stats']['NL_FOCUS']['search_s'] for r in rr if 'NL_FOCUS' in r.get('stats',{})) if arm in MODES else None,
          'decisions':sorted(set(r.get('stats',{}).get('X41_STATS',{}).get('decisions') for r in rr),key=str),
          'conflicts':sorted(set(r.get('stats',{}).get('X41_STATS',{}).get('conflicts') for r in rr),key=str)}
        if arm=='BASE':base_medians=med
        summary[arm]['gain_pct_vs_BASE']=100*(1-sum(med.values())/sum(base_medians.values()))
    # Confirm normalization preserves the complete deterministic search counters.
    by={(r['id'],r['rep'],r['arm']):r for r in rows}
    for s in selected:
        for rep in range(a.reps):
            x,y=(by[(s['id'],rep,arm)] for arm in ('BASE','INPLACE'))
            assert x['verified'] and y['verified'] and x['status']==y['status']
            for k in ('decisions','conflicts','propagations','learnt','restarts'):
                assert x['stats']['X41_STATS'][k]==y['stats']['X41_STATS'][k],('SEARCH_DRIFT',s['id'],k)
    report=dict(status='COMPLETE',sources=len(selected),repeats=a.reps,attempts=len(rows),arms=summary,
         no_timeouts=all(r['verified'] for r in rows),one_logical_cpu=list(os.sched_getaffinity(0)),
         binary_sha256={x:sha('build/drnas-nl-solved' if x in MODES else f'cross/x59/build/{x.lower()}') for x in ARMS},
         platform=platform.platform(),retrospective=True,blind_holdout=False,promotion=False,
         independent_families=1,nonlinear_relation='signed z=a*b over GF(2); local exact encoding, not global irreducibility',
         time_definition='subprocess launch, parse, recognition, solving, proof emission and model output; independent check separately',
         inplace_identical_search_counters=True)
    save(root/'report.json',report);print('NL_FINAL',json.dumps(report,sort_keys=True),flush=True)
if __name__=='__main__':main()
