#!/usr/bin/env python3
"""GATE-R2: six-arm frozen 30-profile test. No persistent cross-CNF memory.
Uses the exact X4.6 generator and validators, but NEW seed namespace.
Primary hypothesis: hysteretic scheduling improves on unchanged X4.6 GATE.
"""
from __future__ import annotations
import argparse, collections, hashlib, itertools, json, math, os, random
import subprocess, tempfile, time
from pathlib import Path
import x46_categories as C
import x46_gate30 as B

C.NAMESPACE='gate-r2-relay30-prospective-20261113-v1'
CAP=2.0
REPEATS=3
EACH=20
SHARDS=12
ARMS={
    'CORE':('build/drnas-x41','core'),
    'ADAPTIVE':('build/drnas-x3','x3'),
    'X45_ONLINE':('build/drnas-x45','x45_online'),
    'X46_GATE':('build/drnas-x46','x46_gate'),
    'R2_FIXED':('build/drnas-gate-r2','gate_r2_fixed'),
    'GATE_R2':('build/drnas-gate-r2','gate_r2'),
}
B.ARMS=ARMS
CODE=(
    'research/gate_r2_trial.py','research/build_gate_r2.py','src/drnas_gate_r2.hpp',
    'research/build_x46_gate30.py','research/x46_categories.py','research/x46_gate30.py',
    'src/drnas_x41.cpp','src/drnas_x3.cpp','src/drnas_x45.cpp','tests/test_gate_r2.cpp',
    'README_GATE_R2.md','.github/workflows/drnas-gate-r2-relay30.yml',
)
GATE_FIELDS=('calls','skipped_schedule','skipped_cost','skipped_timeout','permits',
 'rounds','proxy_good','proxy_bad','observations','state_switches','active_entries',
 'sleep_entries','check_entries','periodic_wakes','shock_wakes','decay_events',
 'throttles','accelerations','shock_checks')

def emit(tag,data):B.emit(tag,data)
def dump(p,data):B.dump(p,data)

def run_one(src,arm,parsed,cap=CAP):
    binary,mode=ARMS[arm];start=time.perf_counter();p=None
    try:p=subprocess.run([binary,src['path'],'--mode',mode,'--time',str(cap),'--stats'],
        capture_output=True,text=True,timeout=cap+0.75)
    except subprocess.TimeoutExpired:pass
    proc=time.perf_counter()-start;sat=False;stats={};gate={}
    if p is not None:
        if p.returncode not in (0,10,20):raise RuntimeError((arm,p.returncode,p.stderr[-1000:]))
        if p.returncode==20:raise RuntimeError('Native UNSAT contradicts generated SAT')
        if p.returncode==10:
            if not B.verify(p.stdout,*parsed):raise RuntimeError('Invalid SAT witness')
            sat=True
        for line in p.stderr.splitlines():
            if line.startswith(('X41_STATS ','X3_STATS ','X45_STATS ','X46_STATS ','GATER2_STATS ')):
                stats=json.loads(line.split(' ',1)[1])
            elif line.startswith(('X46_GATE ','GATER2_GATE ')):
                gate=json.loads(line.split(' ',1)[1])
        if not stats or (arm in ('X46_GATE','R2_FIXED','GATE_R2') and not gate):
            raise RuntimeError('Missing solver/controller telemetry: '+arm)
    elapsed=time.perf_counter()-start;solved=sat and elapsed<=cap
    return {'status':'SAT_VERIFIED' if solved else 'UNKNOWN',
        'e2e_s':round(elapsed,7),'process_s':round(proc,7),
        'verify_and_parse_s':round(elapsed-proc,7),'late_verified':sat and not solved,
        'PAR2_s':round(elapsed if solved else 2*cap,7),
        'decisions':stats.get('decisions',0),'conflicts':stats.get('conflicts',0),
        'probe_seconds':stats.get('probe_seconds',0.),
        'counterfactuals':stats.get('x45_counterfactuals',0),
        'updates':stats.get('x45_online_updates',0),
        'interventions':stats.get('x45_interventions',0),'gate':gate}

def summarize(rows):
    report=B.summarize(rows)
    for arm in ARMS:
        gs=[r['arms'][arm]['gate'] for r in rows]
        report[arm]['gate_totals']={f:sum(g.get(f,0) for g in gs) for f in GATE_FIELDS}
        report[arm]['max_budget_overshoot_s']=max((g.get('max_budget_overshoot_s',0.) for g in gs),default=0.)
        report[arm]['solves_without_probes']=sum(r['arms'][arm]['counterfactuals']==0 for r in rows)
    return report

def comparison(rows,base,iterations=2000):
    # A whole formula (all 3 repeats) is a bootstrap unit, stratified by category.
    grouped=collections.defaultdict(list);meta={}
    for r in rows:
        grouped[r['sha256']].append(r['arms']['GATE_R2']['PAR2_s']-r['arms'][base]['PAR2_s'])
        meta[r['sha256']]=(r['category'],r['domain'])
    cats=collections.defaultdict(list);domains=collections.defaultdict(float)
    for sha,values in grouped.items():
        category,domain=meta[sha];delta=sum(values)
        cats[category].append(delta);domains[domain]+=delta
    rng=random.Random(462602);boot=[];cb=[];db=[]
    ct=[sum(v) for _,v in sorted(cats.items())];dt=list(domains.values())
    for _ in range(iterations):
        boot.append(sum(sum(rng.choice(v) for _ in v) for v in cats.values()))
        cb.append(sum(rng.choice(ct) for _ in ct))
        db.append(sum(rng.choice(dt) for _ in dt))
    def interval(values):
        values.sort();return [round(values[int(.025*iterations)],7),round(values[int(.975*iterations)],7)]
    return {'baseline':base,'delta_PAR2_s':round(sum(ct),7),
        'formula_clustered_stratified_95':interval(boot),
        'category_clustered_95':interval(cb),'domain_clustered_95':interval(db),
        'formula_units':len(grouped),'category_units':len(cats),'domain_units':len(domains),
        'repeats_not_independent':True}

def freeze(prior_dir):
    sources,text,sha=C.make_manifest('gate_r2_generated',EACH)
    history=set();files=[]
    if prior_dir:
        files=sorted(set(Path(prior_dir).rglob('manifest.json'))|set(Path(prior_dir).rglob('frozen_manifest.json')))
        if not files:raise RuntimeError('No prior frozen manifest')
        for file in files:
            data=json.loads(file.read_text())
            if not isinstance(data,list):raise RuntimeError('Bad history manifest')
            history.update(r['sha256'] for r in data)
        if history&{r['sha256'] for r in sources}:raise RuntimeError('Historical SHA overlap')
    dest=Path('gate_r2_frozen');dest.mkdir(exist_ok=True);(dest/'manifest.json').write_text(text)
    p={'manifest_sha256':sha,'namespace':C.NAMESPACE,'sources':600,'categories':30,
       'each':EACH,'repeats':REPEATS,'cap_s':CAP,'shards':SHARDS,'arms':list(ARMS),
       'expected_solver_runs':600*REPEATS*len(ARMS),'historical_sha_checked':len(history),
       'history_manifests':len(files),'generated_sat_only':True,
       'primary':'GATE_R2 vs X46_GATE',
       'primary_success_rule':'PAR2 at least 5% lower; no loss of solved trials or stable 3/3 sources; formula-clustered upper CI below zero',
       'no_outcome_based_filtering':True,'no_cross_formula_memory':True,
       'constants':{'enable_proxy_ewma':.65,'disable_proxy_ewma':.35,'min_outcomes':4,
                    'initial_decisions':64,'check_stride':128,'active_stride':96,
                    'sleep_stride_max':4096,'fixed_stride':192,
                    'budget_base_s':.0005,'budget_fraction_nonprobe':.02,'cost_reserve_factor':1.25},
       'limits':'Proxy usefulness and predicted probe cost, NOT causal seconds saved. WATCH ORDER IS NOT RESTORED. No industrial or large-UNSAT claim.',
       'code_sha256':{path:hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in CODE}}
    dump(dest/'protocol.json',p);emit('GATER2_FROZEN',p)

def manifest():
    raw=Path('gate_r2_frozen/manifest.json').read_bytes()
    p=json.loads(Path('gate_r2_frozen/protocol.json').read_text())
    if hashlib.sha256(raw).hexdigest()!=p['manifest_sha256']:raise RuntimeError('Manifest changed')
    if (p['arms'],p['namespace'],p['repeats'],p['cap_s'])!=(list(ARMS),C.NAMESPACE,REPEATS,CAP):
        raise RuntimeError('Protocol drift')
    for path,sha in p['code_sha256'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:raise RuntimeError('Code drift: '+path)
    return json.loads(raw),p

def shard(number):
    frozen,p=manifest();dest=Path('gate_r2_stage');dest.mkdir(exist_ok=True)
    selected=[r for r in frozen if r['id']%SHARDS==number];rows=[];counts=collections.Counter()
    with (dest/'trials.jsonl').open('w') as out:
        for ix,meta in enumerate(selected):
            src=C.generate(meta['category'],meta['replicate_id'],'gate_r2_generated')
            if src['sha256']!=meta['sha256']:raise RuntimeError('Input changed')
            parsed=B.problem(src['path'])
            for rep in range(REPEATS):
                # Balanced Latin rotations per runner, not id%6 (shard stride is 12).
                order=list(ARMS);rot=(ix*REPEATS+rep)%len(order);order=order[rot:]+order[:rot]
                arms={arm:run_one(src,arm,parsed) for arm in order}
                row={k:meta[k] for k in ('id','sha256','category','domain')}
                row.update(repeat=rep,shard=number,order=order,arms=arms)
                out.write(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n');out.flush();rows.append(row)
                for arm,r in arms.items():
                    counts[arm+'_solved']+=r['status']=='SAT_VERIFIED';counts[arm+'_PAR2_s']+=r['PAR2_s']
            if (ix+1)%10==0:emit('GATER2_PROGRESS',{'shard':number,'sources_done':ix+1,'total':len(selected),**counts})
    report={'shard':number,'sources':len(selected),'paired_rows':len(rows),
            'manifest_sha256':p['manifest_sha256'],'arms':summarize(rows)}
    dump(dest/'report.json',report);emit('GATER2_SHARD_FINAL',report)

def finish():
    frozen,p=manifest();rows=[]
    for number in range(SHARDS):
        folder=Path('gate_r2_downloads')/f'gate-r2-relay30-{number}'
        r=json.loads((folder/'report.json').read_text())
        if r['manifest_sha256']!=p['manifest_sha256'] or r['shard']!=number:raise RuntimeError('Shard mismatch')
        part=[json.loads(x) for x in (folder/'trials.jsonl').read_text().splitlines()]
        if any(row['shard']!=number for row in part):raise RuntimeError('Misfiled trial')
        rows.extend(part)
    B.validate(rows,frozen);rows.sort(key=lambda r:(r['id'],r['repeat']))
    # Additional native scheduling invariants; retain raw per-run telemetry.
    for r in rows:
        for arm in ('R2_FIXED','GATE_R2'):
            x=r['arms'][arm];g=x['gate']
            if not g:continue # process killed by outer deadline; UNKNOWN remains penalized
            if g['proxy_good']+g['proxy_bad']!=g['observations']:raise RuntimeError('Feedback counts')
            if g['observations']!=x['updates']:raise RuntimeError('Missing online feedback')
            if g['rounds']>g['permits'] or g['observations']>g['rounds']:raise RuntimeError('Probe accounting')
            if arm=='R2_FIXED' and g['state_switches']!=0:raise RuntimeError('Fixed-control contamination')
    overall=summarize(rows)
    cats={category:summarize([r for r in rows if r['category']==category]) for category,_ in C.SPECS}
    if len(cats)!=30 or any(x['CORE']['sources']!=20 for x in cats.values()):raise RuntimeError('Missing category')
    comparisons={arm:comparison(rows,arm) for arm in ARMS if arm!='GATE_R2'}
    new=overall['GATE_R2'];old=overall['X46_GATE'];ci=comparisons['X46_GATE']['formula_clustered_stratified_95']
    success=(new['PAR2_s']<=.95*old['PAR2_s'] and new['SAT_verified']>=old['SAT_verified']
        and new['stable_solved_sources']>=old['stable_solved_sources'] and ci[1]<0)
    if new['gate_totals']['observations']<=0:raise RuntimeError('Gate not exercised')
    report={'status':'COMPLETE','protocol':p,'overall':overall,'categories':cats,
        'domains':{domain:summarize([r for r in rows if r['domain']==domain]) for domain in sorted({d for _,d in C.SPECS})},
        'shards':{str(i):summarize([r for r in rows if r['shard']==i]) for i in range(SHARDS)},
        'comparisons':comparisons,'primary_success_rule_pass':success,
        'limits':p['limits']+' Fresh instances of known generator profiles, not unseen industrial families. Three repeats are clustered by input.'}
    dest=Path('gate_r2_final');dest.mkdir(exist_ok=True);dump(dest/'report.json',report)
    (dest/'paired_trials.jsonl').write_text(''.join(json.dumps(r,sort_keys=True,separators=(',',':'))+'\n' for r in rows))
    lines=['## GATE-R2 relay30 — 600 generated SAT formulas, 3 repeats, 6 arms','',
      '| Arm | Verified SAT /1800 | Stable /600 | PAR2 s | E2E s | Probe s |','|---|---:|---:|---:|---:|---:|']
    for arm,x in overall.items():lines.append(f"| {arm} | {x['SAT_verified']} | {x['stable_solved_sources']} | {x['PAR2_s']:.4f} | {x['e2e_s']:.4f} | {x['probe_seconds']:.4f} |")
    lines+=['','| Category | CORE | ADAPTIVE | X45 | X46 GATE | R2 FIXED | GATE R2 |','|---|---:|---:|---:|---:|---:|---:|']
    for category,_ in C.SPECS:lines.append('| '+category+' | '+' | '.join(f"{cats[category][arm]['PAR2_s']:.3f}" for arm in ARMS)+' |')
    lines+=['',f'Primary preregistered success: **{success}**. Negative delta favors R2.']
    for arm,c in comparisons.items():lines.append(f"- vs {arm}: delta {c['delta_PAR2_s']:.4f}s; formula-clustered 95% {c['formula_clustered_stratified_95']}; category 95% {c['category_clustered_95']}; domain 95% {c['domain_clustered_95']}.")
    lines+=['',report['limits']];text='\n'.join(lines)+'\n';(dest/'summary.md').write_text(text)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:f.write(text)
    emit('GATER2_FINAL',{'status':'COMPLETE','sources':600,'categories':30,'solver_runs':10800,
        'overall':overall,'comparisons':comparisons,'primary_success_rule_pass':success})

def selftest():
    subprocess.run(['build/test-gate-r2'],check=True)
    with tempfile.TemporaryDirectory() as tmp:
        old=C.NAMESPACE;C.NAMESPACE=old+'-smoke-only'
        try:
            sources,text,sha=C.make_manifest(tmp,2)
            _,text2,sha2=C.make_manifest(tmp,2)
            assert sha==sha2 and text==text2 and len(sources)==60
            for r in sources:
                n,cs=B.problem(r['path']);assert n==r['nvars'] and len(cs)==r['nclauses']
            rng=random.Random(462602);checks=sat_count=unsat_count=0
            for i in range(100):
                n=6;cs=[]
                for _ in range(16+i%16):
                    vs=rng.sample(range(1,n+1),2+i%2);cs.append([v if rng.getrandbits(1) else -v for v in vs])
                truth=any(all(any(bits[abs(v)-1]==(v>0) for v in c) for c in cs) for bits in itertools.product((False,True),repeat=n))
                sat_count+=truth;unsat_count+=not truth
                # Independent satisfiable components force >64 decisions in SAT cases;
                # truth of the full CNF is exactly the exhaustively checked 6-var core.
                if i<12:
                    for pair in range(100):cs.append([7+2*pair,8+2*pair])
                    n=206
                path=Path(tmp)/'oracle.cnf';path.write_text(f'p cnf {n} {len(cs)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in cs))
                for arm,(exe,mode) in ARMS.items():
                    cp=subprocess.run([exe,str(path),'--mode',mode,'--time','1','--stats'],capture_output=True,text=True,timeout=3)
                    assert cp.returncode==(10 if truth else 20),(arm,i,cp.returncode,cp.stderr[-600:])
                    if truth:assert B.verify(cp.stdout,n,cs)
                    checks+=1
            for category in ('random3_uniform','planted_xor_mix','coloring3'):
                src=C.generate(category,31,tmp);parsed=B.problem(src['path'])
                for arm in ARMS:run_one(src,arm,parsed,.2)
            fake=[]
            for src in sources:
                for rep in range(REPEATS):
                    a={'status':'SAT_VERIFIED','e2e_s':.01,'PAR2_s':.01}
                    row={k:src[k] for k in ('id','category','domain','sha256')}
                    row.update(repeat=rep,shard=src['id']%SHARDS,arms={arm:dict(a) for arm in ARMS});fake.append(row)
            assert B.validate(fake,sources)
            assert comparison(fake,'X46_GATE',100)['formula_clustered_stratified_95']==[0.,0.]
            try:B.validate(fake[:-1]+[fake[0]],sources)
            except RuntimeError:pass
            else:raise AssertionError('Duplicate audit failed')
        finally:C.NAMESPACE=old
    emit('GATER2_SELFTEST_PASS',{'exact_oracle_runs':checks,'SAT_cases':sat_count,'UNSAT_cases':unsat_count,
                               'generated_profiles':30,'determinism':True,'duplicate_audit':True})

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('command',choices=('selftest','freeze','shard','finish'))
    ap.add_argument('--shard',type=int,default=0);ap.add_argument('--prior-dir');args=ap.parse_args()
    if args.command=='selftest':selftest()
    elif args.command=='freeze':freeze(args.prior_dir)
    elif args.command=='finish':finish()
    else:
        if args.shard not in range(SHARDS):ap.error('Invalid shard')
        shard(args.shard)
