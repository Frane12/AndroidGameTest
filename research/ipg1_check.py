#!/usr/bin/env python3
"""Independent source-bound checker for DRNAS IPG1 exact 3-machine cover.

Checks only ORIGINAL CNF premises, not the native analyzer's internal state.
This is a structural/exhaustive UNSAT certificate, NOT DRAT/LRAT/VeriPB.
The 3^n enumeration is intentional; no polynomial general-PCMAX claim.
"""
import argparse
import hashlib
import itertools
import json
import pathlib
import sys


def read_dimacs(raw):
    nvars = nclauses = None
    clauses = []
    pending = []
    for line in raw.decode("ascii").splitlines():
        tok = line.strip().split()
        if not tok or tok[0] == "c":
            continue
        if tok[0] == "p":
            if nvars is not None or len(tok) != 4 or tok[1] != "cnf":
                raise ValueError("invalid DIMACS header")
            nvars, nclauses = map(int, tok[2:])
            if nvars < 0 or nclauses < 0:
                raise ValueError("negative DIMACS counts")
            continue
        if nvars is None:
            raise ValueError("clause before DIMACS header")
        for item in tok:
            literal = int(item)
            if abs(literal) > nvars:
                raise ValueError("out-of-range source literal")
            if literal:
                pending.append(literal)
            else:
                clauses.append(tuple(pending))
                pending = []
    if nvars is None or pending or len(clauses) != nclauses:
        raise ValueError("incomplete DIMACS input")
    return nvars, clauses


def independently_check(raw, certificate):
    sha = hashlib.sha256(raw).hexdigest()
    if certificate.get("version") != "drnas-ipg1-exact-cover-v1":
        raise ValueError("wrong certificate version")
    if certificate.get("source_sha256") != sha:
        raise ValueError("original source SHA-256 mismatch")
    nvars, clauses = read_dimacs(raw)
    if (certificate.get("source_variables") != nvars or
            certificate.get("source_clauses") != len(clauses)):
        raise ValueError("original source size mismatch")
    groups = [c for c in clauses if len(c) == 3 and all(x > 0 for x in c)]
    n = len(groups)
    if n < 3 or n > 15 or nvars != 3*n:
        raise ValueError("unsupported groups; no certificate")
    owner, pos = {}, {}
    for j, group in enumerate(groups):
        if len(set(group)) != 3:
            raise ValueError("duplicate group selector")
        for m, x in enumerate(group):
            if x in owner or x > nvars:
                raise ValueError("source selector overlap")
            owner[x], pos[x] = j, m
    if set(owner) != set(range(1, nvars+1)):
        raise ValueError("uncovered selector")
    mutex = {frozenset((-c[0], -c[1]))
             for c in clauses if len(c) == 2 and c[0] < 0 and c[1] < 0
             and c[0] != c[1]}
    for group in groups:
        for x, y in itertools.combinations(group, 2):
            if frozenset((x,y)) not in mutex:
                raise ValueError("original CNF lacks group at-most-one clause")

    forbidden = [set() for _ in range(3)]
    for clause in clauses:
        if not clause or not all(x < 0 for x in clause):
            continue
        variables = [-lit for lit in clause]
        m = pos[variables[0]]
        if any(pos[x] != m for x in variables):
            continue
        mask = 0
        for x in variables:
            mask |= 1 << owner[x]
        forbidden[m].add(mask)
    if sum(map(len, forbidden)) == 0:
        raise ValueError("no source-grounded capacity clauses")

    N = 1<<n
    full = N-1
    allow = [bytearray([1])*N for _ in range(3)]
    for m in range(3):
        for blocked in forbidden[m]:
            remaining = full ^ blocked
            sub = remaining
            while True:
                allow[m][blocked | sub] = 0
                if sub == 0:
                    break
                sub = (sub-1) & remaining
    patterns = [sum(x) for x in allow]

    examined = 0
    for a in range(N):
        if not allow[0][a]:
            continue
        rem = full ^ a
        b = rem
        while True:
            examined += 1
            if allow[1][b] and allow[2][rem ^ b]:
                raise ValueError("integer partition exists: NOT an UNSAT certificate")
            if b == 0:
                break
            b = (b-1) & rem

    expected = {
        "group_count":n,
        "machine_count":3,
        "selected_negative_clauses":sum(map(len, forbidden)),
        "admissible_subsets":patterns,
        "checked_partitions":examined,
        "claim":"UNSAT_EXHAUSTIVE_SOURCE_CLAUSE_COVER",
    }
    for key, value in expected.items():
        if certificate.get(key) != value:
            raise ValueError(f"certificate field {key}: mismatch")
    return {
        "status":"IPG1_EXACT_SOURCE_COVER_VERIFIED",
        "sha256":sha,
        "jobs":n,
        "machines":3,
        "admissible":patterns,
        "checked_partitions":examined,
        "source_clauses":len(clauses),
    }


def main():
    a=argparse.ArgumentParser()
    a.add_argument("cnf",type=pathlib.Path)
    a.add_argument("certificate",type=pathlib.Path)
    ns=a.parse_args()
    try:
        result=independently_check(ns.cnf.read_bytes(),
                    json.loads(ns.certificate.read_text(encoding="utf-8")))
    except (ValueError,KeyError,TypeError,UnicodeError,OSError,json.JSONDecodeError) as exc:
        print("IPG1_CERTIFICATE_REJECTED "+str(exc),flush=True)
        return 1
    print("IPG1_SOURCE_VERIFIED "+json.dumps(result,sort_keys=True),flush=True)
    return 0


if __name__=="__main__":
    sys.exit(main())
