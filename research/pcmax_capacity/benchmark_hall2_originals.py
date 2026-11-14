#!/usr/bin/env python3
"""Source-pinned original SAT2024 PCMAX: optional HALL1 vs experimental HALL2."""
import hashlib,json,os,pathlib,subprocess,sys,time
ROOT=pathlib.Path(__file__).resolve().parents[2]
BASE=ROOT/'results/hall2-originals'
BASE.mkdir(parents=True,exist_ok=False)
os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
assert len(os.sched_getaffinity(0))==1
manifest=json.loads((ROOT/'pcmax20/report.json').read_text())['results']
fresh=json.loads((ROOT/'pcmax-unseen3-results/source_manifest.json').read_text())
sources=[]
for r in manifest:
    if r['status']!='OK':continue
    p=ROOT/'pcmax20'/pathlib.Path(r['path']).name
    sources.append((p,r['sha256']))
for r in fresh:
    p=ROOT/r['path']
    sources.append((p,r['sha256']))
assert len(sources)>=18
records=[];seen=set()
binary=ROOT/'build/drnas-pcmax'
checker=ROOT/'research/pcmax_capacity/check_clause_hall.py'
for path,sha in sources:
    assert path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest()==sha
    assert sha not in seen
    seen.add(sha)
for rep in range(2):
    order=sources if rep==0 else list(reversed(sources))
    for path,sha in order:
        label='UNSAT' if '-UNSAT.' in path.name else 'SAT' if '-SAT.' in path.name else 'UNKNOWN'
        for arm,flag in ([('HALL1','--pcmax-clause-guard'),('HALL2','--pcmax-hall2')] if rep==0
                         else [('HALL2','--pcmax-hall2'),('HALL1','--pcmax-clause-guard')]):
            cert=BASE/(f'{path.stem}-{arm}-r{rep}.json')
            cmd=[str(binary),str(path),'--mode','core','--time','3',flag,'--pcmax-only',
                 '--pcmax-budget-ms','500','--pcmax-certificate',str(cert)]
            start=time.perf_counter()
            p=subprocess.run(cmd,capture_output=True,text=True,timeout=8)
            wall=time.perf_counter()-start
            tele=[json.loads(x[len('c PCMAX_CAPACITY '):])
                  for x in p.stdout.splitlines() if x.startswith('c PCMAX_CAPACITY ')]
            t=tele[-1] if tele else {}
            verified=False;check_s=0
            if p.returncode==20:
                assert cert.is_file(),('MISSING_CERTIFICATE',path.name,arm)
                ct=time.perf_counter()
                check=subprocess.run([sys.executable,str(checker),str(path),str(cert)],
                                     capture_output=True,text=True,timeout=60)
                check_s=time.perf_counter()-ct
                verified=(check.returncode==0 and
                          json.loads(check.stdout)['status']=='UNSAT_CLAUSE_HALL_CERTIFICATE_VERIFIED')
                assert verified,('UNVERIFIED_CERTIFICATE',path.name,arm,check.stderr[-1000:])
                assert label!='SAT',('FALSE_UNSAT',path.name,arm)
                status='UNSAT_STRUCT_VERIFIED'
            else:
                assert p.returncode==0 and not cert.exists(),('MODULE_ERROR',path.name,arm,p.stderr[-500:])
                status='UNKNOWN'
            row=dict(formula=path.name,source_sha256=sha,expected_label=label,rep=rep,arm=arm,
                     status=status,verified=verified,wall_s=round(wall,6),check_s=round(check_s,6),
                     native_reason=t.get('reason'),groups=t.get('groups'),machines=t.get('machines'),
                     single_cpu=True)
            records.append(row)
            print('HALL2_ORIGINAL_TRIAL '+json.dumps(row,sort_keys=True),flush=True)
summary={arm:{'verified_unsat':sum(x['verified'] for x in records if x['arm']==arm),
              'unknown':sum(x['status']=='UNKNOWN' for x in records if x['arm']==arm)}
         for arm in ('HALL1','HALL2')}
report={'protocol':'HALL2-SUBSET-SAT2024-PAIRED-V1','original_sources':len(sources),
        'trials':len(records),'repetitions':2,'single_logical_cpu':True,
        'not_drat_lrat':True,'summary':summary,'rows':records}
(BASE/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print('HALL2_ORIGINAL_FINAL '+json.dumps({'sources':len(sources),'trials':len(records),
    'summary':summary,'false_unsat':0},sort_keys=True),flush=True)
