# DRNAS New Horizon SAT R2 — robusna linearizacija

Goal: Explore system-theory guided simplification without changing the
SAT system's original semantics. Linearize only *decisions* about method
and cost. Exactly solve the special classes if and only if source-complete
proof obligations are satisfied.

## System integrity contract

- Original CNF and SHA-256 are immutable. Never replace an approximate
  formula with a guessed equivalent or discard constraints.
- A 64-clause source probe may *suggest* a method but **never proves**
  formula membership in a tractable class.
- Before using a method, parse and verify **every original clause**.
- Exact Horn SAT uses forward chaining and least-model construction,
  linear in literal occurrences. Exact 2SAT uses SCC, linear in variables
  plus implication edges. Exact parity uses R164 source-complete GF(2).
- A predicted method that fails full-source verification immediately
  returns to unchanged CDCL.
- For unrecognized/unprofitable structures, fast default CDCL.
- Independent source-model validation on every SAT answer.
- Exact source-derived UNSAT is algorithmically justified, but a separate
  standard LRAT/FRAT certificate is not yet provided here.

## The approximate part

A fixed conservative *piecewise affine* cost surrogate estimates:
baseline CDCL cost minus special-method cost minus observed probe time.
The formulas and coefficients are frozen *before* R2 benchmark results.
This is not a learned predictor, not an established universal timing
model, and **never** changes the formula or logical answer.
A margin rejects fragile estimated gains.

Symbolically:

    expected_gain = affine_baseline(shape) -
                    affine_special(shape) -
                    observed_probe_cost

    use_special_only_if
       expected_gain > conservative_margin
       AND full_source_membership_is_verified

A poor timing estimate costs performance only, not correctness.

## Independent correctness checks

The R2 selftest brute-forces random Horn and 2SAT sources with n=1..7
over 630 combinations, compares satisfiability, and checks generated
SAT witness assignments. Late-clause traps make the first 64 clauses
appear as recognized classes but place a disqualifying clause afterwards.

## Paired experiment

106? NO: R1 74, new Horn 16, new 2SAT 16, late-clause traps 8:
**114 source formulas**, 2 repeats, 4 arms = **912 solver runs**.

Modes: clean / shadow source probe / R1 / robust R2.
Same exact pinned CaDiCaL binary SHA reused from successful R1 CI run
42320433991. Same source SHA and cap per matched pair. Includes
preprocessing wall time, PAR2, exact method selected, source-witness
verification and per-cohort summaries.

Source groups and limits:
- R1 74 already examined sources including 12 previously used external
  originals, not blind; 3s generated / 10s external.
- R2 16 new deterministic Horn SAT/UNSAT.
- R2 16 new deterministic 2SAT SAT/UNSAT.
- R2 8 adversarial late-clause traps.
- New deterministic generators are not external distribution-blind data.
- Four GitHub Actions shards and a fail-closed aggregate audit.

Do not infer general performance improvement from optimized solved easy
families, do not claim a complexity result for arbitrary SAT.
Next scientific milestone is a withheld, independently sourced *real*
SAT/UNSAT holdout and measured selector regret versus an oracle.

## Implementation

- research/new_horizon_r2.py
- research/new_horizon_r2_benchmark.py
- .github/workflows/drnas-new-horizon-sat-r2.yml

### System-design discussion

The constructor's rules are logical correctness constraints. Replacing
them approximately would alter the system's behavior. The selector's
forecast of effort is an *observation-layer approximation* and may be
rough when fallback remains sound. This is the deliberate boundary
between robustness and precision.
