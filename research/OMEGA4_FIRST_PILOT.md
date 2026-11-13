# DRNAS MATH Ω4 — first native live-CDCL pilot (2026-11-13)

Status: **mechanism works; no solving-speed advantage yet**. Historical-development experiment, not blind, not a new theorem or a generally competitive solver.

- [GitHub Actions execution 43514088212](https://github.com/Frane12/AndroidGameTest/actions/runs/43514088212)
- [Pinned audit artifact including 20 per-case logs and solver SHA](https://github.com/Frane12/AndroidGameTest/actions/runs/43514088212/artifacts/14080530975)
- Native C++ module: research/omega4_live_gf2.cpp
- Matched experiment runner: research/omega4_benchmark.py
- Prior independently source-certified extractor: research/drnas_xorabc3_source_rows.cpp

## Mathematical mechanism

Given source-entailed parity equations A x = b, and a real CDCL trail assignment t, compute over GF(2):

  A_U x_U = b XOR A_T t

Each live Gauss–Jordan reduction retains its exact source-equation ancestry bitmap.
Reconstruct and cross-check the full XOR consequence before proposing a CNF unit reason or falsified conflict clause. A failed check causes safe rejection. This is standard sound linear algebra with a proof-carrying CDCL bridge; **no mathematical novelty claimed**.

One compiled CaDiCaL 2.1.0 IPASIR-UP binary in three modes: clean, shadow and live.
Cost bounds: max 32 source-certified XOR rows, width <= 16 for an exported reason, 12,000 live scans, 1 logical CPU per solver.

## External original SHA-locked formulas (16 previously seen development cases)

| Režim | Backend UNSAT status | Neriješeno | PAR-2 (s) |
| --- | ---: | ---: | ---: |
| Clean CaDiCaL | 2 | 14 | 84.033705 |
| Shadow Ω4 | 2 | 14 | 84.078041 |
| Live Ω4 | 2 | 14 | 84.078014 |

*No independent original-CNF LRAT UNSAT certification for these 2 solved cases; verified PAR-2 penalizes them.*

- 228 independently source-certified XOR equations in the 16-CNF pilot
- LIVE: 277 unit proposals, 30 explanations delivered to CaDiCaL, 14 conflict clauses
- Activity confined to two original cases for units and one for conflicts
- SHADOW: 2,856 unit candidates, 450 conflict candidates along its own trail, **not equivalent to causal speedup**
- 8 of 16 LIVE trials reached safe 12,000-scan abstention threshold
- No additional solved original formula or aggregate PAR-2 gain

Four synthetic controls: 3 original-model-verified SAT and 1 independently brute-force-confirmed UNSAT. An actual 3-equation deduction produces a novel implied literal after a CDCL partial assignment; a conflicting assignment yields a source-entailed conflict. Exhaustive 64-assignment proof check, undo and matched shadow selftest passed.

## Next experiment Ω4.1 (not run by this report)

Study reason **usefulness** instead of raw candidate count. On the two signal-bearing, development-only formulas compare clean/shadow/live conflict and decision counts, reason width, scan cost and time at longer caps. Keep the experimental branch isolated. Only after fixing cost/utility ratio freeze a new SHA- and family-separated external holdout against CaDiCaL/Kissat/CryptoMiniSat with independent SAT witnesses and UNSAT proof checking.

The inherited APK-on-any-push workflow ran unexpectedly during initial source commits. Its trigger was restricted to main **only on the Ω4 experimental branch**; no main changes were made.
