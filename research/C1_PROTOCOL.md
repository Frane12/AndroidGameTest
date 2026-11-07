# DRNAS C1 — Certified Source XOR → CDCL, 2026-11-07

## Pre-implementation evidence and why C1 exists

- Ultimate T/T2: the clean CaDiCaL baseline explains most of the jump versus R153; derived-mode passes show extra cost and no validated general performance gain.
- R2T: live GF(2) delivered **zero confirmed reason clauses** on its 40-run subset despite selecting source rows. Do not infer an active CDCL benefit from mere detection.
- TD exact-bucket diagnostic: 11,912 vs 8 exact XOR pattern hits on previously tested sources; no independent UNSAT proof and no measured solver speedup from detection alone.
- TA: the portfolio solved fewer SHA-disjoint SAT2026 instances than R153. A 20-source tuned policy must not be globally promoted.
- Neural R5: no actual alternate solver activation; excluded from C1 to maintain causal isolation.
- R196/R197: split256 helps a development set but gives no solved instances on a fresh holdout. Keep this independent of C1's causal question.

## Primary preregistered question

Can a *source-certified* XOR user propagator produce **completed reason clauses** with lower PAR-2 than the clean native CDCL and the previous TD lazy baseline, after paying preprocessing and runtime overhead?

## Frozen test

- 20 previously TD-tested originals + 30 TA-tested originals; TA's 30 SHA sources were out-of-set for R1/R2/R193, but **are NOT a new blind holdout for this experiment**.
- Six paired arms: `r153`, `t_clean`, `td_lazy_source`, `c1_lazy_shadow`, `c1_lazy_cooldown`, `c1_lazy_fastwake`.
- Two seeded repetitions, source-wise deterministic mode shuffling, 10 runner shards: **600 attempts**.
- Each arm gets the original manifest's same time cap and SHA-identical DIMACS. A common pinned R153, Kissat, CaDiCaL commit and C1 source binary. Samples run on pinned CPU affinity within shard.
- `c1_lazy_shadow` does certified scans but never returns a propagation literal; this isolates overhead from actual CDCL intervention.
- `c1_lazy_cooldown`: previous exact two-watch lazy source XOR with bounded **32,768 scan → 65,536 notification** cooldown.
- `c1_lazy_fastwake`: sensitivity control, **4,096 scan → 8,192 notification** cooldown. Neither permanently disables an XOR component.
- No speculative pairwise rows, no unsafe source guessing, no modified CNF. Original-source XOR extraction is independently replay-checked before native injection.

## Safety and audit

- Fail closed on SHA drift, missing/duplicate paired mode, wrong native mode, impossible PAR-2, contradictory non-timeout SAT/UNSAT, or incorrect SAT witness on the unchanged original.
- Native XOR reason transfer tests validate clause structure, source parity entailment, callback serialization and backtracking.
- Native UNSAT results lack independent LRAT; clearly label this limitation.
- Report wins/losses/ties, penalized times and solved counts per cohort, reasons completed, direct proposals, shadow candidates, cooldown wakes/skips, and missing terminal telemetry.
- Do not claim a general SAT improvement merely because the build succeeds or C1 detects many XOR patterns.
- Promotion gate: no worsened solved count or PAR-2 on either of the two previously tested source cohorts, plus **at least one actual completed reason**. Passing is only permission for an entirely new independently blinded SAT2026 holdout, never direct promotion to production.

## Sources

- T2: https://github.com/Frane12/AndroidGameTest/actions/runs/42352823564
- TA: https://github.com/Frane12/AndroidGameTest/actions/runs/42353551967
- TD detector: https://github.com/Frane12/AndroidGameTest/actions/runs/42356263207
- R2T: https://github.com/Frane12/AndroidGameTest/actions/runs/42350937691
- R197: https://github.com/Frane12/AndroidGameTest/actions/runs/42340570480
