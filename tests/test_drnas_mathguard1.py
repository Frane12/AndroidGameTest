#!/usr/bin/env python3
"""Independent exhaustive small-CNF oracle and RUP audit for MATH-GUARD1.

No benchmark outcome labels are provided to the solver; all candidates must be
original-source binary/ternary resolution and every proof addition must be RUP.
"""
import itertools
import json
from pathlib import Path
import random
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FROZEN = ROOT / "build/drnas-x59-frozen"
GUARD = ROOT / "build/drnas-mathguard1"


def truth(clauses, values):
    return all(any(values[abs(l)] == (l > 0) for l in c) for c in clauses)


def oracle(n, clauses):
    for bits in itertools.product((False, True), repeat=n):
        m = {i + 1: v for i, v in enumerate(bits)}
        if truth(clauses, m):
            return True
    return False


def rup_conflict(clauses, assumptions):
    assigned = {}
    for lit in assumptions:
        v = abs(lit)
        wanted = lit > 0
        if v in assigned and assigned[v] != wanted:
            return True
        assigned[v] = wanted
    while True:
        changed = False
        for clause in clauses:
            if any(assigned.get(abs(l)) == (l > 0) for l in clause
                   if abs(l) in assigned):
                continue
            free = [l for l in clause if abs(l) not in assigned]
            if not free:
                return True
            if len(free) == 1:
                lit = free[0]
                assigned[abs(lit)] = lit > 0
                changed = True
        if not changed:
            return False


def check_proof(src, path, status):
    clauses = list(map(list, src))
    entries = 0
    saw_empty = False
    for line in path.read_text().splitlines():
        tokens = line.strip().split()
        if not tokens or tokens[0] in ("c", "d"):
            continue
        row = list(map(int, tokens))
        assert row[-1] == 0, ("MALFORMED_PROOF", row)
        lemma = row[:-1]
        assert rup_conflict(clauses, [-x for x in lemma]), (
            "NON_RUP_PROOF_ADDITION", lemma, len(clauses))
        clauses.append(lemma)
        entries += 1
        if not lemma:
            saw_empty = True
    if status == 20:
        assert saw_empty, "UNSAT_MISSING_EMPTY_PROOF"
    return entries


def parse_model(out, n):
    m = {}
    for line in out.splitlines():
        if line.startswith("v "):
            for token in line.split()[1:]:
                lit = int(token)
                if lit != 0:
                    m[abs(lit)] = lit > 0
    assert len(m) == n, ("INCOMPLETE_SAT_WITNESS", n, m)
    return m


def events(err, tag):
    return [json.loads(line.split(" ", 1)[1])
            for line in err.splitlines() if line.startswith(tag + " ")]


def source_text(n, clauses):
    return f"p cnf {n} {len(clauses)}\\n".replace("\\\\n", "\\n") + "".join(
        " ".join(map(str, c)) + " 0\\n".replace("\\n", "\n") for c in clauses)


def fixtures():
    cases = [
        ("binary_bridge_sat", 4, [[1, 2, 3], [-1, 2, 3], [-2], [3, 4]]),
        ("binary_bridge_unsat", 3, [[1, 2, 3], [-1, 2, 3], [-2], [-3]]),
        ("unit_resolvent_unsat", 2, [[1, 2], [-1, 2], [-2]]),
        ("already_original", 3, [[1, 2, 3], [-1, 2, 3], [2, 3]]),
        ("parity_sat", 3, [[1, 2, 3], [1, -2, -3], [-1, 2, -3], [-1, -2, 3]]),
        ("parity_unsat", 3, [[1, 2, 3], [1, -2, -3], [-1, 2, -3],
                             [-1, -2, 3], [-1, -2, -3], [-1, 2, 3],
                             [1, -2, 3], [1, 2, -3]]),
        ("nonlinear_shape", 5, [[1, -3, 5], [-1, -3, 5], [2, 3, -4], [-2, 3, -4]]),
        ("empty_clause", 2, [[]]),
        ("root_unit", 2, [[1], [-1, 2]]),
    ]
    for i in range(68):
        rng = random.Random(22040 + i)
        n = 5 + i % 4
        clauses = []
        for _ in range(5 + i % 20):
            width = rng.randint(1, min(4, n))
            vs = rng.sample(range(1, n + 1), width)
            clauses.append([v if rng.randrange(2) else -v for v in vs])
        cases.append((f"random_{i}", n, clauses))
    return cases


def main():
    assert FROZEN.is_file() and GUARD.is_file()
    corpus = fixtures()
    tested = [] 
    all_lemmas = 0
    with tempfile.TemporaryDirectory() as temp:
        temp = Path(temp)
        for name, n, clauses in corpus:
            src = temp / "source.cnf"
            # Standard DIMACS, including the empty-clause edge case.
            src.write_text(f"p cnf {n} {len(clauses)}\n" +
                           "".join(" ".join(map(str, c)) + " 0\n" for c in clauses))
            want = 10 if oracle(n, clauses) else 20
            per_case = []
            for arm, exe, extra in [
                ("FROZEN", FROZEN, []),
                ("GUARD", GUARD, ["--math-guard", "--math-guard-budget-ms", "4.0"]),
            ]:
                proof = temp / f"{arm}.drat"
                result = subprocess.run(
                    [str(exe), str(src), "--mode", "core", "--time", "1.5",
                     "--x5-no-minimize", "--stats", "--proof", str(proof), *extra],
                    capture_output=True, text=True, timeout=6)
                assert result.returncode == want, (
                    "MATHGUARD_VERDICT_MISMATCH", name, arm, want,
                    result.returncode, result.stderr[-1000:])
                if want == 10:
                    assert truth(clauses, parse_model(result.stdout, n)), (
                        "MATHGUARD_INVALID_SAT_MODEL", name, arm)
                if arm == "GUARD":
                    proof_steps = check_proof(clauses, proof, want)
                    st = events(result.stderr, "MATH_GUARD_STATS")
                    assert len(st) == 1, ("MATH_GUARD_MISSING_STATS", name)
                    assert st[0]["enabled"] and st[0]["lemmas"] <= 128
                    learned = events(result.stderr, "MATH_GUARD_LEMMA")
                    assert len(learned) == min(st[0]["lemmas"], 16)
                    source = {tuple(sorted(c)) for c in clauses}
                    for e in learned:
                        a, b = e["parent_positive"], e["parent_negative"]
                        p = e["pivot"]
                        assert tuple(sorted(a)) in source and tuple(sorted(b)) in source
                        assert p in a and -p in b
                        target = sorted(set([l for l in a if l != p] +
                                            [l for l in b if l != -p]))
                        assert sorted(e["clause"]) == target
                        assert len(target) in (1, 2) and not any(-l in target for l in target)
                        assert rup_conflict(clauses, [-l for l in target])
                    if name == "binary_bridge_sat":
                        assert st[0]["lemmas"] >= 1, "MISSING_EXPECTED_BRIDGE"
                    if name == "unit_resolvent_unsat":
                        assert st[0]["units"] >= 1, "MISSING_EXPECTED_UNIT"
                    all_lemmas += st[0]["lemmas"]
                    per_case.append({"arm": arm, "lemmas": st[0]["lemmas"],
                                     "proof_steps": proof_steps,
                                     "guard_ms": st[0]["wall_ms"]})
                else:
                    per_case.append({"arm": arm})
            tested.append({"case": name, "status": "SAT" if want == 10 else "UNSAT",
                           "arms": per_case})
    assert all_lemmas > 0, "NO_MATHGUARD_LEMMAS_EMITTED"
    print("MATH_GUARD1_PREFLIGHT_PASS " + json.dumps({
        "sources": len(tested), "paired_runs": 2 * len(tested),
        "total_verified_guard_lemmas": all_lemmas,
        "all_models_exhaustively_verified": True,
        "all_guard_proof_additions_rup_verified": True,
        "single_process_per_solver": True,
        "speed_claim": False,
    }, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
