# DRNAS Native Core R2 — actual first standalone GF2 CDCL results

Date: 2026-11-10  
Code and workflows: `experiment/drnas-native-core-r2-gf2-20261110`  
GitHub Actions success: https://github.com/Frane12/AndroidGameTest/actions/runs/42839581088

## Own solver implementation

`research/drnas_native_core_r2.cpp`: native C++17 original implementation of CDCL watched literals, trail, unit propagation, phase/activity branching, 1-UIP, backjump and restarts. Native source-certified complete 2..4 arity XOR CNF extractor; exact pairwise GF2 cancellation; proof-backed native trail clauses for GF2 implications and violated parity conflicts. **No third-party SAT solver linked or invoked.**

The R2 source-only detector in this first build limits the active source row pool to the first 128 lexicographically sorted exact complete source equations. This can hide pairs of source XOR rows needed for nontrivial GF2 cancellation. It is not evidence of no underlying XOR structure.

## Independent correctness evidence

- Own R1 C++ exhaustive cases: 818 SAT/UNSAT correct (258 SAT, 560 UNSAT).
- Own R2 C++ exhaustive cases: 1,636 mode-specific SAT/UNSAT correct (516 SAT, 1,120 UNSAT).
- Independent Python exhaustive assignment truth tables: 540 CNFs × three own modes (R1, R2 plain, R2 GF2) = **1,620/1,620 correct comparisons**.
- Of 540 original small CNFs, 120 source-entailed overlapping-XOR controls; derived GF2 propagated or detected contradiction in **120/120**. Mathematically validated on original CNF, with source parity exhaustive selftest across 16 full assignments.
- Neither validation depends on external solver binaries.

## Six previously frozen reference-easy original CNFs

Matched 6 SHA × 3 own arms × 2 repeats = 36 original-CNF attempts at 3-second E2E per attempt; one logical CPU each. SAT models verified on original; UNSAT raw status **is not an independent LRAT/DRAT certificate** and is excluded from strict PAR2.

| Arm | SAT witnessed | raw UNSAT no independent LRAT | timeout | Strict original-SAT-only PAR2 seconds | sum actual wall E2E seconds | Derived GF2 implications |
|---|---:|---:|---:|---:|---:|---:|
| R1 | 4/12 | 2/12 | 6/12 | 51.0868 | 25.8426 | 0 |
| R2 plain | 4/12 | 2/12 | 6/12 | 51.0677 | 25.8185 | 0 |
| R2 GF2 | 4/12 | 2/12 | 6/12 | 51.0419 | 25.7548 | **0** |

The three arms solve exactly the same originals. Tiny numerical timing differences are runner noise, **NOT** a demonstrated speedup. On three of six original SHA, R2 detected 128 source XOR equations, but generated zero derived rows and zero XOR trail implications on these cases.

## Next controlled follow-on

On **separate** `experiment/drnas-native-core-r2b-xor-selection-20261110` branch, source certify up to 1,024 original XOR rows before selecting and scheduling at most 128 live source rows plus 64 derived rows. This corrects the lexical first-128 selection bias and retains the exact source-entailed clause reasons. Independently fuzz its mathematical correctness. Target source-preregistered MIXAB3 originals with previously measured 20 and 16 reductive XOR rows. Measure R1 vs R2 vs R2B with one CPU, 6-second E2E cap and strict proof-aware PAR2, not a retrospective winner.

No main changes. No third-party binary dependency.
