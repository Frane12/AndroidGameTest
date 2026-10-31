# DRNAS NP Lab — NeuroFlow v0.6.2 Fast Horn, measured report

**Date:** 2026-10-31. **Verified workflow SUCCESS:**
https://github.com/Frane12/AndroidGameTest/actions/runs/41193061823

**Raw CSV/frozen policy artifact:**
https://github.com/Frane12/AndroidGameTest/actions/runs/41193061823/artifacts/13039947423

## Outcome

Frozen TRAIN-ONLY selection is **ENABLED** with:
`min_n=30, minority_min=0.13, minority_max=0.28,
unit_max=0.0, defect_max=0.1, pair_budget_ms=12`.

Training: 172 instances (100 previously tested original SATLIB cases and
72 separate constructed controls). Trained net gain before margin: +0.39 ms
per instance. Holdout: 100 previously unused SHA-unique SATLIB problems and
72 separately constructed control instances. Three matched measurements
each, 516 total; all SAT/UNSAT results correct, original models checked.
CryptoMiniSat validates real SATLIB outcomes.

Original archives uf75-325, uuf75-325 and flat30-60 were exhausted by
earlier research; entirely omitted from both splits rather than reusing
known test instances.

## Measured in-process wall time (milliseconds)

| Family | Cases | DRNAS median | NeuroFlow median | Mean PAIRED saving | Recognized |
|---|---:|---:|---:|---:|---:|
| SATLIB (5 families) | 100 | 23.1144 | 22.6318 | +0.1278 | 0 |
| constructed horn_sat | 24 | 4.4239 | 1.7941 | +3.5310 | 24 |
| constructed horn_unsat | 24 | 1.7799 | 1.8911 | -0.1164 | 0 |
| constructed near_sat | 24 | 4.9438 | 5.0245 | -0.1538 | 0 |
| ALL | 172 | 8.9046 | 5.4783 | +0.5293 | 24 |

**Important:** the difference between pooled medians (8.90 to 5.48)
is NOT a valid estimate of mean speed improvement; family mix is highly
nonuniform and the paired mean is only +0.5293ms. The median paired gain
over 516 runs was NEGATIVE -0.0447ms. Thus this is NOT a general
acceleration across arbitrary SAT problems.

Every one of the 24 unseen Horn SAT controls was faster on all three
repetitions (72/72 runs). Casewise median gains were positive in all
24. Horn SAT median speedup was 4.4239/1.7941 = **2.47x**.
It recognized 24/24 constructed SAT Horn cases but NO external SATLIB
cases. Horn UNSAT were excluded with the cheap gate, avoiding the
heavier exact proof, but pay ~0.1ms feature overhead. Near-Horn
controls were mostly rejected.

100 SATLIB cases: 127/300 paired runs faster, 41/100 cases faster by
casewise median; casewise median improvement -0.0322ms. No general
SATLIB gain is established. Ordinary DPLL remains best most of the
time for this data. All SATLIB certificates were checked for SAT,
and statuses matched CryptoMiniSat.

## What this proves and does not prove

It supports a limited engineering conclusion: a cheap two-stage
selector can identify *recognizable renamable Horn SAT* structure
and get an end-to-end speedup including gating costs on this
constructed, previously unseen family. It does not prove a general SAT
speedup, novelty of Horn renaming, or anything about P vs NP.
Additional external renamable Horn application benchmarks are required
for stronger generalization evidence.

Next: benchmark on independent naturally occurring Horn-ish CNFs;
reduce even the first-pass cost on rejected cases; retain safe fallback.
