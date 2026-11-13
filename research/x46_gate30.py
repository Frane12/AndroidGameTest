#!/usr/bin/env python3
"""Frozen 600-SAT/30-profile, 3-repeat, 5-arm native gate ablation.
Primary comparison: GATE vs X45_ONLINE; SPARSE separates fewer probes from
adaptive scheduling. All generated, no claim of industrial/UNSAT superiority.
"""
from __future__ import annotations
import argparse, collections, hashlib, itertools, json, math, os, random
import statistics, subprocess, tempfile, time
from pathlib import Path
import x46_categories as C

CAP=2.0
REPEATS=3
EACH=20
SHARDS=12
ARMS={
 'CORE':('build/drnas-x41','core'),
 'ADAPTIVE':('build/drnas-x3','x3'),
 'X45_ONLINE':('build/drnas-x45','x45_online'),
 'X46_SPARSE':('build/drnas-x46','x46_sparse'),
 'X46_GATE':('build/drnas-x46','x46_gate'),
}

def emit(tag,obj):print(tag+' '+json.dumps(obj,sort_keys=True,separators=(',',':')),flush=True)
def dump(path,obj):Path(path).write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n')

def problem(path):
    n=m=None;clauses=[];pending=[]
    for line in Path(path).read_text().splitlines():
        if not line.strip() or line.startswith('c'):continue
        if line.startswith('p '):
            _,typ,ns,ms=line.split();assert typ=='cnf';n=int(ns);m=int(ms);continue
        for tok in line.split():
            x=int(tok)
            if x: pending.append(x)
            else:clauses.append(pending);pending=[]
    if n is None or pending or len(clauses)!=m:raise ValueError('Invalid DIMACS')
    if any(not 0<abs(x)<=n for c in clauses for x in c):raise ValueError('Bad literal')
    return n,clauses

def verify(stdout,n,clauses):
    assn={}
    for line in stdout.splitlines():
        if not line.startswith('v '):continue
        for tok in line[2:].split():
            x=int(tok)
            if not x:continue
            if not 0<abs(x)<=n or abs(x) in assn:return False
            assn[abs(x)]=x>0
    return len(assn)==n and all(any(assn[abs(x)]==(x>0) for x in c) for c in clauses)

def run_one(src,arm,parsed,cap=CAP):
    exe,mode=ARMS[arm];t=time.perf_counter();p=None
    try:p=subprocess.run([exe,src['path'],'--mode',mode,'--time',str(cap),'--stats'],capture_output=True,text=True,timeout=cap+.75)
    except subprocess.TimeoutExpired:pass
    process_s=time.perf_counter()-t;stats={};gate={};sat=False
    if p is not None:
        if p.returncode not in (0,10,20):raise RuntimeError((arm,src['sha256'],p.returncode,p.stderr[-1200:]))
        if p.returncode==20:raise RuntimeError('UNSAT contradicts hidden SAT witness: '+src['sha256'])
        if p.returncode==10:
            if not verify(p.stdout,*parsed):raise RuntimeError('Invalid original-CNF SAT witness')
            sat=True
        for line in p.stderr.splitlines():
            if line.startswith(('X41_STATS ','X3_STATS ','X45_STATS ','X46_STATS ')):stats=json.loads(line.split(' ',1)[1])
            elif line.startswith('X46_GATE '):gate=json.loads(line.split(' ',1)[1])
        if not stats:raise RuntimeError('Missing stats '+arm)
        if arm.startswith('X46') and not gate:raise RuntimeError('Missing gate diagnostics')
    total=time.perf_counter()-t
    solved=sat and total<=cap
    return {'status':'SAT_VERIFIED' if solved else 'UNKNOWN','e2e_s':round(total,7),
            'process_s':round(process_s,7),'verify_and_parse_s':round(total-process_s,7),
            'late_verified':sat and not solved,'PAR2_s':round(total if solved else 2*cap,7),
            'decisions':stats.get('decisions',0),'conflicts':stats.get('conflicts',0),
            'probe_seconds':stats.get('probe_seconds',0.0),
            'counterfactuals':stats.get('x45_counterfactuals',0),
            'updates':stats.get('x45_online_updates',0),
            'interventions':stats.get('x45_interventions',0),'gate':gate}

def freeze(prior_dir):
    rows,text,sha=C.make_manifest('x46_generated',EACH)
    previous=set();files=[]
    if prior_dir:
        files=sorted(set(Path(prior_dir).rglob('manifest.json'))|set(Path(prior_dir).rglob('frozen_manifest.json')))
        if not files:raise RuntimeError('Expected previous frozen manifests missing')
        for path in files:
            data=json.loads(path.read_text())
            if not isinstance(data,list):raise RuntimeError('Unexpected history manifest schema')
            previous.update(x['sha256'] for x in data)
        if previous&{r['sha256'] for r in rows}:raise RuntimeError('Historical SHA reused')
    dest=Path('x46_frozen');dest.mkdir(exist_ok=True)
    (dest/'manifest.json').write_text(text)
    protocol={'manifest_sha256':sha,'sources':600,'profiles':30,'each':EACH,'repeats':REPEATS,
              'cap_s':CAP,'shards':SHARDS,'arms':list(ARMS),'expected_solver_runs':9000,
              'primary':'X46_GATE vs X45_ONLINE',
              'success_rule':'at least 5% lower verified PAR2, no lost solved runs, formula-clustered CI upper < 0; separately compare both controls',
              'historical_sha_checked':len(previous),'history_manifests':len(files),
              'generated_sat_only':True,'no_outcome_based_filtering':True,
              'probe_reward':'local usefulness proxy, not causal seconds saved',
              'training':'online within each solve; reset for every formula and repetition',
              'code_sha256':{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in
                             ('research/x46_categories.py','research/x46_gate30.py','research/build_x46_gate30.py','src/drnas_x45.cpp')}}
    dump(dest/'protocol.json',protocol);emit('X46_FROZEN',protocol)

def manifest():
    raw=Path('x46_frozen/manifest.json').read_bytes();p=json.loads(Path('x46_frozen/protocol.json').read_text())
    if hashlib.sha256(raw).hexdigest()!=p['manifest_sha256']:raise RuntimeError('Frozen manifest changed')
    if p['arms']!=list(ARMS) or p['repeats']!=REPEATS or p['cap_s']!=CAP:raise RuntimeError('Protocol changed')
    for name,sha in p['code_sha256'].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=sha:raise RuntimeError('Code drift '+name)
    return json.loads(raw),p

def shard(number):
    frozen,protocol=manifest();root=Path('x46_stage');root.mkdir(exist_ok=True)
    selected=[r for r in frozen if r['id']%SHARDS==number]
    counts=collections.Counter();done=[]
    with (root/'trials.jsonl').open('w') as out:
        for ix,meta in enumerate(selected,1):
            src=C.generate(meta['category'],meta['replicate_id'],'x46_generated')
            if src['sha256']!=meta['sha256']:raise RuntimeError('Generated input changed')
            parsed=problem(src['path'])
            for rep in range(REPEATS):
                keys=list(ARMS);rot=(meta['id']+2*rep)%len(keys);keys=keys[rot:]+keys[:rot]
                arms={key:run_one(src,key,parsed) for key in keys}
                row={'id':meta['id'],'sha256':meta['sha256'],'category':meta['category'],
                     'domain':meta['domain'],'repeat':rep,'shard':number,'arms':arms}
                out.write(json.dumps(row,sort_keys=True,separators=(',',':'))+'\n');out.flush();done.append(row)
                for key,a in arms.items():
                    counts[key+'_solved']+=a['status']=='SAT_VERIFIED';counts[key+'_PAR2_s']+=a['PAR2_s']
            if ix%10==0:emit('X46_PROGRESS',{'shard':number,'sources_done':ix,'sources_total':len(selected),**counts})
    report={'shard':number,'sources':len(selected),'paired_rows':len(done),'manifest_sha256':protocol['manifest_sha256'],
            'arms':summarize(done)}
    dump(root/'report.json',report);emit('X46_SHARD_FINAL',report)

def summarize(rows):
    out={}
    for key in ARMS:
        values=[r['arms'][key] for r in rows];groups=collections.defaultdict(list)
        for r in rows:groups[r['sha256']].append(r['arms'][key]['status']=='SAT_VERIFIED')
        a={'sources':len(groups),'trials':len(values),'SAT_verified':sum(v['status']=='SAT_VERIFIED' for v in values),
           'stable_solved_sources':sum(len(v)==REPEATS and all(v) for v in groups.values()),
           'ever_solved_sources':sum(any(v) for v in groups.values())}
        for field in ('PAR2_s','e2e_s','verify_and_parse_s','probe_seconds','counterfactuals','updates','interventions','decisions','conflicts'):
            a[field]=round(sum(v[field] for v in values),7)
        a['gate_totals']={g:sum(v['gate'].get(g,0) for v in values) for g in
                         ('calls','skipped_schedule','skipped_cost','proxy_good','proxy_bad','throttles','accelerations','shock_checks')}
        out[key]=a
    return out

def paired_stats(rows,base,iterations=2000):
    formula=collections.defaultdict(list);cats={}
    for r in rows:
        ident=r['sha256'];a=r['arms']['X46_GATE'];b=r['arms'][base]
        formula[ident].append(a['PAR2_s']-b['PAR2_s']);cats[ident]=r['category']
    bycat=collections.defaultdict(list)
    for ident,v in formula.items():bycat[cats[ident]].append(sum(v))
    rng=random.Random(46030);boot=[];cboot=[];names=sorted(bycat)
    totals=[sum(bycat[k]) for k in names]
    for _ in range(iterations):
        boot.append(sum(sum(rng.choice(v) for _ in range(len(v))) for v in bycat.values()))
        cboot.append(sum(rng.choice(totals) for _ in names))
    boot.sort();cboot.sort();lo=int(.025*iterations);hi=int(.975*iterations)
    return {'baseline':base,'delta_PAR2_s':round(sum(totals),7),
            'formula_clustered_stratified_95':[round(boot[lo],7),round(boot[hi],7)],
            'category_clustered_95':[round(cboot[lo],7),round(cboot[hi],7)],
            'formula_units':len(formula),'category_units':len(names),'repeats_not_independent':True}

def validate(rows,frozen):
    expected={r['sha256']:r for r in frozen};seen=set()
    if len(rows)!=len(frozen)*REPEATS:raise RuntimeError('Incomplete paired rows')
    for r in rows:
        key=(r['sha256'],r['repeat'])
        if key in seen or r['sha256'] not in expected or r['repeat'] not in range(REPEATS):raise RuntimeError('Duplicated or extra trial')
        seen.add(key);orig=expected[r['sha256']]
        if any(r[k]!=orig[k] for k in ('id','category','domain')):raise RuntimeError('Source metadata drift')
        if r['shard']!=r['id']%SHARDS or set(r['arms'])!=set(ARMS):raise RuntimeError('Wrong shard or missing arm')
        for a in r['arms'].values():
            if a['status'] not in ('SAT_VERIFIED','UNKNOWN') or not math.isfinite(a['e2e_s']) or a['e2e_s']<0:raise RuntimeError('Invalid outcome')
            target=a['e2e_s'] if a['status']=='SAT_VERIFIED' else 2*CAP
            if abs(a['PAR2_s']-target)>1e-6:raise RuntimeError('Invalid PAR2')
            if a['status']=='SAT_VERIFIED' and a['e2e_s']>CAP:raise RuntimeError('Late SAT counted')
    return True

def finish():
    frozen,p=manifest();rows=[]
    for shardid in range(SHARDS):
        folder=Path('x46_downloads')/f'x46-gate30-{shardid}'
        report=json.loads((folder/'report.json').read_text())
        if report['manifest_sha256']!=p['manifest_sha256']:raise RuntimeError('Mismatched shard')
        part=[json.loads(x) for x in (folder/'trials.jsonl').read_text().splitlines()]
        if any(x['shard']!=shardid for x in part):raise RuntimeError('Misfiled trial')
        rows.extend(part)
    validate(rows,frozen);rows.sort(key=lambda r:(r['id'],r['repeat']))
    overall=summarize(rows)
    categories={c:summarize([r for r in rows if r['category']==c]) for c,_ in C.SPECS}
    if len(categories)!=30 or any(v['CORE']['sources']!=20 for v in categories.values()):raise RuntimeError('Category audit')
    comparisons={k:paired_stats(rows,k) for k in ARMS if k!='X46_GATE'}
    primary=comparisons['X45_ONLINE'];old=overall['X45_ONLINE'];new=overall['X46_GATE']
    passed=(new['PAR2_s']<=.95*old['PAR2_s'] and new['SAT_verified']>=old['SAT_verified'] and
            primary['formula_clustered_stratified_95'][1]<0)
    if new['updates']<=0 or new['gate_totals']['calls']<=0:raise RuntimeError('Gate never exercised')
    report={'status':'COMPLETE','protocol':p,'overall':overall,'categories':categories,
            'domains':{d:summarize([r for r in rows if r['domain']==d]) for d in sorted({d for _,d in C.SPECS})},
            'shards':{str(s):summarize([r for r in rows if r['shard']==s]) for s in range(SHARDS)},
            'comparisons':comparisons,'primary_success_rule_pass':passed,
            'limits':'Generated SAT structural profiles; not 30 independent real-world domains. Local proxy gate, not causal runtime predictor. 600 formula clusters, not 9000 independent examples. No outcome filtering. SAT witnesses independently checked; no large UNSAT claims.'}
    dest=Path('x46_final');dest.mkdir(exist_ok=True);dump(dest/'report.json',report)
    (dest/'paired_trials.jsonl').write_text(''.join(json.dumps(r,sort_keys=True,separators=(',',':'))+'\n' for r in rows))
    lines=['## X4.6 GATE30 — 600 generated SAT CNFs × 3 repeats × 5 arms','',
           '| Arm | Verified SAT /1800 | Stable solved /600 | PAR2 s | E2E s | Probe s |',
           '|---|---:|---:|---:|---:|---:|']
    for key,a in overall.items():lines.append(f"| {key} | {a['SAT_verified']} | {a['stable_solved_sources']} | {a['PAR2_s']:.3f} | {a['e2e_s']:.3f} | {a['probe_seconds']:.3f} |")
    lines+=['','| Category (20 sources × 3) | CORE PAR2 | ADAPTIVE | X45 | SPARSE | GATE |','|---|---:|---:|---:|---:|---:|']
    for c,_ in C.SPECS:lines.append('| '+c+' | '+' | '.join(f"{categories[c][k]['PAR2_s']:.3f}" for k in ARMS)+' |')
    lines+=['',f'Primary criterion passed: **{passed}**. Negative Δ favors X4.6.']
    for k,v in comparisons.items():lines.append(f"- GATE vs {k}: ΔPAR2 {v['delta_PAR2_s']:.3f}s; formula-clustered 95% {v['formula_clustered_stratified_95']}; category-clustered 95% {v['category_clustered_95']}.")
    lines+=['',report['limits']]
    text='\n'.join(lines)+'\n';(dest/'summary.md').write_text(text)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:f.write(text)
    emit('X46_FINAL',{'status':'COMPLETE','sources':600,'categories':30,'repeats':3,'overall':overall,'comparisons':comparisons,'primary_success_rule_pass':passed})


def selftest(no_native=False):
    assert len(C.SPECS)==30 and len(dict(C.SPECS))==30
    with tempfile.TemporaryDirectory() as d:
        sample,text,sha=C.make_manifest(d,2)
        again,text2,sha2=C.make_manifest(d,2)
        assert sha==sha2 and text==text2 and len({r['sha256'] for r in sample})==60
        for r in sample:
            n,cs=problem(r['path']);assert n==r['nvars'] and len(cs)==r['nclauses']
        fake=[]
        for meta in sample:
            for rep in range(REPEATS):
                a={'status':'SAT_VERIFIED','e2e_s':.01,'PAR2_s':.01}
                fake.append({k:meta[k] for k in ('id','category','domain','sha256')} |
                            {'repeat':rep,'shard':meta['id']%SHARDS,'arms':{k:dict(a) for k in ARMS}})
        assert validate(fake,sample)
        broken=fake[:-1]+[fake[0]]
        try:validate(broken,sample)
        except RuntimeError:pass
        else:raise AssertionError('Duplicate not caught')
        check=paired_stats(fake,'CORE',100)
        assert check['formula_clustered_stratified_95']==[0,0]
        if not no_native:
            rng=random.Random(4606)
            for i in range(60):
                n=6;cs=[]
                for _ in range(16+i%12):
                    vs=rng.sample(range(1,n+1),2+i%2);cs.append([v if rng.getrandbits(1) else -v for v in vs])
                truth=any(all(any(bits[abs(v)-1]==(v>0) for v in c) for c in cs) for bits in itertools.product((False,True),repeat=n))
                path=Path(d)/'oracle.cnf';path.write_text(f'p cnf {n} {len(cs)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in cs))
                for key,(exe,mode) in ARMS.items():
                    run=subprocess.run([exe,str(path),'--mode',mode,'--time','1','--stats'],text=True,capture_output=True,timeout=3)
                    assert run.returncode==(10 if truth else 20),(key,i,run.returncode,run.stderr)
                    if truth:assert verify(run.stdout,n,cs)
            prior=C.NAMESPACE;C.NAMESPACE+='-smoke-only'
            try:
                for cat in ('random3_uniform','planted_xor_mix','coloring3'):
                    src=C.generate(cat,31,d);parsed=problem(src['path'])
                    for key in ARMS:run_one(src,key,parsed,.20)
            finally:C.NAMESPACE=prior
    emit('X46_SELFTEST_PASS',{'generated_smoke':60,'exact_oracle_runs':0 if no_native else 300,'duplicate_audit':True,'all_30_labels_audited':True})

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('command',choices=('selftest','freeze','shard','finish'))
    ap.add_argument('--shard',type=int,default=0);ap.add_argument('--prior-dir');ap.add_argument('--no-native',action='store_true');a=ap.parse_args()
    if a.command=='selftest':selftest(a.no_native)
    elif a.command=='freeze':freeze(a.prior_dir)
    elif a.command=='shard':
        if a.shard not in range(SHARDS):ap.error('Invalid shard')
        shard(a.shard)
    else:finish()
