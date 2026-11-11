"""Bounded, proof-carrying multi-step XOR relations from the CURRENT CNF.

Memory may select this algorithm; it never supplies equations or conclusions.
Each provenance set denotes XOR (not union) of original certified rows.
"""
from collections import defaultdict, deque
import time

from probe import parse_dimacs, detect_xor


def binary_cycle(equations, *, max_source_rows=96, deadline=None):
    """Linear graph reasoning for pure binary XOR, without transitive CNF spam."""
    adjacency=defaultdict(list)
    for i,eq in enumerate(equations[:max_source_rows]):
        a,b=eq['variables']
        adjacency[a].append((b,eq['rhs'],i))
        adjacency[b].append((a,eq['rhs'],i))
    values={};paths={};edges=0
    stats=dict(source_rows=min(len(equations),max_source_rows),derived_rows=0,
               pairs_examined=0,max_depth=0,stop_reason='binary_components',patterns={})
    for root in sorted(adjacency):
        if root in values:continue
        values[root]=0;paths[root]=frozenset();queue=deque([root])
        while queue:
            if deadline is not None and time.perf_counter()>=deadline:
                stats['stop_reason']='time_budget';return [],stats
            a=queue.popleft()
            for b,rhs,i in adjacency[a]:
                edges+=1
                desired=values[a]^rhs
                if b not in values:
                    values[b]=desired;paths[b]=paths[a]^frozenset((i,));queue.append(b)
                elif values[b]!=desired:
                    proof=paths[a]^paths[b]^frozenset((i,))
                    depth=max(1,len(proof)-1)
                    con=dict(kind='conflict',variables=[],rhs=1,
                             source_equations=sorted(proof),derivation_depth=depth)
                    key=f"binary_cycle:parents{len(proof)}:out0:rhs1"
                    stats.update(derived_rows=1,max_depth=depth,
                                 stop_reason='source_conflict',patterns={key:'conflict'},
                                 edges_examined=edges)
                    return [con],stats
    stats['edges_examined']=edges
    return [],stats


def close_relations(equations, *, max_source_rows=96, max_derived=64,
                    max_pairs=4096, max_depth=4, deadline=None):
    if min(max_source_rows,max_derived,max_pairs,max_depth)<0:
        raise ValueError("Negative relational budget")
    rows=[]
    known={}
    incidence=defaultdict(set)
    agenda=deque()
    processed=set()
    conclusions=[]
    patterns={}
    pair_count=0
    stopped="complete"

    def add(vs,rhs,proof,depth):
        key=(vs,rhs)
        if key in known:
            return False
        i=len(rows)
        known[key]=i
        rows.append((vs,rhs,proof,depth))
        for v in vs:
            incidence[v].add(i)
        if depth:
            agenda.appendleft(i)  # finish promising chains before broad scanning
        else:
            agenda.append(i)
        return True

    for i,eq in enumerate(equations[:max_source_rows]):
        vs=frozenset(eq['variables'])
        rhs=eq['rhs']
        if len(vs)!=len(eq['variables']) or rhs not in (0,1):
            raise ValueError("Noncanonical source equation")
        if any(v<=0 for v in vs):
            raise ValueError("Invalid source variable")
        add(vs,rhs,frozenset((i,)),0)
    initial=len(rows)
    while agenda:
        if deadline is not None and time.perf_counter()>=deadline:
            stopped="time_budget"; break
        i=agenda.popleft()
        av,ar,ap,ad=rows[i]
        neighbors=set()
        for v in av:
            neighbors.update(incidence[v])
        candidates=sorted((j for j in neighbors if j!=i),
                          key=lambda j:(len(av^rows[j][0]),j))
        for j in candidates:
            pair=(min(i,j),max(i,j))
            if pair in processed:
                continue
            if pair_count>=max_pairs:
                stopped="pair_budget"; break
            if deadline is not None and time.perf_counter()>=deadline:
                stopped="time_budget"; break
            processed.add(pair);pair_count+=1
            bv,br,bp,bd=rows[j]
            vs,rhs=av^bv,ar^br
            depth=1+max(ad,bd)
            if depth>max_depth or len(vs)>2 or (not vs and not rhs):
                continue
            if (vs,rhs) in known:
                continue
            if len(rows)-initial>=max_derived:
                stopped="row_budget"; break
            proof=ap^bp
            if not proof:
                raise AssertionError("Nontrivial consequence without provenance")
            add(vs,rhs,proof,depth)
            kind="conflict" if not vs else "unit" if len(vs)==1 else "binary_xor"
            con=dict(kind=kind,variables=sorted(vs),rhs=rhs,
                     source_equations=sorted(proof),derivation_depth=depth)
            conclusions.append(con)
            widths=','.join(map(str,sorted(len(equations[k]['variables']) for k in proof)))
            # A renaming-invariant advisory template, never a proof on another CNF.
            key=f"closure:depth{depth}:parents{len(proof)}:widths{widths}:out{len(vs)}:rhs{rhs}"
            patterns[key]=kind
            if kind=="conflict":
                stopped="source_conflict";break
        if stopped!="complete":
            break
    return conclusions,dict(source_rows=initial,derived_rows=len(rows)-initial,
        pairs_examined=pair_count,max_depth=max((r[3] for r in rows),default=0),
        stop_reason=stopped,patterns=patterns)


def probe_relations(text, *, max_clauses=10000, max_rows=96, max_width=3,
                    budget_s=.03):
    start=time.perf_counter()
    clauses=parse_dimacs(text)
    if len(clauses)>max_clauses:
        return dict(status="abstain",reason="clause_budget",clauses=len(clauses),
                    elapsed_s=time.perf_counter()-start)
    equations=[dict(variables=list(v),rhs=rhs) for v,rhs in detect_xor(
        clauses,max_width=max_width)]
    report=dict(status="diagnostic_only",clauses=len(clauses),
                xor_equations=equations)
    if equations and all(len(eq['variables'])==2 for eq in equations):
        consequences,stats=binary_cycle(equations,max_source_rows=max_rows,
                                         deadline=start+budget_s)
    else:
        consequences,stats=close_relations(report['xor_equations'],
            max_source_rows=max_rows,deadline=start+budget_s)
    # Transitive binaries are already reproduced by BCP over source/derived
    # binaries. Keep them internally as relations, but inject only fresh
    # width-reducing first-step binaries, units, or a proved contradiction.
    useful=[c for c in consequences if c['kind']!='binary_xor' or (
        c['derivation_depth']==1 and any(len(equations[i]['variables'])>2
                                       for i in c['source_equations']))]
    stats['redundant_binary_omitted']=len(consequences)-len(useful)
    consequences=useful
    report['consequences']=sorted(consequences,key=lambda c:(
        len(c['variables']),c['derivation_depth'],c['variables'],c['rhs']))
    report['relational_closure']=stats
    report['elapsed_s']=time.perf_counter()-start
    return report
