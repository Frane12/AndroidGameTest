#!/usr/bin/env python3
"""DRNAS DMD2: bounded procedural algebra over the DMD1 native ANF primitive.

Experimental method, not a new complete solver. The only trusted facts injected
into a CNF are clauses independently verified as consequences of the original
clauses and previously certified lemmas. The unmodified original is retained.
"""
import argparse
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time

import dmd1_bench as d1

PROTO = "DRNAS-DMD2-PROCEDURAL-CHAIN-v1"
NATIVE = pathlib.Path("mre_dmd2/bin/dmd1_anf")


def check(cond, msg):
    if not cond:
        raise RuntimeError("DMD2_PROOF_REFUSED: " + msg)


def canonical(clause):
    s = set(clause)
    if any(-x in s for x in s):
        return None
    return tuple(sorted(s, key=lambda v: (abs(v), v < 0)))


def key(clause):
    return canonical(clause)


def serialize(path, n, clauses):
    with pathlib.Path(path).open("w") as out:
        out.write("p cnf %d %d\n" % (n, len(clauses)))
        for clause in clauses:
            out.write(" ".join(map(str, clause)) + " 0\n")


def hash_state(lemmas):
    parts = sorted([",".join(map(str, c)) for c in lemmas])
    return hashlib.sha256("|".join(parts).encode()).hexdigest()


def bcp(clauses, initial=()):
    """Exact Boolean unit-propagation on the SUPPLIED clauses, no SAT guesses."""
    assign = {}
    for lit in initial:
        v, val = abs(lit), lit > 0
        if v in assign and assign[v] != val:
            return assign, True
        assign[v] = val
    while True:
        changed = False
        for clause in clauses:
            sat, unknown, last = False, 0, None
            for lit in clause:
                value = assign.get(abs(lit))
                if value is None:
                    unknown += 1
                    last = lit
                elif value == (lit > 0):
                    sat = True
                    break
            if sat:
                continue
            if unknown == 0:
                return assign, True
            if unknown == 1:
                v, val = abs(last), last > 0
                if v in assign and assign[v] != val:
                    return assign, True
                if v not in assign:
                    assign[v] = val
                    changed = True
        if not changed:
            return assign, False


def rup(clauses, clause):
    """Independent RUP: F and negation of lemma must conflict by BCP."""
    _, conflict = bcp(clauses, (-x for x in clause))
    return conflict


def small_bcp_view(original, added):
    # Selection heuristic only: complete original SAT semantics always preserved.
    # A subset's implications remain sound, but this is NOT a full BCP snapshot.
    return [c for c in original[:1200] if len(c) <= 6] + list(added)


def feedback(original, before, after):
    lhs, lb = bcp(small_bcp_view(original, before))
    rhs, rb = bcp(small_bcp_view(original, after))
    new_units = sum(v not in lhs for v in rhs)
    return dict(
        bcp_units_before=len(lhs), bcp_units_after=len(rhs),
        bcp_new_units=new_units,
        bcp_new_conflict=bool(rb and not lb),
        selection_view_only=True
    )


def choose_lemmas(proposals, known, maximum=12):
    """Rank legal discoveries by shortness; retain neutral steps for chaining."""
    fresh = {}
    for p in proposals:
        c = key(p["clause"])
        if c is None or c in known or len(c) > 3:
            continue
        fresh.setdefault(c, dict(clause=list(c), source_ids=p["source_ids"]))
    ordered = sorted(fresh.values(), key=lambda x: (
        len(x["clause"]),
        len(x["source_ids"]),
        tuple(x["clause"])
    ))
    return ordered[:maximum]


def shorten_by_proved_units(original, added, maximum=6):
    """Conditionally simplify clauses; independently RUP-check every result."""
    view = small_bcp_view(original, added)
    assigned, conflict = bcp(view)
    if conflict:
        return []
    known = {key(c) for c in original}
    known.update(key(c) for c in added)
    out = []
    for c in original[:1200]:
        if not 2 <= len(c) <= 5:
            continue
        if any(abs(l) in assigned and assigned[abs(l)] == (l > 0) for l in c):
            continue
        shortened = [l for l in c if abs(l) not in assigned]
        if len(shortened) >= len(c) or len(shortened) > 2:
            continue
        norm = key(shortened)
        if norm is None or norm in known:
            continue
        check(rup(view, norm), "shortened clause lacks RUP proof")
        out.append(tuple(norm))
        known.add(norm)
        if len(out) >= maximum:
            break
    return out


def discover(original_path, augmented_path, chain_path, max_ms=60, max_steps=3):
    check(5 <= max_ms <= 2000 and 1 <= max_steps <= 5, "invalid budgets")
    start = time.monotonic()
    n, original = d1.read_cnf(original_path)
    original_sha = d1.sha(original_path)
    all_known = set(key(c) for c in original)
    added = []
    frontier = []
    visited = {hash_state(added)}
    stages = []
    total_local_relations = 0
    cycles_pruned = 0
    total_candidates = 0
    total_verified = 0
    total_shortened = 0

    # Proof chain may use a lemma from an earlier, already independently
    # certified stage as a premise. Stage-level proof replay validates this.
    with tempfile.TemporaryDirectory(prefix="dmd2-procedural-") as td:
        tmp = pathlib.Path(td)
        for step in range(max_steps):
            elapsed_ms = (time.monotonic() - start) * 1000
            if elapsed_ms >= max_ms:
                break
            # Put the most recently proved facts at the front to let native
            # local ANF bags combine them with other clauses in the next cycle.
            seen = set()
            reordered = []
            for clause in list(frontier) + list(added) + list(original):
                c = key(clause)
                if c is None or c in seen:
                    continue
                seen.add(c)
                reordered.append(clause)
            stage_input = tmp / ("input-%d.cnf" % step)
            stage_aug = tmp / ("aug-%d.cnf" % step)
            stage_proof = tmp / ("proof-%d.json" % step)
            serialize(stage_input, n, reordered)
            remaining = max(1, int(max_ms - (time.monotonic()-start)*1000))
            stage_budget = min(remaining, 22)
            call_start = time.monotonic()
            p = subprocess.run([
                str(NATIVE), str(stage_input), str(stage_aug),
                str(stage_proof), str(stage_budget), "36"
            ], text=True, capture_output=True)
            check(p.returncode == 0 and stage_proof.is_file(),
                  "native ANF step failed: " + p.stderr[-400:])
            proof = json.loads(stage_proof.read_text())
            d1.proof_replay(stage_input, stage_aug, proof)
            new_proposals = choose_lemmas(proof["lemmas"], all_known)
            total_local_relations += proof["nonlinear_relations"]
            total_candidates += len(proof["lemmas"])
            selected = []
            for proposal in new_proposals:
                norm = key(proposal["clause"])
                if norm not in all_known:
                    selected.append(norm)
                    all_known.add(norm)
            # The second legal operator is conditional clause shortening under
            # globally true root units. Every such lemma receives RUP replay.
            shortcuts = shorten_by_proved_units(original, added + selected)
            for c in shortcuts:
                if c not in all_known:
                    selected.append(c)
                    all_known.add(c)
                    total_shortened += 1
            next_added = added + selected
            state = hash_state(next_added)
            if state in visited:
                cycles_pruned += 1
                break
            visited.add(state)
            f = feedback(original, added, next_added)
            cost_ms = (time.monotonic() - call_start)*1000
            # Heuristic progress, NOT a mathematical distance to a solution.
            reward = 8*f["bcp_new_units"] + 15*int(f["bcp_new_conflict"]) + (
                sum(4 if len(c) == 1 else 2 if len(c) == 2 else 1 for c in selected)
            ) - .08*cost_ms
            stages.append(dict(step=step, operation="ANF_then_verified_substitution",
                input_sha256=d1.sha(stage_input),
                local_exhaustive_proof=True, rup_shortening_checks=len(shortcuts),
                candidate_lemmas=len(proof["lemmas"]),
                new_lemmas=len(selected), new_short_clauses=sum(len(c)<=2 for c in selected),
                nonlinear_relations=proof["nonlinear_relations"],
                certificate_groups=proof["groups"],
                cost_ms=round(cost_ms,4), feedback_reward=round(reward,4),
                **f))
            total_verified += len(selected)
            added = next_added
            frontier = selected
            # Stop on zero novelty, but permit valid neutral discoveries to be
            # combined in the next cycle (lookahead depth <= max_steps).
            if not selected or f["bcp_new_conflict"]:
                break
        # NEVER replace original clauses. Only append certified consequences.
        if added:
            serialize(augmented_path, n, list(original) + list(added))
            nn, result = d1.read_cnf(augmented_path)
            check(nn == n and result == list(original) + list(added),
                  "original CNF or appended lemmas corrupted")
        elif pathlib.Path(augmented_path).exists():
            pathlib.Path(augmented_path).unlink()

    result = dict(protocol=PROTO, original_sha256=original_sha,
        original_clauses=len(original), appended_lemmas=len(added),
        short_lemmas=sum(len(c)<=2 for c in added),
        max_steps=max_steps, budget_ms=max_ms, steps_executed=len(stages),
        steps=stages, cycles_pruned=cycles_pruned,
        candidates=total_candidates, verified_new_lemmas=total_verified,
        nonlinear_relations=total_local_relations,
        rup_shortening=total_shortened, state_hash=hash_state(added),
        elapsed_ms=round((time.monotonic()-start)*1000,4),
        all_step_proofs_independently_replayed=True,
        no_independent_unsat_lrat=True,
        fallback=(not bool(added)))
    pathlib.Path(chain_path).write_text(json.dumps(result, sort_keys=True) + "\n")
    print("DMD2_CHAIN", json.dumps(result, sort_keys=True), flush=True)
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("original")
    ap.add_argument("augmented")
    ap.add_argument("chain")
    ap.add_argument("--max-ms", type=int, default=60)
    ap.add_argument("--max-steps", type=int, default=3)
    args = ap.parse_args()
    try:
        discover(args.original, args.augmented, args.chain, args.max_ms, args.max_steps)
    except Exception as exc:
        print("DMD2_ERROR", str(exc), file=sys.stderr, flush=True)
        sys.exit(1)
