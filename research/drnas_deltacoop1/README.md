# DRNAS DELTA_COOP1 — marginal algebra to CDCL experiment

Status: research-only, 2026-11-14. Not a new P versus NP result, universal speed claim, or competition ranking. Experimental branch only; frozen X5, main and competitor sources are unchanged.

## Hypothesis

At a CDCL Boolean constraint propagation (BCP) fixpoint under partial trail alpha, exact bounded local algebra may infer novel unit or conflicting consequences which plain BCP does not see.

Define delta_candidates(alpha) as locally entailed, non-satisfied clauses which would be unit or conflicting at alpha. Count repeated *events*, not unique variables or dimension reduction.

A SHADOW candidate is mathematically entailed by its original-clause scope but has NOT been independently proof certified. Only ON may inject a clause after its bounded proof chain has been constructed. Independently verify every original-CNF UNSAT verdict.

## Design

- Generated from SHA-pinned COOP54B with drift checking and one new C++ executable.
- Same executable, three modes: --coop4 off / observe / gate. COOP5 probing is off for every arm.
- ON gate may activate from the first conflict window, but remains budget- and cooldown-limited.
- Distinct telemetry: potential unit/conflict events, injected proof clauses, direct forced literals, follow-on BCP forced literals, and safe same-level net assignments.
- The current mathematics is local exact CNF/Walsh affine reasoning. It is NOT yet incremental global GF(2) Gaussian elimination or novel generalized inference.

## Verification

- Exhaustive-oracle and mixed-XOR synthetic formulas, including parity combinations that logically imply a unit which baseline root BCP cannot find.
- Verify original SAT witnesses and original UNSAT DRAT using an independent checker.
- Retrospective SAT2024 REAL36, 36 SHA-verified originals, 2 repeats, 5 arms (OFF SHADOW ON Kissat CaDiCaL), 5 seconds per attempt, 360 attempts, one logical CPU per solver.
- Compare independently certified solved counts, verified-only PAR-2, per-family variability, OFF-to-SHADOW overhead, SHADOW-to-ON net effect.
- No champion promotion. Require a separate new, sealed, SHA-disjoint holdout before any broader speed claim.

Success target: 10 percent or better verified holdout PAR-2 improvement without false SAT or UNSAT, not assumed.
