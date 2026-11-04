#!/usr/bin/env python3
"""R108: sound discovery of hidden XOR from shortened CNF and bounded resolution.

Every found parity row is implied by input CNF: all parity-violating assignments
are covered by independently replayable source or resolution-derived clauses.
This is a research prepass, NOT a general XOR solver or unrestricted inference.
"""
import argparse,collections,hashlib,itertools,json,pathlib,sys,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import r106_verify_solver as dimacs
import r104_static_xor_prepass as gf
import r107b_certified_cadical as base

MAX_POOL=50000
MAX_PAIRS_PER_ROUND=35000
MAX_NEW_PER_ROUND=3000
MAX_CANDIDATES=35000
MAX_XOR_ROWS=7000

def normalize(clause):
    values={}
    for lit in clause:
        v=abs(lit)
        if v in values:
            if values[v]!=lit:return None
        else:values[v]=lit
    return tuple(values[v] for v in sorted(values))

def resolve(a,b,pivot):
    if pivot not in a or -pivot not in b:
        raise RuntimeError("R108_FAIL_CLOSED pivot not in both antecedents")
    return normalize(tuple(x for x in a if x!=pivot)+tuple(x for x in b if x!=-pivot))

def make_resolvents(original,rounds):
    """Only sound resolvents; cap all work; do not silently claim completeness."""
    n=len(original)
    nodes=[]
    seen={}
    candidates=[]
    for i,c in enumerate(original):
        if 1<=len(c)<=8:
            normal=normalize(c)
            if normal is not None and normal not in seen:
                seen[normal]=i
                if len(candidates)<MAX_POOL:candidates.append(i)
    exceeded=len(seen)>MAX_POOL
    def clause(i):
        return original[i] if i<n else nodes[i-n][0]
    pairs=0
    generated_by_round=[]
    for depth in range(rounds):
        occ=collections.defaultdict(lambda: [[],[]])
        for i in candidates:
            c=clause(i)
            if not 2<=len(c)<=8:continue
            for lit in c:
                v=abs(lit)
                if lit>0:occ[v][0].append(i)
                else:occ[v][1].append(i)
        generated=0
        stop=False
        for pivot in sorted(occ,key=lambda v:(len(occ[v][0])*len(occ[v][1]),v)):
            pos,neg=occ[pivot]
            if len(pos)>80 or len(neg)>80:continue
            for a in pos:
                for b in neg:
                    pairs+=1
                    if pairs>MAX_PAIRS_PER_ROUND*rounds:
                        exceeded=True;stop=True;break
                    derived=resolve(clause(a),clause(b),pivot)
                    if derived is None or len(derived)>6 or derived in seen:continue
                    # Exclude empty clause here: its resolution proof is valid,
                    # but only GF2 contradictions are emitted as UNSAT by R108.
                    if not derived:continue
                    index=n+len(nodes)
                    nodes.append((derived,a,b,pivot))
                    seen[derived]=index
                    if len(candidates)<MAX_POOL:candidates.append(index)
                    else:exceeded=True
                    generated+=1
                    if generated>=MAX_NEW_PER_ROUND:
                        exceeded=True;stop=True;break
                if stop:break
            if stop:break
        generated_by_round.append(generated)
        if stop or not generated:break
    return nodes,seen,dict(pairs_checked=pairs,derived=len(nodes),
                             derived_per_round=generated_by_round,budget_truncated=exceeded)

def scan(source,rounds=2,do_resolve=True):
    started=time.perf_counter()
    source=pathlib.Path(source)
    original=dimacs.cnf_clauses(source)
    digest=hashlib.sha256(source.read_bytes()).hexdigest()
    nodes,seen,stats=make_resolvents(original,rounds if do_resolve else 0)
    n=len(original)
    def clause(i):
        return original[i] if i<n else nodes[i-n][0]
    groups=collections.defaultdict(dict)
    for key,i in seen.items():
        if not 1<=len(key)<=6:continue
        vs=tuple(abs(x) for x in key)
        neg=sum(1<<j for j,x in enumerate(key) if x<0)
        if neg not in groups[vs]:groups[vs][neg]=i
    keys=sorted(groups,key=lambda v:(len(v),v))
    truncated=stats['budget_truncated'] or len(keys)>MAX_CANDIDATES
    keys=keys[:MAX_CANDIDATES]
    independents=dimacs.cnf_clauses(source)
    if original!=independents or hashlib.sha256(source.read_bytes()).hexdigest()!=digest:
        raise RuntimeError('R108_FAIL_CLOSED original source changed or mismatched')
    checked_nodes=set()
    def check_node(i):
        if i in checked_nodes:return
        if i<n:
            if normalize(independents[i])!=normalize(clause(i)):
                raise RuntimeError('R108_FAIL_CLOSED original clause changed')
        else:
            c,a,b,pivot=nodes[i-n]
            check_node(a);check_node(b)
            if resolve(clause(a),clause(b),pivot)!=c:
                raise RuntimeError('R108_FAIL_CLOSED bad resolution ancestry')
        checked_nodes.add(i)
    rows=[]
    derived_rows=0
    shortened_rows=0
    for V in keys:
        k=len(V)
        if not 2<=k<=6:continue
        # Only supports included in V can directly falsify assignments of V.
        support=[]
        for length in range(1,k+1):
            for S in itertools.combinations(V,length):
                for signs,i in groups.get(S,{}).items():
                    locations=[V.index(x) for x in S]
                    support.append((locations,signs,i))
        if not support:continue
        witnesses=[-1]*(1<<k)
        for locations,signs,i in support:
            for bits in range(1<<k):
                if witnesses[bits]>=0:continue
                if all(((bits>>slot)&1)==((signs>>j)&1)
                       for j,slot in enumerate(locations)):
                    witnesses[bits]=i
        for rhs in (0,1):
            forbidden=[bits for bits in range(1<<k) if bits.bit_count()%2!=rhs]
            if any(witnesses[b]<0 for b in forbidden):continue
            used=sorted({witnesses[b] for b in forbidden})
            for i in used:check_node(i)
            # Independent clause-by-clause check of every forbidden assignment.
            for bits in forbidden:
                c=clause(witnesses[bits])
                model={v:bool(bits>>j&1) for j,v in enumerate(V)}
                if any(model.get(abs(lit))==(lit>0) for lit in c):
                    raise RuntimeError('R108_FAIL_CLOSED XOR witness not falsified')
                if any(abs(lit) not in model for lit in c):
                    raise RuntimeError('R108_FAIL_CLOSED clause uses external variable')
            rows.append((sum(1<<(v-1) for v in V),rhs,V))
            if any(i>=n for i in used):derived_rows+=1
            if any(len(clause(i))<k for i in used):shortened_rows+=1
            if len(rows)>=MAX_XOR_ROWS:
                truncated=True
                break
        if len(rows)>=MAX_XOR_ROWS:break
    pivots,contradiction=gf.elimination(rows)
    proof=[]
    if contradiction:
        mask,rhs,anc=contradiction
        if (mask,rhs)!=(0,1) or not anc:
            raise RuntimeError('R108_FAIL_CLOSED invalid GF2 contradiction')
        proof=sorted(anc)
        total_mask=total_rhs=0
        for i in proof:
            total_mask^=rows[i][0];total_rhs^=rows[i][1]
        if (total_mask,total_rhs)!=(0,1):
            raise RuntimeError('R108_FAIL_CLOSED invalid XOR ancestry')
    counts={str(k):sum(len(vs)==k for _,_,vs in rows) for k in range(2,7)}
    report=dict(protocol='R108-HIDDEN-XOR-CLAUSE-COVER-RESOLUTION',
      sha256=digest,original_clauses=n,
      original_groups=len(groups),groups_scanned=len(keys),
      certified_rows=len(rows),by_width=counts,
      from_resolution_rows=derived_rows,from_shortened_rows=shortened_rows,
      gf2_rank=len(pivots),gf2_unsat=bool(contradiction),
      gf2_proof_ids=proof,resolution=stats,
      budget_truncated=truncated,prep_s=round(time.perf_counter()-started,6))
    return report

def selftest():
    import tempfile
    def parity(vs,rhs):
        return [tuple(-v if bits>>i&1 else v for i,v in enumerate(vs))
                for bits in range(1<<len(vs)) if bits.bit_count()%2!=rhs]
    def hidden(clauses,aux):
        choices=list(itertools.product((1,-1),repeat=len(aux)))
        return [tuple(c)+tuple(s*v for s,v in zip(sig,aux))
                for c in clauses for sig in choices]
    with tempfile.TemporaryDirectory() as temp:
        root=pathlib.Path(temp)
        def test(name,clauses,n,expected,resolve_rounds=2):
            path=root/(name+'.cnf')
            path.write_text(f'p cnf {n} {len(clauses)}\n'+''.join(
                ' '.join(map(str,c))+' 0\n' for c in clauses))
            result=scan(path,resolve_rounds)
            if result['gf2_unsat']!=expected:
                raise RuntimeError('R108_SELFTEST wrong XOR contradiction '+name)
            print('R108_SELFTEST_CASE',name,result['certified_rows'],
                  result['resolution']['derived'],result['gf2_unsat'],flush=True)
            return result
        vs=(1,2,3,4)
        valid=parity(vs,0);opposite=parity(vs,1)
        test('plain_sat',valid,4,False)
        test('plain_unsat',valid+opposite,4,True)
        r=test('hidden_1_sat',hidden(valid,(5,)),5,False)
        assert r['certified_rows']>=1 and r['from_resolution_rows']>=1
        r=test('hidden_1_unsat',hidden(valid+opposite,(5,)),5,True)
        assert r['from_resolution_rows']>=1
        r=test('hidden_2_unsat',hidden(valid+opposite,(5,6)),6,True)
        assert r['from_resolution_rows']>=1
        r=test('shortened',valid[:-1]+[(1,2,3)],4,False)
        assert r['from_shortened_rows']>=1
        r=test('incomplete',valid[:-1],4,False)
        assert r['certified_rows']==0
    print('R108_HIDDEN_XOR_SELFTEST_PASS',flush=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument('cmd',choices=['selftest','inspect'])
    p.add_argument('--cnf');p.add_argument('--out');p.add_argument('--rounds',type=int,default=2)
    a=p.parse_args()
    if a.cmd=='selftest':selftest();return
    if not a.cnf or not a.out:p.error('missing paths')
    if a.rounds not in (0,1,2):p.error('rounds must be 0..2')
    report=scan(a.cnf,a.rounds)
    dest=pathlib.Path(a.out);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(report,indent=2)+'\n')
    print('R108_SCAN',json.dumps({k:v for k,v in report.items() if k!='gf2_proof_ids'}),flush=True)
if __name__=='__main__':main()
