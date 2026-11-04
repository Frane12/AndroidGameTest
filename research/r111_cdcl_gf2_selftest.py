#!/usr/bin/env python3
"""R111 in-process external GF2<->CDCL differential safety checks."""
import itertools,hashlib,pathlib,subprocess,sys,tempfile
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r106_verify_solver as check

def xor(vs,rhs):
    return [tuple(-v if mask>>i&1 else v for i,v in enumerate(vs))
            for mask in range(1<<len(vs)) if (mask.bit_count()&1)!=rhs]

def write(path,n,clauses):
    path.write_text('p cnf %d %d\n'%(n,len(clauses))+
        ''.join(' '.join(map(str,clause))+' 0\n' for clause in clauses))

def run(binary,mode,source,expected,timeout=8):
    p=subprocess.run([binary,mode,str(source)],capture_output=True,text=True,timeout=timeout)
    if p.returncode not in (10,20):
        raise RuntimeError('R111 selftest solver returned '+str(p.returncode)+
                           ' '+p.stderr[-500:])
    result=check.status(p.stdout,p.returncode)
    if result!=expected:
        raise RuntimeError('R111 status wrong: '+mode+' '+str(source)+' expected '+expected+' got '+result)
    if result=='SAT' and not check.model_valid(p.stdout,check.cnf_clauses(source)):
        raise RuntimeError('R111 SAT model invalid: '+mode+' '+str(source))
    if 'R111_AUDIT' not in p.stderr:
        raise RuntimeError('R111 missing audit')
    return p.stderr.split('R111_AUDIT')[-1].strip()

def main():
    if len(sys.argv)!=2:raise SystemExit('usage: R111 selftest executable')
    binary=sys.argv[1]
    with tempfile.TemporaryDirectory() as d:
        root=pathlib.Path(d)
        vectors=[
            ('xor_pair_sat',4,xor((1,2,3),0)+xor((1,2,4),0)+[(3,)],'SAT'),
            ('xor_pair_unsat',4,xor((1,2,3),0)+xor((1,2,4),0)+[(3,),(-4,)],'UNSAT'),
            ('xor_pair_sat_2',5,xor((1,2,3),1)+xor((1,2,4),0)+xor((2,4,5),1),'SAT'),
            ('xor_pair_unsat_2',5,xor((1,2,3),1)+xor((1,2,4),0)+
             xor((2,4,5),1)+[(3,),(4,),(5,)],'UNSAT'),
            ('incomplete',4,xor((1,2,3),0)[:-1]+xor((1,2,4),1)[:-1],'SAT'),
            ('exact_xor4',5,xor((1,2,3,4),0)+xor((1,2,3,5),0),'SAT'),
            ('exact_xor4_unsat',5,xor((1,2,3,4),0)+xor((1,2,3,5),0)+[(4,),(-5,)],'UNSAT'),
            ('single_xor',4,xor((1,2,3),0)+[(4,)],'SAT'),
        ]
        for name,n,clauses,expected in vectors:
            src=root/(name+'.cnf')
            write(src,n,clauses)
            sha=hashlib.sha256(src.read_bytes()).hexdigest()
            a=run(binary,'clean',src,expected)
            b=run(binary,'bridge',src,expected)
            if hashlib.sha256(src.read_bytes()).hexdigest()!=sha:
                raise RuntimeError('R111 mutated input source')
            print('R111_SELFTEST_CASE',name,expected,'clean',a,'bridge',b,flush=True)
        broken=root/'invalid.cnf'
        broken.write_text('p cnf 4 2\n1 2 0\n')
        p=subprocess.run([binary,'bridge',str(broken)],capture_output=True,text=True)
        if p.returncode==10 or p.returncode==20:
            raise RuntimeError('R111 accepted invalid DIMACS')
    print('R111_IPASIRUP_GF2_SELFTEST_PASS',flush=True)
if __name__=='__main__':main()
