#!/usr/bin/env python3
"""Frozen REAL36: original SAT2024 application-labelled CNFs, never generated.
Selection is metadata/family/size based, never solver-outcome based. Main PAR2
uses verified answers and process wall time (launch, parsing and gate included).
Independent witness/proof-audit costs are reported separately for ALL arms.
A reference UNSAT certificate certifies the instance, not a DRNAS proof trace.
"""
from __future__ import annotations
import argparse, collections, hashlib, io, itertools, json, lzma, os
from pathlib import Path
import random, re, resource, subprocess, tempfile, time, zipfile

ROOT=Path('real36_frozen')
ARCHIVE='https://zenodo.org/records/15095752/files/sat-competition-2024-main-benchmarks.zip?download=1'
META='https://raw.githubusercontent.com/satcompetition/2024/main/downloads/meta.csv'
META_BLOB='02acd5580d828892423bea1f9e2ffb368cb2ea24'
N, REPS, SHARDS, CAP = 36, 3, 12, 5.0
ALLOWED={'hardware-verification','hardware-model-checking','hardware-miter',
         'software-verification','planning','scheduling','bitvector',
         'cryptography','cryptography-simon','cryptography-ascon',
         'risc-instruction-removal-golcrest'}
ARMS={'CORE':('build/drnas-x41','core'),'ADAPTIVE':('build/drnas-x3','x3'),
      'X46_GATE':('build/drnas-x46','x46_gate'),
      'GATE_R2':('build/drnas-gate-r2','gate_r2'),
      'GATE_R3':('build/drnas-gate-r3','gate_r3'),
      'KISSAT':('build/kissat',None),'CADICAL':('build/cadical',None)}
MAX_RAW=32*1024*1024

def emit(tag, x): print(tag+' '+json.dumps(x,sort_keys=True),flush=True)
def dump(path, x): Path(path).write_text(json.dumps(x,sort_keys=True,indent=2)+'\n')
def digest(data): return hashlib.sha256(data).hexdigest()

def parse_cnf(data):
    n=m=None; clauses=[]; pending=[]
    for raw in data.decode('ascii').splitlines():
        line=raw.strip()
        if not line or line[0] in 'c%': continue
        if line.startswith('p '):
            words=line.split()
            if n is not None or len(words)!=4 or words[:2]!=['p','cnf']:
                raise ValueError('Invalid DIMACS header')
            n,m=map(int,words[2:])
            if n<0 or m<0: raise ValueError('Negative dimensions')
            continue
        if n is None: raise ValueError('Missing DIMACS header')
        for token in line.split():
            if token.startswith(('c','%')): break
            lit=int(token)
            if abs(lit)>n: raise ValueError('Literal outside header range')
            if lit: pending.append(lit)
            else: clauses.append(tuple(pending)); pending=[]
    if n is None or pending or len(clauses)!=m: raise ValueError('Incomplete DIMACS')
    return n,clauses

def verify_sat(stdout,n,clauses):
    values={}
    try:
        for line in stdout.splitlines():
            if not line.startswith('v '): continue
            for word in line[2:].split():
                v=int(word)
                if not v: continue
                if abs(v)>n or (abs(v) in values and values[abs(v)]!=(v>0)): return False
                values[abs(v)]=v>0
        return all(any(values.get(abs(lit))==(lit>0) for lit in c) for c in clauses)
    except ValueError: return False

class RangeReader(io.RawIOBase):
    """Bounded HTTP ranges: never accidentally download the 4.3GB archive."""
    def __init__(self,session,url):
        self.session,self.url,self.pos=session,url,0
        self.cache=b''; self.cache_start=0
        r=session.get(url,headers={'Range':'bytes=0-0','Accept-Encoding':'identity'},
                      stream=True,timeout=(20,90))
        try:
            if r.status_code!=206: raise RuntimeError('Server refused ZIP byte ranges')
            self.size=int(r.headers['Content-Range'].split('/')[-1])
        finally: r.close()
    def seekable(self): return True
    def readable(self): return True
    def tell(self): return self.pos
    def seek(self,offset,whence=0):
        self.pos=offset+(0 if whence==0 else self.pos if whence==1 else self.size)
        if not 0<=self.pos<=self.size: raise ValueError('Invalid archive seek')
        return self.pos
    def read(self,n=-1):
        n=min(self.size-self.pos,n if n>=0 else self.size-self.pos)
        if n==0: return b''
        if n>16*1024*1024: raise RuntimeError('Oversized ZIP range')
        if not (self.cache_start<=self.pos and self.pos+n<=self.cache_start+len(self.cache)):
            end=min(self.size-1,self.pos+max(n,131072)-1)
            r=self.session.get(self.url,headers={'Range':f'bytes={self.pos}-{end}',
                    'Accept-Encoding':'identity'},stream=True,timeout=(20,90))
            try:
                expected=f'bytes {self.pos}-{end}/{self.size}'
                if r.status_code!=206 or r.headers.get('Content-Range')!=expected:
                    raise RuntimeError('ZIP response range mismatch: '+str(r.status_code))
                body=r.raw.read(end-self.pos+2)
                if len(body)!=end-self.pos+1: raise RuntimeError('Truncated ZIP range')
            finally: r.close()
            self.cache_start,self.cache=self.pos,body
        offset=self.pos-self.cache_start; self.pos+=n
        return self.cache[offset:offset+n]

def freeze():
    import requests
    from urllib3.util.retry import Retry
    session=requests.Session()
    session.mount('https://',requests.adapters.HTTPAdapter(max_retries=Retry(
        total=5,backoff_factor=1,status_forcelist=[429,500,502,503,504])))
    response=session.get(META,timeout=60); response.raise_for_status(); meta=response.content
    if hashlib.sha1(f'blob {len(meta)}\0'.encode()+meta).hexdigest()!=META_BLOB:
        raise RuntimeError('Official metadata changed; do not silently alter selection')
    metadata={}
    for line in meta.decode().splitlines()[1:]:
        fields=line.split()
        if len(fields)!=4: raise RuntimeError('Unexpected metadata schema')
        h,name,family,author=fields
        if family in ALLOWED: metadata[name]={'gbd_hash':h,'family':family,'author':author}
    ROOT.mkdir(exist_ok=True); (ROOT/'cases').mkdir(exist_ok=True)
    (ROOT/'official_meta.txt').write_bytes(meta)
    pool=collections.defaultdict(list); excluded=[]; selected=[]; seen=set()
    with zipfile.ZipFile(RangeReader(session,ARCHIVE)) as z:
        for info in z.infolist():
            name=Path(info.filename).name
            if name in metadata and name.endswith('.cnf.xz') and info.file_size<=4*1024*1024:
                pool[metadata[name]['family']].append(info)
        for group in pool.values(): group.sort(key=lambda x:(x.file_size,x.filename))
        while len(selected)<N and any(pool.values()):
            for family in sorted(pool):
                if len(selected)==N: break
                while pool[family]:
                    info=pool[family].pop(0); name=Path(info.filename).name
                    decoder=lzma.LZMADecompressor(memlimit=512*1024*1024)
                    raw=decoder.decompress(z.read(info),max_length=MAX_RAW+1)
                    if len(raw)>MAX_RAW or not decoder.eof:
                        excluded.append({'name':name,'reason':'uncompressed_size'}); continue
                    sha=digest(raw); n,clauses=parse_cnf(raw)
                    if n>1000000 or len(clauses)>1000000:
                        excluded.append({'name':name,'reason':'dimensions'}); continue
                    if sha in seen:
                        excluded.append({'name':name,'reason':'duplicate_sha'}); continue
                    seen.add(sha); idx=len(selected)
                    path=ROOT/'cases'/f'{idx:03d}_{sha[:16]}.cnf'; path.write_bytes(raw)
                    row={'id':idx,'path':str(path),'sha256':sha,'archive_entry':info.filename,
                         'filename':name,'bytes':len(raw),'xz_bytes':info.file_size,
                         'nvars':n,'nclauses':len(clauses),**metadata[name]}
                    selected.append(row); emit('REAL36_SOURCE',row); break
    if len(selected)!=N: raise RuntimeError(f'Only {len(selected)} eligible sources, expected {N}')
    dump(ROOT/'manifest.json',selected)
    protocol={'sources':N,'repeats':REPS,'shards':SHARDS,'cap_s':CAP,'arms':list(ARMS),
        'solver_runs':N*REPS*len(ARMS),'archive':ARCHIVE,'metadata':META,
        'metadata_git_blob':META_BLOB,'manifest_sha256':digest((ROOT/'manifest.json').read_bytes()),
        'family_counts':dict(collections.Counter(x['family'] for x in selected)),
        'selection':'round-robin application metadata families, smallest compressed member first; no timing screen',
        'excluded_before_any_solve':excluded,'own_generator_used':False,
        'historically_unseen_not_claimed':True,'native_base_commit':'37be81fe9fe5623c3621aa223b2896dbee8fb04c',
        'timing':'process wall time includes launch, original CNF parsing and all gate costs; correctness audit separately reported',
        'unsat_evidence':'independently checked reference certificate for original instance, NOT a DRNAS proof',
        'limits':'size-biased application-labelled competition sample, not a representative industrial population'}
    dump(ROOT/'protocol.json',protocol); emit('REAL36_FROZEN',protocol)

def execute(cmd,limit,proof_limit=False):
    def bounded(): resource.setrlimit(resource.RLIMIT_FSIZE,(64*1024*1024,64*1024*1024))
    start=time.perf_counter()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=limit,
                         preexec_fn=bounded if proof_limit else None)
        return p,time.perf_counter()-start
    except subprocess.TimeoutExpired: return None,time.perf_counter()-start

def measure(src,arm,n,clauses,cap=CAP):
    binary,mode=ARMS[arm]
    cmd=([binary,src['path'],'--mode',mode,'--time',str(cap),'--stats'] if mode else
         [binary,'-q',src['path']])
    p,wall=execute(cmd,cap+0.25)
    result='TIMEOUT' if p is None else 'UNKNOWN'
    rc=p.returncode if p else None; validation=0.0; stats={}; gate={}
    if p:
        for line in p.stderr.splitlines():
            if ' ' not in line: continue
            prefix,body=line.split(' ',1)
            try:
                if prefix.endswith('_STATS'): stats=json.loads(body)
                if prefix=='GATER2_GATE': gate=json.loads(body)
            except json.JSONDecodeError: pass
        if rc==10:
            tick=time.perf_counter(); valid=verify_sat(p.stdout,n,clauses)
            validation=time.perf_counter()-tick
            result='SAT_WITNESS_VERIFIED' if valid else 'WRONG_SAT'
        elif rc==20: result='UNSAT_UNVERIFIED'
        elif rc not in (0,): result='SOLVER_ERROR'
    return {'reported':result,'returncode':rc,'process_wall_s':round(wall,7),
            'within_cap':wall<=cap,'witness_check_s':round(validation,7),
            'stats':stats,'gate':gate,'stderr_tail':p.stderr[-400:] if p and rc not in (0,10,20) else ''}

def certify_unsat(path):
    tick=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='real36-proof-') as temp:
        proof=Path(temp)/'reference.drat'
        p,_=execute(['build/cadical','-q','--no-binary',str(path),str(proof)],20,True)
        certificate={'verified':False,'producer':'pinned CaDiCaL','checker':'pinned drat-trim'}
        if p and p.returncode==20 and proof.exists():
            certificate['proof_bytes']=proof.stat().st_size
            certificate['proof_sha256']=digest(proof.read_bytes())
            q,_=execute(['build/drat-trim',str(path),str(proof)],30)
            certificate['verified']=bool(q and q.returncode==0 and
                re.search(r'^s VERIFIED\s*$',q.stdout,re.M))
            certificate['checker_tail']=(q.stdout+q.stderr)[-400:] if q else 'CHECK_TIMEOUT'
        else: certificate['producer_returncode']=p.returncode if p else None
    certificate['audit_wall_s']=round(time.perf_counter()-tick,7)
    return certificate

def finalized(record,cert):
    verified=record['reported']=='SAT_WITNESS_VERIFIED' or (
        record['reported']=='UNSAT_UNVERIFIED' and cert.get('verified',False))
    accepted=verified and record['within_cap']
    record.update(accepted=accepted,verified_answer=verified,
        evidence=('SAT_WITNESS' if record['reported']=='SAT_WITNESS_VERIFIED' else
                  'REFERENCE_INSTANCE_UNSAT_CERTIFICATE' if verified else 'NONE'),
        PAR2_s=record['process_wall_s'] if accepted else 2*CAP,
        reported_PAR2_s=record['process_wall_s'] if record['within_cap'] and
            record['reported'] in ('SAT_WITNESS_VERIFIED','UNSAT_UNVERIFIED') else 2*CAP)
    return record

def shard(index):
    sources=json.loads((ROOT/'manifest.json').read_text()); protocol=json.loads((ROOT/'protocol.json').read_text())
    if digest((ROOT/'manifest.json').read_bytes())!=protocol['manifest_sha256']: raise RuntimeError('Manifest drift')
    mine=[s for s in sources if s['id']%SHARDS==index]; allrows=[]; certificates=[]
    out=Path(f'real36_results/{index}'); out.mkdir(parents=True,exist_ok=True)
    with (out/'trials.jsonl').open('w') as fd:
        for src in mine:
            raw=Path(src['path']).read_bytes()
            if digest(raw)!=src['sha256']: raise RuntimeError('Original CNF drift')
            n,clauses=parse_cnf(raw); rows=[]
            for rep in range(REPS):
                order=list(ARMS); shift=(src['id']+rep)%len(order); order=order[shift:]+order[:shift]
                arms={a:measure(src,a,n,clauses) for a in order}
                rows.append({'id':src['id'],'sha256':src['sha256'],'family':src['family'],
                             'filename':src['filename'],'rep':rep,'shard':index,'arms':arms})
            records=[v for r in rows for v in r['arms'].values()]
            cert=certify_unsat(src['path']) if any(r['reported']=='UNSAT_UNVERIFIED' for r in records) else {'verified':False,'audit_wall_s':0}
            cert.update(sha256=src['sha256']); certificates.append(cert)
            sat=any(r['reported']=='SAT_WITNESS_VERIFIED' for r in records)
            if cert['verified'] and sat: raise RuntimeError('SAT witness / UNSAT proof contradiction')
            for row in rows:
                for record in row['arms'].values():
                    finalized(record,cert)
                    record['incorrect']=record['reported']=='WRONG_SAT' or (sat and record['reported']=='UNSAT_UNVERIFIED')
                fd.write(json.dumps(row,sort_keys=True)+'\n'); fd.flush(); allrows.append(row)
            dump(out/'certificates.json',certificates)
            emit('REAL36_PROGRESS',{'shard':index,'completed_formulas':len(allrows)//REPS,
                  'total_formulas':len(mine),'summary':summary(allrows)})
    dump(out/'report.json',{'shard':index,'manifest_sha256':protocol['manifest_sha256'],
         'rows':len(allrows),'summary':summary(allrows)})

def summary(rows):
    return {arm:{'solved':sum(r['arms'][arm]['accepted'] for r in rows),
      'SAT':sum(r['arms'][arm]['accepted'] and r['arms'][arm]['reported']=='SAT_WITNESS_VERIFIED' for r in rows),
      'UNSAT_reference_certified':sum(r['arms'][arm]['accepted'] and r['arms'][arm]['reported']=='UNSAT_UNVERIFIED' for r in rows),
      'unverified_UNSAT':sum(r['arms'][arm]['reported']=='UNSAT_UNVERIFIED' and not r['arms'][arm]['verified_answer'] for r in rows),
      'PAR2_s':round(sum(r['arms'][arm]['PAR2_s'] for r in rows),7),
      'process_wall_s':round(sum(r['arms'][arm]['process_wall_s'] for r in rows),7),
      'witness_check_s':round(sum(r['arms'][arm]['witness_check_s'] for r in rows),7),
      'incorrect':sum(r['arms'][arm].get('incorrect',False) for r in rows)} for arm in ARMS}

def paired(rows,baseline,challenger='GATE_R3'):
    groups=collections.defaultdict(list)
    for row in rows: groups[row['sha256']].append(row['arms'][challenger]['PAR2_s']-row['arms'][baseline]['PAR2_s'])
    deltas=[sum(v) for v in groups.values()]; rng=random.Random(3636)
    boot=sorted(sum(rng.choice(deltas) for _ in deltas) for _ in range(2000))
    return {'delta_PAR2_s':round(sum(deltas),7),'formula_clustered_95_s':[round(boot[50],7),round(boot[1949],7)],
            'independent_formulas':len(deltas),'repetitions_not_independent':True}

def finish():
    protocol=json.loads((ROOT/'protocol.json').read_text()); sources=json.loads((ROOT/'manifest.json').read_text())
    if digest((ROOT/'manifest.json').read_bytes())!=protocol['manifest_sha256']: raise RuntimeError('Manifest drift')
    rows=[]; certs=[]
    for idx in range(SHARDS):
        folder=Path('real36_downloads')/f'gate-real36-{idx}'
        report=json.loads((folder/'report.json').read_text())
        if report['manifest_sha256']!=protocol['manifest_sha256']: raise RuntimeError('Shard drift')
        rows.extend(json.loads(x) for x in (folder/'trials.jsonl').read_text().splitlines())
        certs.extend(json.loads((folder/'certificates.json').read_text()))
    expected={(s['sha256'],rep) for s in sources for rep in range(REPS)}
    if len(rows)!=N*REPS or {(r['sha256'],r['rep']) for r in rows}!=expected: raise RuntimeError('Missing or duplicated pairs')
    bysha={s['sha256']:s for s in sources}
    for row in rows:
        if row['family']!=bysha[row['sha256']]['family'] or set(row['arms'])!=set(ARMS): raise RuntimeError('Row metadata drift')
    report={'status':'COMPLETE','protocol':protocol,'overall':summary(rows),
        'families':{f:summary([r for r in rows if r['family']==f]) for f in sorted({r['family'] for r in rows})},
        'shards':{str(i):summary([r for r in rows if r['shard']==i]) for i in range(SHARDS)},
        'R3_comparisons':{a:paired(rows,a) for a in ARMS if a!='GATE_R3'},
        'certificate_audit_total_s':sum(c['audit_wall_s'] for c in certs),'certificates':certs}
    dest=Path('real36_final'); dest.mkdir(exist_ok=True); dump(dest/'report.json',report)
    (dest/'paired_trials.jsonl').write_text(''.join(json.dumps(r,sort_keys=True)+'\n' for r in sorted(rows,key=lambda r:(r['id'],r['rep']))))
    lines=['# DRNAS GATE REAL36 — original application-labelled SAT2024 CNFs','',
        '| Arm | Verified answers | SAT | Reference-certified UNSAT | PAR2 s | Process wall s |',
        '|---|---:|---:|---:|---:|---:|']
    for a,v in report['overall'].items(): lines.append(f"| {a} | {v['solved']}/{N*REPS} | {v['SAT']} | {v['UNSAT_reference_certified']} | {v['PAR2_s']:.4f} | {v['process_wall_s']:.4f} |")
    lines+=['','UNSAT: independent certificate establishes the original instance is UNSAT; this is NOT a DRNAS proof trace. Witness/proof auditing costs are separate from process PAR2.','',json.dumps(report['R3_comparisons'],indent=2),'','Size-selected competition subset; no universal industrial/generalization claim.']
    text='\n'.join(lines)+'\n'; (dest/'summary.md').write_text(text)
    if os.getenv('GITHUB_STEP_SUMMARY'): Path(os.environ['GITHUB_STEP_SUMMARY']).write_text(text)
    emit('REAL36_FINAL',report)
    if any(v['incorrect'] for v in report['overall'].values()): raise RuntimeError('Incorrect solver answer detected; see artifacts')

def selftest(native=False):
    n,c=parse_cnf(b'c t\np cnf 3 2\n1\n-2 0 3 0\n')
    assert verify_sat('s SATISFIABLE\nv 1 3 0\n',n,c)
    assert not verify_sat('v 1 -1 3 0\n',n,c)
    assert not verify_sat('v 1 0\n',n,c)
    assert not verify_sat('v 1 0\n',1,[()])
    r={'reported':'UNSAT_UNVERIFIED','within_cap':True,'process_wall_s':.1}
    assert not finalized(dict(r),{'verified':False})['accepted']
    assert finalized(dict(r),{'verified':True})['accepted']
    if native:
        with tempfile.TemporaryDirectory() as d:
            for idx in range(20):
                rng=random.Random(3600+idx); n=6
                clauses=[tuple(v*(1 if rng.getrandbits(1) else -1) for v in rng.sample(range(1,n+1),3)) for _ in range(20+idx)]
                sat=any(all(any(bits[abs(v)-1]==(v>0) for v in c) for c in clauses) for bits in itertools.product((False,True),repeat=n))
                path=Path(d)/'test.cnf'; path.write_text(f'p cnf {n} {len(clauses)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in clauses))
                for arm in ARMS:
                    out=measure({'path':str(path)},arm,n,clauses)
                    assert out['reported']==('SAT_WITNESS_VERIFIED' if sat else 'UNSAT_UNVERIFIED'),(idx,arm,out)
            path.write_text('p cnf 1 2\n1 0\n-1 0\n')
            assert certify_unsat(path)['verified'], 'Proof checker pipeline failed'
    emit('REAL36_SELFTEST_PASS',{'native':native,'exact_oracle_runs':140 if native else 0})

if __name__=='__main__':
    parser=argparse.ArgumentParser(); parser.add_argument('stage',choices=['freeze','shard','finish','selftest'])
    parser.add_argument('--shard',type=int,default=0); parser.add_argument('--native',action='store_true'); a=parser.parse_args()
    if a.stage=='freeze': freeze()
    elif a.stage=='shard':
        if not 0<=a.shard<SHARDS: parser.error('Bad shard')
        shard(a.shard)
    elif a.stage=='finish': finish()
    else: selftest(a.native)
