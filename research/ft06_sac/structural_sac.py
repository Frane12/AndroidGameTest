#!/usr/bin/env python3
"""Raw-CNF singleton arc-consistency UNSAT; source-bound DRAT/RUP proof.
No job-shop metadata, expected outcome, or CDCL is supplied to this module.
Output must be independently checked with drat-trim before claiming UNSAT.
"""
import argparse, hashlib, json, time
from pathlib import Path
from collections import deque, defaultdict

def parse(raw):
    nv=nc=None; cs=[]; curr=[]
    for line in raw.decode('ascii').splitlines():
        s=line.split()
        if not s or s[0]=='c':continue
        if s[0]=='p':
            if nv is not None or len(s)!=4 or s[1]!='cnf':raise ValueError('header')
            nv,nc=int(s[2]),int(s[3]);continue
        if nv is None:raise ValueError('missing header')
        for tok in s:
            lit=int(tok)
            if lit:
                if abs(lit)>nv:raise ValueError('literal range')
                curr.append(lit)
            else:cs.append(tuple(curr));curr=[]
    if nv is None or curr or len(cs)!=nc:raise ValueError('clause count')
    return nv,cs

def preparation(raw):
    _,cs=parse(raw)
    groups=[cl for cl in cs if len(cl)>=2 and all(v>0 for v in cl)]
    membership={}
    for i,g in enumerate(groups):
        for j,x in enumerate(g):
            if x in membership:raise ValueError('overlapping source domains')
            membership[x]=(i,j)
    if not groups:raise ValueError('no source domains')
    forbidden=defaultdict(set)
    for cl in cs:
        if len(cl)!=2 or cl[0]>=0 or cl[1]>=0:continue
        a=membership.get(-cl[0]);b=membership.get(-cl[1])
        if a is None or b is None or a[0]==b[0]:continue
        if a[0]>b[0]:a,b=b,a
        forbidden[a[0],b[0]].add((a[1],b[1]))
    support={};adj=[set() for _ in groups]
    for (u,v),bad in forbidden.items():
        forward=[(1<<len(groups[v]))-1 for _ in groups[u]]
        backward=[(1<<len(groups[u]))-1 for _ in groups[v]]
        for i,j in bad:
            forward[i]&=~(1<<j);backward[j]&=~(1<<i)
        support[u,v]=forward;support[v,u]=backward
        adj[u].add(v);adj[v].add(u)
    return groups,support,adj,len(forbidden)

def bits(mask):
    while mask:
        bit=mask&-mask;yield bit.bit_length()-1;mask-=bit

def propagate(D,groups,support,adj,proof,pivot=None,queue=None):
    if queue is None:queue=deque(support)
    while queue:
        u,v=queue.popleft()
        drop=0
        for i in bits(D[u]):
            if not(support[u,v][i]&D[v]):drop|=1<<i
        if not drop:continue
        for i in bits(drop):
            clause={-groups[u][i]}
            if pivot is not None:clause.add(-pivot)
            proof.append(tuple(sorted(clause)))
        D[u]&=~drop
        if not D[u]:return False
        for k in adj[u]:
            if k!=v:queue.append((k,u))
    return True

def derive(raw,seconds=30,cap=6000):
    start=time.perf_counter()
    groups,support,adj,nlinks=preparation(raw)
    D=[(1<<len(g))-1 for g in groups];proof=[]
    checks=removed=0
    def result(status):
        return dict(status=status,source_sha256=hashlib.sha256(raw).hexdigest(),
            groups=len(groups),cross_links=nlinks,checks=checks,
            singleton_eliminations=removed,elapsed_s=round(time.perf_counter()-start,6),
            proof=proof if status=='UNSAT' else [])
    if not propagate(D,groups,support,adj,proof):return result('UNSAT')
    while time.perf_counter()-start<seconds:
        progress=False
        for u in sorted(range(len(D)),key=lambda a:D[a].bit_count()):
            for i in list(bits(D[u])):
                if checks>=cap or time.perf_counter()-start>=seconds:return result('UNKNOWN')
                checks+=1;p=groups[u][i]
                trial=D[:];trial[u]=1<<i
                temporary=[tuple(sorted((-p,-groups[u][j]))) for j in bits(D[u]&~(1<<i))]
                if not propagate(trial,groups,support,adj,temporary,pivot=p,
                                 queue=deque((v,u) for v in adj[u])):
                    proof.extend(temporary);proof.append((-p,))
                    D[u]&=~(1<<i);removed+=1;progress=True
                    if D[u]==0:return result('UNSAT')
                    queue=deque((v,u) for v in adj[u])
                    queue.extend((u,v) for v in adj[u])
                    if not propagate(D,groups,support,adj,proof,queue=queue):
                        return result('UNSAT')
        if not progress:break
    return result('UNKNOWN')

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('cnf',type=Path)
    ap.add_argument('--drat',type=Path)
    ap.add_argument('--report',type=Path)
    ap.add_argument('--seconds',type=float,default=30)
    args=ap.parse_args()
    raw=args.cnf.read_bytes()
    try:r=derive(raw,args.seconds)
    except (ValueError,UnicodeError) as e:
        r={'status':'UNKNOWN','reason':str(e)}
    if r['status']=='UNSAT' and args.drat:
        if args.drat.exists():raise SystemExit('refusing to overwrite proof')
        r['proof_lemmas']=len(r['proof'])
        args.drat.write_text(''.join(' '.join(map(str,c))+' 0\n' for c in r['proof'])+'0\n')
    r.pop('proof',None)
    if args.report:args.report.write_text(json.dumps(r,indent=2,sort_keys=True)+'\n')
    print('SAC_RESULT '+json.dumps(r,sort_keys=True))
if __name__=='__main__':main()
