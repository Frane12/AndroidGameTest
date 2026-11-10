# DRNAS GF-CDCL NOVEL2B — causal selection correction (2026-11-10)

## Why NOVEL2 did not earn promotion
Completed original-CNF single-CPU smoke:
https://github.com/Frane12/AndroidGameTest/actions/runs/42820119566

- Native selftest: exhaustive original CNF UP + cross-GF2 derived reason PASS.
- 2 previously seen source-only selected frozen SHA x 4 arms x 2 reps = 16 attempts, 6-second cap.
- All arms: 0/4 independently solved; strict SAT-only PAR2 48.0 seconds each.
- NOVEL2: 1,082,773 derived-row visits, 654,282 source-row skips, **0 derived proposals**, **0 accepted reasons**. It did not deliver any useful conclusion to the real CDCL solver on this smoke.
- Selection flaw: ranking by count of short XOR pair sums preferred 32 source rows with 496 pairwise sums. Many pair sums merely concatenate independent XOR2 rows into width-4 relations. Such a relation does not improve over original CNF unit propagation.

## NOVEL2B correction
- Derived row must have arity 2..6 and be strictly *shorter than at least one source row*. Exact GF2 symmetric difference of two independently original-CNF certified rows; no adaptive SAT timing or result leakage.
- Source-only first-pass screening counts reductive XOR pairs and separate 1-variable (certified unit) candidates, which are not inserted in the present two-watched bridge.
- Select at most two distinct original SHA with positive useful pair reductions, from the frozen 40; no outcome-based selection.
- Compare clean, direct, novel2b and novel2b_shadow, 2 repetitions each, cap 6s; one CPU per child; SAT original witness verified; backend UNSAT not accepted without independent LRAT.
- If fewer than two eligible cases, fail closed **without** manufacturing a benchmark.
- Any synthetic toy derivation only proves arithmetic validity. Do not claim a real-original-CNF speedup without unique delivered CDCL implications and an E2E win on a preregistered unseen holdout.

## Next if NOVEL2B still no gain
Study certified one-variable XOR consequences from cross-row cancellation (which the watch bridge currently excludes). Proof-first unit insertion or proof-attached root propagation may outperform low-yield live callbacks. Verify on original CNF and independently check the derived unit before inclusion; keep that an explicitly separate experimental arm.
