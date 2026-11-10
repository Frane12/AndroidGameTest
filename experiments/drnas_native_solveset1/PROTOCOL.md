# DRNAS Native SOLVESET1 — source-frozen solvable original CNF development set
Date: 2026-11-10
Branch: `experiment/drnas-native-solveset1-20261110`
GitHub Actions: https://github.com/Frane12/AndroidGameTest/actions/runs/42851269078

## Objective
Stop benchmarking almost exclusively on cases that time out for every native solver. Find a reproducible, original-CNF *development benchmark* with easy and medium cases demonstrably solvable by DRNAS's OWN native CDCL, then measure actual solver time and comparable end-to-end time.

## Candidate sources (never generated from an altered CNF)
- 6 previously frozen reference-easy MIXAB4 official original SHA
- 12 previously frozen 2021–23 source-only MIXAB3 official original SHA
- 5 reference-easy/medium official original SHA rescued as EQUIV10M5
- Verify SHA-256 of all 23 immutable original CNFs and distinct SHA before invoking any solver.
- Only use original C++17 DRNAS R1, R2B, R3C binaries built from repo source. Foreign SAT solvers/binaries are NOT linked or invoked, even as an oracle.

## Qualification then freeze
- Freeze all 23 source SHA *before* screening.
- Screen each with **standalone R3C plain**, one logical CPU, 4.0-second per-original E2E budget, using original DIMACS.
- "DRNAS-solvable" for the purpose of this reproducible set means **SAT with a complete original-CNF-validating model within cap**. This is stricter than accepting raw UNSAT from an unproved native solver. Screen raw UNSAT and UNKNOWN separately, always.
- After screening, freeze up to four very easy (sub-0.2s E2E) and up to six nontrivial (0.2–4.0s E2E) original SHA. Freeze their original SHA and source, *and* the screening result and compiled binary digests, before any matched timing of experimental GF2 arms.
- At least two verified-SAT originals are required to launch benchmark.
- This is **conditional on native R3C solvability**, so it is a **biased DEVELOPMENT/training benchmark**, not a blind SAT competition result. Subsequent regression wins in this set do not establish overall performance on all SAT categories.

## Same-set matched benchmark
Four independent, own C++17 solver arms, each with one logical CPU, two repetitions, nominal 5-second E2E cap:
- DRNAS R1 baseline
- DRNAS R2B with proven original-CNF GF2 deductions
- DRNAS R3C plain indexed-heap control
- DRNAS R3C with event-indexed source-proved GF2

Record real inner solver seconds, wall E2E, reason count, decisions, conflicts, SAT original witness validity, raw UNSAT without independent proof and timeouts. PAR2 is strict: for unverified UNSAT and UNKNOWN, score 2× full cap; verified SAT earns measured E2E. Summaries report number solved, seconds and comparative × ratios only when grounded.

## Post-selection research validity
- This dev cohort is suitable for **performance regression tests, profiling, optimization and replay**.
- It cannot substitute for independent blind/unused original SHA when asserting advances over existing CDCL solvers or generalization.
- Future blind assessment: source-only index-locked disjoint SHA, preregistered before build tuning, with independent SAT witness validation and original-CNF UNSAT proof checking before reporting solving gains. Separate PAR2 and 1CPU/parallel results.

## Result filenames
`source-23-sha.json` — full source population frozen pre-screen.
`screen-23-results.json` — all qualifying/timeout/raw UNSAT rows.
`frozen-solvable-dev-manifest.json` — exact selected SHA, binary digests, source screening digest.
`paired-original-trials.json` — all selected 4-arm x2 repeat original trials.
`final-audit.json` — per-arm strict PAR2 and per-SHA actual solver seconds.

Main branch remains unchanged.
