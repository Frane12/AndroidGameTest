#!/usr/bin/env python3
"""Source-only metamorphic check for native SAC9, independent DRAT acceptance.
The expected label is confined to the harness, never passed into native SAC.
"""
import argparse,hashlib,json,os,random,subprocess,time
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'ft06_sac'))
from structural_sac import parse

def permute(raw,seed):
    rng=random.Random(seed)
    nv,clauses=parse(raw)
    perm=list(range(1,nv+1));rng.shuffle(perm)
    converted=[]
    for clause in clauses:
        xs=[perm[abs(v)-1]*(1 if v>0 else -1) for v in clause]
        rng.shuffle(xs);converted.append(xs)
    rng.shuffle(converted)
    return (f'p cnf {nv} {len(converted)}\n'+
            ''.join(' '.join(map(str,cl))+' 0\n' for cl in converted)).encode()

def execute(cnf,binpath,checker,horizon,out,uncached):
    proof=out/'proof.drat';report=out/'sac9.json'
    args=[str(binpath), '--cnf',str(cnf),'--drat',str(proof),'--report',str(report),
          '--seconds','10','--cap','6000']
    if uncached:args.append('--no-cache')
    started=time.perf_counter()
    p=subprocess.run(args,text=True,capture_output=True,timeout=25)
    e2e=time.perf_counter()-started
    if p.returncode!=0:raise RuntimeError('native process failed: '+p.stderr)
    obj=json.loads(report.read_text())
    passed=False;checker_s=None
    if horizon==54:
        if obj['status']!='EMITTED_UNCHECKED' or not proof.exists():
            raise RuntimeError('missing UNSAT candidate: '+str(obj))
        started=time.perf_counter()
        q=subprocess.run([str(checker),str(cnf),str(proof),'-U','-t','20'],
            capture_output=True,text=True,timeout=35)
        checker_s=time.perf_counter()-started
        (out/'drat_checker.log').write_text(q.stdout+'\n'+q.stderr)
        passed=q.returncode==0 and 's VERIFIED' in q.stdout
        if not passed:raise RuntimeError('DRAT checker rejected proof: '+q.stdout[-1000:]+q.stderr)
    else:
        if obj['status']!='UNKNOWN' or proof.exists():
            raise RuntimeError('false UNSAT on SAT control: '+str(obj))
    return {'horizon':horizon,'source_sha256':hashlib.sha256(cnf.read_bytes()).hexdigest(),
            'uncached':uncached,'status':obj['status'],'drat_accepted':passed,
            'producer_s':round(e2e,6),'checker_s':round(checker_s,6) if checker_s else None,
            'nested_pairs':obj['nested_support_pairs'],'checks':obj['checks'],
            'lemmas':obj['lemmas']}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--source54',type=Path,required=True)
    ap.add_argument('--source55',type=Path,required=True)
    ap.add_argument('--binary',type=Path,required=True)
    ap.add_argument('--checker',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    try:os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    except (AttributeError,OSError):pass
    targets={
        54:('99910f35ed2401b2315618aa7ac23605ba876cfea79c3edadd1e468ef1c674ee',args.source54),
        55:('ec8a9bbb98f7742cedddf4c7430ce1185da7256427505b1b051bff1cbbb4dc20',args.source55)}
    rows=[]
    for h,(sha,path) in targets.items():
        src=path.read_bytes()
        if hashlib.sha256(src).hexdigest()!=sha:raise ValueError('original frozen source changed')
        for rep in range(9):
            raw=src if rep==0 else permute(src,4100+h*117+rep*23)
            folder=args.out/f'h{h}'/f'rep{rep:02d}'
            folder.mkdir(parents=True,exist_ok=True)
            cnf=folder/'original.cnf';cnf.write_bytes(raw)
            record=execute(cnf,args.binary.resolve(),args.checker.resolve(),h,folder,rep%2==0)
            record['rep']=rep
            print('SAC9_METAMORPHIC '+json.dumps(record,sort_keys=True),flush=True)
            rows.append(record)
    (args.out/'summary.json').write_text(json.dumps(rows,indent=2,sort_keys=True)+'\n')
    print('SAC9_METAMORPHIC_TOTAL '+json.dumps({'trials':len(rows),
        'verified_unsat':sum(x['drat_accepted'] for x in rows),
        'sat_controls_unknown':sum(x['horizon']==55 and x['status']=='UNKNOWN' for x in rows)}))

if __name__=='__main__':main()
