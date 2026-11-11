# DRNAS ATLAS-MAP1 — first independent CI audit

**Date:** 2026-11-11  
**Branch:** `experiment/drnas-atlasmap1-structural-shortcuts-20261111`  
**GitHub Actions:** [run 42936295759](https://github.com/Frane12/AndroidGameTest/actions/runs/42936295759)  
**Experiment stage:** code and structural correctness checked; *no general speedup demonstrated*.

## What was actually validated

The automated correctness job completed **SUCCESS**:

- Deterministic C++ source-certified relation-map tests: `ATLASMAP1_SELFTEST_PASS random_bruteforce=350 random_commits=350 certified_pair=1 contradictory_cycle=1 incomplete_pair=1`.
- C++ tests compare satisfiability via a separate exhaustive truth-table oracle and reconstruct every satisfying reduced assignment for accepted six-variable rewrites.
- Python smoke test on both positive and negated parity substitutions, mixed structural formulas and unrelated non-XOR controls. Every SAT model was checked against **original CNF**.
- Persistent statistics gate smoke test: four failed probes, bounded skipping, one-in-eight re-exploration; no logical conclusion is reused from statistics.
- The synthetic mixed control intentionally demonstrates a trade-off: ATLAS-X saved **8** literals in its L2 path; MAP1's cheaper parity-DSU gate saved **4** instead. A cheap route is not necessarily the maximal reduction.

## Original SATLIB source-matched holdout

Four source-selected *previously public* SATLIB satisfiable instances (SHA-based rank 41 from each family), two repeats per arm, six arms, **48 attempts**. Each solver arm was pinned to **one logical CPU**; 10-second cap, PAR-2 timeouts count as 20 seconds per attempt. Native modes all use the same source-built R3C native CDCL backend. Reference solvers are Kissat (commit pinned in workflow) and CaDiCaL package installed by the runner.

| Family / shard | Native A PAR-2 (s) | ATLAS-X (s) | MAP1 (s) | MAP_LEARN cold (s) | Kissat (s) | CaDiCaL (s) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| uf100-430 / 0 | 0.016123 | 0.016903 | 0.017361 | 0.017292 | 0.057456 | 0.016585 |
| uf150-645 / 1 | 0.016410 | 0.016159 | 0.014420 | 0.014417 | 0.094824 | 0.032861 |
| uf200-860 / 2 | 0.073895 | 0.073889 | 0.075683 | 0.075562 | 0.848656 | 0.144824 |
| uf250-1065 / 3 | 40.000000 | 40.000000 | 40.000000 | 40.000000 | 1.809610 | 1.895569 |
| **Total** | **40.106428** | **40.106951** | **40.107464** | **40.107271** | **2.810546** | **2.089839** |
| **SAT solved / 8** | **6/8** | **6/8** | **6/8** | **6/8** | **8/8** | **8/8** |

SHA-256 of normalized original DIMACS inputs:

- uf100-430: `53b2a1fc35de8fad8a845dc9a7bf24610b712214095ef97f56c1f6673cbf1249`
- uf150-645: `9d7af156de90af558d6983d3d836bb8feb21a4b07b29f98e2ac847dab5c11136`
- uf200-860: `b012a23384241acadfbdd71edc74dfdf3cb39a1c019fcb8cab36767e7792ecd9`
- uf250-1065: `a00a46b310ff9d35e260195ca628eaf80f99ffd4b9811f3b4e80042fc1eda6bb`

Each family's exact archive entry, source archive SHA, trial JSON, original CNF and solver telemetry are uploaded to the corresponding CI job's artifacts.

## Result and interpretation

- **MAP1 vs native A:** aggregate 40.107464 vs 40.106428 PAR-2 seconds; the ratio A/MAP1 is approximately **0.99997×**, an effective tie with minor overhead, not a speedup.
- The first three families were all solved and verified SAT by each mode. The fourth timed out at 10 seconds on every native mode while Kissat and CaDiCaL each solved both repeats.
- All MAP1 routes on the three solved families reported `alias_edges=0`. These particular random 3-SAT original CNFs do **not** contain recognized complete source binary equivalence pairs; the selector correctly refrained from inventing relations.
- The fourth native family timed out, so completed per-trial route summaries were not claimed as a solution or speedup.
- Cold MAP_LEARN uses **no trained history file** in this holdout, so the experiment cannot demonstrate improved learned selection.
- This test is prospective to MAP1's rank choice, but SATLIB is a known public dataset and SHA rank 41 is **not** evidence of globally untouched/blind formulas.
- No independent UNSAT LRAT certificate exists. No UNSAT correctness claim is made from these SAT-only benchmark outcomes.

### Next experiment grounded in this result

Source-lock and test **genuine mixed formulas with certified binary equivalence blocks** plus negative controls, with a frozen training/holdout separation for strategy memory. Measure source pair counts, reductions, memory decisions, observed conflict/decision changes and full E2E PAR-2 relative to the *same* native CDCL. Prefer the cheaper MAP1 route only when it saves real end-to-end time, not merely when it removes some literals.

The current implementation is a **pre-CDCL** structural selector, not an online CDCL-trail or restart-time learner. It remains an **isolated experimental branch**, with `main` unchanged.
