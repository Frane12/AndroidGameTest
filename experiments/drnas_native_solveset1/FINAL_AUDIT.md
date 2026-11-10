# DRNAS Native SOLVESET1 — final permanent solvable-original SAT benchmark
Date: 2026-11-10
Selection run: https://github.com/Frane12/AndroidGameTest/actions/runs/42851269078
Reusable, independently re-run (3 repetitions): https://github.com/Frane12/AndroidGameTest/actions/runs/42852201407
Frozen four original SHA: `experiments/drnas_native_solveset1/FROZEN_DEV4.json`
Replay script: `research/drnas_native_solveset1_replay.py`
Workflow: `.github/workflows/drnas-native-solveset1-replay.yml`

## Qualification facts
- 23 **immutable original** source SHA across MIXAB4 6, MIXAB3 12, EQUIV10M5 5, screened with only our source-built standalone R3C plain under 4.0-second cap, one logical CPU.
- **4 verified SAT** with independently checked complete assignment on their original CNF; **1 raw UNSAT without independent LRAT**; **18 UNKNOWN** by timeout. No foreign SAT engine linked or invoked.
- The four successes were frozen in Git *before* the separate three-repetition benchmark of GF2 arms.
- This is explicitly a **development regression set chosen on our R3C-plain SAT success**, not blind / representative. It must never be used as sole evidence of general solver superiority.
- No UNSAT without proof counts in strict solved/PAR2.

## The four original SHA and prior classification
| SHA256 | cohort | category |
| --- | --- | --- |
| `5b874afeed91345a786ac4345c97aa3e617c57f748570be83421d149b34abebc` | MIXAB4 | very easy |
| `fc529dff1a6f763c97b0ed1dd33199e0d9dd26c50d210f9032e4fdaab5534c16` | EQUIV10M5 | easy |
| `907c98ebe3331af203f0f9f67529e6933255cd1b0550ecc7caf9d4cdc35514a0` | MIXAB4 | medium |
| `92e5fa675073ba9aad91afa4b81129fed5757ea37872fc2dbc3bd4ba0d720a4c` | MIXAB4 | medium/harder |

## Reusable matched 4 SHA × 4 native modes × 3 repetitions = 48/48 completed

All 4 original SHA SAT model-validated for every arm and repeat. Each attempt one logical CPU, nominal 5s E2E cap; no foreign SAT solver calls. Original SHA and all source manifests validated before each replay.

| Native mode | verified SAT | raw UNSAT | timeout | sum solver seconds | sum E2E / strict PAR2 seconds | speed ratio vs R1 (higher is better) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| R1 (pure own CDCL) | **12/12** | 0 | 0 | 7.072730 | **7.158529** | 1.000× |
| R2B GF2 | **12/12** | 0 | 0 | 7.213287 | 7.379689 | 0.970× |
| R3C plain indexed heap | **12/12** | 0 | 0 | 8.337426 | 8.426018 | 0.850× |
| R3C GF2 | **12/12** | 0 | 0 | 8.209358 | 8.380914 | 0.854× |

In this development set, **R1 is fastest**. The R3C variants have an E2E regression relative to R1 (not a speedup); source GF2 derived implications are **0 for every arm**, so these four originals measure native-CDCL performance and regression, **not a positive causal GF2-speed test**.

### Per original SHA: replay solver time (mean of 3 trials, in seconds)

| SHA beginning | R1 | R2B GF2 | R3C plain | R3C GF2 |
| --- | ---: | ---: | ---: | ---: |
| 5b874afe | 0.000200 | 0.000239 | 0.000295 | 0.000270 |
| fc529dff | 0.001854 | 0.002028 | 0.002413 | 0.002385 |
| 907c98eb | 0.785453 | 0.801793 | 1.058819 | 1.057002 |
| 92e5fa67 | 1.570070 | 1.600370 | 1.717615 | 1.676795 |

These are **new 3-repetition replay measurements** on this run. The earlier 2-repeat screen/benchmark recorded different E2E times; do not mix timing across runner circumstances.

## How to rerun
Actions → `DRNAS Native — permanent four-source solvable SAT regression benchmark` → Run workflow on `experiment/drnas-native-solveset1-20261110`, or push a change to its own replay script/workflow. The workflow restores only original CNF source files, recompiles our own C++ R1/R2B/R3C, checks full SHA, measures all 48 matched trials and publishes a JSON audit.

## Keep two separate tracks
1. **SOLVESET1 DEV4:** four easy-to-medium *completed* original SAT formulas for CDCL throughput regression, no GF2-derived implications expected.
2. **XOR-active stress/control:** previous two MIXAB3 originals with dozens of verified GF2 reasons, but not solved in short time caps; do NOT pretend they are part of the solvable set. Synthetic 120 short XOR cases remain separately useful for mathematical correctness.

The next scientific goal is source-only finding of *original* formulas that are both verified SAT-solvable and have genuinely novel GF2 reductions, without tuning to candidate results. Never characterize this selected training set as a blind competitive holdout.
Main branch unchanged.
