# DRNAS Native X4.2 — 1,000 CNF training traces, frozen splits

## Purpose

Train an offline estimate of policy-conditional **remaining work**, NOT a purported universal distance to a satisfying assignment. Record actual transitions from independently verified SAT runs, with no fabricated reward for conflicts or structural change. Compare a frozen kNN9 model and fixed regularized log-linear model against a constant median predictor; do not enable an AI branching driver.

## Two independent cohorts — do not conflate them

1. **1,000 new reproducibly GENERATED planted-SAT CNF input files**, 220–283 variables, ten generator families, 600 train / 200 validation / 200 untouched holdout. All 1,000 sources are unique SHA256. This is *not* a set of 1,000 authentic industrial or competition instances. Every original generated input is checked independently for each reported SAT witness. Target is 0.05–3 seconds, but sources are **not discarded or replaced based on their finishing times**. Report achieved target-band count and all censored instances.
2. **100 separately identified ORIGINAL SAT Competition 2024 instances**, retrospective, 3-second cap, selected without observed outcomes. This is the external reality check, not pooled with the generated training set. In the prior X4.1 test only 4/80 original formulas finished inside 1.5 seconds; it would be misleading to claim that 1,000 such fast genuine originals have been sourced.

The source family and split are frozen before any solving. The split is by *generator family*, not merely instance SHA. No same generator family appears in two splits. The Python evaluation may use training SAT labels only to fit the models; metrics are computed separately on validation and holdout. Future holdout updates would require a new holdout.

## Reproduce

```bash
mkdir -p build
g++ -std=c++20 -O3 -Wall -Wextra -Wpedantic -Werror src/drnas_x41.cpp -o build/drnas-x41
python3 tests/test_x42_manifest.py
python3 research/drnas_x42_1000.py --shard 0 --shards 4 --cap 3
# Run each of shards 1, 2, 3 on a separate logical CPU, exactly 250 CNFs each.
# Use GitHub Actions drnas-x42-thousand.yml for 4-shard collection and aggregation.
```

The X4.1 native C++20 solver executes unaided. There is **no** Kissat, CMS or CaDiCaL in the solving process. Source descriptions, known planted witness and split labels are available to the experiment harness only, never the solver. Original CNF SHA256 is checked before each run. All SAT witnesses are independently verified against the original CNF. Timeout, invalid or unverified results have `label_remaining_wall_s=null`. If any planted-SAT problem returns UNSAT, the experiment **fails** and requires investigation.

## Time and cost labels

- Single CPU affinity per shard; whole-process time including CNF I/O, SAT verification, trace serialization is counted in E2E/PAR2. Shards can run on different physical runners, an unavoidable timing-noise source to audit in `x42_versions.txt`.
- Every SAT formula contributes at most one earliest measured trace to offline regression evaluation. Thousands of rows from the same CNF **do not** count as independent examples.
- No claim that retrospective remaining time gives a causal answer about a *different decision*. No policy learns online from holdout, and the branch selector remains the tested X4.1 one.
- Keep formula groups with <50 ms, timeouts, and solved outcomes; never filter holdout using test results to manufacture target difficulty.
- Models: constant median; fixed kNN9; fixed L2-regularized log-time linear model. All preprocessing comes from training. Report mean absolute error and RMS error in milliseconds for complete verified SAT paths, plus counts of censored paths.

## Success criteria and next steps

Minimum: 1,000/1,000 distinct SHA and exact 600/200/200 family splits; no invalid SAT witness or contradiction with planted-SAT construction; separate published-original audit; all timeouts represented and all cost predictors **offline only**. To justify X4.3 online policy, the frozen learned model must beat constant reference on independent source families *and* a separate randomized paired policy intervention must improve verified E2E PAR2/solved with regressions bounded; no arbitrary conflict-reduction reward. UNSAT requires independent checked proofs for verified claims.