#!/usr/bin/env python3
"""Pure-Python preflight for the structural-feature extractor.

These tests do not evaluate SAT performance. They ensure the planned structural
features are unchanged by trivial DIMACS renaming / polarity transformations.
"""
import random
import tempfile
from pathlib import Path
from structural_pilot_v89 import structural_features, SPECS

def write_cnf(path, n, clauses):
    path.write_text("p cnf %d %d\n"%(n,len(clauses))+
                    "".join(" ".join(str(x) for x in clause)+" 0\n" for clause in clauses))

def main():
    n = 8
    clauses = [[1, -2, 3], [-1, 2], [2, 4], [3, -4, 5],
               [5, 6], [-5, -7], [1, -1, 6], [2, -3, 7]]
    rng = random.Random(74123)
    permutation = list(range(1,n+1))
    rng.shuffle(permutation)
    flips = [rng.choice((-1,1)) for _ in range(n)]
    transformed = [[(1 if lit>0 else -1)*permutation[abs(lit)-1]*flips[abs(lit)-1]
                    for lit in clause] for clause in clauses]
    rng.shuffle(transformed)
    with tempfile.TemporaryDirectory() as d:
        first=Path(d)/"one.cnf"
        second=Path(d)/"two.cnf"
        write_cnf(first,n,clauses)
        write_cnf(second,n,transformed)
        before=structural_features(first)
        after=structural_features(second)
        assert before==after, {"before":before,"after":after}
        assert before["isolated_variable_fraction"] == 0.125
        assert before["largest_component_fraction"] == 0.875
        assert before["binary_fraction"] > 0
        assert len(SPECS)==40 and len(set(SPECS))==40
        assert all(isinstance(v,float) for v in before.values())
        # Sanity check that changing the literal count changes a real feature.
        write_cnf(second,n,clauses+[[3,4,7]])
        changed=structural_features(second)
        assert changed["density"] != before["density"]
        # Fail closed for a CNF with mismatching header.
        second.write_text("p cnf 8 2\n1 0\n")
        try:
            structural_features(second)
        except ValueError:
            pass
        else:
            raise AssertionError("Malformed CNF was silently accepted")
    print("STRUCTURAL_V89_SELFTEST_OK: permutation/sign invariance and parsing",flush=True)

if __name__ == "__main__":
    main()
