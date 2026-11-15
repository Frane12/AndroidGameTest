#!/usr/bin/env python3
"""Independent source-clause certificate checker for INEQ-GUARD1.

Each signed binary relation must be backed by BOTH original CNF clauses.
Parity sum around a closed walk = 1 is impossible for Boolean assignments.
For a 3-cycle this is a 1-bit Hamming triangle contradiction.
For a 4-cycle with three equalities and one disequality it is deterministic
CHSH algebra, not a new physical Bell inequality or quantum result.
"""
import argparse
import hashlib
import json
from pathlib import Path
from check_capacity import parse_cnf

class InvalidInequalityCertificate(ValueError):
    pass

def require(ok, msg):
    if not ok:
        raise InvalidInequalityCertificate(msg)

def verify(raw: bytes, certificate: dict):
    require(type(certificate) is dict, "invalid certificate")
    require(certificate.get("format") == "drnas-ineq-guard-v1", "wrong certificate format")
    require(certificate.get("source_sha256") == hashlib.sha256(raw).hexdigest(), "source bytes mismatch")
    variables, source = parse_cnf(raw)
    edges = certificate.get("edges")
    require(type(edges) is list and 2 <= len(edges) <= 257, "invalid edge list")
    expected_label = "triangle" if len(edges)==3 else ("chsh4" if len(edges)==4 else "parity_cycle")
    require(certificate.get("witness") == expected_label, "witness class mismatch")
    parity_sum = 0
    degrees = {}
    for edge in edges:
        require(type(edge) is list and len(edge) == 3 and all(type(z) is int for z in edge),
                "malformed relation")
        u, v, difference = edge
        require(1 <= u < v <= variables and difference in (0,1), "relation out of bounds")
        if difference == 0:
            required = (frozenset((u,-v)), frozenset((-u,v)))
        else:
            required = (frozenset((u,v)), frozenset((-u,-v)))
        require(all(clause in source for clause in required), "missing source parity clause")
        degrees[u] = degrees.get(u,0)^1
        degrees[v] = degrees.get(v,0)^1
        parity_sum ^= difference
    require(all(d == 0 for d in degrees.values()), "not a closed cycle")
    require(parity_sum == 1, "no odd-parity contradiction")
    return {"status": "UNSAT_INEQ_SOURCE_CERTIFIED",
            "source_sha256": certificate["source_sha256"],
            "kind": expected_label, "edges": len(edges), "false_unsat": 0}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cnf",type=Path)
    ap.add_argument("certificate",type=Path)
    args=ap.parse_args()
    try:
        result=verify(args.cnf.read_bytes(),json.loads(args.certificate.read_text()))
    except (OSError, KeyError, TypeError, ValueError) as exc:
        print("INVALID_INEQ_CERTIFICATE "+str(exc))
        return 1
    print("INEQ_CERTIFICATE_VERIFIED "+json.dumps(result,sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
