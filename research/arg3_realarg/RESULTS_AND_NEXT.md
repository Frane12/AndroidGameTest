# DRNAS ARG3 REALARG1 — independent original argumentation category audit

**Date:** 2026-11-15. **Result: no certified out-of-source speedup
observed in the tested 4-second window.** Retrospective source-299
and its renamings are excluded from the test inputs.

## Source freeze (before any solver)

Freeze: https://github.com/Frane12/AndroidGameTest/actions/runs/43714913984

Candidate universe: 19 original SAT Competition 2025 Main Track GBD
entries labeled *argumentation*, identified in the published GBD
metadata regardless of SAT/UNSAT result. Previously studied original
GBD b9ed6fd14f4fc969ec966a4b54c36872 was explicitly excluded.

GBD index is pinned to the SAT Competition 2025 source catalog:
sha256 d02406bb212498ea1d2d9f2e968f9a8f6ad3b6bc479ae1b1368d5b4d638a9120.

Out of 19 fixed GBD candidates, 11 original unmodified CNFs downloaded
within immutable raw/expanded source limits (24/48 MiB), 8 excluded due
to size. No replacement sources, random cherry-picking, benchmark label
optimization, or source selection by our solver's outputs.
Each original source SHA256 was checked independently. Excluded known
previously studied exact byte hashes from earlier CF7 and REAL2025
source sets. Historical exposure outside those lists cannot be
guaranteed absent.

Frozen immutable manifest sha256:
8fe5ccfb1a05557bdbf43b8b801d8cbdb5160aff988d0956ded3904c1d8a70d8

**Important:** This is a frozen original-source category test, not
the overall SAT Competition benchmark distribution.

## Paired verified solver tests

Original ARG3 V2 (max 512 arguments):
https://github.com/Frane12/AndroidGameTest/actions/runs/43715069862

Second experimental variant (max 1024 graph arguments, same source
set and mathematical method, adjusted after source size became known
but before the first variant's outcome analysis):
https://github.com/Frane12/AndroidGameTest/actions/runs/43715235790

Each variant: 11 originals x 5 solver configurations x 2 repeats =
110 trials, one logical CPU per solver, 4s total E2E cap,
unsolved/unverified penalty 8s PAR2.
The five configurations were identical native X59 OFF,
identical X59 ARG3 ON (60ms structural budget), pinned
Kissat, CaDiCaL, and CryptoMiniSat. SAT accepted only after
independent full original CNF model validation; UNSAT accepted
only with an independently verified DRAT or FRAT proof within
the same overall cap. Original sources were unchanged.

| Result | X59 OFF | X59 ARG3 | Kissat | CaDiCaL | CryptoMiniSat |
| --- | ---: | ---: | ---: | ---: | ---: |
| Verified SAT / 22 | 0 | 0 | 0 | 0 | 0 |
| Verified UNSAT / 22 | 0 | 0 | 0 | 0 | 0 |
| Timeout / 22 | 22 | 22 | 22 | 22 | 22 |
| PAR2 sum s | 176 | 176 | 176 | 176 | 176 |

**Same outcome for both size variants.** There was no verified answer
gain and no incorrect accepted result. This does *not* establish that
the original instances are unsatisfiable or intractable: 4 seconds is
very short for this industrial category, and both the ARG3 prefilter
and the CDCL state need stronger analysis.

## Why this does not refute the original ARG3 result

Reproducible source-only structural audit (no solver execution):
https://github.com/Frane12/AndroidGameTest/actions/runs/43715670653

- 11 unique original sources, 10 contain root unit clauses;
- only 1 passes 512-argument size eligibility; 5 pass 1024-argument
  eligibility;
- 1 contains the exact unsimplified three-label triple pattern
  without units, but it has 20,925 variables and 960,801 clauses:
  far beyond the 1024-argument and 110,000-clause safety gates.
- The five within the 1024 size gate are not exact structural matches.
  Their original positive exactly-one ternary counts are below what
  the current recognizer requires, frequently with root units.

Examples from the exact source bytes:

| GBD SHA prefix | Vars | Root units | Positive triples | Expected triples |
| --- | ---: | ---: | ---: | ---: |
| 00d5a43a | 2670 | 159 | 886 | 890 |
| 8b267f95 | 1002 | 1 | 0 | 334 |
| 9754fc1a | 2376 | 814 | 785 | 792 |
| aa558557 | 2445 | 280 | 810 | 815 |
| c0074020 | 1977 | 96 | 655 | 659 |

The previous successful source-299 had a complete unsimplified
320-group pattern and 62,749 source clauses, and was known to
the developers before ARG3 was written.
The new originals often use other encodings or already-simplified
unit-root constraints. Therefore zero additional solves is
**absence of demonstrated transfer**, rather than a controlled
demonstration that ARG3 can recognize the same mathematical language
but fails to search it.

## Valid next research directions

1. Define a verified original-CNF root-unit simplifier and reconstruct
   already fixed argument groups; the selected new sources here become
   *development* data once inspected, not future holdouts.
2. Add separate proof-safe recognizers for the other documented
   argumentation generator encodings, rather than assuming one
   three-variable schema covers the entire family.
3. Retain a strict budget and fallback CDCL. Never infer UNSAT from
   failure to find an extension; accepted SAT needs the full original
   source witness.
4. Freeze another separate GBD source cohort before evaluating the
   next revised recognizer. Benchmark with longer matched limits,
   plus strong argumentation solvers/encoding baselines when possible.
5. Report full source and binary hashes, negative results, paired
   source-wise PAR2 and confidence intervals; no claim of general
   new mathematical or performance superiority from these results.

The latest experimental C++ branch changes neither main nor earlier
frozen solver evidence.
