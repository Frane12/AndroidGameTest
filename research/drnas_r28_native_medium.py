#!/usr/bin/env python3
"""Medium-scope paired original-CNF benchmark, unchanged native DIRECT."""
import argparse,collections,hashlib,json,lzma,bz2,os,pathlib,random,re
import drnas_r28_native_benchmark as B
ROOT=pathlib.Path('r28_native_medium')
ARMS=('R28_NATIVE_DIRECT','R153_EXACT','Kissat','CaDiCaL','CryptoMiniSat')
CAP=60.;REPEATS=2;SHARDS=3
def emit(tag,x): B.emit('R28_MEDIUM_'+tag,x)
def select(parent):
    pool=sorted(parent['sources'],key=lambda s:(s['compressed_bytes'],s['source_file']))
    assert len(pool)==24 and len({s['sha256'] for s in pool})==24
    chosen=pool[1::2]
    assert not {s['sha256'] for s in chosen}&{s['sha256'] for s in pool[::2]}
    return chosen
def prepare():
    from remotezip import RemoteZip
    from drnas_r153_real_context import decode
    manifests=[json.loads(p.read_text()) for p in pathlib.Path('real24_source').rglob('manifest.json')]
    parents=[m for m in manifests if m.get('original_CNF') and len(m.get('sources',[]))==24]
    assert len(parents)==1
    parent=parents[0];sources=[]
    (ROOT/'cases').mkdir(parents=True,exist_ok=True)
    with RemoteZip(parent['archive'],timeout=90) as archive:
        for i,s in enumerate(select(parent)):
            raw=decode(s['source_file'],archive.read(s['source_file']))
            sha=hashlib.sha256(raw).hexdigest();assert sha==s['sha256']
            header=re.search(rb'(?m)^p\s+cnf\s+(\d+)\s+(\d+)\s*$',raw);assert header
            p=ROOT/'cases'/f'{i:02d}_{sha[:16]}.cnf';p.write_bytes(raw)
            c=dict(s,id=i,parent_id=s['id'],path=str(p),cohort=s['family'],dataset='official_SAT2024_retrospective',variables=int(header[1]),clauses=int(header[2]))
            sources.append(c);emit('SOURCE',c)
    manifest=dict(sources=sources,original_CNF=True,blind=False,parent_run=43161813420,archive=parent['archive'],selection='odd positions of compressed-size-sorted frozen real24; disjoint from previous real12; no outcome filtering',cap_s=CAP,repeats=REPEATS,arms=ARMS)
    (ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
def read_sources():return json.loads((ROOT/'manifest.json').read_text())['sources']
def validate(rows,sources):
    expected={(s['sha256'],a,r) for s in sources for a in ARMS for r in range(REPEATS)}
    keys=[(r['sha256'],r['arm'],r['rep']) for r in rows]
    assert len(keys)==len(set(keys)) and set(keys)==expected,'missing/duplicate pairs'
    by_sha={s['sha256']:s for s in sources};claims=collections.defaultdict(set)
    for r in rows:
        s=by_sha[r['sha256']]
        assert r['cap_s']==CAP and r['seed']==17+12*r['rep'] and r['id']==s['id'] and r['shard']==s['id']//4
        if r['reported_solved']:claims[r['sha256']].add('UNSAT' if r['status'].startswith('UNSAT') else 'SAT')
    assert all(len(v)<=1 for v in claims.values()),'contradictory solver claims'
def report(rows,complete):
    result=B.summary(rows,complete);totals=result['groups'].get('official60/ALL',{});native=totals.get('R28_NATIVE_DIRECT',{})
    result.update(one_CPU_per_solver=True,paired_same_runner=True,blind=False,cap_s=CAP,repeats=REPEATS,totals=totals,shards=sorted({r['shard'] for r in rows}))
    result['shard_totals']={str(i):{a:{k:sum(r[k] for r in rows if r['shard']==i and r['arm']==a) for k in ('verified','reported_solved','PAR2_verified_s','PAR2_reported_s')} for a in ARMS} for i in range(SHARDS)}
    result['reference_over_direct']={a:{k:totals[a][k]/native[k] if native[k]>0 else None for k in ('PAR2_verified_s','PAR2_reported_s')} for a in totals if a!='R28_NATIVE_DIRECT'}
    result['verification']='Original SAT model; independent GF2/PHP certificates; generic UNSAT unverified. R153_EXACT has no general fallback; UNKNOWN gets full PAR2 penalty.'
    (B.ROOT/'report.json').write_text(json.dumps(result,indent=2)+'\n');return result
def worker(shard):
    assert shard in range(SHARDS)
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    B.ROOT=ROOT/f'shard-{shard}';B.ROOT.mkdir(parents=True,exist_ok=True)
    sources=[s for s in read_sources() if s['id']//4==shard];assert len(sources)==4
    emit('START',dict(shard=shard,cpu=cpu,sources=4,arms=ARMS,repeats=REPEATS,cap_s=CAP));rows=[]
    with (B.ROOT/'results.jsonl').open('w') as f:
        for c in sources:
            assert B.sha(pathlib.Path(c['path']))==c['sha256']
            for rep in range(REPEATS):
                order=list(ARMS);random.Random(c['sha256']+str(rep)).shuffle(order)
                for arm in order:
                    row=B.trial(c,arm,'official60',rep,CAP);row['shard']=shard
                    rows.append(row);f.write(json.dumps(row)+'\n');f.flush();emit('TRIAL',row)
            emit('PROGRESS',dict(shard=shard,trials=len(rows),totals=report(rows,False)['totals']))
    validate(rows,sources);result=report(rows,True);emit('SHARD_FINAL',dict(shard=shard,totals=result['totals']))
def audit():
    rows=[]
    for shard in range(SHARDS):
        folder=ROOT/f'shard-{shard}';assert json.loads((folder/'report.json').read_text())['complete']
        rows.extend(json.loads(l) for l in (folder/'results.jsonl').read_text().splitlines())
    for name in ('cms.sha256','cms-version.txt'):
        assert len({(ROOT/f'shard-{i}'/name).read_text() for i in range(SHARDS)})==1,'CMS differs between runners'
    validate(rows,read_sources());B.ROOT=ROOT;result=report(rows,True);emit('FINAL',result)
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:
            f.write('## R28 NATIVE DIRECT medium: 12 original SAT2024 CNFs x 2 repeats x 60s\n\n|Arm|Verified|Reported|PAR2 verified s|PAR2 reported s|\n|---|---:|---:|---:|---:|\n')
            for a,s in sorted(result['totals'].items(),key=lambda kv:kv[1]['PAR2_verified_s']):
                f.write(f"|{a}|{s['verified']}/{s['trials']}|{s['reported_solved']}|{s['PAR2_verified_s']:.3f}|{s['PAR2_reported_s']:.3f}|\n")
            f.write('\nOne logical CPU per solver. Previously used parent dataset; not blind. R153 exact-only is a specialized baseline. Generic UNSAT without independent proof is separate. No automatic promotion.\n')
def selftest():
    p=dict(sources=[dict(sha256=str(i),source_file=str(i),compressed_bytes=i) for i in range(24)])
    assert [s['sha256'] for s in select(p)]==[str(i) for i in range(1,24,2)]
    sources=[dict(id=i,sha256=str(i)) for i in range(12)]
    rows=[dict(sha256=s['sha256'],id=s['id'],shard=s['id']//4,arm=a,rep=r,seed=17+12*r,cap_s=CAP,reported_solved=False,status='TIMEOUT') for s in sources for a in ARMS for r in range(REPEATS)]
    validate(rows,sources)
    for bad in (rows[:-1],rows+[rows[0]]):
        try:validate(bad,sources)
        except AssertionError:pass
        else:raise AssertionError('bad completeness accepted')
    rows[0].update(reported_solved=True,status='SAT_VERIFIED');rows[1].update(reported_solved=True,status='UNSAT_UNVERIFIED')
    try:validate(rows,sources)
    except AssertionError:pass
    else:raise AssertionError('contradiction accepted')
    emit('SELFTEST_PASS',dict(disjoint_selection=True,complete_pairs=120,duplicates_rejected=True,contradictions_rejected=True))
def smoke():
    B.ROOT=ROOT/'smoke';B.ROOT.mkdir(parents=True,exist_ok=True)
    p=B.ROOT/'original.cnf';p.write_text('p cnf 2 3\n1 -2 0\n-1 2 0\n1 0\n')
    c=dict(id=0,path=str(p),sha256=B.sha(p),cohort='smoke',dataset='synthetic_smoke')
    for arm in ARMS:
        r=B.trial(c,arm,'smoke',0,3.);assert r['status']=='SAT_VERIFIED',(arm,r);emit('SMOKE_PASS',dict(arm=arm,status=r['status']))
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('action',choices=['prepare','run','audit','selftest','smoke']);ap.add_argument('--shard',type=int,default=0);a=ap.parse_args()
    ROOT.mkdir(exist_ok=True)
    if a.action=='run':worker(a.shard)
    else:globals()[a.action]()
