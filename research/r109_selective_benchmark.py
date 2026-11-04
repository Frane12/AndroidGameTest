#!/usr/bin/env python3
"""R109 external and controlled tests; frozen R107C vs native selective XOR.

Full timing includes each preprocessor subprocess; no speedups inferred from
formula counts. Only formulas having verified GF2 UNSAT are solved (2 repeats).
"""
import csv,hashlib,json,pathlib,subprocess,sys,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r106_verify_solver as check
import r108_hidden_xor_benchmark as corpus
def execute(exe,source,dest,proof):
    start=time.perf_counter()
    try:
        p=subprocess.run([exe,str(source),str(dest),str(proof)],
                         capture_output=True,text=True,timeout=40)
    except subprocess.TimeoutExpired:
        raise RuntimeError('R109 preprocessor unexpectedly exceeded 40 seconds')
    wall=time.perf_counter()-start
    if p.returncode!=0:
        raise RuntimeError('R109_FAIL_CLOSED native error: '+p.stderr[-900:])
    return json.loads(proof.read_text()),wall
def main():
    if len(sys.argv)!=5:raise SystemExit('usage: R109_BENCH.py OUTPUT_DIR R107C_BINARY R109_BINARY CADICAL_BINARY')
    root=pathlib.Path(sys.argv[1]);root.mkdir(parents=True,exist_ok=True)
    base,fast,cadical=sys.argv[2:]
    source_manifest=json.loads((root/'manifest.json').read_text())
    items=[dict(x,path=str(root/'source'/x['name']),kind='real_satcomp2025')
           for x in source_manifest]
    items.extend(corpus.synthetic(root))
    (root/'r109-input-manifest.json').write_text(json.dumps(
        [{k:v for k,v in item.items() if k!='path'} for item in items],indent=2)+'\n')
    all_rows=[]
    for item in items:
        source=pathlib.Path(item['path'])
        digest=hashlib.sha256(source.read_bytes()).hexdigest()
        if digest!=item['sha256']:raise RuntimeError('R109 digest mismatch '+item['name'])
        out=root/'r109';out.mkdir(exist_ok=True)
        base_out=out/(item['name']+'.r107c.cnf')
        fast_out=out/(item['name']+'.r109.cnf')
        base_j=out/(item['name']+'.r107c.json')
        fast_j=out/(item['name']+'.r109.json')
        base_stat,base_wall=execute(base,source,base_out,base_j)
        fast_stat,fast_wall=execute(fast,source,fast_out,fast_j)
        if fast_stat['baseline_xors']!=base_stat['source_xors']:
            raise RuntimeError('R109 baseline XOR counts changed '+item['name'])
        if fast_stat['source_xors']<base_stat['source_xors']:
            raise RuntimeError('R109 dropped baseline rows '+item['name'])
        if base_stat['gf2_unsat'] and not fast_stat['gf2_unsat']:
            raise RuntimeError('R109 lost baseline UNSAT '+item['name'])
        if item['expected']=='SAT' and fast_stat['gf2_unsat']:
            raise RuntimeError('R109 proved UNSAT on known SAT '+item['name'])
        if not fast_stat['gf2_unsat'] and source.read_bytes()!=fast_out.read_bytes():
            raise RuntimeError('R109 changed CNF without proof '+item['name'])
        if fast_stat['gf2_unsat'] and check.cnf_clauses(fast_out)[-1]!=():
            raise RuntimeError('R109 proof has no empty clause '+item['name'])
        if hashlib.sha256(source.read_bytes()).hexdigest()!=digest:
            raise RuntimeError('R109 mutated original source '+item['name'])
        checks=[]
        # Measure CaDiCaL only for proof cases; unaffected CNF is unchanged.
        if base_stat['gf2_unsat'] or fast_stat['gf2_unsat']:
            for rep in range(2):
                for label,filename,prep in [('r107c',base_out,base_wall),
                                            ('r109',fast_out,fast_wall)]:
                    start=time.perf_counter()
                    p=subprocess.run([cadical,str(filename)],
                        capture_output=True,text=True,timeout=6)
                    spent=time.perf_counter()-start
                    status=check.status(p.stdout,p.returncode)
                    if status!=item['expected']:
                        raise RuntimeError('R109 solver mismatched known status '+item['name'])
                    checks.append(dict(rep=rep,mode=label,status=status,
                        solver_s=round(spent,6),total_s=round(spent+prep,6)))
        row=dict(formula=item['name'],kind=item['kind'],expected=item['expected'],
            sha256=digest,r107c_xors=base_stat['source_xors'],
            r109_xors=fast_stat['source_xors'],new_xors=fast_stat['new_xors'],
            r107c_gf2=base_stat['gf2_unsat'],r109_gf2=fast_stat['gf2_unsat'],
            derived=fast_stat['derived_clauses'],
            rounds=fast_stat['rounds'],
            candidates=fast_stat['candidate_groups'],
            truncated=fast_stat['selector_truncated'],
            gate=fast_stat['gate'],
            r107c_prep_s=round(base_wall,6),
            r109_prep_s=round(fast_wall,6),
            paired_solver=checks)
        all_rows.append(row)
        print('R109_CASE',json.dumps(row),flush=True)
    with (root/'r109-results.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=[k for k in all_rows[0] if k!='paired_solver'],
                         extrasaction='ignore')
        w.writeheader();w.writerows(all_rows)
    real=[row for row in all_rows if row['kind']=='real_satcomp2025']
    controlled=[row for row in all_rows if row['kind']!='real_satcomp2025']
    summary=dict(protocol='R109-SELECTIVE-NATIVE-TWIN-RESOLUTION-SAT2025',
      real_cases=len(real),controlled_cases=len(controlled),
      baseline_real_xors=sum(x['r107c_xors'] for x in real),
      r109_real_xors=sum(x['r109_xors'] for x in real),
      new_real_proofs=sum(x['r109_gf2'] and not x['r107c_gf2'] for x in real),
      new_controlled_proofs=sum(x['r109_gf2'] and not x['r107c_gf2'] for x in controlled),
      no_lost_baseline=True,
      notes='Certified identical-core binary resolution, up to two levels, bounded gate. This is R109 vs R107C, not R108 Python total. The formulas are already public 2025 competition, not independently unseen; only proof cases timed through CaDiCaL, all other cases structural counts only.')
    (root/'r109-summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print('R109_COMPLETE_AUDIT',json.dumps(summary),flush=True)
if __name__=='__main__':main()
