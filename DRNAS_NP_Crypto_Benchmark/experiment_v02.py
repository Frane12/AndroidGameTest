#!/usr/bin/env python3
"""Deterministic connected parity graph with three exposed boundary variables."""
import random
from drnas_np_lab import normalize,xor_to_cnf
def sample_instance(vertices,seed,satisfiable=False):
    assert vertices%2==1 and vertices>=7
    rng=random.Random(seed)
    slots=[(v,i) for v in range(vertices) for i in range(2 if v<3 else 3)]
    assert len(slots)%2==0
    for _ in range(5000):
        rng.shuffle(slots)
        pairs=list(zip(slots[::2],slots[1::2]))
        if any(a[0]==b[0] for a,b in pairs):continue
        graph=[set() for _ in range(vertices)]
        for (a,_),(b,_) in pairs:
            graph[a].add(b);graph[b].add(a)
        seen={0};stack=[0]
        while stack:
            for v in graph[stack.pop()]:
                if v not in seen:seen.add(v);stack.append(v)
        if len(seen)==vertices:break
    else:raise RuntimeError("No connected graph generated")
    rows=[[] for _ in range(vertices)]
    for i in range(3):rows[i].append(i+1)
    for i,((a,_),(b,_)) in enumerate(pairs):
        variable=4+i;rows[a].append(variable);rows[b].append(variable)
    assert all(len(row)==3 and len(set(row))==3 for row in rows)
    rhs=[rng.randrange(2) for _ in range(vertices-1)]
    rhs.append(sum(rhs)&1)
    cnf=[cl for variables,bit in zip(rows,rhs) for cl in xor_to_cnf(tuple(variables),bit)]
    cnf.extend([(1,),(2,),(-3,) if satisfiable else (3,)])
    rng.shuffle(cnf)
    n=3+len(pairs)
    cnf=normalize(n,cnf)
    assert len(cnf)==vertices*4+3
    return n,cnf
