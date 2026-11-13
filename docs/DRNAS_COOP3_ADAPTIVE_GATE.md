# DRNAS COOP3 — adaptive algebra gate (experiment)

## Why this experiment exists

In historical SAT Competition 2024 REAL36, COOP2_ON produced 960
source-certified algebraic lemmas and 128 altered branch choices, but
improved PAR2 by only 0.127% relative to its same-binary OFF control;
family-cluster 95% CI included zero, and both solved 24/72 trials.
This does not establish an overall benefit from unconditional algebra.

COOP3 tests **marginal novelty** before spending source-proof cost.
All changes live on the experimental branch only; frozen X5, main,
prior benchmarks, the global model database, and blind holdouts are unchanged.

## Formal decision criterion

At a CDCL unit-propagation fixpoint, given current partial assignment alpha,
take a candidate clause C entailed by an exact local Walsh/affine analysis
of a subset of the original CNF.

The gate accepts C for independent RUP-compatible certification only when:
  1. C is absent from the engine's known original/derived clauses;
  2. C is not already satisfied by alpha;
  3. at most ONE of C's literals remains unassigned under alpha;
  4. the local source-to-clause proof construction completes in budget.

Cases with zero unassigned literals give an immediate conflict; cases with
exactly one unassigned literal give an immediate propagation. Candidates
with two or more unassigned literals are deferred in GATE (the ALGEBRA arm
can still learn them). Therefore this is a *deliberately conservative*
immediate-consequence gate, not a generic learned quality predictor.
No inferred clause enters CDCL without the proof-producing step.

## Adaptive cooldown

No algebra analysis before 64 native CDCL conflicts. The baseline and
COOP3_OFF use the original branching/restart/conflict system. After an
unproductive gate pass, the next available attempt is delayed by a
geometrically increasing 128, 256, 512, 1024, up to 2048 conflicts.
After a pass that successfully certifies a new immediate consequence,
the quiet streak resets and the next gate opens after 64 conflicts.

Unchanged COOP2 bounds: max 4096 variables and 12000 original clauses,
64 local windows with at most 8 variables each, 24 passes, 256 learned
clauses, 8192 proof steps; local build clock 10 ms, pass 2.5 ms,
cumulative analysis 30 ms. These are cooperative checks, not hard
real-time preemption. One logical CPU per solver.

## Same-binary controls

- COOP3_OFF: existing CDCL without any algebra.
- COOP3_OBSERVE: local Walsh/affine observations without learned lemmas.
- COOP3_ALGEBRA: original unconditional certified short algebraic lemmas.
- COOP3_ON: ALGEBRA plus algebraic branching hints.
- COOP3_GATE: immediate-consequence filter + adaptive cooldown, NO branching hints.
- X5_FROZEN, Kissat, CaDiCaL: independent fixed baselines.

The five COOP3 modes are compiled from exactly the same source code and
executable, selected solely by runtime flag. No trained policy is loaded.

## Verification and success gates

Preflight: exhaustive small Boolean truth functions, random SAT/UNSAT
formula oracle checks, every emitted resolution/RUP proof step verified
independently; DRAT-Trim for UNSAT, original-CNF witness check for SAT.
In paired benchmark: every credited solution must be verified; a solve
must fall within the fixed wall cap; no contradictory certified results.

Retrospective real test: original SHA-frozen SAT2024 REAL36, 7 families,
36 unique CNFs, 2 repetitions, 5s cap, 8 arms = 576 attempts.
Report total verified PAR2, distinct solved cases, SAT/UNSAT, proof times,
max RSS, gate candidate/accepted/inactive counts, backoffs and family
bootstrap 95% CI. Report per-family rather than pooling incomparable
benchmarks as if they were fresh holdout.

Separate stress synthetic check: 42 original generated sources in 7
families, two repetitions, 1s cap, 6 arms = 504 attempts. It is useful
for mechanism discovery, NEVER evidence of superiority on unseen real SAT.

Do not promote automatically. To claim practical progress require a
fresh independently sealed family-disjoint holdout, verified PAR2
improvement with a positive confidence bound and no solved regressions.
