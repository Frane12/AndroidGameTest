#!/usr/bin/env python3
"""Paired source-pinned PCMAX capacity guard experiment. No promotion."""
import hashlib,json,os,pathlib,resource,subprocess,tempfile,time,sys
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'research'))
from drnas_pcmax_capacity_guard import derive,NotRecognized
OUT=ROOT/'pcmax-capacity-results'
SHA44='c55ab8fe2c9e10f0579f806802bc32d04913f12cd6ce28e6662b8d59d114c174'
if hasattr(os,'sched_setaffinity'):
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    assert len(os.sched_getaffinity(0))==1

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def check_guard(path,expected=None,limit=5000):
    t=time.perf_counter()
    try:r=derive(path,expected,limit)
    except (NotRecognized,AssertionError,ValueError,KeyError,IndexError,OverflowError,RecursionError) as e:
        r={'status':'UNKNOWN','reason':str(e)}
    return {'status':r['status'],'elapsed_e2e_s':round(time.perf_counter()-t,6),
            'certificate':r}
def solve(path,arm,cap=8):
    t=time.perf_counter()
    with tempfile.TemporaryDirectory(prefix='pcmax-capacity-paired-') as td:
        proof=pathlib.Path(td)/'proof.drat'
        if arm=='Kissat':
            cmd=[str(ROOT/'build/kissat'),str(path),str(proof)]
        elif arm=='X5_NO_MIN':
            cmd=[str(ROOT/'build/drnas-worker-domain'),str(path),'--mode','core',
                 '--time',str(max(.1,cap-.2)),'--x5-no-minimize','--proof',str(proof)]
        else:raise ValueError(arm)
        def limit_file():resource.setrlimit(resource.RLIMIT_FSIZE,(256*1024*1024,256*1024*1024))
        timed=False
        try:run=subprocess.run(cmd,capture_output=True,text=True,timeout=cap,preexec_fn=limit_file)
        except subprocess.TimeoutExpired:timed=True
        elapsed=time.perf_counter()-t
        status='TIMEOUT' if timed else 'UNKNOWN'
        certified=False
        if not timed and run.returncode==20 and proof.is_file():
            p=subprocess.run([str(ROOT/'build/drat-trim'),str(path),str(proof)],
                     capture_output=True,text=True,timeout=120)
            certified=p.returncode==0 and 's VERIFIED' in p.stdout
            status='UNSAT_DRAT_VERIFIED' if certified else 'UNSAT_UNVERIFIED'
        if not timed and run.returncode==10:status='SAT_UNVERIFIED'
        if not timed and run.returncode not in (0,10,20,124,153):
            raise RuntimeError(('SOLVER_ERROR',arm,run.returncode,run.stderr[-500:]))
        return {'status':status,'elapsed_e2e_s':round(elapsed,6),'verified_standard':certified,
            'proof_bytes':proof.stat().st_size if proof.exists() else 0}

def main():
    OUT.mkdir(exist_ok=True)
    manifest=json.loads((ROOT/'cf7/manifest.json').read_text())
    source44=next(s for s in manifest['sources'] if s['id']==44)
    p44=ROOT/source44['path']
    assert sha(p44)==SHA44==source44['sha256']
    rows=[]
    for rep in range(2):
        order=['CAPACITY_GUARD','X5_NO_MIN','Kissat'] if rep==0 else ['Kissat','X5_NO_MIN','CAPACITY_GUARD']
        for arm in order:
            row=check_guard(p44,SHA44) if arm=='CAPACITY_GUARD' else solve(p44,arm,8)
            row.update({'panel':'PCMAX44','rep':rep,'arm':arm,'cap_s':8})
            expected=(row['status']=='UNSAT_STRUCT_VERIFIED') if arm=='CAPACITY_GUARD' else row.get('verified_standard',False)
            row['PAR2_s']=round(row['elapsed_e2e_s'] if expected else 16,6)
            if arm=='CAPACITY_GUARD':
                c=row['certificate']
                assert row['status']=='UNSAT_STRUCT_VERIFIED'
                assert c['demand']==16 and c['capacity']==15
                assert c['bounds']==[1]*9+[3]*2 and c['states']==1250
            rows.append(row)
            print('PCMAX_BENCH',json.dumps({k:v for k,v in row.items() if k!='certificate'},sort_keys=True),flush=True)
    report=json.loads((ROOT/'pcmax20/report.json').read_text())
    seen=set();results=[]
    for entry in report['results']:
        if entry.get('status')!='OK':continue
        p=ROOT/'pcmax20'/pathlib.Path(entry['path']).name
        assert p.is_file() and sha(p)==entry['sha256']
        row=check_guard(p,entry['sha256'],5000)
        classification='SAT' if '-SAT.' in p.name else 'UNSAT' if '-UNSAT.' in p.name else 'UNKNOWN'
        if classification=='SAT':assert row['status']!='UNSAT_STRUCT_VERIFIED','FALSE_UNSAT'
        row.update({'panel':'PCMAX_OTHER_ORIGINALS','source':p.name,'source_class':classification})
        results.append(row)
        print('PCMAX_SWEEP',json.dumps({k:v for k,v in row.items() if k!='certificate'},sort_keys=True),flush=True)
    # One further SAT PCMAX original, source-pinned from CF7 manifest
    sat90=next(s for s in manifest['sources'] if s['id']==90)
    p90=ROOT/sat90['path']
    assert sha(p90)==sat90['sha256']
    ctrl=check_guard(p90,sat90['sha256'])
    assert ctrl['status']!='UNSAT_STRUCT_VERIFIED','FALSE_UNSAT_ON_SAT90'
    print('PCMAX_SAT90_CONTROL',json.dumps({k:v for k,v in ctrl.items() if k!='certificate'},sort_keys=True),flush=True)
    out={'protocol':'PCMAX-CAPACITY-STRUCTURAL-REAL-V1','source44_sha256':SHA44,
        'one_logical_cpu':True,'blind_holdout':False,'standard_drat_or_lrat_for_guard':False,
        'rows':rows,'other_originals':results,'sat90_control':ctrl}
    (OUT/'report.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
    print('PCMAX_CAPACITY_FINAL',json.dumps({
      'paired_trials':len(rows),'other_pcmax_originals':len(results),
      'other_pcmax_sat_controls':sum(x['source_class']=='SAT' for x in results)+1,
      'false_unsat':0,'guard44':next(r['certificate'] for r in rows if r['arm']=='CAPACITY_GUARD')},sort_keys=True),flush=True)
if __name__=='__main__':main()
