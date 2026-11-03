# DRNAS R23 — Structural-link risk guard (shadow validation)

Date: 2026-11-03. Source branch: `experiment/drnas-r23-structural-links-shadow-20261103`.

## Purpose
Distinguish superficially similar SAT CNFs that respond differently to the same restart intervention. Model reads *pre-solve* variable / clause link topology. This is **not** an exact dynamic 1-UIP implication graph. Do not infer cause from feature differences.

## Evidence and reproducibility
- Historical inputs are SHA-pinned R21 archived verified same-binary native MONITOR and forced-2048/50 measurements.
- R21 160 generated CNFs reconstructed and each full DIMACS sha256 independently checked against archived catalog.
- Development: 80 CNFs; blind test: 80 CNFs, no training or threshold fitting on test outcomes.
- Frozen conservative k=7 same-family/same-n nearest-neighbor guard. Zero catastrophic neighbors plus positive local gain required; otherwise abstain to monitor.
- Toy binary-CNF chain (depth 4) vs star (depth 1) checks structural difference.
- Workflow run: https://github.com/Frane12/AndroidGameTest/actions/runs/41600852893
- Artifact: `DRNAS-R23-Structural-Link-Shadow-Guard-R21-Blind-Holdout`, includes `model.json`, `report.json`, `holdout_decisions.csv`.

## Actual measured historical counterfactual result (seconds)

| Fold (80 CNFs each) | R21 monitor | R21 always-forced | R23 shadow | R23 triggers | Always-forced >2× regressions | R23 >2× regressions |
|---|---:|---:|---:|---:|---:|---:|
| Development (leave-one-out) | 144.849185 | 142.119813 | 144.849185 | 0 | 2 | 0 |
| Blind test | 89.579692 | 80.545727 | 89.579692 | 0 | 3 | 0 |

**Result: valid negative finding.** R23's conservative rule makes no interventions. It avoids regressions only by abstaining and also misses a 10.08% aggregate forced50 benefit on the holdout. No improvement claim. Offline replay does not include live feature-extraction overhead.

## Matched development examples

| Formula | Monitor | Forced 2048/50 | Change vs monitor |
|---|---:|---:|---:|
| `r21_random3_200_development_0_05.cnf` | 1.355345 s | 0.920180 s | +32.11% gain |
| `r21_random3_200_development_1_09.cnf` | 0.286916 s | 0.422339 s | -47.20% gain |
| `r21_random3_220_development_0_01.cnf` | 0.940616 s | 0.837604 s | +10.95% gain |
| `r21_random3_220_development_0_05.cnf` | 0.802199 s | 1.282010 s | -59.81% gain |

Near-matched coarse features disagree in outcome. Candidate distinctive static structural metrics include repeated variable pairs, signed-pair motif diversity and cross-partition links. They do not yet predict effect reliably.

## Next scientific test
Do **not** lower thresholds and re-report the same R21 test as blind. Instead, collect exact dynamic implication-chain topology (antecedent edges, UIP depth, fan-in, crossings, role of mature clauses) at frozen 256/512/1024 conflict snapshots, define a new risk rule on development only, and evaluate prospectively on entirely new SHA-distinct CNFs. If uncertainty is high or a safeguard fails, default to monitor.

No changes to production Kissat or the prior R22 frozen protocol.
