#!/usr/bin/env python3
"""Native mixed-width CNF controls + externally checked source-only VeriPB.
Development-generated, never presented as blind industry evidence.
"""
import argparse,hashlib,itertools,json,random,subprocess,sys,time
from pathlib import Path
from verify_clique import verify

UNSAT_DOMAINS=[[0,1],[1,2],[0,1,3],[0,2,3],[0,1,2,3]]
SAT_DOMAINS=[[0,1],[1,2],[0,2,3],[0,1,2,3]]

def generated(domains,seed):
    rng=random.Random(seed);assignment={};clauses=[];per_slot={}
    for job,options in enumerate(domains):
        job_vars=[]
        for slot in options:
            lit=len(assignment)+1;assignment[job,slot]=lit
            job_vars.append(lit);per_slot.setdefault(slot,[]).append(lit)
        clauses.append(job_vars)
        for a,b in itertools.combinations(job_vars,2):clauses.append([-a,-b])
    for vs in per_slot.values():
        for a,b in itertools.combinations(vs,2):clauses.append([-a,-b])
    perm=list(range(1,len(assignment)+1));rng.shuffle(perm)
    clauses=[[perm[abs(v)-1]*(1 if v>0 else -1) for v in cl] for cl in clauses]
    for cl in clauses:rng.shuffle(cl)
    rng.shuffle(clauses)
    return (f'p cnf {len(assignment)} {len(clauses)}\n'+
            ''.join(' '.join(map(str,cl))+' 0\n' for cl in clauses)).encode()

def test(binary,checker,out):
    out.mkdir(parents=True,exist_ok=True);rows=[]
    for idx in range(16):
        unsat=idx<8;label='UNSAT' if unsat else 'SAT'
        source=generated(UNSAT_DOMAINS if unsat else SAT_DOMAINS,9027+idx*107)
        case=out/f'{idx:02d}';case.mkdir(exist_ok=True)
        cnf=case/'original.cnf';cnf.write_bytes(source)
        cert=case/'certificate.json';proof=case/'proof.pbp'
        started=time.perf_counter()
        p=subprocess.run([str(binary),str(cnf),'--mode','core','--time','4',
            '--pcmax-clique-only','--pcmax-clique-budget-ms','2500',
            '--pcmax-certificate',str(cert)],capture_output=True,text=True,timeout=8)
        native_s=time.perf_counter()-started
        got='UNSAT' if p.returncode==20 else 'UNKNOWN' if p.returncode==0 else 'ERROR'
        if unsat:
            assert got=='UNSAT' and cert.exists(),(idx,got,p.stdout[-2000:])
            result=verify(source,json.loads(cert.read_text()))
            assert result['required']==5 and result['capacity']==4
            emit=subprocess.run([sys.executable,str(Path(__file__).with_name('emit_veripb_clique.py')),
                '--cnf',str(cnf),'--certificate',str(cert),'--output',str(proof)],
                capture_output=True,text=True,timeout=15)
            assert emit.returncode==0,(idx,emit.stderr)
            external=subprocess.run([str(checker),'--cnf',str(cnf),str(proof)],
                capture_output=True,text=True,timeout=30)
            assert external.returncode==0 and 's VERIFIED UNSATISFIABLE' in external.stdout+external.stderr, (idx,external.stdout,external.stderr)
            details=json.loads(cert.read_text())
            forged=dict(details);forged['capacity']=details['demand']
            try:verify(source,forged)
            except ValueError:pass
            else:raise AssertionError('forged capacity accepted')
        else:
            assert got=='UNKNOWN' and not cert.exists(),(idx,got,p.stdout[-2000:])
        row={'index':idx,'label':label,'native':got,'native_s':round(native_s,5),
            'standard_veripb_accepted':bool(unsat),'sha256':hashlib.sha256(source).hexdigest()}
        print('MIXED_TEST '+json.dumps(row,sort_keys=True),flush=True)
        rows.append(row)
    (out/'summary.json').write_text(json.dumps(rows,indent=2,sort_keys=True)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--binary',type=Path,required=True)
    p.add_argument('--veripb',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();test(a.binary.resolve(),a.veripb.resolve(),a.output)
