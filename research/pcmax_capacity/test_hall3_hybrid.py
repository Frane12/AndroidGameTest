#!/usr/bin/env python3
"""Proof-first hybrid BDD+mutex fixtures, SAT controls, permutations & forgeries."""
import argparse
import hashlib
import json
import itertools
import random
import subprocess
from pathlib import Path
from check_hall3_hybrid import verify, InvalidCertificate

def instance(n=4, mutex=True, scramble=None):
    x=[i+1 for i in range(n)]
    y=[n+i+1 for i in range(n)]
    clauses=[]
    for a,b in zip(x,y):
        clauses.extend([(a,b),(-a,-b)])
    if mutex:
        clauses.extend([(-a,-b) for a,b in itertools.combinations(y,2)])
    nxt=2*n+1
    s={}
    for i in range(n):
        for count in ([0] if i==0 else [0,1]):
            s[i,count]=nxt;nxt+=1
    accept=nxt;reject=nxt+1;nxt+=2
    clauses.extend([(s[0,0],),(accept,),(-reject,)])
    for (i,count),parent in s.items():
        lo=(s[i+1,count] if i+1<n else accept)
        hi=(reject if count==1 else (s[i+1,1] if i+1<n else accept))
        clauses.extend([(-parent,x[i],lo),(-parent,-x[i],hi)])
    if scramble is not None:
        rng=random.Random(scramble)
        shuffled=list(range(1,nxt));rng.shuffle(shuffled)
        rename={old:new for old,new in zip(range(1,nxt),shuffled)}
        clauses=[tuple(rename[abs(v)]*(1 if v>0 else -1) for v in c) for c in clauses]
        rng.shuffle(clauses)
    return clauses

def write(path,clauses):
    n=max(abs(v) for c in clauses for v in c)
    raw=(f'p cnf {n} {len(clauses)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in clauses)).encode('ascii')
    path.write_bytes(raw);return raw

def call(binary,src,cert,flag):
    p=subprocess.run([str(binary.resolve()),str(src.resolve()),'--mode','core',
        '--time','2.0','--pcmax-only',flag,'--pcmax-budget-ms','400',
        '--pcmax-certificate',str(cert.resolve())],capture_output=True,text=True,timeout=8)
    tele=[json.loads(t[len('c PCMAX_CAPACITY '):]) for t in p.stdout.splitlines()
          if t.startswith('c PCMAX_CAPACITY ')]
    return p.returncode,(tele[-1] if tele else {}),p.stderr

def test(binary,out):
    out.mkdir(parents=True,exist_ok=False)
    cases=[('hybrid_unsat_n4',instance(4),False),
           ('hybrid_sat_n2',instance(2),True),
           ('hybrid_sat_n4_no_mutex',instance(4,mutex=False),True)]
    cases += [(f'hybrid_unsat_permutation_{i}',instance(4,scramble=i),False)
              for i in range(10)]
    rows=[]
    for name,clauses,sat in cases:
        inp=out/(name+'.cnf');raw=write(inp,clauses)
        armrows=[]
        for flag in ('--pcmax-clause-guard','--pcmax-hall2','--pcmax-capacity','--pcmax-hall3'):
            cert=out/(name+'-'+flag[2:]+'.json')
            rc,tele,stderr=call(binary,inp,cert,flag)
            if sat or flag!='--pcmax-hall3':
                assert rc==0 and not cert.exists(),(name,flag,rc,tele,stderr)
                status='UNKNOWN'
            else:
                assert rc==20 and cert.is_file(),(name,flag,rc,tele,stderr)
                proof=json.loads(cert.read_text())
                evidence=verify(raw,proof)
                assert evidence['status']=='UNSAT_HALL3_INDEPENDENTLY_VERIFIED'
                assert evidence['required']>evidence['capacity']
                if name=='hybrid_unsat_n4':
                    for corrupt in ('sha','capacity','clique','transition','cover'):
                        forged=json.loads(json.dumps(proof))
                        if corrupt=='sha':forged['source_sha256']='0'*64
                        if corrupt=='capacity':forged['capacity_sum']+=1
                        if corrupt=='clique':forged['resource_cliques'][0].append(99999)
                        if corrupt=='transition':forged['machines'][0]['transitions'][0][2]=99999
                        if corrupt=='cover':forged['resource_cliques'][0].pop()
                        try:verify(raw,forged)
                        except (InvalidCertificate,KeyError,ValueError,TypeError,IndexError):pass
                        else:raise AssertionError('Forged certificate accepted: '+corrupt)
                status='UNSAT_INDEPENDENTLY_VERIFIED'
            armrows.append({'arm':flag,'status':status,'reason':tele.get('reason'),
                            'wall_s':tele.get('total_elapsed_s')})
        row={'case':name,'expected_sat':sat,'source_sha256':hashlib.sha256(raw).hexdigest(),
             'arms':armrows}
        rows.append(row)
        print('HALL3_FIXTURE '+json.dumps(row,sort_keys=True),flush=True)
    summary={'cases':len(cases),'hybrid_unsat_verified':sum(not x['expected_sat'] for x in rows),
             'sat_controls':sum(x['expected_sat'] for x in rows),'false_unsat':0,
             'old_methods_misses':sum(not x['expected_sat'] for x in rows)*3}
    (out/'report.json').write_text(json.dumps({'summary':summary,'rows':rows},indent=2)+'\n')
    print('HALL3_FIXTURE_SUMMARY '+json.dumps(summary,sort_keys=True),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--binary',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();test(a.binary,a.output)
