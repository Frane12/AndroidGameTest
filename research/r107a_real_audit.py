#!/usr/bin/env python3
"""R107-A verification against 8 externally SHA-pinned Comp2025 CNFs."""
import csv,hashlib,json,pathlib,subprocess,sys
def main():
    if len(sys.argv)!=2:raise SystemExit('usage: r107a_real_audit.py OUTDIR')
    root=pathlib.Path(sys.argv[1]);man=json.loads((root/'manifest.json').read_text())
    report=[]
    for case in man:
        path=root/'source'/case['name']
        if hashlib.sha256(path.read_bytes()).hexdigest()!=case['sha256']:
            raise RuntimeError('R107A SHA mismatch '+case['name'])
        out=root/'r107a'/(case['name']+'.json')
        out.parent.mkdir(parents=True,exist_ok=True)
        p=subprocess.run(['python3','research/r107a_xor_finder.py','inspect',
             '--cnf',str(path),'--out',str(out)],
             capture_output=True,text=True,timeout=150)
        if p.returncode:
            raise RuntimeError('R107A FAIL CLOSED '+case['name']+' '+p.stderr[-1500:])
        r=json.loads(out.read_text())
        if r['sha256']!=case['sha256']:raise RuntimeError('R107A source hash changed')
        # Actual legacy R105 parity finding, not inferred from labels.
        legacy=root/'r107a'/(case['name']+'.r105.json')
        q=subprocess.run(['python3','research/r105_gf2_contradiction_only.py',
                'export','--cnf',str(path),'--out',str(root/'r107a'/(case['name']+'.r105.cnf')),
                '--evidence',str(legacy)],
                capture_output=True,text=True,timeout=45)
        if q.returncode==0:
            old=json.loads(legacy.read_text());legacy_count=old['original_xors']
            if legacy_count!=r['old_three_xor_count']:
                raise RuntimeError('R107A mismatch to frozen R105 XOR3 extraction')
            legacy_proof=old['contradiction'];legacy_status='OK'
        else:
            legacy_count='';legacy_proof='';legacy_status='UNSUPPORTED'
        entry=dict(formula=case['name'],sha256=case['sha256'],
             expected=case['expected'],r105_xors=legacy_count,
             r105_proved_unsat=legacy_proof,r105_status=legacy_status,
             r107a_xors=r['found_xors'],
             xor2=r['by_width']['2'],xor3=r['by_width']['3'],
             xor4=r['by_width']['4'],xor5=r['by_width']['5'],
             xor6=r['by_width']['6'],gf2_rank=r['gf2_rank'],
             r107a_proved_unsat=r['gf2_unsat'],
             r107a_s=r['elapsed_s'],proof_length=len(r['proof_equation_ids']))
        if case['expected']=='SAT' and r['gf2_unsat']:
            raise RuntimeError('R107A FAIL CLOSED incorrect proof on known SAT')
        report.append(entry)
        print('R107A_CASE',json.dumps(entry),flush=True)
    with (root/'r107a-paired.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(report[0]))
        w.writeheader();w.writerows(report)
    summ=dict(protocol='R107A-CERTIFIED-CNF-XOR-2-6-COMP2025',
        real_cases=len(report),old_xor3=sum(int(r['r105_xors'])
            for r in report if r['r105_xors']!=''),
        old_unsupported=sum(r['r105_status']!='OK' for r in report),
        new_xors=sum(r['r107a_xors'] for r in report),
        new_by_width={str(k):sum(r['xor'+str(k)] for r in report)
                      for k in range(2,7)},
        new_verified_GF2_UNSAT=sum(r['r107a_proved_unsat'] for r in report),
        note='Independent full-clauses parity replay. R107A is a parser plus root GF2 proof pilot, not an in-process replacement nor blind SAT Competition 2026 holdout. Only exact complete k-XOR patterns k<=6; no shortened-clause pattern reconstruction.')
    (root/'r107a-summary.json').write_text(json.dumps(summ,indent=2))
    print('R107A_COMPLETE_AUDIT',json.dumps(summ),flush=True)
if __name__=='__main__':main()
