# DRNAS X4.1 — Proof / Structure / Forecast taxonomy

Standalone native C++20 SAT solver without Kissat, CaDiCaL or CMS in its decision loop. X4.1 is an **observer** built on X4.0, not a new learned branching policy.

## Three strictly different signal types

1. **LOGIC:** `logic.unit_propagations_under_assumptions` is the count of assignments implied by unit propagation *under the current assumptions*, and `logic.conflict_under_assumptions` is a contradiction in the current branch. Neither gives distance-to-answer nor an independent whole-formula UNSAT proof.
2. **STRUCTURE:** `structure.delta_open_long`, `delta_open_binary`, and `delta_satisfied` come from a deterministic 64-**original-clause** sample. These are observations under the live partial assignment, **not** a global decrease of computational complexity.
3. **FUTURE:** `remaining_finish_wall_s` is supplied only for SAT witness verified by the native solver. The external dataset collection **independently verifies SAT against the original CNF** and checks the end-to-end time cap before accepting the label. UNKNOWN and uncertified UNSAT have `null`, never a fake completion time. All labels are retrospective and policy-conditional, **never causal rewards**.

No policy reads any trace fields. The observer is bounded to at most 512 retained transition records per run (older samples may be evicted) and supports a JSONL `--transitions` output.

## Compile

```bash
mkdir -p build
g++ -std=c++20 -O3 -Wall -Wextra -Wpedantic -Werror src/drnas_x41.cpp -o build/drnas-x41
build/drnas-x41 input.cnf --mode core --time 5 --stats
build/drnas-x41 input.cnf --mode trace --time 5 --stats --transitions x41_trace.jsonl
python3 tests/test_x41.py --cases 2800
python3 tests/test_x41_data.py
```

## Collect training evidence with no result leakage

```bash
# 384 labelled-as-SYNTHETIC small controls across eight mathematical families.
# Families held out entirely; a SHA difference alone is not a data split.
python3 research/drnas_x41_dataset.py --synthetic --per-family 48 --synthetic-cap 0.35
# Out-of-family, OFFLINE-ONLY baseline vs fixed kNN9 estimate of measured SAT finishing time.
python3 research/drnas_x41_evaluate.py
# Requires public historical SAT Competition 2024 archive and `remotezip` installed.
python3 research/drnas_x41_dataset.py --official --official-count 80 --official-cap 1.5
python3 research/drnas_x41_evaluate.py --transitions drnas_x41_results/retrospective_SAT2024_original/transitions.jsonl --out drnas_x41_results/retrospective_SAT2024_original/offline_eval.json
```

**Dataset taxonomy:** 384 **synthetic** CNFs: 192 train (four generator families), 96 validation (two different families), 96 never-used-for-training holdout (two further families). For the retrospective public SAT2024 archive, 80 **original** CNFs are selected before any solve by smallest variable count/byte size, with 48 train, 16 validation, 16 holdout **source-family-disjoint**. Original CNF SHA256 is frozen before trials. There is no result-based filtering. This is not a fresh/global blind SAT competition test. Any completed original UNSAT without an independently checked proof is `UNSAT_UNVERIFIED` and receives no supervised duration label or verified-solved credit.

**Offline cost model:** one earliest sampled transition per verified SAT CNF. Fixed 9-nearest-neighbor model of remaining SAT time vs a constant median baseline. Feature scaling is computed from training alone, no validation or holdout data reach the model. Report MAE on both splits. Neither model is allowed to affect X4.1 branching. If kNN loses to a constant predictor, **do not promote it**.

## Interpretation

- A high conflict count is not a distance-to-solution.
- A shrinking unsatisfied clause sample is not guaranteed to reduce necessary proof/search work.
- A fast retrospective finishing time under the current CDCL policy does not identify which alternative decision would have been better.
- Samples from the same CNF are **not independent training examples**: the offline evaluator keeps one transition per instance.
- Only after robust, family-disjoint offline validation and controlled paired experiments can a future X4.3 shadow driver be considered.
- Native UNSAT needs independent DRAT/LRAT certificates before public verified UNSAT claims.