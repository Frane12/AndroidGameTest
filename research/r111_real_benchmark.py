#!/usr/bin/env python3
"""R111: four independent SHA-locked original SAT2025 shards; 5 solver modes.

Time measured as complete wallclock process including in-process GF2 detection,
model output and solving. Error != timeout; per-trial SAT model is rechecked.
"""
import argparse,csv,hashlib,json,lzma,pathlib,random,re,subprocess,time,urllib.request,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r106_verify_solver as verifier
MODES=('cadical','r111_clean','r111_bridge','kissat','cryptominisat')
REPEATS=2
CAP=8.
def load_cases(root,shard):
    lock=json.loads(pathlib.Path('research/r111_real_2025_manifest.json').read_text())
    if lock['cap_s']!=CAP or lock['repeats']!=REPEATS or lock['modes']!=list(MODES):
        raise RuntimeError('R111_FAIL_CLOSED benchmark settings changed')
    cases=lock['shards'][shard]
    if len(cases)!=2 or any(c['shard']!=shard for c in cases):
        raise RuntimeError('R111_FAIL_CLOSED manifest mismatch')
    src=root/'source';src.mkdir(parents=True,exist_ok=True)
    for case in cases:
        with urllib.request.urlopen(urllib.request.Request(
                case['url'],headers={'User-Agent':'DRNAS-R111-research/1'}),timeout=90) as stream:
            raw=stream.read(4*1024*1024)
        if len(raw)>=4*1024*1024:raise RuntimeError('R111 compressed download limit')
        decompressed=lzma.decompress(raw,memlimit=128*1024*1024)
        if len(decompressed)!=case['bytes'] or hashlib.sha256(decompressed).hexdigest()!=case['sha256']:
            raise RuntimeError('R111_FAIL_CLOSED source SHA256 differs '+case['name'])
        (src/case['name']).write_bytes(decompressed)
        print('R111_SOURCE_VERIFIED',shard,case['name'],case['sha256'],flush=True)
    (root/'manifest.json').write_text(json.dumps(cases,indent=2)+'\n')
    return cases
def metric(report,key):
    m=re.search(r'(?:^|\s)'+re.escape(key)+r'=([^\s]+)',report)
    return m.group(1) if m else ''
def execute(executable,mode,source,expected):
    args=([executable,'clean' if mode=='r111_clean' else 'bridge',str(source)]
          if mode.startswith('r111') else [executable,str(source)])
    t0=time.perf_counter()
    try:
        proc=subprocess.run(args,capture_output=True,text=True,errors='replace',
            timeout=CAP)
        elapsed=time.perf_counter()-t0
        if proc.returncode not in (10,20):
            raise RuntimeError('R111_FAIL_CLOSED solver exit code '+str(proc.returncode)+
                               ' mode '+mode+' '+proc.stderr[-450:]+proc.stdout[-450:])
        status=verifier.status(proc.stdout,proc.returncode)
        if status!=expected:
            raise RuntimeError('R111_FAIL_CLOSED unexpected SAT label '+str(source)+' '+mode+' '+status)
        checked=False
        if status=='SAT':
            checked=verifier.model_valid(proc.stdout,verifier.cnf_clauses(source))
            if not checked:
                raise RuntimeError('R111_FAIL_CLOSED invalid original CNF SAT witness '+mode)
        if mode.startswith('r111') and 'R111_AUDIT' not in proc.stderr:
            raise RuntimeError('R111_FAIL_CLOSED missing callback audit')
        audit=proc.stderr.split('R111_AUDIT')[-1] if mode.startswith('r111') else ''
        if elapsed>CAP:status='TIMEOUT'
    except subprocess.TimeoutExpired:
        elapsed=CAP;status='TIMEOUT';checked=False;audit=''
    return dict(status=status,elapsed_s=round(elapsed,6),
      PAR2_s=round(2*CAP if status=='TIMEOUT' else elapsed,6),
      sat_model_verified=checked,
      gate=metric(audit,'gate') or None,
      source_xor=int(metric(audit,'source_xor') or 0),
      GF2_derived=int(metric(audit,'derived_GF2_rows') or 0),
      external_lemmas=int(metric(audit,'external_lemmas') or 0),
      external_implications=int(metric(audit,'external_implications') or 0),
      external_conflicts=int(metric(audit,'external_conflicts') or 0),
      assignment_notifications=int(metric(audit,'external_assignments') or 0),
      backtracks=int(metric(audit,'external_backtracks') or 0))
def main():
    p=argparse.ArgumentParser()
    p.add_argument('--shard',type=int,required=True,choices=[0,1,2,3])
    p.add_argument('--out',required=True)
    for key in ('cadical','r111','kissat','cms'):p.add_argument('--'+key,required=True)
    a=p.parse_args()
    root=pathlib.Path(a.out);root.mkdir(parents=True,exist_ok=True)
    cases=load_cases(root,a.shard)
    bins=dict(cadical=a.cadical,r111_clean=a.r111,r111_bridge=a.r111,
              kissat=a.kissat,cryptominisat=a.cms)
    rows=[]
    for case in cases:
        original=root/'source'/case['name']
        for rep in range(REPEATS):
            order=list(MODES)
            random.Random(case['sha256']+str(rep)+'R111_FROZEN').shuffle(order)
            for mode in order:
                result=execute(bins[mode],mode,original,case['expected'])
                row=dict(shard=a.shard,formula=case['name'],family=case['family'],
                    sha256=case['sha256'],already_seen=case['already_tested_R106_R110'],
                    repeat=rep,solver=mode,expected=case['expected'],**result)
                rows.append(row)
                print('R111_TRIAL',json.dumps(row),flush=True)
            if hashlib.sha256(original.read_bytes()).hexdigest()!=case['sha256']:
                raise RuntimeError('R111_FAIL_CLOSED original source changed')
        print('R111_CASE',case['name'],json.dumps({mode:[
              {'status':row['status'],'time_s':row['elapsed_s'],
               'derived_GF2':row['GF2_derived'],'lemmas':row['external_lemmas']}
              for row in rows if row['formula']==case['name'] and row['solver']==mode]
              for mode in MODES}),flush=True)
    if len(rows)!=len(cases)*REPEATS*len(MODES):
        raise RuntimeError('R111_FAIL_CLOSED incomplete paired measurements')
    with (root/'paired.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)
    summary={}
    for mode in MODES:
        sel=[r for r in rows if r['solver']==mode]
        summary[mode]=dict(trials=len(sel),
          solved=sum(r['status'] in ('SAT','UNSAT') for r in sel),
          timeout=sum(r['status']=='TIMEOUT' for r in sel),
          PAR2_s=round(sum(r['PAR2_s'] for r in sel),6),
          certified_sat_models=sum(r['sat_model_verified'] for r in sel),
          total_bridge_lemmas=sum(r['external_lemmas'] for r in sel),
          total_bridge_conflicts=sum(r['external_conflicts'] for r in sel))
    report=dict(protocol='R111-INPROCESS-GF2-CDCL-PAIRED-SAT2025',shard=a.shard,
      original_real_cases=len(cases),trials=len(rows),cap_s=CAP,methods=summary,
      limitations=['Public SAT2025 originals; not SAT Competition 2026, not globally blind',
        'R111 learned GF2 clauses are from independently verified source 2..6 XOR equations',
        'R111 currently derives only pairwise GF2 rows up to 8 variables and 96 observed variables; not a full Gaussian solver',
        'CaDiCaL IPASIR-UP variable freezing can affect solver performance; r111_clean controls this',
        'External solver UNSAT answers do not include independently checked proof',
        'PAR2 is a timeout penalty, not measured solve time'])
    (root/'summary.json').write_text(json.dumps(report,indent=2)+'\n')
    print('R111_SHARD_COMPLETE_AUDIT',json.dumps(report),flush=True)
if __name__=='__main__':main()
