# DRNAS New Horizon SAT R6 — two live CaDiCaL profiles, source-exact

## Why
R5 on 16 original SAT Competition 2026 formulas showed complementary profiles:
- Native CaDiCaL default solved a lights-out SAT original in 7.60 s; UNSAT profile timed out.
- Native CaDiCaL UNSAT profile solved a hardware-verification UNSAT original in 1.93 s; default timed out.
- The R5 source-header router missed the winning UNSAT profile.
- Fourteen other real inputs timed out under all observed modes.

R6 asks whether a pair of live CDCL solvers with bounded pilots can select the better profile in time, preserving the selected solver's same learned state.

## Source semantics and cost
- Two CaDiCaL 2.1 solvers ingest the identical ORIGINAL CNF.
- A single monotonic deadline starts before source parse; all source loading,
  both pilot costs, and the losing solver are charged.
- Each candidate runs two alternated 128-conflict pilot windows; order
  is counterbalanced across repetitions.
- Learner callback only counts offered clause lengths; it never injects any.
- The chosen same in-process solver continues, preserving its learned clauses.
- Purely approximate decision is which existing native profile to continue.
- On conclusive SAT pilot results, source-original SAT witness is checked.
- On UNSAT, CaDiCaL's native conclusion is accepted as algorithmic result,
  but an independent LRAT/FRAT replay is NOT supplied.
- Optional interleave control serially alternates 4096-conflict chunks
  on one CPU: this is NOT simultaneous multicore execution.

## Seven preregistered modes
1. default: native no dual overhead.
2. unsat: native UNSAT profile no dual overhead.
3. dual_keep_default: pilot both then continue default unless already solved.
4. dual_keep_unsat: pilot both then continue UNSAT unless already solved.
5. dual_fast: choose UNSAT only when 15% faster at equal pilot-conflict budget.
6. dual_learning: choose UNSAT only on 30% higher offered short-clause rate.
7. dual_interleave: keep both live, alternate bounded conflict chunks
   until one solves or the full wall-clock budget expires.

No decision can access filename, answer, or R5 per-source timing.

## Reproducibility
- Exactly the 16 byte-immutable R5 GBD main_2026 originals.
- R5 manifest SHA256:
  8931f7f544c04336cc9469039d5677915e999c5cd8f4070a4e103d2be8e346a7.
- CaDiCaL 2.1 pinned commit:
  31f9aae44947c673dc6190c9beb399acb9ffec6a.
- 16 formulas, two repeats, seven matched methods: 224 trials on 8 shards.
- 12-second wall cap per trial, including all dual overhead and validation.
- Fail-closed audit on source SHA, missing arm, contradictory SAT/UNSAT,
  mismatched PAR2, and selected live-state retention.
- Native UNSAT no independently replayed LRAT.

## Limitations
R6 REUSES the R5 sources and is NOT a blind real holdout. R6 cap is 12s,
R5 cap 8s; cross-run PAR2 is not directly comparable. Existing CaDiCaL
profiles do not constitute a new CDCL algorithm. Any promising result
needs new SHA-disjoint original SAT2026 formulas and repeated seed/hardware
reproductions before production.

## Files
- research/new_horizon_r6_dual_unsat_driver.cpp
- research/new_horizon_r6_dual_live_benchmark.py
- .github/workflows/drnas-new-horizon-r6-dual-live.yml
