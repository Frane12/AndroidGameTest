#!/usr/bin/env python3
"""Frozen original-CNF SCALE6 regression and independent checker timing.
Expected labels are test-oracle metadata and never passed to the native solver.
"""
import argparse,hashlib,json,os,random,statistics,subprocess,sys,tempfile,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from verify_clique import verify,parse

def mutate(raw,seed):
    rng=random.Random(seed)
    nvars,clauses=parse(raw)
    labels=list(range(1,nvars+1));rng.shuffle(labels)
    new=[]
    for old in clauses:
        arr=[labels[abs(x)-1]*(1 if x>0 else -1) for x in old]
        rng.shuffle(arr);new.append(arr)
    rng.shuffle(new)
    return (f'p cnf {nvars} {len(new)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in new)).encode()

def trial(binary,source,label,tag,output):
    output.mkdir(parents=True,exist_ok=True)
    cnf=output/'source.cnf';cert=output/'proof.json'
    cnf.write_bytes(source)
    start=time.perf_counter()
    p=subprocess.run([str(binary),str(cnf),'--mode','core','--time','6',
        '--pcmax-clique-only','--pcmax-clique-budget-ms','4000',
        '--pcmax-certificate',str(cert)],capture_output=True,text=True,timeout=9)
    native_s=time.perf_counter()-start
    result={'tag':tag,'label':label,'sha256':hashlib.sha256(source).hexdigest(),
            'vars':parse(source)[0],'clauses':len(parse(source)[1]),
            'native_s':round(native_s,6),'status':'UNSAT' if p.returncode==20 else
            ('UNKNOWN' if p.returncode==0 else 'ERROR'),'verified':False}
    if result['status']=='UNSAT':
        if not cert.is_file():raise RuntimeError('UNSAT without saved certificate')
        proof=json.loads(cert.read_text())
        verify(source,proof)
        q=subprocess.run([sys.executable,str(Path(__file__).with_name('verify_clique.py')),
              str(cnf),str(cert)],capture_output=True,text=True,timeout=25)
        if q.returncode!=0:raise RuntimeError('independent checker rejected: '+q.stderr)
        result.update(verified=True,demand=proof['demand'],capacity=proof['capacity'])
        bad=json.loads(json.dumps(proof));bad['source_sha256']='0'*64
        try:verify(source,bad)
        except ValueError:pass
        else:raise RuntimeError('forged hash accepted')
        bad=json.loads(json.dumps(proof));bad['capacity']=bad['demand']
        try:verify(source,bad)
        except ValueError:pass
        else:raise RuntimeError('forged deficit accepted')
    result['with_checker_s']=round(time.perf_counter()-start,6)
    if label=='SAT' and result['status']!='UNKNOWN':raise RuntimeError('SAT control misclassified')
    if label=='UNSAT' and result['status']!='UNSAT':raise RuntimeError('unexpected UNKNOWN on frozen UNSAT regression')
    print('SCALE6_TRIAL',json.dumps(result,sort_keys=True),flush=True)
    return result

def main():
    a=argparse.ArgumentParser()
    a.add_argument('--binary',type=Path,required=True)
    a.add_argument('--manifest',type=Path,required=True)
    a.add_argument('--output',type=Path,required=True)
    args=a.parse_args()
    try:os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    except (AttributeError,OSError):pass
    cases=json.loads(args.manifest.read_text())
    rows=[]
    for ent in cases:
        raw=Path(ent['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=ent['sha256']:raise RuntimeError('frozen source SHA mismatch')
        for rep in range(3):
            rows.append(trial(args.binary.resolve(),raw,ent['label'],
                       ent['tag']+f'-rep{rep}',args.output/ent['tag']/f'rep{rep}'))
        if ent.get('metamorphic'):
            for i in range(8):
                rows.append(trial(args.binary.resolve(),mutate(raw,821004+i*1371),
                            ent['label'],ent['tag']+f'-shuffle{i}',
                            args.output/ent['tag']/f'shuffle{i}'))
    (args.output/'summary.json').write_text(json.dumps(rows,indent=2,sort_keys=True)+'\n')
    print('SCALE6_TOTAL',json.dumps({'trials':len(rows),'verified_unsat':sum(x['verified'] for x in rows),
         'sat_controls':sum(x['label']=='SAT' and x['status']=='UNKNOWN' for x in rows)},sort_keys=True))
if __name__=='__main__':main()
