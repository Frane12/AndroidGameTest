#!/usr/bin/env python3
"""Frozen transferred memory on 12 original SAT2024 CNFs, six serial arms."""
import argparse,bz2,collections,gzip,hashlib,json,lzma,os,pathlib,random,re,statistics,time
from drnas_r28_context_memory import Memory,solve,file_sha
import drnas_r28_native_benchmark as references
ROOT=pathlib.Path('r153_real_context')
ARMS=('NATIVE_DIRECT','CONTEXT_COLD','CONTEXT_MEMORY','Kissat','CaDiCaL','CryptoMiniSat')
REFS=ARMS[3:];CAP=5.;REPEATS=2

def emit(tag,x):print(tag,json.dumps(x,sort_keys=True),flush=True)
def decode(name,data):
    limit=24_000_000
    if name.endswith('.xz'):decoder=lzma.LZMADecompressor()
    elif name.endswith('.bz2'):decoder=bz2.BZ2Decompressor()
    elif name.endswith('.gz'):
        import zlib
        decoder=zlib.decompressobj(16+zlib.MAX_WBITS)
    else:
        if len(data)>limit:raise ValueError('oversized original CNF')
        return data
    result=decoder.decompress(data,limit+1)
    if len(result)>limit or not decoder.eof:raise ValueError('oversized/truncated compressed original CNF')
    return result

def collect(fixtures):
    from remotezip import RemoteZip
    manifests=[json.loads(p.read_text()) for p in fixtures.rglob('manifest.json')]
    manifests=[m for m in manifests if m.get('original_CNF') and len(m.get('sources',[]))==24]
    assert len(manifests)==1,'missing unique frozen MATH14 real24 manifest'
    parent=manifests[0];pool=sorted(parent['sources'],key=lambda x:(x['compressed_bytes'],x['source_file']))
    chosen=pool[::2];assert len(chosen)==12
    out=[];(ROOT/'cases').mkdir(parents=True,exist_ok=True)
    with RemoteZip(parent['archive'],timeout=90) as archive:
        for i,item in enumerate(chosen):
            raw=decode(item['source_file'],archive.read(item['source_file']))
            sha=hashlib.sha256(raw).hexdigest();assert sha==item['sha256'],'original source SHA mismatch'
            match=re.search(rb'(?m)^p\s+cnf\s+(\d+)\s+(\d+)\s*$',raw);assert match,'DIMACS header missing'
            p=ROOT/'cases'/f'{i:02d}_{sha[:16]}.cnf';p.write_bytes(raw)
            source=dict(item,id=i,parent_id=item['id'],path=str(p),split='evaluation',dataset='official_SAT2024',cohort=item['family'],variables=int(match[1]),clauses=int(match[2]))
            out.append(source);emit('R153_REAL_SOURCE',source)
    assert len({s['sha256'] for s in out})==12 and len({s['family'] for s in out})==12
    manifest=dict(archive=parent['archive'],parent_run=43161813420,original_CNF=True,potentially_seen=True,blind=False,selection='every other compressed-size-sorted source in frozen real24 manifest; no outcome selection',cap_s=CAP,repetitions=REPEATS,sources=out)
    (ROOT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return out

def summarize(rows,complete=False):
    def aggregate(rs):
        out={}
        for arm in ARMS:
            subset=[r for r in rs if r['arm']==arm]
            out[arm]=dict(trials=len(subset),verified=sum(r['verified'] for r in subset),reported_solved=sum(r['reported_solved'] for r in subset),SAT_verified=sum(r['status']=='SAT_VERIFIED' for r in subset),UNSAT_math_verified=sum(r['status'] in ('UNSAT_GF2_VERIFIED','UNSAT_PHP_VERIFIED') for r in subset),UNSAT_unverified=sum(r['status']=='UNSAT_UNVERIFIED' for r in subset),timeouts=sum(r['status'] in ('TIMEOUT','UNKNOWN') for r in subset),PAR2_verified_s=sum(r['PAR2_verified_s'] for r in subset),PAR2_reported_s=sum(r['PAR2_reported_s'] for r in subset),e2e_s=sum(r['e2e_s'] for r in subset),memory_prepare_s=sum(r.get('prepare_s',0) for r in subset),prior_loaded_attempts=sum(r.get('prior_weight',0)>0 for r in subset),learning_window_attempts=sum(r.get('learning_windows_logged',0)>0 for r in subset))
        return out
    totals=aggregate(rows);shards={str(i):aggregate([r for r in rows if r['shard']==i]) for i in range(3)}
    warm=totals['CONTEXT_MEMORY'];paired=collections.defaultdict(dict)
    for row in rows:paired[(row['sha256'],row['rep'])][row['arm']]=row
    regressions=[];gains=[]
    for pair in paired.values():
        a=pair.get('CONTEXT_MEMORY')
        if not a:continue
        for ref in ARMS:
            b=pair.get(ref)
            if not b or ref=='CONTEXT_MEMORY':continue
            if b['verified'] and (not a['verified'] or a['e2e_s']>b['e2e_s']/0.7):regressions.append(dict(id=a['id'],family=a['family'],rep=a['rep'],reference=ref,candidate_status=a['status'],candidate_s=a['e2e_s'],reference_s=b['e2e_s']))
            if a['verified'] and (b['verified'] or b['status']=='TIMEOUT'):
                gains.append(dict(id=a['id'],family=a['family'],rep=a['rep'],reference=ref,ratio=(b['e2e_s'] if b['verified'] else CAP)/a['e2e_s'],kind='measured' if b['verified'] else 'timeout_lower_bound'))
    ratios={metric:{arm:(totals[arm][metric]/warm[metric] if warm[metric]>0 else None) for arm in ARMS if arm!='CONTEXT_MEMORY'} for metric in ('PAR2_verified_s','PAR2_reported_s')}
    report=dict(complete=complete,original_official_CNF=True,possibly_seen=True,blind=False,one_logical_cpu=True,cap_s=CAP,repetitions=REPEATS,trials=len(rows),totals=totals,shards=shards,ratio_reference_over_memory=ratios,regressions=regressions,gains=sorted(gains,key=lambda g:g['ratio'],reverse=True)[:20],promotion=False,verification='SAT original witness; GF2/PHP independent source certificates; generic UNSAT remains unverified. Proof coverage is not search speed.')
    (ROOT/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    return report

def check_claims(rows):
    by_sha=collections.defaultdict(set)
    for r in rows:
        if r['status'].startswith('SAT_'):by_sha[r['sha256']].add('SAT')
        if r['status'].startswith('UNSAT_'):by_sha[r['sha256']].add('UNSAT')
    assert all(len(v)<=1 for v in by_sha.values()),'contradictory solver claims'

def run(sources,memory):
    before=memory.info();digest=memory.digest()
    # Registration is outside timed trials, as are frozen source integrity checks.
    for c in sources:
        assert file_sha(c['path'])==c['sha256'];memory.register(c['sha256'],'eval')
    memory.snapshot();rows=[]
    emit('R153_REAL_START',dict(memory=before,arms=ARMS,sources=len(sources),cap_s=CAP,repeats=REPEATS,one_CPU=True,no_training=True))
    with (ROOT/'results.jsonl').open('w') as f:
        for c in sources:
            for rep in range(REPEATS):
                order=list(ARMS);random.Random(c['sha256']+str(rep)).shuffle(order)
                for arm in order:
                    if arm in REFS:
                        row=references.trial(c,arm,'official12',rep,CAP)
                    else:
                        binary='mre_r28_native/drnas_r28_native' if arm=='NATIVE_DIRECT' else 'mre_r28_context/drnas_r28_context'
                        row,out=solve(memory,c['path'],'eval',CAP,17+rep*12,arm=='CONTEXT_MEMORY',binary)
                        weights=[int(v) for v in re.findall(r'R28_CONTEXT_LOAD[^\n]*prior_weight=(\d+)',out)]
                        row.update(prior_weight=sum(weights),learning_windows_logged=out.count('c LTM13_WINDOW'),route='exact_gf2' if 'route=exact_gf2' in out else 'native_learning')
                        if row['answer_verified']:
                            proof=ROOT/'certificates'/f'{c["id"]:02d}-{arm}-{rep}.txt';proof.parent.mkdir(exist_ok=True);proof.write_text(out)
                    row.update(id=c['id'],sha256=c['sha256'],family=c['family'],arm=arm,rep=rep,shard=c['id']//4)
                    rows.append(row);f.write(json.dumps(row)+'\n');f.flush();emit('R153_REAL_TRIAL',row)
            check_claims(rows);report=summarize(rows);emit('R153_REAL_PROGRESS',dict(sources_completed=c['id']+1,totals=report['totals']))
    assert memory.digest()==digest,'evaluation changed learned statistics'
    report=summarize(rows,True);report['memory_before']=before;report['memory_after']=memory.info();report['memory_frozen']=True
    (ROOT/'report.json').write_text(json.dumps(report,indent=2)+'\n');emit('R153_REAL_FINAL',report)
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a') as f:
            f.write('## R153/R160 memory on 12 original SAT2024 formulas\n\nFrozen prior; 2 repeats; 5s; one logical CPU. Previously used dataset, not a blind benchmark.\n\n| Arm | Verified | Reported | PAR2 verified s | PAR2 reported s | Loaded priors |\n|---|---:|---:|---:|---:|---:|\n')
            for arm,s in report['totals'].items():f.write(f"|{arm}|{s['verified']}/{s['trials']}|{s['reported_solved']}|{s['PAR2_verified_s']:.4f}|{s['PAR2_reported_s']:.4f}|{s['prior_loaded_attempts']}|\n")
            f.write('\nMissing generic UNSAT certificates affect verified PAR2. No automatic promotion.\n')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--fixtures',type=pathlib.Path,default=pathlib.Path('real24_source'));ap.add_argument('--db',default='drnas_memory/memory.sqlite');ap.add_argument('--smoke',action='store_true');a=ap.parse_args()
    ROOT.mkdir(exist_ok=True);os.sched_setaffinity(0,{min(os.sched_getaffinity(0))});references.ROOT=ROOT
    memory=Memory(a.db)
    try:
        if a.smoke:
            p=ROOT/'smoke.cnf';p.write_text('p cnf 3 3\n1 2 0\n-2 3 0\n-3 0\n')
            c=dict(id=0,path=str(p),sha256=file_sha(p),family='smoke',cohort='smoke',dataset='synthetic_smoke')
            for arm in ARMS:
                if arm in REFS:r=references.trial(c,arm,'smoke',0,3.)
                else:r,_=solve(memory,p,'eval',3.,17,arm=='CONTEXT_MEMORY','mre_r28_native/drnas_r28_native' if arm=='NATIVE_DIRECT' else 'mre_r28_context/drnas_r28_context')
                assert r['status']=='SAT_VERIFIED',(arm,r);emit('R153_REAL_SMOKE_PASS',dict(arm=arm,status=r['status']))
        else:run(collect(a.fixtures),memory)
    finally:memory.close()
if __name__=='__main__':main()
