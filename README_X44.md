# DRNAS Native X4.4 — Controlled Counterfactual First-Polarity Experiment

Independent native C++20 CDCL solver built from the X4.1 core. No external SAT solver is linked or invoked.

## Goal

Measure whether decisions at *the exact same internal CDCL state* lead to materially different **future solving time**. This is *not* an absolute distance-to-SAT metric, and no alternative decision is chosen online by a model in X4.4.

## Control and intervention

- Construct 300 deterministic **generated planted-SAT** CNFs (10 unrelated structural generator families, 30 each; **not** original industrial SAT2024 inputs). Freeze SHA256 and family-disjoint splits: 180 TRAIN, 60 VALIDATION, 60 HOLDOUT.
- For each source, run unmodified X4.4 CORE to completion (cap **2.5 seconds**). If verified SAT, deterministically select **up to five** decision indices spanning that baseline solve. No source is removed from reports if it times out or has few decisions.
- For each selected index, rerun from the original source in two fresh processes. The solver follows the **identical deterministic CDCL prefix** until that decision, then forces **positive** or **negative** polarity for the **same normally selected branching variable**. After the first intervention, full CDCL (backtracking and both branches when necessary) resumes unchanged. The original CNF is not modified.
- Check that the candidate variable, decision index, default sign and a deterministic 64-bit fingerprint of the decision-trail, assignments, reasons, phases, counters and clause database **match before the intervention**. The fingerprint is a useful control, not a mathematical proof of complete binary state identity; the fixed deterministic replay is the principal control.
- Independently verify every SAT witness on the original CNF. The generator has a planted witness, so native UNSAT is an error. Timeouts and missed checkpoints are **censored**, never assigned a bogus completion time.
- Compare **time from the checkpoint to verified completion** (`post_checkpoint_s`), not just startup-inclusive E2E. Include the checkpoint instrumentation equally in both arms. Reverse run order across pairs to reduce cache bias.

## Statistical validation

Only pairs where **both** continuations produce independently verified SAT outcomes receive numeric pair labels. Define a conservative strong signal as an absolute difference of at least 2 ms **and** at least 10% of the faster continuation. These thresholds are fixed before examining test outcomes.

Fit a regularized linear model predicting relative positive-vs-negative finishing time from **pre-decision structural/state features only**: assignment fraction, depth, conflict/decision ratio, learned/original ratio, residual-long-clause fraction, variable positive/negative and binary incidence, default phase, and input dimensions. No SHA, family, filenames, reported time, or observed post-decision labels may be prediction inputs.

TRAIN only fits model parameters. VALIDATION only chooses among fixed regularization values 0.1/1/10/100. Only after model selection is frozen, score HOLDOUT once. Correlated states from the same CNF are grouped when bootstrapping confidence intervals.

Report matched states, completed/censored pairs, strong signal frequency, model vs original phase choice on identical states, unattainable hindsight-oracle lower bound, and **overall** CPU spent generating paired training data. Offline shadow evaluation is not a validated in-solver speedup. Single repetitions can be noisy, particularly below 10ms; next stage will require independent repeats and new unseen formula sources.

## Build and local tests

```bash
mkdir -p build
g++ -std=c++20 -O3 -Wall -Wextra -Wpedantic -Werror src/drnas_x44.cpp -o build/drnas-x44
python3 tests/test_x44.py
python3 research/drnas_x44_counterfactual.py freeze
python3 research/drnas_x44_counterfactual.py shard --shard 0 --shards 10 --cap 2.5
```

Executable interface (DIMACS result and complete witness, exit SAT=10, UNSAT=20, UNKNOWN=0):

```bash
build/drnas-x44 input.cnf --mode core --time 2.5 --checkpoint 100 --force-polarity 1 --stats
build/drnas-x44 input.cnf --mode core --time 2.5 --checkpoint 100 --force-polarity -1 --stats
```

Two JSON stderr events are available: `X44_CHECKPOINT` for pre-intervention state and `X44_STATS` for end-to-end and post-intervention time. Stage `aggregate` consumes all 10 shard artifacts, audits frozen source identities and training splits, fits the shadow model and writes a compact final report.

This benchmark answers *whether a measurable decision signal exists on this generated source distribution*. It does not claim a general solution-distance metric, causal effects from observational traces, SAT2024 competition performance, independently verified general UNSAT proofs, or a deployed better branching policy.