#!/usr/bin/env python3
"""TD2: sparse certified GF2, bounded preparation and original-solver pilot.

Development experiment on the exposed R199 sources. No formula ID, family,
expected answer or historical timing participates in routing. The original
R193 implementation remains the control. No partially certified output is used.
"""
from __future__ import annotations

import contextlib
import pathlib
import signal
import time

import r193_certified_gauss_cms as certified

PREP_CAP_S = 0.8
PILOT_CAP_S = 0.025


class PreparationExpired(TimeoutError):
    pass


@contextlib.contextmanager
def deadline(seconds):
    """Linux/main-thread deadline; restore any enclosing timer and handler."""
    previous_handler = signal.getsignal(signal.SIGALRM)
    previous_timer = signal.getitimer(signal.ITIMER_REAL)
    started = time.perf_counter()

    def expire(_signum, _frame):
        raise PreparationExpired("TD2 preparation budget")

    signal.signal(signal.SIGALRM, expire)
    limit = max(0.000001, seconds)
    if previous_timer[0] > 0:
        limit = min(limit, previous_timer[0])
    signal.setitimer(signal.ITIMER_REAL, limit)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
        remaining, interval = previous_timer
        if remaining > 0:
            remaining = max(0.000001, remaining - (time.perf_counter() - started))
        signal.setitimer(signal.ITIMER_REAL, remaining, interval)


def sparse_gaussian(rows):
    """Same echelon insertion; substitute only present lower pivot bits.

    When row h is reduced, every lower pivot row is already reduced. Subtracting
    such a row cannot introduce another pivot bit, so the pending bit set only
    shrinks. This computes the same reduced rows and original-source traces as
    R182's ascending-pivot dense pair scan.
    """
    gf = certified.gf_src.gf
    pivots = {}
    for i, (variables, rhs, _ids) in enumerate(rows):
        mask = sum(1 << (v - 1) for v in variables)
        trace = 1 << i
        while mask:
            bit = mask.bit_length() - 1
            if bit not in pivots:
                pivots[bit] = (mask, rhs, trace)
                break
            other, parity, parent = pivots[bit]
            mask ^= other
            rhs ^= parity
            trace ^= parent
        if not mask and rhs:
            gf.check_trace(rows, 0, 1, trace)
            return {"conflict": True, "conflict_trace": trace,
                    "units": {}, "rank": len(pivots)}
    pivot_mask = sum(1 << k for k in pivots)
    for high in sorted(pivots):
        mask, rhs, trace = pivots[high]
        pending = mask & pivot_mask & ((1 << high) - 1)
        while pending:
            bit_mask = pending & -pending
            low = bit_mask.bit_length() - 1
            other, parity, parent = pivots[low]
            mask ^= other
            rhs ^= parity
            trace ^= parent
            pending ^= bit_mask
        pivots[high] = (mask, rhs, trace)
    units = {}
    for mask, rhs, trace in pivots.values():
        if mask.bit_count() == 1:
            var = mask.bit_length()
            gf.check_trace(rows, mask, rhs, trace)
            certified.need(var not in units or units[var][0] == rhs,
                           "TD2 inconsistent derived units")
            units[var] = (rhs, trace)
    return {"conflict": False, "conflict_trace": None,
            "units": units, "rank": len(pivots)}


def preprocess(source, rep, shard, output_root, budget_s=PREP_CAP_S):
    """R193-equivalent extraction/derivation with sparse Gauss and a hard cap.

    Preserve all original clauses. Budget expiry discards every partial result
    and returns the untouched source, leaving the solve budget available.
    """
    source = pathlib.Path(source)
    root = pathlib.Path(output_root)
    gf, ext, deriv = certified.gf_src.gf, certified.gf_src.ext, certified.deriv
    begin = time.perf_counter()
    stats = {"xor_rows": 0, "covered_clauses": 0, "residual_clauses": 0,
             "gf2_units": 0, "added_total_clauses": 0,
             "source_GF2_contradiction": False, "preprocess_budget_exhausted": False,
             "preprocess_s": 0.0, "gaussian_s": 0.0,
             "augmented_sha256": None}
    out = root / "augmented" / f"shard-{shard}" / f"{source.stem}-{rep}.cnf"
    proof_path = root / "proofs" / f"shard-{shard}" / f"{source.stem}-{rep}.json"
    try:
        with deadline(budget_s):
            source_sha = certified.sha(source)
            n, clauses = gf.dimacs(source)
            rows, covered = ext.xor_source(clauses)
            stats.update(xor_rows=len(rows), covered_clauses=len(covered),
                         residual_clauses=len(clauses) - len(covered))
            if not rows or len(rows) > 3000:
                stats["gate_reason"] = "no_xor" if not rows else "gt_3000_rows"
                return source, stats, None
            phase = time.perf_counter()
            gauss = sparse_gaussian(rows)
            stats["gaussian_s"] = round(time.perf_counter() - phase, 6)
            if gauss["conflict"]:
                gf.check_trace(rows, 0, 1, gauss["conflict_trace"])
                certified.save(proof_path, {
                    "original_sha256": source_sha, "source_rows": rows,
                    "conflict_trace": gauss["conflict_trace"],
                    "source_trace_replayed": True})
                stats["source_GF2_contradiction"] = True
                stats["gate_reason"] = "source_contradiction_replayed"
                return source, stats, "UNSAT"
            units = []
            for var, (rhs, trace) in sorted(gauss["units"].items()):
                gf.check_trace(rows, 1 << (var - 1), rhs, trace)
                units.append(var if rhs else -var)
            extra, report, proof = deriv.prepare(clauses, rows, covered, "hybrid4")
            stats.update(gf2_units=len(units), derived_candidates=report["new_clauses"],
                         prep_pair_exams=report["xor_pair_examined"])
            if not units and not extra:
                stats["gate_reason"] = "no_certified_additions"
                return source, stats, None
            deriv.write_augmented(out, n, clauses, units, extra)
            count = certified.prefix_unchanged(out, n, clauses)
            certified.need(count == len(units) + len(extra), "TD2 count mismatch")
            augmented_sha = certified.sha(out)
            certified.save(proof_path, {
                "original_sha256": source_sha, "augmented_sha256": augmented_sha,
                "unit_literals": units, "unit_source_traces_replayed": True,
                "derived_clause_proofs": proof,
                "derived_resolution_traces_replayed": True})
            stats.update(added_total_clauses=count, augmented_sha256=augmented_sha,
                         gate_reason="certified_augmentation")
            return out, stats, None
    except PreparationExpired:
        out.unlink(missing_ok=True)
        proof_path.unlink(missing_ok=True)
        stats.update(preprocess_budget_exhausted=True, gf2_units=0,
                     added_total_clauses=0, augmented_sha256=None,
                     source_GF2_contradiction=False, gate_reason="budget_fallback_original")
        return source, stats, None
    finally:
        stats["preprocess_s"] = round(time.perf_counter() - begin, 6)
