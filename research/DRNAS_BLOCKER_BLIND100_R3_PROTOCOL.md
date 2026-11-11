# DRNAS BLOCKER-BLIND100-R3 — frozen protocol (11 November 2026)

## Hypothesis
The proof-safe cached-blocker watched-literal implementation `DRNAS_ONE2_BLOCKER` reduces DRNAS native end-to-end cost on previously unseen source CNFs, without loss of SAT model correctness. The target is real-world search and BCP throughput, not an artificial two-pass learning procedure.

## Prospective cohort
- 20 fixed source families: original SATLIB `uf100-430`, `uuf100-430`, `uf250-1065`, `uuf250-1065`, `flat200-479`; and 15 source-frozen synthetic families from `research/drnas_atlas_wide500.py`.
- Fixed first 35 sources per SATLIB family chosen using frozen pinned SHA-256 archive and deterministic hash order; **use indices 30–34 only**, never indices 0–29 previously used in WIDE500 or Prospective3.
- Each of five shards handles one fresh index across all 20 categories. Exactly 100 SHA-distinct selected CNFs, 25 original SATLIB / 75 deterministic synthetic.
- Reject SHA overlap with earlier 400-source training table or prior 100-source prospective cohort. Merged results additionally check all 100 SHA uniqueness and 3-arm, 3-repetition pairing.

## Solver arms and controls
- `A`: DRNAS ATLAS-MAP2 native engine `--mode A`, built `-O2`.
- `BLOCKER`: **same** native source and optimization `-O2`, with just `-DDRNAS_ONE2_BLOCKER`.
- `KISSAT`: upstream Kissat commit `8af8e56f174b778aef3aa45af9f739b2a5f492c2`, configured and built from source.
- No `DRNAS_PROFILE`, no `DRNAS_WATCH_DIAG`, no `DRNAS_ATLAS_TRAIN_TRACE`. One logical CPU pinned per shard; engines measured sequentially, so each solver gets one CPU while run's distinct shards may use distinct GitHub runners.
- Three repeated attempts per source per solver, 8-second limit per attempt. 900 process attempts overall. Source generation and archive download are not charged to solve E2E; process spawn, DIMACS parse, solver execution and original SAT witness verification are part of observed E2E (verification is also independently repeated by the harness).
- Source CNF is byte-identical across all three arms, repetitions and oneCPU comparisons.

## Outcome rules
- `SAT` only if original CNF model is independently checked by the harness; fail if a claimed SAT model is missing or false.
- `UNSAT_UNCERTIFIED` is the solver's UNSAT exit status without independently checked proof; do not label as certified UNSAT.
- `UNKNOWN` / timeout gets 16 s PAR-2 penalty.
- Report both (1) **reported-status PAR-2** (SAT witness verified + solver UNSAT claim) and (2) **independently verified SAT-only PAR-2** (all unproven UNSAT also incur penalty). Report solved counts for each class separately.
- Before considering production-default switch, require meaningful win on source-original SATLIB and no serious regression on previously unseen categories; compare with reference Kissat and report paired outliers.

## Audit provenance
- Workflow run GitHub Actions: https://github.com/Frane12/AndroidGameTest/actions/workflows/drnas-blocker-blind100-r3.yml
- Code: `research/drnas_blocker_blind100_r3.py`, `.github/workflows/drnas-blocker-blind100-r3.yml`.
- Every shard uploads a SHA manifest, per-trial machine-readable audit and raw log. Merge checks 100 SHA, 20 families, 3 repetitions, 3 arms and publishes `research/drnas_blocker_blind100_r3_summary.json`.
- Main remains untouched.
