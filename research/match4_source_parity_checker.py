#!/usr/bin/env python3
"""Independent original-CNF source + parity certificate checker.

Uses neither the producer nor comments / filenames / declared SAT status as
premises. Enumerates bounded masks and matchings independently. Project-specific
certificate, NOT VeriPB, LRAT or DRAT.
"""
import argparse,hashlib,itertools,json
from pathlib import Path
FORMAT='DRNAS-MATCH4-SOURCE-WEIGHTED-GRAPH-V1'

def parse(raw):
    nv=expected=None;clauses=[];tmp=[]
    for line in raw.decode('ascii').splitlines():
        words=line.split()
        if not words or words[0]=='c':continue
        if words[0]=='p':
            if nv is not None or len(words)!=4 or words[1]!='cnf':raise ValueError('source header')
            nv,expected=int(words[2]),int(words[3]);continue
        if nv is None:raise ValueError('missing source header')
        for token in words:
            x=int(token)
            if abs(x)>nv:raise ValueError('out-of-range source literal')
            if x:tmp.append(x)
            else:clauses.append(frozenset(tmp));tmp=[]
    if nv is None or tmp or len(clauses)!=expected or expected>10000:raise ValueError('source clause count')
    return nv,clauses

def check(raw,cert):
    if (cert.get('format')!=FORMAT or cert.get('method')!='MATCH4-ORIGINAL-SOURCE-PARITY'
            or cert.get('status')!='UNSAT_UNCHECKED'):
        raise ValueError('wrong proof claim')
    digest=hashlib.sha256(raw).hexdigest()
    if cert.get('source_sha256')!=digest:raise ValueError('source mutated')
    nv,clauses=parse(raw);src=set(clauses)
    groups=cert.get('groups');resources=cert.get('resources');weights=cert.get('weights')
    if not isinstance(groups,list) or not 6<=len(groups)<=15 or nv!=3*len(groups):
        raise ValueError('bad ALO groups')
    if (not isinstance(resources,list) or len(resources)!=3 or
            not isinstance(weights,list) or len(weights)!=len(groups)):
        raise ValueError('bad resource/weight format')
    varjob={}
    for j,g in enumerate(groups):
        if not isinstance(g,list) or len(g)!=3 or len(set(g))!=3:
            raise ValueError('bad ALO group')
        if frozenset(g) not in src:raise ValueError('ALO missing from source')
        for x in g:
            if type(x)!=int or not 1<=x<=nv or x in varjob:
                raise ValueError('selector reuse')
            varjob[x]=j
        for x,y in itertools.combinations(g,2):
            if frozenset((-x,-y)) not in src:raise ValueError('AMO missing')
    if set(varjob)!=set(range(1,nv+1)):raise ValueError('not full input assignment groups')
    touched=set();resource_for_job=[]
    for rr in resources:
        if not isinstance(rr,list) or len(rr)!=len(groups) or len(set(rr))!=len(rr):
            raise ValueError('resource size')
        if any(type(x)!=int or x not in varjob for x in rr) or touched.intersection(rr):
            raise ValueError('bad resource partition')
        touched.update(rr)
        if {varjob[x] for x in rr}!=set(range(len(groups))):
            raise ValueError('resource contains duplicate or missing job')
        resource_for_job.append(rr)
    if touched!=set(varjob):raise ValueError('resources do not cover input')
    # Pure integer base-three parsing, distinct from candidate producer parser.
    ends=[]
    for size in weights:
        if type(size)!=int or size<=0:raise ValueError('invalid job size')
        digits=[];temp=size;bit=0
        while temp:
            q,rem=divmod(temp,3)
            if rem==2:raise ValueError('size is not graph edge')
            if rem:digits.append(bit)
            temp=q;bit+=1
        if len(digits)!=2:raise ValueError('bad edge size')
        ends.append(tuple(digits))
    vertex_count=max(max(e) for e in ends)+1
    if vertex_count>12 or len(set(ends))!=len(ends) or vertex_count*3!=len(ends)*2:
        raise ValueError('cubic graph count')
    degree=[0]*vertex_count
    for x,y in ends:
        degree[x]+=1;degree[y]+=1
    if any(k!=3 for k in degree):raise ValueError('graph not cubic')
    T=sum(pow(3,i) for i in range(vertex_count))
    if sum(weights)!=3*T or cert.get('bound')!=T or cert.get('vertices')!=vertex_count:
        raise ValueError('not tight three machine packing')
    if cert.get('source_variables')!=nv or cert.get('source_clauses')!=len(clauses):
        raise ValueError('wrong original source size')
    # Independent support checker: mark all supersets of every source ban invalid.
    N=1<<len(groups);full=N-1;details=[]
    for r in resource_for_job:
        allowed=bytearray(b'\x01')*N
        bans=set()
        local=set(r)
        for c in clauses:
            if c and all(x<0 and -x in local for x in c):
                ban=0
                for x in c:ban |= 1<<varjob[-x]
                bans.add(ban)
        if not bans:raise ValueError('no local constraints')
        for ban in bans:
            free=full^ban;mask=free
            while True:
                allowed[ban|mask]=0
                if not mask:break
                mask=(mask-1)&free
        for mask in range(N):
            if allowed[mask] and sum(weights[i] for i in range(len(groups)) if mask>>i&1)>T:
                raise ValueError('source fails proposed PB upper bound')
        details.append({'allowed_masks':sum(allowed),'negative_source_clauses':len(bans)})
    if cert.get('local_source_supports')!=details:
        raise ValueError('source statistics tampered')
    # Independent complete matching enumerator via memoized vertex bitmask recursion.
    adj=[[] for _ in range(vertex_count)]
    for i,(u,v) in enumerate(ends):
        adj[u].append((v,i));adj[v].append((u,i))
    memo={}
    def enum(free):
        if not free:return ((),)
        if free in memo:return memo[free]
        low=free & -free;u=low.bit_length()-1
        out=[]
        for v,idx in adj[u]:
            if free&(1<<v):
                for rest in enum(free^(1<<u)^(1<<v)):
                    out.append(tuple(sorted((idx,)+rest)))
                    if len(out)>100:raise ValueError('matching count exceeds fixed pilot budget')
        memo[free]=tuple(sorted(set(out)))
        return memo[free]
    actual=set(enum((1<<vertex_count)-1))
    entries=cert.get('matching_odd_witnesses')
    if not isinstance(entries,list) or not entries or len(entries)!=len(actual):
        raise ValueError('incomplete matching list')
    supplied=set()
    for entry in entries:
        if not isinstance(entry,dict):raise ValueError('wrong matching record')
        match=entry.get('matching');cycle=entry.get('odd_cycle')
        if (not isinstance(match,list) or len(match)*2!=vertex_count or
                any(type(i)!=int or not 0<=i<len(ends) for i in match) or
                len(set(match))!=len(match)):
            raise ValueError('bad matching')
        key=tuple(sorted(match))
        if key not in actual or key in supplied:raise ValueError('not a complete distinct matching')
        supplied.add(key)
        if not isinstance(cycle,list) or len(cycle)%2!=1 or len(cycle)<3 or len(set(cycle))!=len(cycle):
            raise ValueError('bad odd cycle')
        if any(type(v)!=int or not 0<=v<vertex_count for v in cycle):raise ValueError('cycle vertex')
        left={tuple(sorted(ends[i])) for i in range(len(ends)) if i not in match}
        for a,b in zip(cycle,cycle[1:]+cycle[:1]):
            if tuple(sorted((a,b))) not in left:raise ValueError('not an actual residual odd cycle')
    if supplied!=actual or cert.get('matching_count')!=len(actual):
        raise ValueError('matchings not exhaustive')
    return {'status':'MATCH4_ORIGINAL_SOURCE_PARITY_VERIFIED',
            'source_sha256':digest,'jobs':len(groups),'source_clauses':len(clauses),
            'vertices':vertex_count,'complete_perfect_matchings':len(actual),
            'local_source_supports':details}

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('cnf',type=Path);ap.add_argument('certificate',type=Path)
    a=ap.parse_args()
    try:
        result=check(a.cnf.read_bytes(),json.loads(a.certificate.read_text()))
        print('MATCH4_SOURCE_VERIFIED '+json.dumps(result,sort_keys=True),flush=True)
    except (ValueError,KeyError,IndexError,TypeError,UnicodeError,OverflowError) as e:
        print('MATCH4_REJECT '+str(e),flush=True)
        raise SystemExit(1)
