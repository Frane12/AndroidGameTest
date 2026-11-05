# R152 — Stratified CNF / regret-abstention (pre-registered before benchmark)

Date: 2026-11-05
Branch: `experiment/drnas-r152-stratified-regret-20261105`

## Scientific motivation and falsifiable hypothesis
R150's tiny gain on exposed/then prospective sources came almost entirely from two cryptography formulas. Two old R148 routing errors produced >80 s of PAR-2 regret on official 2025/2026. R151_05 had a prospective +2.75% PAR-2 result over Kissat on 40 separately frozen formulas, but the bootstrap confidence interval included zero; a cautious 1.5-level policy collapsed back to Kissat.

**Hypothesis:** source-wide heterogeneity (binary/Horn/ternary clause statistics) captured with three tiny, disjoint-ish CNF windows (start, center, end) rather than a single prefix allows an abstaining, risk-sensitive portfolio to generalize better across SAT Competition families **without** paying an excessive feature cost. The hypothesis is rejected on the prospective test if it does not improve the solved count and paired PAR-2 robustly against Kissat, unchanged R148, and R151_05.

## Implementation
- Native `research/r152_stratified_selector.cpp`: at most three 64 KiB windows and 1,024 terminated clauses per window; deterministic sampling, read-only original CNF.
- 24 bounded features: four global header/size values, 6 clause metrics per window (binary, Horn, ternary, normalized mean length, positive polarity, coverage), plus spread of binary and Horn proportions.
- KNN (K=24) with per-feature historical scales and full **unclipped** two-repetition PAR-2 regret target `PAR-2(CaDiCaL) - PAR-2(Kissat)`; one C++ process performs the sampling and final decision.
- Safe fallback: choose CaDiCaL only when `mean_regret + z*SE < -0.5s`, otherwise abstain to Kissat. Two pre-fixed `z`: 0.5 and 1.5. No use of formula IDs for routing, no solver/CNF edits.
- Model trained on the pre-existing 400 original CNFs and 4,000 previously collected historical trials. Leave-one-whole-cohort-out crossfit is recorded only as a historical *diagnostic*; it cannot justify promotion.

## Frozen prospective benchmark
- Predeclared source quotas: official2026=12, official2025=12, cryptography=10, miter=10, xor_shifting=10, uniform_random=10 (up to 64 original real CNFs, accept 48–64 with ≥5 family groups if source availability limits acquisition).
- SHA/URL/source identifier exclusions from R135 original 400, R132 125, R135 56, R135S 21, R148 50, R150 55, R151 40. These are the accessible known ledgers, not exhaustive lifetime exclusion.
- Freeze every original source SHA and full DIMACS clause-count validation **before any prospective solver timing**. Never choose by speed, structure, or performance.
- Six paired methods: pure Kissat, pure CaDiCaL, exact frozen R148, pinned R151_05 model, R152_05, R152_15; same original CNF, pinned binaries, 2 paired repeats, 15-second cap, randomized order and eight shards.
- With 64 cases: 768 paired trials. Timeout PAR-2 = 30s. SAT models checked against the original unmodified CNF, UNSAT is **not** independently LRAT/FRAT certified.
- Final audit: number solved, timeouts, SAT and UNSAT tier, individual and aggregate PAR-2, solved median, 2x regressions, bootstrap 95% by source cohort, both directions of route changes, measured detector overhead, exact binary/model SHA, per-formula CSV and source provenance.
- CPU model may differ between shards, but every formula's baseline/candidate is measured within the same shard. Subsecond gains remain vulnerable to runner noise. No formula-specific post-hoc tuning.

## References
- R150 completed: https://github.com/Frane12/AndroidGameTest/actions/runs/42088721067
- R150 causal forensics: https://github.com/Frane12/AndroidGameTest/blob/experiment/drnas-r150-forensics-20261105/research/R150-DEEP-FORENSICS-20261105.md
- R151 completed independent 40: https://github.com/Frane12/AndroidGameTest/actions/runs/42094754907
- R17 external 24 audited retrospective: https://github.com/Frane12/AndroidGameTest/actions/runs/42100654382

**Promotion guard:** do not call R152 best unless a *new* independent cohort and repeated paired validation demonstrate reliable improvement in both solved count and PAR-2 without unacceptable individual regressions or correctness failures. Reject or transparently report negative results. No main branch or frozen baseline changes.
