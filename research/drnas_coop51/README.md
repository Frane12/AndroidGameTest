# DRNAS COOP5.1 — exploratory hybrid BCP probe gate

## Purpose

The earlier COOP5 FIXED gate resolved a particular original SAT2024 scheduling
formula in two repetitions where dynamic/ungated CDCL timed out; the same FIXED
gate regressed on several synthetic stress formulas. COOP5.1 attempts a
budgeted compromise without altering logical correctness.

The experiment is **development/retrospective only**, not a fresh blind
holdout. It does not modify `main`, frozen X5, training/memory data,
clause proof generation, conflict learning, watched literals or restart policy.

## Three separately compiled executables

- `build/drnas-coop5-fixed`: SHA256
  `4dc87df8c3dff7dee877563357117e9b21f3b9b4d9748bfdd569b005f9d8c8d5`;
  320 inspections per speculative branch, 24-decision minimum spacing,
  25 ms **total** probe wall budget per formula.
- `build/drnas-coop5-dynamic`: SHA256
  `d2a584b8a5f015e36469a015e057b2223b88c7bee040d629c0f84d150b628a44`;
  initial 96 inspections, 64-decision spacing, adaptive depth/cadence,
  budget min(25 ms, max(1 ms, 0.5% solver cap)).
- `build/drnas-coop51-hybrid`: new binary from identical frozen X5 source.
  Starting at 64 native CDCL conflicts, first eligible gate invocation is
  deep (320 inspections/branch); the next three use 96 inspections, and
  every fourth is deep again. Initial minimum spacing is 24 decisions.
  The spacing adapts (24..128 decisions): after credible proxy wins it
  shortens, after consecutive weak probes or disappointing actual
  propagation it backs off. Total probe budget is inherited from dynamic
  (25 ms at 5 s solver cap, 15 ms at a 3 s cap, 5 ms at 1 s).
  This budget is **cumulative** and checked between probe pairs, so
  a final pair may slightly exceed it. A single pair consists of exactly
  two bounded and fully rolled-back BCP attempts at VSIDS and algebra
  candidate variables, using their current phases.

For SHADOW: simulate and score but never override VSIDS. For ON: override
only when candidate wins a bounded BCP proxy by a nontrivial margin.
Every candidate remains just a heuristic branch decision; no speculative
SAT/UNSAT conclusion is committed, nor any RUP/DRAT proof modified.

## Data and verification

Preflight compile: `-std=c++20 -O3 -DNDEBUG -Wall -Wextra -Wpedantic -Werror`.

Preflight source safety: all 256 Boolean 3-bit functions plus random
small CNFs and affine/nonlinear stress, original-witness SAT check,
RUP step verification and independent DRAT-trim for UNSAT;
313 sources × 4 hybrid modes (OFF, ALGEBRA, SHADOW, ON) = 1,252 verified
attempts.

Benchmark:
- synthetic: seven families ×3 cases each, 21 distinct cases,
  2 repeats ×7 arms = 294 attempts, 1 s cap.
- real retrospective: 18 SAT2024 original CNFs satisfying the
  frozen algebra input-size gate, 2 repeats ×7 arms = 252 attempts,
  3 s cap; all CNF SHA-256 compared to the original source manifest.
- Exact arms: frozen X5, plain ALGEBRA, frozen FIXED ON, frozen
  DYNAMIC ON, HYBRID OFF, HYBRID SHADOW, HYBRID ON.
- Solver pinned to one logical CPU per run; source/arm order randomized
  deterministically; all credited results independently verified.
- Report PAR2 and family-cluster bootstrap intervals, probe wall ms,
  96/320 depth counts, overrides and source-level solved regressions.
- Do not promote to `main` without a separate sealed blind family
  holdout, verified net improvement and no material solved regressions.

## Interpretation

The exact initial deep action is a *hypothesis based on prior development
evidence*, not a pre-validated general rule; the original scheduling
case is also retrospective. CPU sampling overhead and altered CDCL
search path effects must be analyzed separately. A small percentage
difference on 21/18 sources is not proof of a general solver advantage.
