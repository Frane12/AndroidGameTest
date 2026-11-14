#!/usr/bin/env python3
"""Independent proof checker for native clause-only Hall/pigeonhole certificates.

Soundness:
- n disjoint original CNF clauses demand at least n distinct TRUE literals.
- k covering cliques, each supported by ORIGINAL pairwise blocking clauses,
  allow at most k of those literals to be simultaneously TRUE.
- If n>k, every assignment contradicts these clauses. No BDD, solver, LP,
  or heuristic search is trusted by the checker.
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from check_capacity import parse_cnf

class InvalidCertificate(ValueError):
    pass

def require(cond,description):
    if not cond: raise InvalidCertificate(description)

def check(raw, proof):
    require(type(proof) is dict,"proof must be dict")
    require(proof.get("format")=="pcmax-clause-hall-v1","incorrect proof format")
    require(proof.get("source_sha256")==hashlib.sha256(raw).hexdigest(),"CNF SHA256 mismatch")
    _,clauses=parse_cnf(raw)
    gs=proof.get("alo_groups")
    rs=proof.get("resource_cliques")
    require(type(gs) is list and type(rs) is list and len(gs)>len(rs)>0,
            "no Hall deficit or no cliques")
    require(len(gs)<=300 and len(rs)<=300,"proof resource safety limits")
    seen_variables=set()
    union_literals=set()
    for g in gs:
        require(type(g) is list and len(g)>=2 and len(g)<=128,"invalid source group")
        require(all(type(l) is int and l!=0 for l in g),"invalid group literal")
        require(len(set(g))==len(g),"duplicate group literal")
        require(frozenset(g) in clauses,"ALO clause not present in original CNF")
        for l in g:
            require(abs(l) not in seen_variables,"selected ALO groups must be variable-disjoint")
            seen_variables.add(abs(l))
            union_literals.add(l)
    covered=set()
    for resource in rs:
        require(type(resource) is list and len(resource)>0 and len(resource)<=512,
                "invalid resource clique")
        require(all(type(l) is int and l!=0 for l in resource),"invalid resource literal")
        require(len(set(resource))==len(resource),"duplicate clique literal")
        for i,a in enumerate(resource):
            covered.add(a)
            for b in resource[:i]:
                require(frozenset((-a,-b)) in clauses,
                        f"unsupported resource conflict between {a} and {b}")
    require(union_literals <= covered,
            "some demanded ALO options are uncovered by source-proven cliques")
    require(proof.get("required_groups")==len(gs),"wrong required group count")
    require(proof.get("resource_bound")==len(rs),"wrong clique capacity count")
    return {
        "status":"UNSAT_CLAUSE_HALL_CERTIFICATE_VERIFIED",
        "source_sha256":hashlib.sha256(raw).hexdigest(),
        "required_groups":len(gs),"resource_bound":len(rs),
        "deficit":len(gs)-len(rs),"original_unique_clauses":len(clauses),
        "covered_literals":len(union_literals)
    }

def main():
    a=argparse.ArgumentParser()
    a.add_argument("cnf",type=Path)
    a.add_argument("certificate",type=Path)
    arg=a.parse_args()
    try:
        raw=arg.cnf.read_bytes()
        data=json.loads(arg.certificate.read_text())
        print(json.dumps(check(raw,data),sort_keys=True))
    except Exception as e:
        print("INVALID_CLAUSE_HALL_PROOF "+str(e),file=sys.stderr)
        sys.exit(1)

if __name__=="__main__": main()
