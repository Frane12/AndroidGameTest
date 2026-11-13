#!/usr/bin/env python3
"""Frozen X5_NO_MIN: global policy x exact-result SQLite cache factorial.

Cold and warm passes are NEVER pooled for claims about new-formula solving.
Global policy is an experimental X46 transfer, not a trained X5 champion.
"""
import argparse, collections, gzip, hashlib, json, os, random, signal
import sqlite3, subprocess, tempfile, time
from pathlib import Path
import drnas_x5_bench as B
import drnas_x5_diverse72 as D
from drnas_x5_report import comparison

MODEL_SHA = '6211674987f4810edc68c040ef3672e161185b9727801662f0f4eff91c8ed406'
STORE_COMMIT = 'b1e738d9ff5eacd6a1e1dac57957afc6ee4ba746'
ARMS = ['BASE', 'GLOBAL', 'CACHE', 'GLOBAL_CACHE', 'PROBE', 'CORE', 'Kissat', 'CaDiCaL', 'CMS']
CACHE_LIMIT = 64 * 1024 * 1024
ENTRY_LIMIT = 8 * 1024 * 1024

def digest(b): return hashlib.sha256(b).hexdigest()
def dump(p, obj): p.write_text(json.dumps(obj, indent=2, sort_keys=True)+'\n')

def export_global(store, output):
    start = time.monotonic()
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)/'global.sqlite'
        p.write_bytes(gzip.decompress(store.read_bytes()))
        db = sqlite3.connect(f'file:{p}?mode=ro', uri=True)
        assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        row = db.execute('SELECT frozen_text,model_version,evaluation_status,provenance_json FROM x46_frozen_cost_models WHERE model_sha=?', (MODEL_SHA,)).fetchone()
        assert row and row[1] == 'X46COST1'
        data = row[0].encode('ascii')
        assert digest(data) == MODEL_SHA and data.startswith(b'X46COST1 12\n')
        protected = set()
        for table in ('x46_training_events', 'x46_validation_sources'):
            protected.update(x[0] for x in db.execute('SELECT DISTINCT source_sha FROM '+table))
        db.close()
    output.write_bytes(data)
    return protected, {'model_sha256': MODEL_SHA, 'store_commit': STORE_COMMIT,
        'snapshot_sha256': B.sha(store), 'evaluation_status': row[2],
        'experimental_transfer_to_X5': True, 'provenance': json.loads(row[3]),
        'export_setup_s': time.monotonic()-start,
        'setup_timing': 'one-time gzip/SQLite export excluded from each solve; native model parsing included'}

class ResultCache:
    def __init__(self, path):
        self.path = path
        self.db = sqlite3.connect(path)
        self.db.execute('CREATE TABLE IF NOT EXISTS results (key TEXT PRIMARY KEY, status TEXT, output TEXT, proof BLOB, payload_sha TEXT, size INTEGER)')
        self.db.commit()
    def get(self, key):
        row = self.db.execute('SELECT status,output,proof,payload_sha FROM results WHERE key=?', (key,)).fetchone()
        if row:
            status, output, proof, checksum = row
            assert digest(status.encode()+output.encode()+proof) == checksum, 'corrupt cached certificate'
            return status, output, proof
    def put(self, key, status, output, proof):
        size = len(output.encode()) + len(proof)
        if size > ENTRY_LIMIT: return False
        used = self.db.execute('SELECT COALESCE(SUM(size),0) FROM results').fetchone()[0]
        if used + size > CACHE_LIMIT: return False
        self.db.execute('INSERT OR REPLACE INTO results VALUES(?,?,?,?,?,?)',
            (key,status,output,proof,digest(status.encode()+output.encode()+proof),size))
        self.db.commit()
        return True
    def close(self): self.db.close()

def run(arm, source, cnf, td, a, cache=None):
    start = time.monotonic()
    source_sha = digest(cnf.read_bytes())
    assert source_sha == source['sha256']
    if arm in ('CORE','Kissat','CaDiCaL','CMS'):
        r = B.run(arm,source,cnf,td,a)
        total = time.monotonic()-start
        r.update(e2e_s=total, accepted=r['accepted'] and total<=a.cap,
                 cache_hit=False, cache_stored=False, probe={})
        r['PAR2'] = total if r['accepted'] else 2*a.cap
        return r
    global_on = arm in ('GLOBAL','GLOBAL_CACHE')
    probe_on = global_on or arm == 'PROBE'
    policy = {'source':source_sha,'binary':a.binary_sha,'model':a.model_sha if global_on else None,
              'no_minimize':True,'probe':probe_on,'branch_at':4,'probe_conflicts':8,'probe_ms':2.5,
              'schema':'X5-CERT-CACHE-1'}
    key = digest(json.dumps(policy,sort_keys=True).encode())
    proof = td/'proof.drat'; rss = td/'rss.txt'
    proof.unlink(missing_ok=True); rss.unlink(missing_ok=True)
    hit = cache.get(key) if cache else None
    output=''; stderr=''; status='TIMEOUT'; verified=False; stored=False
    if hit:
        status, output, data = hit
        proof.write_bytes(data)
    else:
        remaining = a.cap-(time.monotonic()-start)
        cmd=[str(B.ROOT/'build/drnas-x5'),str(cnf),'--mode','core','--stats',
             '--time',str(max(.001,remaining)),'--proof',str(proof),'--x5-no-minimize']
        if probe_on: cmd += ['--branch-at','4','--x46-conflicts','8','--x46-probe-ms','2.5']
        if global_on: cmd += ['--x46-model',str(a.model.resolve())]
        if remaining > 0:
            p=subprocess.Popen([str(B.ROOT/'build/timed'),str(rss),*cmd],stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE,text=True,start_new_session=True)
            try:
                output,stderr=p.communicate(timeout=max(.001,a.cap-(time.monotonic()-start)))
                if p.returncode not in (0,10,20): raise RuntimeError((arm,p.returncode,stderr[-1500:]))
                status={0:'UNKNOWN',10:'SAT',20:'UNSAT'}[p.returncode]
            except subprocess.TimeoutExpired:
                os.killpg(p.pid,signal.SIGKILL); output,stderr=p.communicate()
    solve=time.monotonic()-start; check_start=time.monotonic()
    if status in ('SAT','UNSAT') and source.get('expected_status'):
        assert status == source['expected_status'], ('incorrect answer',arm,source_sha)
    if status == 'SAT':
        verified=B.B.verify_model_on_original_text(source,output)
        assert verified, ('invalid original witness',arm,source_sha)
    elif status == 'UNSAT':
        remaining=a.cap-(time.monotonic()-start)
        if remaining>0:
            try:
                q=subprocess.run([str(a.checker.resolve()),str(cnf),str(proof)],
                                 capture_output=True,text=True,timeout=remaining)
                verified='s VERIFIED' in q.stdout and (q.returncode==0 or 'c trivial UNSAT' in q.stdout)
                assert verified, ('invalid independent DRAT certificate',arm,source_sha,q.stdout[-500:])
            except subprocess.TimeoutExpired: pass
    check=time.monotonic()-check_start
    if cache and not hit and verified and time.monotonic()-start <= a.cap:
        # Storage cost is included; only verified certificates, never UNKNOWN.
        if proof.stat().st_size <= ENTRY_LIMIT:
            stored=cache.put(key,status,output,proof.read_bytes())
    stats={}; extra={}; probe={}
    for line in stderr.splitlines():
        if line.startswith('X41_STATS '): stats=json.loads(line[10:])
        if line.startswith('X5_STATS '): extra=json.loads(line[9:])
        if line.startswith('X46_PROBE '): probe=json.loads(line[10:])
    if global_on and not hit and probe:
        assert probe['learned_model'], 'global model was not loaded by native solver'
    peak=None
    if rss.exists():
        try: peak=int(rss.read_text().splitlines()[-1])
        except (ValueError,IndexError): pass
    total=time.monotonic()-start
    accepted=verified and total<=a.cap
    return {'arm':arm,'status':status,'verified':verified,'accepted':accepted,
            'PAR2':total if accepted else 2*a.cap,'e2e_s':total,'solve_s':solve,'check_s':check,
            'maxrss_kib':peak,'conflicts':stats.get('conflicts'),'decisions':stats.get('decisions'),
            'x5':extra,'probe':probe,'cache_hit':bool(hit),'cache_stored':stored}

def summaries(rows, arms):
    totals=B.summarize(rows,arms)
    for arm,t in totals.items():
        rr=[r for r in rows if r['arm']==arm]
        t.update(cache_hits=sum(r['cache_hit'] for r in rr),cache_stores=sum(r['cache_stored'] for r in rr),
                 model_loads=sum(r['probe'].get('learned_model',False) for r in rr),
                 probe_triggers=sum(r['probe'].get('triggered',False) for r in rr),
                 recommended_flips=sum(r['probe'].get('recommend_flip',False) for r in rr))
    return totals

def benchmark(a):
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    a.out.mkdir(parents=True,exist_ok=False)
    a.model=a.out/'global_model.txt'
    protected, global_info=export_global(a.store,a.model)
    a.model_sha=B.sha(a.model); a.binary_sha=B.sha(B.ROOT/'build/drnas-x5')
    arms=a.arms.split(','); assert set(arms)<=set(ARMS)
    if a.official:
        from drnas_x47_official_dedup import official_sources
        cases=official_sources(12)
    else:
        # Eight fresh formulas per category, medium/larger sizes only.
        cases=[D.source(f,a.offset+3*(i//2)+1+i%2) for f in D.FAMILIES for i in range(a.per_family)]
    assert len({s['sha256'] for s in cases})==len(cases)
    assert not protected & {s['sha256'] for s in cases}, 'test overlaps global training/validation'
    total=len(cases); random.Random(a.offset).shuffle(cases); cases=cases[a.shard::a.shards]
    for s in cases: s.setdefault('level','official')
    manifest={'cohort':'official_retrospective' if a.official else 'synthetic',
        'count':len(cases),'total_count':total,'cap':a.cap,'repeats':2,'arms':arms,
        'shard':a.shard,'shards':a.shards,'logical_cpus':list(os.sched_getaffinity(0)),
        'source_offset':a.offset,'candidate_sha256':B.sha(B.ROOT/'src/drnas_x5.cpp'),
        'binary_sha256':a.binary_sha,'model_sha256':a.model_sha,'checker_sha256':B.sha(a.checker),
        'global_memory':global_info,'global_train_validation_overlap':0,
        'cache_definition':'exact original CNF SHA + solver/policy identity; verified witness/DRAT; no cross-formula clause transfer',
        'cache_limit_bytes_per_arm':CACHE_LIMIT,'cache_entry_limit_bytes':ENTRY_LIMIT,
        'rss_scope':'solver child only; persistent cache disk size reported separately',
        'sources':[{k:v for k,v in s.items() if k not in ('content','clauses')} for s in cases]}
    dump(a.out/'manifest.json',manifest)
    caches={arm:ResultCache(a.out/(arm+'.sqlite')) for arm in arms if arm in ('CACHE','GLOBAL_CACHE')}
    rows=[]
    (a.out/'sources').mkdir()
    for s in cases: (a.out/'sources'/(s['sha256']+'.cnf')).write_text(s['content'])
    with tempfile.TemporaryDirectory() as tmp,(a.out/'trials.jsonl').open('w') as log:
        for rep in range(2):
            # Complete cold pass before replay. Close/reopen SQLite to test persistence.
            if rep:
                for arm,c in list(caches.items()):
                    path=c.path; c.close(); caches[arm]=ResultCache(path)
            for i,s in enumerate(cases):
                cnf=(a.out/'sources'/(s['sha256']+'.cnf')).resolve()
                order=list(arms); random.Random(a.offset+i*31+rep).shuffle(order)
                for arm in order:
                    r=run(arm,s,cnf,Path(tmp),a,caches.get(arm))
                    if rep==0: assert not r['cache_hit']
                    r.update(sha256=s['sha256'],family=s['family'],level=s['level'],rep=rep,
                             phase='cold' if rep==0 else 'warm_replay',shard=a.shard)
                    rows.append(r); log.write(json.dumps(r,sort_keys=True)+'\n');log.flush()
                    B.emit('X5_MEMORY_TRIAL',r)
                B.emit('X5_MEMORY_PROGRESS',{'phase':rep,'completed':i+1,'sources':len(cases),'shard':a.shard})
    for c in caches.values(): c.close()
    assert B.sha(a.model)==a.model_sha
    dump(a.out/'cache_sizes.json',{arm:c.path.stat().st_size for arm,c in caches.items()})
    result={phase:summaries([r for r in rows if r['phase']==phase],arms) for phase in ('cold','warm_replay')}
    dump(a.out/'report.json',result); B.emit('X5_MEMORY_FINAL',result)

def report(a):
    groups=collections.defaultdict(list); manifests=collections.defaultdict(list)
    for f in a.root.rglob('manifest.json'):
        m=json.loads(f.read_text()); rows=[json.loads(x) for x in f.with_name('trials.jsonl').read_text().splitlines()]
        expected={(s['sha256'],rep,arm) for s in m['sources'] for rep in range(2) for arm in m['arms']}
        assert len(rows)==len(expected) and {(r['sha256'],r['rep'],r['arm']) for r in rows}==expected
        assert len(m['logical_cpus'])==1 and m['global_train_validation_overlap']==0
        assert all(not r['accepted'] or r['verified'] and r['e2e_s']<=m['cap'] for r in rows)
        assert all(not r['cache_hit'] for r in rows if r['rep']==0)
        groups[m['cohort']]+=rows; manifests[m['cohort']].append(m)
    result={}
    for cohort,count in [('synthetic',96),('official_retrospective',12)]:
        rows=groups[cohort]; mm=manifests[cohort]
        assert len({r['sha256'] for r in rows})==count
        assert len({(r['sha256'],r['rep'],r['arm']) for r in rows})==len(rows)
        assert sorted(m['shard'] for m in mm)==[0,1,2]
        for key in ('candidate_sha256','binary_sha256','model_sha256','checker_sha256','cap','total_count'):
            assert len({m[key] for m in mm})==1,key
        assert all(m['arms']==ARMS for m in mm)
        phases={}
        for phase in ('cold','warm_replay'):
            rr=[r for r in rows if r['phase']==phase]
            phases[phase]={'totals':summaries(rr,ARMS),
                'comparisons_vs_BASE':{arm:comparison(rr,arm,'BASE') for arm in ARMS if arm!='BASE'},
                'global_vs_same_probe':comparison(rr,'GLOBAL','PROBE'),
                'cache_with_global_vs_global':comparison(rr,'GLOBAL_CACHE','GLOBAL'),
                'global_with_cache_vs_cache':comparison(rr,'GLOBAL_CACHE','CACHE'),
                'by_family':{f:summaries([r for r in rr if r['family']==f],ARMS) for f in sorted({r['family'] for r in rr})}}
        result[cohort]={'sources':count,'phases':phases}
    result['limits']=['No model training or automatic promotion in this experiment.',
        'Global model transferred from X46, previously rejected there; experimental only.',
        'Warm result-cache gains apply only to identical CNF replay, not generalization.',
        'Original SAT2024 cohort is retrospective. Synthetic families share templates.',
        'PAR2 includes source hashing, cache I/O, model loading, solve and certificate verification; one-time SQLite export reported separately.',
        'One cold and one warm observation per source/arm; bootstrap clusters source SHA, not repeated independent sources.']
    dump(a.out,result)
    for cohort in ('synthetic','official_retrospective'):
        for phase, rr in result[cohort]['phases'].items():
            B.emit('X5_MEMORY_AB_SUMMARY',{'cohort':cohort,'phase':phase,'totals':rr['totals'],
                'comparisons_vs_BASE':rr['comparisons_vs_BASE'],'global_vs_same_probe':rr['global_vs_same_probe']})

def main():
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='cmd',required=True)
    b=sub.add_parser('bench'); b.add_argument('--out',type=Path,required=True)
    b.add_argument('--store',type=Path,required=True); b.add_argument('--official',action='store_true')
    b.add_argument('--cap',type=float,default=5); b.add_argument('--offset',type=int,default=14700000)
    b.add_argument('--per-family',type=int,default=8); b.add_argument('--shard',type=int,default=0); b.add_argument('--shards',type=int,default=3)
    b.add_argument('--arms',default=','.join(ARMS))
    b.add_argument('--checker',type=Path,default=B.ROOT/'build/drat-trim'); b.add_argument('--frat',type=Path,default=B.ROOT/'build/frat-rs')
    b.add_argument('--kissat',default='build/kissat'); b.add_argument('--cadical',default='build/cadical'); b.add_argument('--cms',default='build/cms')
    r=sub.add_parser('report'); r.add_argument('--root',type=Path,required=True); r.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.cmd=='bench':
        assert a.cap>0 and 0<=a.shard<a.shards and a.offset%3==0
        benchmark(a)
    else: report(a)
if __name__=='__main__': main()
