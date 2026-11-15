#!/usr/bin/env python3
"""Second, certificate-free audit for the odd-degree original count21 formula.
Independently reads original clauses. No Gaussian elimination or producer code.
Also constructs satisfying assignments after removing essential premises.
"""
import argparse, collections, hashlib, itertools, json, os, random, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from test_bridge import raw_cnf,call,transform,satisfies
from check_math5 import verify,InvalidProof

def main():
    a=argparse.ArgumentParser();a.add_argument('--cnf',type=Path,required=True)
    a.add_argument('--certificate',type=Path,required=True);a.add_argument('--binary',type=Path,required=True)
    a.add_argument('--out',type=Path,required=True);args=a.parse_args();args.out.mkdir(parents=True,exist_ok=False)
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    raw=args.cnf.read_bytes();original=[];n=nc=None;pending=[]
    for line in raw.decode('ascii').splitlines():
        v=line.split()
        if not v or v[0]=='c':continue
        if v[0]=='p':n,nc=map(int,v[2:]);continue
        for x in map(int,v):
            if x:pending.append(x)
            else:original.append(tuple(pending));pending=[]
    assert len(original)==nc and not pending
    source=set(map(frozenset,original))
    groups=[list(c) for c in original if len(c)>2 and all(x>0 for x in c)]
    for g in groups:
        assert all(frozenset((-a,-b)) in source for a,b in itertools.combinations(g,2))
    counts=collections.Counter(x for g in groups for x in g)
    assert len(groups)==25 and len(counts)==300 and set(counts.values())=={2}
    # Each source group sums to 1. Summing all 25 equations gives 2*sum(x)=25.
    audit=dict(source_sha256=hashlib.sha256(raw).hexdigest(),variables=n,clauses=nc,
               source_alo_groups=len(groups),each_group_width=24,checked_mutex_pairs=sum(len(g)*(len(g)-1)//2 for g in groups),
               distinct_variables=len(counts),every_variable_multiplicity=2,integer_equation='2 * sum(x_1,...,x_300) = 25',
               status='UNSAT_BY_EVEN_EQUALS_ODD',certificate_used=False)
    cert=json.loads(args.certificate.read_text());verify(raw,cert)
    mut_reject=0
    altered=json.loads(json.dumps(cert));altered['exact_one_groups'].pop()
    try:verify(raw,altered)
    except InvalidProof:mut_reject+=1
    else:raise AssertionError('incomplete parity proof accepted')
    incident=collections.defaultdict(list)
    for i,g in enumerate(groups):
        for v in g:incident[v].append(i)
    edge={tuple(sorted(ij)):v for v,ij in incident.items()}
    # Pair two edges at vertex 0, then pair all remaining 22 vertices.
    a,b=groups[0][:2];covered=set(incident[a]+incident[b]);assert len(covered)==3
    remaining=sorted(set(range(25))-covered)
    selected={a,b}|{edge[tuple(remaining[i:i+2])] for i in range(0,len(remaining),2)}
    cases=[('missing_mutex',[c for c in original if frozenset(c)!=frozenset((-a,-b))],{v:v in selected for v in range(1,n+1)})]
    remaining=list(range(1,25));selected={edge[tuple(remaining[i:i+2])] for i in range(0,len(remaining),2)}
    cases.append(('missing_alo',[c for c in original if frozenset(c)!=frozenset(groups[0])],{v:v in selected for v in range(1,n+1)}))
    sat_results=[]
    for name,cs,model in cases:
        assert satisfies(cs,model)
        newraw=raw_cnf(n,cs);path=args.out/(name+'.cnf');path.write_bytes(newraw)
        path.with_suffix('.model.json').write_text(json.dumps(model))
        forged={**cert,'source_sha256':hashlib.sha256(newraw).hexdigest()}
        try:verify(newraw,forged)
        except InvalidProof:mut_reject+=1
        else:raise AssertionError('missing source premise accepted')
        rc,wall,tele=call(args.binary,path,args.out/(name+'.cert.json'),'--math5',750)
        assert rc==0,(name,'false UNSAT')
        sat_results.append(dict(name=name,explicit_model_verified=True,native_status='UNKNOWN',seconds=wall))
    rng=random.Random(2026111501);permutations=[]
    for k in range(16):
        cs,_=transform(n,original,None,rng);newraw=raw_cnf(n,cs)
        path=args.out/f'permuted-{k}.cnf';proof=args.out/f'permuted-{k}.json';path.write_bytes(newraw)
        rc,wall,tele=call(args.binary,path,proof,'--math5',750)
        assert rc==20
        checked=verify(newraw,json.loads(proof.read_text()))
        permutations.append(dict(index=k,verified=True,seconds=wall,certificate=checked))
    audit.update(sat_controls=sat_results,signed_variable_and_clause_permutations_verified=len(permutations),
                 rejected_mutations=mut_reject,permutations=permutations)
    (args.out/'summary.json').write_text(json.dumps(audit,indent=2));print(json.dumps({k:v for k,v in audit.items() if k!='permutations'},indent=2))
if __name__=='__main__':main()
