# DRNAS MRE7 — prospective easy-original gate test (precommitted protocol)

2026-11-08. Branch: `experiment/drnas-mre7-prospective-easy-gate-20261108`

## Motivation

MRE6f repeated a real fixed-conflict signal: original official SAT2026 `2fcd8533...` yielded ~35.09% fewer propagations and ~1.21x faster full wall over three repetitions at 5,000 conflicts. No solver finished; this is not an end-to-end SAT proof or a new blind test. Small-equality control regressed strongly.

## Source selection and leakage controls

- SAT2026 scout run [42500711059](https://github.com/Frane12/AndroidGameTest/actions/runs/42500711059) found only 1 eligible CaDiCaL3 reference-easy source in the prior-source-disjoint range 0.1–5s. Do not present the old SAT2026 cohort as 20 fresh easy originals.
- New MRE7 freeze draws from published SAT2024 and SAT2025 Main Track GBD source identifiers; hashes and source files are verified. Exclude historical manually enumerated GBD IDs, all IDs visibly in checked-out research scripts, and a conservative 220-ID prior R82 SAT2025 SHA-ranked region.
- Candidate order is salted SHA-rank interleaving 2024/2025, **independent of the gate**. Up to 180 attempted downloads. Fixed compressed/plainsize, variable, clause limits. Never discard a case because MRE performance is poor; all candidate rejection reasons are logged.
- A reference-only CMS 5.11.15 solver with original-input SAT model replay selects approx. 0.08–5s solving cases (24 target, minimum 20). UNSAT additionally needs a concordant CaDiCaL result. This is reference-easiness-conditioned holdout, **not a uniform random sample**.
- Important: the accessible historical registry is not guaranteed globally exhaustive; do not call this dataset universally unseen.

## Solver benchmark

- All four arms receive the **same exact frozen original source SHA**. Within CMS arms, the seed is identical and deterministically derived from the SHA and repetition. Kissat uses its documented native default settings on the same source.
- Modes: `cms_native`, `all_equalities`, `gate_auto`, `kissat` (pinned Kissat 4.0.4). Each input has two repetitions, total wall cap 8.0 s per arm, including all parsing/preprocessing/starting/solving/witness audit.
- `all_equalities` uses only original-CNF binary positive equivalences, verified by replay, with transitive closure and SAT-model lifting back to original.
- Frozen **MRE7 gate** (before all result observation):
  - at least 64 removed clauses and 6% fewer clauses;
  - at least 32 merged/eliminated variables and 4% fewer variables;
  - otherwise fall back to original CMS (preprocessing overhead is still counted).
- Gate does not use observed holdout solve-time, conflicts, solved status, Python benchmark labels, test set family, or result-dependent adaptive tuning.
- Report per-arm original SAT witnesses independently checked. UNSAT is cross-solver-consistent but no independently verified LRAT; do **not** report it as an independently certified UNSAT proof.
- PAR-2 for timeouts is 16s per attempt. Report solved SAT/UNSAT (UNSAT labeled as unverified LRAT), median and aggregate wall including prep, per-case paired regressions, and gate activation.
- No automatic deployment or main-branch changes: promotion requires independent follow-up with harder genuinely fresh SHA-disjoint sources, complete verification, and net positive overall time.

## CI runs

- Source scout: https://github.com/Frane12/AndroidGameTest/actions/runs/42500711059
- Pre-gate original freeze: https://github.com/Frane12/AndroidGameTest/actions/runs/42501143598
- Prospective four-arm 8s PAR2: https://github.com/Frane12/AndroidGameTest/actions/runs/42501527378
