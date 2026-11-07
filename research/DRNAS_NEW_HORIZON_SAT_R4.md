# DRNAS New Horizon SAT R4 — proven structural routing with cost envelopes

## Starting question
Can an adaptive SAT system preserve its exact logical behavior while
approximately deciding **when not to spend time recognizing structures**?

R3 demonstrated local gains but small Horn formulas and unknown SAT formulas
still accumulated screening overhead. R4 is an incremental, separate, SHA-
frozen experiment to test a source-only family-specific cost envelope.
The user did not ask for a claim of general SAT speedup or a polynomial
shortcut for NP-hard SAT.

## Decision procedure

1. If source bytes exceed the precommitted analysis budget (320000) or
   clause metadata exceeds 6000, do **not** screen. Run clean CaDiCaL.
2. Before reading any clauses, skip small classes where the R3 development
   measurements showed marginal benefit:
   - Horn candidate only if n >= 256 and m >= 300;
   - 2-SAT candidate if m >= 80;
   - pure XOR3 candidate if m <= 64.
   These are heuristic performance rules, not SAT truths.
3. Preview at most 64 original clauses. One counterexample refutes a
   candidate Horn, 2-SAT or pure XOR3 classification, without a full scan.
   If every enabled fast class has been refuted, stop immediately.
4. Use a conservative, fixed affine runtime surrogate for candidate
   routing. It may be inaccurate. It NEVER changes constraints.
5. To use a special method, verify the **entire original source**:
   exact Horn forward-chaining, exact SCC-based 2-SAT or source-certified
   R164 XOR3/GF(2). An early positive pattern is never sufficient.
6. On missing/weak evidence or failed full-source verification, run
   the original source through the exact same pinned CaDiCaL binary.
7. SAT witness always checked against original CNF. Native UNSAT is
   not independently LRAT/FRAT replayed. GF2 contradictions are
   source-trace justified but not independent LRAT either.

## Source-pinned experiment

Four arms: clean baseline; R4 shadow observer (no routing effect);
the frozen R3 policy; the new R4 policy.

- 146 SHA-preserved R3 CNFs including previously seen external real inputs.
- 12 deterministic large Horn SAT/UNSAT CNFs.
- 12 deterministic large 2-SAT SAT/UNSAT CNFs.
- 12 deterministic planted-SAT general unknown sources.
- 12 deliberately deceptive late-clause sources, with source-wide
  Horn/2SAT classification invalidated *after* the preview.
- 194 formulas x 2 reps x 4 arms = **1552 matched trials**.
- 8 GitHub Actions shards, with the same pinned solver SHA
  d3e17f52ee77be0df090da28710a10ba9543576e8ca12e9b2555288a02a077ed.
- Same SHA source, cap and randomized arm order within each matched replicate.
- All analysis and parsing wall-time counted. PAR2 explicitly audited.
- Complete independent source SAT witness checks and no conflicting
  successful SAT-vs-UNSAT statuses between matched arms.
- Results by cohort, actual route, screening cost and early-abstention count.

## Scientific limitations

These are deterministic new samples from already-known families and the
R3 corpus was used in development. The test is NOT blind industrial holdout.
Thresholds are informed by R3 results, so gains on its reused sources
are not independent validation. Microscopic timings at the ms scale
are subject to process-start and runner noise. Stronger followup should
use multiple hardware environments and genuinely unseen originals.

R4 cannot change general SAT worst-case exponential complexity; it
rearranges expensive work by recognizing classes where exact linear
methods already exist.

## Reproducibility and artifacts

- research/new_horizon_r4.py
- research/new_horizon_r4_benchmark.py
- .github/workflows/drnas-new-horizon-sat-r4.yml
- GitHub R3 successful source artifact from run 42324250732
- SHA-256 R3 manifest:
  9c8a18686e6a83b2272dcb86b87cc4c5ca0fa9a82ea2dc81c407e7ad791f1b40

## R5 decision after R4 audit

If R4 meaningfully reduces screening overhead but has no gain on external
real SAT, the next experiment should switch from trying more heuristic
thresholds to a source-certified dynamic *interaction* feature. A
control experiment must isolate whether the feature predicts net
speedup on previously unseen real formulas without changing source semantics.
