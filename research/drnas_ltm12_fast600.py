#!/usr/bin/env python3
"""Fast synthetic SAT curriculum. Instance-disjoint, NOT family/OOD evidence.
No official holdout results are training labels. All rewards require witnesses.
"""
import hashlib, itertools, json, os, pathlib, random, sys, tempfile, time
import drnas_ltm12_progressive as L
B, F = L.B, L.F
ROOT = pathlib.Path('ltm12_fast600')
ARMS = L.SCREEN_ARMS
TEST = ('LTM12_NATIVE', 'LTM12_HYBRID') + ARMS
CAP = 1.0

def generate(family, seed):
    r = random.Random(seed)
    n = r.randrange(35, 101)
    model = {i: bool(r.getrandbits(1)) for i in range(1, n+1)}
    clauses = set()
    def add(c):
        c = tuple(sorted(c, key=abs))
        assert any(model[abs(v)] == (v > 0) for v in c)
        clauses.add(c)
    if family == 'xor3':
        for _ in range(n*2):
            vs = r.sample(range(1,n+1),3)
            parity = sum(model[v] for v in vs)%2
            for bits in itertools.product((False,True), repeat=3):
                if sum(bits)%2 != parity:
                    add([(-v if b else v) for v,b in zip(vs,bits)])
    else:
        width, density = {'binary':(2,2), 'three_sparse':(3,3),
                          'three_dense':(3,5), 'mixed':(0,4), 'wide':(6,4)}[family]
        for _ in range(n*density):
            k = width or r.choice((2,3,4,7))
            c = [v if r.getrandbits(1) else -v for v in r.sample(range(1,n+1),k)]
            if not any(model[abs(v)] == (v>0) for v in c):
                j=r.randrange(k); c[j]=-c[j]
            add(c)
    cs=sorted(clauses)
    r.shuffle(cs)
    raw=f'p cnf {n} {len(cs)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in cs)
    witness='v '+' '.join(str(i if model[i] else -i) for i in model)+' 0\n'
    return raw,witness

def collect(root):
    (root/'cases').mkdir(parents=True)
    sources=[]
    families=('binary','three_sparse','three_dense','mixed','wide','xor3')
    for split,count,offset in [('train',60,1200000),('validation',20,2200000),('holdout',20,3200000)]:
        group=[]
        for fidx,family in enumerate(families):
            for i in range(count):
                seed=offset+fidx*10000+i
                raw,witness=generate(family,seed)
                sha=hashlib.sha256(raw.encode()).hexdigest()
                path=root/'cases'/f'{sha}.cnf'; path.write_text(raw)
                assert B.sat_witness_valid(path,B.nvars(path),witness)
                group.append(dict(path=str(path),sha256=sha,split=split,
                                  family=family,generator_seed=seed))
        random.Random(offset).shuffle(group);sources.extend(group)
    assert len(sources)==len({s['sha256'] for s in sources})==600
    for i,s in enumerate(sources):s['id']=i
    (root/'manifest.json').write_text(json.dumps(dict(sources=sources,
        synthetic=True,all_SAT=True,instance_disjoint=True,family_disjoint=False,
        outcome_filtering=False,official_benchmark_claim=False),indent=2))
    return sources

def trial(arm,source,seed):
    row=L.run_checked(arm,source,seed,CAP)
    if row['status'] in ('UNSAT_UNVERIFIED','UNSAT_MATH_CERTIFIED'):
        raise RuntimeError('UNSAT on independently witness-checked SAT source')
    row['family']=source['family']
    return row

def routed(mode,memory,source,seed):
    start=time.monotonic();model=memory[mode]
    # Disabled policies do not need structural features.
    feature=F.extract(source['path']) if model['enabled'] else {}
    chosen=L.pick(model,feature);overhead=time.monotonic()-start
    if overhead >= CAP-0.55:
        row=dict(id=source['id'],split=source['split'],seed=seed,status='UNKNOWN',
                 verified=False,php_math_certified=False,e2e_s=CAP)
    else: row=L.run_checked(chosen,source,seed,CAP-overhead)
    row.update(arm='LTM12_'+mode,chosen_solver=chosen,family=source['family'],
               feature_extract_s=overhead,e2e_s=time.monotonic()-start,cap_s=CAP)
    if row['e2e_s']>CAP:row.update(status='UNKNOWN',verified=False,php_math_certified=False)
    return B.with_metrics(row,CAP)

def main():
    if '--selftest' in sys.argv:
        with tempfile.TemporaryDirectory() as td:
            sources=collect(pathlib.Path(td))
            assert len([s for s in sources if s['split']=='train'])==360
            for source in sources:F.extract(source['path'])
        # No signal (all UNKNOWN) must never enable a policy.
        f={k:0.0 for k in F.FEATURES}
        rows={a:dict(cap_s=CAP,PAR2_verified_s=2*CAP) for a in ARMS}
        for mode in ('NATIVE','HYBRID'):
            assert not L.fit([(f,rows)]*20,[(f,rows)]*10,mode,.002,.05)['enabled']
        L.selftest();print('LTM12_FAST600_SELFTEST_PASS 600 unique witness-verified CNFs',flush=True)
        return
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    L.setup_source()
    sources=collect(ROOT);pairs={'train':[],'validation':[]};screen=[]
    L.emit('LTM12_FAST600_START',dict(sources=600,train=360,validation=120,holdout=120,cap_s=CAP))
    with (ROOT/'screen.jsonl').open('w') as fd:
        for s in sources:
            if s['split']=='holdout':continue
            t=time.monotonic();f=F.extract(s['path']);f['feature_extract_s']=time.monotonic()-t
            paired={}
            rotated=list(ARMS);shift=s['id']%len(ARMS);rotated=rotated[shift:]+rotated[:shift]
            for arm in rotated:
                row=trial(arm,s,17);paired[arm]=row;screen.append(row)
                fd.write(json.dumps(row)+'\n');fd.flush()
            pairs[s['split']].append((f,paired))
            if (s['id']+1)%60==0:
                L.emit('LTM12_FAST600_PROGRESS',dict(completed_sources=s['id']+1,
                    split=s['split'],metrics=B.metrics(screen,CAP,ARMS),
                    oracle_PAR2_s=sum(min(r['PAR2_verified_s'] for r in rs.values()) for _,rs in pairs[s['split']]),
                    note='Training signal only; not holdout performance'))
    B.check_contradictions(screen)
    # One candidate per mode, one validation gate. No repeated validation tuning.
    models={mode:L.fit(pairs['train'],pairs['validation'],mode,
                      win_margin=.002,min_gain=.05) for mode in ('NATIVE','HYBRID')}
    memory=dict(schema=L.SCHEMA,models=models,holdout_used_for_fit=False,
                train_sha256=[s['sha256'] for s in sources if s['split']=='train'],
                validation_sha256=[s['sha256'] for s in sources if s['split']=='validation'],
                noise_margin_s=.002,min_aggregate_gain_s=.05)
    (ROOT/'memory.json').write_text(json.dumps(memory,indent=2))
    models=json.loads((ROOT/'memory.json').read_text())['models']
    L.emit('LTM12_FAST600_LEARNED',models)
    rows=[]
    with (ROOT/'holdout.jsonl').open('w') as fd:
        for s in sources:
            if s['split']!='holdout':continue
            for rep,seed in enumerate((17,29,43)):
                shift=(s['id']+rep)%len(TEST);order=TEST[shift:]+TEST[:shift]
                for arm in order:
                    row=(routed(arm.split('_',1)[1],models,s,seed) if arm.startswith('LTM12_') else trial(arm,s,seed))
                    row.update(rep=rep,shard=(s['id']-480)//30)
                    rows.append(row);fd.write(json.dumps(row)+'\n');fd.flush()
            if (s['id']+1)%30==0:L.emit('LTM12_FAST600_HOLDOUT',B.metrics(rows,CAP,TEST))
    B.check_contradictions(rows)
    totals=B.metrics(rows,CAP,TEST)
    report=dict(synthetic=True,official=False,source_count=600,holdout_sources=120,
                repetitions=3,one_CPU=True,models=models,totals=totals,
                shards={str(i):B.metrics([r for r in rows if r['shard']==i],CAP,TEST) for i in range(4)},
                families={f:B.metrics([r for r in rows if r['family']==f],CAP,TEST) for f in sorted({s['family'] for s in sources})},
                native_speedup=totals['LTM9_FAST']['PAR2_verified_s']/totals['LTM12_NATIVE']['PAR2_verified_s'],
                hybrid_speedup=totals['Kissat']['PAR2_verified_s']/totals['LTM12_HYBRID']['PAR2_verified_s'])
    (ROOT/'report.json').write_text(json.dumps(report,indent=2));L.emit('LTM12_FAST600_FINAL',report)
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:
            f.write('## LTM12 FAST600 — synthetic SAT, one CPU\n\n360 train / 120 validation / 120 holdout x3. Not an official or family-disjoint benchmark.\n\n| Arm | Verified solved | PAR2 s |\n|---|---:|---:|\n')
            for a,m in totals.items():f.write(f"| {a} | {m['SAT_verified']}/{m['trials']} | {m['PAR2_verified_s']:.6f} |\n")
    print('LTM12_FAST600_PASS',flush=True)

if __name__=='__main__':main()
