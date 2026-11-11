# DRNAS ATLAS4 — persistent learning on similar real CNF formulas

**Branch**: `experiment/drnas-atlas4-persistent-learning-20261111`
**Run**: https://github.com/Frane12/AndroidGameTest/actions/runs/42939425438
**Status**: 1/1 CI job SUCCESS, 16 SHA-pinned source CNFs, 8 training
and 8 temporally later holdout, 3 repeats per arm, one logical CPU,
8-second cap, original SAT witness independently verified.

## Hypothesis

A small, persistent, training-only memory can learn when to skip the
expensive Boolean atlas on similar but unseen formulas. The first
implementation is deliberately conservative and **does not train the
underlying CDCL solver**. It trains a preprocessing **routing policy**,
choosing native A or full ATLAS2 before solving.

## Design

* The 16 distinct CNFs are original public software feature models,
  `Tractables/cnfs/feature-models/Pett2021-*.cnf.xz`. All files are
  pinned by exact upstream Git blob SHA1 under commit
  `de4731f68e5a5bb6629269b3be1d19b44e812763`, and each decompressed
  source SHA256 is logged.
* Train on 8 earlier Pett2021 snapshots (May 20 to June 12); hold out
  8 later snapshots (June 12 to June 19). Similarity is intentional:
  this is **within-family transfer**, not evidence of generalization
  to unrelated SAT instances.
* Source-only fingerprint: log(variable count), log(clause count), and
  0/1/2/3/4+ literal-clause length histogram fractions. No solver
  results, solution witnesses or names in the feature vector.
* Training labels are derived from the median of three paired E2E
  runs. ATLAS2 is marked better only if its median wins by both
  5% relative and 0.5ms absolute. Else learn native A.
* Persist eight labeled feature examples to
  `mre_atlas4/learned_model.json`; freeze SHA256 **before opening
  holdout labels**. Nearest three training neighbors must all vote
  ATLAS2 before choosing ATLAS2. Otherwise ABSTAIN -> native A.
* Holdout independently benchmarks A, ATLAS2 and ATLAS3. Learned
  result is **a counterfactual policy replay using the corresponding
  measured A/ATLAS2 trial times**, not a fourth separately timed
  process. Therefore no extra inference overhead is charged; the
  reported learned PAR2 is a lower bound on real learned implementation
  cost, not an exact measured deployed solver E2E.
* All SAT witnesses verified on ORIGINAL CNFs; no UNSAT result
  counted without independent certification.

## Actual result

8/8 training instances preferred native A under the conservative
margin. The learned JSON memory was frozen at SHA256
`a509bd4aa460f3bd783b4116700d0bea7cb9d72c891cb72ee0201bed94bb6858`.

On all 8 later holdout instances, the nearest-neighbor policy
recommended native A (zero ATLAS2 selections).

| Holdout arm | Verified SAT | Sum PAR2 (s) |
|---|---:|---:|
| Native A | 24/24 | **0.103714** |
| Learned policy replay (A on all 8) | 24/24 | **0.103714** |
| Frozen ATLAS2 | 24/24 | 0.106497 |
| ATLAS3 gate12 | 24/24 | 0.106659 |

Avoiding ATLAS2 gives a **2.69% reduction** in observed E2E time
relative to forcing ATLAS2 on all holdout instances. This is not an
improvement over native A; the learned policy merely recovered A
and avoided unnecessary preprocessing. The raw absolute difference
is **2.783ms across 24 trials**, small and susceptible to noise.
The measured policy-replay time excludes model lookup and inference.

## Scientific interpretation

The first experiment supports a useful negative result: for a
homogeneous family of easy SAT CNFs, the learned policy abstains from
an unprofitable atlas on unseen but similar formulas. It does **not**
demonstrate improving solver performance with additional experience,
positive transfer, generalization across different formula families,
or a causal advantage over the already good native A baseline.

Next steps:
1. Add a genuinely prospective training set with both profitable
   and unprofitable atlas transformations; do not assume any positive
   examples exist until observed.
2. Compare **online learning curves** after 0/4/8/16 source-disjoint
   training formulas, evaluated on a fixed frozen holdout.
3. Time the full deployed policy including loading the JSON memory
   and nearest-neighbor decision; include a fixed no-learning
   structural gate and a random/placebo router.
4. Prefer medium-hard structured CNFs where preprocessing can
   influence actual CDCL conflicts and propagations, rather than
   4ms SAT problems dominated by startup overhead.
5. Keep independent source family holdouts to detect overfitting
   and measure real generalization.

Stable main and ATLAS3 reference remain unchanged.
