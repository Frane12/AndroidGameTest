#!/usr/bin/env python3
"""Experimental PCMAX capacity guard: fail closed, structural certificate only.

Derive a strict |S| > sum_m c_m(S) contradiction from original DIMACS clauses.
Every BDD transition, root, false terminal, and assignment group must be
present in the source CNF. The guard never emits DIMACS UNSAT exit 20:
the certificate is structural, not DRAT/LRAT.
"""
import argparse, collections, hashlib, json, pathlib, sys, time

class NotRecognized(Exception):
    pass

def parse_cnf(path):
    sha=hashlib.sha256(path.read_bytes()).hexdigest()
    n=m=None
    clauses=[];current=[]
    for line in path.open('r',encoding='ascii',errors='replace'):
        line=line.strip()
        if not line or line.startswith('c'):continue
        if line.startswith('%'):break
        if line.startswith('p '):
            parts=line.split()
            if len(parts)<4 or parts[1]!='cnf':raise NotRecognized('non-cnf')
            n,m=map(int,parts[2:4]);continue
        if n is None:raise NotRecognized('missing header')
        for token in line.split():
            x=int(token)
            if x==0:
                if not current or len(set(current))!=len(current) or any(-v in current for v in current):
                    raise NotRecognized('noncanonical clause')
                clauses.append(tuple(current));current=[]
            elif abs(x)>n:raise NotRecognized('literal outside range')
            else:current.append(x)
    if current or n is None or len(clauses)!=m:raise NotRecognized('bad CNF header')
    return sha,n,clauses

def derive(path,expected_sha=None,max_ms=2000):
    start_time=time.perf_counter()
    def check_time():
        if 1000*(time.perf_counter()-start_time)>max_ms:
            raise NotRecognized('guard budget exceeded')
    path=pathlib.Path(path)
    sha,n,clauses=parse_cnf(path)
    if expected_sha and sha!=expected_sha:raise NotRecognized('source SHA drift')
    check_time()
    orig=set(clauses)
    groups=[c for c in clauses if len(c)>=2 and all(x>0 for x in c)]
    if len(groups)<2:raise NotRecognized('no assignment groups')
    choice_group={}
    for j,g in enumerate(groups):
        for x in g:
            if x in choice_group:raise NotRecognized('overlapping jobs')
            choice_group[x]=j
    choices=set(choice_group)
    maxchoice=max(choices)
    edges=collections.defaultdict(dict)
    witnesses={}
    for c in clauses:
        if len(c)!=3:continue
        sel=[v for v in c if abs(v) in choices]
        rem=[v for v in c if abs(v) not in choices]
        if len(sel)!=1 or len(rem)!=2:continue
        ns=[-v for v in rem if v<0]
        pc=[v for v in rem if v>0]
        if len(ns)!=1 or len(pc)!=1:continue
        state,child=ns[0],pc[0]
        if state<=maxchoice or child<=maxchoice:continue
        var=abs(sel[0]);branch=int(sel[0]<0)
        if branch in edges[state] and edges[state][branch]!=(var,child):
            raise NotRecognized('ambiguous transition')
        edges[state][branch]=(var,child)
        witnesses[(state,branch)]=c
    if not edges:raise NotRecognized('no BDD')
    if any(set(b)!={0,1} or len({v for v,_ in b.values()})!=1 for b in edges.values()):
        raise NotRecognized('incomplete BDD branching')
    pos={c[0] for c in clauses if len(c)==1 and c[0]>maxchoice}
    neg={-c[0] for c in clauses if len(c)==1 and c[0]<-maxchoice}
    roots=sorted(pos&edges.keys())
    good=pos-set(roots);bad=neg
    if not roots or len(roots)!=len(good) or len(roots)!=len(bad):
        raise NotRecognized('ambiguous roots/terminals')
    if good&bad or (good|bad)&edges.keys():
        raise NotRecognized('bad terminal encoding')
    check_time()
    machine_of=collections.defaultdict(set)
    machine_states=[];global_states=set()
    for mid,root in enumerate(roots):
        seen=set();stack=[root]
        while stack:
            s=stack.pop()
            if s in seen:continue
            if s in good or s in bad:continue
            if s not in edges:raise NotRecognized('missing state')
            if s in global_states:raise NotRecognized('shared BDD state')
            seen.add(s)
            for branch,(var,child) in edges[s].items():
                if witnesses[(s,branch)] not in orig:raise NotRecognized('absent source witness')
                if child<=s:raise NotRecognized('non-DAG edge')
                if child not in good and child not in bad:stack.append(child)
                machine_of[var].add(mid)
        machine_states.append(seen);global_states.update(seen)
    if len(global_states)!=len(edges):raise NotRecognized('unreachable states')
    if any(len(machine_of[x])!=1 for x in choices):
        raise NotRecognized('selector not uniquely owned')
    stage={s:choice_group[edges[s][0][0]] for s in edges}
    for mid,seen in enumerate(machine_states):
        for s in seen:
            var0,child0=edges[s][0];var1,child1=edges[s][1]
            if var0!=var1 or next(iter(machine_of[var0]))!=mid:
                raise NotRecognized('machine selector mismatch')
            for child in (child0,child1):
                if child in edges and stage[child]<=stage[s]:
                    raise NotRecognized('BDD stage not increasing')
    per_machine=[collections.Counter() for _ in roots]
    for x,j in choice_group.items():
        per_machine[next(iter(machine_of[x]))][j]+=1
    def missing(mid,a,b):
        return sum(per_machine[mid].get(j,0) for j in range(a,b))
    nj=len(groups)
    found=None
    for prefix in range(1,nj+1):
        bounds=[];detail=[]
        for mid,(root,seen) in enumerate(zip(roots,machine_states)):
            best={root:missing(mid,0,min(stage[root],prefix))}
            for s in sorted(seen):
                if s not in best:continue
                cur=best[s];j=stage[s]
                for branch,(var,child) in edges[s].items():
                    if child in bad:continue
                    nextj=stage[child] if child in edges else nj
                    val=cur+(branch if j<prefix else 0)+missing(mid,min(j+1,prefix),min(nextj,prefix))
                    if val>best.get(child,-1):best[child]=val
            maxima=[best[t] for t in good if t in best]
            if not maxima:raise NotRecognized('machine without accepting path')
            bound=max(maxima);bounds.append(bound)
            detail.append({'machine':mid,'root':root,'states':len(seen),'bound':bound})
        check_time()
        if sum(bounds)<prefix:
            found=(prefix,bounds,detail)
            break
    if found:prefix,bounds,detail=found
    else:prefix=nj
    return {
        'status':'UNSAT_STRUCT_VERIFIED' if found else 'UNKNOWN',
        'cnf_sha256':sha,'variables':n,'clauses':len(clauses),
        'jobs':nj,'machines':len(roots),'states':len(edges),
        'demand':prefix,'capacity':sum(bounds),'bounds':bounds,
        'detail':detail,'prefix_jobs':prefix,
        'certificate_kind':'CNF_BDD_CAPACITY_NOT_DRAT_LRAT',
        'elapsed_ms':round(1000*(time.perf_counter()-start_time),3)
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('cnf',type=pathlib.Path)
    ap.add_argument('--sha256')
    ap.add_argument('--max-ms',type=int,default=2000)
    args=ap.parse_args()
    try:result=derive(args.cnf,args.sha256,args.max_ms)
    except (NotRecognized,AssertionError,ValueError,IndexError,KeyError,OverflowError,RecursionError) as e:
        result={'status':'UNKNOWN','reason':str(e)}
    print(json.dumps(result,sort_keys=True))
    return 0

if __name__=='__main__':sys.exit(main())
