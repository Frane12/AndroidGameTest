"""DRNAS LTM4: exact source-XOR relational graph and read-only trail shadow.

No advice is injected into native CDCL. Every row must be independently
certified from COMPLETE original CNF XOR encoding. This is a testable shadow
evaluator for CDCL assignment snapshots; a native-trail callback is a separate
integration step, not claimed here.
"""
from collections import Counter
from itertools import combinations
import hashlib
import json


def source_rows(clauses, *, max_width=3, max_groups=100000):
    """Exact detection of width-2/3 source XORs, not guessed implications."""
    supports={}
    for clause in clauses:
        variables=tuple(sorted(set(abs(int(l)) for l in clause)))
        if len(variables) not in (2,3) or len(variables)!=len(clause):
            continue
        if len(supports)>=max_groups and variables not in supports:
            continue
        byvar={abs(l):l for l in clause}
        mask=sum(1<<i for i,v in enumerate(variables) if byvar[v]<0)
        supports.setdefault(variables,set()).add(mask)
    rows=[]
    for variables,seen in sorted(supports.items()):
        for rhs in (0,1):
            required={m for m in range(1<<len(variables))
                      if m.bit_count()%2 != rhs}
            if required<=seen:
                rows.append(dict(variables=list(variables),rhs=rhs,
                                 complete_source_certified=True))
    return rows


def graph(clauses, *, max_pairs=200000):
    """Structural motifs are renaming-invariant; labels are never proofs."""
    rows=source_rows(clauses)
    adjacency=[]
    features=Counter()
    for row in rows:
        features["row_width_"+str(len(row["variables"]))]+=1
    for i,a in enumerate(rows):
        for j in range(i+1,len(rows)):
            if len(adjacency)>=max_pairs:
                break
            b=rows[j]
            shared=len(set(a["variables"])&set(b["variables"]))
            if not shared:
                continue
            width=len(set(a["variables"])^set(b["variables"]))
            rhs=a["rhs"]^b["rhs"]
            # Parity transforms under variable *negation*, but not renaming.
            # Signed polarity is part of the key and must be retained.
            motif="overlap:%d:%d:shared%d:out%d:rhs%d"%(
                len(a["variables"]),len(b["variables"]),shared,width,rhs)
            features[motif]+=1
            adjacency.append(dict(i=i,j=j,shared=shared,
                                  reduced_width=width,reduced_rhs=rhs,
                                  motif=motif))
    signature=hashlib.sha256(json.dumps(
        sorted(features.items()),separators=(",",":")).encode()).hexdigest()[:24]
    return dict(rows=rows,edges=adjacency,features=dict(features),
                signature=signature,truncated_pairs=len(adjacency)>=max_pairs)


def shadow_snapshot(rows, values, *, bcp_known=(), decision_level=0):
    """Evaluate XOR rows on an externally provided CDCL assignment snapshot.

    values: mapping var -> {True,False}; omitted means undefined.
    bcp_known: literals already inferred by the ordinary BCP at same
    measurement boundary. Without actual BCP closure from native CDCL,
    'candidate' MUST NOT be reported as a confirmed novel implication.
    """
    values={int(k):bool(v) for k,v in values.items() if v is not None}
    bcp={int(x) for x in bcp_known}
    observations=Counter()
    candidates=[]
    for row in rows:
        unassigned=[v for v in row["variables"] if v not in values]
        parity=row["rhs"]^sum(values[v] for v in row["variables"]
                             if v in values)%2
        if len(unassigned)==0:
            if parity:
                observations["candidate_conflict"]+=1
                candidates.append(dict(type="conflict",row=row))
        elif len(unassigned)==1:
            v=unassigned[0]
            lit=v if parity else -v
            if lit in bcp:
                observations["already_known_to_BCP"]+=1
            else:
                observations["candidate_unconfirmed_BCP"]+=1
            candidates.append(dict(type="unit_candidate",literal=lit,
                                   already_known=(lit in bcp),row=row))
        else:
            observations["inactive_multiple_unassigned"]+=1
    return dict(decision_level=decision_level,measurements=dict(observations),
                candidates=candidates,shadow_only=True,
                native_bcp_closure_confirmed=False)


def sample_snapshots(clauses, *, max_snapshots=24):
    """Synthetic deterministic stress snapshots for unit tests/CI ONLY.

    NOT a native CDCL trail, not evidence of real missed BCP propagations.
    """
    rows=source_rows(clauses)
    vars_=sorted({v for row in rows for v in row["variables"]})
    snapshots=[]
    for i in range(min(max_snapshots,len(vars_))):
        assigned={v:bool((i+j)&1) for j,v in enumerate(vars_[:i])}
        snapshots.append(shadow_snapshot(rows,assigned,decision_level=i))
    return snapshots
