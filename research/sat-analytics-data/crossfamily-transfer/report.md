# DRNAS SAT -- preregistered cross-family structural transfer
**159 real SATLIB formulas, 40+40+39+40, 318 upstream Kissat attempts.**
Prespecified transfer criterion met: **False**.
All inputs SHA-1 verified, per-formula SHA-256 frozen before timing.

| Family | Gini rho | Degree CV rho | Pair reuse rho | Timeout attempts / category ||---|---:|---:|---:|---:|
| uf200-860 | -0.1906 | -0.1894 | -0.0963 | 0 |
| uf250-1065 | -0.0199 | -0.0322 | +0.3812 | 0 |
| uuf200-860 | -0.4962 | -0.4960 | -0.2724 | 0 |
| flat200-479 | +0.0334 | +0.0554 | N/A (no variance) | 0 |

## Within-family pooled rank-effect (Fisher z, strata preserved)
| Feature | Pooled rho | Permutation p | BH q |
|---|---:|---:|---:|
| degree_gini | -0.1766 | 0.0302 | 0.0543 |
| degree_cv | -0.1738 | 0.0362 | 0.0543 |
| reused_varpair_fraction | N/A | N/A (not estimable across all four families) | N/A (not estimable across all four families) |

**Interpretation:** A feature that predicts harder original Kissat instances in one random SATLIB family may fail on SAT, graph-coloring, or other structural classes. A failed transfer does not invalidate the original within-family finding.
No interventions; original Kissat only; no independently verified UNSAT proof for original Kissat.
