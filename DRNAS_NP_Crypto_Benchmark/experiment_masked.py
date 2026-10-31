#!/usr/bin/env python3
"""Camouflage exactly one clause of each detected XOR quartet by clause splitting."""
from collections import defaultdict
from drnas_np_lab import normalize
def mask(n,clauses):
    groups=defaultdict(list)
    for i,c in enumerate(clauses):
        if len(c)==3: groups[tuple(sorted(abs(x) for x in c))].append(i)
    masked_indices={indices[0] for indices in groups.values() if len(indices)==4}
    out=[];nxt=n
    for i,c in enumerate(clauses):
        if i in masked_indices:
            nxt+=1;out.extend([c+(nxt,),c+(-nxt,)])
        else:out.append(c)
    return nxt,normalize(nxt,out),len(masked_indices)
