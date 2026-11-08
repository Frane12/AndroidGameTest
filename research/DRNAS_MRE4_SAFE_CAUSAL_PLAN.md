# DRNAS MRE4 — Safe Causal Mathematical Reduction (P1)
2026-11-08 · Experimental branch `experiment/drnas-mre4-safe-causal-20261108`

## Purpose
**Do not simply produce more XOR rows.** Prove that any mathematical reduction is original-CNF implied, low-cost, useful and safe, then measure causal native CDCL effects.

## Retained from the successful research
- **R28 / R164:** exact pure-XOR mathematical fast path only if the original SAT witness passes a full-CNF check. UNSAT XOR certificate is checked but *not accepted as an independent LRAT*, so conservative R28 route falls back to CMS for UNSAT.
- **R194:** hybrid is a portfolio, not unconditional additional work.
- **R195:** C++ API to pinned CryptoMiniSat 5.11.15 and independently verified original SAT models.
- **MRE1/CRR1A:** source-complete XOR detection; deterministic truth-table replay; resolution / GF(2) proof replay for each derived short CNF lemma.
- **MRE2/MRE3:** native CMS CDCL counters and source-paired shadow/active ablation; cheap DIMACS-header guard before expensive Python parsing.
- **T6A:** very small end-to-end preparation budgets and abstention on no predicted novel BCP impact.
- **YalSAT R2:** useful concept of selective gating, NOT enabled by default: new official-source holdout showed no SAT scout win.

## Disabled until separate safety and causality proof
- CMS on-the-fly Gaussian option `set_allow_otf_gauss()`, which generated invalid SAT witness in R195 active imports.
- Unchecked or guessed XOR rows, partial XOR blocks, wide unverified clauses and mass derived XOR import.
- Full-CNF or quadratic gate before an early cheap eligibility check.
- Compulsory SAT scouting, long unconditional Gaussian preprocessing, or >2 active derived CRR lemmas.
- Calling global change of propagations/conflicts an actual per-lemma *reason event*; R195 / MRE3 did not yet instrument inside CMS.
- Treating native UNSAT as independently LRAT certified.

## Stage P1: 32 prior SHA-pinned development sources
Five modes, two seeds, 30 seconds, 8 shards → **320 attempts**:
- `cms_native`: clean CMS control, OTF Gaussian OFF.
- `r28_safe`: guarded exact pure-XOR SAT fast path; otherwise clean CMS.
- `xor_no_otf`: source-certified XORs only, OTF Gaussian OFF.
- `crr_shadow`: same derivation/gate and source XORs as active, no additional CNF clauses.
- `crr_active`: same prep, at most two proven short clauses, only when measured bounded pre-solve UP effect is substantial.

Every mode uses exact source SHA, same seed, original model validation, full wall timing, PAR-2. Separate official/synthetic cohorts in audit. Per-lemma *causal clause presence* evaluation is not a direct in-CDCL callback.

## Strict promotion gates
1. Original SAT witness always verified (native C++ and outer Python).
2. No unsafe OTF Gaussian; all derived clauses independently proof-replayed.
3. Active must beat its exact-prep shadow and source-XOR-only control, not merely pure CMS.
4. Measured active gain must exceed extra cost and show no significant regression.
5. Source-instrumented CMS watch/reason telemetry needed before a *live per-lemma reason* claim.
6. Only then select genuinely new original SAT competition holdout cases, lock all SHA, run paired blind evaluation, validate UNSAT with independent proof or state it is unverified.

## Interpretation
A green build with zero active imports is a *correct abstention*, NOT an active solver speed breakthrough. A win on reused SAT2026 sources is developmental evidence, NOT a new world-record claim.
