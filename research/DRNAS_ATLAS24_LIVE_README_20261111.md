# DRNAS ATLAS24 — adaptive single-process CDCL (experimental)

Branch `experiment/drnas-atlas24-live-cdcl-20261111` · 2026-11-11 · main and old experiments unchanged.

## Motivation and architecture
An original SATLIB regression run, ATLAS23, found that A is often better than C7 on one cohort while C7 is better on another. ATLAS24 therefore uses one mutable native CDCL instance, not a two-solver portfolio.

1. Begin with frozen A search (no ATLAS15/CDCL C-arm initially).
2. After each window of 1,500 conflicts, measure incremental watched visits and propagations.
3. Only after **two consecutive** windows with at least 32 watched visits per propagation and at least 3,000 total conflicts, enable C7 adaptive retention, CDCL minimization/restarts, C-arm selection and 23's stable-phase policy.
4. If the active C7 state later has **two** windows of at least 96 watched visits per propagation and at least 3,000 conflicts since activation, switch heuristics back to A. Retain learned clauses and implication reasons. Never restart a second solver.
5. At most one activation and one recovery per solve. These thresholds are a frozen **engineering hypothesis**, not statistically tuned or proven optimal.

## Variant arms
- `V24_LIVE`: source-original CNF, online pressure gate.
- `V24_LIVE_GAUSS`: same online gate with the existing source-derived XOR/GF(2) Gaussian extraction path. It is not always active; backend core activates only if source structure qualifies.
- Reference controls: A, C7_ADAPT, V23_C7_STABLE, clean oneCPU Kissat and CMS.

## Evaluation
- Smoke then three groups: 10 exact ATLAS21M SHA (regression, 10s), 6 SATLIB originals distinct from regression SHA (extension, 12s), 16 deterministic generated CNFs (fresh, 8s).
- Per arm / per group two paired repetitions, single logical CPU, full end-to-end subprocess, same source SHA and caps.
- Test groups are disjoint within ATLAS24. Older original SATLIB pools mean the regression and extension are **not** globally blind. Fresh generated SHA are new to the selected ATLAS series but not asserted globally unseen.
- Strict SAT original model verification. UNSAT without independently checked original proof remains `UNSAT_UNVERIFIED` and is penalized in strict verified PAR-2.
- Print reported and strict verified PAR-2 separately, solved SAT, uncertified UNSAT, conflicts, watch visits, activation and recovery event counts, and outliers.
- A successful compile or GitHub run is not evidence of higher solving performance. A zero activation count is evidence the gate did not actually exercise in completed measured solves.

## Limitations
Adaptive transitions retain all currently derived clauses; disabling the policy does not undo earlier CDCL search or restore the exact A trajectory. Entering C7 late also lacks C7's full-history learned-clause metadata. `V24_LIVE_GAUSS` is not an original UNSAT proof unless a separate original-CNF verifier checks a certificate. Adaptive thresholds must be changed only in new preregistered experiments, never retroactively after observing a holdout.

Build script `research/drnas_atlas24_build.py`; runner `research/drnas_atlas24_benchmark.py`; workflow `.github/workflows/drnas-atlas24-live-cdcl.yml`.
