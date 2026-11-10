#!/usr/bin/env python3
"""Fail-closed SATLIB DIMACS canonicalization. Only comments/layout/end markers
are removed; literals, clause boundaries and declared counts must match exactly.
Canonicalization is not a mathematical solver reduction.
"""
import re

_INTEGER=re.compile(r"[+-]?\d+\Z")

def canonical_dimacs(raw: bytes):
    text=raw.decode("utf-8",errors="replace")
    header=None
    clauses=[]
    pending=[]
    ended=False
    for line_no,line in enumerate(text.splitlines(),1):
        s=line.strip()
        if not s:continue
        if s.startswith(("c","C")):continue  # SATLIB comments, including "c p ..."
        if s.startswith("%"):
            if header is None:raise ValueError(f"end marker before header at {line_no}")
            ended=True
            continue
        if ended:
            if s=="0":continue  # legacy SATLIB end sentinel
            raise ValueError(f"unexpected text after end marker at {line_no}: {s[:50]!r}")
        words=s.split()
        if words[0].lower()=="p":
            if header is not None or len(words)!=4 or words[1].lower()!="cnf" or not all(x.isdigit() for x in words[2:]):
                raise ValueError(f"invalid/duplicate DIMACS header at {line_no}")
            header=(int(words[2]),int(words[3]))
            if header[0]<0 or header[1]<0:raise ValueError("negative dimensions")
            continue
        if header is None:raise ValueError(f"missing header before data at {line_no}")
        nv,nc=header
        for token in words:
            if not _INTEGER.fullmatch(token):raise ValueError(f"non-integer DIMACS token {token[:32]!r} at {line_no}")
            lit=int(token)
            if lit==0:
                clauses.append(tuple(pending))
                pending=[]
                if len(clauses)>nc:raise ValueError("extra clauses beyond declared header")
            else:
                if abs(lit)>nv:raise ValueError(f"literal outside header variable bound at {line_no}")
                pending.append(lit)
    if header is None:raise ValueError("missing DIMACS header")
    if pending:raise ValueError("unterminated DIMACS clause")
    if len(clauses)!=header[1]:
        raise ValueError(f"clause count mismatch declared={header[1]} actual={len(clauses)}")
    canonical=(f"p cnf {header[0]} {header[1]}\n"+"".join(
        " ".join(map(str,clause))+(" " if clause else "")+"0\n" for clause in clauses
    )).encode("ascii")
    return canonical,header,clauses

def witness_ok(clauses, stdout):
    assignment={}
    for line in stdout.splitlines():
        if not (line.startswith("v ") or line.startswith("v\t")):continue
        for word in line[1:].split():
            v=int(word)
            if v==0:continue
            var=abs(v)
            if var in assignment and assignment[var]!=(v>0):return False
            assignment[var]=(v>0)
    return bool(assignment) and all(
        any(assignment.get(abs(lit))==(lit>0) for lit in clause)
        for clause in clauses
    )
