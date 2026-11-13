#!/usr/bin/env python3
"""Profile exact XOR blocks and connectivity; never solve or modify CNFs."""
import hashlib,json,os,pathlib,re,resource,subprocess,time
BASE=pathlib.Path('prior')
OUT=pathlib.Path('xor_large_diagnostic');OUT.mkdir(exist_ok=True)
candidates=[]
for p in BASE.rglob('manifest.json'):
    try: obj=json.loads(p.read_text())
    except (ValueError,OSError):continue
    if obj.get('source')=='SAT Competition 2024 Main' and isinstance(obj.get('cases'),list): candidates.append((p,obj))
if len(candidates)!=1: raise RuntimeError(f'expected one source manifest, got {len(candidates)}')
manifest_path,manifest=candidates[0]
result_paths=list(BASE.rglob('results.json'))
if len(result_paths)!=1:raise RuntimeError('expected one original results.json')
old=json.loads(result_paths[0].read_text())
rows=[]
for item in manifest['cases']:
    sha=item['sha256']; paths=list(BASE.rglob(sha+'.cnf'))
    if len(paths)!=1: raise RuntimeError(f'expected source {sha}, got {len(paths)}')
    cnf=paths[0]
    if hashlib.sha256(cnf.read_bytes()).hexdigest()!=sha:raise RuntimeError(f'checksum mismatch {sha}')
    def limit():
        resource.setrlimit(resource.RLIMIT_AS,(2*1024**3,2*1024**3))
        resource.setrlimit(resource.RLIMIT_CPU,(75,80))
    begin=time.monotonic()
    try:
        p=subprocess.run(['./compiled/xor_structure_diagnostic',str(cnf)],capture_output=True,text=True,timeout=90,preexec_fn=limit)
        if p.returncode!=0: row={'status':'ERROR','returncode':p.returncode,'stderr_tail':p.stderr[-500:]}
        else:
            row=json.loads(p.stdout);row['status']='COMPLETE'
    except subprocess.TimeoutExpired:
        row={'status':'TIMEOUT'}
    row.update(source=item['source_file'],family=item['family'],sha256=sha,wall_subprocess_s=time.monotonic()-begin)
    prior=[r for r in old if r['sha256']==sha and r['arm']=='R153_NATIVE' and 'reason=mixed_consistent_xor' in r.get('route','')]
    if prior and row['status']=='COMPLETE':
        route=prior[0]['route']; m=re.search(r'covered=(\d+) equations=(\d+)',route)
        if not m:raise RuntimeError('could not parse historical R153 route')
        row['prior_r153_covered']=int(m.group(1));row['prior_r153_equations']=int(m.group(2))
        row['calibration_match']=row['covered_clauses']==int(m.group(1)) and row['equations_with_units']==int(m.group(2))
        if not row['calibration_match']:
            print('XOR_DIAG_MISMATCH '+json.dumps(row,sort_keys=True),flush=True)
            raise RuntimeError('diagnostic differs from R153 on same source')
    rows.append(row)
    (OUT/'results.json').write_text(json.dumps(rows,indent=2))
    print('XOR_DIAG_CASE '+json.dumps(row,sort_keys=True),flush=True)
summary={'source_run':43435404147,'source_manifest_sha256':hashlib.sha256(manifest_path.read_bytes()).hexdigest(),'diagnostic_only':True,'solver_modified':False,'max_memory_bytes':2*1024**3,'time_limit_s':90,'files':len(manifest['cases']),'completed':sum(r['status']=='COMPLETE' for r in rows),'calibrated':sum(r.get('calibration_match',False) for r in rows),'results':rows}
(OUT/'summary.json').write_text(json.dumps(summary,indent=2))
print('XOR_DIAG_FINAL '+json.dumps(summary,sort_keys=True),flush=True)
