#!/usr/bin/env python3
"""R107-A: complete 2..6 XOR CNF signatures, independent replay, GF(2) proof.

Read immutable source CNF, identify all 2^(k-1) forbidden assignments for
a k-variable parity equation. A SECOND read verifies each exact clause.
No heuristic partial patterns are certified; no UNSAT without 0=1 ancestry.
"""
import argparse,collections,hashlib,itertools,json,pathlib,sys,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r104_static_xor_prepass as gf
import r106_verify_solver as cnf
MAX_GROUPS=500000
def masks(k):
    patterns=[0,0]
    for bits in range(1<<k):
        patterns[bits.bit_count()&1] |= 1<<bits
    return patterns

def extract(source):
    clauses=cnf.cnf_clauses(source)
    patterns={k:masks(k) for k in range(2,7)}
    groups={}
    for clause in clauses:
        k=len(clause)
        if k<2 or k>6:continue
        values=sorted(clause,key=lambda x:abs(x))
        variables=tuple(abs(x) for x in values)
        if len(set(variables))!=k:continue
        mask=sum((1<<i) for i,v in enumerate(values) if v<0)
        if variables not in groups:
            if len(groups)>=MAX_GROUPS:raise RuntimeError('R107_FAIL_CLOSED XOR group limit')
            groups[variables]=0
        groups[variables] |= 1<<mask
    found=[]
    for variables,seen in sorted(groups.items()):
        k=len(variables)
        # rhs=0 forbids odd assignments; rhs=1 forbids even.
        for rhs in (0,1):
            expected=patterns[k][1-rhs]
            if seen&expected==expected:
                found.append((variables,rhs))
    # Independent full-CNF replay; no trust in the group's bitset.
    # Re-read immutable source and compare canonical clause tuples.
    replay=set()
    for clause in cnf.cnf_clauses(source):
        if 2<=len(clause)<=6 and len(set(map(abs,clause)))==len(clause):
            replay.add(tuple(sorted(clause,key=lambda x:abs(x))))
    checked=[]
    for variables,rhs in found:
        k=len(variables)
        for bits in range(1<<k):
            if bits.bit_count()%2 != rhs:
                expected=tuple(-v if bits>>i&1 else v for i,v in enumerate(variables))
                if expected not in replay:
                    raise RuntimeError('R107_FAIL_CLOSED parity certificate missing')
        checked.append((sum(1<<(v-1) for v in variables),rhs,variables))
    return clauses,groups,checked

def inspect(source,out=None):
    start=time.perf_counter()
    source=pathlib.Path(source)
    clauses,groups,rows=extract(source)
    baseline=sum(len(x[2])==3 for x in rows)
    pivots,contradiction=gf.elimination(rows)
    proof=[]
    if contradiction:
        mask,rhs,anc=contradiction
        if mask!=0 or rhs!=1:
            raise RuntimeError('R107_FAIL_CLOSED invalid contradictory pivot')
        mm=bb=0
        for idx in sorted(anc):
            if not 0<=idx<len(rows):raise RuntimeError('R107_FAIL_CLOSED invalid ancestry')
            mm^=rows[idx][0];bb^=rows[idx][1]
        if (mm,bb)!=(0,1):raise RuntimeError('R107_FAIL_CLOSED GF2 ancestry mismatch')
        proof=sorted(anc)
    diag=dict(protocol='R107A-EXACT-XOR-CNF-2-6',sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
      total_clauses=len(clauses),supported_groups=len(groups),
      old_three_xor_count=baseline,found_xors=len(rows),by_width={
       str(k):sum(len(x[2])==k for x in rows) for k in range(2,7)},
      gf2_rank=len(pivots),gf2_unsat=bool(contradiction),
      proof_equation_ids=proof,elapsed_s=round(time.perf_counter()-start,6))
    if out:
        pathlib.Path(out).parent.mkdir(parents=True,exist_ok=True)
        pathlib.Path(out).write_text(json.dumps(diag,indent=2)+'\n')
    print('R107A_XOR_AUDIT',json.dumps({k:v for k,v in diag.items() if k!='proof_equation_ids'}),flush=True)
    return diag

def selftest():
    import tempfile
    def cs(variables,rhs):
        clauses=[]
        for bits in range(1<<len(variables)):
            if bits.bit_count()%2 != rhs:
                clauses.append(tuple(-v if bits>>i&1 else v for i,v in enumerate(variables)))
        return clauses
    with tempfile.TemporaryDirectory() as folder:
        root=pathlib.Path(folder)
        def write(name,n,clauses):
            p=root/name
            p.write_text(f'p cnf {n} {len(clauses)}\n'+
                ''.join(' '.join(map(str,c))+' 0\n' for c in clauses))
            return p
        for k in (2,3,4,5,6):
            group=cs(tuple(range(1,k+1)),0)
            d=inspect(write(f'xor{k}.cnf',k,group))
            assert d['found_xors']==1 and d['by_width'][str(k)]==1
            assert d['old_three_xor_count']==int(k==3)
            assert not d['gf2_unsat']
            if k>=3:
                partial=inspect(write(f'partial{k}.cnf',k,group[:-1]))
                assert partial['found_xors']==0
        both=cs((1,2,3,4),0)+cs((1,2,3,4),1)
        d=inspect(write('xor4-unsat.cnf',4,both))
        assert d['gf2_unsat'] and d['found_xors']==2
    print('R107A_SELFTEST_PASS')
if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('action',choices=['selftest','inspect'])
    p.add_argument('--cnf');p.add_argument('--out')
    args=p.parse_args()
    if args.action=='selftest':selftest()
    else:
        if not args.cnf:p.error('missing --cnf')
        inspect(args.cnf,args.out)
