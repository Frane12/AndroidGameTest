#!/usr/bin/env python3
"""Experimental source-grounded weighted-cubic-graph parity prover.

Hints are untrusted. Completeness relies only on rechecking source
clauses and a fully enumerated bounded set of perfect matchings.
"""
import argparse, hashlib, itertools, json
from collections import defaultdict
from pathlib import Path

FORMAT='DRNAS-MATCH4-SOURCE-WEIGHTED-GRAPH-V1'
MAX_EDGES=15

def read_cnf(raw):
    nv=nc=None; cs=[]; pending=[]
    for ln in raw.decode('ascii').splitlines():
        a=ln.split()
        if not a or a[0]=='c':continue
        if a[0]=='p':
            if nv is not None or len(a)!=4 or a[1]!='cnf':raise ValueError('header')
            nv,nc=map(int,a[2:]);continue
        if nv is None:raise ValueError('missing header')
        for tok in a:
            x=int(tok)
            if abs(x)>nv:raise ValueError('literal bound')
            if x:pending.append(x)
            else:cs.append(tuple(pending));pending=[]
    if nv is None or pending or len(cs)!=nc or nc>10000:raise ValueError('DIMACS count')
    return nv,cs

def get_groups(nv,cs):
    groups=[tuple(c) for c in cs if len(c)==3 and len(set(c))==3 and all(x>0 for x in c)]
    if not (6<=len(groups)<=MAX_EDGES) or nv!=3*len(groups):raise ValueError('ALO count')
    owner={}
    for j,g in enumerate(groups):
        for v in g:
            if v in owner:raise ValueError('overlap')
            owner[v]=j
    if set(owner)!=set(range(1,nv+1)):raise ValueError('unmapped variables')
    source={frozenset(c) for c in cs}
    for g in groups:
        for a,b in itertools.combinations(g,2):
            if frozenset((-a,-b)) not in source:raise ValueError('AMO absent')
    return groups,owner

def resources(owner,cs,n):
    parent={v:v for v in owner}
    def root(a):
        while parent[a]!=a:
            parent[a]=parent[parent[a]];a=parent[a]
        return a
    def join(a,b):
        x,y=root(a),root(b)
        if x!=y:parent[max(x,y)]=min(x,y)
    for c in cs:
        if len(c)<2 or any(x>=0 or -x not in owner for x in c):continue
        if len({owner[-x] for x in c})!=len(c):continue
        for x in c[1:]:join(-c[0],-x)
    d=defaultdict(list)
    for v in owner:d[root(v)].append(v)
    rr=sorted([sorted(v) for v in d.values()],key=lambda x:x[0])
    if len(rr)!=3 or any(len(r)!=n or len({owner[x] for x in r})!=n for r in rr):
        raise ValueError('no complete 3-resource partition')
    return rr

def graph(weights):
    if not weights or len(weights)>MAX_EDGES or any(type(w)!=int or w<=0 for w in weights):
        raise ValueError('weights')
    edges=[];tops=[]
    for w in weights:
        positions=[];v=0
        while w:
            d=w%3
            if d==1:positions.append(v)
            elif d!=0:raise ValueError('weight not sum of two ternary unit powers')
            w//=3;v+=1
        if len(positions)!=2:raise ValueError('not edge weight')
        edges.append(tuple(positions));tops.extend(positions)
    V=max(tops)+1
    if V>12 or set(tops)!=set(range(V)) or len(edges)*2!=V*3 or len(set(edges))!=len(edges):
        raise ValueError('not simple cubic graph')
    degree=[tops.count(v) for v in range(V)]
    if any(d!=3 for d in degree):raise ValueError('not cubic')
    return edges,V,sum(3**v for v in range(V))

def source_entails_capacity(groups,owner,rr,cs,weights,T):
    n=len(groups);N=1<<n
    sums=[0]*N
    for mask in range(1,N):
        b=mask & -mask; j=b.bit_length()-1;sums[mask]=sums[mask^b]+weights[j]
    assert sum(weights)==3*T
    data=[]
    for r in rr:
        rset=set(r);bans=set()
        for c in cs:
            if c and all(x<0 and -x in rset for x in c):
                bans.add(sum(1<<owner[-x] for x in c))
        if not bans:raise ValueError('no source bans')
        allowed=0
        for mask in range(N):
            admissible=not any((mask & b)==b for b in bans)
            if admissible:
                if sums[mask]>T:raise ValueError('source does not imply candidate bound')
                allowed+=1
        data.append({'allowed_masks':allowed,'negative_source_clauses':len(bans)})
    return data

def perfect_matchings(edges,V,limit=100):
    incident=[[] for _ in range(V)]
    for idx,(a,b) in enumerate(edges):
        incident[a].append((idx,b));incident[b].append((idx,a))
    out=[]
    def recurse(free,selected):
        if len(out)>limit:return
        if not free:out.append(tuple(sorted(selected)));return
        u=min(free)
        for idx,v in incident[u]:
            if v in free:
                recurse(free-{u,v},selected+(idx,))
                if len(out)>limit:return
    recurse(set(range(V)),tuple())
    return sorted(set(out)),len(out)>limit

def complement_odd(edges,V,matching):
    chosen=set(matching);adj=[[] for _ in range(V)]
    for k,(u,v) in enumerate(edges):
        if k not in chosen:adj[u].append(v);adj[v].append(u)
    if any(len(a)!=2 for a in adj):raise ValueError('invalid matching')
    unseen=set(range(V))
    while unseen:
        start=min(unseen);cyc=[start];before=None;now=start
        while True:
            nxt=next((a for a in adj[now] if a!=before),None)
            if nxt is None:raise ValueError('cycle')
            if nxt==start:break
            if nxt in cyc:raise ValueError('non cycle complement')
            cyc.append(nxt);before,now=now,nxt
        unseen.difference_update(cyc)
        if len(cyc)%2:return cyc
    return None

def hint_from_comments(raw):
    for ln in raw.decode('ascii').splitlines():
        if ln.startswith('c Item sizes:'):
            try:return [int(v) for v in ln.split(':',1)[1].strip().split()]
            except ValueError:return None
    return None

def prove(raw,weights=None):
    out={'format':FORMAT,'source_sha256':hashlib.sha256(raw).hexdigest(),
         'status':'UNKNOWN','method':'NONE'}
    try:
        nv,cs=read_cnf(raw); groups,owner=get_groups(nv,cs)
        weights=weights if weights is not None else hint_from_comments(raw)
        if weights is None or len(weights)!=len(groups):
            out['reason']='no_candidate_weight_hint';return out
        edges,V,T=graph(weights)
        rr=resources(owner,cs,len(groups))
        loc=source_entails_capacity(groups,owner,rr,cs,weights,T)
        matchings,overflow=perfect_matchings(edges,V)
        if overflow:
            out['reason']='matching_count_exceeded';return out
        if not matchings:
            out['reason']='no_matching';return out
        records=[]
        for mat in matchings:
            odd=complement_odd(edges,V,mat)
            if odd is None:
                out['reason']='3_edge_coloring_not_excluded';return out
            records.append({'matching':list(mat),'odd_cycle':odd})
        out.update({'status':'UNSAT_UNCHECKED','method':'MATCH4-ORIGINAL-SOURCE-PARITY',
            'source_variables':nv,'source_clauses':len(cs),'groups':[list(g) for g in groups],
            'resources':rr,'weights':weights,'vertices':V,'bound':T,
            'local_source_supports':loc,'matching_count':len(records),
            'matching_odd_witnesses':records})
    except (ValueError,TypeError,IndexError,UnicodeError,OverflowError,RecursionError) as e:
        out['reason']=str(e)
    return out

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('cnf',type=Path);p.add_argument('--certificate',type=Path,required=True)
    p.add_argument('--weights-json',type=Path);a=p.parse_args()
    weights=json.loads(a.weights_json.read_text()) if a.weights_json else None
    obj=prove(a.cnf.read_bytes(),weights)
    a.certificate.write_text(json.dumps(obj,indent=2,sort_keys=True)+'\n')
    print('MATCH4_PRODUCER '+json.dumps({k:v for k,v in obj.items() if k not in ('groups','resources','matching_odd_witnesses')},sort_keys=True),flush=True)
