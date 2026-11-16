#!/usr/bin/env python3
"""Independent MATCH2-BDD-MASK1 source-grounded UNSAT checker.

Does not import producer, old MATCH2 or fixture generator.
Re-parses original DIMACS, verifies ALO + AMO and selector partition,
rebuilds negative-constraint mask profiles with a different algorithm,
then checks impossibility of exact disjoint cover from source clauses.
It is NOT a standardized LRAT/DRAT/VeriPB certificate verifier.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path

FORMAT="DRNAS-MATCH2-BDD-MASK1-SOURCE-V1"

def original(raw):
    if len(raw)>1000000:raise ValueError("source_too_large")
    nv=nc=None;result=[];partial=[]
    for line in raw.decode("ascii").splitlines():
        tokens=line.split()
        if not tokens or tokens[0]=="c":continue
        if tokens[0]=="p":
            if nv is not None or len(tokens)!=4 or tokens[1]!="cnf":
                raise ValueError("invalid_header")
            nv,nc=map(int,tokens[2:])
            if not (0<=nv<=100000 and 0<=nc<=5000):
                raise ValueError("bad_source_counts")
            continue
        if nv is None:raise ValueError("header_missing")
        for t in tokens:
            v=int(t)
            if abs(v)>nv:raise ValueError("literal_out_of_bounds")
            if v:
                partial.append(v)
                if len(partial)>10000:raise ValueError("clause_too_long")
            else:
                result.append(frozenset(partial))
                partial=[]
    if nv is None or partial or len(result)!=nc:
        raise ValueError("incomplete_original_source")
    return nv,nc,set(result)

def check_structure(raw,certificate):
    if certificate.get("format")!=FORMAT or certificate.get("method")!="MATCH2-BDD-MASK1":
        raise ValueError("unsupported_format")
    if certificate.get("status")!="UNSAT_UNCHECKED":
        raise ValueError("no_claim")
    if certificate.get("source_sha256")!=hashlib.sha256(raw).hexdigest():
        raise ValueError("altered_source_bytes")
    nv,nc,clauses=original(raw)
    groups=certificate.get("groups")
    machines=certificate.get("resources")
    if not isinstance(groups,list) or not 2<=len(groups)<=15:
        raise ValueError("invalid_groups")
    if not isinstance(machines,list) or not 2<=len(machines)<=5:
        raise ValueError("invalid_resource_count")
    if any(not isinstance(g,list) or len(g)!=len(machines) for g in groups):
        raise ValueError("invalid_job_group_width")
    owner={}
    for j,g in enumerate(groups):
        if len(set(g))!=len(g) or any(type(v)!=int or not 1<=v<=nv for v in g):
            raise ValueError("invalid_selector_group")
        if frozenset(g) not in clauses:
            raise ValueError("source_ALO_missing")
        for a,b in itertools.combinations(g,2):
            if frozenset((-a,-b)) not in clauses:
                raise ValueError("source_AMO_missing")
        for v in g:
            if v in owner:raise ValueError("overlapping_selectors")
            owner[v]=j
    seen=set()
    for machine in machines:
        if not isinstance(machine,list) or len(machine)!=len(groups):
            raise ValueError("bad_machine_size")
        if any(type(v)!=int or v not in owner for v in machine) or len(set(machine))!=len(machine):
            raise ValueError("bad_machine_selector")
        if seen.intersection(machine):
            raise ValueError("duplicate_selector_across_machines")
        seen.update(machine)
        if len({owner[v] for v in machine})!=len(groups):
            raise ValueError("non_unique_job_per_machine")
    if seen!=set(owner):raise ValueError("lost_alo_selector")
    if certificate.get("source_variables")!=nv or certificate.get("source_clauses")!=nc:
        raise ValueError("incorrect_source_size")
    if certificate.get("jobs")!=len(groups) or certificate.get("machines")!=len(machines):
        raise ValueError("wrong_extracted_size")
    return owner,machines,clauses

def source_profiles(owner,machines,clauses):
    n=len(set(owner.values()))
    N=1<<n
    profiles=[];counts=[];ban_counts=[]
    for machine in machines:
        part=set(machine)
        forb=set()
        for clause in clauses:
            if clause and all(v<0 and -v in part for v in clause):
                forb.add(sum(1<<owner[-v] for v in clause))
        if not forb:raise ValueError("unrestricted_resource_in_proof")
        # Derivation distinct from producer: downward closure of forbidden
        # masks; each invalid support makes all of its supersets invalid.
        allowed=bytearray(N)
        allowed[0]=1
        for mask in range(1,N):
            if mask in forb:
                continue
            if all(allowed[mask^(1<<j)]
                   for j in range(n) if mask & (1<<j)):
                allowed[mask]=1
        profiles.append(allowed)
        counts.append(sum(allowed))
        ban_counts.append(len(forb))
    return profiles,counts,ban_counts

def independent_disjoint_cover(profiles,n):
    N=1<<n
    full=N-1
    reached=bytearray(N)
    reached[0]=1
    rows=[1]
    for machine in profiles:
        next_reached=bytearray(N)
        # Enumerate previous covered subsets, then all disjoint subsets
        # admitted by the next source-derived machine.
        for already in range(N):
            if not reached[already]:continue
            free=full^already
            option=free
            while True:
                if machine[option]:
                    next_reached[already|option]=1
                if option==0:break
                option=(option-1)&free
        reached=next_reached
        rows.append(sum(reached))
    return bool(reached[full]),rows

def check(raw,cert):
    owner,machines,clauses=check_structure(raw,cert)
    profiles,counts,ban_counts=source_profiles(owner,machines,clauses)
    if counts!=cert.get("allowed_support_counts"):
        raise ValueError("local_machine_profiles_tampered")
    if ban_counts!=cert.get("machine_source_forbidden_counts"):
        raise ValueError("forbidden_constraint_counts_tampered")
    satisfiable,rows=independent_disjoint_cover(profiles,len(set(owner.values())))
    if rows!=cert.get("reachable_mask_counts"):
        raise ValueError("global_exact_cover_count_mismatch")
    if satisfiable:
        raise ValueError("source_relaxation_allows_full_assignment")
    return {"status":"MATCH2_BDD_MASK1_SOURCE_UNSAT_VERIFIED",
            "source_sha256":hashlib.sha256(raw).hexdigest(),
            "jobs":len(set(owner.values())),
            "machines":len(machines),
            "allowed_support_counts":counts,
            "reachable_mask_counts":rows,
            "full_coverage_reachable":False}

if __name__=="__main__":
    p=argparse.ArgumentParser()
    p.add_argument("cnf",type=Path)
    p.add_argument("certificate",type=Path)
    a=p.parse_args()
    try:
        result=check(a.cnf.read_bytes(),json.loads(a.certificate.read_text()))
        print("MATCH2_BDD_MASK1_VERIFIED "+json.dumps(result,sort_keys=True),flush=True)
    except (ValueError,KeyError,IndexError,TypeError,UnicodeError,OverflowError,OSError) as exc:
        print("MATCH2_BDD_MASK1_REJECT "+str(exc),flush=True)
        raise SystemExit(1)
