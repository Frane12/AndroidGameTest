#!/usr/bin/env python3
"""Independent original-source soundness checker for IPG2 CNF count certificates.

Does NOT import discovery/solver. Re-reads exact DIMACS bytes, verifies each
asserted forbidden count pair against actual original clauses, and performs
a separate count DP. A valid UNSAT claim is logically implied by the source.

No standard VeriPB/DRAT proof is produced by this checker.
"""
import argparse
import hashlib
import itertools
import json
import pathlib

def parse(raw):
    nv=nc=None;clauses=[];pending=[]
    for line in raw.decode("ascii").splitlines():
        t=line.split()
        if not t or t[0]=="c":continue
        if t[0]=="p":
            if nv is not None or len(t)!=4 or t[1]!="cnf":
                raise ValueError("invalid DIMACS header")
            nv,nc=int(t[2]),int(t[3])
            if nv<0 or nv>144 or nc<0 or nc>350000:
                raise ValueError("unsupported source size")
            continue
        if nv is None:raise ValueError("missing source header")
        for word in t:
            v=int(word)
            if abs(v)>nv:raise ValueError("invalid source literal")
            if v:pending.append(v)
            else:clauses.append(tuple(pending));pending=[]
    if nv is None or pending or nc!=len(clauses):
        raise ValueError("mismatched original clause count")
    return nv,clauses

def check(raw,cert):
    if cert.get("format")!="DRNAS-IPG2-CNF-COUNT-V1" or (
        cert.get("status")!="UNSAT_SOURCE_COUNT_CERTIFICATE_UNCHECKED"):
        raise ValueError("no suitable UNSAT source certificate")
    if cert.get("source_sha256")!=hashlib.sha256(raw).hexdigest():
        raise ValueError("CNF SHA256 differs")
    nv,clauses=parse(raw)
    if cert.get("source_variables")!=nv or cert.get("source_clauses")!=len(clauses):
        raise ValueError("declared source size changed")
    m=cert.get("machines")
    if type(m)!=int or m not in (2,3):raise ValueError("machine count unsupported")
    groups=[tuple(c) for c in clauses if len(c)==m and all(x>0 for x in c)]
    n=len(groups)
    if n<3 or n>48 or m*n!=nv or cert.get("jobs")!=n:
        raise ValueError("source not full disjoint group encoding")
    index={frozenset(c) for c in clauses}
    machine_for={}
    jobs_for={}
    for job,group in enumerate(groups):
        if len(set(group))!=m:raise ValueError("duplicate selector")
        for machine,lit in enumerate(group):
            if lit in machine_for:raise ValueError("overlapping source groups")
            machine_for[lit]=machine
            jobs_for[lit]=job
        for a,b in itertools.combinations(group,2):
            if frozenset((-a,-b)) not in index:
                raise ValueError("source lacks job at-most-one")
    if set(machine_for)!=set(range(1,nv+1)):
        raise ValueError("source group cover incomplete")

    raw_for=[set() for _ in range(m)]
    for c in clauses:
        if not 1<=len(c)<=3 or any(lit>=0 for lit in c):
            continue
        positive=[-x for x in c]
        mach=machine_for[positive[0]]
        if any(machine_for[x]!=mach for x in positive):continue
        jobs=frozenset(jobs_for[x] for x in positive)
        if len(jobs)==len(c):raw_for[mach].add(jobs)
    if cert.get("source_negative_patterns")!=[len(s) for s in raw_for]:
        raise ValueError("different source negative patterns")

    groups2=cert.get("classes")
    if not isinstance(groups2,list) or len(groups2)!=2:
        raise ValueError("missing type classes")
    A,B=groups2
    if not all(isinstance(z,list) and all(type(v)==int for v in z) for z in groups2):
        raise ValueError("malformed type classes")
    if len(set(A))!=len(A) or len(set(B))!=len(B):
        raise ValueError("duplicate job in class")
    if set(A)&set(B) or (set(A)|set(B))!=set(range(n)):
        raise ValueError("type classes do not partition jobs")
    forbidden=cert.get("forbidden_counts")
    if not isinstance(forbidden,list) or len(forbidden)!=m:
        raise ValueError("missing machine restrictions")
    checks=0
    for machine,tuples in enumerate(forbidden):
        if not isinstance(tuples,list):raise ValueError("bad machine pattern list")
        for uv in tuples:
            if not isinstance(uv,(tuple,list)) or len(uv)!=2:
                raise ValueError("bad forbidden count pair")
            u,v=uv
            if (type(u)!=int or type(v)!=int or u<0 or v<0 or
                u+v<1 or u+v>3 or u>len(A) or v>len(B)):
                raise ValueError("forbidden count outside fixed polynomial scope")
            for s1 in itertools.combinations(A,u):
                for s2 in itertools.combinations(B,v):
                    selected=set(s1+s2)
                    checks+=1
                    if not any(f.issubset(selected) for f in raw_for[machine]):
                        raise ValueError("claimed capacity pattern is NOT entailed by original clauses")

    # Independently compute reachability, using a different iteration order:
    # for each possible per-machine count, shift the previously reachable set.
    na,nb=len(A),len(B)
    reachable={(0,0)}
    row_sizes=[1]
    for k,patterns in enumerate(forbidden):
        nxt=set()
        for aa in range(na+1):
            for bb in range(nb+1):
                if any(aa>=u and bb>=v for u,v in patterns):
                    continue
                for olda,oldb in reachable:
                    if olda+aa<=na and oldb+bb<=nb:
                        nxt.add((olda+aa,oldb+bb))
        reachable=nxt
        row_sizes.append(len(reachable))
    if cert.get("reachable_sizes")!=row_sizes:
        raise ValueError("claimed DP rows differ from independent calculation")
    if (na,nb) in reachable:
        raise ValueError("feasible source count relaxation: cannot certify UNSAT")
    return {"status":"IPG2_SOURCE_COUNTS_VERIFIED",
            "jobs":n,"machines":m,"classes":[na,nb],
            "source_patterns_checked":checks,"reachability_rows":row_sizes,
            "sha256":hashlib.sha256(raw).hexdigest()}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("cnf",type=pathlib.Path)
    p.add_argument("certificate",type=pathlib.Path)
    a=p.parse_args()
    try:
        r=check(a.cnf.read_bytes(),json.loads(a.certificate.read_text()))
        print("IPG2_BRIDGE_ACCEPT "+json.dumps(r,sort_keys=True),flush=True)
        return 0
    except (OSError,ValueError,KeyError,TypeError,IndexError,UnicodeError,json.JSONDecodeError) as e:
        print("IPG2_BRIDGE_REJECT "+str(e),flush=True)
        return 1

if __name__=="__main__":
    raise SystemExit(main())
