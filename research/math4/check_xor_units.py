#!/usr/bin/env python3
"""Source-only independent checker for GF(2) UNSAT using root-UP units.

Proof validity depends only on ORIGINAL DIMACS SHA256, original full
XOR parity half-cube clauses, and a fresh root unit-propagation closure.
It never trusts a producer's elimination, source classification or solver.
"""
import hashlib
import itertools
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"pcmax_capacity"))
from check_capacity import parse_cnf

class InvalidMath4Proof(ValueError):
    pass

def require(condition,message):
    if not condition:raise InvalidMath4Proof(message)

def closure(clauses,nvars):
    assignments={}
    rounds=0
    while True:
        rounds+=1
        require(rounds<=nvars+1,"root propagation closure did not converge")
        changed=False
        for c in clauses:
            sat=False
            pending=0
            last=None
            for lit in c:
                assigned=assignments.get(abs(lit))
                if assigned is None:
                    pending+=1
                    last=lit
                elif assigned==(lit>0):
                    sat=True
                    break
            if sat:continue
            if pending==0:
                # A direct source-clause unit conflict is already an UNSAT
                # proof, but this proof FORMAT is for GF2 contradictions.
                raise InvalidMath4Proof("source BCP contradiction; use separate RUP proof")
            if pending==1:
                desired=last>0
                var=abs(last)
                prev=assignments.get(var)
                require(prev is None or prev==desired,"unit assignment conflict")
                if prev is None:
                    assignments[var]=desired
                    changed=True
        if not changed:return assignments

def verify(raw,proof):
    require(isinstance(proof,dict) and proof.get("format")=="drnas-math4-xor-unit-v1",
            "invalid proof format")
    require(proof.get("source_sha256")==hashlib.sha256(raw).hexdigest(),
            "exact original input SHA256 mismatch")
    nvars,original=parse_cnf(raw)
    require(nvars>0 and nvars<=6000 and len(original)<=100000,
            "proof checker bounded original size")
    rows=proof.get("xor_rows")
    units=proof.get("root_units")
    require(type(rows) is list and 1<=len(rows)<=4096 and
            type(units) is list and len(units)<=4096,
            "invalid witness collections")
    # Independently re-derive all forced assignments, not trusting a list of
    # claimed unit implications or any intermediate solver state.
    forced=closure(original,nvars)
    variables=set()
    right=0
    for row in rows:
        require(type(row) is dict,"bad XOR row")
        support=row.get("vars")
        forbid=row.get("forbidden_parity")
        require(type(support) is list and 2<=len(support)<=6 and
                len(set(support))==len(support) and
                all(type(v) is int and 0<v<=nvars for v in support),
                "invalid XOR variable support")
        require(type(forbid) is int and forbid in (0,1),"bad XOR parity")
        # FULL original half cube is required. No learned clauses, no
        # preprocessing and no algebraic guesses can pass this proof checker.
        for bits in itertools.product((0,1),repeat=len(support)):
            if sum(bits)%2!=forbid:continue
            clause=frozenset(-v if b else v for v,b in zip(support,bits))
            require(clause in original,"missing original XOR support clause")
        for v in support:
            if v in variables:variables.remove(v)
            else:variables.add(v)
        right^=1-forbid
    seen_units=set()
    for lit in units:
        require(type(lit) is int and lit!=0 and abs(lit)<=nvars,
                "invalid root unit")
        require(abs(lit) not in seen_units,"duplicate or contradictory unit")
        seen_units.add(abs(lit))
        require(forced.get(abs(lit))==(lit>0),
                "root unit not derivable by original-CNF unit propagation")
        if abs(lit) in variables:variables.remove(abs(lit))
        else:variables.add(abs(lit))
        right^=int(lit>0)
    require(not variables and right==1,
            "XOR witness does not derive 0 = 1")
    return {"status":"UNSAT_VERIFIED","source_sha256":hashlib.sha256(raw).hexdigest(),
            "method":"GF2_WITH_SOURCE_BCP_UNITS","xor_rows":len(rows),
            "root_units":len(units),"original_clauses":len(original),
            "forced_unit_closure":len(forced)}


if __name__=="__main__":
    import argparse,json,sys
    from pathlib import Path
    parser=argparse.ArgumentParser()
    parser.add_argument("cnf",type=Path)
    parser.add_argument("certificate",type=Path)
    a=parser.parse_args()
    try:
        result=verify(a.cnf.read_bytes(),json.loads(a.certificate.read_text()))
        print(json.dumps(result,sort_keys=True))
    except Exception as exc:
        print("INVALID_MATH4_SOURCE_CERTIFICATE "+str(exc),file=sys.stderr)
        raise SystemExit(1)
