# DRNAS SAT V15.3.1 + R6 — cumulative analysis

Base SQLite: GitHub Actions run 41341529210; appended R6: 41343506152.
Previous data preserved; R6 adds 40 formulas and 480 attempts.
Generated and already-public SATLIB are labelled separately. This is not official competition validation.

## R6 by formula-level PAR-2 medians

| Category | Strategy | Formula count | Speedup vs monitor | Switches (repeats) |
|---|---|---:|---:|---:|
| r6_external_satlib | stable_v1531 | 10 | 0.7725069x | 0 |
| r6_external_satlib | monitor | 10 | 1.0x | 0 |
| r6_external_satlib | forced_restart25 | 10 | 1.0000887x | 0 |
| r6_external_satlib | r5_frozen_gate | 10 | 1.0099897x | 0 |
| r6_graphcolor | stable_v1531 | 10 | 0.7875684x | 0 |
| r6_graphcolor | monitor | 10 | 1.0x | 0 |
| r6_graphcolor | forced_restart25 | 10 | 0.9881397x | 0 |
| r6_graphcolor | r5_frozen_gate | 10 | 0.9915999x | 0 |
| r6_random3 | stable_v1531 | 10 | 0.9895781x | 0 |
| r6_random3 | monitor | 10 | 1.0x | 0 |
| r6_random3 | forced_restart25 | 10 | 1.000944x | 27 |
| r6_random3 | r5_frozen_gate | 10 | 0.9962694x | 0 |
| r6_xor | stable_v1531 | 10 | 1.7117368x | 0 |
| r6_xor | monitor | 10 | 1.0x | 0 |
| r6_xor | forced_restart25 | 10 | 0.9889522x | 3 |
| r6_xor | r5_frozen_gate | 10 | 0.9953161x | 0 |

## Measured early indicators

Monitor crossed 512 conflicts 36 times across 120 monitor executions.
R5 frozen gate switched 0 times; forced policies switched 30 times overall.
R6 produced 654 observed telemetry points and 60 paired post-action checkpoints.

Feature association computed on distinct formulas (not repeated attempts); results are hypothesis generators only.
Blank values mean the threshold was not reached or the value could not be measured.

## Warehouse and CSV exports

sat_analytics.sqlite, r6_import_audit.json, r6_findings.json,
r6_formula_medians.csv, r6_category_summary.csv,
r6_feature_correlations.csv, r6_dynamics.csv, r6_post_intervention.csv.

## SQLite example

SELECT f.category, a.solver, COUNT(*), SUM(a.par2_seconds)
FROM attempts a JOIN formulas f ON a.dataset=f.dataset AND a.case_name=f.case_name
WHERE a.dataset LIKE 'r6_%' GROUP BY f.category,a.solver;

GLUE RATIO is stored as r6_checkpoint_features.glue_ratio, NOT telemetry.avg_lbd.
All R6 source pins and hashes are in the imported manifest and r6_import_audit.
