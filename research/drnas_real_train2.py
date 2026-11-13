#!/usr/bin/env python3
"""Verified curriculum and conservative family-balanced training. Frozen X5_NO_MIN baseline."""
from __future__ import annotations
import argparse, collections, json, math, os, random, select, signal, statistics, subprocess, tempfile, time
from pathlib import Path
import drnas_real_material2 as M
BASE='X5_NO_MIN'; ARMS=(BASE,'CORE','X5'); ROOT=Path(__file__).resolve().parents[1]

def choose(rule,features):
    if rule is None: return BASE
    if rule['kind']=='fixed': return rule['arm']
    hit=features[rule['feature']]<rule['threshold']
    return rule['arm'] if hit==rule['below'] else BASE

def witness(clauses,stdout,n):
    values={}
    for line in stdout.splitlines():
        if not line.startswith('v '): continue
        for token in line[2:].split():
            v=int(token)
            if not v: continue
            if abs(v)>n or (abs(v) in values and values[abs(v)]!=(v>0)): return False
            values[abs(v)]=v>0
    return all(any(values.get(abs(lit))==(lit>0) for lit in clause) for clause in clauses)

def execute(arm,cnf,clauses,n,cap,td,policy=None):
    """All runtime routing, solver parsing and independent checking are inside the cap."""
    start=time.monotonic(); effective=arm; overhead=0.0
    if arm in ('LEARNED','SHAM'):
        model=json.loads(Path(policy).read_text())
        with cnf.open('rb') as f: prefix=f.read(131072)
        feat=M.features(prefix)
        effective=choose(model['rule'],feat) if arm=='LEARNED' else BASE
        overhead=time.monotonic()-start
    proof=td/'proof'; proof.unlink(missing_ok=True)
    binaries={'CORE':'frozen-proof','X5_NO_MIN':'drnas-x5','X5':'drnas-x5',
              'Kissat':'kissat','CaDiCaL':'cadical','CMS':'cms'}
    binary=ROOT/'build'/binaries[effective]
    if effective in ARMS:
        cmd=[str(binary),str(cnf),'--mode','core','--stats','--time',str(cap),'--proof',str(proof)]
        if effective==BASE: cmd+=['--x5-no-minimize']
    elif effective=='CMS': cmd=[str(binary),'--threads=1','--verb=0','--frat='+str(proof),str(cnf)]
    else: cmd=[str(binary),str(cnf),str(proof)]
    status='TIMEOUT'; verified=False; code=None; rss=None; output=''; error=''; stats={}
    remaining=cap-(time.monotonic()-start)
    if remaining>0:
        with (td/'stdout').open('w+') as out,(td/'stderr').open('w+') as err:
            proc=subprocess.Popen(cmd,stdout=out,stderr=err,start_new_session=True)
            fd=os.pidfd_open(proc.pid)
            try:
                ready,_,_=select.select([fd],[],[],max(0.,cap-(time.monotonic()-start)))
                if not ready:
                    try: os.killpg(proc.pid,signal.SIGKILL)
                    except ProcessLookupError: pass
                _,wait_status,usage=os.wait4(proc.pid,0)
                code=os.waitstatus_to_exitcode(wait_status); proc.returncode=code; rss=usage.ru_maxrss
            finally: os.close(fd)
            out.seek(0);output=out.read();err.seek(0);error=err.read()
        if code in (0,10,20): status={0:'UNKNOWN',10:'SAT',20:'UNSAT'}[code]
        elif code!=-signal.SIGKILL: raise RuntimeError(f'{effective} failed {code}: {error[-1000:]}')
    solve=time.monotonic()-start; verify_started=time.monotonic()
    if status=='SAT':
        verified=witness(clauses,output,n)
        if not verified: raise AssertionError('INVALID SAT WITNESS '+effective)
    elif status=='UNSAT' and cap>solve:
        cmd=([str(ROOT/'build/frat-rs'),'elab',str(proof),str(cnf),'-v'] if effective=='CMS'
             else [str(ROOT/'build/drat-trim'),str(cnf),str(proof)])
        try:
            check=subprocess.run(cmd,capture_output=True,text=True,timeout=cap-solve)
            verified=(check.returncode==0 and 'VERIFIED' in check.stdout.splitlines()) if effective=='CMS' else (
                's VERIFIED' in check.stdout and (check.returncode==0 or 'c trivial UNSAT' in check.stdout))
            if not verified: raise AssertionError('INVALID/FAILED UNSAT PROOF '+effective+' '+check.stdout[-800:])
        except subprocess.TimeoutExpired: pass
    for line in error.splitlines():
        if line.startswith('X41_STATS '):
            try: stats=json.loads(line[10:])
            except json.JSONDecodeError: pass
    elapsed=time.monotonic()-start; accepted=bool(verified and elapsed<=cap)
    return {'arm':arm,'effective_arm':effective,'status':status,'verified':verified,'accepted':accepted,
        'cap_s':cap,'e2e_s':elapsed,'PAR2':elapsed if accepted else 2*cap,'solve_s':solve,
        'check_s':time.monotonic()-verify_started,'routing_s':overhead,'maxrss_kib':rss,
        'conflicts':stats.get('conflicts'),'propagations':stats.get('propagations')}

def manifest(args):
    data=json.loads((args.material/'manifest.json').read_text())
    if data['protocol']!=M.PROTOCOL: raise AssertionError('protocol mismatch')
    rows=data['sources']; seen=set(); groups={}
    for r in rows:
        if r['semantic_sha256'] in seen: raise AssertionError('semantic duplicate')
        seen.add(r['semantic_sha256'])
        if r['split']!=M.split_for(r['family']): raise AssertionError('split drift')
        groups.setdefault(r['family'],r['split'])
        if groups[r['family']]!=r['split']: raise AssertionError('family overlap')
    return data

def bench(args):
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    material=manifest(args); entries=sorted((s for s in material['sources'] if s['split']==args.stage),key=lambda s:s['sha256'])
    rescue={s['sha256'] for s in entries[:24]}
    entries=entries[args.shard::args.shards]; args.out.mkdir(parents=True,exist_ok=False)
    arms=ARMS if args.stage=='train' else (*ARMS,'LEARNED','SHAM')
    if args.stage=='holdout': arms=(*arms,'Kissat','CaDiCaL','CMS')
    meta={'protocol':M.PROTOCOL,'stage':args.stage,'shard':args.shard,'shards':args.shards,
        'sources':[s['sha256'] for s in entries],'arms':arms,'repeats':args.repeats,'cpus':1,
        'model_sha':M.sha(args.model.read_bytes()) if args.model else None,
        'material_sha':M.sha((args.material/'manifest.json').read_bytes()),
        'binary_sha':{k:M.sha((ROOT/'build'/k).read_bytes()) for k in ('frozen-proof','drnas-x5','drat-trim')}}
    M.save(args.out/'manifest.json',meta)
    completed=0; useful=0
    with tempfile.TemporaryDirectory() as tmp,(args.out/'trials.jsonl').open('w') as log,(args.out/'screen.jsonl').open('w') as screen:
        td=Path(tmp)
        for s in entries:
            cnf=args.material/s['file']; raw=cnf.read_bytes()
            if M.sha(raw)!=s['sha256']: raise AssertionError('source changed')
            n,m,clauses,identity=M.parse(raw)
            if identity!=s['semantic_sha256']: raise AssertionError('semantic drift')
            def measure(cap,rep):
                order=list(arms); random.Random(int(s['sha256'][:12],16)+rep).shuffle(order); rows=[]
                for arm in order:
                    row=execute(arm,cnf,clauses,n,cap,td,args.model)
                    row.update({k:s[k] for k in ('sha256','family','split','features','provenance')})
                    row['rep']=rep;rows.append(row)
                answers={r['status'] for r in rows if r['verified']}
                if len(answers)>1: raise AssertionError('contradictory certified answers')
                return rows
            if args.stage=='train':
                caps=(.5,3.,12.) if s['sha256'] in rescue else (.5,3.)
                for cap in caps:
                    first=measure(cap,0)
                    for row in first: screen.write(json.dumps(row,sort_keys=True)+'\n')
                    screen.flush()
                    if any(r['accepted'] for r in first): break
                repeats=args.repeats if any(r['accepted'] for r in first) else 1
            else: cap=args.cap; first=measure(cap,0); repeats=args.repeats
            rows=first[:]
            for rep in range(1,repeats): rows.extend(measure(cap,rep))
            for row in rows: log.write(json.dumps(row,sort_keys=True)+'\n')
            log.flush(); completed+=1; useful+=any(r['accepted'] for r in rows)
            M.emit('REAL1_M2_PROGRESS',{'stage':args.stage,'shard':args.shard,'completed':completed,
                'total':len(entries),'sources_with_verified_result':useful,'last_cap':cap})
    M.emit('REAL1_M2_SHARD_DONE',{'stage':args.stage,'sources':completed,'useful':useful})

def read_trials(root,material,stage):
    records=[]; metas=[]
    for p in sorted(root.rglob('manifest.json')):
        meta=json.loads(p.read_text())
        if meta.get('stage')!=stage: continue
        if meta['cpus']!=1 or meta['protocol']!=M.PROTOCOL: raise AssertionError('invalid run metadata')
        rows=[json.loads(x) for x in p.with_name('trials.jsonl').read_text().splitlines() if x]
        keys=[(r['sha256'],r['arm'],r['rep']) for r in rows]
        if len(keys)!=len(set(keys)): raise AssertionError('duplicate observations')
        if {r['sha256'] for r in rows}!=set(meta['sources']): raise AssertionError('missing sources')
        for source in meta['sources']:
            subset=[r for r in rows if r['sha256']==source]
            reps=meta['repeats'] if stage!='train' or any(r['accepted'] for r in subset) else 1
            expected={(source,a,k) for a in meta['arms'] for k in range(reps)}
            if set(k for k in keys if k[0]==source)!=expected: raise AssertionError('incomplete paired measurements')
            if len({r['cap_s'] for r in subset})!=1: raise AssertionError('unmatched limits')
            if len({r['status'] for r in subset if r['verified']})>1: raise AssertionError('certified contradiction')
        for r in rows:
            if r['split']!=stage or (r['accepted'] and not r['verified']): raise AssertionError('unverified credit/split leakage')
            if r['PAR2']!=(r['e2e_s'] if r['accepted'] else 2*r['cap_s']): raise AssertionError('incorrect PAR2')
        records.extend(rows);metas.append(meta)
    if not metas or sorted(m['shard'] for m in metas)!=list(range(metas[0]['shards'])): raise AssertionError('missing/duplicate shards')
    if any(m['material_sha']!=M.sha((material/'manifest.json').read_bytes()) for m in metas): raise AssertionError('material drift')
    if len({json.dumps(m['binary_sha'],sort_keys=True) for m in metas})!=1: raise AssertionError('binary drift')
    expected={r['sha256'] for r in json.loads((material/'manifest.json').read_text())['sources'] if r['split']==stage}
    actual=[s for m in metas for s in m['sources']]
    if len(actual)!=len(set(actual)) or set(actual)!=expected: raise AssertionError('whole cohort mismatch')
    return records,metas

def samples(rows):
    groups=collections.defaultdict(lambda:collections.defaultdict(list))
    for r in rows: groups[r['sha256']][r['arm']].append(r)
    result=[]; censored=stable=0
    for h,g in groups.items():
        if set(g)!=set(ARMS): raise AssertionError('training arms')
        if min(map(len,g.values()))<3: censored+=1;continue
        if not any(all(r['accepted'] for r in v) for v in g.values()): censored+=1;continue
        base=sorted(g[BASE],key=lambda r:r['rep']);costs={}; flags={}
        for arm in ARMS:
            rr=sorted(g[arm],key=lambda r:r['rep'])
            diffs=[b['PAR2']-r['PAR2'] for b,r in zip(base,rr)]
            gain=statistics.median(diffs);scale=max(.02,statistics.median(r['PAR2'] for r in base))
            consistent=max(sum(d>.003 for d in diffs),sum(d<-.003 for d in diffs))>=2
            flags[arm]=bool(consistent and abs(gain)>=max(.003,.10*scale))
            costs[arm]=max(-1.,min(1.,gain/scale)) if flags[arm] else 0.
        stable+=any(flags.values()); first=base[0]
        result.append({'sha':h,'family':first['family'],'features':first['features'],'gain':costs,
                       'actionable':any(flags.values()),'paired_complete':all(all(r['accepted'] for r in v) for v in g.values())})
    return result,{'informative_sources':len(result),'all_censored_or_unstable':censored,'actionable_sources':stable,
        'complete_three_arm_sources':sum(r['paired_complete'] for r in result),
        'families':len({r['family'] for r in result})}

def score(data,rule):
    families=collections.defaultdict(list)
    for d in data: families[d['family']].append(d['gain'][choose(rule,d['features'])])
    return statistics.mean(statistics.mean(v) for v in families.values()) if families else 0.

def fit_rule(data):
    if not data:return None,0.
    candidates=[{'kind':'fixed','arm':a} for a in ARMS[1:]]
    for feature in M.FEATURES:
        values=sorted(d['features'][feature] for d in data)
        for q in (.2,.4,.6,.8):
            threshold=values[min(len(values)-1,int(q*(len(values)-1)))]
            candidates.extend({'kind':'threshold','feature':feature,'threshold':threshold,'below':side,'arm':a}
                              for a in ARMS[1:] for side in (False,True))
    best=None; best_score=.01
    for rule in candidates:
        acted=[d for d in data if choose(rule,d['features'])!=BASE]
        if len(acted)<12 or len({d['family'] for d in acted})<3:continue
        gain=score(data,rule)
        if gain>best_score:best=rule;best_score=gain
    return best,best_score if best else 0.

def fit(args):
    rows,metas=read_trials(args.data,args.material,'train');data,quality=samples(rows)
    folds=[]
    for k in range(5):
        train=[d for d in data if int(M.sha(d['family'].encode())[:8],16)%5!=k]
        test=[d for d in data if int(M.sha(d['family'].encode())[:8],16)%5==k]
        rule,_=fit_rule(train);folds.append(score(test,rule))
    rule,gain=fit_rule(data);reasons=[]
    if quality['informative_sources']<60:reasons.append('fewer_than_60_repeated_informative_sources')
    if quality['actionable_sources']<15:reasons.append('fewer_than_15_stable_strategy_differences')
    if quality['families']<8:reasons.append('fewer_than_8_informative_families')
    if sum(x>0 for x in folds)<3 or statistics.mean(folds)<=0:reasons.append('family_cross_validation_not_positive')
    if rule is None:reasons.append('no_supported_rule')
    result={'protocol':M.PROTOCOL,'baseline':BASE,'rule':None if reasons else rule,'proposed_rule':rule,
        'quality':quality,'family_cv':folds,'train_score':gain,'reasons':reasons,'promoted':False,
        'scope':'global native-strategy routing only; local CDCL engines unchanged; no neural SAT prediction'}
    M.save(args.out,result);M.emit('REAL1_M2_TRAIN_RESULT',result)

def metrics(rows):
    result={}
    for arm in sorted({r['arm'] for r in rows}):
        rr=[r for r in rows if r['arm']==arm]
        result[arm]={'PAR2':sum(r['PAR2'] for r in rr),'verified':sum(r['accepted'] for r in rr),
            'SAT':sum(r['accepted'] and r['status']=='SAT' for r in rr),'UNSAT':sum(r['accepted'] and r['status']=='UNSAT' for r in rr),
            'trials':len(rr),'unique_solved':len({r['sha256'] for r in rr if r['accepted']})}
    return result

def interval(rows,control=BASE,draws=3000):
    families=collections.defaultdict(lambda:collections.defaultdict(float))
    for r in rows:
        if r['arm'] in ('LEARNED',control): families[r['family']][r['arm']]+=r['PAR2']
    units=list(families.values());rng=random.Random(131126);values=[]
    def reduction(selected):
        before=sum(u[control] for u in selected);after=sum(u['LEARNED'] for u in selected)
        return (before-after)/before if before else 0.
    for _ in range(draws):values.append(reduction([rng.choice(units) for u in units]))
    values.sort()
    return {'reduction':reduction(units),'lower95':values[int(.025*(draws-1))],
        'upper95':values[int(.975*(draws-1))],'family_units':len(units)}

def report(args):
    model=json.loads(args.model.read_text());rows,metas=read_trials(args.data,args.material,args.stage)
    if any(m['model_sha']!=M.sha(args.model.read_bytes()) for m in metas):raise AssertionError('model drift')
    totals=metrics(rows);ci=interval(rows);reasons=[]
    best_fixed=min(ARMS,key=lambda a:totals[a]['PAR2'])
    vs_best=interval(rows,best_fixed)
    if model['rule'] is None:reasons.append('training_abstained')
    if totals[BASE]['unique_solved']<8 or ci['family_units']<5:reasons.append('insufficient_evaluation_support')
    threshold=.03 if args.stage=='validation' else .10
    if ci['reduction']<threshold or ci['lower95']<=0:reasons.append('no_confident_net_improvement')
    if any(totals['LEARNED']['verified']<totals[a]['verified'] for a in ARMS):reasons.append('solved_regression')
    if vs_best['reduction']<=0 or vs_best['lower95']<=0:reasons.append('not_better_than_best_fixed_native')
    for f in {r['family'] for r in rows}:
        fm=metrics([r for r in rows if r['family']==f])
        if fm['LEARNED']['PAR2']>1.10*fm[BASE]['PAR2']:reasons.append('family_regression_over_10pct');break
    result={'protocol':M.PROTOCOL,'stage':args.stage,'totals':totals,'versus_baseline':ci,
            'accepted':not reasons,'reasons':reasons,'promoted':False,'model_sha':M.sha(args.model.read_bytes()),
            'best_fixed_native':best_fixed,'versus_best_fixed_native':vs_best,
            'sources':len({r['sha256'] for r in rows}),'scope':'retrospective size-bounded benchmark, not all industrial',
            'routing':dict(collections.Counter(r['effective_arm'] for r in rows if r['arm']=='LEARNED'))}
    M.save(args.out,result);M.emit('REAL1_M2_EVALUATION',result)
    if args.stage=='validation':
        model['validation']=result
        if reasons:model['rule']=None
        M.save(args.out.parent/'frozen_policy.json',model)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('command',choices=('bench','fit','report'))
    p.add_argument('--material',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--stage',choices=('train','validation','holdout'),default='train');p.add_argument('--data',type=Path)
    p.add_argument('--model',type=Path);p.add_argument('--shard',type=int,default=0);p.add_argument('--shards',type=int,default=4)
    p.add_argument('--cap',type=float,default=3.);p.add_argument('--repeats',type=int,default=3)
    a=p.parse_args()
    if not 0<=a.shard<a.shards or a.cap<=0 or a.repeats<1:p.error('invalid experiment limits')
    {'bench':bench,'fit':fit,'report':report}[a.command](a)
