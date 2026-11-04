#!/usr/bin/env python3
"""R107C regression: native proof and XOR counts must equal Python R107B.

Selftests for k=2..6, intentionally missing clauses and UNSAT proof ancestry.
"""
import hashlib,json,pathlib,subprocess,sys,tempfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r107a_xor_finder as reference
import r107b_certified_cadical as old
import r106_verify_solver as reader

def xor_clauses(vs,rhs):
    return [tuple(-v if bits>>i&1 else v for i,v in enumerate(vs))
            for bits in range(1<<len(vs)) if bits.bit_count()%2 != rhs]
def write(path,n,clauses):
    path.write_text(f'p cnf {n} {len(clauses)}\n'+
                    ''.join(' '.join(map(str,c))+' 0\n' for c in clauses))
def invoke(binary,source,output,proof):
    p=subprocess.run([binary,str(source),str(output),str(proof)],capture_output=True,text=True,timeout=30)
    if p.returncode:raise RuntimeError(f'R107C selftest failed: {p.stderr[-500:]}')
    diag=json.loads(proof.read_text())
    old_rows=reference.extract(source)[2]
    if diag['source_xors']!=len(old_rows):
        raise AssertionError('R107C lost/miscounted valid XOR equation')
    if diag['gf2_unsat']:
        ancestors=diag['proof_row_ids']
        old.verify_proof(source,[(old_rows[i][2],old_rows[i][1]) for i in ancestors])
        if reader.cnf_clauses(output)[-1] != ():raise AssertionError('missing certified empty clause')
    else:
        if source.read_bytes()!=output.read_bytes():
            raise AssertionError('R107C changed CNF without proof')
    return diag
def main():
    if len(sys.argv)!=2:raise SystemExit('usage: r107c_native_selftest.py BINARY')
    binary=sys.argv[1]
    with tempfile.TemporaryDirectory() as td:
        root=pathlib.Path(td);src=root/'case.cnf';dst=root/'result.cnf';proof=root/'proof.json'
        for k in (2,3,4,5,6):
            clauses=xor_clauses(tuple(range(1,k+1)),0)
            write(src,k,clauses)
            r=invoke(binary,src,dst,proof)
            assert r['source_xors']==1 and r['widths'][str(k)]==1 and not r['gf2_unsat']
            write(src,k,clauses[:-1])
            r=invoke(binary,src,dst,proof)
            assert r['source_xors']==0 and not r['gf2_unsat']
        for k in (2,3,4,5,6):
            vs=tuple(range(1,k+1))
            write(src,k,xor_clauses(vs,0)+xor_clauses(vs,1))
            r=invoke(binary,src,dst,proof)
            assert r['gf2_unsat'] and r['source_xors']==2 and r['proof_length']==2
        # Shared-variable contradiction that requires elimination across 3 equations.
        write(src,5,xor_clauses((1,2,3),0)+xor_clauses((1,2,4),0)+
              xor_clauses((3,4,5),1)+xor_clauses((5,6),0))
        # Fix declared vars: this case deliberately must refuse invalid DIMACS.
        p=subprocess.run([binary,str(src),str(dst),str(proof)],capture_output=True,text=True)
        assert p.returncode!=0
        write(src,6,xor_clauses((1,2,3),0)+xor_clauses((1,2,4),0)+
              xor_clauses((3,4,5),1)+xor_clauses((5,6),0))
        r=invoke(binary,src,dst,proof)
        assert not r['gf2_unsat']  # last row is not contradictory
        for case in (('badheader','p cnf 4 2\n1 2 3 0\n'),
                     ('badliteral','p cnf 3 1\n1 2 4 0\n')):
            src.write_text(case[1])
            p=subprocess.run([binary,str(src),str(dst),str(proof)],capture_output=True,text=True)
            assert p.returncode!=0
    print('R107C_NATIVE_CERTIFIED_SELFTEST_PASS',flush=True)
if __name__=='__main__':main()
