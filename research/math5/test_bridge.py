#!/usr/bin/env python3
"""Deterministic designed fixtures, SAT witnesses, brute-force fuzz, proof mutations.
Not a blind competition benchmark. One logical CPU, serial native processes.
"""
from __future__ import annotations
import argparse, copy, hashlib, itertools, json, os, random, subprocess, sys, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from check_math5 import verify, InvalidProof

SEED=20261115

def raw_cnf(n,clauses):
    return (f'p cnf {n} {len(clauses)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in clauses)).encode()

def encode_xor(vs,rhs):
    return [[-v if b else v for v,b in zip(vs,bits)]
            for bits in itertools.product((0,1),repeat=len(vs)) if (sum(bits)&1)!=rhs]

def fixture(groups,width,sat):
    vs=list(range(1,groups*width+1));clauses=[];model={}
    for i in range(groups):
        g=vs[i*width:(i+1)*width]
        clauses.append(g);clauses.extend([[-a,-b] for a,b in itertools.combinations(g,2)])
        model.update({v:j==0 for j,v in enumerate(g)})
    target=(groups&1) ^ int(not sat)
    n=len(vs)
    if len(vs)<=6:
        clauses+=encode_xor(vs,target)
    else:
        prev=vs[0]
        for v in vs[1:-1]:
            n+=1;clauses+=encode_xor([prev,v,n],0)
            model[n]=model[prev]^model[v];prev=n
        clauses+=encode_xor([prev,vs[-1]],target)
    return n,clauses,model if sat else None

def transform(n,clauses,model,rng):
    order=list(range(1,n+1));rng.shuffle(order)
    flip={i:rng.choice((1,-1)) for i in range(1,n+1)}
    mapping={i:order[i-1]*flip[i] for i in range(1,n+1)}
    result=[[mapping[abs(l)]*(1 if l>0 else -1) for l in c] for c in clauses]
    for c in result:rng.shuffle(c)
    rng.shuffle(result)
    witness=None if model is None else {abs(mapping[i]):bool(model[i])^(mapping[i]<0) for i in range(1,n+1)}
    return result,witness

def satisfies(clauses,model):
    return all(any(model[abs(l)]==(l>0) for l in c) for c in clauses)

def brute(n,clauses):
    for bits in itertools.product((False,True),repeat=n):
        model=dict(enumerate(bits,1))
        if satisfies(clauses,model):return model
    return None

def call(binary,cnf,cert,flag,ms=100):
    cmd=[str(binary.resolve()),str(cnf.resolve()),'--mode','core','--time','2',flag,
         '--pcmax-only','--pcmax-budget-ms',str(ms),'--pcmax-certificate',str(cert.resolve())]
    start=time.perf_counter()
    p=subprocess.run(cmd,text=True,capture_output=True,timeout=4)
    elapsed=time.perf_counter()-start
    tele=[json.loads(l.removeprefix('c PCMAX_CAPACITY ')) for l in p.stdout.splitlines() if l.startswith('c PCMAX_CAPACITY ')]
    if p.returncode not in (0,20):raise AssertionError((cmd,p.returncode,p.stdout,p.stderr))
    return p.returncode,elapsed,tele[-1] if tele else {}

def main():
    a=argparse.ArgumentParser();a.add_argument('--binary',type=Path,required=True)
    a.add_argument('--baseline',type=Path,required=True);a.add_argument('--out',type=Path,required=True)
    args=a.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    cpu=min(os.sched_getaffinity(0));os.sched_setaffinity(0,{cpu})
    rng=random.Random(SEED);cases=[]
    for sat in (False,True):
        for groups in (1,2,3,5,8,12,20,32):
            for width in (3,4,5,6):
                for transformed in (False,True):
                    n,cs,model=fixture(groups,width,sat)
                    if transformed:cs,model=transform(n,cs,model,rng)
                    cases.append((f'bridge_{int(sat)}_{groups}_{width}_{int(transformed)}',n,cs,model,'designed_mixed'))
    for kind in ('missing_alo','missing_mutex'):
        for k in range(16):
            n,cs,_=fixture(1,3,False)
            if kind=='missing_alo':cs=cs[1:];model={1:False,2:False,3:False}
            else:cs.remove([-1,-2]);model={1:True,2:True,3:False}
            cs,model=transform(n,cs,model,rng)
            cases.append((f'{kind}_{k}',n,cs,model,'negative_control'))
    for k in range(128):
        n=rng.randint(3,8)
        cs=[[v*rng.choice((-1,1)) for v in rng.sample(range(1,n+1),rng.randint(2,min(4,n)))] for _ in range(rng.randint(3,35))]
        model=brute(n,cs)
        cases.append((f'bruteforce_{k}',n,cs,model,'bruteforce_fuzz'))
    manifest=[dict(name=name,nvars=n,clauses=len(cs),label='SAT' if model is not None else 'UNSAT',family=fam,
                   sha256=hashlib.sha256(raw_cnf(n,cs)).hexdigest()) for name,n,cs,model,fam in cases]
    (args.out/'manifest.json').write_text(json.dumps(manifest,indent=2))
    rows=[]; mutations=0
    for ix,(name,n,cs,model,fam) in enumerate(cases):
        if model is not None:assert satisfies(cs,model),(name,'bad witness')
        raw=raw_cnf(n,cs);cnf=args.out/(name+'.cnf');cnf.write_bytes(raw)
        row=dict(manifest[ix]);row['arms']={}
        for arm,binary,flag in (('MATH4',args.baseline,'--math4'),('MATH5',args.binary,'--math5')):
            cert=args.out/(name+'.'+arm+'.json')
            rc,wall,tele=call(binary,cnf,cert,flag)
            entry=dict(rc=rc,wall_s=wall,telemetry=tele,verified=False)
            if rc==20:
                assert model is None,(name,arm,'FALSE UNSAT')
                proof=json.loads(cert.read_text())
                if proof['format']=='drnas-math5-eo-xor-unit-v1':
                    start=time.perf_counter();checked=verify(raw,proof);entry['checker_s']=time.perf_counter()-start
                    entry['proof']=checked;entry['verified']=True
                    forged=copy.deepcopy(proof);forged['source_sha256']='0'*64
                    try:verify(raw,forged)
                    except InvalidProof:mutations+=1
                    else:raise AssertionError('tampered hash accepted')
                    if proof['exact_one_groups']:
                        g=proof['exact_one_groups'][0];pair=frozenset((-g[0],-g[1]))
                        changed=[c for c in cs if frozenset(c)!=pair]
                        changed_raw=raw_cnf(n,changed);forged=copy.deepcopy(proof)
                        forged['source_sha256']=hashlib.sha256(changed_raw).hexdigest()
                        try:verify(changed_raw,forged)
                        except InvalidProof:mutations+=1
                        else:raise AssertionError('removed mutex accepted')
                        forged=copy.deepcopy(proof);forged['exact_one_groups'][0][0]*=-1
                        try:verify(raw,forged)
                        except InvalidProof:mutations+=1
                        else:raise AssertionError('flipped signed group accepted')
                else:
                    # Existing guard proof format; use its original independent verifier.
                    if proof['format']=='drnas-math4-xor-unit-v1':
                        converted={**proof,'format':'drnas-math5-eo-xor-unit-v1','exact_one_groups':[]}
                        verify(raw,converted)
                    elif proof['format']=='pcmax-clause-hall-v1':
                        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pcmax_capacity'))
                        from check_clause_hall import check
                        check(raw,proof)
                    elif proof['format']=='pcmax-capacity-v1':
                        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pcmax_capacity'))
                        from check_capacity import check
                        check(raw,proof)
                    else:raise AssertionError(proof['format'])
                    entry['verified']=True
            else:assert not cert.exists()
            row['arms'][arm]=entry
        rows.append(row)
    summary=dict(seed=SEED,logical_cpu=cpu,cases=len(rows),sat_controls=sum(r['label']=='SAT' for r in rows),
                 unsat_cases=sum(r['label']=='UNSAT' for r in rows),false_unsat=0,rejected_mutations=mutations,
                 arms={arm:dict(certified=sum(r['arms'][arm]['verified'] for r in rows),
                                designed_mixed_certified=sum(r['family']=='designed_mixed' and r['arms'][arm]['verified'] for r in rows)) for arm in ('MATH4','MATH5')},
                 new_mixed_sources=sum(r['arms']['MATH5']['verified'] and not r['arms']['MATH4']['verified'] for r in rows),
                 note='Designed/fuzz guard-only experiment. Not a blind general-SAT speed/PAR2 comparison.')
    (args.out/'trials.json').write_text(json.dumps(rows,indent=2))
    (args.out/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
