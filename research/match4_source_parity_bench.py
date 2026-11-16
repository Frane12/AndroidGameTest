#!/usr/bin/env python3
"""MATCH4 original-source weighted CNF pilot with mutation/SAT controls."""
import copy,hashlib,itertools,json,os,random
from pathlib import Path
from match4_source_parity import prove,read_cnf
from match4_source_parity_checker import check

RNG=random.Random(16112604)
OUT=Path('results/match4_source_parity')
ROWS=[]

def encode(edges,name,comments=True):
    edges=list(edges);n=len(edges);V=max(max(e) for e in edges)+1
    T=sum(3**v for v in range(V));weights=[3**u+3**v for u,v in edges]
    sums=[0]*(1<<n)
    for mask in range(1,1<<n):
        low=mask&-mask;j=low.bit_length()-1;sums[mask]=sums[mask^low]+weights[j]
    clauses=[]
    x=lambda j,m:3*j+m+1
    for j in range(n):
        clauses.append([x(j,m) for m in range(3)])
        for a,b in itertools.combinations(range(3),2):
            clauses.append([-x(j,a),-x(j,b)])
    for mask in range(1,1<<n):
        if sums[mask]>T and all(sums[mask^(1<<j)]<=T for j in range(n) if mask>>j&1):
            jobs=[j for j in range(n) if mask>>j&1]
            for m in range(3):clauses.append([-x(j,m) for j in jobs])
    prefix=(f'c {name}\n'+'c Item sizes: '+' '.join(map(str,weights))+'\n') if comments else ''
    return (prefix+f'p cnf {3*n} {len(clauses)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in clauses)).encode(),weights

def petersen():
    edges=[tuple(sorted((i,(i+1)%5))) for i in range(5)]
    edges += [(i,i+5) for i in range(5)]
    edges += [tuple(sorted((i+5,((i+2)%5)+5))) for i in range(5)]
    return edges

def K33():return [(i,3+j) for i in range(3) for j in range(3)]

def dimacs(n,clauses):
    return (f'p cnf {n} {len(clauses)}\n'+''.join(' '.join(map(str,c))+' 0\n' for c in clauses)).encode()

def renumber_shuffled(raw,weights):
    nv,clauses=read_cnf(raw)
    perm=list(range(1,nv+1));RNG.shuffle(perm)
    alo=[(j,c) for j,c in enumerate(c for c in clauses if len(c)==3 and all(x>0 for x in c))]
    assert len(alo)==len(weights)
    RNG.shuffle(alo)
    rest=[c for c in clauses if not (len(c)==3 and all(x>0 for x in c))]
    RNG.shuffle(rest)
    newclauses=[tuple(perm[abs(v)-1]*(1 if v>0 else -1) for v in c) for j,c in alo]
    newclauses += [tuple(perm[abs(v)-1]*(1 if v>0 else -1) for v in c) for c in rest]
    return dimacs(nv,newclauses),[weights[j] for j,c in alo]

def check_model(raw,truth):
    nv,cls=read_cnf(raw)
    assert all(1<=x<=nv for x in truth)
    return all(any((x in truth if x>0 else -x not in truth) for x in c) for c in cls)

def test(name,raw,weights,expected,need=False,model=None):
    result=prove(raw,weights)
    asserted=result['status']=='UNSAT_UNCHECKED'
    if need and not asserted:raise AssertionError(f'{name} missed: {result}')
    if expected=='SAT' and asserted:raise AssertionError('FALSE UNSAT '+name)
    verified=None
    if asserted:verified=check(raw,result)
    if model is not None and not check_model(raw,model):
        raise AssertionError('broken SAT control model '+name)
    OUT.joinpath('cnf').mkdir(parents=True,exist_ok=True)
    OUT.joinpath('proofs').mkdir(parents=True,exist_ok=True)
    (OUT/'cnf'/f'{name}.cnf').write_bytes(raw)
    (OUT/'proofs'/f'{name}.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    ROWS.append({'name':name,'expected':expected,'status':'VERIFIED_UNSAT' if verified else 'UNKNOWN',
        'reason':result.get('reason'),'source_sha256':hashlib.sha256(raw).hexdigest(),
        'source_variables':read_cnf(raw)[0],'source_clauses':len(read_cnf(raw)[1]),
        'matching_count':result.get('matching_count'),'source_supports':result.get('local_source_supports'),
        'checked_sat_model':bool(model is not None)})
    return result

def run():
    OUT.mkdir(parents=True,exist_ok=True)
    raw,weights=encode(petersen(),'Genuine PCMAX decision formula, no solution on 3 machines')
    assert hashlib.sha256(raw).hexdigest()=='c2fefeffc1f9644ffd6f85728106a21c82dfc01d0d021f32d4d73569cc2bfb70'
    cert=test('original_petersen_45_300',raw,weights,'UNSAT',need=True)
    assert cert['matching_count']==6 and all(x['allowed_masks']==7036 for x in cert['local_source_supports'])
    for i in range(4):
        changed,wh=renumber_shuffled(raw,weights)
        test(f'petersen_renumbered_order_{i}',changed,wh,'UNSAT',need=True)
    # Source comments are not proof prerequisites; try without any comments.
    plain,weights2=encode(petersen(),'petersen_without_hint',comments=False)
    test('petersen_no_comments_explicit_candidate',plain,weights2,'UNSAT',need=True)
    assert prove(plain)['status']=='UNKNOWN'  # Producer needs candidate; checker never uses hints.
    # SAT K3,3 has an actual three edge coloring: (left + right) modulo 3.
    g33=K33();sat,sw=encode(g33,'K33 valid packing')
    model={3*j+((u+(v-3))%3)+1 for j,(u,v) in enumerate(g33)}
    test('k33_graph_3colorable_sat',sat,sw,'SAT',model=model)
    nv,cls=read_cnf(raw)
    with_removed=[c for c in cls if not (all(x<0 for x in c) and len({(abs(x)-1)//3 for x in c})==len(c))]
    relaxed=dimacs(nv,with_removed)
    model_all_zero={3*j+1 for j in range(15)}
    test('petersen_all_weight_clauses_removed_sat',relaxed,weights,'SAT',model=model_all_zero)
    # Deleting a single inclusion-minimal overweight source clause
    # must invalidate proposed PB source-bound proof.
    ix=next(i for i,c in enumerate(cls) if len(c)>2 and all(x<0 for x in c))
    weakened=dimacs(nv,cls[:ix]+cls[ix+1:])
    test('petersen_single_capacity_clause_deleted_unknown',weakened,weights,'UNKNOWN')
    wrong=weights.copy();wrong[0]+=1
    test('petersen_wrong_weight_hint_unknown',raw,wrong,'UNKNOWN')
    tests=[]
    bad=copy.deepcopy(cert);bad['source_sha256']='0'*64;tests.append(bad)
    bad=copy.deepcopy(cert);bad['matching_odd_witnesses'].pop();tests.append(bad)
    bad=copy.deepcopy(cert);bad['matching_odd_witnesses'][0]['odd_cycle']=[0,1,2];tests.append(bad)
    bad=copy.deepcopy(cert);bad['resources'][0].pop();tests.append(bad)
    bad=copy.deepcopy(cert);bad['weights'][0]+=1;tests.append(bad)
    bad=copy.deepcopy(cert);bad['local_source_supports'][0]['allowed_masks']=-1;tests.append(bad)
    bad=copy.deepcopy(cert);bad['matching_odd_witnesses'][0]['matching'][0]=20;tests.append(bad)
    bad=copy.deepcopy(cert);bad['status']='UNKNOWN';tests.append(bad)
    rejected=0
    for t in tests:
        try:check(raw,t)
        except (ValueError,TypeError,KeyError,IndexError,OverflowError):rejected+=1
        else:raise AssertionError('forged certificate accepted')
    try:check(raw+b'c altered bytes\n',cert)
    except ValueError:rejected+=1
    else:raise AssertionError('changed source accepted')
    summary={'status':'PASS','cases':len(ROWS),'source_verified_unsat':sum(x['status']=='VERIFIED_UNSAT' for x in ROWS),
        'sat_controls':sum(x['expected']=='SAT' for x in ROWS),
        'sat_models_checked':sum(x['checked_sat_model'] for x in ROWS),
        'false_unsat':sum(x['expected']=='SAT' and x['status']=='VERIFIED_UNSAT' for x in ROWS),
        'forged_mutated_rejected':rejected,
        'original_petersen':'VERIFIED_UNSAT',
        'permuted_originals_verified':sum(x['status']=='VERIFIED_UNSAT' and 'renumbered' in x['name'] for x in ROWS),
        'petersen_matchings':cert['matching_count'],
        'petersen_local_support_counts':[p['allowed_masks'] for p in cert['local_source_supports']],
        'limits':'bounded n<=15 O(2^n) source-bound check; project-specific proof; not polynomial for general input, not standard VeriPB or blind PAR2'}
    assert rejected==len(tests)+1 and summary['false_unsat']==0
    (OUT/'summary.json').write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
    (OUT/'cases.json').write_text(json.dumps(ROWS,indent=2,sort_keys=True)+'\n')
    print('MATCH4_FINAL '+json.dumps(summary,sort_keys=True),flush=True)

if __name__=='__main__':
    if hasattr(os,'sched_setaffinity'):
        os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    run()
