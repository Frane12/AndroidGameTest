#!/usr/bin/env python3
"""Independent original-CNF checker for DRNAS-source-clique-capacity-v1.

Checks a sound UNSAT certificate without invoking the detector or any SAT
solver. For each disjoint positive input clause, at least one variable is true.
All selected variables are partitioned into fewer resources, each a complete
input-supported pairwise mutex clique. Therefore UNSAT by pigeonhole.
This is not a DRAT/LRAT/PBP competition proof.
"""
import hashlib
import json
import sys
from pathlib import Path

def check(cnf, cert):
    raw=Path(cnf).read_bytes()
    certificate=json.loads(Path(cert).read_text())
    if certificate.get("format")!="DRNAS-source-clique-capacity-v1":
        raise ValueError("bad_certificate_format")
    if hashlib.sha256(raw).hexdigest()!=certificate.get("source_sha256"):
        raise ValueError("source_sha_mismatch")
    n=claimed=None
    source_positive=set()
    source_mutex=set()
    complete=0
    clause=[]
    for line in raw.splitlines():
        tok=line.split()
        if not tok or tok[0]==b'c':continue
        if tok[0]==b'p':
            if n is not None or len(tok)!=4 or tok[1]!=b'cnf':
                raise ValueError("bad_source_header")
            n=int(tok[2]);claimed=int(tok[3])
            if n>200000 or claimed>1000000:raise ValueError("size_gate")
            continue
        if n is None:raise ValueError("missing_source_header")
        for token in tok:
            x=int(token)
            if x:
                if abs(x)>n:raise ValueError("literal_out_of_range")
                clause.append(x)
            else:
                complete+=1
                if clause and all(x>0 for x in clause):
                    source_positive.add(tuple(sorted(clause)))
                if len(clause)==2 and all(x<0 for x in clause):
                    a,b=sorted((-clause[0],-clause[1]))
                    if a!=b:source_mutex.add((a,b))
                clause=[]
    if n is None or clause or complete!=claimed:raise ValueError("invalid_source_dimacs")
    if certificate.get("source_variables")!=n or certificate.get("source_clauses")!=claimed:
        raise ValueError("source_dimensions_mismatch")
    groups=certificate["selected_groups"]
    resources=certificate["capacity_cliques"]
    if not isinstance(groups,list) or not isinstance(resources,list):
        raise ValueError("invalid_group_lists")
    if not 3<=len(groups)<=256 or not 1<=len(resources)<len(groups):
        raise ValueError("no_capacity_contradiction")
    if certificate.get("demand")!=len(groups) or certificate.get("capacity")!=len(resources):
        raise ValueError("invalid_demand_capacity")
    selected=set()
    for group in groups:
        if not isinstance(group,list) or not group:
            raise ValueError("empty_selected_group")
        if len(group)!=len(set(group)) or any(type(v) is not int or v<1 or v>n for v in group):
            raise ValueError("invalid_selected_variables")
        if tuple(sorted(group)) not in source_positive:
            raise ValueError("missing_source_positive_demand_clause")
        if selected.intersection(group):raise ValueError("overlapping_positive_groups")
        selected.update(group)
    resource_union=set()
    for group in resources:
        if not isinstance(group,list) or len(group)<2:
            raise ValueError("bad_resource")
        if len(group)!=len(set(group)) or any(type(v) is not int or v<1 or v>n for v in group):
            raise ValueError("bad_resource_literal")
        if resource_union.intersection(group):raise ValueError("overlapping_resources")
        resource_union.update(group)
        for i,a in enumerate(group):
            for b in group[i+1:]:
                if (min(a,b),max(a,b)) not in source_mutex:
                    raise ValueError("resource_missing_original_mutex_clause")
    if resource_union!=selected:
        raise ValueError("resource_partition_does_not_match_demand_variables")
    return dict(status="UNSAT_SOURCE_CLIQUE_VERIFIED",
                sha256=hashlib.sha256(raw).hexdigest(),
                variables=n,clauses=claimed,required_groups=len(groups),
                capacity_resources=len(resources),
                deficit=len(groups)-len(resources),
                original_pairs_checked=sum(len(g)*(len(g)-1)//2 for g in resources),
                selected_vars=len(selected))

def main():
    if len(sys.argv)!=3:
        raise SystemExit("usage: check_php_partition.py ORIGINAL.cnf CAPACITY_CERTIFICATE.json")
    try:
        result=check(sys.argv[1],sys.argv[2])
    except (ValueError,TypeError,KeyError,OSError) as exc:
        print("INVALID_SOURCE_CLIQUE_CERTIFICATE "+str(exc),file=sys.stderr)
        return 1
    print(json.dumps(result,sort_keys=True))
    return 0

if __name__=="__main__":
    sys.exit(main())
