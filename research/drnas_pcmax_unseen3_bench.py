#!/usr/bin/env python3
"""Source-pinned fresh PCMAX originals: weighted/prefix guard vs frozen X5/Kissat."""
import hashlib, html, json, lzma, os, pathlib, re, resource, subprocess, sys, tempfile, time, urllib.parse, urllib.request
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'research'))
from drnas_pcmax_capacity_guard import derive, NotRecognized
OUT=ROOT/'pcmax-unseen3-results'
CNFS=OUT/'original_cnfs'
CNFS.mkdir(parents=True,exist_ok=True)
TARGETS=[
('pcmax-scheduling-m30-14113-167638-UNSAT.sanitized.cnf.xz','UNSAT','dafc03ea784fee849febca7b64230558'),
('pcmax-scheduling-m19-10199-62102-UNSAT.sanitized.cnf.xz','UNSAT','bfadd34e71516e95d0ba2a3a8fb2ba03'),
('pcmax-scheduling-m12-8049-55035-SAT.sanitized.cnf.xz','SAT','da929c2aefde5e59878ad87c4323e581')]
if hasattr(os,'sched_setaffinity'):
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    assert len(os.sched_getaffinity(0))==1

def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':'DRNAS-PCMAX-SAT2024-fresh-benchmark/1.0'})
    with urllib.request.urlopen(req,timeout=90) as f:return f.read()

def collect():
    page=None
    for origin in ('https://benchmark-database.de/','https://www.benchmark-database.de/'):
        try:
            page=get(origin+'?track=main_2024').decode('utf-8')
            print('GBD_PAGE_OK',origin,len(page),flush=True)
            break
        except Exception as e:print('GBD_PAGE_FAILED',origin,repr(e),flush=True)
    if not page:raise RuntimeError('Official GBD page unavailable; no substituted formulas')
    rows=re.findall(r'(?is)<tr\b[^>]*>.*?</tr>',page)
    previous=json.loads((ROOT/'pcmax20/report.json').read_text())['results']
    names={p.get('name') for p in previous}
    hashes={p.get('sha256') for p in previous}
    data=[]
    for filename,label,record_hash in TARGETS:
        assert filename not in names
        rows_for=[r for r in rows if filename in html.unescape(r)]
        if len(rows_for)!=1 or record_hash not in rows_for[0]:
            raise RuntimeError(('GBD row/hash mismatch',filename,len(rows_for)))
        links=re.findall(r'''(?i)href\s*=\s*["']([^"']+)["']''',rows_for[0])
        links=[html.unescape(l) for l in links if '/file/' in l]
        if not links:raise RuntimeError(('GBD file link missing',filename))
        url=urllib.parse.urljoin('https://benchmark-database.de/',links[0])
        packed=get(url)
        if len(packed)>30_000_000:raise RuntimeError(('GBD archive too large',filename))
        raw=lzma.decompress(packed)
        headers=[line for line in raw.splitlines() if line.startswith(b'p cnf ')]
        if len(headers)!=1:raise RuntimeError(('DIMACS header invalid',filename))
        n,c=map(int,headers[0].split()[2:4])
        vnum,cnum=map(int,re.search(r'-m\d+-(\d+)-(\d+)-(?:UNSAT|SAT)\.',filename).groups())
        if n not in (vnum,vnum-1) or c!=cnum:raise RuntimeError(('DIMACS dimensions differ',filename,n,c))
        sha=hashlib.sha256(raw).hexdigest()
        if sha in hashes or sha=='c55ab8fe2c9e10f0579f806802bc32d04913f12cd6ce28e6662b8d59d114c174':
            raise RuntimeError(('Previously evaluated formula',filename))
        p=CNFS/filename.removesuffix('.xz')
        p.write_bytes(raw)
        (CNFS/filename).write_bytes(packed)
        item={'name':filename,'label':label,'gbd_record_hash':record_hash,'url':url,
              'sha256':sha,'compressed_sha256':hashlib.sha256(packed).hexdigest(),
              'vars':n,'clauses':c,'path':str(p.relative_to(ROOT))}
        data.append(item)
        print('PCMAX_UNSEEN_SOURCE',json.dumps(item,sort_keys=True),flush=True)
    (OUT/'source_manifest.json').write_text(json.dumps(data,indent=2,sort_keys=True)+'\n')
    return data

def guard(path,sha,ms):
    t=time.perf_counter()
    try:r=derive(path,sha,ms)
    except (NotRecognized,AssertionError,ValueError,KeyError,IndexError,OverflowError,RecursionError) as e:
        r={'status':'UNKNOWN','reason':str(e)}
    return {'status':r['status'],'elapsed_e2e_s':round(time.perf_counter()-t,6),
            'standard_verified':False,'certificate':r}

def solve(path,arm):
    with tempfile.TemporaryDirectory(prefix='pcmax-unseen-') as td:
        proof=pathlib.Path(td)/'proof.drat'
        cmd=([str(ROOT/'build/kissat'),str(path),str(proof)] if arm=='Kissat'
             else [str(ROOT/'build/drnas-worker-domain'),str(path),'--mode','core',
                   '--time','7.8','--x5-no-minimize','--proof',str(proof)])
        def file_limit():resource.setrlimit(resource.RLIMIT_FSIZE,(256<<20,256<<20))
        t=time.perf_counter()
        try:res=subprocess.run(cmd,capture_output=True,text=True,timeout=8,preexec_fn=file_limit)
        except subprocess.TimeoutExpired:res=None
        elapsed=round(time.perf_counter()-t,6)
        if res is None:status='TIMEOUT'
        elif res.returncode==10:status='SAT_UNVERIFIED'
        elif res.returncode==20:status='UNSAT_UNVERIFIED'
        elif res.returncode in (0,124,153):status='UNKNOWN'
        else:raise RuntimeError(('Solver failure',arm,res.returncode,res.stderr[-500:]))
        verified=False
        if res is not None and res.returncode==20 and proof.exists():
            try:
                v=subprocess.run([str(ROOT/'build/drat-trim'),str(path),str(proof)],
                                 capture_output=True,text=True,timeout=90)
                verified=v.returncode==0 and 's VERIFIED' in v.stdout
            except subprocess.TimeoutExpired:pass
            if verified:status='UNSAT_DRAT_VERIFIED'
        return {'status':status,'elapsed_e2e_s':elapsed,'standard_verified':verified,
                'proof_bytes':proof.stat().st_size if proof.exists() else 0}

def main():
    sources=collect()
    trials=[]
    for rep in range(2):
        for src in (sources if rep==0 else list(reversed(sources))):
            p=ROOT/src['path']
            assert hashlib.sha256(p.read_bytes()).hexdigest()==src['sha256']
            arms=('PREFIX','WEIGHTED','Kissat','X5_NO_MIN') if rep==0 else ('X5_NO_MIN','Kissat','WEIGHTED','PREFIX')
            for arm in arms:
                r=(guard(p,src['sha256'],1200) if arm=='PREFIX'
                   else guard(p,src['sha256'],5000) if arm=='WEIGHTED'
                   else solve(p,arm))
                if src['label']=='SAT' and r['status'].startswith('UNSAT'):
                    raise RuntimeError(('FALSE_UNSAT_ON_SAT',src['name'],arm,r['status']))
                struct=r['status']=='UNSAT_STRUCT_VERIFIED' or r['standard_verified']
                standard=r['standard_verified']
                r.update({'formula':src['name'],'sha256':src['sha256'],
                          'expected_label':src['label'],'arm':arm,'rep':rep,'cap_s':8,
                          'guard_budget_ms':1200 if arm=='PREFIX' else 5000 if arm=='WEIGHTED' else None,
                          'PAR2_structural_s':r['elapsed_e2e_s'] if struct else 16.,
                          'PAR2_standard_s':r['elapsed_e2e_s'] if standard else 16.})
                trials.append(r)
                summary={k:v for k,v in r.items() if k!='certificate'}
                if 'certificate' in r:
                    c=r['certificate']
                    summary.update({'jobs':c.get('jobs'),'machines':c.get('machines'),
                                    'demand':c.get('demand'),'capacity':c.get('capacity'),
                                    'weighted_lp_iterations':c.get('weighted_lp_iterations'),
                                    'weights_nonzero':sum(w>0 for w in c.get('weights') or []),
                                    'reason':c.get('reason')})
                print('PCMAX_UNSEEN_TRIAL',json.dumps(summary,sort_keys=True),flush=True)
    report={'protocol':'PCMAX-UNSEEN3-SAT2024-PAIRED-V1','source':sources,'rows':trials,
            'fresh_from_previous_15':True,'single_logical_cpu':True,
            'guard_proof_standard_drat_lrat':False,'repetitions':2}
    (OUT/'report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    stats={}
    for arm in ('PREFIX','WEIGHTED','Kissat','X5_NO_MIN'):
        a=[r for r in trials if r['arm']==arm]
        stats[arm]={'structural_unsat':sum(r['status']=='UNSAT_STRUCT_VERIFIED' for r in a),
                    'standard_unsat':sum(r['status']=='UNSAT_DRAT_VERIFIED' for r in a),
                    'par2_structural':round(sum(r['PAR2_structural_s'] for r in a),6),
                    'par2_standard':round(sum(r['PAR2_standard_s'] for r in a),6)}
    print('PCMAX_UNSEEN_FINAL',json.dumps({'sources':len(sources),'trials':len(trials),
        'false_unsat':0,'stats':stats},sort_keys=True),flush=True)

if __name__=='__main__':main()
