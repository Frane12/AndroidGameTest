# DRNAS SAT — cross-family structure discovery protocol

**Date:** 2026-10-31. **Status:** experimental / no discovered general class yet.

## Question
Can static, label-invariant features of CNF formulas predict which problems benefit from the frozen V7.6 phase-hint strategy relative to the same strategy without hints, even on a different SAT family? This is about a measurable *subclass* of SAT, not proving P=NP or establishing a new worst-case complexity bound.

## Pilot — 40 new cases, exploratory
- 5 families: random 3-SAT, random 4-SAT, graph 3-coloring, XOR-3, pigeonhole.
- Four prespecified sizes and 2 independent instance seeds per family, total **40**.
- 5 methods: CaDiCaL 3.0.1 plain, frozen V7.6 guided, frozen V7.6 plain, V8.9 yield unhinted, V8.9 yield late-hint.
- Three matched repetitions and 3-second wall limit each: **600 attempts**, 5 separate pinned-core shards.
- SHA256 of every DIMACS CNF and source hashes; record timeouts, errors and SAT/UNSAT consistency.
- SAT witnesses checked by the solver; UNSAT proof independently unchecked. No world-record claim.

Features: clauses/variables, average clause width, binary-clause fraction, variable-degree coefficient of variation, maximal degree vs mean, polarity imbalance, largest variable-incidence component, isolated-variable fraction. All are invariant under bijective variable renaming and independent sign flips. **Do not include problem-family IDs, solving results or labels as inputs to a future gate.**

### Exploratory screen
For two successfully solved strategies with 3/3 solves and baseline median >= 0.10 seconds:
- Guided win: (V7.6 plain time)/(V7.6 guided time) > 1.25
- Guided loss: ratio < 0.8
- Otherwise neutral; if censored, inconclusive.

Rank feature associations **within family**, avoid concluding from random3 vs random4 alone. Inspect negative controls and all regressions. Report the hindsight per-instance oracle, explicitly **not deployable**, to see how much upside a phase selector could possibly extract relative to always plain.

## Holdout — 200 further, previously unseen cases (NOT yet evaluated)
Before generating these formulas:
1. Freeze the exact selected feature(s), threshold(s), selector implementation, baseline and source/seed generation rules in a commit.
2. Generate 40 further cases per family, stratified over sizes and independent new seeds; do **not** reuse any pilot formulas or known benchmarks. Include an optional external industrial SAT validation dataset in a **separate** analysis.
3. Run 3 repeats for every method including a cheap feature-gated mode and a matched no-hints control. Compare paired wall and CPU times; include timeouts under PAR-2 and completion rates.
4. Report family-by-family wins/losses, effect size and uncertainty (paired bootstrap over *formulas*, not repeated runs), runtime overhead of feature calculation, and ablation against a constant always-plain policy.
5. Verify satisfiable witnesses independently. For unsatisfiable cases requiring scientific correctness claims, generate and check independent proof certificates.
6. A promising predictor must generalize across *families*, not merely classify a family by clause width. A positive headline needs at least a **5%** PAR-2 improvement relative to the best frozen control across held-out formulas, no serious regressions, and a replicated result on an independent dataset. This threshold is a research target, not evidence.

## Interpretation
Finding a predictive structural subclass would be a useful empirical algorithmic result, potentially applicable to graph encodings and circuit/constraint CNFs. It would **not** by itself be a complexity-theoretic breakthrough or prove any worst-case polynomial bound.
