# DRNAS SAT TRAIL-RECONSTRUCT1: reconstruct a residual CNF during CDCL

This is an opt-in **single-process, single-logical-CPU** C++20 experiment. It does **not** change main, frozen references or APK.

## Hypothesis

After real CDCL assignments and BCP, the remaining original CNF may contain Horn, 2-SAT, matching or XOR substructures obscured at the root. At decision numbers 1, 4, 12 and 32, within a strict **12 ms total** CPU-local discovery budget (maximum 2.5 ms per invocation), the solver:

1. Simplifies **immutable original clauses** using the actual current CDCL trail; satisfied clauses are removed, and falsified literals are omitted. This transformation is used only for analysis.
2. Renumbers residual free variables densely and attempts an existing verified full SAT constructor (Horn, 2-SAT, MATCH and GF(2)).
3. If the whole residual is not solved, attempts closed structural components and parity subset hints with the previous SAT-LOCAL1 module.
4. A complete constructed model is lifted back through the current trail, assigning remaining unmentioned variables FALSE, and verified against **all original clauses**, before any SAT return.
5. Partial assignments are reversible **phase hints only**, invalidated when CDCL backtracks below their original assumption level. No SAT/UNSAT return, learned clause, proof step, or forced propagation originates from a nonverified hint.

Source gates: at most 2,048 variables, 12,000 clauses and 75,000 literals; maximum 4 attempts; no probing in speculative solver clones. Default OFF; `--sat-trail-ms 12` enables ACTIVE; add `--sat-trail-shadow` for inspection-only. The root-level `--sat-local-ms` remains independently disabled throughout this comparison.

## Deterministic soundness gate

`research/sat_trail1/selftest.py` constructs 20 anonymous gated mixed SAT CNFs (their internal structural components only emerge after a CDCL assignment), plus 10 gated UNSAT controls. OFF, SHADOW, ACTIVE are checked against the full original SAT model and the expected UNSAT response. UNSAT DRAT proof verification is additionally enforced by the full benchmark harness.

## Pinned retrospective original-CNF comparison

Reuse the unchanged 600 public SATLIB originals and original/normalized SHA-256 manifest from REAL600 (run 43731136744), plus 24 previously exposed SAT2024 CF7 originals (source IDs 0,4,...,92). 624 distinct sources, 6 arms, 3,888 trials, four shards.

- Arms: one X59 executable OFF, TRAIL_SHADOW, TRAIL_ON, plus pinned Kissat, CaDiCaL, CryptoMiniSat.
- SATLIB 2 s, SAT2024 3 s verified end-to-end caps; one native CPU per solver process, random paired arm order, two repeats for SAT2024 only.
- Accept SAT only after independent check against original SATLIB or SAT2024 source clauses; accept UNSAT only after separate DRAT/FRAT checker success within the same cap.
- Full source hashes, each trial verdict, CPU seconds, RSS, method and trail telemetry, accepted result and PAR2 are saved. Print only 25-source progress logs per shard and final summary.
- Report SATLIB and SAT2024 separately, no blind holdout claim, no automatic promotion. Correctness comes before performance.

This is an exploratory engineering combination of established methods, not an NP-completeness or polynomial SAT theorem. Source SHA-disjoint selection within this fixed evaluation does not make previously exposed public CNFs blind.
