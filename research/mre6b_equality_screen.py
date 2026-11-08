#!/usr/bin/env python3
"""Read-only screen of directly certified positive CNF equivalences."""
import argparse, collections, json, time

def screen(path):
    start=time.perf_counter(); clauses=[]; n=0
    with open(path) as f:
        pending=[]
        for line in f:
            if line.startswith(('c','%')) or not line.strip(): continue
            if line.startswith('p'):
                n=int(line.split()[2]); continue
            for token in line.split():
                x=int(token)
                if x: pending.append(x)
                else: clauses.append(tuple(pending)); pending=[]
        if pending: raise ValueError('unterminated clause')
    binary={tuple(sorted(c)) for c in clauses if len(c)==2}
    pairs=set()
    for c in binary:
        a,b=c
        if a*b<0 and abs(a)!=abs(b) and tuple(sorted((-a,-b))) in binary:
            pairs.add(tuple(sorted((abs(a),abs(b)))))
    parent={}
    def find(x):
        parent.setdefault(x,x)
        while parent[x]!=x:
            parent[x]=parent[parent[x]]; x=parent[x]
        return x
    for a,b in sorted(pairs):
        ra,rb=find(a),find(b)
        if ra!=rb: parent[max(ra,rb)]=min(ra,rb)
    groups=collections.defaultdict(list)
    for x in parent: groups[find(x)].append(x)
    replacements={v:root for root,vs in groups.items() for v in vs if v!=root}
    before_lits=sum(map(len,clauses)); changed=taut=0; out=[]
    for c in clauses:
        mapped=[(1 if x>0 else -1)*replacements.get(abs(x),abs(x)) for x in c]
        changed+=sum(x!=y for x,y in zip(c,mapped))
        s=set(mapped)
        if any(-x in s for x in s): taut+=1; continue
        out.append(tuple(sorted(s)))
    unique=set(out)
    return dict(vars_declared=n, clauses=len(clauses), binary_clauses=len(binary), direct_unique_pairs=len(pairs), equality_classes=len(groups), class_sizes=sorted((len(x) for x in groups.values()),reverse=True)[:20], independent_merges=len(replacements), mapped_occurrences=changed, tautologies_after_mapping=taut, duplicate_clauses_after_mapping=len(out)-len(unique), projected_unique_clauses=len(unique), literals_before=before_lits, projected_literals=sum(map(len,unique)), elapsed_s=round(time.perf_counter()-start,6), note='Diagnostic estimate using original CNF direct positive equalities; no formula is changed and no derived XOR equalities are counted.')
if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('cnf'); a=p.parse_args(); print(json.dumps(screen(a.cnf),sort_keys=True))
