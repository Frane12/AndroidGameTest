# DRNAS SAT V15.3.1 — analytical warehouse

This branch adds a **read-only analytics layer** for the frozen V15.3.1 run [41278912894](https://github.com/Frane12/AndroidGameTest/actions/runs/41278912894). It does not change a solver, its restarts or policy.

## Inputs

- `DRNAS-V1531-Regression-168`: **generated development** structural families; previously evaluated.
- `DRNAS-V1531-Mixed-96`: **generated development** mixed XOR instances; previously evaluated.
- `DRNAS-V1531-SATLIB-40-Regression`: **external but previously seen**, non-official SATLIB F.
- `DRNAS-V1531-NoHang-Stress`: **generated stress** (not external holdout).

Never combine those into an advertised independent/official success rate. The separate proposed **4 × 10 never-seen** challenge needs its own frozen corpus manifest, SHA-256 inventory, and untouched run.

## Outputs (GitHub Actions artifact)

`sat_analytics.sqlite` has tables `datasets`, `formulas`, `attempts`, and `telemetry`. CSVs `datasets.csv`, `formulas.csv`, `attempts.csv`, `grouped.csv`, `paired.csv`, `telemetry.csv` and `summary.json` are generated alongside scatter PNGs.

- `scatter_paired_v1531.png`: Kissat vs V15.3.1 median **PAR-2** by formula; below the diagonal is faster.
- `scatter_gain_v1531.png`: per-formula PAR-2 improvement (%) grouped by category.
- Corresponding V15.3 scatter charts are also produced.
- `scatter_conflicts.png` is produced **only when measured telemetry exists**, never from invented conflict counts.

PAR-2 is calculated per attempt as actual wall time for a correct SAT/UNSAT result, or `2 × timeout` for timeouts, wrong/unknown answers. Missing caps prevent PAR-2 calculation. Rows and formula hashes are joined **within the same dataset**. This is a description of paired wall-time, not proof of a universal speedup.

Existing V15.3.1 log JSONs contain wall time and route, plus some SAT model/UNSAT certificate checks. They **do not** contain a continuous conflict/restart/LBD time series; the `telemetry` table is therefore intentionally empty until future passive instrumented logs are added. A solver proof flag is not a claim of an independent competition-grade proof for every UNSAT.

## Run locally

```bash
python3 -m pip install matplotlib
python3 research/tseitin-replay/v1531_analytics_db.py \
  --input raw-artifacts/ \
  --out sat-analysis/ \
  --source-run 41278912894 \
  --source-sha 188600aba8c530a4c20005ee0737fa92735403d3 \
  --runner github-hosted-ubuntu-24.04
```

Example SQL:

```sql
SELECT f.category, a.solver, COUNT(*) AS attempts,
       SUM(a.par2_seconds) AS total_par2
FROM attempts a JOIN formulas f
ON a.dataset=f.dataset AND a.case_name=f.case_name
WHERE a.par2_seconds IS NOT NULL
GROUP BY f.category, a.solver;
```

The workflow `.github/workflows/drnas-v1531-analytics-db.yml` downloads the **existing** reference run's four artifacts, builds this analytical warehouse, and uploads it as a single GitHub Actions artifact. It **does not** run a new benchmark or claim 40 newly unseen cases.
