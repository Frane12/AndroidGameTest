# DRNAS MATH Ω4.2 — actual CDCL component-local GF(2) audit (2026-11-13)

**Result:** source-certified online GF(2) reasoning now runs on affected XOR components rather than the entire system. Math scan time improves, but no aggregate solver PAR-2 or solved-count gain. **Do not promote to main or frozen champion.**

## Primary frozen historical-development benchmark
[Run 43519470159](https://github.com/Frane12/AndroidGameTest/actions/runs/43519470159) · [Raw audit artifact](https://github.com/Frane12/AndroidGameTest/actions/runs/43519470159/artifacts/14082557445)

16 historical original SHA-verified CNFs, 4 synthetic controls, 6 modes × 2 repeats = **240 paired attempts**; CaDiCaL 2.1.0 IPASIR-UP, same compiled binary, one logical CPU per attempt, 5-second E2E cap. Historical examples were previously exposed, so **not blind**.

| Mode | Reported PAR-2 on 32 external attempts (s) | Math scan time (ms) | Completed reasons | External conflict clauses |
| --- | ---: | ---: | ---: | ---: |
| Clean CaDiCaL | **280.087729** | 0 | 0 | 0 |
| Full live Ω4 | 280.226374 | 693.934 | 60 | 28 |
| Cost-gated Ω4.1 | 280.226347 | 405.767 | 114 | 172 |
| Component Ω4.2 | 280.225512 | **237.295** | 88 | 1628 |
| Component shadow | 280.226122 | 199.981 | 0 | 0 |

Each mode: 4 backend-reported UNSAT, 28 unresolved (18 UNKNOWN, 10 TIMEOUT). Original-CNF UNSAT proof is **not independently LRAT/DRAT checked**; independently verified PAR-2 = 320.0 s for each mode.

Math scanning cost decrease: 41.5% vs Ω4.1 and 65.8% vs full Ω4. No additional solved formula, no aggregate end-to-end win. 1628 conflict clauses are **emitted clauses, NOT independently demonstrated unique or useful CDCL conflicts**. Their usefulness and duplication need independent measurement.

## Independent correctness and execution audit

1. [Extractor CI 43520756910](https://github.com/Frane12/AndroidGameTest/actions/runs/43520756910): 320 independent deterministic CNF source-mask cases, including 27 original formulas entailing contradictory parities on one support and 46 incomplete-XOR negative controls; **942 certified parity rows, zero incorrectly exported rows**.
2. Found and fixed a **fail-closed extractor-ordering error**: comparing two equivalent but differently ordered row lists when both parities of one support are source-entailment. The new `research/omega42_source_rows.cpp` canonicalizes independent rows before comparison; source certification remains mandatory.
3. Found and fixed an **independent SAT witness auditor error**: an unassigned variable must not be treated as False when checking a negative literal. `research/omega42_benchmark.py` now checks that a literal is assigned before using it to satisfy a clause. Regression passed in CI 43520756910; native CaDiCaL already checked each original clause using `solver.val()`.
4. Separate offline exhaustive ground-truth test: **440 small random CNFs × 4 modes = 1760 executions**, with 364 SAT and 76 UNSAT per mode, zero mismatched verdicts, zero invalid SAT models, zero source-proof replay errors. All 440 were rerun with corrected extractor.
5. Main 240-trial benchmark: no SAT/UNSAT cross-mode disagreement or source-proof runtime exception. 296 reason antecedent literals checked on actual CDCL trails. Four tiny synthetic controls gave the same truth status across all six arms.

**Limits:** exhaustive ground-truth test was on only 5–10-variable synthetic formulas; there is no full formal proof that all possible CDCL callback schedules are free of errors. On real formula runs, independently checked UNSAT proofs are still missing. Native CDCL conflict/decision counters have incomplete coverage (22/32 and 18/32); at a time cap fewer conflicts do not necessarily mean faster searching.

## Implementation

- Research-only branch: `experiment/drnas-math-omega42-20261113`.
- Source-certified native component bridge: `research/omega42_live_gf2.cpp`.
- Source-only XOR extractor with contradictory-parity ordering fix: `research/omega42_source_rows.cpp`.
- Six-arm 240-trial benchmark: `research/omega42_benchmark.py`.
- Independent extractor test: `research/omega42_extractor_regression.py`.
- CI: `.github/workflows/drnas-math-omega42.yml` and `.github/workflows/drnas-math-omega42-extractor-audit.yml`.

The gate is heuristic only. **Only source-certified, independently reconstructed GF(2) rows justify outgoing clauses.** Upon CDCL assignment changes/backtracking, impacted components are marked dirty, pending proposals are invalidated, obsolete reason caches are dropped, and every returned reason antecedent is checked against the current trail. Main and frozen references untouched.

## Decision

Keep as experiment. Next development check should measure **unique vs duplicate exported conflict clauses**, reject repeated low-value reasons, and compare causal CDCL progress at equal resource budgets before any fresh blind multi-family evaluation against CaDiCaL, Kissat and CryptoMiniSat with independent original-CNF UNSAT proof checking.
