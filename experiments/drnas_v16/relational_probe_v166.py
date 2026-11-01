#!/usr/bin/env python3
"""DRNAS v16.6 relational probe. Feature-only: no solver feedback or selector training.
Counts: variable coupling, repeated pairs, signed motif recurrence, binary implication reach,
and deterministic unit propagation. All statistics are computed before solving.
"""
import argparse, collections, csv, json, math, pathlib, random

def parse(path):
    n=m=None; clauses=[]; pending=[]
    for raw in pathlib.Path(path).read_text().splitlines():
        s=raw.strip()
        if not s or s[0] in 'c%': continue
        if s.startswith('p '):
            a=s.split()
            if len(a)!=4 or a[1]!='cnf' or n is not None: raise ValueError("header")
            n,m=map(int,a[2:]); continue
        if n is None: raise ValueError("missing header")
        for token in s.split():
            v=int(token)
            if v==0:
                clauses.append(tuple(pending));pending=[]
            else:
                if abs(v)>n or not v: raise ValueError("bad literal")
                pending.append(v)
    if pending or n is None or len(clauses)!=m: raise ValueError("malformed CNF")
    return n,clauses

def features(path, sample_limit=128):
    n,clauses=parse(path)
    deg=[0]*(n+1); pos=[0]*(n+1); neg=[0]*(n+1)
    pairs=collections.Counter(); signed_pairs=collections.Counter()
    # Unary/binary implications: (not a => b) for clause (a OR b).
    graph=collections.defaultdict(set); units=[]
    for clause in clauses:
        distinct=set(clause)
        if len(distinct)!=len(clause) or any(-x in distinct for x in distinct):
            continue
        for v in clause:
            deg[abs(v)]+=1
            if v>0:pos[v]+=1
            else:neg[-v]+=1
        for i,a in enumerate(clause):
            for b in clause[i+1:]:
                pairs[tuple(sorted((abs(a),abs(b))))]+=1
                signed_pairs[tuple(sorted((a,b)))]+=1
        if len(clause)==1: units.append(clause[0])
        if len(clause)==2:
            a,b=clause;graph[-a].add(b);graph[-b].add(a)
    # Deterministic, linear-time unit propagation with occurrence lists.
    occurrences=collections.defaultdict(list)
    remaining=[len(c) for c in clauses]; satisfied=[False]*len(clauses)
    for j,c in enumerate(clauses):
        for lit in c: occurrences[lit].append(j)
    assignment={}; queue=collections.deque(units); forced=0; conflict=False
    while queue and not conflict:
        lit=queue.popleft(); v=abs(lit); val=lit>0
        if v in assignment:
            if assignment[v]!=val: conflict=True
            continue
        assignment[v]=val;forced+=1
        for j in occurrences[lit]: satisfied[j]=True
        for j in occurrences[-lit]:
            if satisfied[j]:continue
            remaining[j]-=1
            if remaining[j]==0:conflict=True;break
            if remaining[j]==1:
                for other in clauses[j]:
                    if abs(other) not in assignment:queue.append(other);break
    # Subsample uniformly and deterministically to bound work on large instances.
    vertices=sorted({x for c in clauses for x in c})
    rng=random.Random(166)
    sampled=sorted(rng.sample(vertices,min(sample_limit,len(vertices)))) if vertices else []
    reach=[]; cycles=0
    for v in sampled:
        for start in (v,-v):
            seen={start};frontier=[start]
            for _ in range(4):
                nxt=[]
                for a in frontier:
                    for b in graph[a]:
                        if b not in seen:seen.add(b);nxt.append(b)
                frontier=nxt
                if not frontier:break
            reach.append(len(seen)-1)
            cycles+=(-start in seen)
    d=[x for x in deg[1:] if x]; mean=sum(d)/len(d) if d else 0
    variance=sum((x-mean)**2 for x in d)/len(d) if d else 0
    total_pairs=sum(pairs.values())
    repeated=sum(c for c in pairs.values() if c>1)
    signed_repeated=sum(c for c in signed_pairs.values() if c>1)
    polarity=[abs(pos[i]-neg[i])/(pos[i]+neg[i]) for i in range(1,n+1) if pos[i]+neg[i]]
    return dict(file=pathlib.Path(path).name,nvars=n,nclauses=len(clauses),
        density=len(clauses)/max(n,1), degree_cv=math.sqrt(variance)/mean if mean else 0,
        pair_repeat_fraction=repeated/max(total_pairs,1),
        signed_pair_repeat_fraction=signed_repeated/max(sum(signed_pairs.values()),1),
        max_pair_multiplicity=max(pairs.values(),default=0),
        polarity_imbalance=sum(polarity)/max(1,len(polarity)),
        implication_reach4=sum(reach)/max(1,len(reach)),
        implication_opposite4_fraction=cycles/max(1,2*len(sampled)),
        unit_forced_fraction=forced/max(n,1),
        unit_conflict=int(conflict),binary_clause_fraction=sum(len(c)==2 for c in clauses)/max(1,len(clauses)))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--cnf-dir',required=True,type=pathlib.Path)
    ap.add_argument('--output',required=True,type=pathlib.Path)
    a=ap.parse_args(); paths=sorted(a.cnf_dir.rglob('*.cnf'))
    if not paths:raise SystemExit("no inputs")
    rows=[dict(group=p.parent.name,**features(p)) for p in paths]
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    print(json.dumps(rows,indent=2))

if __name__=='__main__':main()
