# DRNAS SAT -- preregistered cross-family structural transfer
**159 real SATLIB formulas, 40+40+39+40, 318 upstream Kissat attempts.**
Prespecified transfer criterion met: **False**.
All inputs SHA-1 verified, per-formula SHA-256 frozen before timing.

| Family | Gini rho | Degree CV rho | Pair reuse rho | Timeout attempts / category ||---|---:|---:|---:|---:|
| uf200-860 | -0.1938 | -0.1898 | -0.0923 | 0 |
| uf250-1065 | +0.0347 | +0.0144 | +0.4174 | 0 |
| uuf200-860 | -0.5000 | -0.4984 | -0.2642 | 0 |
| flat200-479 | +0.0276 | +0.0485 | N/A (no variance) | 0 |

## Within-family pooled rank-effect (Fisher z, strata preserved)
| Feature | Pooled rho | Permutation p | BH q |
|---|---:|---:|---:|
| degree_gini | -0.1667 | 0.0406 | 0.0456 |
| degree_cv | -0.1650 | 0.0456 | 0.0456 |
| reused_varpair_fraction | N/A | N/A (not estimable across all four families) | N/A (not estimable across all four families) |

**Interpretation:** A feature that predicts harder original Kissat instances in one random SATLIB family may fail on SAT, graph-coloring, or other structural classes. A failed transfer does not invalidate the original within-family finding.
No interventions; original Kissat only; no independently verified UNSAT proof for original Kissat.
