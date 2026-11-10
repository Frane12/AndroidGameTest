# DRNAS Native Core R2 — standalone GF2 / CRR integrated native CDCL
Date: 2026-11-10
Experimental branch: `experiment/drnas-native-core-r2-gf2-20261110`

## What is original and standalone
- `research/drnas_native_core_r1.cpp`: own source-only C++17 DIMACS, two-watched literal BCP, 1-UIP conflict analysis, learned clauses, decision activity, phase, nonchronological backtracking and restarts.
- `research/drnas_native_core_r2.cpp`: extends the exact same own CDCL engine with certified native GF(2) XOR source detection, reductive pairwise cross-representation reasoning (CRR) and an **internal native CDCL XOR inference** step.
- `research/drnas_native_core_r2_test.py`: independent brute-force satisfiability oracle and source-SHA model checks; contains no imported or invoked foreign SAT solver.
- No CaDiCaL, Kissat, CryptoMiniSat, IPASIR or foreign solver library linked or invoked. System libc/libstdc++/libm are not SAT solvers.

## Mathematical source certification
- The original CNF is scanned deterministically for all 2–4-variable complete parity encodings. For every variable tuple and forbidden parity, the detector requires every one of the `2^(k-1)` distinct exact forbidden-sign CNF clauses before accepting its XOR relation as entailed.
- A derived row is the exact symmetric difference GF(2) sum of two source-certified rows, only if nonempty, arity ≤4, and strictly shorter than at least one input row. At most 128 source rows and 64 derived rows are admitted. This is *proof by source logical entailment*, not a general Gaussian matrix or proof logging implementation.
- Native GF2 scans current CDCL trail after its own two-watched-literal propagation reaches a fixed point. If an XOR row has one unknown, append a source-entailed reason clause and enqueue that unit in our own CDCL trail. If fully assigned and violated, construct a source-entailed conflict clause and give it directly to our own 1-UIP analysis.
- Safe resource budget: at most 500,000 XOR row evaluations per solve. When exceeded, disable GF2 (safe fallback to the same native CDCL) and log `xor_budget_off`.
- The XOR reason clauses are permanent consequences of the **original** source XOR encodings; they do not depend on heuristic inference.

## Correctness gates
- Standalone C++ R1 selftest 818 small cases, standalone C++ R2 selftest 1,636 mode-specific checks (including a 16-assignment exhaustive source-derived XOR witness).
- Independent Python brute force on 540 generated CNFs, testing each against three source-built solvers/modes: R1, R2 plain, R2 GF2, total 1,620 independently checked attempts.
- Of those 540 CNF, 120 contain deliberately complete overlapping parity rows. Derived reduction must **activate in native R2 GF2** on each; acceptance merely from extraction without actual native propagation/conflict is not sufficient.
- Original SAT assignments are independently checked against the original DIMACS formula. Report original UNSAT from the solver as **unverified** until independently checked proof is available; no claim of DRAT or LRAT proof logging.

## Fair original benchmark
- Six previously source-frozen MIXAB4 reference-easy original CNFs, exactly verified SHA before use. These are *not blind* to previous work.
- Three own code arms: R1 original binary; R2 plain; R2 + GF2. All built from source with identical C++17 flags on the same runner class.
- 2 repeats, 3s full runner attempt cap per arm, same logical CPU, record wall E2E, internal solver seconds, conflict counts, GF2 implication and reasons, and **strict proof-accepted PAR2**. An uncertified UNSAT counts as timeout for strict PAR2 even when solver internally returns UNSAT.
- Synthetic positive controls are not competitive benchmarks; overall speedup requires validated original-CNF success with matched E2E and meaningful baseline comparison.

## Limits before promotion
1. Tiny core has no proper independent UNSAT proof emitter or externally accepted LRAT verifier.
2. Simple linear activity scan, no clause database reduction, no optimized EVSIDS heap or advanced LBD strategy; not yet expected to compete broadly with leading CDCL engines.
3. Source-certified XOR parity encodings are limited to 2–4 vars and two-source cancellations; wider Gauss needs separate verified implementation.
4. Source rows, derived row limits and 500k scan budget may miss useful algebra and impose overhead. Measure direct additional solved outcomes rather than number of GF2 events.
5. No auto promotion into main. Keep both source and harness reproducible.
