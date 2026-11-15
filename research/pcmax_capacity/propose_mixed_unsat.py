#!/usr/bin/env python3
"""Bounded proof producers for source-only 2-SAT, XOR and tiny general CNFs.

Independent checker: check_mixed_unsat.py.
All proposals are optional, single CPU, and return UNKNOWN on unsupported work.
"""
import collections
import hashlib
import itertools
import time
from check_capacity import parse_cnf

FORMAT="drnas-mixed-unsat1"

def wrap(raw,method,**fields):
    return {"format":FORMAT,"source_sha256":hashlib.sha256(raw).hexdigest(),
            "method":method,**fields}

def binary_proof(raw,nvars,clauses,deadline):
    if nvars>64:return None
    graph=collections.defaultdict(list)
    for c in clauses:
        if len(c)==1:
            a=next(iter(c))
            graph[-a].append(a)
        elif len(c)==2:
            a,b=tuple(c)
            graph[-a].append(b)
            graph[-b].append(a)
    def bfs(start,goal):
        queue=collections.deque([start])
        parent={start:None}
        while queue:
            if time.perf_counter()>deadline:return None
            u=queue.popleft()
            if u==goal:
                path=[]
                while u is not None:
                    path.append(u)
                    u=parent[u]
                return path[::-1]
            for v in graph[u]:
                if v not in parent:
                    parent[v]=u
                    queue.append(v)
        return None
    for variable in range(1,nvars+1):
        if time.perf_counter()>deadline:return None
        forward=bfs(variable,-variable)
        if forward is None:continue
        backward=bfs(-variable,variable)
        if backward is not None:
            return wrap(raw,"binary_cycle",pivot=variable,
                        pos_to_neg=forward,neg_to_pos=backward)
    return None

def xor_proof(raw,nvars,clauses,deadline):
    # A complete half-cube of input clauses on identical variable support
    # is exactly one XOR equation; opposite half-cubes contradict.
    by=collections.defaultdict(lambda: [set(),set()])
    for clause in clauses:
        if time.perf_counter()>deadline:return None
        if not (3<=len(clause)<=8):continue
        support=tuple(sorted(abs(l) for l in clause))
        if len(set(support))!=len(support):continue
        negatives=frozenset(abs(l) for l in clause if l<0)
        by[support][len(negatives)%2].add(negatives)
    blocks=[]
    rows=[]
    for support,halves in by.items():
        for forbid_parity,patterns in enumerate(halves):
            if len(patterns)==(1<<(len(support)-1)):
                blocks.append({"vars":list(support),"forbidden_parity":forbid_parity})
                rows.append((sum(1<<(v-1) for v in support),1-forbid_parity))
                if len(blocks)>=32:break
        if len(blocks)>=32:break
    basis={}
    for i,(mask0,rhs0) in enumerate(rows):
        mask,rhs,trace=mask0,rhs0,1<<i
        while mask:
            if time.perf_counter()>deadline:return None
            pivot=(mask&-mask).bit_length()-1
            if pivot not in basis:
                basis[pivot]=(mask,rhs,trace)
                break
            base_m,base_rhs,base_trace=basis[pivot]
            mask^=base_m
            rhs^=base_rhs
            trace^=base_trace
        if mask==0 and rhs==1:
            selected=[j for j in range(len(rows)) if (trace>>j)&1]
            return wrap(raw,"xor_gf2",blocks=blocks,combine=selected)
    return None

def dpll_proof(raw,nvars,clauses,deadline):
    if nvars>8 or len(clauses)>512:return None
    items=sorted(clauses,key=lambda c:(len(c),sorted(c)))
    ticks=[0]
    def work(assignment):
        ticks[0]+=1
        if ticks[0]>350 or time.perf_counter()>deadline:raise TimeoutError()
        unresolved=[]
        for c in items:
            true_literal=False
            left=[]
            for lit in c:
                value=assignment.get(abs(lit))
                if value is None:
                    left.append(lit)
                elif value==(lit>0):
                    true_literal=True
                    break
            if true_literal:continue
            if not left:return {"clause":list(c)}
            unresolved.append(left)
        if not unresolved:return None # already satisfied, not UNSAT
        clause=min(unresolved,key=len)
        v=abs(clause[0])
        if v in assignment:raise AssertionError("bad DPLL choice")
        left=work({**assignment,v:False})
        if left is None:return None
        right=work({**assignment,v:True})
        if right is None:return None
        return {"split":v,"false":left,"true":right}
    try:
        tree=work({})
    except TimeoutError:
        return None
    if tree is None:return None
    return wrap(raw,"dpll_tree",tree=tree)

def propose(raw,budget_ms=50):
    started=time.perf_counter()
    deadline=started+max(0.001,budget_ms/1000.0)
    nvars,clauses=parse_cnf(raw)
    if nvars>256 or len(clauses)>250000:return None
    for fn in (binary_proof,xor_proof,dpll_proof):
        if time.perf_counter()>deadline:return None
        proof=fn(raw,nvars,clauses,deadline)
        if proof is not None:return proof
    return None
