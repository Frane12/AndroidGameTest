#!/usr/bin/env python3
"""DRNAS R110: proof-carrying ANF bridge between linear XOR and nonlinear AND.

Research preprocessor: independently verifies every emitted unit/binary
implicate against ORIGINAL CNF witness clauses by exhaustive local checking.
Never assumes that XOR+AND algebra is linear. Never silently modifies input.
No live Kissat inter-worker clause exchange in this research prototype.
"""
import argparse
import hashlib
import itertools
import json
import pathlib
import sys
import tempfile
import time
from collections import defaultdict

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from r106_verify_solver import cnf_clauses

MAX_GATES = 5000
MAX_WINDOWS = 256
MAX_LEMMAS = 256
MAX_WINDOW_VARS = 8


def canonical(clause):
    s = set(clause)
    if any(-x in s for x in s):
        return None
    return tuple(sorted(s))


def extract(clauses):
    """A gate is admitted ONLY if all defining clauses occur in original CNF."""
    index, triples = {}, defaultdict(dict)
    for i, clause in enumerate(clauses):
        key = canonical(clause)
        if key is None or len(key) not in (2, 3):
            continue
        index.setdefault(key, i)
        if len(key) == 3 and len({abs(v) for v in key}) == 3:
            vs = tuple(sorted(abs(v) for v in key))
            mask = sum(1 << j for j, v in enumerate(vs) if -v in key)
            triples[vs].setdefault(mask, i)

    gates, seen = [], set()

    def add(kind, vs, witnesses, detail):
        signature = (kind, tuple(sorted(witnesses)))
        if signature not in seen and len(gates) < MAX_GATES:
            seen.add(signature)
            gates.append(dict(kind=kind, vars=list(vs),
                              witness_clause_ids=sorted(witnesses),
                              detail=detail))

    # CNF sign masks are assignments that falsify individual 3-clauses.
    for vs, masks in sorted(triples.items()):
        for rhs, forbidden in ((0, (1, 2, 4, 7)), (1, (0, 3, 5, 6))):
            if all(m in masks for m in forbidden):
                add("XOR3", vs, [masks[m] for m in forbidden],
                    dict(rhs=rhs, equation="x XOR y XOR z = rhs"))

        # Signed signal z=(a AND b); negative signals are allowed.
        for z in vs:
            a, b = (v for v in vs if v != z)
            for pa, pb, pz in itertools.product((0, 1), repeat=3):
                A, B, Z = (-a if pa else a), (-b if pb else b), (-z if pz else z)
                keys = (canonical((-A, -B, Z)),
                        canonical((A, -Z)), canonical((B, -Z)))
                if all(k in index for k in keys):
                    add("AND", vs, [index[k] for k in keys],
                        dict(inputs=[A, B], output=Z,
                             equation="signed_output = signed_input1 AND signed_input2"))
    return gates


def satisfies(clauses, assignment):
    return all(any(assignment[abs(lit)] == (lit > 0)
                   for lit in clause) for clause in clauses)


def windows(gates):
    """Bounded XOR/AND interactions only; no unbounded component search."""
    occ = defaultdict(list)
    for i, gate in enumerate(gates):
        for var in gate["vars"]:
            occ[var].append(i)
    seen = set()
    for i, gate in enumerate(gates):
        if gate["kind"] != "AND":
            continue
        for v in gate["vars"]:
            for j in occ[v][:128]:
                if gates[j]["kind"] != "XOR3":
                    continue
                pair = tuple(sorted((i, j)))
                union = set(gate["vars"]) | set(gates[j]["vars"])
                if pair not in seen and len(union) <= MAX_WINDOW_VARS:
                    seen.add(pair)
                    yield pair
                    if len(seen) >= MAX_WINDOWS:
                        return


def entailed_by_witness(clauses, witness_ids, lemma):
    """Independent raw-CNF truth-table certificate, not a guessed score."""
    witness = [clauses[i] for i in witness_ids]
    vs = sorted({abs(x) for c in witness + [lemma] for x in c})
    if len(vs) > MAX_WINDOW_VARS:
        return False
    for bits in range(1 << len(vs)):
        assignment = {v: bool(bits & (1 << j)) for j, v in enumerate(vs)}
        if satisfies(witness, assignment) and not satisfies([lemma], assignment):
            return False
    return True


def inspect(source):
    source = pathlib.Path(source)
    t0 = time.perf_counter()
    original_sha = hashlib.sha256(source.read_bytes()).hexdigest()
    clauses = cnf_clauses(source)
    gates = extract(clauses)
    original_set = {canonical(c) for c in clauses}
    discovered = []
    emitted = set()
    inconsistency = []
    count_windows = 0
    for pair in windows(gates):
        count_windows += 1
        ws = sorted({i for j in pair for i in gates[j]["witness_clause_ids"]})
        witness = [clauses[i] for i in ws]
        vars_ = sorted({abs(x) for c in witness for x in c})
        if len(vars_) > MAX_WINDOW_VARS:
            continue
        valid = []
        for bits in range(1 << len(vars_)):
            assignment = {v: bool(bits & (1 << j)) for j, v in enumerate(vars_)}
            if satisfies(witness, assignment):
                valid.append(assignment)
        if not valid:
            inconsistency.append(dict(gate_ids=list(pair), witness_clause_ids=ws))
            continue

        candidates = []
        for v in vars_:
            for value in (False, True):
                if all(a[v] == value for a in valid):
                    candidates.append((v if value else -v,))
        for x, y in itertools.combinations(vars_, 2):
            for bx, by in itertools.product((False, True), repeat=2):
                if not any(a[x] == bx and a[y] == by for a in valid):
                    candidates.append(((-x if bx else x),
                                       (-y if by else y)))

        for lemma in candidates:
            key = canonical(lemma)
            if key in original_set or key in emitted:
                continue
            if not entailed_by_witness(clauses, ws, key):
                raise RuntimeError("R110_FAIL_CLOSED invalid independent witness replay")
            emitted.add(key)
            discovered.append(dict(clause=list(key), gate_ids=list(pair),
                                   witness_clause_ids=ws,
                                   proof="exhaustive original-CNF witness check",
                                   source_sha256=original_sha))
            if len(discovered) >= MAX_LEMMAS:
                break
        if len(discovered) >= MAX_LEMMAS:
            break

    if hashlib.sha256(source.read_bytes()).hexdigest() != original_sha:
        raise RuntimeError("R110_FAIL_CLOSED source changed during analysis")
    return dict(protocol="DRNAS-R110-ANF-MIXED-v1", source=str(source),
                source_sha256=original_sha, original_clauses=len(clauses),
                gates={"xor3": sum(g["kind"] == "XOR3" for g in gates),
                       "and": sum(g["kind"] == "AND" for g in gates)},
                mixed_windows=count_windows, candidate_lemmas=discovered,
                local_unsat_windows=inconsistency,
                preparation_seconds=round(time.perf_counter()-t0, 6),
                provenance="all proofs refer to 0-indexed original CNF clauses",
                limitation="bounded pair-of-gates research; not complete ANF/Groebner solving")


def augmented(source, output, report):
    """Opt-in only: preserve all source clauses, append checked lemmas."""
    clauses = cnf_clauses(source)
    if hashlib.sha256(pathlib.Path(source).read_bytes()).hexdigest() != report["source_sha256"]:
        raise RuntimeError("R110_FAIL_CLOSED source SHA mismatch before writing")
    for item in report["candidate_lemmas"]:
        lemma = tuple(item["clause"])
        if not entailed_by_witness(clauses, item["witness_clause_ids"], lemma):
            raise RuntimeError("R110_FAIL_CLOSED lemma audit failed")
    if not report["candidate_lemmas"]:
        pathlib.Path(output).write_bytes(pathlib.Path(source).read_bytes())
        return
    n = max((abs(x) for c in clauses for x in c), default=0)
    # Preserve declared n, which may include unused variables.
    with pathlib.Path(source).open("r", encoding="ascii") as f:
        headers = [l.split() for l in f if l.startswith("p cnf ")]
    if len(headers) != 1:
        raise RuntimeError("R110_FAIL_CLOSED missing/ambiguous CNF header")
    n = max(n, int(headers[0][2]))
    with pathlib.Path(output).open("w") as f:
        f.write("c DRNAS R110 appended independently checked derived clauses\n")
        f.write(f"p cnf {n} {len(clauses) + len(report['candidate_lemmas'])}\n")
        for c in clauses:
            f.write(" ".join(str(x) for x in c) + " 0\n")
        for item in report["candidate_lemmas"]:
            f.write(" ".join(str(x) for x in item["clause"]) + " 0\n")
    output_clauses = cnf_clauses(output)
    if output_clauses[:len(clauses)] != clauses:
        raise RuntimeError("R110_FAIL_CLOSED source prefix mismatch")


def write_formula(path, n, clauses):
    path.write_text(f"p cnf {n} {len(clauses)}\n" +
                    "".join(" ".join(map(str, c)) + " 0\n" for c in clauses))


def selftest():
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        # c = a XOR b, and c = a AND b -> only a=b=c=0.
        xor = [(-1, 2, 3), (1, -2, 3), (1, 2, -3), (-1, -2, -3)]
        and_ = [(-1, -2, 3), (1, -3), (2, -3)]
        original = xor + and_
        p = root/"mixed.cnf"
        write_formula(p, 3, original)
        report = inspect(p)
        lemmas = [tuple(r["clause"]) for r in report["candidate_lemmas"]]
        assert report["gates"]["xor3"] >= 1 and report["gates"]["and"] >= 1
        assert report["mixed_windows"] >= 1
        assert {(-1,), (-2,), (-3,)}.issubset(set(lemmas)), report
        augmented(p, root/"aug.cnf", report)
        assert cnf_clauses(root/"aug.cnf") == original + lemmas
        for values in itertools.product((False, True), repeat=3):
            assignment = dict(zip((1, 2, 3), values))
            assert satisfies(original, assignment) == satisfies(original+lemmas, assignment)

        # Drop a parity clause: never invent complete XOR.
        p2 = root/"incomplete.cnf"
        write_formula(p2, 3, xor[:-1]+and_)
        r2 = inspect(p2)
        assert r2["gates"]["xor3"] == 0 and not r2["candidate_lemmas"]
        # Fake witness/certificate must fail on raw original clauses.
        assert not entailed_by_witness(original, [0], (-1,))
        # Pure XOR does not masquerade as nonlinear interaction.
        p3 = root/"pure.cnf"
        write_formula(p3, 3, xor)
        r3 = inspect(p3)
        assert r3["gates"]["xor3"] and r3["gates"]["and"] == 0
        assert not r3["candidate_lemmas"]
        # Signed NAND gate checks.
        p4 = root/"nand.cnf"
        write_formula(p4, 3, [(-1, -2, -3), (1, 3), (2, 3)])
        r4 = inspect(p4)
        assert r4["gates"]["and"] >= 1 and r4["mixed_windows"] == 0
    print("R110_ANF_MIXED_SELFTEST_PASS")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("selftest")
    p = sub.add_parser("inspect")
    p.add_argument("--cnf", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--augmented")
    args = parser.parse_args()
    if args.command == "selftest":
        selftest()
    else:
        result = inspect(args.cnf)
        pathlib.Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        pathlib.Path(args.out).write_text(json.dumps(result, indent=2, sort_keys=True)+"\n")
        if args.augmented:
            augmented(args.cnf, args.augmented, result)
        print("R110_INSPECT_COMPLETE", json.dumps({
            "sha256": result["source_sha256"], "gates": result["gates"],
            "mixed_windows": result["mixed_windows"],
            "lemmas": len(result["candidate_lemmas"]),
            "prep_s": result["preparation_seconds"]}), flush=True)


if __name__ == "__main__":
    main()
