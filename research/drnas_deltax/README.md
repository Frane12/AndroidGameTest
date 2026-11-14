# DRNAS DELTAX — proof-carrying guarded equivalence inside native CDCL

**Experimental branch:** experiment/drnas-deltax-live-guarded-equivalence-20261114
**First integration:** 2026-11-14, CI run 43590234175 (PASS).

## Scientific goal, not speed

Test whether a nonlinear information gap exposed by an EXACT local join
can be converted into a reusable, conditional, source-entailed equality
between Boolean variables during live CDCL solving.

The antecedent is a real SAT2024 hardware-miter CNF (ID30, original SHA
ead2a1c2fb44d173d3a24bab1212f07adf571f4fc7563392d434e0f58386939b).
No source names, labels, or known answers are read by the solver to select a
candidate. The older DELTA2 exact-pair nonlinearity witness activates a
bounded source clause search; no inference is accepted from the statistical
signal alone.

## Logic and original-CNF reason

For any matched pair of ORIGINAL clauses that resolve in one step to

    (not a OR b OR guard)

and an independently existing ORIGINAL binary reverse clause

    (a OR not b),

the formula entails

    (not guard) => (a <=> b).

The guard must be FALSE on the live CDCL trail before creating an alias
record. The full three-literal resolvent is globally sound and remains in
the learned clause database with proof logging. If the guard is later
undone, the learned clause itself remains valid but the conditional alias
does NOT remain active.

DELTAX currently handles same-polarity equalities. It deliberately does
not turn a conditional alias into a global unconditional XOR equality.

## Live architecture

* Extends the existing original-clause JOIN engine, with a new DELTAX mode.
* Detects only exact guarded two-way implications, with an original binary
  reverse leg and a one-step resolvent of two ORIGINAL clauses.
* ON emits the three-literal RUP-consequence through the normal CDCL
  learned-clause bridge, which uses ordinary watches, reasons, conflict
  analysis and backtracking. SHADOW reports validated candidates without
  injection; the same compiled binary supports both.
* Maintains a read-only guarded-equivalence tracker that recomputes active
  equivalence classes when guard assignments change and after backtracking.
* Marks DELTAX-origin CDCL clauses and counts their use as propagation or
  conflict reasons (independently of alias activation count).
* No physical variable ID substitution, no rewrite of the CDCL trail, no
  unproved unit enqueue, no solver/benchmark promotion, no main changes.

The distinction between a mathematical equivalence, a RUP-checked clause,
a watched clause actually entered into CDCL, and a reason that CDCL used
is measured and is NEVER collapsed into one "speedup" metric.

## First independent integration results

GitHub Actions run 43590234175: PASS.
* 28 small oracle solver runs, 8 independently checked UNSAT cases.
* Original SAT2024 hardware-miter ID30: 2 verified guarded-alias events in
  both SHADOW and ON, 2 RUP source-derived clauses installed in ON.
* Live alias-guard tracker: 1852 activations, 1851 deactivations,
  maximum two variable identities merged in the observational tracker
  (three identities represented by one when both guards hold).
* **Important negative result:** 0 CDCL reason uses and 0 CDCL conflict uses
  attributed to the two newly installed clauses within the short experiment.
  The integration is real, but no causal search benefit has yet been shown.
* Real ID30 attempt ended UNKNOWN within its cap; no SAT/UNSAT claim.
* Source-verified original-CNF clauses and all small SAT models/UNSAT proof
  checks passed. We have not benchmarked runtime speed.

## Next semantic milestone

Make an automatically discovered guarded equality causally useful:
show at least one *actual* CDCL assignment or conflict whose reason is a
DELTAX-origin proof clause, or demonstrate a safe conditional decision
canonicalization without changing the solution set. Prefer source-disjoint
examples; compare with ordinary BCP/binary implication closure. Only after
these semantic milestones is performance optimization warranted.

This is established Boolean logic, resolution and relational joins; DELTAX
is an experimental integration policy, not an established new theorem.
