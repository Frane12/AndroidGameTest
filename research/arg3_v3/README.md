# DRNAS ARG3-V3 — root-unit and partial triple reconstruction

**Experimental result: construction recognized real partially simplified
argumentation encodings but did NOT solve unseen original development
sources in the tested caps.** Date 2026-11-15.

## Implementation

Files:
- src/drnas_sat_arg3_v3.hpp
- src/drnas_sat_arg3.hpp
- src/drnas_x59.cpp
- research/arg3_v3/smoke.py
- research/arg3_v3/benchmark.py

X59 opt-in argument: --arg3-v3-ms 150. Default OFF.
No extra process or portfolio; one logical CPU per solver.

Algorithm, source-only:
1. Read root unit clauses and perform a bounded sequence of legitimate
   Boolean unit propagations. Contradictory root state -> UNKNOWN, never UNSAT.
2. Detect exactly-one triples across 3 contiguous [IN,OUT,UNDEC] layers.
3. Allow a missing source triple and its binary mutexes ONLY when the
   ORIGINAL source contains source-unit clauses IN_i, -OUT_i, -UNDEC_i.
   This is a conservative reconstruction for model search, not a new
   entailment or proof of UNSAT.
4. Construct the directed implication graph from source binary
   (-IN_j OR OUT_i) clauses; honor root-fixed state restrictions.
5. Search bounded randomized conflict-free out-dominating sets; propose
   total three-valued models.
6. Return SAT only if an independent complete scan satisfies EVERY clause
   of the original source CNF. Otherwise original X59 CDCL continues.

The source shape detector has guards of 1024 groups, 110k original
clauses, at least 95% source-positive exactly-one triples, and an
overall monotonic budget. This is not a general argumentation solver.

## Positive controls and structural recognition

Smoke run:
https://github.com/Frane12/AndroidGameTest/actions/runs/43716828980

- Synthetic already-known SAT graph, one whole group removed and
  replaced by original fixed units: SAT model independently verified.
- Unrelated CNF: detector abstained (though the ordinary CDCL fallback
  can independently return SAT).
- Four fixed 2025 original development sources recognized and partial
  groups reconstructed:
  - 00d5a43a: 4 recovered groups, 286 root-derived implications
  - 9754fc1a: 7 recovered groups, 183 root-derived implications
  - aa558557: 5 recovered groups, 520 root-derived implications
  - c0074020: 4 recovered groups, 160 root-derived implications

At the pilot 150 ms analysis cap, none of those four produced a
certified source SAT witness. Three returned no stable candidate;
one produced over 1100 stable candidates but they did NOT satisfy the
full original CNF. No false SAT declarations observed.

The previously studied source #299 was not solved by the separate V3
path; older native ARG3-V2 remains independently opt-in.

## Full retrospective original argumentation comparison

Frozen originals were collected BEFORE V2 outcomes, but have since been
inspected and are now **development sources**, not a blind holdout.
Original source-freeze SHA256:
8fe5ccfb1a05557bdbf43b8b801d8cbdb5160aff988d0956ded3904c1d8a70d8

Source-paired real benchmark:
https://github.com/Frane12/AndroidGameTest/actions/runs/43717349094

11 official SAT Competition 2025 argumentation source CNFs,
2 repetitions, 3 arms (identical native X59 OFF and V3 ON, CaDiCaL),
8-second total E2E limit; 66 trials. SAT accepts only an original-CNF
independently checked complete witness; UNSAT accepts only an
independently verified standard proof within the same E2E cap.
Unsolved/unverified -> PAR2 16 seconds.

| Arm | Verified SAT/22 | Verified UNSAT/22 | PAR2 sum seconds |
| --- | ---: | ---: | ---: |
| X59 OFF | 0 | 0 | 352.0 |
| X59 with ARG3-V3 | 0 | 0 | 352.0 |
| CaDiCaL | 0 | 0 | 352.0 |

All 66 attempts timed out at 8 seconds. No incorrect models or proof
verdicts were accepted. This is *no demonstrated real-original speedup*,
not a proof that the originals are UNSAT or impossible.
Note: timed-out solvers did not emit end-of-process statistics, so
the aggregate zero recognized count from completed-trial telemetry
does not contradict the standalone smoke's four successful recognitions.

## Interpretation and next engineering route

The fixed-unit sources can now be classified, but their source
clauses include global positive cardinality/nontrivial-extension
constraints and graph encodings that are not equivalent to the
simple stable-extension cases solved by V2. Merely regenerating the
missing triples does not find a satisfying extension.

Do not promote or claim general algorithmic novelty.
A next **separate development experiment** should compare
complete-labeling (allowing UNDEC), admissibility constraints,
and clause-guided local repair under an independently checked
original witness. Negative original performance must remain in
the report. A NEW SHA-disjoint source cohort must be frozen before
any subsequent promotion claim.
