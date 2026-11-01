# Independent structural validation (40 untouched UUF250 CNFs)
- Input identity manifest sha256: 811801df28c00b77b3747e4a73e2e65f490a0012394d840d14490975fc24b6da
- Attempts: 80, timeouts: 8.
- Preregistered joint rule met: **True**.
| Feature | Holdout Spearman rho | permutation p | BH q | Bootstrap 95% rho |
|---|---:|---:|---:|---|
| degree_gini | -0.4256 | 0.0033 | 0.0050 | [-0.6252949076668063, -0.15467123806083352] |
| degree_cv | -0.4781 | 0.0033 | 0.0050 | [-0.6572545179871426, -0.22982769983993975] |
| reused_varpair_fraction | 0.0805 | 0.5820 | 0.5820 | [-0.21627451917996054, 0.35341081668552127] |

All 40 formulas included; timeout PAR-2=10.6s.
No outcomes, thresholds or formula identities altered after the preregistration.
SATLIB UNSAT status labels not independently proof-validated here.
Statistical association is neither causality nor validation of DRNAS-specific acceleration.
