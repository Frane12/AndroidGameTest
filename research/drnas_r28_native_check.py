"""Independent original-CNF SAT, GF(2), and counting certificate checks."""
import collections,re
from drnas_ltm9_independent_cert import parse_dimacs,certificate_from_stdout,verify_php_certificate

def check_sat(source,out):
    values={}
    for line in out.splitlines():
        if not line.startswith('v '):continue
        for tok in line.split()[1:]:
            lit=int(tok)
            if not lit:continue
            v=abs(lit)
            if v>source['n'] or (v in values and values[v]!=(lit>0)):raise ValueError('invalid witness')
            values[v]=lit>0
    if not all(any(abs(v) in values and values[abs(v)]==(v>0) for v in c) for c in source['clauses']):
        raise ValueError('SAT model fails original CNF')
    return True

def check_gf2(source,out):
    units={c[0] for c in source['clauses'] if len(c)==1}
    groups=collections.defaultdict(set)
    for c in source['clauses']:
        if not 2<=len(c)<=6 or len({abs(v) for v in c})!=len(c):continue
        c=sorted(c,key=abs);vs=tuple(map(abs,c))
        groups[vs].add(sum(1<<i for i,v in enumerate(c) if v<0))
    equations={}
    for line in out.splitlines():
        m=re.fullmatch(r'c R28_EQ id=(\d+) rhs=([01]) vars=([\d,]+)',line)
        if not m:continue
        idx,rhs=int(m[1]),int(m[2]);vs=tuple(map(int,m[3].split(',')))
        if idx in equations or not vs or len(set(vs))!=len(vs) or any(v<=0 or v>source['n'] for v in vs):raise ValueError('bad equation')
        if len(vs)==1:
            if (vs[0] if rhs else -vs[0]) not in units:raise ValueError('unsupported unit')
        else:
            if not 2<=len(vs)<=6 or vs!=tuple(sorted(vs)):raise ValueError('bad XOR order')
            masks={m for m in range(1<<len(vs)) if m.bit_count()%2==1-rhs}
            if not masks<=groups[vs]:raise ValueError('XOR not implied by complete source block')
        equations[idx]=(rhs,vs)
    cert=re.search(r'^c R28_UNSAT_CERT ids=([\d,]+)$',out,re.M)
    if not cert:raise ValueError('missing GF2 proof')
    ids=list(map(int,cert[1].split(',')))
    if len(set(ids))!=len(ids) or any(i not in equations for i in ids):raise ValueError('bad proof indices')
    rhs=0;bits=set()
    for i in ids:
        b,vs=equations[i];rhs^=b
        for v in vs:bits.symmetric_difference_update({v})
    if bits or rhs!=1:raise ValueError('proof does not produce 0=1')
    return True

def verify(source,out,rc):
    statuses=re.findall(r'^s (SATISFIABLE|UNSATISFIABLE|UNKNOWN)\s*$',out,re.M)
    if not statuses:return 'UNKNOWN',False
    if len(set(statuses))>1:
        # The hard end-to-end deadline wins over an answer interrupted during output.
        if 'c R28_NATIVE deadline' in out:return 'UNKNOWN',False
        raise ValueError('contradictory output statuses')
    status=statuses[-1]
    if status=='SATISFIABLE':
        if rc!=10:raise ValueError('SAT exit code mismatch')
        check_sat(source,out);return 'SAT_VERIFIED',True
    if status=='UNSATISFIABLE':
        if rc!=20:raise ValueError('UNSAT exit code mismatch')
        if 'c R28_UNSAT_CERT' in out:
            check_gf2(source,out);return 'UNSAT_GF2_VERIFIED',True
        if 'c LTM9_PHP_CERT' in out:
            verify_php_certificate(source,certificate_from_stdout(out));return 'UNSAT_PHP_VERIFIED',True
        return 'UNSAT_UNVERIFIED',False
    return 'UNKNOWN',False
