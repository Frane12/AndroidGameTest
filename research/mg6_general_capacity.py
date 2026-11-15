#!/usr/bin/env python3
"""MG6 experimental generic CNF clique-cover capacity proof producer.

Select disjoint positive ALO clauses from the original CNF, partition their
selectors into pairwise negative-clause cliques, and derive a contradiction
using only original source clause IDs and VeriPB 3 cutting planes. This is an
incomplete detector. Its emitted output is NEVER an UNSAT verdict until a
separate verifier accepts the original CNF plus the proof.
"""
import argparse
import hashlib
import itertools
import json
import pathlib
import sys
import time


def read_cnf(path):
    raw = pathlib.Path(path).read_bytes()
    nvars = nclauses = None
    clauses, partial = [], []
    for line in raw.decode("ascii").splitlines():
        terms = line.strip().split()
        if not terms or terms[0] == "c":
            continue
        if terms[0] == "p":
            if nvars is not None or len(terms) != 4 or terms[1] != "cnf":
                raise ValueError("bad DIMACS header")
            nvars, nclauses = int(terms[2]), int(terms[3])
            continue
        if nvars is None:
            raise ValueError("missing DIMACS header")
        for tok in terms:
            v = int(tok)
            if abs(v) > nvars:
                raise ValueError("out-of-range literal")
            if v:
                partial.append(v)
            else:
                clauses.append(tuple(partial))
                partial = []
    if nvars is None or partial or len(clauses) != nclauses:
        raise ValueError("invalid DIMACS source")
    return raw, clauses


def discover(clauses, max_groups=48, max_lits=256):
    ids = {}
    for i, clause in enumerate(clauses, 1):
        ids.setdefault(frozenset(clause), i)
    candidates, seen = [], set()
    for clause in clauses:
        if not 2 <= len(clause) <= 8 or any(v <= 0 for v in clause):
            continue
        if len(set(clause)) != len(clause):
            continue
        key = frozenset(clause)
        if key not in seen:
            seen.add(key)
            candidates.append(tuple(clause))
    mutex = {
        frozenset((-c[0], -c[1]))
        for c in clauses
        if len(c) == 2 and c[0] < 0 and c[1] < 0 and c[0] != c[1]
    }
    for width in sorted({len(g) for g in candidates}):
        options = [g for g in candidates if len(g) == width]
        for begin in range(min(12, len(options))):
            groups, selected = [], set()
            for group in options[begin:] + options[:begin]:
                if len(groups) >= max_groups:
                    break
                if selected.isdisjoint(group) and len(selected) + len(group) <= max_lits:
                    groups.append(group)
                    selected.update(group)
            if len(groups) < 3:
                continue
            cliques = []
            for group in groups:
                for v in group:
                    fits = [
                        i for i, cl in enumerate(cliques)
                        if all(frozenset((v, u)) in mutex for u in cl)
                    ]
                    if fits:
                        dest = max(fits, key=lambda i: (len(cliques[i]), -i))
                        cliques[dest].append(v)
                    else:
                        cliques.append([v])
            if len(cliques) >= len(groups):
                continue
            # Check all premises against original clause IDs, not inferred structure.
            assert len(selected) == sum(map(len, groups)) == sum(map(len, cliques))
            assert all(frozenset(g) in ids for g in groups)
            assert all(
                frozenset((-a, -b)) in ids
                for clique in cliques
                for a, b in itertools.combinations(clique, 2)
            )
            return groups, cliques, ids
    return None


def emit(path, nclauses, groups, cliques, ids):
    last = nclauses
    steps = 0
    with pathlib.Path(path).open("w") as f:
        f.write("pseudo-Boolean proof version 3.0\n")
        f.write(f"f {nclauses} ;\n")
        bounds = []
        for clique in cliques:
            if len(clique) == 1:
                continue
            prev = ids[frozenset((-clique[0], -clique[1]))]
            for j in range(2, len(clique)):
                pairs = [
                    ids[frozenset((-v, -clique[j]))] for v in clique[:j]
                ]
                tokens = [str(pairs[0])]
                for pid in pairs[1:]:
                    tokens.extend((str(pid), "+"))
                tokens.append(str(prev))
                if j - 1 > 1:
                    tokens.extend((str(j - 1), "*"))
                tokens.extend(("+", str(j), "d"))
                f.write("pol " + " ".join(tokens) + " ;\n")
                last += 1
                steps += 1
                prev = last
            bounds.append(prev)
        all_ids = [ids[frozenset(group)] for group in groups] + bounds
        tokens = [str(all_ids[0])]
        for ident in all_ids[1:]:
            tokens.extend((str(ident), "+"))
        f.write("pol " + " ".join(tokens) + " ;\n")
        f.write("output NONE ;\nconclusion UNSAT ;\nend pseudo-Boolean proof ;\n")
        steps += 1
    return steps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cnf", required=True)
    ap.add_argument("--proof", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args()
    start = time.monotonic()
    raw, clauses = read_cnf(args.cnf)
    found = discover(clauses)
    report = {
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "source_clauses": len(clauses),
        "verifier_status": "NOT_RUN",
        "status": "UNKNOWN",
    }
    if found:
        groups, cliques, ids = found
        steps = emit(args.proof, len(clauses), groups, cliques, ids)
        report.update(
            status="PROOF_EMITTED_UNCHECKED",
            groups=len(groups),
            cliques=len(cliques),
            selectors=sum(map(len, groups)),
            proof_steps=steps,
            group_clauses=[ids[frozenset(g)] for g in groups],
            max_clique=max(map(len, cliques)),
        )
    report["producer_s"] = round(time.monotonic() - start, 6)
    pathlib.Path(args.report).write_text(json.dumps(report, sort_keys=True, indent=2) + "\n")
    print("MG6_RESULT " + json.dumps(report, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
