#!/usr/bin/env python3
"""Independent Python certificate checker for DRNAS V15.3 structural UNSAT paths.
Checks original input clauses, not C++ internal flags. Does not replace LRAT/DRAT.
"""
from collections import defaultdict
from itertools import combinations
def _unit(payload,clauses):
    trace=payload.get("unit_trace")
    ci=payload.get("conflict_clause")
    if not isinstance(trace,list) or not isinstance(ci,int) or ci<0 or ci>=len(clauses):
        return False
    a={}
    for entry in trace:
        if not isinstance(entry,list) or len(entry)!=2:return False
        lit,reason=entry
        if not isinstance(lit,int) or not isinstance(reason,int) or lit==0:return False
        if not 0<=reason<len(clauses) or abs(lit) in a:return False
        if lit not in clauses[reason]:return False
        if any(abs(x) not in a or a[abs(x)]==(x>0)
               for x in clauses[reason] if x!=lit):return False
        a[abs(lit)]=lit>0
    return all(abs(x) in a and a[abs(x)]!=(x>0) for x in clauses[ci])
def _binary(payload,clauses):
    v=payload.get("variable")
    a=payload.get("path_pos_to_neg")
    b=payload.get("path_neg_to_pos")
    if not isinstance(v,int) or v<1 or not isinstance(a,list) or not isinstance(b,list):
        return False
    edges=set()
    for cl in clauses:
        if len(cl)==1:edges.add((-cl[0],cl[0]))
        elif len(cl)==2:
            x,y=cl;edges.add((-x,y));edges.add((-y,x))
    def valid(path,start,end):
        return len(path)>=2 and path[0]==start and path[-1]==end and all(
            (path[i],path[i+1]) in edges for i in range(len(path)-1))
    return valid(a,v,-v) and valid(b,-v,v)
def _exhaustive(payload,clauses):
    support=payload.get("support",[])
    if not isinstance(support,list) or len(set(support))!=len(support) or not 1<=len(support)<=10:return False
    support=tuple(sorted(support))
    masks=set()
    for cl in clauses:
        if len(cl)!=len(support) or tuple(sorted(map(abs,cl)))!=support:continue
        masks.add(sum(1<<i for i,v in enumerate(support) if -v in cl))
    return len(masks)==(1<<len(support))
def _affine(payload,clauses):
    patterns=defaultdict(set)
    for cl in clauses:
        if not 2<=len(cl)<=10:continue
        support=tuple(sorted(map(abs,cl)))
        if len(set(support))!=len(support):continue
        mask=sum(1<<i for i,v in enumerate(support) if -v in cl)
        patterns[support].add(mask)
    equations=[]
    for support,masks in sorted(patterns.items(),
            key=lambda e:e[0]+(0,)*(10-len(e[0]))):
        count=1<<len(support)
        if len(masks)<count//2:continue
        if len(masks)==count:return False # Should take exhaustive route first.
        parity={m.bit_count()%2 for m in range(count) if m not in masks}
        if len(parity)==1:
            equations.append((set(support),next(iter(parity))))
    rows=payload.get("proof_rows")
    if not isinstance(rows,list) or not rows:return False
    vars_=set();rhs=0
    for idx in rows:
        if not isinstance(idx,int) or not 0<=idx<len(equations):return False
        support,p=equations[idx]
        vars_=vars_.symmetric_difference(support)
        rhs^=p
    return not vars_ and rhs==1
def _php(payload,clauses):
    holes=payload.get("holes");birds=payload.get("pigeons")
    if not isinstance(holes,int) or not isinstance(birds,int) or birds<=holes or holes<2:return False
    pos=[cl for cl in clauses if len(cl)==holes and all(v>0 for v in cl)]
    neg=[cl for cl in clauses if len(cl)==2 and all(v<0 for v in cl)]
    if len(pos)!=birds or len(pos)+len(neg)!=len(clauses):return False
    if len({v for cl in pos for v in cl})!=holes*birds:return False
    bird_of={v:b for b,cl in enumerate(pos) for v in cl}
    if any(len(set(cl))!=holes for cl in pos):return False
    pairs=set()
    for cl in neg:
        a,b=map(abs,cl)
        if a==b or a not in bird_of or b not in bird_of or bird_of[a]==bird_of[b]:return False
        key=tuple(sorted((a,b)))
        if key in pairs:return False
        pairs.add(key)
    if len(pairs)!=holes*birds*(birds-1)//2:return False
    # Variables at each identical hole form cliques across birds.
    adj=defaultdict(set)
    for a,b in pairs:adj[a].add(b);adj[b].add(a)
    seen=set();components=[]
    for v in bird_of:
        if v in seen:continue
        todo=[v];seen.add(v);comp=set()
        while todo:
            u=todo.pop();comp.add(u)
            for w in adj[u]:
                if w not in seen:seen.add(w);todo.append(w)
        components.append(comp)
    return len(components)==holes and all(
        len(comp)==birds and len({bird_of[v] for v in comp})==birds for comp in components)

def _hall(payload, clauses):
    """Replay a Hall deficiency from the positive ALO/negative AMO sub-CNF."""
    birds=[cl for cl in clauses if 3<=len(cl)<=32 and all(v>0 for v in cl)]
    if not 3<=len(birds)<=512:return False
    bird_of={}
    for b,cl in enumerate(birds):
        for lit in cl:
            if lit in bird_of:return False
            bird_of[lit]=b
    negatives=set()
    for cl in clauses:
        if len(cl)!=2 or cl[0]>=0 or cl[1]>=0:continue
        a,b=sorted([-cl[0],-cl[1]])
        if a==b or a not in bird_of or b not in bird_of:continue
        if bird_of[a]==bird_of[b]:return False
        negatives.add((a,b))
    parent={x:x for x in bird_of}
    def root(x):
        while parent[x]!=x:
            parent[x]=parent[parent[x]]
            x=parent[x]
        return x
    for a,b in negatives:
        x,y=root(a),root(b)
        if x!=y:parent[x]=y
    groups=defaultdict(set)
    for v in bird_of:groups[root(v)].add(v)
    if len(groups)!=payload.get("holes") or len(birds)!=payload.get("birds"):
        return False
    for members in groups.values():
        if len({bird_of[v] for v in members})!=len(members):return False
        for a in members:
            for b in members:
                if a<b and (a,b) not in negatives:return False
    indices=payload.get("hall_birds")
    if not isinstance(indices,list) or not indices:return False
    if any(not isinstance(i,int) or i<0 or i>=len(birds) for i in indices):
        return False
    if len(indices)!=len(set(indices)):return False
    domain={root(v) for i in indices for v in birds[i]}
    return len(domain)<len(indices)


def _unified_linear(payload, clauses):
    """Independent GF(2) + original-unit + binary-SCC proof replay."""
    rows=payload.get("rows")
    if not isinstance(rows,list) or len(rows)<2:return False
    patterns=defaultdict(set)
    graph_edges=set()
    for cl in clauses:
        if 2<=len(cl)<=10:
            support=tuple(sorted(map(abs,cl)))
            if len(support)==len(set(support)):
                mask=sum(1<<i for i,v in enumerate(support) if -v in cl)
                patterns[support].add(mask)
        if len(cl)==1:
            graph_edges.add((-cl[0],cl[0]))
        elif len(cl)==2:
            a,b=cl
            graph_edges.add((-a,b))
            graph_edges.add((-b,a))
    total_vars=set()
    total_rhs=0
    for row in rows:
        if not isinstance(row,dict):return False
        kind=row.get("kind")
        if kind=="xor":
            support=row.get("vars")
            rhs=row.get("rhs")
            if (not isinstance(support,list) or not 2<=len(support)<=10 or
                not all(isinstance(v,int) and v>0 for v in support) or
                support!=sorted(set(support)) or rhs not in (0,1)):
                return False
            forbidden=patterns.get(tuple(support),set())
            allowed=[m for m in range(1<<len(support)) if m not in forbidden]
            if not allowed or any(m.bit_count()%2!=rhs for m in allowed):return False
            variables=set(support)
        elif kind=="unit":
            index=row.get("clause")
            if not isinstance(index,int) or not 0<=index<len(clauses):
                return False
            cl=clauses[index]
            if len(cl)!=1:return False
            variables={abs(cl[0])}
            rhs=int(cl[0]>0)
        elif kind=="equiv":
            a,b=row.get("a"),row.get("b")
            if (not isinstance(a,int) or not isinstance(b,int) or
                a==0 or b==0 or abs(a)==abs(b)):return False
            def path_ok(path,start,end):
                return (isinstance(path,list) and len(path)>=2 and
                    path[0]==start and path[-1]==end and
                    all((path[i],path[i+1]) in graph_edges
                        for i in range(len(path)-1)))
            if (not path_ok(row.get("ab"),a,b) or
                not path_ok(row.get("ba"),b,a)):return False
            variables={abs(a),abs(b)}
            rhs=int((a<0)^(b<0))
        else:return False
        total_vars=total_vars.symmetric_difference(variables)
        total_rhs^=rhs
    return not total_vars and total_rhs==1

def verify_certificate(payload,clauses):
    if not payload or payload.get("status")!="UNSAT":return True
    path=payload.get("path","")
    if path=="v153_unit_propagation":return _unit(payload,clauses)
    if path=="v153_binary_scc":return _binary(payload,clauses)
    if path=="v153_exhaustive_support":return _exhaustive(payload,clauses)
    if path=="v153_affine_unsat":return _affine(payload,clauses)
    if path=="pigeonhole_exact":return _php(payload,clauses)
    if path=="v153_hall_unsat":return _hall(payload,clauses)
    if path=="v153_unified_linear_unsat":return _unified_linear(payload,clauses)
    return False # Unknown DRNAS UNSAT proof mechanism.
