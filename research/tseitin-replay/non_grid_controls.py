"""Transfer control: two connected, simple, non-bipartite 4-regular graphs.
Paired charge flip changes SAT/UNSAT. Adding a weakening of an existing
clause preserves every satisfying assignment and each UNSAT verdict.
"""
import itertools,json,os,random,resource,sys
from pathlib import Path
from transfer_bench import SOLVERS,solve,validate,save,digest
from xor4_benchmark import write_cnf
from proofcheck import verify_model

def generate(n):
    nodes=list(range(n));randomizer=random.Random(261101455+n)
    def edges(order):
        return {tuple(sorted((order[i],order[(i+1)%n]))) for i in range(n)}
    first=edges(nodes)
    while True:
        randomizer.shuffle(nodes)
        second=edges(nodes)
        if not first & second and any((u-v)%2==0 for u,v in second):break
    edge_list=sorted(first|second);randomizer.shuffle(edge_list)
    vs=[[] for _ in range(n)]
    for variable,(u,v) in enumerate(edge_list,1):
        vs[u].append(variable);vs[v].append(variable)
    assert all(len(g)==4 for g in vs)
    charge=[randomizer.randrange(2) for _ in vs];charge[0]=sum(charge[1:])%2
    return vs,charge

def main(slot):
    n=[64,192][slot//2];odd=slot%2
    vs,charge=generate(n);charge[0]^=odd
    clauses=[]
    rng=random.Random(n*1062205)
    for group,rhs in zip(vs,charge):
        for bits in itertools.product((0,1),repeat=4):
            if sum(bits)%2!=rhs:
                c=[-v if b else v for v,b in zip(group,bits)];rng.shuffle(c);clauses.append(c)
    rng.shuffle(clauses)
    extra=next(v for v in range(1,2*n+1) if v not in map(abs,clauses[0]))
    variants={'clean':clauses,'redundant':clauses+[clauses[0]+[extra]]}
    out=Path('out');out.mkdir();files={}
    for key,rows in variants.items():
        p=out/(key+'.cnf');write_cnf(p,2*n,rows);files[key]=p
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
    resource.setrlimit(resource.RLIMIT_AS,(3*1024**3,3*1024**3))
    label='UNSAT' if odd else 'SAT'
    trials=[]
    for rep in range(3):
        order=list(itertools.product(variants,SOLVERS));rng.shuffle(order)
        for key,solver in order:
            status,seconds,route,ans=solve(solver,files[key])
            if status!='TIMEOUT':
                assert status==label
                if status=='SAT':verify_model(2*n,variants[key],ans['model'])
                elif route.startswith('affine_exact'):
                    cert=validate(files[key],status,ans)
                    assert cert
                    if rep==0:save(out/(key+'-'+solver+'-proof.json'),dict(rows=cert,raw=ans))
            trials.append(dict(variant=key,solver=solver,rep=rep,seconds=seconds,status=status,route=route))
    save(out/'results.json',dict(n=n,label=label,slot=slot,inputs={v:digest(p) for v,p in files.items()},trials=trials))
if __name__=='__main__':main(int(sys.argv[1]))
