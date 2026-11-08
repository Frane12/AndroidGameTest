# DRNAS MRE10b — source-disjoint prospective validation (2026-11-08)

Run: https://github.com/Frane12/AndroidGameTest/actions/runs/42511332725
Branch: experiment/drnas-mre10b-new2023-2025-20261108

## Precommitted scientific design

Evaluate the **unchanged** MRE10 native C++ Joint solver against the unchanged
pinned CMS baseline, CMS via the new native wrapper, and the C++ Clean-only
control on **12 different original official SAT competition Main Track
2023–2025 CNFs** selected BEFORE any MRE10b solving.

Choose four sources per year 2023, 2024 and 2025 by independent public GBD
competition index plus minisat1m=yes ranking, a fixed SHA salt, source file
geometry (<=50,000 variables, <=85,000 clauses), and a CaDiCaL status/time
window **0.07–10.0 s**. CaDiCaL is the external selection reference; NO CMS,
MRE10, R28, DRNAS result or equivalence structure can influence inclusion.

Exclude all GBD IDs and SHAs in the previous MRE10 16-source cohort, as
well as the tracked historical GBD exclusion registry. No claim of
exhaustive global historical non-reuse is made; the historical registry
is known to be incomplete. Every accepted original is downloaded, SHA
recorded and NEVER changed/excluded after timing any DRNAS mode.
Keep rejected download/reference attempts in the source manifest.

## Benchmark / cost definition

12 original SHA-verified sources × 3 frozen source-specific CMS seeds ×
4 modes = **144 true SAT/UNSAT end-to-end attempted solves**.

Four arms:
- N_ext original pinned 5.11.15 CMS, unchanged source CNF
- cpp_native native C++ wrapper using same exact pinned CMS library, no rewriting
- cpp_clean C++ exact syntactic duplicate and tautology removal, original CNF
- cpp_joint C++ certified binary-implication positive equality quotient
  plus exact original-CNF syntactic cleanup.

Each trial has a strict **15-second full wall** cap from entering trial
through parsing, rewriting, CMS solve, SAT model reconstruction/checking
against exact original SHA. A timeout costs **30 PAR2 seconds**.
Report per-arm SAT/UNSAT solved, timeout, PAR2 total seconds, × vs CMS,
C++ applied count, variable eliminations, removed clause counts and
paired source/seed regressions. Keep an exact C++ vs Python 12-original
CNF clause-by-clause parity smoke test, signed/positive equality
certificate validation and pinned native SHA checks.

SAT witness is verified against original CNF, UNSAT status independently
crosschecked by precommitted external CaDiCaL status; no independent
UNSAT LRAT is claimed. No production promotion from one small
preselected external-difficulty cohort. This is source-disjoint from
tracked MRE10 prior 16 originals, but NOT a globally random holdout,
because eligibility is conditioned on independent reference solver
difficulty and a public Minisat1m label.

## Interpretation

The prior MRE10 640-trial 8-second development suite gave native C++ Joint
PAR2 168.473602 vs CMS 211.756782 seconds (1.2569×), mostly driven
by one already-seen SAT2025 source. The precommitted MRE10b suite tests
whether that effect generalizes with identical solver code and a
separate reference-selected official cohort. Analyze differences
source-by-source, not only the aggregate, and check that any benefit
remains when the largest source winner is removed.
