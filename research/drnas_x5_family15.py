#!/usr/bin/env python3
"""15 untouched originals per GBD family; periodic telemetry is a separate arm."""
import argparse,collections,hashlib,json,lzma,gzip,bz2,os,random,signal,subprocess,tempfile,time,shutil
from pathlib import Path
import drnas_x5_bench as B
from drnas_x5_report import comparison
ROOT=B.ROOT
SOURCE_MANIFEST=ROOT/'experiments/drnas_x5/family15_sources.json'
ARMS=['X5_NO_MIN','CORE','Kissat','CaDiCaL','CMS','X5_DIAG']

def dump(p,data):p.write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')
def records(p):return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]

def parse_diagnostic_stderr(stderr,killed):
    """Only an unterminated final record after our SIGKILL may be incomplete.

    Complete malformed records and malformed records on normal exit stay fatal.
    Keep all prior complete progress; never manufacture or zero missing counters.
    """
    telemetry=[];stats={};extra={};truncated=[]
    lines=stderr.splitlines(keepends=True)
    prefixes=('X5_PROGRESS ','X41_STATS ','X5_STATS ')
    for index,line in enumerate(lines):
        prefix=next((p for p in prefixes if line.startswith(p)),None)
        tail=killed and index==len(lines)-1 and not line.endswith(('\n','\r'))
        if prefix:
            try:record=json.loads(line[len(prefix):])
            except json.JSONDecodeError:
                if not tail:raise
                truncated.append({'prefix':prefix.strip(),'bytes':len(line.encode()),
                    'sha256':hashlib.sha256(line.encode()).hexdigest()})
                continue
            if prefix=='X5_PROGRESS ':telemetry.append(record)
            elif prefix=='X41_STATS ':stats=record
            else:extra=record
        elif tail and line and any(p.startswith(line) for p in prefixes):
            truncated.append({'prefix':'partial_tag','bytes':len(line.encode()),
                'sha256':hashlib.sha256(line.encode()).hexdigest()})
    assert telemetry,'diagnostic solver produced no complete progress records'
    return telemetry,stats,extra,truncated

def retained_pairs(root,manifest):
    """Retain only whole six-arm (source, repetition) groups from matching inputs."""
    if root is None:return [],{}
    old=json.loads((root/'manifest.json').read_text())
    for key in ('cohort','family','count','repeats','cap','arms','shard','shards',
                'source_manifest_sha256','candidate_sha256','diagnostic_source_sha256','binary_sha256','sources'):
        assert old[key]==manifest[key],('resume identity mismatch',key)
    rr=records(root/'trials.jsonl');seen=set();groups=collections.defaultdict(list)
    source_ids={s['sha256']:s['source_id'] for s in manifest['sources']}
    for r in rr:
        key=(r['sha256'],r['rep'],r['arm'])
        assert key not in seen and r['sha256'] in source_ids and r['rep'] in (0,1) and r['arm'] in ARMS
        assert r['family']==manifest['family'] and r['shard']==manifest['shard']
        assert r['source_id']==source_ids[r['sha256']]
        assert not r['accepted'] or r['verified'] and r['e2e_s']<=manifest['cap']
        seen.add(key);groups[key[:2]].append(r)
    retained=[]
    for group in groups.values():
        if {r['arm'] for r in group}==set(ARMS):
            for r in group:
                if r['arm']=='X5_DIAG':
                    path=root/'telemetry'/f"{r['sha256']}_{r['rep']}.jsonl"
                    events=records(path)
                    assert events and events[-1]==r['last_progress'] and len(events)==r['progress_samples']
                retained.append({**r,'measurement_run_id':r.get('measurement_run_id','43390611380'),
                                 'retained_from_prior_run':True})
    return retained,{'origin_run':'43390611380','retained_trials':len(retained),
                     'retained_complete_pairs':len(retained)//len(ARMS),
                     'partial_group_trials_not_mixed':len(rr)-len(retained)}

def prepare(a):
    from remotezip import RemoteZip
    manifest=json.loads(SOURCE_MANIFEST.read_text());a.out.mkdir(parents=True,exist_ok=False)
    assert len(manifest['sources'])==75
    assert collections.Counter(s['family'] for s in manifest['sources'])=={f:15 for f in manifest['families']}
    assert len({s['isohash2'] for s in manifest['sources']})==75
    assert len({s['sha256'] for s in manifest['sources']})==75
    with RemoteZip(manifest['archive_url'],timeout=95) as z:
        for i,s in enumerate(manifest['sources']):
            data=z.read(s['archive_path'])
            assert len(data)==s['compressed_file_bytes']
            raw=lzma.decompress(data) if s['filename'].endswith('.xz') else gzip.decompress(data) if s['filename'].endswith('.gz') else bz2.decompress(data) if s['filename'].endswith('.bz2') else data
            assert hashlib.sha256(raw).hexdigest()==s['sha256'] and len(raw)==s['bytes']
            (a.out/(s['sha256']+'.cnf')).write_bytes(raw)
            B.emit('FAMILY15_DOWNLOAD',{'completed':i+1,'total':75,'family':s['family'],'bytes':len(raw)})
    dump(a.out/'source_manifest.json',manifest)

def diagnostic(source,cnf,td,a,raw_stderr_path=None):
    proof=td/'diag.drat';rss=td/'rss.txt'
    proof.unlink(missing_ok=True);rss.unlink(missing_ok=True)
    start=time.monotonic();status='TIMEOUT';verified=False;killed=False
    cmd=[str(ROOT/'build/timed'),str(rss),str(ROOT/'build/x5-telemetry'),str(cnf),
         '--mode','core','--x5-no-minimize','--stats','--time',str(a.cap),'--proof',str(proof)]
    p=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
    try:
        output,stderr=p.communicate(timeout=a.cap)
        if p.returncode not in (0,10,20):raise RuntimeError(('DIAG',p.returncode,stderr[-1500:]))
        status={0:'UNKNOWN',10:'SAT',20:'UNSAT'}[p.returncode]
    except subprocess.TimeoutExpired:
        os.killpg(p.pid,signal.SIGKILL);output,stderr=p.communicate();killed=True
    solve=time.monotonic()-start;check_start=time.monotonic()
    if status=='SAT':
        verified=B.B.verify_model_on_original_text(source,output)
        assert verified,('invalid diagnostic original witness',source['sha256'])
    elif status=='UNSAT':
        remaining=a.cap-(time.monotonic()-start)
        if remaining>0:
            try:
                q=subprocess.run([str(a.checker.resolve()),str(cnf),str(proof)],capture_output=True,text=True,timeout=remaining)
                verified='s VERIFIED' in q.stdout and (q.returncode==0 or 'c trivial UNSAT' in q.stdout)
                assert verified,('invalid diagnostic proof',source['sha256'],q.stdout[-500:])
            except subprocess.TimeoutExpired:pass
    check=time.monotonic()-check_start;total=time.monotonic()-start;accepted=verified and total<=a.cap
    # Preserve raw evidence before parsing, including a partial final write.
    # Artifact I/O stays outside the already captured E2E solver/check budget.
    if raw_stderr_path is not None:raw_stderr_path.write_text(stderr)
    telemetry,stats,extra,truncated=parse_diagnostic_stderr(stderr,killed)
    for left,right in zip(telemetry,telemetry[1:]):
        assert right['elapsed_s']>=left['elapsed_s']
        assert right['conflicts']>=left['conflicts'] and right['propagations']>=left['propagations']
    last=telemetry[-1]
    r={'arm':'X5_DIAG','status':status,'verified':verified,'accepted':accepted,
       'PAR2':total if accepted else 2*a.cap,'e2e_s':total,'solve_s':solve,'check_s':check,
       'maxrss_kib':last['maxrss_kib'],'conflicts':stats.get('conflicts',last['conflicts']),
       'decisions':stats.get('decisions',last['decisions']),'x5':extra,'killed_by_budget':killed,
       'progress_samples':len(telemetry),'last_progress':last,'partial_counters':killed,
       'diagnostic_timing_only':True,'truncated_tail_records':truncated}
    return r,telemetry

def bench(a):
    manifest=json.loads(SOURCE_MANIFEST.read_text());family=manifest['families'][a.shard]
    cases=[s for s in manifest['sources'] if s['family']==family];assert len(cases)==15
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    a.out.mkdir(parents=True,exist_ok=False);(a.out/'telemetry').mkdir();(a.out/'raw_stderr').mkdir()
    for s in cases:
        cnf=a.sources/(s['sha256']+'.cnf');assert B.sha(cnf)==s['sha256']
    m={'cohort':'original_SAT2024_retrospective','family':family,'count':15,'repeats':2,'cap':a.cap,
       'arms':ARMS,'shard':a.shard,'shards':5,'logical_cpus':list(os.sched_getaffinity(0)),
       'source_manifest_sha256':B.sha(SOURCE_MANIFEST),'candidate_sha256':B.sha(ROOT/'src/drnas_x5.cpp'),
       'diagnostic_source_sha256':B.sha(ROOT/'build/x5-telemetry.cpp'),
       'binary_sha256':{name:B.sha(ROOT/'build'/name) for name in ('drnas-x5','x5-telemetry','frozen-proof','kissat','cadical','cms','drat-trim','frat-rs')},
       'sources':cases,'no_learning':True,'cache':False,
       'telemetry':'Separate diagnostic arm; uninstrumented X5_NO_MIN remains the performance candidate. Flush every ~1 s at safe observation points and at search start/finish.'}
    resume_root=getattr(a,'resume_root',None)
    rows,resume=retained_pairs(resume_root,m)
    done={(r['sha256'],r['rep']) for r in rows}
    m['resume']=resume;m['stderr_parser_version']='strict-killed-final-tail-v2'
    dump(a.out/'manifest.json',m)
    if resume_root:
        for r in rows:
            if r['arm']=='X5_DIAG':
                name=f"{r['sha256']}_{r['rep']}.jsonl"
                shutil.copy2(resume_root/'telemetry'/name,a.out/'telemetry'/name)
    B.emit('FAMILY15_RESUME',{'family':family,**resume,'new_trials':180-len(rows)})
    with tempfile.TemporaryDirectory() as tmp,(a.out/'trials.jsonl').open('w') as log:
        for r in rows:log.write(json.dumps(r,sort_keys=True)+'\n')
        log.flush()
        for i,s in enumerate(cases):
            cnf=(a.sources/(s['sha256']+'.cnf')).resolve()
            source={**s,'content':cnf.read_text(),'cert':'ORIGINAL_PROOF_REQUIRED'}
            for rep in range(2):
                if (s['sha256'],rep) in done:continue
                order=ARMS.copy();random.Random(151113+s['source_id']*31+rep).shuffle(order)
                for arm in order:
                    if arm=='X5_DIAG':
                        r,telemetry=diagnostic(source,cnf,Path(tmp),a,
                            a.out/'raw_stderr'/f"{s['sha256']}_{rep}.txt")
                        path=a.out/'telemetry'/f"{s['sha256']}_{rep}.jsonl"
                        path.write_text(''.join(json.dumps(t,sort_keys=True)+'\n' for t in telemetry))
                    else:r=B.run(arm,source,cnf,Path(tmp),a)
                    r.update(sha256=s['sha256'],family=family,rep=rep,source_id=s['source_id'],shard=a.shard,
                             measurement_run_id=os.getenv('GITHUB_RUN_ID','local'),retained_from_prior_run=False)
                    rows.append(r);log.write(json.dumps(r,sort_keys=True)+'\n');log.flush();B.emit('FAMILY15_TRIAL',r)
            B.emit('FAMILY15_PROGRESS',{'family':family,'completed':i+1,'sources':15,'totals':B.summarize(rows,ARMS)})
    report={'family':family,'sources':15,'trials':len(rows),'totals':B.summarize(rows,ARMS)}
    dump(a.out/'report.json',report);B.emit('FAMILY15_FINAL',report)

def report(a):
    rows=[];mm=[]
    for p in a.root.rglob('manifest.json'):
        m=json.loads(p.read_text());rr=records(p.with_name('trials.jsonl'))
        assert m['count']==15 and m['repeats']==2 and m['arms']==ARMS and len(m['logical_cpus'])==1
        expected={(s['sha256'],rep,arm) for s in m['sources'] for rep in range(2) for arm in ARMS}
        assert len(rr)==180 and len(expected)==180 and {(r['sha256'],r['rep'],r['arm']) for r in rr}==expected
        assert all(not r['accepted'] or r['verified'] and r['e2e_s']<=m['cap'] for r in rr)
        rows+=rr;mm.append(m)
    assert len(rows)==900 and len(mm)==5 and len({r['sha256'] for r in rows})==75
    assert sorted(m['shard'] for m in mm)==list(range(5))
    for key in ('source_manifest_sha256','candidate_sha256','diagnostic_source_sha256','cap'):
        assert len({m[key] for m in mm})==1,key
    assert len({json.dumps(m['binary_sha256'],sort_keys=True) for m in mm})==1,'binary identity differs across runners'
    def section(rr):
        diag=[r['last_progress'] for r in rr if r['arm']=='X5_DIAG']
        totals={key:sum(t[key] for t in diag) for key in ('elapsed_s','parse_s','bcp_s','analysis_s','select_s','reduce_s','conflicts','propagations','restarts')}
        return {'totals':B.summarize(rr,ARMS),
                'comparisons_vs_X5_NO_MIN':{arm:comparison(rr,arm,'X5_NO_MIN') for arm in ARMS if arm!='X5_NO_MIN'},
                'diagnostic_partial_totals':totals,
                'telemetry_trials':len(diag),'telemetry_timeouts':sum(r.get('killed_by_budget',False) for r in rr)}
    result={'sources':75,'per_family':15,'trials':900,'cap_s':mm[0]['cap'],
       'overall':section(rows),'retained_trials':sum(r.get('retained_from_prior_run',False) for r in rows),
       'truncated_tail_records':sum(len(r.get('truncated_tail_records',[])) for r in rows),
       'by_family':{f:section([r for r in rows if r['family']==f]) for f in sorted({r['family'] for r in rows})},
       'limits':['Official original inputs, retrospective evaluation; not a new globally blind holdout.',
                 'Selection by source family and compressed file size only; no solved-outcome screening.',
                 'Diagnostic per-function clocks add overhead; X5_DIAG is not a speed candidate.',
                 'Timeout counters are last flushed observations, not zero and not final full-budget counts.',
                 'A periodic sample may be delayed by a long operation; sampling gap is visible in the retained JSONL.',
                 'After a watchdog kill only an incomplete final stderr JSON record may be skipped; complete earlier samples and raw stderr are retained.',
                 'Resume retains complete six-arm pairs on matching binaries/inputs; incomplete pairs are rerun together on one runner.',
                 'No global learning, cache, tuning, promotion or merge in this diagnostic cycle.']}
    dump(a.out,result);B.emit('FAMILY15_REPORT',result)

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='cmd',required=True)
    q=sub.add_parser('prepare');q.add_argument('--out',type=Path,required=True)
    q=sub.add_parser('bench');q.add_argument('--out',type=Path,required=True);q.add_argument('--sources',type=Path,required=True)
    q.add_argument('--resume-root',type=Path)
    q.add_argument('--shard',type=int,required=True);q.add_argument('--cap',type=float,default=15)
    q.add_argument('--checker',type=Path,default=ROOT/'build/drat-trim');q.add_argument('--frat',type=Path,default=ROOT/'build/frat-rs')
    q.add_argument('--kissat',default='build/kissat');q.add_argument('--cadical',default='build/cadical');q.add_argument('--cms',default='build/cms')
    q=sub.add_parser('report');q.add_argument('--root',type=Path,required=True);q.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.cmd=='bench':assert 0<=a.shard<5 and a.cap>0
    {'prepare':prepare,'bench':bench,'report':report}[a.cmd](a)
if __name__=='__main__':main()
