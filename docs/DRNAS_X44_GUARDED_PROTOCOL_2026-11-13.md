# DRNAS X4.4 — Guarded Memory (experimental)

Date 2026-11-13; branch experiment/drnas-x44-guarded-memory-20261113.

## Goal

Fix the failure of X4.3 to distinguish useful from harmful SAT decision steps
on out-of-distribution families. On X4.3 training, a 90-epoch three-class
model overfit and generalization degraded when the third cohort arrived.
A shorter fit (20 epochs) and stronger L2 penalties helped log-loss, but
they still produced very poor away/toward calibration on new families.
The fact that a model can retrospectively rank away steps does NOT imply
that it can make useful decisions or that the oracle's direction is the right
objective for CDCL.

## Changes in X4.4

- Binary conditional classifier for **away vs toward**, excluding "flat"
  from supervision but never claiming neutral examples are unsafe.
- Source-level and family-level weighting to prevent long trajectories or
  one generator from dominating learning.
- Three genuinely incremental learning cycles. Carry parameters forward;
  transform coefficients exactly when the training-only normalization changes,
  then apply 20 additional gradient epochs per cycle after the first 50.
- Extract before-action structural and decision features from native X4.2
  recorded states. Oracle outcomes remain offline and unavailable to solver.
- Statistical OOD score from a fixed set of pre-action structural features.
  Use the greater of a conservative score floor and the TRAIN 98.5th
  percentile as the OOD threshold. Exact SAT/UNSAT truth never sets it.
- Explicit abstention when unfamiliar structure exceeds the OOD threshold,
  or when the inferred risk is too close to a VAL-only decision threshold.
- Threshold/margin and the selected checkpoint are calibrated only on
  family-disjoint validation CNFs before testing new families.
- Output full coverage, away/toward recall, away precision, binary AUC,
  accepted-class balanced accuracy, and formula-cluster confidence intervals.

## Source split

Training families (six): planted3, planted_2sat, planted_xor, community3,
sparse3, xor_ring. 48 genuinely new CNFs per family, 288 total, index >=71000.

Validation families (four): sparse4, planted4_dense, xor_bridge,
mixed_sparse_23. 16 new CNFs each, 64 total, indices >=76000.

NEW holdout families (four never previously used as generator families):
hub4_planted, modular2_3, ring3_planted, xor_fan. 32 distinct CNFs per family,
128 independent originals, indices >=82000.

UNSAT controls: php_unsat and graph_k4_unsat, eight each, indices >=87000.
These are exhausted by a separate n<=18 oracle; no spurious away/toward target
is assigned for UNSAT.

Total 496 distinct original CNFs; three variable-renamed replay trajectories
per source, 1,488 native runs. Replays and individual decisions are correlated
observations, not independent samples. Each source is identified by SHA256.

The exact conditional SAT completion probability used to train/predict labels
requires exponential exhaustive enumeration (small n only). It is NOT an
online-computable general solution-distance function.

## Evaluation gate

The native solver X4.2 is exactly the existing source; predictions are
**SHADOW ONLY**, not used to choose native CDCL decisions. This test cannot
establish a runtime speedup. A new active branching policy remains gated
behind a positive independent result and a separate proof-safe paired
end-to-end benchmark.

A positive descriptive result requires:
- >=15% nonflat coverage on untouched families,
- nonzero accepted sample counts for away and toward,
- formula-cluster lower 95% bootstrap bound of balanced accuracy >50%, and
- a report of all abstention rates, source count and family heterogeneity.

These are statistical research heuristics; because four families are a small
non-random set, they cannot establish a universal claim.

If the model has 0% coverage, is poorly calibrated, or fails to recognize
away steps, report failure. Do not relax the gate after viewing outcomes.

## Correctness and provenance

The output SAT assignment must satisfy the original CNF. The independent
exhaustive oracle checks both SAT and UNSAT for all small diagnostic cases.
Native X4.2 does not call another SAT backend. Learned risk never adds
clauses, claims UNSAT, changes proof requirements, or bypasses model checks.

Files: research/drnas_x44_guard.py, research/drnas_x44_benchmark.py,
.github/workflows/drnas-x44-guarded.yml.
