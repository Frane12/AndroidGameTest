# DRNAS SAT / ORION — Independent Reproduction and Audit Guide

**Author:** Frane Drnas · **Updated:** 2026-11-10 · **Status:** research-stage; not peer-reviewed

This guide is aimed at an independent researcher who wants to verify specific claims **on the original DIMACS CNF**, rather than accept benchmark headlines alone. It links public evidence but **does not assert that all required source files, proof artifacts, pinned binaries or CI artifacts remain permanently downloadable**.

## Start with these exact runs

| Study | Original input and experiment | Evidence | Correct interpretation |
| --- | --- | --- | --- |
| [**R32q**](https://github.com/Frane12/AndroidGameTest/actions/runs/41658992807) | One known official-source XOR case, two repeats | [Raw results artifact](https://github.com/Frane12/AndroidGameTest/actions/runs/41658992807/artifacts/13239399691) · [pinned source](https://github.com/Frane12/AndroidGameTest/tree/95b2b06f16efc68827ed34de9cbc1bda7b6a0a37) | Verified SAT witnesses, two R28 timings of 0.004179/0.004189 s; Kissat timeout after 60 s twice. **>14,340× is a censored lower bound**, not measured complete-run ratio |
| [**R194**](https://github.com/Frane12/AndroidGameTest/actions/runs/42386841737) | 38 cases × 6 modes × 2 repeats = 456 trials | [Final audit artifact](https://github.com/Frane12/AndroidGameTest/actions/runs/42386841737/artifacts/13579769872) · [pinned source](https://github.com/Frane12/AndroidGameTest/tree/8229dc79bbb55577e1f0850ea3153a6740d18d38) | Cohort **PAR-2**, not 14,000× broad speedup: CMS plain 758.878 s vs CMS + R28 655.967 s; Kissat plain 1209.259 s vs Kissat + R28 864.852 s |
| [**R189**](https://github.com/Frane12/AndroidGameTest/actions/runs/42228208905) | 38 cases; selective source-certified gate | [Research dossier](../research/DRNAS_ORION_2026-11-06_PUBLIC_REVIEW.md) · [pinned source](https://github.com/Frane12/AndroidGameTest/tree/7728bc0d9b7caa29e6547319953f79035b26d747) | Selective gate PAR-2 1085.118 s vs clean 1514.506 s on that cohort, not a blind generalizable result |

R32q original benchmark database ID: `75429ff7acb5acb597abe01aa745c2a6`. Original CNF **SHA-256**:
`243e5d0079606862166a4619691cbbb8ffc9c8c14eb16250138b16d724c6bc83` (250 variables, 1,000 clauses).

## Independent auditor checklist

1. **Pin identity.** Record original formula name/source, raw DIMACS SHA-256 (not just a transformed file), Git commit, binary hash and exact test command. If any item is unavailable, report this as an artifact gap.
2. **Collect raw runs.** Download the linked GitHub Actions artifacts (sign-in may be necessary; expiration is possible), including per-trial JSON, stderr/stdout and workflow log. Distinguish original-CNF results from preprocessed, derived or bounded-CDCL results.
3. **Match conditions.** Check solver versions, flags, runner/CPU information, logical CPU affinity, RAM, timeout, wall vs CPU time, repetitions and seed/order. Four parallel CI *shards* do not establish four-core speedup.
4. **Recheck SAT.** Parse the SAT assignment from each trial and evaluate every clause of the **unmodified original DIMACS**. A successful subprocess exit or transformed-formula witness is insufficient without the original check.
5. **Recheck UNSAT.** Require a proof linked to the **original** CNF and independently verify it (for example with a compatible LRAT/FRAT/DRAT pipeline and external checker; verify the exact proof format and conversion). If proof is missing or not independently checked, label it **UNSAT claimed / independent certificate not established**. Do not infer certification from `UNSAT` in a solver log.
6. **Recompute PAR-2.** For each attempted solve with time cap `T`, contribute recorded solve time if solved within cap, or `2T` on timeout. Sum consistently across exactly the same cases and repetitions. Also report solved/total, timeouts, regressions, per-family data and the timing definition.
7. **Check claims.** A baseline timeout gives a lower bound `T / measured_DRNAS_time`, not the baseline's true runtime. Compare paired cases with equal limits; do not treat an aggregate PAR-2 ratio as an uncensored per-instance speedup.
8. **Report reproducibility gaps.** Publish negative outcomes, missing artifacts, failed independent checks, hardware changes and any source/formula that cannot be located. A fully independent reproduction must not silently reuse a development set.

## R194 published PAR-2 cross-check

Each mode has 76 attempts (38 formulas × 2 repeats):

| Mode | Solved / 76 | PAR-2 seconds | Ratio vs corresponding plain |
| --- | ---: | ---: | ---: |
| CryptoMiniSat plain | 52 | 758.878 | 1.00× |
| CryptoMiniSat + R28 route | 52 | 655.967 | **1.16×** |
| CryptoMiniSat + GF(2) hybrid | 52 | 674.599 | **1.12×** |
| Kissat plain | 26 | 1209.259 | 1.00× |
| Kissat + R28 route | 40 | 864.852 | **1.40×** |
| Kissat + GF(2) hybrid | 40 | 867.566 | **1.39×** |

The reported ratios are **plain aggregate PAR-2 divided by variant aggregate PAR-2** on this particular source-selected study, not a universal SAT performance ranking. [Original research-status table](../research/DRNAS_SAT_STATUS.md).

## Proposed prospective blind protocol (future work, not a completed validation)

- Freeze a development selection rule, classifier/gate settings and a SHA-disjoint untouched evaluation list **before** trial results are observed.
- Include multiple diverse SAT and UNSAT families, clean XOR, partial/hidden XOR, mixed CNF and non-XOR negative controls.
- Compare plain Kissat, plain CaDiCaL, plain CryptoMiniSat, R28 route, selective gate, and (only if implemented and independently correct) native end-to-end DRNAS.
- Run each solver with **one logical CPU per arm**, matched time/memory limits and preregistered repetition policy. Keep multi-core portfolios separate.
- Produce a public frozen manifest, original-CNF witness/proof audit, per-formula and per-family solved/PAR-2 summary, confidence intervals, regressions and an untouched holdout report.
- Clearly differentiate diagnostic telemetry (GF(2) proposals, passive trail observations, bounded-CDCL steps) from independently verified end-to-end SAT/UNSAT results.

## Request for independent reviewers

Please submit findings through [Issues](https://github.com/Frane12/AndroidGameTest/issues) with a **source SHA, experiment run ID, formula SHA-256, exact artifact, solver flags, outcome, SAT witness/UNSAT proof verification status and reproduced timings**. Independent refutation, regressions and failure to generalize are welcome.

[Architecture](ARCHITECTURE.md) · [Research status](../research/DRNAS_SAT_STATUS.md) · [ORION scientific dossier](../research/DRNAS_ORION_2026-11-06_PUBLIC_REVIEW.md)
