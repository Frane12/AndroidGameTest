#!/usr/bin/env python3
"""R92 bounded XOR<->CNF preprocessing pilot; NOT live in-process Kissat exchange.

Source clauses establish exact 3-XOR equations. Every injected clause is
independently reconstructed from immutable source equations and RUP-checked
CNF unit assignments. Never admit unverifiable clauses; never claim UNSAT.
"""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "experiments" / "drnas_v16"))
import r88_cooperative as r88

PROTO = "R92-VERIFIED-TWO-WAY-PREPASS-v1"

def xor_sources(clauses):
    """A complete four-clause parity signature implies one immutable 3-XOR."""
    sets = collections.defaultdict(set)
    for clause in clauses:
        if len(clause) != 3 or len({abs(x) for x in clause}) != 3:
            continue
        vars_ = tuple(sorted(abs(x) for x in clause))
        sign = sum(1 << i for i, x in enumerate(vars_) if -x in clause)
        sets[vars_].add(sign)
    equations = []
    even = {0, 3, 5, 6}
    odd = {1, 2, 4, 7}
    for variables, signs in sorted(sets.items()):
        for forbidden, rhs in ((even, 1), (odd, 0)):
            if forbidden.issubset(signs):
                mask = sum(1 << (v - 1) for v in variables)
                equations.append((mask, rhs, variables))
    return equations

def cnf_bcp(clauses, max_sweeps=24):
    """Only root-level CNF implications; return None on a detected conflict."""
    assigned = {}
    for _ in range(max_sweeps):
        changed = False
        for clause in clauses:
            remaining = []
            satisfied = False
            for lit in clause:
                if abs(lit) not in assigned:
                    remaining.append(lit)
                elif assigned[abs(lit)] == (lit > 0):
                    satisfied = True
                    break
            if satisfied:
                continue
            if not remaining:
                return None
            if len(remaining) == 1:
                lit = remaining[0]
                val = lit > 0
                prior = assigned.get(abs(lit))
                if prior is not None and prior != val:
                    return None
                if prior is None:
                    assigned[abs(lit)] = val
                    changed = True
        if not changed:
            break
    return assigned

def row_xor(a, b):
    return (a[0] ^ b[0], a[1] ^ b[1],
            a[2].symmetric_difference(b[2]),
            a[3].symmetric_difference(b[3]))

def echelon(original_rows, assigned):
    """Lowest-bit pivots make repeated lower-variable supports cancel."""
    rows = [(mask, rhs, frozenset((i,)), frozenset())
            for i, (mask, rhs, _vars) in enumerate(original_rows)]
    for var, truth in sorted(assigned.items()):
        rows.append((1 << (var-1), int(truth), frozenset(),
                     frozenset(((var, int(truth)),))))
    pivots = {}
    for row in rows:
        while row[0]:
            pivot = row[0] & -row[0]
            if pivot not in pivots:
                pivots[pivot] = row
                break
            row = row_xor(row, pivots[pivot])
    return list(pivots.values())

def row_clauses(mask, rhs):
    vars_ = [i+1 for i in range(mask.bit_length()) if mask & (1 << i)]
    if len(vars_) == 1:
        return [(vars_[0] if rhs else -vars_[0],)]
    if len(vars_) == 2:
        a, b = vars_
        return [(a, b), (-a, -b)] if rhs else [(-a, b), (a, -b)]
    return []

def independently_certify(row, original, source_equations, earlier):
    """Replay the entire claimed row; don't trust its pivot or cached flags."""
    mask, rhs, originals, units = row
    fresh = xor_sources(original)
    got_mask = got_rhs = 0
    for idx in sorted(originals):
        if not isinstance(idx, int) or idx < 0 or idx >= len(fresh):
            return False
        x, bit, _ = fresh[idx]
        got_mask ^= x
        got_rhs ^= bit
    # Unit premises are only admitted with a source + previously proved RUP.
    for var, truth in sorted(units):
        lit = var if truth else -var
        if not r88.bcp_conflict(original + earlier, [-lit]):
            return False
        got_mask ^= 1 << (var-1)
        got_rhs ^= truth
    return (got_mask, got_rhs) == (mask, rhs) and bool(row_clauses(mask, rhs))

def bridge(clauses, budget_s=0.12, max_xor=400, max_additions=100, rounds=3):
    """Proof-carrying two-direction preprocessing; safe no-op on any uncertainty."""
    start = time.monotonic()
    diag = dict(protocol=PROTO, xor_equations=0, bcp_units=0, verified=0,
                rejected=0, rounds=0, reason="no_xor", active_exchange=False)
    original = xor_sources(clauses)
    diag["xor_equations"] = len(original)
    if not original or len(original) > max_xor or budget_s <= 0:
        diag["reason"] = "no_xor_or_limit"
        return [], diag
    added = []
    existing = set(tuple(x) for x in clauses)
    accepted = set()
    for iteration in range(rounds):
        if time.monotonic() - start >= budget_s:
            diag["reason"] = "budget"
            break
        units = cnf_bcp(clauses + added)
        if units is None:
            diag["reason"] = "cnf_conflict_fallback"
            break
        diag["bcp_units"] = max(diag["bcp_units"], len(units))
        # CNF -> XOR: only root-level BCP units with checkable RUP derivations.
        new = 0
        for row in echelon(original, units):
            if time.monotonic() - start >= budget_s:
                diag["reason"] = "budget"
                break
            proposals = row_clauses(row[0], row[1])
            if not proposals:
                continue
            proposals = [tuple(x) for x in proposals
                         if tuple(x) not in existing and tuple(x) not in accepted]
            if not proposals:
                continue
            if not independently_certify(row, clauses, original, added):
                diag["rejected"] += len(proposals)
                continue
            # XOR -> CNF: each proposal is implied by the replayed parity row.
            if len(added) + len(proposals) > max_additions:
                diag["reason"] = "addition_limit"
                break
            for clause in proposals:
                accepted.add(clause)
                added.append(clause)
                new += 1
            diag["verified"] += len(proposals)
        diag["rounds"] = iteration + 1
        if not new:
            break
    diag["active_exchange"] = bool(added)
    if diag["reason"] == "no_xor":
        diag["reason"] = "complete"
    diag["preparation_s"] = round(time.monotonic()-start, 7)
    return added, diag

def selftest():
    # Two independent 3-XOR equations: (x^y^z=0) ^ (x^y^w=0) -> z^w=0.
    clauses = []
    for vars_ in ((1,2,3),(1,2,4)):
        for sign in (1,2,4,7):  # odd forbidden assignments -> XOR RHS 0
            clauses.append(tuple(-v if sign & (1<<i) else v
                                 for i, v in enumerate(vars_)))
    rows = xor_sources(clauses)
    assert len(rows) == 2 and all(eq[1] == 0 for eq in rows)
    learned, info = bridge(clauses, 2.0)
    assert (-3,4) in learned and (3,-4) in learned, (learned, info)
    assert info["verified"] >= 2 and info["active_exchange"]
    # Prevent arbitrary unproved pivot/row injection.
    fake = (1 << 483, 1, frozenset((484,)), frozenset())
    assert not independently_certify(fake, clauses, rows, [])
    fake2 = (1 << 490, 1, frozenset((491,)), frozenset())
    assert not independently_certify(fake2, clauses, rows, [])
    assert not independently_certify((1<<4, 1, frozenset((0,)), frozenset()),
                                     clauses, rows, [])
    # Truth-table prove equisatisfiability, including all partial settings.
    for bits in range(16):
        val = lambda l: bool(bits & (1 << (abs(l)-1))) == (l > 0)
        if all(any(val(l) for l in c) for c in clauses):
            assert all(any(val(l) for l in c) for c in learned)
    assert bridge([(1,2,3)], 2.0)[0] == []
    assert bridge(clauses, 0.0)[0] == []
    print("R92_SELFTEST_PASS", json.dumps(info, sort_keys=True))

def main():
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=("selftest","inspect"))
    p.add_argument("--cnf")
    p.add_argument("--out", default="r92-diagnostic.json")
    p.add_argument("--augmented")
    p.add_argument("--budget", type=float, default=0.12)
    a = p.parse_args()
    if a.command == "selftest":
        selftest()
        return
    if a.cnf is None or not 0 <= a.budget <= 2:
        p.error("--cnf and 0<=--budget<=2 required")
    source = Path(a.cnf)
    n, clauses = r88.read_cnf(source)
    extras, diag = bridge(clauses, a.budget)
    diag["source_sha256"] = r88.sha(source)
    diag["base_clauses"] = len(clauses)
    diag["added_clauses"] = len(extras)
    if a.augmented:
        r88.write_augmented(n, clauses, extras, Path(a.augmented))
    Path(a.out).write_text(json.dumps(diag, indent=2)+"\n")
    print("R92_PROOF_BRIDGE_PASS", json.dumps(diag, sort_keys=True))

if __name__ == "__main__":
    main()
