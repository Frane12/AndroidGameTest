# DRNAS X4.5 — frozen-model ONLINE decision benchmark

This experiment tests a genuinely deployed but **bounded** learned polarity intervention in our independent native C++20 CDCL solver, versus the identical solver with no intervention.

## Frozen model and correctness

The ridge model is **the 28-feature model frozen in X4.5 repeated counterfactual run #43366617752** (training 509 robust states, family-separated validation, holdout not used for fitting/selection). It uses source-independent state and local propagation features only. Before any chosen polarity, the solver computes the same 28 predecision features used for training, including log1p transforms for local counts. Prediction is evaluated inside the native solver, without Python or a competing SAT engine.

A trained model may change **exactly one** polarity, at the fixed 32nd CDCL decision (zero-based). The solver continues full CDCL search with backtracking, preserving SAT/UNSAT correctness. It never assumes the preferred polarity is globally satisfiable and never uses the planted witness, SHA or filename for decisions.

Run both native arms on exactly 100 newly generated planted-SAT CNFs (10 per family; source SHA frozen by a deterministic fresh seed), **two repeats per formula**, 0.8-second wall-time cap, one logical CPU. Alternate arm order. Verify every successful SAT witness independently against ORIGINAL CNF. Unknowns get PAR2=2×cap. Include model parsing, predecision features, and inference time in end-to-end wall time. No competing SAT solver is invoked. These are generated, not official industrial CNFs, and use previously studied generator families. Do not claim globally blind generalization.

## Locally reproduced pilot results (not GitHub runner timings)

| Arm | Verified SAT | PAR2 (s) | sum E2E wall (s) |
|---|---:|---:|---:|
| CORE | 166/200 | 84.248159 | 57.486796 |
| Frozen X4.5 online | 164/200 | 87.594963 | 59.260444 |

This corresponds to a **3.97% PAR2 regression** in the online arm. 46 paired attempts faster, 64 slower, 90 nearly tied, and the formula-clustered CI for model-minus-core mean PAR2 includes zero. Thus the frozen policy is **not promoted** for production use. X4.5's offline holdout likewise showed a 3.83% time regression, which is a warning, not independent proof.

## Reproduce

```bash
mkdir -p build
g++ -std=c++20 -O3 -Wall -Wextra -Wpedantic -Werror src/drnas_x45_live.cpp -o build/drnas-x45-live
python3 research/drnas_x45_live_benchmark.py --per-family 10 --reps 2 --cap 0.8 --checkpoint 32 --model-json research/drnas_x45_frozen_28.json
```

The model format is converted from frozen JSON to a text-only coefficients file by the benchmark runner; input to the native C++ binary is `--model-file <path> --checkpoint 32`. The C++ decoder does not import external code. An independent test checked native and Python scoring to within 1e-6 on the same captured checkpoint.

Future proper improvements should investigate context features independent of variable numbering, repeated timing, broader disjoint families and possibly cost-aware abstention before promotion.
