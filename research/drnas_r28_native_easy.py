#!/usr/bin/env python3
"""Retrospective measured-easy originals and separately scored synthetic controls."""
import argparse,collections,json,os,pathlib,random,tempfile
import drnas_r28_native_benchmark as B
ROOT=pathlib.Path('r28_native_easy')
ARMS=('R28_NATIVE_DIRECT','R153_EXACT','Kissat','CaDiCaL','CryptoMiniSat')
REPEATS=3
CAPS={'official_easy':8.,'synthetic_easy':2.}
def emit(tag,x):B.emit('R28_EASY_'+tag,x)
def controls():
    cases=B.controls()
    rng=random.Random(2815316012)
    for n in (40,60,100,140):
        witness=[rng.getrandbits(1) for _ in range(n)];cs=[]
        for _ in range(4*n):
            c=[v if rng.getrandbits(1) else -v for v in rng.sample(range(1,n+1),3)]
            if not any(witness[abs(v)-1]==(v>0) for v in c):c[0]=-c[0]
            cs.append(c)
        p=ROOT/'controls'/f'planted_easy_{n}.cnf'
        p.write_text(f'p cnf {n} {len(cs)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in cs))
        cases.append(dict(id=f'planted_easy_{n}',path=str(p),sha256=B.sha(p),cohort='planted3sat',dataset='synthetic_controls'))
    assert len(cases)==12 and len({c['sha256'] for c in cases})==12
    return cases

def prepare():
    from remotezip import RemoteZip
    from drnas_r153_real_context import decode
    frozen=json.loads(pathlib.Path('research/drnas_r28_native_easy_sources.json').read_text());cases=[]
    (ROOT/'originals').mkdir(parents=True,exist_ok=True)
    with RemoteZip(frozen['archive'],timeout=90) as archive:
        for item in frozen['sources']:
            assert any(e['status']=='SAT_VERIFIED' and e['e2e_s']<2 for e in item['evidence'])
            raw=decode(item['source_file'],archive.read(item['source_file']))
            p=ROOT/'originals'/f"{item['sha256'][:16]}.cnf";p.write_bytes(raw);assert B.sha(p)==item['sha256']
            c=dict(item,id='official_'+str(item['id']),path=str(p),cohort=item['normalized_name_family'],dataset='official_SAT2024_retrospective',split='evaluation')
            cases.append(c);emit('SOURCE',c)
    synth=controls();assert len({c['sha256'] for c in cases+synth})==16
    plan=[dict(stage='official_easy',cap_s=8.,sources=cases),dict(stage='synthetic_easy',cap_s=2.,sources=synth)]
    (ROOT/'manifest.json').write_text(json.dumps(dict(plans=plan,arms=ARMS,repeats=REPEATS,blind=False,selection='historical verified solves under 2s by at least one solver; synthetic separate'),indent=2)+'\n')

def validate(rows,plans):
    expected={(p['stage'],c['sha256'],a,r) for p in plans for c in p['sources'] for a in ARMS for r in range(REPEATS)}
    keys=[(r['stage'],r['sha256'],r['arm'],r['rep']) for r in rows]
    assert len(keys)==len(set(keys)) and set(keys)==expected,'missing/duplicate attempts'
    claims=collections.defaultdict(set)
    for r in rows:
        assert r['cap_s']==CAPS[r['stage']] and r['seed']==17+12*r['rep']
        assert abs(r['PAR2_verified_s']-(r['e2e_s'] if r['verified'] else 2*r['cap_s']))<1e-8
        if r['reported_solved']:claims[r['sha256']].add('UNSAT' if r['status'].startswith('UNSAT') else 'SAT')
    assert all(len(v)<=1 for v in claims.values()),'contradictory solver claims'

def report(rows,complete):
    result=B.summary(rows,complete)
    result.update(blind=False,selection='measured easy retrospective originals plus separate synthetic controls',one_logical_cpu=True,repeats=REPEATS,pooled_PAR2=False)
    result['reference_over_direct']={stage:{a:{metric:s[metric]/g['R28_NATIVE_DIRECT'][metric] if g['R28_NATIVE_DIRECT'][metric]>0 else None for metric in ('PAR2_verified_s','PAR2_reported_s')} for a,s in g.items() if a!='R28_NATIVE_DIRECT'} for stage,g in result['groups'].items() if stage.endswith('/ALL')}
    (ROOT/'report.json').write_text(json.dumps(result,indent=2)+'\n');return result

def run():
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    plans=json.loads((ROOT/'manifest.json').read_text())['plans'];rows=[]
    emit('START',dict(cpu=cpu,arms=ARMS,repeats=REPEATS,plans=[dict(stage=p['stage'],cap_s=p['cap_s'],sources=len(p['sources'])) for p in plans]))
    with (ROOT/'results.jsonl').open('w') as f:
        for p in plans:
            for c in p['sources']:
                assert B.sha(pathlib.Path(c['path']))==c['sha256']
                for rep in range(REPEATS):
                    order=list(ARMS);random.Random(c['sha256']+str(rep)).shuffle(order)
                    for arm in order:
                        r=B.trial(c,arm,p['stage'],rep,p['cap_s']);rows.append(r)
                        f.write(json.dumps(r)+'\n');f.flush();emit('TRIAL',r)
                partial=report(rows,False);emit('PROGRESS',dict(stage=p['stage'],trials=len(rows),groups={k:v for k,v in partial['groups'].items() if k.endswith('/ALL')}))
    validate(rows,plans);result=report(rows,True);emit('FINAL',result)
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:
            for stage in CAPS:
                f.write(f'## {stage}: cap {CAPS[stage]:g}s, 3 repeats\n\n|Arm|Verified|Unique solved|Reported|PAR2 verified s|PAR2 reported s|\n|---|---:|---:|---:|---:|---:|\n')
                for a,s in sorted(result['groups'][stage+'/ALL'].items(),key=lambda kv:kv[1]['PAR2_verified_s']):
                    f.write(f"|{a}|{s['verified']}/{s['trials']}|{s['unique_verified']}|{s['reported_solved']}|{s['PAR2_verified_s']:.4f}|{s['PAR2_reported_s']:.4f}|\n")
            f.write('\nRetrospective easy diagnostic, not blind. Do not pool stages. SAT original witness checked; generic UNSAT without independent proof remains unverified. R153 exact-only abstains on unsupported inputs. No promotion.\n')

def selftest():
    global ROOT
    old=ROOT
    with tempfile.TemporaryDirectory() as d:
        ROOT=pathlib.Path(d);B.ROOT=ROOT;synth=controls()
        # All planted controls carry a real SAT model by construction; no claimed runtime guarantee.
        assert len(synth)==12
        plans=[dict(stage='synthetic_easy',sources=synth)]
        rows=[dict(stage='synthetic_easy',sha256=c['sha256'],arm=a,rep=r,seed=17+12*r,cap_s=2.,verified=False,reported_solved=False,status='TIMEOUT',e2e_s=2.,PAR2_verified_s=4.) for c in synth for a in ARMS for r in range(REPEATS)]
        validate(rows,plans)
        for bad in (rows[:-1],rows+[rows[0]]):
            try:validate(bad,plans)
            except AssertionError:pass
            else:raise AssertionError('bad pairs accepted')
    ROOT=old;B.ROOT=ROOT;emit('SELFTEST_PASS',dict(controls=12,completeness=True,duplicates=True))
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','run','selftest']);a=ap.parse_args()
    ROOT.mkdir(exist_ok=True);B.ROOT=ROOT;globals()[a.action]()
