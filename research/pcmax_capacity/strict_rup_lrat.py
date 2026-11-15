#!/usr/bin/env python3
"""Independent strict checker for the RUP-only subset of ASCII LRAT.

This does not import the DRNAS generator. It checks each positive LRAT hint
as an actual unit-propagation step and requires an explicit final conflict
when deriving each lemma. It rejects RAT-only proofs (not used here).
Output is accepted only with independent drat-trim and upstream lrat-check.
"""
import argparse
from pathlib import Path

class InvalidLRAT(ValueError):
    pass

def require(condition,why):
    if not condition:raise InvalidLRAT(why)

def parse_input(data):
    header=None
    clauses=[]
    partial=[]
    for raw in data.decode("ascii").splitlines():
        line=raw.split()
        if not line or line[0]=="c":continue
        if line[0]=="p":
            require(header is None and len(line)==4 and line[1]=="cnf",
                    "invalid DIMACS header")
            header=(int(line[2]),int(line[3]))
            require(header[0]>=0 and header[1]>=0,"negative DIMACS count")
            continue
        require(header is not None,"clause before DIMACS header")
        for token in line:
            lit=int(token)
            require(abs(lit)<=header[0],"DIMACS variable out of range")
            if lit==0:
                clauses.append(tuple(partial))
                partial=[]
            else:partial.append(lit)
    require(header is not None and len(clauses)==header[1] and not partial,
            "DIMACS clause count mismatch")
    return header,clauses

def literal_status(lit,values):
    val=values.get(abs(lit))
    if val is None:return None
    return val==(lit>0)

def check(original,proof):
    (nvars,nsource),initial=parse_input(original)
    database={i:tuple(c) for i,c in enumerate(initial,1)}
    previous=nsource
    derived=0
    seen_empty=False
    for line_number,raw in enumerate(proof.decode("ascii").splitlines(),1):
        fields=raw.split()
        if not fields or fields[0]=="c":continue
        require(not seen_empty,"unexpected additions after empty-clause proof")
        numbers=[int(s) for s in fields]
        require(len(numbers)>=4,"short LRAT line")
        idx=numbers[0]
        require(idx>previous,"LRAT indexes not monotonically increasing")
        try:
            first_zero=numbers.index(0,1)
        except ValueError as e:
            raise InvalidLRAT("missing LRAT literal terminator") from e
        require(numbers[-1]==0,"missing LRAT hint terminator")
        clause=numbers[1:first_zero]
        hints=numbers[first_zero+1:-1]
        require(len(hints)>0 and all(h>0 and h in database for h in hints),
                "missing, future or non-RUP hint")
        require(all(0<abs(l)<=nvars for l in clause),
                "out-of-range derived literal")
        require(len({abs(l) for l in clause})==len(clause),
                "repeated or tautological derived variable")
        assignment={}
        for lit in clause:
            # Negation of every derived literal is an assumed true literal.
            assignment[abs(lit)]=(lit<0)
        conflicted=False
        for i,hid in enumerate(hints):
            c=database[hid]
            unsolved=[]
            sat=False
            for lit in c:
                status=literal_status(lit,assignment)
                if status is True:
                    sat=True
                    break
                if status is None:unsolved.append(lit)
            require(not sat,"LRAT hint already satisfied")
            if len(unsolved)==0:
                conflicted=True
                require(i==len(hints)-1,"unused hints after conflict")
            elif len(unsolved)==1:
                lit=unsolved[0]
                require(i<len(hints)-1,"last hint only propagates a unit")
                variable=abs(lit)
                value=lit>0
                require(variable not in assignment,
                        "hint claims unit on assigned literal")
                assignment[variable]=value
            else:raise InvalidLRAT("hint not unit or conflict under assumptions")
        require(conflicted,"no explicit conflict: invalid RUP addition")
        database[idx]=tuple(clause)
        previous=idx
        derived+=1
        if not clause:seen_empty=True
        require(derived<=100000,"proof line safety bound")
    require(seen_empty and derived>0,"LRAT does not derive the empty clause")
    return {"status":"STRICT_RUP_LRAT_VERIFIED",
            "source_clauses":nsource,"proof_additions":derived}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("cnf",type=Path)
    p.add_argument("proof",type=Path)
    args=p.parse_args()
    try:
        result=check(args.cnf.read_bytes(),args.proof.read_bytes())
    except (InvalidLRAT,ValueError,UnicodeDecodeError) as exc:
        print("INVALID_STRICT_RUP_LRAT "+str(exc))
        raise SystemExit(1)
    print(f"{result['status']} source={result['source_clauses']} steps={result['proof_additions']}")

if __name__=="__main__":main()
