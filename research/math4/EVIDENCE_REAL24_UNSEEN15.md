# DRNAS MATH4 — independently checked real-CNF algebra evidence

## Experimental implementation

This document describes the **experimental** optional native CF7 guard, not `main`.
The code under `src/math4_xor_unit.hpp` identifies complete original-source
CNF parity half-cubes, derives root units using source-unit propagation, and
performs exact GF(2) elimination. If it derives `0 = 1`, it writes a
source-SHA256-bound certificate (`drnas-math4-xor-unit-v1`). The separate
`research/math4/check_xor_units.py` verifier checks every original XOR
clause, recomputes the root unit closure, and checks the final parity
combination. It never trusts the solver's algebra or official catalog label.

There is **one native process and one logical CPU**, and on no certificate
the guard passes control to the existing HALL3 and unchanged CF7 CDCL.
No changes to the repository's `main` or frozen comparison binaries.

## Pre-existing source-pinned Main24 retrospective (SAT Competition 2026)

- Run: https://github.com/Frane12/AndroidGameTest/actions/runs/43646454422
- 24 original CNFs, 12 families, 2 reps, five paired arms (240 attempts).
- 12 s per solve including independent proof checker, PAR2 timeout penalty
  24 s, one logical CPU per sequential trial.
- Source-verified E2E PAR2 sums (48 trials per arm):

| Arm | distinct sources solved | verified trials | PAR2 (s) |
|---|---:|---:|---:|
| MATH4_ON | 4/24 | 8/48 | 965.681656 |
| HALL3_ON | 3/24 | 6/48 | 1013.565902 |
| CaDiCaL | 2/24 | 4/48 | 1084.679167 |
| Kissat | 1/24 | 2/48 | 1109.098746 |
| CF7_OFF | 0/24 | 0/48 | 1152.000000 |

MATH4's additional original-CNF proof is
lights-out source `667341ee8c1dea3db613db317e2b2c33`:
0.080896 and 0.082159 s total (native + independent proof-check)
in the paired run. HALL3 returns UNKNOWN for this source within the
12 s cap; the two arms share other original Hall successes.
Source-cluster bootstrap 95% interval for the **per-source** HALL3 minus
MATH4 PAR2 improvement is [-0.001233, 2.992619] seconds. The interval
includes zero: *do not claim general superiority*.

## Separate precommitted source-disjoint 15-source SAT2026 catalog sample

- Selection was committed **before running any solver** in
  `research/math4/holdout_selection.json`.
- Lexicographically earliest participating catalog IDs per declared family
  and SAT/UNSAT/unknown quota; unique isohashes; excludes all source IDs and
  isohashes of the earlier HALL3 Main24 sample. **It does not establish
  disjointness from every historical DRNAS experiment or a new family.**
- Freeze: 15/15 exact source downloads, zero replacements/exclusions.
- Run: https://github.com/Frane12/AndroidGameTest/actions/runs/43646870786
- 15 original CNFs, 5 families, 2 reps, five arms (150 attempts);
  10 s end-to-end cap, verified PAR2 penalty 20 s.
- Source-verified E2E PAR2 sums (30 trials per arm):

| Arm | distinct sources solved | verified trials | PAR2 (s) |
|---|---:|---:|---:|
| MATH4_ON | 4/15 | 8/30 | 441.132829 |
| HALL3_ON | 1/15 | 2/30 | 560.677984 |
| Kissat | 1/15 | 2/30 | 571.664117 |
| CF7_OFF | 0/15 | 0/30 | 600.000000 |
| CaDiCaL | 0/15 | 0/30 | 600.000000 |

MATH4 has 21.32% lower verified PAR2 than HALL3 in this exact sample,
primarily from three additional independent GF(2) contradictions on
the three new unsat lights-out sources:

| ID | GBD source ID | original SHA256 | source XOR proof rows | forced units in proof | verified end-to-end seconds (2 reps) |
|---|---|---|---:|---:|---|
| 0 | 0efcbd10294eb001b16b4d126923372f | 84729f80119b50efac42d9477438abbc58c8712654ffe1fcdf9f324e44ae165d | 184 | 0 | 0.072843, 0.073864 |
| 1 | 32e344a5ab3af245f982678d2b751c6d | fec9c446068a306641493d88daa4bf6b1cbb1adc0252d2712902c308824a570b | 682 | 200 | 0.065038, 0.058769 |
| 2 | 80b163b706e0a16702173ec27f3d1331 | 8e18f556aac81645e8b9f285552e4b42e51710340a419ffddc44c4a79c5811aa | 200 | 0 | 0.095301, 0.072728 |

All three sources carry external source-only independently checked
certificates twice. HALL3, CF7, Kissat, CaDiCaL did not produce a
verified answer on these three within the 10 s cap. Another graph-coloring
UNSAT source was verified twice by both MATH4 and HALL3 using the
preexisting Hall path. The two known-SAT control CNFs did not elicit a
false UNSAT; they were not solved as SAT under this protocol.

Source-cluster bootstrap 95% interval for **per-source** HALL3 minus
MATH4 gain is [0, 7.972238] seconds. It touches zero, so avoid declaring
a statistically established general benefit across future source families.

## Interpretation and next step

- **Proof soundness for these accepted formulas** is independently
  established by re-checking only original source clauses; the
  certified derivation is an established GF(2) linear-algebra identity
  plus original CNF unit propagation, not a newly proved theorem.
- **Structural certificates are not DRAT/LRAT**; the benchmark reports
  both source-verified and strict DRAT-only scores. The latter treats
  MATH4's structural-only outputs as unverified.
- The strongest presently supported claim is a repeatable
  source-only automated proof mechanism on the selected lights-out
  family. No global SAT performance superiority has been demonstrated.
- Next experiments should sample additional genuinely disjoint
  lights-out input families, compare against a dedicated stand-alone
  GF(2) solver and standard CDCL, and integrate a learned source-blind
  detector for safe activation on other categories.
- Freeze the current binary/checker SHA256 and **do not promote to main**
  without broad blinded certified PAR2, no false SAT/UNSAT, and
  acceptable nonmatching-family overhead.

This branch is retained as a research artifact. Reproduction requires
the original CNF SHA256, the exact guard binary and checker, and the
certificate archived with each successful run.
