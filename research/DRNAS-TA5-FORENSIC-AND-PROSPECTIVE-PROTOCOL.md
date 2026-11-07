# DRNAS TA5 — frozen forensic findings and next prospective validation (2026-11-07)

**Status:** evidence review and preregistration; **NO TA5 performance claim**. No edits to main. This document is derived from audited source-locked workflows, not preliminary shards.

## Pinned evidence

| Cohort | Final GitHub Actions audit | Original formulas | Runs | Verdict |
|---|---|---:|---:|---|
| R199 mixed SAT2025 | [42390697619](https://github.com/Frane12/AndroidGameTest/actions/runs/42390697619) | 40 | 720 | PASS |
| TK planted mixed XOR | [42391271033](https://github.com/Frane12/AndroidGameTest/actions/runs/42391271033) | 12 deterministic generated | 108 | PASS; negative finding |
| TA2 source-only structure | [42391835603](https://github.com/Frane12/AndroidGameTest/actions/runs/42391835603) | 40 (same R199 sources) | 40 profiles | PASS; NOT a selector benchmark |
| TA3 official SAT2026 | [42398019262](https://github.com/Frane12/AndroidGameTest/actions/runs/42398019262) | 24 | 384 recovered trials | PASS; original [42396350093](https://github.com/Frane12/AndroidGameTest/actions/runs/42396350093) solver data |
| TA4 SAT2025 | [42395771235](https://github.com/Frane12/AndroidGameTest/actions/runs/42395771235) | 15 | 240 | PASS |

WorldSim W1 [42397824391](https://github.com/Frane12/AndroidGameTest/actions/runs/42397824391): at the time of this review its eight shards were still running; no final verdict recorded.

## Exact PAR-2 scores within each cohort

### R199 (120 paired attempts per mode, cap 20s, PAR-2 totals)

| Mode | Solved | PAR-2 s | Difference from its plain host |
|---|---:|---:|---:|
| Kissat plain | 33/120 | 3560.914758 | baseline |
| Kissat R28 | 36/120 | 3440.828233 | +120.086525 s, 3.37% reduction |
| Kissat GF2 hybrid | 36/120 | 3457.011651 | +103.903107 s, 2.92% reduction |
| CMS plain | 30/120 | 3684.655586 | baseline |
| CMS R28 | 30/120 | 3680.083215 | +4.572371 s, 0.12% reduction |
| CMS GF2 hybrid | 30/120 | 3700.683560 | -16.027974 s (regression) |

Of Kissat R28's total 120.086525 s PAR-2 improvement, **119.907267 s (99.85%) was in the xor_crypto cohort**. The other 3 cohorts combined change by +0.179258 s PAR-2, too small to claim meaningful benefit. The aggregate can hide losses in individual solved pairs: 21 losses, 13 wins, 86 ties for Kissat R28 versus Kissat plain.

The GF2-CMS industrial_planning subset loses 90.624857 s, outweighing its +78.971955 s hardware_software gain and smaller losses elsewhere. This is a strong **no-default-GF2-CMS** signal for this tested population, not an impossibility proof for any new method.

### TA3 and TA4 (not the same evaluation cohort)

- TA3-2026: 24 originals x 2 reps x 8 arms = 384 attempts; portfolio 10/48, PAR-2 1582.844897; plain Kissat 6/48, 1705.965230; plain CMS 6/48, 1723.827576. Relative PAR-2 reductions 7.217% and 8.178%.
- TA4: 15 originals x 2 reps x 8 arms = 240 attempts; TA4 pilot 8/30, 962.587782; TA3 portfolio 8/30, 963.287414; difference 0.699632 s (0.073%), no additional solves. A 0.073% edge is too small to promote to a general causal gain without repeatability.

### TK: live XOR reason mechanism has not fired

T clean 1.575181 s; C1 lazy shadow 1.722849 s; active cooldown 1.740688 s (36 attempts each, all solved). **Proposals = 0; reasons = 0**. Active is 10.51% slower than clean by total elapsed/PAR-2 in this tiny generated planted cohort. This is not evidence of a live GF2→CDCL reasoning win.

### TA2 structural fingerprint cost and labels

40 source-only fingerprints; average scan 35.455 ms, maximum 61.499 ms, capped at 16k clauses/160k literals. Tags: complete_xor3_sample 19, binary_implication_dominant 10, horn_dominant 2, long_clause_dominant 2, mixed_generic 7. These are heuristics based only on sampled DIMACS, not validated solver route labels. No solver outcomes were used to build the fingerprints. Crucially, TA2 used the SAME 40 source SHA values as R199: any fitted threshold or routing rule evaluated on R199 is exploratory, **not blind**.

## TA5 preregistered experiment design

1. **Hypothesis:** a cheap source-only selector can preserve R28+Kissat's verified xor_crypto gain while avoiding preprocessing on clearly non-XOR source formulas, and can be calibrated against the native Kissat baseline. Test this; do not assert it before prospective results.
2. Fix an immutable classifier **before opening any new benchmark outcomes**. Candidate arms: plain Kissat, always R28+Kissat, a frozen 16k-clause source-only XOR gate, always GF2+Kissat, plain CMS, and a frozen TA3 portfolio. An isolated shadow arm measures gate-only cost and decisions.
3. Obtain a **new source-SHA-disjoint evaluation**: exclude every original in the R199, TA3, TA4, WorldSim W1, R189, R194 and R115 manifests; verify the SHA set in the prepare job before launching solver trials. Do not use source-family names as hidden route labels unless explicitly declared.
4. Run all arms with identical source CNF SHA, fixed solver versions, fixed seed list, per-arm wall cap and randomized execution order. Repeat at least 3 times for each new original. Report SAT and UNSAT separately, and independent witness/proof verification where supported. Charge feature scans and preprocessing to total elapsed time.
5. Report per-source paired winners/losses/ties, solved counts, family-specific PAR-2, aggregate PAR-2, confidence intervals across original formulas, memory, feature and preprocessing overhead, and worst regression (especially formulas taking <0.1s on the baseline).
6. Promotion gates: no missing proof/witness audits; no extra false SAT/UNSAT; added solves vs plain Kissat, positive prospective PAR-2 delta, and no unacceptable per-instance severe regression. If gate cannot improve over always-R28, leave it in research only.
7. Only after a **successful new blind holdout**, evaluate certified XOR-to-CNF clause communication as a separate causal intervention (clean/shadow/live), requiring actual nonzero injected reasons. Do not attribute the TA3 portfolio effect to a novel underlying CDCL algorithm.

This file is a frozen research handoff, not a claim of a run launched or completed. Incremental SQL migration: `research/drnas_sat_benchmark_increment_20261107.sql`.
