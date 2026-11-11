#!/usr/bin/env python3
"""Independent PHP subformula certificate checker on ORIGINAL CNF.
No LRAT claim. Conservative: a complete exact PHP subformula suffices
for UNSAT, regardless of unrelated additional original clauses.
"""
from collections import defaultdict
from drnas_atlas26_php import prove_php

def prove_php_subset(clauses):
    neg=[c for c in clauses if len(c)==2 and all(v<0 for v in c)]
    groups_by_width=defaultdict(list)
    for c in clauses:
        if 2<=len(c)<=64 and all(v>0 for v in c) and len(set(c))==len(c):
            groups_by_width[len(c)].append(c)
    for width, groups in groups_by_width.items():
        if not width<len(groups)<=512:continue
        owners=defaultdict(list)
        for i,g in enumerate(groups):
            for v in g:owners[v].append(i)
        invalid={i for ids in owners.values() if len(ids)>1 for i in ids}
        parent=list(range(len(groups)))
        def find(a):
            while parent[a]!=a:
                parent[a]=parent[parent[a]]
                a=parent[a]
            return a
        for c in neg:
            x,y=-c[0],-c[1]
            ai=owners.get(x,[]);bi=owners.get(y,[])
            if len(ai)!=1 or len(bi)!=1:continue
            i,j=ai[0],bi[0]
            if i in invalid or j in invalid or i==j:continue
            parent[find(i)]=find(j)
        components=defaultdict(list)
        for i,g in enumerate(groups):
            if i not in invalid:components[find(i)].append(g)
        for subgroups in components.values():
            if not width<len(subgroups)<=128:continue
            certificate=prove_php(subgroups+neg)
            if certificate is not None:
                return dict(certificate,checker="original_clause_subset",
                            selected_positive_groups=len(subgroups))
    return None
