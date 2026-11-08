#!/usr/bin/env python3
"""DRNAS MRE6g: certified implication-SCC / signed equivalence quotient.

Original binary clause (a OR b) licenses implications (-a -> b),
(-b -> a). Every SCC is a mathematically valid two-way equivalence,
INCLUDING signed complements (x == not y). Certificates contain actual
paths within the original and separately proof-replayed derived clauses.

MRE1 GF(2) derived CNF may extend the graph ONLY after independent
MRE1.verify_proofs on the UNMODIFIED source CNF. Never learn an equality
from a heuristic XOR pattern or a one-way reachability edge.

Signed representative mapping e.g. {2:-1} means x2=NOT x1. The GF2
right-hand side flips for every negated substitution; duplicate variables
cancel modulo two. SAT model lifting checks every original CNF clause.
"""
from __future__ import annotations
import collections,hashlib,itertools,json,pathlib,sys,time
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parent))
import mre1_cross_representation as mre1

PROTO="DRNAS-MRE6G-SIGNED-SCC-REPLAY-CERT-v1"
MAX_MERGES=64
MAX_BFS_VISITS=12000
MAX_PATH_LEN=256

class Abstain(Exception):
    pass

def need(ok,msg):
    if not ok: raise RuntimeError("MRE6G_PROOF_FAIL_CLOSED "+str(msg))

def certified_binary(original,source_rows=(),proofs=()):
    """Return proof-checked binary clauses: source clauses plus MRE1 records."""
    if proofs or source_rows:
        need(mre1.verify_proofs(original,source_rows,proofs),
             "independent source/GF2 proof replay failed")
    clauses=set()
    for c in original:
        if len(c)==2:
            cl=mre1.normalize(c)
            if cl is not None and len(cl)==2:clauses.add(cl)
    original_count=len(clauses)
    for p in proofs:
        if len(p["clause"])!=2:continue
        cl=mre1.normalize(p["clause"])
        if cl is not None and len(cl)==2:clauses.add(cl)
    return clauses,original_count

def graph_for(binary):
    g=collections.defaultdict(list)
    rg=collections.defaultdict(list)
    vertices=set()
    for c in sorted(binary):
        a,b=c
        if a == -b:continue
        # Normalize original clause; two complementary implications are
        # one and the same propositional axiom.
        for u,v in ((-a,b),(-b,a)):
            g[u].append(v);rg[v].append(u)
            vertices.add(u);vertices.add(v)
    return g,rg,vertices

def components(g,rg,vertices,deadline):
    seen=set()
    order=[]
    for v in sorted(vertices):
        if v in seen:continue
        seen.add(v)
        stack=[(v,iter(g.get(v,())))]
        while stack:
            if time.perf_counter()>deadline:raise Abstain("SCC_time_budget")
            node,it=stack[-1]
            w=next(it,None)
            if w is None:
                order.append(node)
                stack.pop()
            elif w not in seen:
                seen.add(w);stack.append((w,iter(g.get(w,()))))
    comp={}
    number=0
    for v in reversed(order):
        if v in comp:continue
        stack=[v];comp[v]=number
        while stack:
            if time.perf_counter()>deadline:raise Abstain("SCC_time_budget")
            u=stack.pop()
            for w in rg.get(u,()):
                if w not in comp:
                    comp[w]=number;stack.append(w)
        number+=1
    return comp,number

def path(adj,u,v,comp,deadline):
    if u==v:return [u]
    q=collections.deque([u])
    prev={u:None}
    while q:
        if len(prev)>MAX_BFS_VISITS or time.perf_counter()>deadline:
            raise Abstain("proof_path_cost_guard")
        w=q.popleft()
        for x in adj.get(w,()):
            if comp[x]!=comp[u] or x in prev:continue
            prev[x]=w
            if x==v:
                rev=[v]
                while rev[-1]!=u:rev.append(prev[rev[-1]])
                rev.reverse()
                if len(rev)>MAX_PATH_LEN:
                    raise Abstain("proof_path_too_long")
                return rev
            q.append(x)
    raise RuntimeError("MRE6G SCC path nonexistent")

def discover(original,source_rows=(),proofs=(),*,budget_s=.38,max_merges=MAX_MERGES):
    start=time.perf_counter()
    deadline=start+budget_s
    # Independent verification of GF2 and resolution steps, if supplied.
    binary,original_binary_count=certified_binary(original,source_rows,proofs)
    if time.perf_counter()>deadline:raise Abstain("certificate_replay_budget")
    g,rg,vertices=graph_for(binary)
    if time.perf_counter()>deadline:raise Abstain("graph_build_budget")
    if not vertices:
        return {},dict(status="no_binary_graph",certified_pairs=0,
          binary_original=original_binary_count,binary_total=len(binary),
          edges=0,elapsed_s=time.perf_counter()-start)
    comp,ncomps=components(g,rg,vertices,deadline)
    # SCC(x)==SCC(-x) means binary subformula already yields UNSAT.
    for v in vertices:
        if -v in comp and comp[v]==comp[-v]:
            raise Abstain("binary_SCC_contradiction_requires_independent_UNSAT_proof")
    groups=collections.defaultdict(set)
    for v in vertices:
        if v<=0 or -v not in comp:continue
        key=tuple(sorted((comp[v],comp[-v])))
        groups[key].add(v)
    occur=collections.Counter(abs(l) for c in original for l in c)
    mapping={}
    certs=[]
    for key,members in sorted(groups.items(),key=lambda x:min(x[1])):
        if len(members)<2:continue
        rep=min(members,key=lambda v:(-occur[v],v))
        for var in sorted(members):
            if var==rep:continue
            if len(mapping)>=max_merges:
                break
            signed_rep=rep if comp[var]==comp[rep] else -rep
            need(comp[var]==comp[signed_rep],"SCC sign mismatch")
            forward=path(g,var,signed_rep,comp,deadline)
            backward=path(g,signed_rep,var,comp,deadline)
            # Every path edge corresponds to an independently verified
            # original/derived (not u OR v) binary clause.
            for chain in (forward,backward):
                for u,v in zip(chain,chain[1:]):
                    need(mre1.normalize((-u,v)) in binary,
                         "SCC certificate edge is not a certified CNF implication")
            mapping[var]=signed_rep
            certs.append(dict(variable=var,representative=signed_rep,
                forward_path_length=len(forward)-1,
                backward_path_length=len(backward)-1,
                proof_digest=hashlib.sha256(json.dumps(
                  [forward,backward],sort_keys=True).encode()).hexdigest()))
        if len(mapping)>=max_merges:break
    stats=dict(status="certified_SCC_quotient" if mapping else
                "no_nontrivial_SCC_equivalence",
        certified_pairs=len(mapping),
        signed_complements=sum(x<0 for x in mapping.values()),
        binary_original=original_binary_count,binary_total=len(binary),
        derived_binary=len(binary)-original_binary_count,
        edges=sum(len(x) for x in g.values()),scc_count=ncomps,
        classes=sum(len(x)>1 for x in groups.values()),
        max_merges=max_merges,
        proofs=certs[:8],
        proof_count=len(certs),
        elapsed_s=round(time.perf_counter()-start,6))
    return mapping,stats

def quotient(original,rows,mapping):
    if not mapping:
        return list(original),list(rows),dict(
          replaced_literals=0,removed_clauses=0,output_clauses=len(original),
          transformed_xors=len(rows),generated_units=0)
    need(all(v>0 and v!=abs(r) for v,r in mapping.items()),
         "invalid signed representative mapping")
    cnf=[]
    seen=set()
    removed=0;replaced=0
    def insert(c):
        nonlocal removed
        clause=tuple(dict.fromkeys(c))
        literals=set(clause)
        if any(-v in literals for v in literals):
            removed+=1;return
        canonical=frozenset(literals)
        if canonical in seen:removed+=1;return
        seen.add(canonical);cnf.append(clause)
    for c in original:
        values=[]
        for lit in c:
            r=mapping.get(abs(lit),abs(lit))
            v=r if lit>0 else -r
            replaced+=int(lit!=v)
            values.append(v)
        insert(values)
    xor=[]
    xor_set=set()
    units=0
    for vs,rhs in rows:
        need(rhs in (0,1),"GF2 RHS is not binary")
        active=set()
        bit=rhs
        for v in vs:
            signed=mapping.get(v,v)
            if signed<0:bit^=1
            root=abs(signed)
            if root in active:active.remove(root)
            else:active.add(root)
        if not active:
            if bit:insert(())
        elif len(active)==1:
            v=next(iter(active))
            insert((v if bit else -v,))
            units+=1
        else:
            item=(tuple(sorted(active)),bit)
            if item not in xor_set:
                xor.append(item);xor_set.add(item)
    need(all(abs(l) not in mapping for c in cnf for l in c) and
         all(v not in mapping for vs,rhs in xor for v in vs),
         "eliminated variable remains in signed quotient")
    return cnf,xor,dict(replaced_literals=replaced,
        removed_clauses=removed,output_clauses=len(cnf),
        transformed_xors=len(xor),generated_units=units)

def reconstruct(model,mapping):
    m=dict(model)
    for v,signed in mapping.items():
        r=abs(signed)
        need(r in m and isinstance(m[r],bool),
             "signed representative absent in SAT witness")
        m[v]=m[r] if signed>0 else (not m[r])
    return m

def selftest():
    # Indirect positive equality via x1->x2->x3 and x3->x4->x1.
    pos=[(-1,2),(-2,3),(-3,4),(-4,1)]
    # Indirect negative: x1->not x5 and not x5->x1 via
    # implication - clauses. Two-clause direct signed equivalence:
    neg=[(-1,-5),(1,5)]
    cases=[
        (pos,1,3,True),
        (neg,1,5,False),
        (pos+neg,1,5,False)
    ]
    for clauses,a,b,same in cases:
        mp,meta=discover(clauses,budget_s=1)
        need(b in mp and (mp[b]>0)==same,
             "signed/indirect SCC equivalence discovery failed")
        cnf,xor,_=quotient(clauses,[((a,b),0)],mp)
        vals=sorted({abs(l) for c in clauses for l in c})
        for truth in itertools.product((False,True),repeat=len(vals)):
            original=dict(zip(vals,truth))
            allorig=all(any(original[abs(l)]==(l>0) for l in c) for c in clauses)
            allorig=allorig and ((original[a]^original[b])==0)
            # Any satisfying original assignment must obey certified map.
            if allorig:
                need(all(original[v]==(original[abs(s)] if s>0 else
                          not original[abs(s)]) for v,s in mp.items()),
                     "model does not satisfy certified signed relation")
            new={k:v for k,v in original.items() if k not in mp}
            lifted=reconstruct(new,mp)
            satisfied=all(any(lifted[abs(l)]==(l>0) for l in c) for c in cnf)
            satisfied=satisfied and all((sum(lifted[v] for v in vs)&1)==rhs
                                      for vs,rhs in xor)
            # Projection of source CNF + GF2 to representative assignment.
            projected=all(any(lifted[abs(l)]==(l>0) for l in c) for c in clauses)
            projected=projected and ((lifted[a]^lifted[b])==0)
            need(satisfied==projected,"signed quotient GF2 model-equivalence failure")
    lonely,meta=discover([(1,2)],budget_s=1)
    need(lonely=={},"one-way implication falsely became an equality")
    print("MRE6G_SCC_SIGNED_EXHAUSTIVE_SELFTEST_PASS",PROTO,flush=True)

if __name__=="__main__":
    selftest()
