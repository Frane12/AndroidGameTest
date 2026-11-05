#!/usr/bin/env python3
"""Official 2026 original-CNF local benchmark: DRNAS SAT V7.7 versus
unmodified CaDiCaL 3.0.1 and unmodified Kissat rel-4.0.4.

60-second per process / 120s PAR-2 penalty; same two GitHub Actions repeats.
Never cherry-pick timeouts. Kissat is independent and NOT a "DRNAS mode".
No official 5000-second conditions or independent UNSAT proof certificates.
"""
import argparse,csv,hashlib,json,random,subprocess,time
from pathlib import Path
import benchmark as nf77

MODES=('plain','majority','v76_guided','quality_plain',
       'quality_guided','quality_random','kissat404')
TIMEOUT=60.
FIELDS=('case','family','method','repeat','answer','elapsed_s','native_s','observed',
    'short5','short_fraction','extended','resumed','hints',
    'kissat_model_checked','error','source_sha256','cutoff_s')

def check_witness(path,output):
    # Kissat normally prints DIMACS witness lines beginning with "v ".
    vals={}
    for line in output.splitlines():
        l=line.lstrip()
        if not l.startswith('v '):continue
        for token in l[2:].split():
            lit=int(token)
            if lit:vals[abs(lit)]=lit>0
    if not vals:return False
    clauses=[];clause=[];header=False
    with open(path,encoding='ascii') as f:
        for line in f:
            l=line.strip()
            if not l or l[0]=='c':continue
            if l.startswith('p '):
                header=True;continue
            if l[0]=='%':break
            if not header:raise RuntimeError('Invalid original DIMACS header')
            for token in l.split():
                lit=int(token)
                if lit:
                    clause.append(lit)
                else:
                    clauses.append(clause);clause=[]
    if clause:raise RuntimeError('Incomplete original CNF')
    if any(not any(vals.get(abs(lit),None)==(lit>0) for lit in c) for c in clauses):
        raise RuntimeError('KISSAT INVALID SAT WITNESS: original clause violated')
    return True

def run_native(binary,mode,path,seed,limit):
    try:
        r=nf77.execute(binary,mode,path,seed,limit)
    except RuntimeError as err:
        return dict(answer='ERROR',elapsed_s=limit,native_s='',error=str(err)[:350])
    return dict(answer=r['answer'],elapsed_s=r['wall_s'],native_s=r['native_s'],
       observed=r.get('observed'),short5=r.get('short5'),
       short_fraction=r.get('short_fraction'),extended=r.get('extended'),
       resumed=r.get('resumed'),hints=r.get('phases'),error=r.get('error',''))

def run_kissat(binary,path,limit):
    start=time.perf_counter()
    try:
        p=subprocess.run([str(binary),str(path)],capture_output=True,text=True,
                         timeout=limit,check=False)
    except subprocess.TimeoutExpired:
        return dict(answer='TIMEOUT',elapsed_s=limit,model_checked='',error='')
    elapsed=time.perf_counter()-start
    if p.returncode not in (0,10,20):
        return dict(answer='ERROR',elapsed_s=elapsed,model_checked='',
                    error=f'kissat exit={p.returncode}: {p.stderr[-250:]}')
    lines=[l.strip() for l in p.stdout.splitlines()]
    sat=any(l=='s SATISFIABLE' for l in lines)
    unsat=any(l=='s UNSATISFIABLE' for l in lines)
    if sat==unsat:
        return dict(answer='ERROR',elapsed_s=elapsed,model_checked='',
                    error='Kissat missing/ambiguous result: '+p.stdout[-200:])
    witness='N/A'
    if sat:
        try:
            if not check_witness(path,p.stdout):
                raise RuntimeError('Kissat did not emit checkable SAT witness')
        except Exception as e:
            return dict(answer='ERROR',elapsed_s=elapsed,model_checked=False,
                        error='Kissat SAT model not certified: '+str(e)[:230])
        witness=True
    return dict(answer='SAT' if sat else 'UNSAT',elapsed_s=elapsed,
                model_checked=witness,error='')

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--native',required=True)
    p.add_argument('--kissat',required=True)
    p.add_argument('--sources',required=True)
    p.add_argument('--outdir',required=True)
    p.add_argument('--timeout',type=float,default=60.)
    p.add_argument('--repeats',type=int,default=2)
    args=p.parse_args()
    assert args.timeout==TIMEOUT and args.repeats==2
    entries=json.loads(Path(args.sources).read_text())
    assert len(entries)==2
    out=Path(args.outdir);out.mkdir(parents=True,exist_ok=True)
    allrows=[];summary={}
    with (out/'raw.csv').open('w',newline='',encoding='utf8') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader()
        for idx,entry in enumerate(entries):
            path=Path(entry['path'])
            assert hashlib.sha256(path.read_bytes()).hexdigest()==entry['sha256']
            case=entry['id'];known=None
            for rep in range(args.repeats):
                methods=list(MODES)
                random.Random(77072026+int(case[:8],16)+rep*2111).shuffle(methods)
                for mode in methods:
                    if mode=='kissat404':r=run_kissat(args.kissat,path,TIMEOUT)
                    else:r=run_native(args.native,mode,path,
                                      (7707000+rep*527+int(case[:8],16))%2**32,TIMEOUT)
                    if r['answer'] in ('SAT','UNSAT'):
                        if known is not None and r['answer']!=known:
                            raise RuntimeError('CONTRADICTION across solvers: '+case+
                                ' expected '+known+' got '+r['answer']+' '+mode)
                        known=r['answer']
                    row={key:r.get(key,'') for key in FIELDS}
                    row.update(case=case,family='SATComp2026Main',
                               method=mode,repeat=rep,source_sha256=entry['sha256'],
                               cutoff_s=TIMEOUT)
                    allrows.append(row);w.writerow(row);f.flush()
                    print('TRIAL',case,'repeat',rep,mode,r['answer'],
                           round(float(r['elapsed_s']),4),'s',r.get('error','')[:120],flush=True)
            summary[case]=known or 'NOT_SOLVED'
            print('CASE',idx+1,'/2',case,'verified_status',summary[case],flush=True)
    (out/'case_statuses.json').write_text(json.dumps(summary,indent=2))
    print('SUCCESSFULLY MEASURED',len(allrows),'TRIALS, 2 official CNFs',flush=True)

if __name__=='__main__':main()
