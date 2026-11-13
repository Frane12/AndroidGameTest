# DRNAS X4.6 GATE30

This branch implements the probe-cost scheduling experiment, separate from any matched-state continuation-work X4.6 branch. `main` and the original X4.5 solver remain unchanged.

## What changes

X4.6 keeps X4.5's within-CNF two-weight online scorer. It first asks whether probing is worth paying for. It waits 64 decisions before probing, then normally probes every 192 decisions. GATE doubles or halves that interval after four measured outcomes (48–1536 decisions); SPARSE keeps 192 fixed. A conflict burst permits a new budget check, but never bypasses the cost limit. The approximate cumulative probe budget is 0.5 ms + 2% of elapsed solver time, with possible overshoot by one bounded round. Near the timeout it returns to the ordinary CDCL choice. Skipped probes do not fetch three candidate variables.

The gate's reward is **a local usefulness proxy**, based on changed decisions, predicted score gap, real propagation and structural reduction. It is not a learned estimate of causal seconds saved, remaining search cost, or distance to SAT. Failed literals are not treated as global UNSAT certificates. Assignment rollback does not restore watch ordering, so this is not a fully matched-state causal experiment.

## Frozen prospective test

30 explicitly named generated SAT structural profiles, 20 independently seeded inputs each, three repetitions, five arms, 2-second end-to-end cap: **600 SHA-distinct inputs and 9,000 solver executions**. Profiles include planted random/modular CNF, pure and mixed parity, 2-SAT/Horn, gates, adders/multipliers, coloring, assignments, covers, and Latin squares. Parameter variants are grouped into broader domains in the report. They are not 30 independent industrial domains. SHA uniqueness does not establish non-isomorphism.

Arms: CORE, ADAPTIVE, unchanged X45_ONLINE, X46_SPARSE and X46_GATE. A fresh process resets all online state for every input/repetition. One logical CPU per runner; paired arm order rotates; 12 balanced shards. Generation checks a hidden witness that is never passed to any solver. Every returned SAT assignment is independently checked against original CNF; validation and wrapper overhead are included in E2E. An UNSAT answer on these planted inputs stops the experiment. UNKNOWN/late SAT costs 4 seconds in PAR2. Nothing is filtered by observed runtime.

Historical X4.4/X4.5 manifests are checked for SHA overlap before evaluation. Policies, code fingerprints and inputs are frozen before measurements. No threshold is tuned on this evaluation set.

## Predeclared primary criterion

X46_GATE vs X45_ONLINE: at least 5% lower total verified PAR2, no reduction in solved runs, and a negative upper endpoint of the paired formula-clustered 95% bootstrap interval. CORE, ADAPTIVE and SPARSE comparisons are secondary and must still be disclosed. Passing against X4.5 alone does not establish superiority to ordinary CDCL or industrial solvers.

Three repeats of one input are kept as a single bootstrap cluster, stratified by profile. A second category-clustered interval exposes sensitivity to category mix. Report all categories, broader domains and shards, stable 3/3 solves, regressions, wall time, probe time, scheduling decisions and online updates. The broad-category interval is a sensitivity check, not a guarantee about arbitrary unseen problems.

Before evaluation: 300 exact brute-force-checked small SAT/UNSAT runs; deterministic generator smoke tests; duplicate/metadata/PAR2 audit tests. Large benchmark UNSAT proof support is outside this experiment.
