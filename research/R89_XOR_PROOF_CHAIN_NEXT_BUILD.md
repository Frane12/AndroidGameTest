# DRNAS R89 — XOR proof-chain repair gate (research specification)

Status: SPECIFICATION ONLY. No solver change or benchmark result is claimed by this commit.

## Blocking observation
R87 proof forensics run 41775336120 reported 64 XOR deductions on formula ba7732774961fdf7508a998a41bd5366 with 0 independently verified and MISSING_PIVOT examples 484, 491. This is a proof-chain failure signal, not proof that all deductions are mathematically false.

## Next build implementation requirements
1. Record provenance for each XOR-derived deduction: immutable original equation IDs, row-operation ancestry, pivot variable, variable ordering, normalization convention, and final implied clause.
2. Reconstruct each derived XOR equation from immutable original equations in a standalone verifier, then independently validate the implied CNF clause (or produce a checkable DRAT/LRAT-compatible proof when supported). Do not trust solver-internal success flags.
3. On missing pivot, truncated ancestry, inconsistent row, timeout, or verifier disagreement, disable the affected XOR deduction and fall back to unchanged Kissat. Never inject unverified learned clauses.
4. Add deterministic regression fixture for the cited formula and pivot IDs 484 and 491. Distinguish invalid mathematics from missing proof metadata; retain failing traces as artifacts.
5. Compare baseline Kissat, instrumentation-only, proof-verified XOR, and forced-disable XOR on the same pinned source, runner class, seeds and time caps. Preserve frozen V15.3.1 as reference; do not alter it.
6. Separate development/replayed fixtures from newly selected external SAT Competition formulas. Freeze external manifest and SHA-256 before benchmarking; exclude tuning on holdout.
7. Audit SAT witness, UNSAT proof where applicable, formula SHA-256, binary/source SHA, runner/CPU, seed, per-formula PAR-2, paired speedups, >2x regressions, and formula-bootstrap 95% CI. Include cost of proof verification.

## Promotion gates
- Zero unverified XOR deductions are admitted to search.
- Independent verifier accepts every enabled XOR deduction; all missing-pivot cases safely fall back.
- All SAT witnesses validate; UNSAT claims require independent checking.
- No claim of speedup until complete, audited, unseen external benchmark is available.

Suggested next workflow name: drnas-r89-xor-proof-audit.yml. Implement and execute separately; this commit intentionally cannot launch an unimplemented workflow.
