#!/usr/bin/env python3
"""Experimental PHP subformula recognizer. Only claims UNSAT when it finds
n distinct positive rows, m<n, with m disjoint column cliques of negative
binary clauses. All clauses of the witness are present in the input.
Not a general PCMAX recognizer or proof emitter.
"""
from collections import defaultdict
import sys

def find_php_core(clauses):
    rows = defaultdict(list)
    neg = set()
    for c in clauses:
        if len(c) >= 2 and all(x > 0 for x in c) and len(set(c)) == len(c):
            rows[len(c)].append(tuple(c))
        if len(c) == 2 and c[0] < 0 and c[1] < 0 and c[0] != c[1]:
            neg.add(tuple(sorted((-c[0], -c[1]))))
    def edge(x, y):
        return tuple(sorted((x, y))) in neg
    for m, rr in rows.items():
        if len(rr) <= m:
            continue
        for start, anchor in enumerate(rr):
            cols = [[x] for x in anchor]
            used = set(anchor)
            chosen = [anchor]
            for r in rr[start + 1:]:
                if used.intersection(r):
                    continue
                mapping = []
                for x in anchor:
                    options = [y for y in r if edge(x, y)]
                    if len(options) != 1:
                        break
                    mapping.append(options[0])
                if len(mapping) != m or len(set(mapping)) != m:
                    continue
                if not all(edge(y, z) for col, y in zip(cols, mapping) for z in col):
                    continue
                for col, y in zip(cols, mapping):
                    col.append(y)
                chosen.append(r)
                used.update(r)
                if len(chosen) > m:
                    return {"rows": chosen, "columns": cols}
    return None

def read_dimacs(stream):
    clauses = []
    clause = []
    for line in stream:
        line = line.strip()
        if not line or line.startswith("c") or line.startswith("p"):
            continue
        for token in line.split():
            lit = int(token)
            if lit == 0:
                clauses.append(tuple(clause))
                clause = []
            else:
                clause.append(lit)
    if clause:
        raise ValueError("unterminated DIMACS clause")
    return clauses

def make_php(n, extra=True):
    m = n - 1
    rows = [[i * m + j + 1 for j in range(m)] for i in range(n)]
    cs = [tuple(r) for r in rows]
    for j in range(m):
        for i in range(n):
            for k in range(i):
                cs.append((-rows[i][j], -rows[k][j]))
    if extra:
        for i in range(n * 2):
            cs.append((n*m+i+1, -rows[i%n][i%m]))
    return cs

def selftest():
    import random
    for n in (4, 8, 16, 32):
        cs = make_php(n)
        random.Random(n).shuffle(cs)
        assert find_php_core(cs) is not None
        cs = make_php(n, False)
        cs.remove(next(c for c in cs if len(c) == 2 and all(x < 0 for x in c)))
        assert find_php_core(cs) is None
        # SAT control: n pigeons in n holes
        m=n
        rows=[[i*m+j+1 for j in range(m)] for i in range(n)]
        sat=[tuple(r) for r in rows]
        sat += [(-rows[i][j],-rows[k][j]) for j in range(m)
                for i in range(n) for k in range(i)]
        assert find_php_core(sat) is None
    print("SELFTEST PASS: 4 sizes, extra clauses, missing edges, SAT controls")

if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        result = find_php_core(read_dimacs(sys.stdin))
        print("s UNSATISFIABLE" if result else "s UNKNOWN")
        # Exit 0 deliberately: this is not yet a certified solver interface.
