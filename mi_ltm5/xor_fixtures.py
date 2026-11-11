"""Canonical COMPLETE XOR-to-CNF fixture shared by LTM5 proof tests and smoke CI.

The returned clauses forbid assignments of parity opposite to rhs; these
fixtures demonstrate source certification, not a substitute for proof checking.
"""

def xor_clauses(variables, rhs):
    variables=tuple(variables)
    if rhs not in (0,1) or not variables or len(set(variables))!=len(variables) or any(v<=0 for v in variables):
        raise ValueError("invalid XOR fixture")
    return [tuple(-v if mask & (1<<i) else v for i,v in enumerate(variables))
            for mask in range(1<<len(variables)) if mask.bit_count()%2!=rhs]
