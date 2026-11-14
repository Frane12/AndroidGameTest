# DRNAS ΔCOOP3 — using a real nonlinear separator signal

**Status:** isolated proof-first experiment, not a new mathematical theorem or a promoted solver.
Source branch: experiment/drnas-deltacoop3-nonlinear-clause-20261114.
Frozen DELTA2 original SAT2024 REAL36 inputs and reference binaries are not edited.

## Exact observed motivation

DELTA2 run 43584992768, real hardware-miter source ID30, produced the same independently
checked nonlinear tuple witness in both repeats (under assumptions -771, -772).
Original source clauses include:

- left: [1,-3,771], [-1,-3,777] (and other clauses)
- right: [-1,3,772] (and other clauses)

The conditional x1=x3 relation is obtained by joining two exact local tables,
even though the affine hulls of the two local tables separately permit the
blocked tuple. This is **local nonlinear-to-linear information loss**, not
a new complexity-class theorem. It does not by itself imply a globally
unconditional XOR clause or a speed improvement.

The right clause [-1,3,772] and left clause [-1,-3,777] resolve on x3:

    [-1,772,777]

This clause is RUP under its original two parents and was absent from that
original source. Unlike a conditional XOR shortcut, it is a globally sound
CNF implication with all original guard literals retained.

## ΔCOOP3 policy

Existing exact pair joining and affine-countermodel witness screening are
unchanged. **Only upon an independently checkable nonlinear tuple witness**,
scan at most 192 cross-block original clause pairs and generate a bounded
set of short non-tautological one-step resolvents. Reject originals,
subsumed clauses, satisfied clauses and clauses longer than 3 literals.
Emit at most 2 new clauses per witness, 4 witness probes and 8 clauses
per pass. Inherited delayed gate: 64 conflicts; inherited 30ms algebra
budget, 24 passes, 256 learned clauses and 8192 proof steps.

No assertion is based solely on a statistical, spectral or nonlinear
candidate; the activation signal only determines when to *look* for
one-step **original-CNF RUP** clauses. Every injected clause is written
to DRAT before insertion into the actual CDCL clause database.

This experiment tests the **specific witness-gated short-resolution
engineering policy**, not novelty of resolution, joins or XOR.

## Controlled matched comparison

OFF and JOIN: frozen DELTA2 binary; BRIDGE-SHADOW and BRIDGE: same
new DELTA3 binary with cross-resolution off/on, plus frozen Kissat and
CaDiCaL. 36 source-SHA-fixed retrospective SAT2024 CNFs, 2 repeats,
6 arms, 5s per attempt: 432 source-paired trials. A single logical
CPU for each serial solver. SAT assignments are checked against the
original source; all credited UNSAT verdicts require an independently
checked original-source DRAT proof. Bridge lemma events are independently
checked against their original parent clauses, including the exact
resolution pivot and unit-propagation RUP.

Primary outcomes:
1. Whether the true real witness yields the exact expected short RUP clause;
2. Whether NEW BRIDGE clauses are actually injected on original CNFs;
3. Actual subsequent CDCL reason use, conflicts, decisions and time;
4. Verified solved cases and PAR-2 including extraction and proof overhead.

No model promotion, and no claim of statistical superiority from this
retrospective cohort. If promising, test on a fresh SHA-disjoint, family-
separated sealed holdout and require >=10% verified PAR-2 improvement,
positive uncertainty margin, and no invalid proofs.
