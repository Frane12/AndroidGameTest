#!/usr/bin/env python3
"""Proof-first HALL2 test: hidden subset deficiency, SAT control, renamings."""
import argparse, hashlib, itertools, json, os, random, subprocess, sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from check_clause_hall import check, InvalidCertificate

def cnf_case(sat=False,seed=None):
    # 3 groups and 3 slots globally; groups B,C both require slot 0.
    # HALL1 starts with each literal as a separate slot and misses B,C.
    # HALL2 finds the exact 2 jobs / 1 resource subset.
    groups=[[1,2,3],[4,5],[6,7]]
    clauses=[tuple(g) for g in groups]
    for a,b in itertools.combinations([1,4,5,6,7],2):
        if sat and {a,b}=={4,6}:continue
        clauses.append((-a,-b))
    if seed is not None:
        rng=random.Random(seed)
        ids=list(range(1,8));rng.shuffle(ids)
        perm={i+1:ids[i] for i in range(7)}
        clauses=[tuple(perm[abs(x)] if x>0 else -perm[abs(x)] for x in c) for c in clauses]
        rng.shuffle(clauses)
    return clauses

def raw_cnf(clauses):
    n=max(abs(x) for c in clauses for x in c)
    return (f'p cnf {n} {len(clauses)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in clauses)).encode()

def brute_sat(clauses):
    n=max(abs(x) for c in clauses for x in c)
    for mask in range(1<<n):
        if all(any(bool(mask & (1 << (abs(x)-1))) == (x>0) for x in c) for c in clauses):
            return True
    return False

def run(binary,src,cert,mode):
    args=[str(binary.resolve()),str(src.resolve()),'--mode','core','--time','3',
          mode,'--pcmax-only','--pcmax-budget-ms','600',
          '--pcmax-certificate',str(cert.resolve())]
    p=subprocess.run(args,capture_output=True,text=True,timeout=10)
    tele=[json.loads(s[len('c PCMAX_CAPACITY '):]) for s in p.stdout.splitlines()
          if s.startswith('c PCMAX_CAPACITY ')]
    return p.returncode,(tele[-1] if tele else {}),p.stderr

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--binary',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    cases=[('subset_unsat',cnf_case(),False),
           ('subset_sat_one_missing_mutex',cnf_case(sat=True),True)]
    cases.extend((f'renamed_{i}',cnf_case(seed=i),False) for i in range(12))
    report=[]
    for name,clauses,sat in cases:
        raw=raw_cnf(clauses)
        assert brute_sat(clauses)==sat,name
        inp=args.output/(name+'.cnf');inp.write_bytes(raw)
        rows=[]
        for flag in ('--pcmax-clause-guard','--pcmax-hall2'):
            cert=args.output/(name+('-h1.json' if flag=='--pcmax-clause-guard' else '-h2.json'))
            rc,tele,stderr=run(args.binary,inp,cert,flag)
            if sat:
                assert rc==0 and not cert.exists(),(name,flag,rc,tele,stderr)
                outcome='SAT_UNKNOWN'
            elif flag=='--pcmax-clause-guard':
                assert rc==0 and not cert.exists(),(name,flag,rc,tele,stderr)
                outcome='BASELINE_HALL1_MISS'
            else:
                assert rc==20 and cert.is_file(),(name,rc,tele,stderr)
                proof=json.loads(cert.read_text())
                verified=check(raw,proof)
                assert verified['status']=='UNSAT_CLAUSE_HALL_CERTIFICATE_VERIFIED'
                assert verified['required_groups']==2 and verified['resource_bound']==1
                outcome='HALL2_INDEPENDENTLY_VERIFIED'
                if name=='subset_unsat':
                    forged=json.loads(json.dumps(proof))
                    forged['source_sha256']='0'*64
                    try:check(raw,forged)
                    except (InvalidCertificate,KeyError,ValueError):pass
                    else:raise AssertionError('forged source accepted')
                    forged=json.loads(json.dumps(proof))
                    forged['resource_cliques'][0].append(9999)
                    try:check(raw,forged)
                    except (InvalidCertificate,KeyError,ValueError):pass
                    else:raise AssertionError('forged clique accepted')
                    forged=json.loads(json.dumps(proof))
                    forged['alo_groups'][0][0]*=-1
                    try:check(raw,forged)
                    except (InvalidCertificate,KeyError,ValueError):pass
                    else:raise AssertionError('forged demand accepted')
            rows.append({'arm':flag,'outcome':outcome,'reason':tele.get('reason'),
                         'wall_s':tele.get('total_elapsed_s')})
        row={'case':name,'known_sat':sat,'source_sha256':hashlib.sha256(raw).hexdigest(),
             'arms':rows}
        report.append(row)
        print('HALL2_CASE '+json.dumps(row,sort_keys=True),flush=True)
    summary={'cases':len(report),'certified_hall2_unsat':sum(not x['known_sat'] for x in report),
             'false_unsat':0,'sat_controls':sum(x['known_sat'] for x in report),
             'hall1_misses':sum(not x['known_sat'] for x in report)}
    (args.output/'report.json').write_text(json.dumps({'summary':summary,'cases':report},indent=2)+'\n')
    print('HALL2_SUMMARY '+json.dumps(summary,sort_keys=True),flush=True)

if __name__=='__main__':main()
