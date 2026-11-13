# DRNAS COOP5.2 — decision-quality gate and sub-25-ms sampling

Status: experimental branch, not blind evidence, no main promotion.

## What this run actually compares

The new C++ executable `build/drnas-coop52-quality` is produced from the
same source-frozen X5/COOP5.1 solver. It changes only speculative selection
of the next CDCL decision. RUP-certified algebraic learning, unit propagation,
1-UIP, restarts, SAT-model checking and UNSAT proof output are unchanged.

Before overriding VSIDS, COOP5.2 requires matched BCP completion (both
prefixes complete, or both incomplete) with larger improvement thresholds.
Probes roll back; their results never become SAT/UNSAT conclusions.

Every probe budget is cumulative *for the whole formula*, never per probe
pair or fixed-interval timer. Flags: `--coop52-budget-ms 0.25|1|5|25`.

**Important effective-cap correction:** the underlying COOP5.1 dynamic
policy also caps probing at min(25 ms, max(1 ms, 0.005 × solve cap)).
The COOP5.2 budget is the *minimum* of the CLI setting and that dynamic
cap, so on a 1s solve the effective limits are 0.25/1/5/5 ms, and on a
3s solve they are 0.25/1/5/15 ms. The label Q25_ON means 'requested 25ms,
clamped by dynamic policy'. The benchmark does NOT contain an uncapped
literal-25ms variant on 1s/3s caps. This difference must not be hidden.

The experiment compares:
- X5_FROZEN, ALGEBRA, FIXED_ON, DYNAMIC_ON, HYBRID_ON;
- Q025_ON, Q1_ON, Q5_ON, Q25_ON from one identical COOP5.2 binary;
- Q1_SHADOW to measure probing overhead without altering branches.

Preflight: 313 original small CNFs × two budgets × four controls
= 2,504 independently checked SAT/UNSAT outcomes. UNSAT via independent
DRAT-trim; emitted proof additions checked by RUP oracle.

Retrospective benchmark: 18 official original SAT2024 eligible CNFs,
two repetitions, 3s cap, ten arms; all source SHA checked against frozen
manifest. Synthetic: 21 varied formulas from seven generator families,
two repetitions, 1s cap, ten arms. One logical CPU per solver, shuffled
arm order and no automatic promotion.

## Measurement interpretation

Observed per-formula probe cost in COOP5.1 (54 sampled trials): max
approximately 0.310ms. Only two trials exceeded 0.25ms; none exceeded 1ms.
Thus a 1ms cap is unlikely to affect the known cohort; only more expensive
unseen problems can establish whether it is preferable to the existing
dynamic soft cap. Probe CPU time must be distinguished from downstream
search-path impact. A smaller budget does not itself improve heuristics.

## GitHub

- Source branch: experiment/drnas-coop52-budget-quality-20261114
- Preflight run: 43526600207
- Paired experiment: 43526754231
- Original frozen COOP5.1 reference: 43524579330
