"""Independent original-CNF semantic verifier for DRNAS MATH Ω3.

Never imports the detector. Every claimed XOR row must follow from its listed
original clauses on at most four variables; the sum must give 0 = 1.
Backend UNSAT without separate DRAT/LRAT is NOT certified by this verifier.
"""
import hashlib
import itertools


def parse_cnf(raw):
    declared = None
    clauses = []
    clause = []
    for line in raw.decode("ascii").splitlines():
        line = line.strip()
        if not line or line.startswith("c"):
            continue
        if line.startswith("p "):
            f = line.split()
            if len(f) != 4 or f[1] != "cnf" or declared is not None:
                raise ValueError("Invalid DIMACS header")
            declared = (int(f[2]), int(f[3]))
            continue
        if declared is None:
            raise ValueError("DIMACS clause before header")
        for f in line.split():
            v = int(f)
            if v:
                if abs(v) > declared[0] or not v:
                    raise ValueError("Literal out of declared range")
                clause.append(v)
            else:
                clauses.append(tuple(clause))
                clause = []
    if declared is None or clause or declared[1] != len(clauses):
        raise ValueError("Bad clause count or missing terminator")
    return declared[0], clauses


def verify_unsat(raw, rows):
    n, clauses = parse_cnf(raw)
    source = {tuple(sorted(c)) for c in clauses}
    if not rows or len(rows) > 5000:
        raise ValueError("Empty or oversized proof")
    left = set()
    right = 0
    for row in rows:
        premise = [tuple(map(int, c)) for c in row["premises"]]
        if not premise or any(tuple(sorted(c)) not in source for c in premise):
            raise ValueError("Untraceable premise")
        support = sorted({abs(v) for c in premise for v in c})
        vars_ = sorted(map(int, row["vars"]))
        rhs = int(row["rhs"])
        if not 1 <= len(support) <= 4 or vars_ != support or rhs not in (0, 1):
            raise ValueError("Invalid parity row")
        nonempty = 0
        for bits in itertools.product((False, True), repeat=len(support)):
            assignment = dict(zip(support, bits))
            if all(any(assignment[abs(v)] == (v > 0) for v in c) for c in premise):
                nonempty += 1
                if sum(assignment[v] for v in vars_) % 2 != rhs:
                    raise ValueError("Source fragment does not entail parity")
        if not nonempty:
            raise ValueError("Contradictory rule premise")
        left.symmetric_difference_update(vars_)
        right ^= rhs
    if left or right != 1:
        raise ValueError("No 0=1 contradiction")
    return {"verified": True, "rows": len(rows), "sha256": hashlib.sha256(raw).hexdigest()}


def verify_sat(raw, log):
    n, clauses = parse_cnf(raw)
    assignment = {}
    for line in log.splitlines():
        if line.startswith("v "):
            for field in line[1:].split():
                lit = int(field)
                if lit and abs(lit) <= n:
                    assignment[abs(lit)] = (lit > 0)
    if not assignment:
        raise ValueError("Missing SAT assignment")
    if any(not any(assignment.get(abs(v), False) == (v > 0) for v in c)
           for c in clauses):
        raise ValueError("Assignment fails original clauses")
    return {"verified": True, "assigned": len(assignment)}


def verify_source_preserving_sat_view(original, sat_view):
    """Independently check that SAT view retained every original source clause.

    Allowed non-SAT metadata: DIMACS 'c' comments (including weighted/projected
    annotations), separate 'w ' weight lines, and terminal SATLIB '%' marker.
    Returns the semantic clause count, never a SAT/UNSAT verdict.
    """
    n, reference = parse_cnf(sat_view)
    source_n = source_m = None
    clause = []
    original_clauses = []
    for rawline in original.decode("ascii").splitlines():
        line = rawline.strip()
        if not line or line.startswith("c") or (line.startswith("w ") or line.startswith("w\t")):
            continue
        if line.startswith("%"):
            break
        if line.startswith("p "):
            parts = line.split()
            if len(parts) != 4 or parts[1] != "cnf" or source_n is not None:
                raise ValueError("Unsupported source header")
            source_n, source_m = int(parts[2]), int(parts[3])
            continue
        if source_n is None:
            raise ValueError("Missing original header")
        for field in line.split():
            lit = int(field)
            if lit:
                if abs(lit) > source_n:
                    raise ValueError("Out-of-range original literal")
                clause.append(lit)
            else:
                original_clauses.append(tuple(clause))
                clause = []
    if source_n != n or source_m != len(reference) or original_clauses != reference or clause:
        raise ValueError("Not a clause-preserving SAT projection")
    return {"source_clauses": len(reference), "source_vars": n}
