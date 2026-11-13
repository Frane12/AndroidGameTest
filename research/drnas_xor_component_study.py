#!/usr/bin/env python3
"""Bounded component XOR analysis; independently verify every consequence."""
import hashlib,json,pathlib,resource,subprocess,time
ROOT=pathlib.Path('prior');OUT=pathlib.Path('xor_component_study');OUT.mkdir(exist_ok=True)

def verify(cnf,proof):
    begin=time.monotonic(); original=set(); current=[]
    for raw in cnf.read_bytes().splitlines():
        line=raw.strip()
        if not line or line.startswith((b'c',b'p',b'%')):continue
        for lit in line.split():
            value=int(lit)
            if value: current.append(value)
            else: original.add(tuple(sorted(current)));current.clear()
    if current:raise ValueError('partial original clause')
    sources={};units=contradictions=0
    for raw in proof.read_text().splitlines():
        row=json.loads(raw);typ=row['type']
        if typ=='source':
            idx=row['id'];vs=row['vars'];rhs=row['rhs']
            if idx in sources or rhs not in (0,1) or not (1<=len(vs)<=6) or len(set(vs))!=len(vs) or any(v<=0 for v in vs):raise ValueError('bad source equation')
            for bits in range(1<<len(vs)):
                if bits.bit_count()%2==rhs:continue
                blocked=tuple(sorted(-v if (bits>>j)&1 else v for j,v in enumerate(vs)))
                if blocked not in original:raise ValueError('source equation not justified by original CNF')
            sources[idx]=(vs,rhs)
        elif typ in ('unit','contradiction'):
            ids=row['ids'];lit=row['lit']
            if not ids or len(ids)!=len(set(ids)) or any(i not in sources for i in ids):raise ValueError('missing or duplicate source id')
            support=set();rhs=0
            for idx in ids:
                vs,b=sources[idx];rhs^=b
                for v in vs:
                    if v in support:support.remove(v)
                    else:support.add(v)
            if typ=='unit':
                if not lit or support!={abs(lit)} or rhs!=(1 if lit>0 else 0):raise ValueError('invalid unit proof')
                units+=1
            else:
                if lit or support or rhs!=1:raise ValueError('invalid contradiction proof')
                contradictions+=1
        else:raise ValueError('unknown certificate record')
    return {'source_equations_checked':len(sources),'verified_units':units,'verified_contradictions':contradictions,'verification_s':time.monotonic()-begin}

# Only the same two Simon CNFs and the AES-related CNF from the frozen test.
manifest_files=[]
for p in ROOT.rglob('manifest.json'):
    try:m=json.loads(p.read_text())
    except (ValueError,OSError):continue
    if m.get('source')=='SAT Competition 2024 Main' and isinstance(m.get('cases'),list):manifest_files.append((p,m))
if len(manifest_files)!=1:raise RuntimeError('expected frozen source manifest')
manifest=manifest_files[0][1];cases=[c for c in manifest['cases'] if c['family'] in ('simon','aes')]
if len(cases)!=3:raise RuntimeError(f'expected 3 Simon/AES inputs, got {len(cases)}')
rows=[]
for c in cases:
    sha=c['sha256'];paths=list(ROOT.rglob(sha+'.cnf'))
    if len(paths)!=1:raise RuntimeError('missing frozen source')
    cnf=paths[0]
    if hashlib.sha256(cnf.read_bytes()).hexdigest()!=sha:raise RuntimeError('source checksum mismatch')
    proof=OUT/(sha+'.proof.jsonl')
    def limit():
        resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
        resource.setrlimit(resource.RLIMIT_CPU,(45,50))
    start=time.monotonic()
    try:
        p=subprocess.run(['./compiled/xor_component_study',str(cnf),str(proof)],capture_output=True,text=True,timeout=60,preexec_fn=limit)
        if p.returncode:row={'status':'ERROR','returncode':p.returncode,'stderr':p.stderr[-500:]}
        else:
            row=json.loads(p.stdout)
            checked=verify(cnf,proof)
            if checked['verified_units']!=row['candidate_units'] or checked['verified_contradictions']!=row['candidate_contradictions']:
                raise RuntimeError('proof count mismatch')
            row.update(checked);row['status']='COMPLETE'
    except subprocess.TimeoutExpired: row={'status':'TIMEOUT'}
    row.update(source=c['source_file'],family=c['family'],sha256=sha,total_with_verification_s=time.monotonic()-start)
    rows.append(row)
    (OUT/'results.json').write_text(json.dumps(rows,indent=2))
    print('XOR_COMPONENT_CASE '+json.dumps(row,sort_keys=True),flush=True)
summary={'source_run':43435404147,'diagnostic_only':True,'solver_modified':False,'max_component_vars':2048,'max_component_equations':3000,'max_components':128,'component_time_s':0.4,'total_gauss_s':5,'memory_limit_bytes':2*1024**3,'results':rows}
(OUT/'summary.json').write_text(json.dumps(summary,indent=2))
print('XOR_COMPONENT_FINAL '+json.dumps(summary,sort_keys=True),flush=True)
