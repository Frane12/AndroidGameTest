#!/usr/bin/env python3
"""R104: proof-carrying GF(2) prepass and bounded short XOR consequences.

Original CNF is immutable. Every additional clause is justified by a
separately decoded complete 3-XOR CNF signature and GF(2) ancestry replay.
An empty clause is emitted ONLY after replaying a certified 0 = 1 parity proof.
"""
import argparse
import collections
import itertools
import json
import pathlib
import sys
import time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r92_verified_xor_bridge as r92
import r93_export_verified_rows as r93
import r88_cooperative as r88

def independent_replay(mask,rhs,ancestry,sources,independent):
    if not ancestry or rhs not in (0,1): return False
    m = b = 0
    for idx in sorted(ancestry):
        if idx < 0 or idx >= len(sources): return False
        im,ib,_ = sources[idx]
        if (im,ib) not in independent: return False
        m ^= im
        b ^= ib
    return (m,b)==(mask,rhs)

def elimination(sources):
    pivots = {}
    contradictory = None
    for i,(mask,rhs,_) in enumerate(sources):
        ancestry=frozenset((i,))
        while mask:
            bit=mask & -mask
            if bit not in pivots:
                pivots[bit]=(mask,rhs,ancestry)
                break
            pm,pr,pa=pivots[bit]
            mask ^= pm;rhs ^= pr;ancestry=ancestry.symmetric_difference(pa)
        if mask==0 and rhs:
            contradictory=(0,1,ancestry)
            break
    return pivots,contradictory

def parity_clauses(mask,rhs):
    variables=[i+1 for i in range(mask.bit_length()) if mask & (1<<i)]
    if not 2<=len(variables)<=4:raise ValueError('unsupported parity width')
    for bits in itertools.product((0,1),repeat=len(variables)):
        if sum(bits)%2!=rhs:
            yield tuple(-v if b else v for v,b in zip(variables,bits))

def produce(src,target,evidence,width=2,max_derived=48,max_pair_checks=60000):
    start=time.perf_counter()
    src=pathlib.Path(src)
    n,clauses=r88.read_cnf(src)
    original=r92.xor_sources(clauses)
    independent=r93.independent_index(clauses)
    if any((m,r) not in independent for m,r,_ in original):
        raise RuntimeError('R104_FAIL_CLOSED: source parity independent decoder mismatch')
    pivots,contradiction=elimination(original)
    base_sha=r88.sha(src)
    report=dict(protocol='R104-CERTIFIED-ROOT-GF2',sha256=base_sha,
        original_xors=len(original),matrix_rank=len(pivots),width=width,
        contradiction=bool(contradiction),candidate_pairs=0,
        independent_rows=0,short_rows=0,new_clauses=0,proof_equation_ids=[],
        source_cnf_clauses=len(clauses))
    if contradiction:
        mask,rhs,anc=contradiction
        if not independent_replay(mask,rhs,anc,original,independent):
            raise RuntimeError('R104_FAIL_CLOSED: contradiction ancestry invalid')
        # Empty clause follows logically from certified 0 = 1.
        added=[()]
        report['proof_equation_ids']=sorted(anc)
        report['new_clauses']=1
    else:
        seen=set()
        candidates=[]
        def consider(mask,rhs,anc):
            if not 2<=mask.bit_count()<=width or len(anc)<2: return
            if (mask,rhs) not in seen:
                seen.add((mask,rhs))
                candidates.append((mask,rhs,anc))
        for mask,rhs,anc in pivots.values():
            consider(mask,rhs,anc)
        incidence=collections.defaultdict(list)
        for i,(mask,_,variables) in enumerate(original):
            for var in variables:incidence[var].append(i)
        checked=set()
        done=False
        for var in sorted(incidence):
            members=incidence[var]
            for i,j in itertools.combinations(members,2):
                if (i,j) in checked:continue
                checked.add((i,j))
                report['candidate_pairs']+=1
                if report['candidate_pairs']>max_pair_checks:done=True;break
                am,ar,_=original[i];bm,br,_=original[j]
                consider(am^bm,ar^br,frozenset((i,j)))
            if done:break
        candidates.sort(key=lambda x:(x[0].bit_count(),len(x[2]),x[0],x[1]))
        orig_clause_set={tuple(sorted(c)) for c in clauses}
        added=[];new_set=set(); accepted=0
        for mask,rhs,anc in candidates:
            if accepted>=max_derived:break
            if not independent_replay(mask,rhs,anc,original,independent):
                raise RuntimeError('R104_FAIL_CLOSED: derived row proof invalid')
            proposals=list(parity_clauses(mask,rhs))
            novel=[c for c in proposals if tuple(sorted(c)) not in orig_clause_set
                   and tuple(sorted(c)) not in new_set]
            if not novel:continue
            for c in novel:
                new_set.add(tuple(sorted(c)))
                added.append(c)
            accepted+=1
        report['short_rows']=accepted
        report['independent_rows']=sum(1 for mask,rhs,anc in candidates
                                      if independent_replay(mask,rhs,anc,original,independent))
        report['new_clauses']=len(added)
    target=pathlib.Path(target);target.parent.mkdir(parents=True,exist_ok=True)
    r88.write_augmented(n,clauses,added,target)
    report['prep_s']=round(time.perf_counter()-start,8)
    pathlib.Path(evidence).write_text(json.dumps(report,indent=2)+'\n')
    print('R104_PROOF_PREPASS',json.dumps(report),flush=True)
    return report

def selftest():
    from tempfile import TemporaryDirectory
    from pathlib import Path
    with TemporaryDirectory() as d:
        p=Path(d)/'f.cnf'
        # x^y^z=0 and x^y^w=0 imply z^w=0.
        clauses=[]
        for vs in ((1,2,3),(1,2,4)):
            for sign in (1,2,4,7):
                clauses.append(tuple(-v if sign & (1<<i) else v for i,v in enumerate(vs)))
        r88.write_augmented(4,clauses,[],p)
        res=produce(p,Path(d)/'aug.cnf',Path(d)/'cert.json',2)
        assert not res['contradiction'] and res['short_rows']>=1 and res['new_clauses']>=2
        # Add the opposite x^y^z=1: genuine algebraic contradiction.
        for sign in (0,3,5,6):
            clauses.append(tuple(-v if sign & (1<<i) else v for i,v in enumerate((1,2,3))))
        r88.write_augmented(4,clauses,[],p)
        res=produce(p,Path(d)/'unsat.cnf',Path(d)/'unsat.json',2)
        assert res['contradiction'] and res['new_clauses']==1
        # Parity-only model truth table must reject all 16 bit assignments.
        assert not any(all(any(((bits>>(abs(l)-1))&1)==(l>0) for l in c)
                           for c in clauses) for bits in range(16))
    print('R104_GF2_CERTIFICATE_SELFTEST_PASS')

if __name__=='__main__':
    ap=argparse.ArgumentParser()
    ap.add_argument('command',choices=['selftest','export'])
    ap.add_argument('--cnf');ap.add_argument('--out');ap.add_argument('--evidence')
    ap.add_argument('--width',type=int,default=2,choices=[2,4])
    a=ap.parse_args()
    if a.command=='selftest':selftest()
    else:
        if not(a.cnf and a.out and a.evidence):ap.error('missing paths')
        produce(a.cnf,a.out,a.evidence,width=a.width)
