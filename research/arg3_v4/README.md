# DRNAS ARG3-V4 — complete three-label local SAT repair

Experimental branch: experiment/drnas-arg3-undec-repair-v4-20261115
Date: 2026-11-15. No main branch or frozen-reference edits.

## Problem and method

Previous ARG3 sought stable argumentation extensions, which forbid
UNDEC labels. Genuine source CNFs may encode complete three-valued
labelings and globally constrained argumentation models. These
allow an argument to be IN, OUT or UNDEC.

For N arguments, represent each argument i with three Boolean vars
IN_i, OUT_i, UNDEC_i and exactly-one constraints. We never treat this
abstraction alone as proof of satisfiability. The original DIMACS
CNF with all wide constraints is the final arbiter.

Source-only algorithm, all inside the original native X59 process:

1. Check 3*N variables, source bytes/clauses/literals and the shared
   monotonic budget. No filename, source SHA, label, solver result or
   training oracle is read by any constructor.
2. Run bounded, logically sound original-CNF root unit propagation.
   Contradictory roots cause abstention (not UNSAT).
3. Require most expected one-hot source triple clauses plus source
   pairwise mutual exclusions. Missing groups are allowed only with
   three original unit clauses fixing exactly one of IN, OUT, UNDEC.
4. Build the allowed state set for each group from genuine source
   root assignments. A fixed group is never modified.
5. Initialize assignments using UNDEC, IN or deterministic randomized
   allowed states. Evaluate *all original* clauses, including global
   blocker, cardinality and cross-group constraints.
6. Repeatedly pick an unsatisfied original source clause. Evaluate
   up to 24 candidate group state changes using incremental counts
   of satisfied literals in every affected original clause. Prefer
   moves that remove more weighted unsatisfied clauses than they break.
   Add limited weights to persistently violated clauses, with bounded
   restarts and deterministic tie-breaking. No second solver, thread,
   portfolio or external SAT backend.
7. Only if all original clauses appear satisfied, independently verify
   the full constructed Boolean model by rescanning all source clauses
   and return SAT. Otherwise abstain and continue standard X59 CDCL.

Command:
  g++ -O3 -std=c++20 -DNDEBUG src/drnas_x59.cpp -o build/drnas-sat-native-x59
  build/drnas-sat-native-x59 input.cnf --mode core --time 8 --arg3-v4-ms 400 --stats

Default V4=OFF. Existing V3 also remains OFF unless separately opted in.
V4 never declares UNSAT. UNSAT in the integrated solver must come from
its original CDCL path and independent DRAT/LRAT verification.

## Current verified controls

Source:
https://github.com/Frane12/AndroidGameTest/actions/runs/43718646944

- An odd directed cycle family with no stable labeling, but a complete
  SAT labeling with UNDEC, was solved by V4 with a complete original
  source model.
- A source from that family with one missing one-hot group replaced by
  positive UNDEC and negative IN/OUT source units was reconstructed and
  solved with original model verification.
- An acyclic segment joined to odd cycles requires a mixture of
  IN, OUT and UNDEC states; a full original SAT model was verified.
- Twelve unrelated random CNFs were not falsely recognized as
  argumentation. Standard CDCL may independently solve them.
- Four previously exposed true SAT Competition 2025 original
  argumentation sources were recognized. At 200 ms V4 structural
  search, best source-unsatisfied clause counts were 2, 18, 2, 2,
  respectively; none returned a verified SAT model.
- Known source #299 was also recognized, but the V4 path did not
  solve it in 100 ms. Existing optional ARG3-V2 remains a separate
  successful path on that previously studied source.
- No false SAT response was observed in these controls.
- One initial smoke run failed because a small test (N=15) required
  one allowed missing group while integer n/20 truncated to zero.
  Fixed using max(1,n/20), without changing original/source input
  or accepted answers. Success on the next run is recorded.

## Scientific limitations

This is a bounded stochastic local search. A two-unsatisfied-clause
candidate is not a SAT witness. Even with zero residual clauses in
its fast incremental cache, full original-CNF checking is mandatory.
Failure, root contradiction, unrecognized encodings or timeout cannot
be interpreted as UNSAT.

The 11 SAT2025 sources are ALREADY DEVELOPMENT DATA: previously frozen
for ARG3 tests and inspected. A retrospective comparison on this set
cannot support blind promotion. A new SHA-disjoint original cohort
must be frozen before claiming any generalization.

The built-in category assumes one-hot source groups in contiguous
three-layer variable order. Arbitrarily renamed originals may require
V2's separate source-role canonicalization. This version is not a
complete argumentation reasoner or an exact general SAT algorithm.
