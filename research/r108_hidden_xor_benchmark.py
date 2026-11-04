#!/usr/bin/env python3
"""R108 frozen real vs controlled hidden-XOR structural + solver experiments."""
import csv,hashlib,itertools,json,pathlib,subprocess,sys,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r106_verify_solver as checker

def parity(vs,rhs):
    return [tuple(-v if bits>>i&1 else v for i,v in enumerate(vs))
            for bits in range(1<<len(vs)) if bits.bit_count()%2!=rhs]
def hide(clauses,aux):
    return [tuple(c)+tuple(s*v for s,v in zip(signs,aux))
            for c in clauses for signs in itertools.product((1,-1),repeat=len(aux))]
def synthetic(out):
    root=out/'synthetic';root.mkdir(parents=True,exist_ok=True)
    v=(1,2,3,4)
    p0=parity(v,0);p1=parity(v,1)
    v5=(1,2,3,4,5)
    scenarios=[
      ('r108_plain4_sat',p0,4,'SAT'),
      ('r108_shortened4_sat',p0[:-1]+[p0[-1][:3]],4,'SAT'),
      ('r108_incomplete4_sat',p0[:-1],4,'SAT'),
      ('r108_hidden1_sat',hide(p0,(5,)),5,'SAT'),
      ('r108_hidden1_unsat',hide(p0,(5,))+hide(p1,(6,)),6,'UNSAT'),
      ('r108_hidden2_unsat',hide(p0,(5,6))+hide(p1,(7,8)),8,'UNSAT'),
      ('r108_hidden2_xor5_unsat',hide(parity(v5,0),(6,7))+
                              hide(parity(v5,1),(8,9)),9,'UNSAT'),
    ]
    items=[]
    for name,clauses,n,expected in scenarios:
        file=root/(name+'.cnf')
        file.write_text(f'p cnf {n} {len(clauses)}\n'+
             ''.join(' '.join(map(str,c))+' 0\n' for c in clauses))
        items.append(dict(name=file.name,expected=expected,
             sha256=hashlib.sha256(file.read_bytes()).hexdigest(),
             kind='controlled_hidden_xor',path=str(file)))
    return items
def evaluate(cmd,timeout):
    start=time.perf_counter()
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=timeout)
        elapsed=time.perf_counter()-start
        if p.returncode:
            return None,elapsed,(p.stderr or p.stdout)[-500:]
        return p,elapsed,''
    except subprocess.TimeoutExpired:
        return None,timeout,'TIMEOUT'
def solve(cadical,src,expected,timeout=6.):
    start=time.perf_counter()
    try:
        p=subprocess.run([cadical,str(src)],capture_output=True,text=True,
                         errors='replace',timeout=timeout)
        elapsed=time.perf_counter()-start
        result=checker.status(p.stdout,p.returncode)
        if result!=expected:
            raise RuntimeError('R108 mismatch against known SAT status')
        if result=='SAT' and not checker.model_valid(p.stdout,checker.cnf_clauses(src)):
            raise RuntimeError('R108 invalid SAT witness')
        return dict(status=result,seconds=round(elapsed,6))
    except subprocess.TimeoutExpired:
        return dict(status='TIMEOUT',seconds=timeout)
def main():
    if len(sys.argv)!=4:
        raise SystemExit('usage: r108_benchmark.py OUTPUT_DIR R107C_BINARY CADICAL_BINARY')
    out=pathlib.Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
    native,cadical=sys.argv[2:]
    originals=json.loads((out/'manifest.json').read_text())
    items=[dict(x,kind='SAT Competition 2025 SHA-pinned',
                path=str(out/'source'/x['name'])) for x in originals]+synthetic(out)
    (out/'r108-frozen-input-manifest.json').write_text(json.dumps(
        [{key:v for key,v in item.items() if key!='path'} for item in items],indent=2)+'\n')
    report=[]
    for case in items:
        source=pathlib.Path(case['path'])
        if hashlib.sha256(source.read_bytes()).hexdigest()!=case['sha256']:
            raise RuntimeError('R108 source SHA mismatch '+case['name'])
        stem=case['name']
        outputs=out/'r108';outputs.mkdir(exist_ok=True)
        base_dest=outputs/(stem+'.native.cnf')
        base_ev=outputs/(stem+'.native.json')
        native_p,native_s,native_err=evaluate(
            [native,str(source),str(base_dest),str(base_ev)],timeout=60)
        native_info=json.loads(base_ev.read_text()) if native_p else {}
        direct_ev=outputs/(stem+'.direct.json')
        compressed_p,compressed_s,compressed_err=evaluate(
            ['python3','research/r108_hidden_xor.py','inspect',
             '--cnf',str(source),'--rounds','0','--out',str(direct_ev)],timeout=55)
        compressed_info=json.loads(direct_ev.read_text()) if compressed_p else {}
        deep_dest=outputs/(stem+'.deep.cnf')
        deep_ev=outputs/(stem+'.deep.json')
        deep_p,deep_s,deep_err=evaluate(
            ['python3','research/r108_hidden_xor.py','export',
             '--cnf',str(source),'--rounds','2',
             '--out',str(deep_ev),'--augmented',str(deep_dest)],timeout=55)
        deep_info=json.loads(deep_ev.read_text()) if deep_p else {}
        if deep_p:
            if deep_info['sha256']!=case['sha256']:
                raise RuntimeError('R108 scan SHA mismatch '+stem)
            if case['expected']=='SAT' and deep_info['gf2_unsat']:
                raise RuntimeError('R108 falsely proved UNSAT on known SAT '+stem)
            if not deep_info['gf2_unsat'] and source.read_bytes()!=deep_dest.read_bytes():
                raise RuntimeError('R108 rewrote source CNF without certificate '+stem)
            if deep_info['gf2_unsat'] and checker.cnf_clauses(deep_dest)[-1]!=():
                raise RuntimeError('R108 failed to append certified empty clause '+stem)
        if case['expected']=='SAT' and native_info.get('gf2_unsat',False):
            raise RuntimeError('R107C falsely proved UNSAT on known SAT '+stem)
        # Solver checks only when a certified contradiction was found.
        paired=[]
        if native_p and deep_p and (native_info.get('gf2_unsat') or
                                   deep_info.get('gf2_unsat')):
            for rep in range(2):
                for name,filename,prep in [('native',base_dest,native_s),
                                           ('deep',deep_dest,deep_s)]:
                    s=solve(cadical,filename,case['expected'],6.)
                    paired.append(dict(rep=rep,method=name,
                        status=s['status'],solver_s=s['seconds'],
                        full_s=round(s['seconds']+prep,6),
                        PAR2=round(12 if s['status']=='TIMEOUT' else s['seconds']+prep,6)))
        entry=dict(formula=stem,kind=case['kind'],expected=case['expected'],
          sha256=case['sha256'],
          native_rows=native_info.get('source_xors',''),
          native_proof=native_info.get('gf2_unsat',''),
          native_prep_s=round(native_s,6),
          direct_rows=compressed_info.get('certified_rows',''),
          direct_shortened=compressed_info.get('from_shortened_rows',''),
          direct_proof=compressed_info.get('gf2_unsat',''),
          direct_prep_s=round(compressed_s,6),
          r108_rows=deep_info.get('certified_rows',''),
          r108_from_resolution=deep_info.get('from_resolution_rows',''),
          r108_from_shortened=deep_info.get('from_shortened_rows',''),
          r108_proof=deep_info.get('gf2_unsat',''),
          r108_prep_s=round(deep_s,6),
          resolution_pairs=deep_info.get('resolution',{}).get('pairs_checked',''),
          budget_limited=deep_info.get('budget_truncated',''),
          errors=' | '.join(x for x in (native_err,compressed_err,deep_err) if x),
          timed_solver=paired)
        report.append(entry)
        print('R108_CASE',json.dumps(entry),flush=True)
    with (out/'r108-results.csv').open('w',newline='') as f:
        keys=[k for k in report[0] if k!='timed_solver']
        w=csv.DictWriter(f,fieldnames=keys,extrasaction='ignore');w.writeheader();w.writerows(report)
    summary=dict(protocol='R108-HIDDEN-XOR-RESOLUTION-AUDIT',
      real_cases=sum(x['kind'].startswith('SAT Competition') for x in report),
      controlled_cases=sum(x['kind']=='controlled_hidden_xor' for x in report),
      real_xor_native=sum(x['native_rows'] for x in report if x['kind'].startswith('SAT Competition') and isinstance(x['native_rows'],int)),
      real_xor_r108=sum(x['r108_rows'] for x in report if x['kind'].startswith('SAT Competition') and isinstance(x['r108_rows'],int)),
      proven_real_unsat=sum(x['r108_proof'] is True for x in report if x['kind'].startswith('SAT Competition')),
      new_controlled_proofs=sum(x['r108_proof'] is True and x['native_proof'] is False for x in report if x['kind']=='controlled_hidden_xor'),
      errors=sum(bool(x['errors']) for x in report),
      notes='R108 2-round bounded resolution + shortened-clause XOR implication certificates. Unknown XOR rows/proofs are not counted as solved. Scan can be deliberately truncated and is not an exhaustive algorithm. This is a development experiment, not an official 2026 blind holdout.')
    (out/'r108-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print('R108_COMPLETE_AUDIT',json.dumps(summary),flush=True)
if __name__=='__main__':main()
