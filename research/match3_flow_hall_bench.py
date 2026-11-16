#!/usr/bin/env python3
"""Deterministic MATCH3 source-CNF pilot, independent verification and guards."""
import copy
import hashlib
import itertools
import json
import os
import random
from pathlib import Path
from match3_flow_hall import prove, parse
from match3_flow_hall_checker import verify
from match2 import prove as old_match2

OUT = Path("results/match3_flow_hall")
RNG = random.Random(20261116)
ROWS = []

def dimacs(nv, clauses, name):
    return (f"c {name}: generated original-CNF source\np cnf {nv} {len(clauses)}\n"
            + "".join(" ".join(map(str, c)) + " 0\n" for c in clauses)).encode("ascii")

def encode(choices, caps, name, amo=False, renumber=False):
    n = len(choices)
    m = len(caps)
    assert all(2 <= len(set(rs)) <= 16 for rs in choices)
    assert all(0 <= r < m for rs in choices for r in rs)
    variable = {(j, r): k + 1 for k, (j, rs) in enumerate(choices)
                for r in sorted(set(rs))}
    clauses = [tuple(variable[j, r] for r in sorted(set(rs))) for j, rs in enumerate(choices)]
    if amo:
        for j, rs in enumerate(choices):
            for a, b in itertools.combinations(sorted(set(rs)), 2):
                clauses.append((-variable[j, a], -variable[j, b]))
    for r, cap in enumerate(caps):
        eligible = [variable[j, r] for j, rs in enumerate(choices) if r in rs]
        if cap < len(eligible):
            for combo in itertools.combinations(eligible, cap + 1):
                clauses.append(tuple(-x for x in combo))
    nv = len(variable)
    if renumber:
        perm = list(range(1, nv + 1))
        RNG.shuffle(perm)
        clauses = [tuple(perm[abs(x) - 1] * (1 if x > 0 else -1) for x in c)
                   for c in clauses]
        variable = {key: perm[v-1] for key, v in variable.items()}
        RNG.shuffle(clauses)
    return dimacs(nv, clauses, name), variable

def model_satisfies(raw, chosen, variables):
    nv, clauses = parse(raw)
    positive = {variables[j, r] for j, r in enumerate(chosen)}
    assert all((j, r) in variables for j, r in enumerate(chosen))
    assert max(positive) <= nv
    return all(any((x > 0 and x in positive) or (x < 0 and -x not in positive)
                   for x in c) for c in clauses)

def exact_dpll(raw):
    nv, clauses = parse(raw)
    if nv > 18:
        return None
    def dfs(a):
        while True:
            unit = None
            remaining = []
            for c in clauses:
                if any(abs(x) in a and a[abs(x)] == (x > 0) for x in c):
                    continue
                unassigned = [x for x in c if abs(x) not in a]
                if not unassigned:
                    return False
                if len(unassigned) == 1:
                    unit = unassigned[0]
                    break
                remaining.append(unassigned)
            if unit is None:
                if not remaining:
                    return True
                break
            a = dict(a)
            a[abs(unit)] = unit > 0
        v = abs(remaining[0][0])
        return dfs(dict(a, **{str(v): True})) if False else branch(a, v)
    def branch(a, v):
        left = a.copy()
        left[v] = True
        if dfs(left):
            return True
        right = a.copy()
        right[v] = False
        return dfs(right)
    return "SAT" if dfs({}) else "UNSAT"

def check_case(name, raw, expected, model=None, variables=None, required=False):
    proof = prove(raw)
    found = proof["status"] == "UNSAT_UNCHECKED"
    if required and not found:
        raise AssertionError(f"undetected expected Hall witness: {name}, {proof}")
    if expected == "SAT" and found:
        raise AssertionError("false UNSAT " + name)
    certified = None
    if found:
        certified = verify(raw, proof)
        assert certified["status"] == "MATCH3_SOURCE_HALL_UNSAT_VERIFIED"
    if model is not None:
        assert model_satisfies(raw, model, variables), "invalid SAT model " + name
    oracle = exact_dpll(raw)
    if oracle is not None and oracle != expected:
        raise AssertionError(f"wrong fixture truth {name}: {oracle} != {expected}")
    old = old_match2(raw)
    old_found = old["status"] == "UNSAT_UNCHECKED"
    if old_found and expected == "SAT":
        raise AssertionError("old baseline false UNSAT")
    (OUT / "cnf").mkdir(parents=True, exist_ok=True)
    (OUT / "proofs").mkdir(parents=True, exist_ok=True)
    (OUT / "cnf" / (name + ".cnf")).write_bytes(raw)
    (OUT / "proofs" / (name + ".json")).write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
    ROWS.append({"name": name, "expected": expected, "match3": "VERIFIED_UNSAT" if certified else "UNKNOWN",
                 "match2": "UNSAT_UNCHECKED" if old_found else "UNKNOWN",
                 "jobs": proof.get("jobs"), "resources": proof.get("resource_count"),
                 "maxflow": proof.get("maxflow"), "hall_deficiency": proof.get("deficiency"),
                 "cnf_sha256": hashlib.sha256(raw).hexdigest(),
                 "nvars": parse(raw)[0], "nclauses": len(parse(raw)[1]),
                 "independent_source_verified": bool(certified),
                 "small_oracle": oracle, "sat_model_checked": bool(model is not None)})
    return proof

def run():
    OUT.mkdir(parents=True, exist_ok=True)
    # Small exact-oracle controls (including an actual SAT after one clause removal).
    for n, m, label in [(3, 2, "UNSAT"), (2, 2, "SAT"), (4, 3, "UNSAT"),
                         (3, 3, "SAT")]:
        choices = [list(range(m)) for _ in range(n)]
        raw, variables = encode(choices, [1] * m, f"small_{n}_{m}", amo=True)
        model = list(range(n)) if label == "SAT" else None
        check_case(f"small_{n}_{m}", raw, label, model, variables, required=(label=="UNSAT"))
    # Break a single source mutex: the former overload now has an exact SAT assignment.
    raw, variables = encode([[0,1]] * 3, [1,1], "weakened_sat")
    nv, cls = parse(raw)
    cls.remove((-variables[0,0], -variables[1,0]))
    weak = dimacs(nv, cls, "weakened_sat")
    check_case("weakened_sat", weak, "SAT", [0,0,1], variables)
    # Larger all-neighbor and proper-subset Hall cuts, beyond MATCH2's n<=18 cutoff.
    for n, m in [(31,8), (45,12), (65,12)]:
        raw, v = encode([list(range(m)) for _ in range(n)], [1]*m,
                        f"php_{n}_{m}", renumber=(n == 45))
        check_case(f"php_{n}_{m}", raw, "UNSAT", required=True)
    choices = [list(range(5)) for _ in range(10)]
    choices += [[5+(j+t)%25 for t in range(4)] for j in range(20)]
    raw, _ = encode(choices, [1]*30, "subset_30_30", renumber=True)
    check_case("subset_30_30", raw, "UNSAT", required=True)
    # Capacity two is justified by ORIGINAL negative triples, not source comments.
    for n, m, cap in [(7,3,2), (24,11,2)]:
        raw, _ = encode([list(range(m)) for _ in range(n)], [cap]*m, f"capacity_{n}_{m}")
        check_case(f"capacity_{n}_{m}", raw, "UNSAT", required=True)
    for n, m in [(14,16), (28,30), (38,42)]:
        choices = [[j, (j+1)%m, (j+2)%m] for j in range(n)]
        raw, variables = encode(choices, [1]*m, f"sat_{n}_{m}", renumber=(n==28))
        check_case(f"sat_{n}_{m}", raw, "SAT", list(range(n)), variables)
    # Random restricted neighborhoods: deterministic frozen generated instances.
    for k in range(10):
        jobs = RNG.randint(21, 34)
        resources = RNG.randint(5, 10)
        choices = [sorted(RNG.sample(range(resources), RNG.randint(2, min(6, resources))))
                   for _ in range(jobs)]
        raw, _ = encode(choices, [1]*resources, f"random_unsat_{k}")
        check_case(f"random_unsat_{k}", raw, "UNSAT", required=True)
    # Historical original weighted PCMAX: no invented theorem or success claim.
    from ipg1_fixtures import petersen
    check_case("petersen_original_45_300", petersen().encode("ascii"), "UNSAT")
    # Independently checked mutations of a previously certified source proof.
    original = (OUT/"cnf"/"php_31_8.cnf").read_bytes()
    valid = json.loads((OUT/"proofs"/"php_31_8.json").read_text())
    candidates = []
    bad = copy.deepcopy(valid); bad["source_sha256"] = "0"*64; candidates.append(bad)
    bad = copy.deepcopy(valid); bad["hall_jobs"] = [0]; candidates.append(bad)
    bad = copy.deepcopy(valid); bad["capacity_bound"] = -1; candidates.append(bad)
    bad = copy.deepcopy(valid); bad["capacities"][0] = 0; candidates.append(bad)
    bad = copy.deepcopy(valid); bad["resources"][0].pop(); candidates.append(bad)
    bad = copy.deepcopy(valid); bad["groups"][0][0] = 100000; candidates.append(bad)
    bad = copy.deepcopy(valid); bad["status"] = "SAT"; candidates.append(bad)
    rejected = 0
    for bad in candidates:
        try:
            verify(original, bad)
        except (ValueError, TypeError, KeyError, OverflowError, IndexError):
            rejected += 1
        else:
            raise AssertionError("forged witness accepted")
    try:
        verify(original + b"c mutated source\n", valid)
    except ValueError:
        rejected += 1
    else:
        raise AssertionError("source-mutated certificate accepted")
    summary = {
        "status": "PASS", "cases": len(ROWS),
        "match3_verified_unsat": sum(x["independent_source_verified"] for x in ROWS),
        "old_match2_produced_unsat": sum(x["match2"] == "UNSAT_UNCHECKED" for x in ROWS),
        "new_cases_over_old": sum(x["independent_source_verified"] and x["match2"] == "UNKNOWN" for x in ROWS),
        "sat_controls": sum(x["expected"] == "SAT" for x in ROWS),
        "sat_models_checked": sum(x["sat_model_checked"] for x in ROWS),
        "exact_small_oracles": sum(x["small_oracle"] is not None for x in ROWS),
        "false_unsat": sum(x["expected"] == "SAT" and x["independent_source_verified"] for x in ROWS),
        "forged_proofs_rejected": rejected,
        "petersen_status": next(x["match3"] for x in ROWS if x["name"] == "petersen_original_45_300"),
        "scope": "retrospective generated original-CNF; polynomial flow on verified direct capacities; NOT blind, not DRAT/LRAT/VeriPB, not native production or PAR2"
    }
    assert summary["false_unsat"] == 0 and rejected == len(candidates)+1
    (OUT/"summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True)+"\n")
    (OUT/"trials.json").write_text(json.dumps(ROWS, indent=2, sort_keys=True)+"\n")
    print("MATCH3_FLOW_FINAL " + json.dumps(summary, sort_keys=True), flush=True)

if __name__ == "__main__":
    if hasattr(os, "sched_setaffinity"):
        os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    run()
