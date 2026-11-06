# DRNAS R162 — GF(2) component feedback versus native CDCL

Date: 2026-11-06. Branch: `experiment/drnas-r162-gf2-cdcl-component-feedback-20261106`.

## Causal research question

R158x showed fewer native CDCL conflicts and decisions under source-certified direct GF(2) reasons, but **zero improvement in solved problems at the timeout**. R162 tests whether avoiding nonproductive GF(2) work *per connected XOR component* improves actual runtime and solves.

## Native implementation

- `research/r162_component_feedback.cpp` derives from the R158x CaDiCaL 2.1.0 IPASIR-UP bridge.
- Connected components are defined by variables co-occurring in certified XOR rows (disjoint-set union); source CNF remains unchanged.
- The same native instrumented binary runs all five modes: `clean`, `shadow_boundary`, `direct_full`, `direct_boundary_nogate`, `direct_feedback`.
- All direct propagation reasons remain original-source-derived and checked; timeout uses CaDiCaL Terminator to expose native conflict/decision/propagation counters. No independent UNSAT LRAT certification is claimed.
- `direct_feedback` uses the *same bounded rows* as `direct_boundary_nogate`, but stops just the optional GF(2) callback work for a component once it has >=4096 scanned rows, fewer than two proposals, and zero completed CDCL reason requests. The original CNF/CDCL path continues unmodified.
- Metrics include number of components, components with consumed complete reasons, skipped rows, component gates, direct proposals, completed explanations and nanoseconds spent in `cb_propagate`.
- **Reason consumption is not itself evidence of a helpful conflict**; compare actual paired native CDCL time, solved counts, PAR-2 and regressions. Microtimings include instrumentation overhead.

## First experiment

Reuses the eight R154/R158x original SHA-pinned development formulas, with four mixed-residual and four controls, to verify the mechanism. Five native modes × two repeats × eight formulas = **80 paired SAT attempts**, four shards. Existing original source artifact from run 42112755104 is independently rehashed and GF(2) rows replayed. Mixed formulas: 15 s cap; controls: 5 s. Source GF(2) preprocessing cost is charged, and all modes share one compiled native binary SHA per run.

**This is a development pilot, not a blind holdout, not a claim of superiority.** Progress means a genuinely lower PAR-2 or more solved mixed formulas without new severe regressions, not just a reduction in conflict count. A new SHA-disjoint industrial/mixed holdout with longer limits and independent UNSAT proofs is required before promotion.

## Correctness / fail-closed audit

- Exhaustive source-CNF implied XOR row check and source SHA fingerprint
- Original CNF SAT witness verification
- Uniform exact native binary SHA across shards
- Five-mode paired, complete row accounting, no missing trials or conflicting SAT/UNSAT statuses
- No unexplained external propagation reasons or modified source clauses
- Any CI/compilation/source-certificate failure means no performance claim
