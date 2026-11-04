#!/usr/bin/env python3
"""R107-B: proof-carrying 2..6 XOR recognition -> GF(2) -> CaDiCaL CNF.

Never insert an empty clause unless the immutable source independently entails
0=1 by a separately replayed combination of complete parity CNF signatures.
Otherwise preserve the input CNF byte-for-byte. All analysis is charged.
"""
import argparse,hashlib,json,pathlib,shutil,tempfile,time,sys
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r107a_xor_finder as finder
import r106_verify_solver as parser

def verify_proof(source, selected):
    """Reconstruct source parity witnesses afresh, independent of finder bitset."""
    original=parser.cnf_clauses(source)
    canonical=set()
    for clause in original:
        if 2<=len(clause)<=6 and len(set(map(abs,clause)))==len(clause):
            canonical.add(tuple(sorted(clause,key=lambda x:abs(x))))
    mask=rhs=0
    proofs=[]
    for vs, parity in selected:
        if not 2<=len(vs)<=6 or len(set(vs))!=len(vs) or parity not in (0,1):
            raise RuntimeError('R107B_FAIL_CLOSED malformed proof row')
        for value in range(1<<len(vs)):
            if value.bit_count()%2!=parity:
                clause=tuple(-v if value>>i&1 else v for i,v in enumerate(vs))
                if clause not in canonical:
                    raise RuntimeError('R107B_FAIL_CLOSED missing original XOR clause')
        proofs.append(dict(vars=list(vs),rhs=parity))
        mask ^= sum(1<<(v-1) for v in vs)
        rhs ^= parity
    if (mask,rhs)!=(0,1):
        raise RuntimeError('R107B_FAIL_CLOSED GF2 contradiction not replayed')
    return proofs

def append_empty(source,dest,original_count):
    """Preserve DIMACS original clauses; increase header by exactly one."""
    changed=False
    with source.open('r',encoding='ascii',errors='strict') as src, dest.open('w',encoding='ascii') as dst:
        for line in src:
            words=line.split()
            if words and words[0]=='p':
                if changed or len(words)!=4 or words[1]!='cnf':
                    raise RuntimeError('R107B_FAIL_CLOSED bad DIMACS header')
                if int(words[3])!=original_count:
                    raise RuntimeError('R107B_FAIL_CLOSED clause-count disagreement')
                dst.write(f'p cnf {int(words[2])} {original_count+1}\n')
                changed=True
            else:
                dst.write(line)
                if not line.endswith('\n'):dst.write('\n')
        if not changed:raise RuntimeError('R107B_FAIL_CLOSED missing header')
        dst.write('0\n')

def build(source,dest,evidence):
    started=time.perf_counter()
    source=pathlib.Path(source);dest=pathlib.Path(dest);evidence=pathlib.Path(evidence)
    sha=hashlib.sha256(source.read_bytes()).hexdigest()
    clauses,groups,rows=finder.extract(source)
    pivots,contradiction=finder.gf.elimination(rows)
    proof=[]
    if contradiction:
        mask,rhs,ancestors=contradiction
        if mask!=0 or rhs!=1:
            raise RuntimeError('R107B_FAIL_CLOSED malformed GF2 contradiction')
        if not ancestors or any(not 0<=i<len(rows) for i in ancestors):
            raise RuntimeError('R107B_FAIL_CLOSED bad ancestry indices')
        # Independently reread the immutable original and re-prove each parity.
        proof=verify_proof(source,[(rows[i][2],rows[i][1]) for i in sorted(ancestors)])
    dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.resolve()==source.resolve():
        raise RuntimeError('R107B_FAIL_CLOSED source overwrite refused')
    if contradiction:
        append_empty(source,dest,len(clauses))
    else:
        shutil.copyfile(source,dest)
    if hashlib.sha256(source.read_bytes()).hexdigest()!=sha:
        raise RuntimeError('R107B_FAIL_CLOSED source mutated')
    stats=dict(protocol='R107B-CERTIFIED-GF2-TO-CADICAL',source_sha256=sha,
        source_clauses=len(clauses),source_xors=len(rows),
        widths={str(k):sum(len(row[2])==k for row in rows) for k in range(2,7)},
        gf2_rank=len(pivots),gf2_unsat=bool(contradiction),
        proof_original_rows=proof,proof_length=len(proof),
        added_empty_clause=int(bool(contradiction)),
        prep_s=round(time.perf_counter()-started,7),
        output_sha256=hashlib.sha256(dest.read_bytes()).hexdigest())
    evidence.parent.mkdir(parents=True,exist_ok=True)
    evidence.write_text(json.dumps(stats,indent=2)+'\n')
    print('R107B_PREPASS',json.dumps({k:v for k,v in stats.items() if k!='proof_original_rows'}),flush=True)
    return stats

def selftest():
    def xor(variables,rhs):
        return [tuple(-v if bits>>i&1 else v for i,v in enumerate(variables))
                for bits in range(1<<len(variables)) if bits.bit_count()%2!=rhs]
    def put(path,variables,clauses):
        path.write_text(f'p cnf {variables} {len(clauses)}\n'+''.join(
            ' '.join(map(str,c))+' 0\n' for c in clauses))
    with tempfile.TemporaryDirectory() as temp:
        root=pathlib.Path(temp)
        source=root/'source.cnf';output=root/'augmented.cnf';ev=root/'cert.json'
        sat=xor((1,2,3,4),0)
        put(source,4,sat)
        result=build(source,output,ev)
        assert not result['gf2_unsat'] and source.read_bytes()==output.read_bytes()
        assert result['source_xors']==1
        # Opposite 4-XOR produces valid 0=1 proof.
        put(source,4,sat+xor((1,2,3,4),1))
        result=build(source,output,ev)
        assert result['gf2_unsat'] and result['proof_length']==2
        assert parser.cnf_clauses(output)[-1]==()
        # Remove one source clause from the opposite XOR: cannot claim an XOR proof.
        incomplete=sat+xor((1,2,3,4),1)[:-1]
        put(source,4,incomplete)
        result=build(source,output,ev)
        assert not result['gf2_unsat'] and source.read_bytes()==output.read_bytes()
        # Independent checker must reject a fabricated parity witness.
        try:
            verify_proof(source,[((1,2,3,4),1)])
        except RuntimeError:pass
        else:raise AssertionError('R107B failed closed clause-removal test')
    print('R107B_CERTIFIED_SELFTEST_PASS',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('cmd',choices=['selftest','export'])
    p.add_argument('--cnf');p.add_argument('--out');p.add_argument('--evidence')
    a=p.parse_args()
    if a.cmd=='selftest':selftest()
    else:
        if not(a.cnf and a.out and a.evidence):p.error('missing arguments')
        build(a.cnf,a.out,a.evidence)
