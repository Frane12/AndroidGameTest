#!/usr/bin/env python3
"""DRNAS Structural SAT v4: benchmark the actual v4 cutset algorithm vs CaDiCaL.

Reproduces the formula families and decision procedures of DRNAS SAT experiment 4.
Standard library only. The CaDiCaL binary is the official compiled C++ CLI.
"""
import argparse
import csv
import itertools
import json
import platform
import random
import statistics
import subprocess
import time
from collections import Counter, defaultdict
from pathlib import Path

def normalize(cnf):
    return set(frozenset(c) for c in cnf if not any(-v in c for v in c))

def primal_neighbors(clauses):
    adj=defaultdict(set)
    for c in clauses:
        vs={abs(l) for l in c}
        for x in vs: adj[x].update(vs-{x})
    return adj

def solve(formula,node_budget=100000):
    nodes=0
    def rec(f):
        nonlocal nodes
        nodes+=1
        if nodes>node_budget:return None
        while True:
            if not f:return True
            if frozenset() in f:return False
            unit=next((next(iter(c)) for c in f if len(c)==1),None)
            if unit is None:break
            f=tuple(c-{-unit} for c in f if unit not in c)
        lits=set().union(*f)
        pure=next((l for l in lits if -l not in lits),None)
        if pure is not None:return rec(tuple(c for c in f if pure not in c))
        freqs=Counter(abs(l) for c in f for l in c)
        v=max(freqs,key=lambda z:(freqs[z],-z))
        for l in (v,-v):
            val=rec(tuple(c-{-l} for c in f if l not in c))
            if val is True:return True
            if val is None:return None
        return False
    return rec(tuple(formula)),nodes

def random_3sat(rng,n,ratio,planted):
    model={i:rng.choice((-1,1)) for i in range(1,n+1)}
    f=[]
    for _ in range(round(n*ratio)):
        vs=rng.sample(range(1,n+1),3)
        lits=[v*rng.choice((-1,1)) for v in vs]
        if planted and not any((lit>0)==(model[abs(lit)]>0) for lit in lits):lits[0]=-lits[0]
        f.append(lits)
    return f

def modular_3sat(rng,blocks=4,k=9,ratio=3.6,bridge=2,planted=False):
    n=blocks*k
    model={i:rng.choice((-1,1)) for i in range(1,n+1)}
    f=[]
    for b in range(blocks):
        vs=list(range(b*k+1,(b+1)*k+1))
        for _ in range(round(k*ratio)):
            ls=[v*rng.choice((-1,1)) for v in rng.sample(vs,3)]
            if planted and not any((lit>0)==(model[abs(lit)]>0) for lit in ls):ls[0]=-ls[0]
            f.append(ls)
    for b in range(blocks-1):
        for _ in range(bridge):
            vs=rng.sample(range(b*k+1,(b+1)*k+1),2)+rng.sample(range((b+1)*k+1,(b+2)*k+1),1)
            ls=[v*rng.choice((-1,1)) for v in vs]
            if planted and not any((lit>0)==(model[abs(lit)]>0) for lit in ls):ls[0]=-ls[0]
            f.append(ls)
    return f

def pigeonhole(n_pigeons,n_holes):
    x=lambda p,h:1+p*n_holes+h
    f=[[x(p,h) for h in range(n_holes)] for p in range(n_pigeons)]
    for h in range(n_holes):
        for p in range(n_pigeons):
            for q in range(p+1,n_pigeons):f.append([-x(p,h),-x(q,h)])
    return f

def xor_chain(rng,n,contradiction):
    assignment=[rng.randrange(2) for _ in range(n)]
    parities=[assignment[i]^assignment[(i+1)%n] for i in range(n)]
    if contradiction:parities[-1]^=1
    f=[]
    for i,p in enumerate(parities):
        a,b=i+1,(i+1)%n+1
        if p==0:f.extend([[a,-b],[-a,b]])
        else:f.extend([[a,b],[-a,-b]])
    return f

def cases(seed=20261231,count=40):
    rng=random.Random(seed)
    families=['modular_55_random','modular_55_planted','modular_72_random','random_55','random_72','xor_sat','xor_unsat','pigeonhole_unsat']
    result=[]
    for i in range(count):
        fam=families[i%len(families)]
        if fam.startswith('modular_55'):f=modular_3sat(rng,5,11,rng.uniform(3.8,4.45),1,fam.endswith('planted'))
        elif fam=='modular_72_random':f=modular_3sat(rng,6,12,rng.uniform(3.8,4.3),1,False)
        elif fam=='random_55':f=random_3sat(rng,55,rng.uniform(4.05,4.45),False)
        elif fam=='random_72':f=random_3sat(rng,72,rng.uniform(4.05,4.45),False)
        elif fam=='xor_sat':f=xor_chain(rng,55,False)
        elif fam=='xor_unsat':f=xor_chain(rng,55,True)
        else:f=pigeonhole(6,5)
        result.append((f'{i:04d}',fam,normalize(f)))
    return result

def components(adj,cut=()):
    remaining=set(adj)-set(cut);groups=[]
    while remaining:
        start=next(iter(remaining));remaining.remove(start)
        stack=[start];group={start}
        while stack:
            u=stack.pop()
            for v in adj[u]:
                if v in remaining:
                    remaining.remove(v);stack.append(v);group.add(v)
        groups.append(group)
    return sorted(groups,key=lambda s:-len(s))

def condition(cnf,assignment):
    out=set()
    for c in cnf:
        if any(l in assignment for l in c):continue
        new=frozenset(l for l in c if -l not in assignment)
        if not new:return {frozenset()}
        out.add(new)
    return out

def find_separator(cnf,adaptive=True,max_pairs=700):
    adj=primal_neighbors(cnf);n=len(adj)
    if n<20:return None,dict(reason='small',n=n)
    density=sum(map(len,adj.values()))/(n*(n-1))
    if adaptive and density>0.42:return None,dict(reason='dense',n=n,density=density)
    verts=sorted(adj,key=lambda v:(len(adj[v]),v));best=None;inspected=0
    for k in (1,2):
        if best is not None:break
        candidates=((v,) for v in verts) if k==1 else itertools.combinations(verts,2)
        for cut in candidates:
            if k==2 and inspected>=n+max_pairs:break
            inspected+=1;groups=components(adj,cut)
            if len(groups)<2 or len(groups[1])<4:continue
            residual=n-k
            if len(groups[0])>0.78*residual or residual/len(groups[0])<1.5:continue
            score=(len(groups[0])*2**k + (len(groups)-2)*2,-len(groups[1]),cut)
            if best is None or score<best[0]:best=(score,cut,groups)
    if best is None:return None,dict(reason='no_viable_cut',inspected=inspected,density=density)
    _,cut,groups=best
    return (cut,groups),dict(reason='selected',inspected=inspected,density=density,separator_size=len(cut),pieces=list(map(len,groups)))

def quick_cut(cnf,pair_cap=32,density_max=0.42):
    adj=primal_neighbors(cnf);n=len(adj)
    if n<20:return None,dict(reason='small',inspected=0)
    density=sum(map(len,adj.values()))/(n*(n-1))
    if density>density_max:return None,dict(reason='dense',inspected=0)
    verts=sorted(adj,key=lambda v:(len(adj[v]),v));inspected=0;best=None
    for k in (1,2):
        if best is not None:break
        candidates=((v,) for v in verts) if k==1 else itertools.islice(itertools.combinations(verts[:min(n,16)],2),pair_cap)
        for cut in candidates:
            inspected+=1;groups=components(adj,cut)
            if len(groups)<2 or len(groups[1])<4 or len(groups[0])>0.78*(n-k):continue
            score=(2**k*len(groups[0]),-len(groups[1]),cut)
            if best is None or score<best[0]:best=(score,cut,groups)
    if best is None:return None,dict(reason='no_cut',inspected=inspected,density=density)
    _,cut,groups=best
    return (cut,groups),dict(reason='selected',inspected=inspected,density=density,separator_size=len(cut),pieces=[len(g) for g in groups])

def solve_with_cut(cnf,selector=quick_cut,solver=solve):
    cnf=normalize(cnf);info,meta=selector(cnf)
    if info is None:
        ans,nodes=solver(cnf)
        return ans,nodes,meta
    cut,groups=info;v_group={v:i for i,group in enumerate(groups) for v in group}
    nodes=0;uncertain=False
    for signs in itertools.product((-1,1),repeat=len(cut)):
        reduced=condition(cnf,{v*s for v,s in zip(cut,signs)})
        if frozenset() in reduced:continue
        parts=[set() for _ in groups]
        for clause in reduced:
            which={v_group[abs(l)] for l in clause}
            if len(which)!=1:raise AssertionError('separator invalid')
            parts[next(iter(which))].add(clause)
        sat=True;local_unknown=False
        for part in parts:
            if not part:continue
            answer,n=solver(part);nodes+=n
            if answer is False:sat=False;break
            if answer is None:sat=False;local_unknown=True
        if sat:return True,nodes,meta
        uncertain|=local_unknown
    return (None if uncertain else False),nodes,meta

def brute_sat(cnf):
    vs=sorted({abs(l) for c in cnf for l in c})
    if len(vs)>15:raise ValueError('too many variables')
    for vals in itertools.product((False,True),repeat=len(vs)):
        model=dict(zip(vs,vals))
        if all(any(model[abs(l)]==(l>0) for l in c) for c in cnf):return True
    return False

def validate():
    rng=random.Random(20261031)
    stats={'bruteforce_comparisons':0,'cut_selected_correct':0}
    for i in range(120):
        n=rng.randint(2,11)
        f=[[x*rng.choice([-1,1]) for x in rng.sample(range(1,n+1),rng.randint(1,min(4,n)))] for _ in range(rng.randint(0,4*n))]
        f=normalize(f);truth=brute_sat(f)
        for algorithm in (lambda f:solve(f)[0],lambda f:solve_with_cut(f)[0],lambda f:solve_with_cut(f,selector=find_separator)[0]):
            if algorithm(f)!=truth:raise AssertionError(('validation',i,truth))
            stats['bruteforce_comparisons']+=1
    for i in range(30):
        f=normalize(modular_3sat(rng,5,11,4.1,1,True))
        expected=solve(f)[0];ans,n,meta=solve_with_cut(f)
        if ans!=expected:raise AssertionError(('cut',i))
        if meta['reason']=='selected':stats['cut_selected_correct']+=1
    return stats

def write_dimacs(path,cnf):
    n=max((abs(l) for c in cnf for l in c),default=0)
    with open(path,'w') as out:
        out.write(f'p cnf {n} {len(cnf)}\n')
        for c in sorted(cnf,key=lambda c:(len(c),tuple(sorted(c)))):
            out.write(' '.join(map(str,sorted(c,key=lambda x:(abs(x),x))))+' 0\n')

def cadical_cli(path,binary,timeout=30):
    t=time.perf_counter_ns()
    try:proc=subprocess.run([binary,str(path)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
    except subprocess.TimeoutExpired:raise RuntimeError('CaDiCaL timeout '+str(path))
    ms=(time.perf_counter_ns()-t)/1e6
    if proc.returncode==10:return True,ms
    if proc.returncode==20:return False,ms
    raise RuntimeError(f'CaDiCaL returncode {proc.returncode}: {proc.stderr.decode(errors="replace")[:500]}')

def benchmark(outdir,count=40,seed=20261231,reps=5,cadical=None):
    outdir=Path(outdir);outdir.mkdir(parents=True,exist_ok=True)
    dimdir=outdir/'dimacs';dimdir.mkdir(exist_ok=True)
    instances=cases(seed,count);rows=[]
    for idx,(case,fam,f) in enumerate(instances):
        dim=dimdir/f'{case}_{fam}.cnf';write_dimacs(dim,f)
        expected,_=solve(f)
        if expected is None:raise RuntimeError('DPLL budget '+case)
        methods=['dpll','v3_adaptive','v4_fast','cadical_cli']*reps
        rng=random.Random(seed+idx);rng.shuffle(methods)
        for method in methods:
            start=time.perf_counter_ns()
            if method=='cadical_cli':
                if not cadical:raise RuntimeError('CaDiCaL binary missing')
                answer,elapsed=cadical_cli(dim,cadical);nodes=None;meta={}
            elif method=='dpll':
                answer,nodes=solve(f);elapsed=(time.perf_counter_ns()-start)/1e6;meta={}
            elif method=='v3_adaptive':
                answer,nodes,meta=solve_with_cut(f,selector=find_separator)
                elapsed=(time.perf_counter_ns()-start)/1e6
            else:
                answer,nodes,meta=solve_with_cut(f)
                elapsed=(time.perf_counter_ns()-start)/1e6
            if answer is None or answer!=expected:raise AssertionError((case,method,answer,expected))
            rows.append(dict(case=case,family=fam,method=method,ms=elapsed,answer='SAT' if answer else 'UNSAT',nodes=nodes,selected=meta.get('reason')=='selected',inspected=meta.get('inspected',0),nvars=max(abs(l) for c in f for l in c),clauses=len(f)))
        print('Checked:',idx+1,'/',count,case,fam,flush=True)
    with (outdir/'measurements.csv').open('w',newline='') as fp:
        w=csv.DictWriter(fp,fieldnames=list(rows[0].keys()));w.writeheader();w.writerows(rows)
    summary={};by_family={}
    for method in sorted({r['method'] for r in rows}):
        sub=[r for r in rows if r['method']==method]
        medians=[statistics.median(r['ms'] for r in sub if r['case']==case) for case,_,_ in instances]
        summary[method]=dict(cases=count,sum_medians_ms=round(sum(medians),3),median_case_ms=round(statistics.median(medians),4),
                             cases_faster_than_dpll=None)
        by_family[method]={fam:round(sum(statistics.median(r['ms'] for r in sub if r['case']==case) for case,f,_ in instances if f==fam),3) for fam in sorted({f for _,f,_ in instances})}
    dpll_meds={case:statistics.median(r['ms'] for r in rows if r['case']==case and r['method']=='dpll') for case,_,_ in instances}
    for method in summary:
        summary[method]['cases_faster_than_dpll']=sum(statistics.median(r['ms'] for r in rows if r['case']==case and r['method']==method)<dpll_meds[case] for case,_,_ in instances) if method!='dpll' else None
    report=dict(seed=seed,cases=count,repetitions=reps,python=platform.python_version(),
                platform=platform.platform(),cadical_binary=cadical,validation=validate(),summary=summary,
                by_family=by_family,
                caveats=['Synthetic formulas, not SAT Competition benchmark','CaDiCaL process launch and I/O included','Python vs native C++ is not algorithm-only comparison','Microsecond timings are noisy'])
    (outdir/'summary.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--outdir',default='bench_cadical')
    p.add_argument('--seed',type=int,default=20261231)
    p.add_argument('--count',type=int,default=40)
    p.add_argument('--reps',type=int,default=5)
    p.add_argument('--cadical',required=True)
    a=p.parse_args()
    benchmark(a.outdir,a.count,a.seed,a.reps,a.cadical)
