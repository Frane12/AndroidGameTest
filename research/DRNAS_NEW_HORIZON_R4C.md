# DRNAS New Horizon R4c — source-density economic veto

## Motivation

The preceding source-exact R4b five-repeat confirmation found:
- source-exact pure XOR3: **5.72x** speedup on 12 generated formulas, 60/60
  paired trial wins vs clean native CaDiCaL.
- small, relatively dense 2-SAT: **1.60x** speedup on 12 generated formulas,
  60/60 paired wins vs clean.
- misleading sparse prefixes, source-wide *not* 2-SAT: **10.8% slowdown**,
  0/40 paired wins.
- large 2-SAT: Python full-source checks and SCC can be significantly
  slower than the pinned native solver.
- a single clean-only timeout on near-cap general 3-CNF contaminated
  aggregate PAR2; it is not evidence of a hard general SAT improvement.

## R4c: a conservative performance-only density veto

Before parsing source clauses for the optional 2-SAT path:
  - require 80 <= source clauses <= 512,
  - require n <= 192 declared variables,
  - require **m >= 2 n** original clauses.

This is a heuristic *economics* criterion fixed **before** R4c
measurement, not a mathematical claim about 2-SAT complexity. It may
refuse even beneficial sparse 2-SAT sources, in which case the original,
unmodified CNF is solved by the same native CaDiCaL. The acceptance of
a class still requires reading and validating *every original clause*.

The exact XOR3 source-complete path remains unchanged. UNSAT derived
from certified original GF2 and exact SCC algorithms is algorithmic;
no independent LRAT/FRAT proof is provided. Every SAT witness is
verified against original source clauses.

No model approximates original Boolean constraints. The selector can
only choose an optional method, or abstain.

## Controlled stress experiment

72 original deterministic SHA-frozen cases, 4 repeats, 4 arms:
**1,152 paired trials**, all including detector/proof wall time.

Arms:
- clean CaDiCaL,
- frozen R4b,
- R4b XOR-only ablation,
- R4c density-veto proposal.

Seven groups (all known generator families, not a blind holdout):
- 12 pure XOR3 source-equivalent;
- 12 dense real 2-SAT source equivalents;
- 12 sparse 2-SAT source equivalents (possible missed opportunities);
- 12 sparse misleading 2-SAT prefixes with a late non-2CNF clause;
- 8 *dense* misleading 2-SAT prefixes with a late non-2CNF clause;
- 8 large 2-SAT sources;
- 8 general planted 3-CNF controls.

New deterministic seeds and explicit corner cases stress density
boundaries, not necessarily unseen real-world formula distributions.

## Required audit

- Exact SHA-256 original source per case; identical native solver
  CaDiCaL-2.1 build SHA as earlier R4b.
- Four methods on every identical source and cap, randomized order
  per repetition.
- Fail closed on missing arm, contradictory SAT/UNSAT, original source
  mutation, or incorrect PAR2.
- No interpretation of one native near-cap timeout as a general solver
  advantage.

## Conditions to move forward

Compare per-group relative risk. Acceptance requires that the
sparse-prefix regression measurably improves **without** causing
unacceptable sparse-valid-2SAT regressions. A density classifier that
merely overfits known examples is NOT a general advance.

A subsequent truly blind original industrial SAT holdout and
hardware-stable timing are still essential before any production merge.
